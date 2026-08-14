# Audit & remediation log

Three independent, adversarial audits were run against the codebase (UX/legibility,
backend engineering/correctness, data-science/measurement validity), each checked against
`PRODUCT_CONVENTIONS.md` rather than opinion. This records what they found and the honest
status of each finding — fixed, or deferred with rationale. Deferred items are real work, not
dismissals.

## Fixed

### Measurement validity (the conclusions are now defensible)
- **Health score gates on critical metrics.** A weighted mean structurally couldn't express
  "unusable" (10% loss diluted to a C). Now loss/availability gate the grade (F when loss is
  catastrophic), and the loss penalty is convex near zero (`analysis/score.py`).
- **Verdict is burst-aware.** Loss/jitter fed to the score are the worst path's p95, not a
  window mean that erased the bursty drops that are the actual symptom (`api/queries.py`).
- **MOS reflects reality.** Computed at loaded latency + measured loss, so it can't advertise
  4.4/5 on a link graded F for bufferbloat (`probes/active.py`).
- **Attribution requires persistence.** Loss must run contiguously from a hop to the
  destination; a lone mid-path ICMP-rate-limit spike is no longer blamed (`analysis/attribute.py`).
- **Correlation is sound.** Retry *ratio* (Δretries/Δtx-packets, new `tx_packets` column),
  Spearman not Pearson, minimum bucket count, reset/roam buckets dropped (`api/queries.py`).
- **Outage hysteresis.** Requires N consecutive failing cycles, so one hiccup can't flap it.

### Engineering
- Non-numeric raw filter returns 400, not 500. SQL aggregates (O(1) memory) + bounded p95
  sample. Stable pagination tiebreaker. Escaped LIKE wildcards. Network-scoped alerts.

### UX / legibility / accessibility
- Distinct loading/error/empty states (an empty table no longer claims "healthy").
- Keyboard focus ring, `prefers-reduced-motion`, `th scope`, `aria-sort`, tab roles;
  severity by icon+label+colour; distinct colour per series; good+bad threshold lines;
  percentile bands; sticky header; contrast fixes; per-hop RTT + loss legend; speedtest
  labelled as a data-cost action with feedback.

## Deferred (tracked on the roadmap, honestly not yet done)

These are genuine gaps, mostly research-grade analysis and product-depth features:

- **Per-target rolling baselines + anomaly detection wired in.** `stats.robust_z`/`ewma` exist
  and are tested but are not yet used to replace the fixed `latency ≥ 100 ms` / `loss ≥ 2%`
  thresholds — so a legitimately-distant host or evening congestion can still be flagged. (B1)
- **Confidence intervals** on reported numbers (Wilson for loss proportions, bootstrap for MOS,
  a p-value gate on the correlation beyond the bucket-count minimum). Attribution confidence is
  still a label, not computed from effect/sample size.
- **Change-point detection** and **time-of-day/seasonality** normalization (diurnal congestion
  is still reported as a fault). (B2, B4)
- **Distribution views** (histogram/CDF/p50-p95-p99), **outage/hop timelines**, **event
  annotations on charts**, **chart→raw drill-down**, **WiFi channel-congestion view**,
  **cross-network comparison**. (B4, D3, E1, E2, N5)
- **Exportable forensic report** (peritaje). (A4)
- **Spanish (es_CO) UI.** (F1)
- **Full ITU-T G.107** Ie,eff (codec/burst-aware), and up-vs-down bufferbloat split; the
  current E-model is the widely-used *simplified* form and is labelled as such.
- **More test coverage**: collector outage/roaming/network-detection paths, `hop_timeline`.

See `ROADMAP.md` for how these sequence. The bar for "done" on each is `PRODUCT_CONVENTIONS.md`.

---

## Round 2 — 2026-08-14 (4-expert panel)

A second panel (adversarial correctness/SRE, UX/data-viz, product/features, code/architecture)
re-audited the grown codebase. Every confirmed finding was fixed; see the ROADMAP "Delivered"
section for the feature work done alongside.

### Fixed (correctness)
- **Self-measurement no longer pollutes the grade.** Ping samples taken during the tool's own WiFi
  scans and speedtests (they spike every target including the gateway) are excluded from
  loss/latency stats (`_drop_measurement_artifacts`).
- **Grade reflects the internet, not the LAN.** `status()` and the score use internet targets
  (median), not the ~2 ms gateway or the single most-optimistic host. Latency is per-target with a
  per-target floor; the grade's loss input is the typical *average*, not a p95 of quantized
  per-cycle loss (which stepped straight to F).
- **Unbounded growth fixed.** Every append-only table is pruned; a 7d window is capped to raw
  retention so availability/coverage aren't computed against absent time; diurnal reads rollups.
- **Drift & correctness.** Migration table list derived from the models; regional baseline follows
  the client country; on-demand speedtest lock-guarded; the meaningless cumulative `tx_retries`
  series removed; map null-island (0,0) hops and centroid-stacked services dropped.
- **Ops/UX.** Collector heartbeat → `collector_healthy` and a header status light; verdict findings
  ranked (errors prominent, info collapsed); panels have real error states; composite indexes and a
  SQL `max(ts)` latest-flow fetch replace full-window scans; `queries.py` split (`api/raw_queries.py`).

### Delivered features
A4 forensic report, B1 anomaly detection (robust_z), B5 SLA tracking, H3 DoT + IPv6 parity,
UDP/QUIC media-path probe (real call quality). Verified: `make check` + 6 Playwright e2e +
`doctor.sh`, all green.

### Round 2b — adversarial statistical re-audit (correctness pass)

A dedicated correctness auditor re-checked the analysis after the round-2 fixes and found three that
made the tool actively misreport (all now fixed):
- **SLA uptime false breach.** The prior uptime fix divided full-window downtime by raw-retention
  covered time (7d numerator, ~48h denominator) → a fabricated live SLA breach. Fixed: cap the
  uptime window to raw retention so both are the same window, and count only **ISP-side** outages
  (a local WiFi drop is not the ISP failing to deliver).
- **Latency-anomaly detector couldn't fire.** It z-scored a cross-target median against a pooled
  baseline mixing near and far hosts, so the denominator was dominated by distance variance and the
  threshold needed a total meltdown. Fixed: z-score each target's current p95 against that same
  target's own 1-h history, take the max — like-vs-like, so a real per-path step-up trips it.
- **Live-call false positive.** ICMP rate-limiting on a media peer (partial loss) was rated as call
  loss → "call degraded" on a fine call. Fixed: rate live calls on jitter + RTT only; ICMP loss to a
  media server is not media loss.
- Also: transit-vs-access restricted to internet-kind targets (a far work host was permanently
  mislabeled "international transit"); browsing's "fair" band gained a loss ceiling; the speedtest
  exclusion window was right-sized (+25 s, recovers by ~17 s). Deferred (low): the availability/loss
  double-weight in the composite score, and two latent stats helpers (`effective_n` unused,
  `block_bootstrap_ci` returns range for small n) — both currently inert.
