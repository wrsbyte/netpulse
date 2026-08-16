# Architecture

## Goal

Attribute network problems to a **layer** — WiFi radio, LAN/gateway, ISP, or DNS — by
measuring each independently and simultaneously. Everything is local, single-host, and cheap
enough to run continuously.

## Two processes, one store

```
                    ┌──────────────────────────┐
  probes ──samples─▶│  collector (APScheduler)  │──writes──┐
                    └──────────────────────────┘           ▼
                                                      ┌───────────┐
                    ┌──────────────────────────┐      │  SQLite   │
  browser ──HTTP───▶│  API + SPA (FastAPI)      │◀─────│  (WAL)    │
                    └──────────────────────────┘ reads └───────────┘
```

- **collector** (`collector.py`) schedules every probe on its own cadence, persists results,
  and derives discrete **events** (outages, roaming, IP changes). It never lets one failing
  probe stop the others — each job is wrapped so an exception is logged and skipped.
- **API** (`api/app.py`) serves the JSON endpoints and, in production, the built SPA from
  `frontend/dist`. Read-only; bound to localhost.
- **store** — one SQLite file in WAL mode so the API reads while the collector writes.

Splitting collection from serving means the dashboard can restart, crash, or be absent
without losing a single sample.

## Data model

One **raw table per probe** (`ping_raw`, `wifi_raw`, `throughput_raw`, `dns_raw`, …),
append-only, indexed by timestamp. A generic **`agg`** table holds downsampled rollups: one
row per `(bucket, resolution, metric, tag)` with avg/min/max/p95/n. Operational tables:
`event` (discrete incidents, with an `end_ts` for ongoing ones) and `state` (collector
key/value: last counters, public IP).

### Provenance (which code measured this row)

Every sample carries a `code_version` (on the `NetworkScoped` mixin, stamped by the collector next
to `network_id`) and the collector records each version + git SHA in a `data_version` registry at
startup. The package semver is bumped by **data impact**, so a query can trust or exclude rows by
how they were measured. Full design: [DATA_VERSIONING.md](DATA_VERSIONING.md); per-version trust
notes: [DATA_VERSIONS.md](DATA_VERSIONS.md).

### Downsampling & retention

The rollup job (every 5 min) recomputes a bounded recent window idempotently:

```
raw  ──5-min buckets──▶  agg("5m")  ──1-hour buckets──▶  agg("1h")
```

The dashboard range picks the resolution — **6 h reads raw, 24 h reads 5-min, 7 d reads
1-hour** — so a week of history is a few hundred rows, not millions. Retention prunes raw
after 48 h, 5-min after 14 d, 1-hour after ~400 d (all configurable).

## Probes

Each probe is a small async function that shells out to a system tool via `shell.run` (a
timeout-guarded, injection-safe wrapper) and returns ORM rows. Parsing lives in the probe;
pure transforms are factored out for unit testing (e.g. `flows.extract_remotes`,
`quality.mos`). A probe with a missing tool returns nothing and is skipped.

| Probe | Tool | Layer it isolates |
|-------|------|-------------------|
| ping | `ping` | connectivity/latency/loss/jitter per target |
| wifi | `iw` | radio: signal, bitrate, retries, BSSID (roaming), noise |
| throughput | `/sys/class/net` counters | uplink RX/TX |
| dns | `dig` | resolution time/success per resolver |
| traceroute | `mtr`→`tracepath` | per-hop loss/RTT (where loss starts) |
| flows | `ss` + rDNS + Team Cymru ASN | who we talk to, classified by app/CDN |
| wifi_scan | `nmcli` | neighbor APs per channel (congestion) |
| public_ip | `curl` | egress IP + change detection |
| active | `speedtest` | bandwidth + bufferbloat (loaded latency) |

## Derived signal

- **Outage** = all internet-tagged targets at 100 % loss at once. Labelled `wifi/lan` if the
  gateway also failed, else `isp` — the single most useful attribution.
- **Bufferbloat grade** (A+…F) from loaded − idle latency; **MOS** (1–5) from the E-model.
  Pure functions in `quality.py`, unit-tested.

netpulse is a diagnostic dashboard, not a notifier: the verdict, events and Routes surface the
state — there are no threshold alerts or desktop notifications.

## Frontend

React + TypeScript, Vite build, Tailwind v4 (`@theme` tokens), ECharts (tree-shaken core).
TanStack Query polls the API every 15 s; Zustand holds the selected range. A thin `Chart`
wrapper owns the ECharts lifecycle (init / setOption / resize / dispose); each panel builds a
typed `EChartsOption`. The API serves the built bundle, so there is no separate web server in
production.
