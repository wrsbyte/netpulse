"""The sampling daemon.

Schedules every probe on its configured cadence (APScheduler), persists results, and derives
the discrete events that matter: outages (all internet targets down at once — labelled WiFi vs
ISP by whether the gateway also failed), AP roaming (BSSID change), and public-IP changes.
Runs the downsampling rollup on the rollup cadence. Designed to degrade: a probe that raises is
logged and skipped, the rest keep sampling.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable, Iterator

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from netpulse.aggregation import run_rollups
from netpulse.config import NetpulseConfig, Settings, get_config, get_settings
from netpulse.db.migrate import _NETWORK_SCOPED_TABLES
from netpulse.db.models import (
    AnycastPop,
    Event,
    FlowQuality,
    HopLocation,
    Network,
    RegionalBaseline,
    State,
    Traceroute,
)
from netpulse.db.session import get_session, init_engine
from netpulse.external import ripe_atlas, ripe_stat
from netpulse.logging import configure_logging, get_logger
from netpulse.probes import (
    active,
    anycast,
    dns,
    flow_quality,
    flows,
    network,
    ping,
    public_ip,
    tcp_connect,
    throughput,
    traceroute,
    wifi,
    wifi_events,
    wifi_scan,
)
from netpulse.shell import run as shrun

log = get_logger("collector")

_OUTAGE_CYCLES = 3  # consecutive all-internet-down ping cycles before an outage is declared
_HOP_GEO_BATCH = 16  # new hop/flow IPs to geolocate per run, gentle on the free RIPEstat endpoint


def _is_public_ip(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_global
    except ValueError:
        return False


class Collector:
    def __init__(self, settings: Settings, config: NetpulseConfig) -> None:
        self.settings = settings
        self.config = config
        self.iface = config.interface
        self.scheduler = AsyncIOScheduler()
        self._last_bssid: str | None = None
        self._network_id: int | None = None
        self._outage_streak = 0

    async def start(self) -> None:
        if not self.iface:
            self.iface = await _detect_iface()
        await self._sync_network()
        if self._network_id is not None:
            self._backfill_network(self._network_id)
        await self._guard(self._anycast)()  # capture the serving POP immediately (long cadence)
        await self._guard(self._regional_baseline)()  # seed the outside-in baseline at startup
        await self._guard(self._wifi_events)()  # backfill recent disconnects immediately
        await self._guard(self._wifi_scan)()  # a full neighbour scan for channel congestion
        await self._guard(self._hop_geo)()  # geolocate the current route's hops for the map
        log.info("starting", iface=self.iface, targets=len(self.config.targets),
                 network_id=self._network_id)
        self._schedule()
        self.scheduler.start()

    def _schedule(self) -> None:
        iv = self.config.intervals
        add = self.scheduler.add_job
        add(self._guard(self._sync_network), "interval", seconds=iv.network)
        add(self._guard(self._ping), "interval", seconds=iv.ping)
        add(self._guard(self._tcp_connect), "interval", seconds=iv.tcp_connect)
        add(self._guard(self._wifi), "interval", seconds=iv.wifi)
        add(self._guard(self._wifi_events), "interval", seconds=iv.wifi_events)
        add(self._guard(self._throughput), "interval", seconds=iv.throughput)
        add(self._guard(self._dns), "interval", seconds=iv.dns)
        add(self._guard(self._flows), "interval", seconds=iv.flows)
        add(self._guard(self._flow_quality), "interval", seconds=iv.flow_quality)
        add(self._guard(self._traceroute), "interval", seconds=iv.traceroute)
        add(self._guard(self._wifi_scan), "interval", seconds=iv.wifi_scan)
        add(self._guard(self._public_ip), "interval", seconds=iv.public_ip)
        add(self._guard(self._anycast), "interval", seconds=iv.anycast)
        add(self._guard(self._regional_baseline), "interval", seconds=iv.regional)
        add(self._guard(self._hop_geo), "interval", seconds=iv.hop_geo)
        add(self._guard(self._rollup), "interval", seconds=iv.rollup)
        if self.config.active.enabled:
            add(self._guard(self.run_active), "interval", seconds=self.config.active.interval)

    def _guard(self, fn: Callable[[], Awaitable[None]]) -> Callable[[], Awaitable[None]]:
        async def wrapper() -> None:
            try:
                await fn()
            except Exception:
                log.exception("probe failed", probe=fn.__name__)

        wrapper.__name__ = fn.__name__
        return wrapper

    # --- probe jobs --------------------------------------------------------

    async def _ping(self) -> None:
        now = time.time()
        results = await asyncio.gather(
            *(ping.sample(now, t.host) for t in self.config.targets)
        )
        self._stamp(results)
        with _session() as s:
            s.add_all(results)
            self._detect_outage(s, now, results)
            s.commit()

    async def _wifi(self) -> None:
        row = await wifi.sample(time.time(), self.iface)
        if row is None:
            return
        self._stamp([row])
        with _session() as s:
            s.add(row)
            self._detect_roaming(s, row.ts, row.bssid)
            s.commit()

    async def _tcp_connect(self) -> None:
        targets = [
            (t.host, 443) for t in self.config.targets if t.kind in ("internet", "site", "work")
        ]
        self._persist(await tcp_connect.sample(time.time(), targets))

    async def _throughput(self) -> None:
        row = await throughput.sample(time.time(), self.iface)
        if row is not None:
            self._persist([row])

    async def _dns(self) -> None:
        now = time.time()
        jobs = [
            dns.sample(now, d, r)
            for d in self.config.dns.domains
            for r in ["", *self.config.dns.resolvers]
        ]
        self._persist(await asyncio.gather(*jobs))

    async def _flows(self) -> None:
        self._persist(await flows.sample(time.time(), self.iface))

    async def _flow_quality(self) -> None:
        self._persist(await flow_quality.sample(time.time(), self.iface))

    async def _traceroute(self) -> None:
        now = time.time()
        for target in self.config.targets:
            self._persist(await traceroute.sample(now, target.host))

    async def _wifi_events(self) -> None:
        now = time.time()
        with _session() as s:
            wm = s.get(State, "wifi_disc_watermark")
            since_ts = float(wm.value) if wm else now - 86400  # first run: backfill 24h
            discs = await wifi_events.since(since_ts)
            for d in discs:
                s.add(Event(
                    ts=d.ts, end_ts=d.ts, kind="wifi_disconnect", severity="info",
                    detail=f"reason={d.reason} {'local' if d.local else 'remote'}",
                    network_id=self._network_id,
                ))
            newest = max((d.ts for d in discs), default=since_ts)
            self._upsert_state(s, "wifi_disc_watermark", str(max(newest, since_ts)))
            s.commit()

    async def _wifi_scan(self) -> None:
        self._persist(await wifi_scan.sample(time.time(), self.iface))

    async def _public_ip(self) -> None:
        v4, v6 = await public_ip.sample()
        with _session() as s:
            for family, value in (("ipv4", v4), ("ipv6", v6)):
                if value is None:
                    continue
                self._track_ip_change(s, family, value)
            s.commit()

    async def _regional_baseline(self) -> None:
        rtts = await ripe_atlas.regional_rtts("MX")
        if not rtts:
            return
        now = time.time()
        user = await ping.sample(now, ripe_atlas.K_ROOT_IP)  # our own RTT to the same reference
        with _session() as s:
            s.add(RegionalBaseline(
                ts=now, source="ripe_atlas", target=ripe_atlas.K_ROOT_IP, country="MX",
                metric="rtt_ms", values_json=json.dumps(rtts), n=len(rtts),
            ))
            if user.rtt_avg is not None:
                self._upsert_state(s, "kroot_rtt", str(user.rtt_avg))
            public = s.get(State, "public_ipv4")
            if public is not None:
                bgp = await ripe_stat.bgp_summary(public.value)
                if bgp is not None:
                    self._upsert_state(s, "bgp_updates", str(bgp.total))
                    self._upsert_state(s, "bgp_stable", "1" if bgp.stable else "0")
            s.commit()
        log.info("regional baseline updated", country="MX", n=len(rtts))

    async def _hop_geo(self) -> None:
        """Geolocate new public traceroute-hop IPs AND the endpoints of active flows via RIPEstat,
        cached — so the map can draw the real route and place every service you talk to. A few per
        run; private/unlocatable IPs are skipped."""
        since = time.time() - 3600
        with _session() as s:
            hop_ips = {
                h for h in s.scalars(
                    select(Traceroute.host).where(Traceroute.ts >= since).distinct()
                ).all() if h
            }
            hop_ips |= {
                ip for ip in s.scalars(
                    select(FlowQuality.remote_ip).where(FlowQuality.ts >= since).distinct()
                ).all() if ip
            }
            cached = set(s.scalars(select(HopLocation.ip)).all())
        todo = [ip for ip in hop_ips if ip not in cached and _is_public_ip(ip)]
        for ip in todo[:_HOP_GEO_BATCH]:
            loc = await ripe_stat.geolocate(ip)
            with _session() as s:
                s.add(HopLocation(
                    ip=ip, ts=time.time(), located=loc is not None,
                    lat=loc.lat if loc else None, lon=loc.lon if loc else None,
                    city=loc.city if loc else None, country=loc.country if loc else None,
                ))
                s.commit()
        if todo:
            log.info("hop geo updated", new=min(len(todo), _HOP_GEO_BATCH))

    def _upsert_state(self, s: Session, key: str, value: str) -> None:
        state = s.get(State, key)
        if state is None:
            s.add(State(key=key, value=value))
        else:
            state.value = value

    async def _anycast(self) -> None:
        rows = await anycast.sample(time.time())
        if not rows:
            return
        self._stamp(rows)
        with _session() as s:
            for row in rows:
                self._detect_pop_flip(s, row)
                s.add(row)
            s.commit()

    def _detect_pop_flip(self, s: Session, row: AnycastPop) -> None:
        prev = s.scalars(
            select(AnycastPop)
            .where(AnycastPop.provider == row.provider, AnycastPop.target == row.target)
            .order_by(AnycastPop.ts.desc())
            .limit(1)
        ).first()
        if prev and prev.colo and row.colo and prev.colo != row.colo:
            s.add(Event(
                ts=row.ts, end_ts=row.ts, kind="pop_flip", severity="info",
                detail=f"{row.provider} {row.target}: {prev.colo} -> {row.colo}",
                network_id=self._network_id,
            ))
            log.info("anycast POP flip", provider=row.provider, frm=prev.colo, to=row.colo)

    async def run_active(self) -> None:
        row = await active.sample(time.time())
        if row is not None:
            self._persist([row])

    async def _rollup(self) -> None:
        with _session() as s:
            run_rollups(s, self.config.retention, time.time())

    # --- derived events ----------------------------------------------------

    def _detect_outage(self, s: Session, now: float, results: list) -> None:  # type: ignore[type-arg]
        by_host = {r.target: r for r in results}
        internet = [t for t in self.config.targets if t.kind in ("internet", "site", "work")]
        gateway = [t for t in self.config.targets if t.kind == "lan"]
        down = bool(internet) and all(by_host[t.host].loss_pct >= 100 for t in internet)
        # Require several consecutive failing cycles so one Wi-Fi hiccup doesn't flap an outage.
        self._outage_streak = self._outage_streak + 1 if down else 0
        open_event = _open_event(s, "outage")
        if self._outage_streak >= _OUTAGE_CYCLES and open_event is None:
            gw_down = any(by_host[t.host].loss_pct >= 100 for t in gateway)
            cause = "wifi/lan" if gw_down else "isp"
            s.add(Event(ts=now, end_ts=None, kind="outage", severity="error", detail=cause,
                        network_id=self._network_id))
            log.warning("outage started", cause=cause, cycles=self._outage_streak)
        elif not down and open_event is not None:
            open_event.end_ts = now
            log.info("outage cleared", duration=round(now - open_event.ts, 1))

    def _detect_roaming(self, s: Session, now: float, bssid: str | None) -> None:
        if bssid and self._last_bssid and bssid != self._last_bssid:
            s.add(Event(
                ts=now, end_ts=now, kind="roam", severity="info",
                detail=f"{self._last_bssid} -> {bssid}", network_id=self._network_id,
            ))
            log.info("roamed", from_bssid=self._last_bssid, to_bssid=bssid)
        if bssid:
            self._last_bssid = bssid

    def _track_ip_change(self, s: Session, family: str, value: str) -> None:
        key = f"public_{family}"
        state = s.get(State, key)
        if state is None:
            s.add(State(key=key, value=value))
            return
        if state.value != value:
            s.add(Event(
                ts=time.time(), end_ts=time.time(), kind="ip_change", severity="info",
                detail=f"{family}: {state.value} -> {value}", network_id=self._network_id,
            ))
            log.info("public ip changed", family=family, old=state.value, new=value)
            state.value = value

    def _persist(self, rows: list) -> None:  # type: ignore[type-arg]
        rows = [r for r in rows if r is not None]
        if not rows:
            return
        self._stamp(rows)
        with _session() as s:
            s.add_all(rows)
            s.commit()

    def _stamp(self, rows: list) -> None:  # type: ignore[type-arg]
        """Tag rows with the current network so every sample is attributable."""
        if self._network_id is None:
            return
        for row in rows:
            if getattr(row, "network_id", "missing") is None:
                row.network_id = self._network_id

    async def _sync_network(self) -> None:
        fp = await network.detect()
        if fp is None:
            return  # no default route = offline; keep the last known network
        now = time.time()
        with _session() as s:
            net = s.scalars(select(Network).where(Network.key == fp.key)).first()
            if net is None:
                net = Network(
                    key=fp.key, ssid=fp.ssid, bssid=fp.bssid, gateway_ip=fp.gateway_ip,
                    gateway_mac=fp.gateway_mac, interface=fp.interface,
                    label=fp.ssid or "Wired", first_seen=now, last_seen=now,
                )
                s.add(net)
                s.flush()
            else:
                net.last_seen = now
                net.bssid = fp.bssid or net.bssid
            changed = self._network_id is not None and self._network_id != net.id
            self._network_id = net.id
            if changed:
                s.add(Event(
                    ts=now, end_ts=now, kind="network", severity="info",
                    detail=f"switched to {net.label or net.key}", network_id=net.id,
                ))
                log.info("network changed", to_id=net.id, key=fp.key)
            s.commit()

    def _backfill_network(self, network_id: int) -> None:
        """One-time: seed existing rows (all taken on today's single network) with it."""
        with _session() as s:
            if s.get(State, "network_backfilled") is not None:
                return
            for table in _NETWORK_SCOPED_TABLES:
                s.execute(
                    text(f"UPDATE {table} SET network_id = :nid WHERE network_id IS NULL"),
                    {"nid": network_id},
                )
            s.add(State(key="network_backfilled", value="1"))
            s.commit()


@contextlib.contextmanager
def _session() -> Iterator[Session]:
    session = get_session()
    try:
        yield session
    finally:
        session.close()


def _open_event(s: Session, kind: str) -> Event | None:
    return s.scalars(
        select(Event).where(Event.kind == kind, Event.end_ts.is_(None))
    ).first()


_ROUTE_DEV = re.compile(r"\bdev\s+(\S+)")


async def _detect_iface() -> str:
    res = await shrun("ip", "route", "get", "1.1.1.1", timeout=4)
    m = _ROUTE_DEV.search(res.stdout)
    return m.group(1) if m else "wlan0"


async def _run_forever() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)  # one line per job is noise
    init_engine(settings.db_path)
    collector = Collector(settings, get_config())
    await collector.start()
    await asyncio.Event().wait()  # run until killed


def main() -> None:
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_run_forever())
