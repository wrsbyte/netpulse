# Runbook — WiFi & DNS hardening (this workstation)

Three permanent, reversible changes measured by netpulse. Each has an **activate**,
a **deactivate**, and a **verify** step. All facts here are from netpulse's own DB
(7-day window, 4341 samples per resolver) and live `dig`/`iw`, captured 2026-08-13.

## Why (the evidence, not opinion)

| Change | Before | After (target) | Basis |
|---|---|---|---|
| DNS resolver | Quad9 IPv6 only, **DoT off**, no fallback, DHCP-scoped | Quad9 primary + Google fallback, **DoT opportunistic**, `Domains=~.` (portable) | 7d: Quad9 jitter **4 ms** / fail **1.2%** vs Google 30 ms / 2.9% vs Cloudflare 55 ms / 7.1%. Median 18 ms Quad9≈Google (tie); the win is *stability + security*, not median. |
| WiFi power-save | **on** | **off** | Power-save parks the radio between beacons → latency spikes and self-inflicted deauths. netpulse saw 9 of 10 recent disconnects `locally_generated` (laptop-initiated), not the network. |
| WiFi channel | 5 GHz **149** (12–14 APs sharing it) | 5 GHz **36/40** (clean UNII-1) | netpulse scan: channel 149 = 12–14 neighbour APs; 36/40 = 0. Router-side change only (below). |
| journal access | user not in `systemd-journal` | member | netpulse's disconnect probe reads the *system* journal (wpa_supplicant); without the group the `--user` service gets `[]`. |

The DNS median is a tie on purpose — do **not** sell this as a speed win. The
substantial, verified improvements are: p95 105 vs 132 ms, jitter 4 vs 30 ms,
failure rate 1.2% vs 2.9% (Quad9 vs Google), and Cloudflare eliminated (7.1% fail).

## 1. DNS — Quad9 primary + Google fallback, portable, encrypted

**Activate** (drop-in owned by us, survives NetworkManager rewrites):

```bash
sudo install -d /etc/systemd/resolved.conf.d
sudo tee /etc/systemd/resolved.conf.d/dns.conf >/dev/null <<'EOF'
[Resolve]
DNS=9.9.9.9#dns.quad9.net 2620:fe::fe#dns.quad9.net
FallbackDNS=8.8.8.8#dns.google 2001:4860:4860::8888#dns.google
DNSOverTLS=opportunistic
Domains=~.
EOF
sudo systemctl restart systemd-resolved
```

- `Domains=~.` routes **all** lookups to these resolvers regardless of what DHCP
  hands out per-link → same trusted DNS at home, café, or tethered = portable.
- `DNSOverTLS=opportunistic` encrypts to port 853 when reachable, silently falls
  back to plaintext when it isn't → **captive portals still work** (see below).
  Flip to `yes` (strict) only on hostile networks you don't trust; strict breaks
  any network that blocks 853.

**Verify:**

```bash
resolvectl status | grep -E 'Current DNS|DNSOverTLS|DNS Domain'
resolvectl query google.com          # should resolve; +DNSOverTLS when encrypted
```

**Deactivate / revert:** `sudo rm /etc/systemd/resolved.conf.d/dns.conf && sudo systemctl restart systemd-resolved`

**Captive portals** (hotel/airport login pages): opportunistic DoT + `Domains=~.`
usually just works because NetworkManager's connectivity check triggers the portal.
If a portal won't load, temporarily let the link's own DNS win:

```bash
sudo resolvectl domain wlan0 ''      # stop forcing ~. on this link
sudo resolvectl dns wlan0 ''         # use DHCP-provided DNS for the portal
# ...log in to the portal, then restore:
sudo systemctl restart systemd-resolved
```

## 2. WiFi power-save — off, permanently

**Activate:**

```bash
sudo tee /etc/NetworkManager/conf.d/wifi-powersave-off.conf >/dev/null <<'EOF'
[connection]
wifi.powersave = 2
EOF
sudo systemctl restart NetworkManager
```

`wifi.powersave = 2` = disable (0 default, 1 don't-touch, 2 off, 3 on).

**Verify:** `iw dev wlan0 get power_save` → `Power save: off`

**Deactivate / revert:** `sudo rm /etc/NetworkManager/conf.d/wifi-powersave-off.conf && sudo systemctl restart NetworkManager`
(on battery you may want it back on to save power — that's the only reason to revert).

## 3. journal access for netpulse's disconnect probe

On this box the collector **already** reads the system journal — `/var/log/journal`
has an ACL granting `wheel` and `adm` read, and the collector runs with group
`wheel`. So no group change or re-login was actually required (verified: fresh
`wifi_disconnect` events flow, watermark advances). `usermod -aG systemd-journal
"$USER"` is a belt-and-suspenders extra if you ever move the collector out of `wheel`.

**Verify:** netpulse's Events tab shows `wifi_disconnect` rows, or
`SELECT count(*) FROM event WHERE kind='wifi_disconnect'` > 0. All recent ones are
`reason=3 local` = the laptop's own WiFi blips (suspend / config apply), not outages.

**Deactivate / revert:** `sudo gpasswd -d "$USER" systemd-journal` (then re-login).

## 4. WiFi channel — router-side (document only, not a PC change)

netpulse can *see* the congestion (scan: 12–14 APs on 149) but cannot change it —
it's a router setting. In the router admin (http://192.168.100.1):

1. WiFi 5 GHz settings → Channel: change **Auto/149 → 36** (or 40).
2. Bandwidth 80 MHz is fine on clean UNII-1.
3. Save; the 5 GHz SSID drops ~5 s and returns on the new channel.

**Verify:** `iw dev wlan0 link | grep freq` → `freq: 5180` (ch 36) or `5200` (ch 40).
netpulse's "WiFi channel N is crowded" finding clears once the scan re-reads the new channel.

## After applying — measured, with the honest caveat

Cutover ~2026-08-13 23:30. First check ~7 h later hit a real methodology trap worth
recording: the laptop **suspended overnight (01:42–07:08, a 5.4 h collection gap)**, so
wall-clock "after" was 7.7 h but only ~2.3 h were actually sampled. netpulse now detects
this (`covered_seconds`) and flags "Partial data — device was asleep" below 90% coverage;
availability is computed over covered time, not the gap.

What the short awake window supports:

- **Rate metrics (trustworthy — computed over ~22 k samples, gap-insensitive):**
  end-to-end loss to 8.8.8.8 / 9.9.9.9 ~1.0% → ~0.36%; DNS failures Quad9 2.05% → 0.75%,
  Google 3.7% → 1.33%. Loss to the **gateway** (pure local WiFi segment) fell from
  ~1–3.9%/h during the power-save + channel-149 period to ~0–0.44%/h after — isolating the
  gain to the WiFi changes, not DNS.
- **Outage count (NOT yet conclusive):** 6 outages in 8 solid pre-fix hours (0.75/h) vs
  0 in ~2 solid post-fix hours. But P(0 in 2 h | rate 0.75/h) ≈ 22% — too little data to
  claim a magnitude. Needs a full **awake** day, not just wall-clock.

Verdict: direction is positive and consistent (grade A on the clean 6 h window, all rate
metrics down), but **promising, not proven** until a full waking day accumulates. Re-run
this comparison then and require coverage ≥ 90% before trusting outage-rate deltas.

- DNS (before, 7d): Quad9 j=4/fail=1.2%, Google j=30/fail=2.9%, Cloudflare j=55/fail=7.1%.
- Power-save (before): `on`; disconnects `locally_generated`: 9/10.
