# netpulse

A local, always-on **network health & analysis** tool for a single host. It samples
connectivity, WiFi radio quality, DNS, routing, throughput and endpoints into a local
time-series store and serves a modern ECharts dashboard with **6 h / 24 h / 7 d** views.

Built to answer one question precisely: *when my internet fails, is it the WiFi radio, the
LAN/gateway, the ISP, or DNS?* It measures each layer independently and at the same time, so
an outage can be attributed rather than guessed.

## Monorepo layout

```
netpulse/
├── backend/        # Python — collector (APScheduler) + FastAPI API + SQLite store
│   ├── src/netpulse/
│   │   ├── probes/     # one module per measurement (ping, wifi, dns, flows…)
│   │   ├── db/         # SQLAlchemy 2.0 models + session
│   │   ├── api/        # FastAPI app, routers, read queries
│   │   ├── collector.py    aggregation.py  alerts.py  quality.py  config.py
│   ├── tests/      # pytest (pure logic + probe-parsing regressions)
│   └── config.toml # the monitoring plan (targets, intervals, alerts)
├── frontend/       # React + TypeScript + Vite + Tailwind + ECharts dashboard
├── systemd/        # user services (autostart on login)
├── scripts/        # doctor.sh + optional sudoers.d/netpulse
└── docs/           # ARCHITECTURE.md, CONVENTIONS.md
```

Two processes, one SQLite file: the **collector** writes samples; the **API** reads them and
serves the SPA. Both are localhost-only.

## Quick start

```bash
make setup            # uv sync + pnpm install
make build            # build the dashboard into frontend/dist
make install-services # systemd --user: collector + api, autostart on login
# open http://127.0.0.1:8477
```

Develop with live reload instead:

```bash
make collector   # terminal 1 — start sampling
make api         # terminal 2 — API on :8477
make dev         # terminal 3 — Vite on :5173 (proxies /api)
```

Verify the environment and see which optional tools are installed:

```bash
make doctor
```

## What it measures

Connectivity/latency/loss/jitter per layer · WiFi signal/bitrate/retries/roaming · DNS timing
per resolver · path (per-hop loss via `mtr`) · interface throughput · active bandwidth +
**bufferbloat grade** and **MOS** · top destinations classified by app/CDN + ASN · derived
**events** (outages labelled WiFi-vs-ISP, roaming, IP changes) and **threshold alerts** with
desktop notifications.

Core metrics need **no root**. Optional extras (per-hop loss via raw-socket `mtr`) use a
scoped `NOPASSWD` sudoers entry — see `scripts/sudoers.d/netpulse`. Missing tool or
permission → that probe is skipped, everything else keeps running.

## Configuration

- **Monitoring plan** — `backend/config.toml`: targets (each tagged with the layer it
  isolates), sampling intervals, retention, active-test cadence, DNS domains/resolvers, alert
  rules.
- **Runtime** — environment variables (`NETPULSE_DB_PATH`, `NETPULSE_PORT`, …); see
  `Settings` in `backend/src/netpulse/config.py`.

See `docs/ARCHITECTURE.md` for how the pieces fit and `docs/CONVENTIONS.md` for the coding
standards this repo follows.
