# Roadmap

Where netpulse is, and where it goes next. The north star: the system should not just
*display* metrics — it should **analyze, attribute, and conclude**. A non-technical user opens
it and reads a verdict: *"your internet was degraded 8 % of the last 24 h; root cause =
packet loss starting at ISP hop 8; your WiFi was healthy."*

## Current state (v0.2)

Probes: ping (IPv4 **and IPv6**), wifi, wifi_events, dns (plain **and DoT**), throughput,
tcp_connect, traceroute/mtr, flows, flow_quality (passive TCP `ss -ti`), **media (UDP/QUIC
call/game path)**, wifi_scan, public_ip, anycast (CDN POP), regional (RIPE Atlas), hop_geo
(RIPEstat geolocation), active/Ookla. SQLite with raw→5m→1h rollups + retention (**all
append-only tables pruned**, composite indexes). FastAPI + React dashboard (6h/24h/7d), first-class
network identity, raw-data explorer (`api/raw_queries.py`) with CSV export.

Analyzes and concludes: A–F health score, automatic loss **attribution** to a layer/hop,
per-activity **experience** ratings (calls use the real UDP path when a call is live), **latency
anomaly** vs the link's own history, **peering-outlier** and **transit-vs-access** segmentation,
**SLA contract-vs-delivered**, and a shareable **forensic HTML report**. Self-induced noise (WiFi
scans, speedtests) and collection gaps (device sleep) are excluded from grading; a **collector
heartbeat** surfaces "data may be stale".

Verified: `make check` green (ruff, mypy strict, 120 pytest), frontend oxlint + tsc, **6 Playwright
e2e** (every tab, no console errors), `doctor.sh` 11/11.

Still open (see backlog): cross-network comparison (N5), change-point narrative (B2), distribution/
heatmap views (B4), own bufferbloat test (B6), Alembic (C1), Spanish UI (F1), per-process bytes (H1).

---

## Delivered — audit hardening + roadmap features (2026-08-14)

A 4-expert unbiased audit (correctness/SRE, UX/data-viz, product/features, code/architecture)
drove a hardening + feature push. All landed with tests and `make check` + e2e green.

**Correctness fixes (from the audit):**
- Self-induced noise excluded from grading: WiFi-scan and speedtest ping samples (they spike every
  target — the gateway too — which is physically impossible for a real fault).
- Grade on the **internet** (median across targets, **average** loss), not the LAN gateway or a p95
  of quantized loss that stepped straight to F. Latency is **per-target** with per-target floor, so
  a distant-but-stable host no longer reads as congestion.
- Retention: **every** append-only table is pruned (was unbounded); composite indexes on hot paths;
  a 7d window is honestly capped to raw retention; diurnal reads the 1-h rollups.
- Migration table list **derived from the models** (was drifting); regional baseline follows the
  PC's country; on-demand speedtest is lock-guarded; the meaningless cumulative `tx_retries` series
  removed.
- Map false precision fixed (null-island 0,0 hops dropped, centroid-stacked services deduped);
  verdict findings ranked with error/warning prominent and info collapsed; panels have error states;
  loss chart auto-scales; a **collector heartbeat** → `collector_healthy` drives a header status dot.

**New capabilities (the 6 roadmap items):**
- **A4 ✅ Forensic report** — `GET /api/report` self-contained printable HTML (verdict, SLA, outage
  log, DNS comparison, geolocated route, methodology). Export button in the verdict panel.
- **B1 ✅ Anomaly detection** — `robust_z` (was unused) now flags latency that's ≥3 SD above the
  link's **own** 1-h-rollup history.
- **B5 ✅ SLA contract-vs-delivered** — `[sla]` config + `analysis/sla.py` + `/api/sla` + card:
  capacity passes at ≥90% of the headline rate, uptime/latency are hard thresholds.
- **H3 ✅ DoT + IPv6 parity** — DNS-over-TLS health per resolver (`dig +tls`); dual-stack IPv6 ping
  (`ping_raw.af`, `ipv6_targets`) with a "broken IPv6 / happy-eyeballs" finding.
- **H\* ✅ UDP/QUIC media probe** — `probes/media.py` detects an active UDP call/game flow and pings
  its real peer; the "Video calls" experience rating uses that **real path** when a call is live.
- **C4/C5 ✅** retention pruning + collector heartbeat; **perf** — latest-flow-per-IP via SQL
  `max(ts)` (not full-window scans); `queries.py` split (raw explorer → `api/raw_queries.py`).

Also new since v0.1: block-aware WiFi channel analysis, service-geolocated route map, DNS-resolver
comparison, per-service traffic aggregation, per-activity experience ratings, live-speed KPIs,
Playwright e2e smoke suite.

---

## Themes & backlog

Priority: **P0** = highest leverage for the actual goal (know why it fails). Effort: S/M/L.
Items completed above are marked ✅ inline.

### A. Diagnostic & verdict engine — *"que concluya el sistema"* (P0) 🚩

The flagship. Turn measurements into an attributed conclusion.

- **A1** Composite health score per window (A–F): weighted latency·jitter·loss·bufferbloat·
  throughput, with the weights documented. One glanceable grade per 6h/24h/7d. *(M)*
- **A2** Automatic outage/degradation **attribution**: for each loss/outage window, join the
  concurrent mtr per-hop history and classify the cause — `wifi-radio` (loss at hop 1 with
  TX-retries↑ and signal↓ at the same timestamps), `isp-lastmile` (loss begins at an ISP hop,
  WiFi clean), `dns` (resolver failing while ping is fine), `gateway` (hop-1 down). *(L)*
- **A3** **Verdict panel** + natural-language summary generated server-side from A1/A2:
  ranked findings with evidence (timestamps, hops, magnitudes). *(M)*
- **A4 ✅** **Forensic report (peritaje)**: exportable self-contained HTML/PDF for the window —
  verdict, evidence tables, per-hop path, annotated charts, methodology — something you send
  to the ISP. *(L)*

### N. Network identity & multi-network analysis (P0) 🚩 foundational

The PC is not always on the same network (home / office / café). Without a network dimension,
their samples mix and every conclusion is wrong when you move. This underpins A and B.

- **N1** Detect the current network by a robust **fingerprint** — gateway MAC (survives DHCP
  IP changes) + SSID/BSSID + interface; wired vs wireless. *(M)*
- **N2** First-class `network` identity + tag **every** sample with `network_id`; per-network
  rollups. *(M)*
- **N3** **Network-change events** ("switched from Home to Office at 09:12") and editable
  labels per network. *(S)*
- **N4** **Per-network views & verdict**: a network selector (default = current) so the
  dashboard, tables, score and verdict are all scoped to one network — or "all". *(M)*
- **N5** Cross-network comparison ("Home vs Office: which is worse, and how"). *(M)*

### B. Data science & scientific rigor (P0/P1)

Make the analysis defensible, not eyeballed.

- **B1 ✅ (anomaly)** Rolling **baselines + anomaly detection** per metric (EWMA + MAD/robust z-score) →
  "anomalously bad vs *your* normal", not fixed thresholds. Feeds A2/alerts. *(M)*
- **B2** **Change-point detection** on RTT/loss (regime shifts: "latency stepped up at 14:05
  and stayed"). *(M)*
- **B3** **Correlation analysis**: quantify loss↔TX-retries, RTT↔signal, loss↔hop — report
  coefficients so attribution is evidence-based. *(M)*
- **B4** Distribution views: **CDF / histogram / p50-p95-p99** per metric; time-of-day/day-of-
  week **heatmaps** ("it fails weekday evenings"). *(M)*
- **B5 ✅** Statistical **outage/SLA definition** (sustained p95 breach, not only 100 % loss) +
  availability %, MTBF/MTTR. *(S)*
- **B6** Own **latency-under-load** test (saturate + ping) so bufferbloat doesn't depend on
  Ookla, and to isolate up vs down bloat. *(M)*
- **B7** MOS confidence + jitter model refinement; per-target quality scoring. *(S)*

### C. Data engineering (P1)

- **C1** **Alembic migrations** (replace `create_all`) — real schema evolution. *(S)*
- **C2** Richer rollups: store p50/p99 (not just p95), per-hop aggregation table, sample-count
  and gap tracking (data-quality signals). *(M)*
- **C3** **Analytical query layer**: expose Parquet export + optional DuckDB/Polars views for
  ad-hoc analysis over history without touching the live DB. *(M)*
- **C4 ✅** Retention/rollup tuning + compaction; VACUUM schedule; DB size dashboard. *(S)*
- **C5 ✅ (heartbeat)** Backpressure/health: collector self-metrics (probe durations, failures) as a series. *(S)*

### D. Raw data & tables — *"ver datos crudos, como tablas"* (P0)

- **D1** A **Data tab**: sortable/filterable/paginated tables for ping, dns, flows,
  traceroute, events; CSV/JSON export per view. *(M)*
- **D2** **Per-hop traceroute-over-time** table + timeline (the PingPlotter view): which hop
  degrades when. *(M)*
- **D3** Chart **drill-down**: click a point → raw samples behind that bucket. *(M)*

### E. UI / UX (P1)

- **E1** **Outage timeline** (Gantt bars, colour = attributed cause) + **WiFi channel
  congestion** bar view from scan data. *(M)*
- **E2** Per-hop **heatmap** (hop × time, colour = loss/RTT). *(M)*
- **E3 ✅ (states)** Light/dark toggle, responsive/mobile pass, empty/error/loading states, WCAG (keyboard,
  contrast, state by colour+icon). *(M)*
- **E4** Range = custom window + live "follow" mode; per-target show/hide; annotations on
  events. *(S)*

### F. i18n — Spanish (es_CO) UI (P1)

- **F1** Light i18n layer (react-i18next or a typed dict), **es_CO** as default for this user,
  English fallback. Localised dates/numbers (coma decimal, DD/MM/YYYY). *(M)*

### G. Testing & CI (P1)

- **G1** Backend: aggregation-rollup correctness, outage/roaming detection, alert lifecycle,
  anomaly/attribution units. *(M)*
- **G2** Frontend: **Vitest** + Testing Library for chart-option builders, hooks, formatters. *(M)*
- **G3 ✅** **Playwright** e2e smoke (dashboard renders, range switch, speedtest button). *(S)*
- **G4** **GitHub Actions** CI running `make check` on push. *(S)*

### H. More probes / breadth (P2)

- **H1** Per-process bandwidth (`nethogs`, root) → "which app used the network". *(M)*
- **H2** TLS SNI sniffing (`tcpdump`) for exact app classification beyond rDNS/ASN. *(L)*
- **H3 ✅ (DoT+IPv6)** DoH/DoT latency, DNSSEC validation, IPv6 path parity. *(M)*
- **H4** WiFi channel utilization / airtime, beacon loss, roaming quality scoring. *(M)*
- **H5** Gateway ARP/reachability micro-probe (sub-second WiFi-drop detection). *(S)*

---

## Proposed milestones

- **M1 — "See & conclude" (P0):** D1 raw-data tab + D2 per-hop-over-time + A1 health score +
  A3 verdict panel (rules from what we already store). Immediately answers *"what's wrong?"*.
- **M2 — "Scientific attribution" (P0/P1):** B1 baselines + B3 correlation + A2 automatic
  hop/cause attribution + B4 heatmaps. Makes the verdict defensible.
- **M3 — "Report & polish" (P1):** A4 forensic report + E1/E2 timelines & heatmaps + F1
  Spanish UI + G1–G4 tests/CI.
- **M4 — "Depth" (P1/P2):** B2 change-points, B6 own bufferbloat, C1–C3 data-engineering, H\*
  extra probes.

Each milestone is independently shippable and leaves `make check` green.

## PF — Remove alerts/notifications (final)

The threshold-alert engine and desktop notifications are not wanted: netpulse is a diagnostic
dashboard, not a notifier. Remove `alerts.py`, its collector job, the `alerts` config, the
`alert` event kind, and any notify-send path. The verdict + events + Routes surface the state;
no push notifications.
