# Design — Route & Peering Intelligence (v2, hardened after methodology audit)

A continuous, *scientific* capability to determine which routes/peerings degrade the user's
internet, whether it's fixable user-side, and how it varies over time — with an uncertainty-aware
route/geo map. v1 was a good product spec but a weak measurement spec; an adversarial
network-measurement methodology audit rewrote it. This version is the serious study. Every claim
it emits carries a confidence interval that respects the data's real (autocorrelated) structure,
and no headline conclusion rests on a single vantage or a synthetic panel.

> Context correction: the monitored connection is in **Mexico** (public IP AS13999/Megacable, MX;
> first transit hop AS32098, MX), not Colombia. So Mexico↔US has a ~30–50 ms physical floor and
> the observed ~98 ms carries *more* excess than distance explains — but see the min-RTT baseline
> below; we no longer derive excess from geography at all.

## Non-negotiable methodology principles (from the audit)

1. **Excess = observed RTT − self-calibrated min-RTT**, not RTT − geographic floor. The floor is a
   running hard-minimum / 1st-percentile per `(destination-prefix, address-family, route-epoch)`.
   This is CAIDA/bufferbloat base-RTT filtering; the kernel already computes it per socket as
   `tcpi_min_rtt`. Speed-of-light is demoted to (a) a **plausibility validator** — if `min_RTT`
   is below the great-circle floor, the geolocation is wrong (auto-flag, downgrade the map pin);
   and (b) a **routing-stretch ratio** `min_RTT / geo_floor`, reported as path inefficiency,
   explicitly *not* congestion. Baselines are segmented by **route-epoch** (a POP-flip or AS-path
   change resets the min, else a stale min fabricates excess).
2. **Statistics respect autocorrelation.** Loss/latency samples are not i.i.d. (bursty,
   Gilbert–Elliott). CIs use an **effective sample size** `n_eff = n·(1−ρ₁)/(1+ρ₁)` or a
   **stationary block bootstrap (Politis–Romano)**. Loss is modelled as a two-state process and
   reported as *marginal rate + mean burst length + conditional loss*, so "9% as one daily outage"
   is distinguished from "9% spread uniformly".
3. **Measure real experience, passively, first.** The primary signal is the kernel's own per-flow
   view of the user's actual traffic via `ss -ti`: `tcpi_min_rtt`, `tcpi_rtt/rttvar`,
   `tcpi_retrans/bytes_retrans`, `tcpi_delivery_rate`, `tcpi_reordering`, `tcpi_notsent_bytes`.
   This gives RTT, base-RTT, forward-path loss and achieved goodput on the destinations the user
   *actually uses*, at zero probe cost and with no selection bias. Synthetic probing only fills
   idle periods and covers designed controls.
4. **App-relevant active probes, not ICMP alone.** TCP-connect RTT (SYN→SYN/ACK:443, forwarding-
   plane, traverses ICMP filters), QUIC/TLS handshake, HTTP TTFB. ICMP is one channel; an
   ICMP-filtered host is `filtered`, **never** 100% loss. Reverse-path loss is acknowledged as not
   separable from a single host (would need a TWAMP reflector) — we stop implying loss is
   directional beyond what the path evidence supports.
5. **Identification needs a second vantage.** One home host cannot distinguish "my ISP's peering
   is bad" from "this CDN POP is bad for everyone" — observationally identical inside-out. An
   **outside-in arm** (RIPE Atlas built-in + custom measurements from other MX probes/anchors, and
   public looking glasses) supplies the "is it just me / just my ISP / the whole region?" contrast.
6. **Population from realized traffic, not a curated list.** The destination set is sampled
   probability-proportional-to-use from the user's own flows/DNS, then **stratified by
   ASN × CDN × region × address-family** with a per-stratum sample budget for power. Fixed anchor
   controls (RIPE Atlas anchors, root/TLD) give longitudinal comparability. **The jurisdiction/gov
   dimension is dropped** (recon/legal risk, zero causal value — jurisdiction is not a network
   variable; ASN/IXP/transit is).
7. **Causation is interventional and controlled**, not correlational: a **randomized within-
   subject crossover** for WARP/VPN (interleaved on/off blocks, netting the tunnel's own
   overhead); a **same-border/different-transit** destination pair (difference-in-differences
   isolates ISP vs transit); an **in-country IXP-peered local control**; host-load covariates.
8. **Geolocation renders uncertainty.** POPs inferred from rDNS IATA/city codes (DRoP/undns/CAIDA
   hoiho) cross-referenced to PeeringDB facilities/IXPs and RIPE IPmap/CAIDA ITDK, with
   **Constraint-Based Geolocation (CBG, Gueye et al.)** using `min_RTT` as a hard distance bound →
   a feasibility **disk**, not a point, from one vantage. Confidence tiers (PTR-confirmed >
   PeeringDB-facility > IP-geo-guess) shown by colour/opacity; an unlocatable hop is drawn as
   "unlocated hop N (ASN X)", never at invented coordinates.
9. **Report vectors, not a letter.** Per ASN/POP: excess ms, loss % ± CI, POP city + confidence,
   jitter, goodput — the separation of these is the diagnosis; a single A–F grade destroys it.
   (The user experience KPI can still grade the *overall* connection; peering is a vector.)
10. **Diurnal is a pre-registered mixed-effects test.** ≥3–4 weeks; model
    `outcome ~ hour + day_of_week + holiday + host_load + (1|destination) + (1|ASN)` instead of
    240 separate ASN×hour tests; **Benjamini–Hochberg FDR**; pre-register the exact contrast
    (e.g. 20:00–23:00 vs 04:00–06:00 local) and split exploratory vs confirmatory windows (no
    HARKing).

## The two decisions this must resolve (pre-registered)

These are the answers that matter for the user; the design is built to make each *falsifiable*,
with the thresholds written down before the confirmatory window (no HARKing).

**Decision A — local/last-mile oversubscription vs transit/peering congestion** (opposite
fixability). The **local path is a first-class co-measured control class**: gateway RTT/loss, the
first-N ISP hops (the access/aggregation network *before* the border AS), and a locally-peered
control (short AS-path host reachable via the national IXP). Every path sample is split into
**pre-border excess vs post-border excess** using the mtr AS-path (the border AS = where you leave
the ISP). Pre-registered rule:
- local segment (gateway + first ISP hops + IXP control) **degrades at peak** → *access-network
  oversubscription* — **not** user-fixable, VPN won't help;
- local **flat** at peak but international **degrades** → *transit/peering congestion beyond the
  border* — candidate VPN-fixable → **confirm with the WARP crossover**;
- both degrade → decompose by where excess accumulates along the hop ramp.
Shared-border/different-transit destination pairs are the clean identifier (same access, different
transit → a divergence localizes the tier by difference-in-differences).

**Decision B — "is my ISP bad, or is this normal for the region?"** Never answerable inside-out, so
metrics are reported **region-relative**, not absolute: `excess_relative = user_excess −
regional_median_excess(ASN, region)`, and the peering signal is a **percentile within region**
("worse than X% of comparable MX / AS13999 connections"), not an absolute letter that would brand
physics or region-wide reality a fault. Regional distributions come from RIPE Atlas (MX probes on
the ISP's AS + neighbours), Cloudflare Radar, and M-Lab NDT — all free, cached offline, refreshed
weekly, degrading gracefully to a clearly-labelled lower-confidence inside-out verdict when offline.

## New measurements (superset)

Per-flow passive (`ss -ti`) · TCP-connect / QUIC / TTFB active · ICMP+mtr (path, with AS-path,
border AS, peering AS, per-hop with rate-limit caveat) · **both address families** (native v6 ASN
via `origin6.asn.cymru.com`, Happy-Eyeballs aware) · resolver-POP identity (EDNS0 **NSID**,
`hostname.bind/id.server` CHAOS) · **PMTUD/MTU-blackhole** (DF sweep) · **DNS transport** (Do53 vs
DoH/DoT, stub→resolver vs resolver→auth) · **BGP route-change correlation** (RIPE RIS / RouteViews
/ RIPEstat: confirm an observed AS-path change against a real BGP update — routing event vs
congestion) · per-path **bufferbloat under load** and **goodput** (from `ss`) · ECN / reordering /
SACK · host-state covariates (CPU, wlan0 TX-retries, concurrent throughput) · a loopback/gateway
**zero-excess anchor** to subtract the apparatus's own jitter floor.

## New analysis

Per-ASN/POP vectors with autocorrelation-aware CIs · Gilbert–Elliott loss (burst length +
conditional loss) · the pre-registered diurnal mixed-effects model with FDR q-values · POP-flip /
route-change / BGP-update event timeline · the outside-in "just me vs region" comparison · a
per-destination root-cause statement generated from the *identified* evidence, always with its
confidence and the vantage it rests on.

## New visualization: the map

World map via ECharts `geo`/`map` with a **vendored** GeoJSON (offline, CSP-safe). Endpoints and
hops drawn at inferred locations **with uncertainty** (feasibility disks / confidence-tiered
opacity; unlocated hops listed, not pinned). Route arcs from the user through geolocated hops;
per-destination path detail with the RTT/loss/goodput ramp. The map never asserts a coordinate the
data can't support.

## Data engineering

Tables: `flow_sample` (passive `ss -ti` snapshot per socket: dst, asn, family, min_rtt, srtt,
retrans, delivery_rate, reorder, ts, network_id), `endpoint_active` (dst, family, method, rtt,
loss, ttfb…), `endpoint_path` (hop, ip, asn, country, ptr, rtt, loss, epoch), `route_epoch`
(dst/prefix/family → epoch boundaries from POP-flip/AS-path change), `host_state` (cpu, tx_retries,
throughput). **Dataset versioning is mandatory**: every sample records the GeoLite2 vintage, Cymru
snapshot date, and destination-list version, or the study isn't reproducible.

## Procedure & reproducibility

Warm-up/calibration before any excess claim; recalibrate the min baseline on POP-flip/route-change;
subtract the loopback/gateway noise floor. Pre-register the diurnal hypothesis; keep an
exploratory→confirmatory split. Ground-truth validation of excess against a **known-location**
target (an in-city IXP host or one we control) and against RIPE Atlas anchor distances. Handle
failure modes explicitly: ICMP-filtered (→ `filtered`, fix the `ping.py` 100%-loss default),
**CGNAT** (`100.64.0.0/10` first hops break border-AS and public-IP logic), split-horizon DNS
(key by `network_id`), anycast flap, IPv6 Happy-Eyeballs fallback. Third-party probing is low-rate
TCP-connect, never ICMP floods.

## Prerequisite code fixes (the plan builds on these)

- `probes/ping.py`: distinguish "ICMP filtered / unreachable" from "100% loss" — the current
  `loss = 100.0` regex-miss default manufactures outages.
- `probes/flows.py`: enable IPv6 ASN enrichment (`origin6.asn.cymru.com`) — required for the
  v4/v6 divergence analysis.

## Revised phasing

- **P1 — real-experience foundation:** passive `ss -ti` (RTT/min-RTT/loss/goodput per real
  destination) + TCP-connect probing + host-load covariates + IPv4/IPv6 split + the two code
  fixes. Ships the honest experience signal before any modelling.
- **P2 — calibrated metrics & honest statistics:** min-RTT excess (route-epoch-segmented) +
  `n_eff`/block-bootstrap CIs + Gilbert–Elliott loss + the pre-registered mixed-effects diurnal
  model with FDR. Per-ASN vectors, not a letter.
- **P3 — identification:** RIPE Atlas outside-in arm + same-border/different-transit and
  IXP-peered controls + randomized WARP/VPN crossover + BGP route-change correlation.
- **P4 — geolocation & map:** PTR/IATA + PeeringDB + CBG feasibility-disk geolocation with
  uncertainty rendering; MaxMind city as one low-confidence input, never the sole pin.

Each phase leaves `make check` green and is independently useful. Cut: the jurisdiction/gov
dimension. Kept: ASN/CDN/region/address-family strata driven by the user's own traffic.
