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
