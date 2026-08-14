# Design — Route & Peering Intelligence

A continuous, scientific capability to answer "when my internet is slow, *which* routes/peerings
are the cause, is it fixable on my side, and how does it move over the day?" — not a one-off
test. It extends collection with **destination classes**, adds **distance-normalized** metrics,
and introduces a **route/geo map**. Every claim it makes is backed by a measurable number with a
confidence interval.

## Why (from the evidence so far)

A one-shot probe showed local/CDN-cached destinations at ~20 ms/0% loss and international-transit
ones at ~78–98 ms with 3–9% loss, with the latency jump inside the ISP and loss at specific
peerings. That is suggestive but not yet *proven continuously*: a one-off can't show diurnal
congestion, anycast POP flips, route changes, or trends, and 30-packet loss has a wide CI. This
feature turns that snapshot into a monitored, statistically-honest signal. (The prior analysis is
under an independent audit; this design stands regardless of its verdict — it is the instrument
that *settles* the open questions.)

## New collection: destination classes

A `reference_target` taxonomy (config-driven), each tagged on three orthogonal dimensions so the
cause can be isolated without bias:

- **provider/ASN class**: `cdn-cloudflare`, `cdn-google`, `cdn-akamai`, `cdn-fastly`,
  `cdn-cloudfront`, `cdn-meta`, `cdn-netflix`, `origin-direct` (no CDN), `anycast-dns`.
- **jurisdiction**: `gov-co`, `gov-mx`, `gov-us`, `gov-latam`, `gov-eu` (plus general `svc`).
- **expected cache-locality**: `local-cached` vs `international-origin`.

~30–40 curated hostnames, ≥3 per provider class so per-ASN aggregates have power (not one sample).
Balanced across regions to avoid a US-centric bias. Resolved periodically — an anycast IP that
changes POP is captured, not assumed.

## New probe (`probes/endpoint.py`)

Per reference target, on a cheap cadence:
1. **Resolve** (trusted resolver) → current IP.
2. **ASN + country** — Team Cymru's `origin.asn.cymru.com` TXT already returns the country code,
   so no new dependency for country-level geo. Plus **rDNS** (POP hints, e.g. `mia`/`bog` in the
   PTR).
3. **Geo** of the endpoint IP: country-level now (Cymru); **city-level optional** via a bundled
   MaxMind GeoLite2-City DB (config path) to distinguish "your Cloudflare POP is Bogotá" from
   "…is Miami" — the difference *is* the peering-health signal.
4. **Ping** (loss/RTT/jitter) — reuse the existing probe, longer packet count for tighter CIs.
5. **mtr** (periodic, data-cheap) → per-hop IP+ASN+country → the **AS-path**, the **border AS**
   (where you leave the ISP), the **peering AS**, and where loss first persists to the endpoint.

## New metrics (the science)

1. **Excess latency** `RTT_excess = RTT_measured − RTT_floor`, where
   `RTT_floor = 2 · dist_km / v`, `v ≈ 200 000 km/s` (fibre ≈ ⅔ c), `dist` = great-circle from the
   user's geo to the endpoint geo. This **separates congestion / routing inefficiency from pure
   physical distance** — the single most important unbiased metric here. A US endpoint at 90 ms
   with a 60 ms floor has 30 ms of *excess* — that 30 ms is the fixable part; the 60 ms is physics.
2. **Loss with a Wilson 95% CI**, pooled per class/ASN over many packets so the interval is tight
   enough to distinguish "9%" from "3%". Continuous, not single-run.
3. **Anycast POP + POP-flip events**: endpoint city/ASN over time; a flip (e.g. Bogotá→Miami) is
   logged as an event — it directly reveals a peering withdrawal/failover.
4. **AS-path & peering AS** per destination; route-change events; the transit ASNs crossed.
5. **Diurnal model**: per class, loss/RTT/excess by hour-of-day aggregated over ≥1 week → the
   peak-vs-trough delta *with a CI*. This is what actually **proves or disproves** peak-hour
   congestion (a 3.6 h monotonic rise does not).
6. **Peering-health grade** per CDN/ASN: a composite (loss + excess latency + jitter + POP
   locality) → A–F, reusing the existing scoring/gating engine. "Cloudflare peering: D."

## New analysis

- Per-class time series (loss/RTT/**excess**) with CI bands.
- **Diurnal heatmap** (hour-of-day × class, colour = loss or excess) — the "it's worse weekday
  evenings" answer.
- POP-flip / route-change **event timeline**.
- A per-class **root-cause sentence**, generated like the verdict: *"Cloudflare is slow because
  your traffic terminates in <city> via <transit AS>; excess latency <Y> ms; loss begins at hop
  <N> (<peering ASN>); worst at <hour> (<peak loss> vs <trough>)."*

## New visualization: the map

- A **world map** via ECharts `geo`/`map` with a **vendored** world GeoJSON (~150 KB, bundled — no
  external tiles, CSP-safe like the rest of the app).
- Each reference destination plotted at its endpoint geo, coloured by health (excess/loss).
- **Route arcs** from the user's location through geolocated traceroute hops to each destination
  (ECharts `lines` with a directional effect) — the picture of "CO → Miami, loss at the peering."
- A per-destination detail: the hop-by-hop path drawn on the map + the RTT/loss ramp.

## Data engineering

- Tables: `reference_target` (or config), `endpoint_sample` (ts, target, ip, asn, country, city?,
  rtt/loss/jitter, network_id), `endpoint_path` (ts, target, hop, ip, asn, country, rtt, loss).
  Network-scoped and rolled up per class like existing metrics; retention mirrors the raw tables.
- Geo: an embedded country-centroid table (~250 rows) for coarse distance immediately; MaxMind
  City optional for POP precision.
- Cadence: ping continuous; resolve+ASN+country every ~10 min; mtr every ~15 min per class — all
  data-cheap (no bandwidth tests).

## Measurability & validation

- Everything is quantitative: excess latency (ms), per-ASN loss (% ± CI), POP-flips (count),
  diurnal delta (ms/% peak−trough ± CI), route-changes (count).
- **Mitigation A/B**: run the same metrics with WARP/VPN off, then on — the deltas *prove*
  user-side fixability with numbers, not opinion.

## Phasing

- **P1** — reference-target classes + endpoint probe (resolve/ASN/country/ping) + per-class
  continuous stats + Wilson CIs. Confirms route-specificity *continuously*.
- **P2** — excess latency (country-centroid distance) + diurnal model + peering-health grade.
- **P3** — the map (vendored GeoJSON: endpoint scatter + route arcs) + POP-flip/route-change
  events + per-hop geo.
- **P4** — MaxMind city-level POP + the WARP/VPN A/B harness.

Each phase leaves `make check` green and is independently useful.
