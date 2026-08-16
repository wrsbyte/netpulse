# Data versions — changelog & trust notes

Every collected sample stores the `code_version` that produced it. This file maps each version to
what changed in the *measurement* and **what you can and cannot trust across the boundary**. Newest
first. See [DATA_VERSIONING.md](DATA_VERSIONING.md) for the how; [CONVENTIONS.md](CONVENTIONS.md#data-versioning-provenance--trust)
for the bump rules.

## 0.2.0 — honest loss & grade (MINOR: measurement method changed)

**Changed**
- **Loss from tx/rx counts, deterministic sample.** Ping loss is computed from
  transmitted/received counts over a fixed **10-packet** cycle (`-c 10 -i 0.2 -W 1`). Was: parsed
  from the printed `%` over a 4-packet burst with `-w` (an overall deadline that let a lossy cycle
  send 11-15 packets, drifting the denominator).
- **No fabricated outages.** A missing/garbled ping summary is now a *measurement gap*
  (`sample()→None`, dropped), not a `100%`-loss row; outage detection needs every internet target
  present AND confirmed down.
- **Grade on forward-path (TCP) loss.** The health grade's loss input is the `tcp_connect`
  handshake failure rate to the internet resolvers, not ICMP (which routers rate-limit into phantom
  loss). ICMP loss is still stored/surfaced as `typical_loss` for findings.

**Trust**
- ✅ First version whose **loss and grade are trustworthy** for real user-facing impact.
- ⚠️ **Do NOT compare loss or grade across the 0.1.x → 0.2.0 boundary.** Pre-0.2.0 loss over-reports
  (ICMP quantization + rate-limiting + fabricated 100% cycles); a live verdict sat at "F" purely on
  that artifact, vs "A" measured correctly at 0.2.0.
- ✅ RTT/jitter, WiFi, DNS timing are comparable across the boundary (unchanged).

## 0.0.0 — pre-versioning (sentinel: provenance unknown)

Rows collected before per-sample versioning existed, backfilled to `0.0.0`. **Do not trust for
cross-version comparison.** Known issues: ping `-c` drifted from the committed value (loss quantized
as 1/5 while code said 1/4 — not reproducible); loss defaulted to `100%` on a parse miss
(fabricated outages); the grade was fed rate-limited ICMP loss. RTT is broadly fine; loss/grade are
not.
