#!/usr/bin/env bash
# Run 1, cluster tier (B3e amended order): 8MiB, 64MiB, auto (= 100 MiB at -Xmx2G), one node lifetime each.
# usage: cluster-chain.sh [shakedown]   (shakedown: one 2MiB lifetime with NW=NR=100000, NC=5000 under .../shakedown/; not evidence)
# Needs: source ~/Library/Caches/stage4/env.sh. Output: ${KCS_OUT:-$W/logs/key_cache_size-applySimpleConfig/cluster}/<label>/ (env C, KCS_NODE, KCS_OUT pass through to cluster-run.sh)
H=$(cd "$(dirname "$0")" && pwd)
if [ "${1:-}" = shakedown ]; then
  O=$W/logs/key_cache_size-applySimpleConfig/shakedown; mkdir -p "$O"
  echo "[$(date '+%F %T')] sd-k2 start" >> "$O/chain.out"
  OUT=$O NW=100000 NR=100000 NC=5000 bash "$H/cluster-run.sh" sd-k2 2MiB > /dev/null 2>&1; echo "[$(date '+%F %T')] sd-k2 rc=$?" >> "$O/chain.out"
else
  O=${KCS_OUT:-$W/logs/key_cache_size-applySimpleConfig/cluster}; mkdir -p "$O"   # KCS_OUT: cluster re-run 2026-10-25 (H4)
  for spec in "k8 8MiB" "k64 64MiB" "kauto auto"; do
    set -- $spec; echo "[$(date '+%F %T')] $1 start" >> "$O/chain.out"
    OUT=$O bash "$H/cluster-run.sh" "$1" "$2" > /dev/null 2>&1; echo "[$(date '+%F %T')] $1 rc=$?" >> "$O/chain.out"
  done
fi
pgrep -f org.apache.cassandra.service.CassandraDaemon >/dev/null && echo "WARNING: CassandraDaemon left" >> "$O/chain.out" || echo "no CassandraDaemon left" >> "$O/chain.out"
echo "[$(date '+%F %T')] chain done" >> "$O/chain.out"
