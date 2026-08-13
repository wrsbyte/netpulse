# netpulse — local network health & analysis

A professional, always-on **local** network monitor for this PC (CachyOS, WiFi). Samples connectivity,
WiFi quality, DNS, routing, throughput and endpoints into a local time-series DB, and serves a modern
ECharts + Tailwind dashboard with **6h / 24h / 7d** views. Built to answer: *why does my internet fail?*

> Environment (discovered): CachyOS, uplink = **WiFi `wlan0`** (SSID "CASA RODRIGUEZ COLLAZO 5G",
> 192.168.100.99/24, gw 192.168.100.1, IPv6 present), DNS = systemd-resolved (Quad9 fallback). Heavy
> Docker (many `br-*`/`veth*` — ignored; only `wlan0` is the uplink). `sudo` needs a password.

## Why this design

The symptom is "internet fails on WiFi." On WiFi the usual culprits are **radio quality** (weak signal,
retries, AP roaming, channel congestion) and the **ISP path** (packet loss beyond the gateway), not the
laptop. So the tool must **separate the layers**: is it the WiFi link, the LAN/gateway, the ISP, or DNS?
It does that by measuring each hop independently at the same time.

## Architecture

- **collector** (`collector.py`, Python, runs as your user via a `systemd --user` service — starts on
  login, runs whenever the PC is on). No root needed for the core metrics. Optional root-only modules are
  toggled by config if you enable them.
- **storage** — SQLite (`data/netpulse.db`). Raw samples for 6h/24h; a downsampling job rolls old rows
  into 1-min then 5-min aggregates so 7d stays small and fast. WAL mode; retention configurable.
- **server** (`server.py`, Python stdlib `http.server`, localhost only) — serves the dashboard and a JSON
  API (`/api/series?metric=…&range=6h|24h|7d`) with server-side downsampling.
- **dashboard** (`web/`, static) — ECharts + Tailwind, **vendored locally** (no CDN — it must work while
  the internet is down). Dark/light, responsive, keyboard-friendly.

Everything self-contained under `~/Projects/wrsbyte/netpulse/`. Start/stop with one command.

## What it measures

### 1. Connectivity & latency (the layer-separator)
Ping every ~2–5 s to a set of targets, each isolating a layer — RTT (min/avg/max), **packet loss %**,
**jitter**, IPv4 vs IPv6:
- `192.168.100.1` (gateway) — is the **WiFi/LAN** healthy?
- ISP first hop (from traceroute) — is the **last mile** healthy?
- `1.1.1.1`, `8.8.8.8`, `9.9.9.9` — is the **internet** healthy?
- a couple of real endpoints (e.g. `google.com`) and **your work hosts** (titan `131.153.202.57`, demo
  node `131.153.11.143`) — since those dropped for you earlier, we watch them directly.

### 2. WiFi radio quality (prime suspect) — `iw dev wlan0 link` / `station dump`
Every ~5 s: **signal (dBm)**, signal/noise, **TX/RX bitrate (Mbps)** + MCS/width, **TX retries**,
**TX failed**, RX drops, **BSSID** (detect AP roaming), channel/frequency, beacon loss, inactivity.
Retries/failed climbing or signal dropping → the problem is the radio, not the ISP.

### 3. DNS — via `dig`/`resolvectl`
Resolution time for several domains against the local resolver **and** directly against public resolvers;
failures; which server answered; detect slow/failing DNS (a very common "internet feels broken" cause).

### 4. Routing / path — `tracepath` (or `mtr` if installed)
Periodic (~1–5 min) hop-by-hop latency + loss to key targets → shows **where** loss starts (your AP vs the
ISP vs beyond). Detects **route changes** and default-gateway changes.

### 5. Throughput & usage — `/proc/net/dev` deltas on `wlan0`
RX/TX rate (Mbps) sampled continuously; cumulative data used per hour/day. (Optional per-process "who's
using the network" via `nethogs` — needs root.)

### 6. Endpoints / CDNs — `ss -tanp` + reverse DNS + ASN
Snapshot active connections → remote IPs → rDNS + ASN (Team Cymru whois or a local map) → **top
destinations and CDNs** you talk to, aggregated over time. (Per-process attribution needs root.)

### 7. Public IP, route & outage detection
Public IPv4/IPv6 (lightweight check) + change detection; **outage detection** = when *all* internet
targets fail at once → log outage start/end + duration (the headline number for "internet falla"),
distinguishing a WiFi drop (gateway also fails) from an ISP outage (gateway OK, internet fails).

### 8. Active bandwidth (optional) — speedtest
Periodic down/up/latency test (Ookla `speedtest` or a light HTTP download). **Consumes data**, so it's
opt-in with a configurable cadence + an on-demand button.

## Pro features distilled from real tools (researched)

What the professional tools do that a "basic" pinger doesn't — netpulse adopts all of these:

- **SmokePing → "smoke" latency bands + smart alerting.** Instead of a single RTT line, draw the median
  with a shaded **percentile band** (p25–p75, p95) so you *see* the jitter/variance. Alerting is
  **threshold + pattern based** (e.g. "loss >20% sustained >10 min", "RTT p95 >3× baseline for 5 min") →
  fires a desktop notification (`notify-send`) and logs the event.
- **PingPlotter / ThousandEyes → per-hop latency timeline.** Combine the traceroute path with continuous
  per-hop pings so the dashboard shows **which hop degrades over time** (your AP? the ISP? beyond?), not
  just end-to-end. Path/route-change history.
- **Bufferbloat.net methodology → latency-under-load (the headline for "unstable meetings/games").** Measure
  idle RTT baseline, then RTT **while a download/upload runs** → report loaded median, **p95 tail**, loaded
  jitter, and a **bufferbloat grade (A–F)**. High latency-under-load = laggy calls even when "speed" looks
  fine. This is very likely part of your problem.
- **Telco E-model → MOS (call quality score).** Derive a **Mean Opinion Score (1–5)** from latency + jitter
  + loss so you get a "your calls would sound like: 4.1/5" number, and see when it drops.
- **Composite quality score (A–F).** A weighted score per range (latency 25% · jitter 20% · bufferbloat 30%
  · loss 15% · throughput 10%) — one glanceable grade for "how good was my internet in the last 6h/24h/7d".
- **ntopng → flow & application classification.** Beyond "top IPs": classify flows by **application/service**
  (SNI hostname from TLS ClientHello via optional `tcpdump`, else rDNS + ASN) → "you spent X on Google
  Meet / YouTube / GitHub", top talkers, protocol mix, historical per-app bandwidth.
- **Netdata → per-second granularity + health.** Fast sampling on the cheap metrics, real-time feel, and a
  health/anomaly view (rolling baselines → flag when a metric is anomalously bad).
- **WiFi analyzer (NetSpot/iw) → channel-congestion scan + roaming.** Periodically `iw scan` neighbors →
  **APs per channel + their RSSI** → congestion map and a **"switch to channel N" recommendation**; combine
  RSSI + SNR + **TX retries** to distinguish *weak signal* vs *interference*; log AP roaming (BSSID changes).

## Dashboard (6h / 24h / 7d, ECharts)

- **Status bar:** online/offline now, current RTT + loss, WiFi signal + bitrate, public IP, uptime,
  outages in range, data used.
- **Latency (multi-line)** per target + a **loss** band; **jitter**.
- **WiFi:** signal + bitrate + retries (dual-axis); BSSID/roaming markers.
- **Throughput** RX/TX + cumulative usage.
- **DNS** resolution time (per resolver) + failure markers.
- **Outages timeline** (bars) with cause (WiFi vs ISP vs DNS).
- **Top destinations / CDNs** table (by connections/bytes, with ASN).
- **Traceroute** latest hop-latency + a **route-change / events log** (disconnects, IP changes, DNS fails).

7d uses 5-min aggregates; 24h uses 1-min; 6h uses raw — kept fast by server-side downsampling.

## Privileges

Core metrics (ping, wifi via `iw`, dns via `dig`, interface counters, `ss`, routes) run **as your user, no
root**. Root-only extras — per-process bandwidth (`nethogs`), connection tracking (`conntrack`), raw-socket
`mtr` — are **optional**, enabled only if you grant a scoped `NOPASSWD` sudoers entry or `setcap`. The tool
degrades gracefully: missing tool/permission → that module is skipped, everything else keeps working.

## Optional tools (pacman) that add data

`mtr` (better traces than tracepath), `traceroute`, `speedtest-cli`/ookla `speedtest` (active bandwidth),
`vnstat` (historical usage), `nethogs` (per-process, root), `conntrack-tools` (deep conn tracking, root).
None are required to start; each unlocks a module.

## Deliverables

```
netpulse/
├── collector.py         # the sampling daemon (config-driven, graceful degradation)
├── server.py            # localhost dashboard + JSON API (downsampling)
├── config.toml          # targets, intervals, retention, feature toggles
├── netpulse.sh          # start|stop|status|logs helper
├── systemd/netpulse.service  # user service (autostart)
├── schema.sql           # SQLite tables + retention/rollup
├── web/                 # index.html + app.js + ECharts/Tailwind vendored
└── data/netpulse.db     # the time-series store (gitignored)
```
