# Design — Local-Network & Multi-Network Measurement Coverage

Companion to [route-peering-intelligence.md](route-peering-intelligence.md). That plan hardens the
**outward** (route/peering) measurement. This one closes the **inward** gaps — the local medium
(WiFi/LAN) and the *per-network, all-networks* verdict — so netpulse can do what it was built for:
**evaluate every aspect of every network it sees and say, per network, whether the fix is user-side
configuration or something to report to the ISP** — not just diagnose the current device by hand.

## Why this exists (the triggering finding)

A live session diagnosed a network (Telmex/Infinitum) as "Grade F". A manual campaign
(`ping` gateway vs external, `iw station/survey dump`) proved the instability was **100% the WiFi
link** (jitter to the gateway ≈ jitter to Google: 28.9 ms vs 29.6 ms), not the ISP. **netpulse could
not have concluded this on its own** — the analysis was hand-run. The gaps below are the reason.

## Non-negotiable principles

1. **Attribution before advice.** Never say "the ISP is bad" or "your WiFi is bad" without the
   split that proves it. The primitive is `jitter/loss at the first hop (gateway)` vs
   `jitter/loss end-to-end`. If the variance is already present at the gateway, it is **local**
   (WiFi/LAN); if it appears only past the gateway, it is **access/ISP**. This is the single most
   important missing measurement.
2. **Per-network, not per-device.** Every network fingerprint (`gateway_mac`) carries its own
   baseline, verdict, and recommendation. The product surface is "your networks", each graded.
3. **Confidence-gated verdicts.** Below a minimum effective sample size a network shows
   *"insufficient data"*, never a letter grade. A grade on 8 samples is misinformation.
4. **Measure the medium, not just the link.** Signal strength alone is a weak predictor. Airtime
   occupancy, channel width, retries, and neighbour census explain *why* a strong-signal link still
   stutters (co-channel contention with neighbours' APs — a shared-medium effect, not a "my
   devices" effect).
5. **Config-vs-report is the output contract.** Each finding resolves to one of:
   `user-config` (channel/width/placement/cable), `ISP-report` (peering/line/bufferbloat on their
   CPE), or `insufficient-data`.

## Measurement gaps (what we don't measure yet — all mandatory)

| # | Gap | Source already available? | Fix |
|---|-----|---------------------------|-----|
| **G1** | **Gateway/LAN ping target is hardcoded** (`config.toml` `192.168.100.1`). The `network.py` probe already detects and stores each network's real `gateway_ip`, but `ping.py` never uses it → on any network but the original, the first-hop signal is missing. | **Yes** — `Network.gateway_ip` is stored. | Collector injects a synthetic `lan`-kind target = the *current* network's detected gateway each cycle. |
| **G2** | **No LAN-vs-WAN attribution.** `attribution.py` doesn't compare first-hop vs end-to-end variance. | Yes, once G1 lands. | New `attribute_local()` producing a `local` / `access` / `isp` verdict with the jitter/loss split as evidence. |
| **G3** | **Airtime occupancy not captured.** The WiFi probe runs `survey dump` but only parses `noise`; it drops `channel active/busy/receive/transmit time`. | Yes — same `survey dump` output. | Parse busy/active → `airtime_busy_pct`; derive `airtime_foreign_pct = (busy−rx−tx)/active` = neighbour contention. |
| **G4** | **Channel width not captured** (80/40/20 MHz). Central to the co-channel-contention diagnosis. | Yes — `iw link` reports width. | Add `width_mhz` to `WifiRaw`. |
| **G5** | **No per-network verdict/comparison surface.** Data is network-scoped but the UI/verdict is current-network-centric. | Partial. | `verdict_all_networks()` + a "Networks" view: each network, grade (or insufficient-data), top cause, config-vs-report. |
| **G6** | **Thin-data networks still get a letter grade.** 8 samples → "Grade F". | — | Gate grades behind `n_eff ≥ N_min` and coverage; else `insufficient-data`. |
| **G7** | **No LAN device / airtime-hog census.** Can't distinguish "a neighbour's AP" from "my own second device saturating the air". Today ruled out only by hand (`ip neigh`). | Partial (`ip neigh`; full census needs router/ARP-scan). | Optional `lan_census` probe: `ip neigh` + reachable count; flag when own-network airtime is high. |
| **G8** | **No roaming/DFS instability capture.** BSSID flaps and DFS radar channel-switches cause latency/loss the current model reads as generic jitter. | Partial (BSSID in probe). | Track BSSID changes/sec and channel-switch events as their own signal. |
| **G9** | **Bufferbloat not attributed to a layer.** 92 ms under load could be WiFi airtime or CPE queue. | Partial. | Run the load-latency probe once wired vs wireless (or correlate with airtime) to place the queue. |

### Scan/channel-advice enrichment (we HAVE the scan — nmcli, no root — but the advice is weak)

The neighbour scan (`wifi_scan.py`, `WifiScan`) works and populates per network. But
`analyze_channel` gave demonstrably bad advice in a live case ("switch 149 → 36") because:

| # | Defect in current channel advice | Fix | Status |
|---|----------------------------------|-----|--------|
| **G10** | **Counts AP *quantity*, ignores signal strength.** A −90 dBm AP (negligible) weighs the same as a −58 dBm one. It recommended a block whose neighbours were *stronger* but fewer. | Only count neighbours above a −85 dBm contention floor. | ✅ done |
| **G11** | **Doesn't exclude the *same router's other radios*.** Only the exact connected BSSID is dropped; the Telmex box's second SSID (`INFINITUM38B5_2.4` on the same 5745) counts as a "neighbour", inflating your own block. | Exclude by SSID-root (`ssid_root()`), not just exact BSSID. | ✅ done |
| **G12** | **Width-blind.** It buckets an "80 MHz block" heuristically but never reads the router's real width (G4) nor each neighbour's width. On 80 MHz the *right* first move is often "narrow to 40/20 MHz on the same channel", which the advice never suggests. | Read real width (G4); make **"narrow the width"** a first-class recommendation. | ✅ done |

> **Shipped (block 1):** G3/G4 (`WifiRaw.width_mhz`, `airtime_busy_pct`, `airtime_foreign_pct`;
> width parsed from the VHT bitrate line, airtime from the survey in-use block) + G10/G11/G12
> (signal-weighted, SSID-root-aware, width-aware `analyze()`). Verified on the live Infinitum
> network: the old wrong advice ("switch to 36" — the *busier* block) is gone; the engine now
> correctly reports the 5 GHz channel as clear of competing APs. 130 backend tests green.

## New/changed data model

- `WifiRaw`: add `width_mhz`, `airtime_busy_pct`, `airtime_foreign_pct`, `bssid`.
- `PingRaw`: no change — the gateway simply becomes a real, per-network `lan` target (G1).
- New `NetworkVerdict` (materialised or computed): `grade | insufficient`, `bottleneck_layer`
  (`local|access|isp`), `primary_cause`, `action_class` (`user-config|ISP-report`), `n_eff`.

## Attribution logic (G2 — the core)

```
lan  = jitter/loss to gateway (first hop)      # WiFi/LAN medium
e2e  = jitter/loss to internet targets         # whole path
if lan_var  ≳ e2e_var * 0.7   -> layer = LOCAL   (WiFi/LAN)   action = user-config
elif e2e_var ≫ lan_var        -> layer = ACCESS/ISP           action = ISP-report
loss: same split; loss present past gateway but not at it -> ISP.
bufferbloat: high + airtime high -> LOCAL; high + airtime low -> CPE/ISP queue.
```
All comparisons use the autocorrelation-aware CIs from the companion plan (`n_eff`, block
bootstrap), never raw counts.

## Signals & exact sources (so nothing is hand-run again)

| Signal | Command | Field |
|--------|---------|-------|
| First-hop jitter/loss | `ping <detected gateway>` | `PingRaw` (lan) |
| Channel width | `iw dev <if> link` → `width: N MHz` | `WifiRaw.width_mhz` |
| Airtime busy/active | `iw dev <if> survey dump` (in-use freq) | `airtime_busy_pct` |
| Foreign airtime | `busy − rx − tx) / active` | `airtime_foreign_pct` |
| Neighbour census | `iw dev <if> scan` (needs CAP_NET_ADMIN) | `WifiScan` (already) |
| Roaming | `iw link` BSSID delta | `WifiRaw.bssid` |
| LAN census | `ip neigh` | `lan_census` |

> Permissions note: `scan`/`survey` may need `CAP_NET_ADMIN`. Grant the collector
> `AmbientCapabilities=CAP_NET_ADMIN` (or `setcap`) so airtime/neighbour data is captured
> unattended — today the scan silently returns empty without it.

## Network topology / architecture understanding (G13 — new capability)

Today a "network" is one gateway fingerprint. Real homes/offices are richer: several APs on one
LAN, mesh nodes, repeaters, double-NAT, two ISPs behind one SSID. netpulse should **infer and show
the architecture**, because the fix depends on it (a repeater loop and an oversubscribed ISP look
the same in end-to-end numbers but need opposite actions).

| Signal to infer | How (data we can get) | Tells us |
|-----------------|-----------------------|----------|
| **Multiple APs, one LAN** | several BSSIDs sharing the SSID-root + same gateway subnet; BSSID roaming in `iw link` | mesh / multiple access points → roaming handoff quality matters |
| **Repeater / extender** | a "neighbour" BSSID with the *same SSID* but a **worse uplink**, or your traffic double-hopping (extra ~consistent RTT at hop 1) | extender is halving throughput / adding latency → advise wiring the backhaul |
| **Double-NAT** | first traceroute hop is a **private** IP *and* the gateway itself sits behind another private hop (`10.x`/`192.168.x` twice before public) | double-NAT → port-forwarding/latency issues, advise bridge mode |
| **CGNAT (ISP-side)** | public IP from `public_ip` probe is in `100.64.0.0/10`, or differs from the first public traceroute hop's prefix owner | no inbound reachability; relevant for gaming/hosting |
| **Two ISPs / load-balancer** | public IP or first-hop ASN **flips** within one network fingerprint | dual-WAN → per-flow variance is routing, not congestion |
| **Band/AP the client is stuck on** | current `freq`/BSSID vs the strongest same-SSID BSSID seen in scan | client glued to a far AP / wrong band → steering/placement fix |
| **Wired vs wireless** | interface type from `network.py` | attribution baseline (wired removes the WiFi variable) |

Model: extend `Network` with an inferred `topology` record — `ap_count`, `is_mesh`,
`has_repeater`, `double_nat`, `cgnat`, `wan_count`, `client_ap_bssid` — recomputed from the scan +
traceroute + public-IP probes, surfaced as an **architecture panel** ("this network = 1 ISP →
Telmex CPE (double-NAT) → 2 APs, you're on the far one"). Each inference carries the evidence and a
confidence, per the companion plan's principles.

## Phasing

- **P1 ✅ done (unblocks everything):** G1 gateway auto-target + G2 LAN-vs-WAN attribution + G6
  insufficient-data gate. Turns the manual session analysis into an automatic per-network verdict.
  - **Shipped:** the collector pings each network's detected `gateway_ip` as the LAN hop (static
    `lan` config targets dropped); `analysis/local_attribution.py` compares first-hop spread vs the
    **best** internet path's spread (per-target, never pooled — a real-data run caught that pooling
    inflates jitter with baseline gaps and mis-blamed the ISP); the verdict emits a "WiFi/LAN vs
    ISP/access" finding, and headline shows "insufficient data" below 30 ping cycles. Verified live:
    the engine now says *"the instability is your WiFi/LAN, not the ISP"* for Infinitum, matching the
    manual gateway-vs-Google comparison. 136 backend tests green.
- **P2 ✅ done (explains WiFi):** G3 airtime + G4 width + G10–G12 channel-advice fixes
  (RSSI-weighted, own-router-aware, width-aware). Turned the wrong "switch to 36" into correct
  advice. *(airtime is captured but driver-gated — `None` on the current adapter's `survey`.)*
- **P3 ✅ done (all networks):** G5 `network_verdicts()` + `GET /api/networks/verdicts` (every
  network graded with bottleneck layer + `user-config`/`ISP-report`/`insufficient`/`ok` action);
  G7 `lan_census` probe (`ip neigh` device count in `TopologyVerdict.lan_devices`).
- **P4 ✅ done (architecture):** G13 `analysis/topology.py` — double-NAT (short private prefix,
  not the ISP's long private access chain — real-data-corrected), CGNAT, mesh/AP count,
  stuck-on-far-AP; surfaced as verdict findings.
- **P5 ✅ done (edge signals):** G8 roam-count finding (flapping mesh handoff) + G9 bufferbloat
  layer attribution (WiFi airtime vs CPE queue, keyed on wired + local attribution).

**All 13 gaps implemented, 149 backend tests green, deployed.** Remaining refinements (not gaps):
a true mesh needs same-*band* BSSID counting (cross-band currently inflates `ap_count`, but no
finding depends on it); airtime findings await a driver that populates `survey`.

## Success criteria

For any network the user connects to, netpulse states, unattended and confidence-gated:
its grade (or "insufficient data"), the **bottleneck layer** (local/access/ISP), the **one action**
(a concrete config change *or* the exact evidence to report to the ISP) — for **every** network in
its history, not just the current device's current link.
