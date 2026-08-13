#!/usr/bin/env bash
# Report which probe tools are available. netpulse degrades gracefully: a missing tool
# only disables its own metric. Required tools are core; optional ones unlock extras.
set -euo pipefail

check() {
  local tool=$1 kind=$2 unlocks=$3
  if command -v "$tool" >/dev/null 2>&1; then
    printf '  \033[32m✓\033[0m %-12s %s\n' "$tool" "$unlocks"
  elif [ "$kind" = required ]; then
    printf '  \033[31m✗\033[0m %-12s MISSING (required) — %s\n' "$tool" "$unlocks"
  else
    printf '  \033[33m•\033[0m %-12s optional — %s\n' "$tool" "$unlocks"
  fi
}

echo "Required:"
check ping required "connectivity & latency"
check iw   required "WiFi radio quality"
check dig  required "DNS resolution timing"
check ss   required "active connections / flows"
check curl required "public IP detection"

echo "Optional (unlock more data):"
check mtr          optional "per-hop loss (needs scoped sudo — see sudoers.d/netpulse)"
check tracepath    optional "path tracing fallback (no root)"
check nmcli        optional "neighbor AP / channel-congestion scan"
check speedtest    optional "active bandwidth + bufferbloat grade"
check notify-send  optional "desktop alert notifications"

echo
echo "Passwordless sudo for mtr (optional):"
if sudo -n mtr --help >/dev/null 2>&1; then
  echo -e "  \033[32m✓\033[0m mtr runs without a password (per-hop loss enabled)"
else
  echo -e "  \033[33m•\033[0m not configured — install scripts/sudoers.d/netpulse to enable per-hop loss"
fi
