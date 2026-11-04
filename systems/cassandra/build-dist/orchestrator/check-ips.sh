#!/usr/bin/env bash
# Discovers each node's experiment-LAN IP by SSHing in and inspecting its
# interfaces, then writes the result directly into config/environment.sh's
# CLUSTER_IP array. Safe to re-run (e.g. after a CloudLab experiment swap
# changes the LAN addresses) -- it replaces the whole CLUSTER_IP block each
# time and keeps a config/environment.sh.bak of the previous version.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "$SCRIPT_DIR/config.sh"

CONFIG_FILE="$REPO_ROOT/config/environment.sh"

# All addresses on this experiment's nodes have been observed to be
# 10.10.1.x; fall back to any RFC1918 private address (excluding
# loopback) if that specific subnet isn't found, so this still works if a
# different experiment topology assigns a different LAN subnet.
find_lan_ip() {
  local idx="$1"
  local addrs
  addrs="$(ssh_node "$idx" "ip -4 -o addr show | awk '{print \$4}' | cut -d/ -f1" 2>/dev/null)" || true

  local ip
  ip="$(echo "$addrs" | grep -E '^10\.10\.1\.' | head -1)"
  if [[ -z "$ip" ]]; then
    ip="$(echo "$addrs" | grep -E '^(10\.|172\.(1[6-9]|2[0-9]|3[0-1])\.|192\.168\.)' | grep -v '^127\.' | head -1)"
  fi
  echo "$ip"
}

echo "Discovering CLUSTER_IP for each node ..."
declare -A found
missing=0
for idx in "${NODE_INDEXES[@]}"; do
  ip="$(find_lan_ip "$idx")"
  found[$idx]="$ip"
  if [[ -n "$ip" ]]; then
    echo "  node${idx} (${SSH_HOST[$idx]}): $ip"
  else
    echo "  node${idx} (${SSH_HOST[$idx]}): NOT FOUND -- leaving blank, check manually" >&2
    missing=1
  fi
done

block="# Experiment-LAN IP per node, last discovered by check-ips.sh on $(date -u +%Y-%m-%dT%H:%MZ)."
block+=$'\n'"declare -A CLUSTER_IP=("
for idx in "${NODE_INDEXES[@]}"; do
  block+=$'\n'"  [$idx]=\"${found[$idx]}\""
done
block+=$'\n'")"

cp "$CONFIG_FILE" "$CONFIG_FILE.bak"

awk -v block="$block" '
  BEGIN { skip = 0; bufn = 0 }
  {
    if (skip == 1) {
      if ($0 ~ /^\)/) skip = 0
      next
    }
    if ($0 ~ /^#/) { buf[++bufn] = $0; next }
    if ($0 ~ /^declare -A CLUSTER_IP=\(/) {
      bufn = 0
      print block
      skip = 1
      next
    }
    for (i = 1; i <= bufn; i++) print buf[i]
    bufn = 0
    print
  }
  END { for (i = 1; i <= bufn; i++) print buf[i] }
' "$CONFIG_FILE" > "$CONFIG_FILE.tmp"
mv "$CONFIG_FILE.tmp" "$CONFIG_FILE"

echo
echo "config/environment.sh updated (previous version saved to config/environment.sh.bak)."
if [[ "$missing" -eq 1 ]]; then
  echo "One or more nodes' IPs could not be discovered -- check config/environment.sh and fill in manually." >&2
fi
