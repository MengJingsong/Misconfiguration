#!/usr/bin/env bash
# Run 1, cluster tier (B3e amended order): 4MiB, 32MiB, auto (= 50 MiB at -Xmx2G), one node lifetime each.
# usage: cluster-chain.sh [shakedown]   (shakedown: one 2MiB lifetime with NW=100000, NC=200 under .../shakedown/; not evidence)
# Needs: source ~/Library/Caches/stage4/env.sh. Output: $W/logs/counter_cache_size-applySimpleConfig/cluster/<label>/
H=$(cd "$(dirname "$0")" && pwd)
if [ "${1:-}" = shakedown ]; then
  O=$W/logs/counter_cache_size-applySimpleConfig/shakedown; mkdir -p "$O"
  echo "[$(date '+%F %T')] sd-c2 start" >> "$O/chain.out"
  OUT=$O NW=100000 NC=200 bash "$H/cluster-run.sh" sd-c2 2MiB > /dev/null 2>&1; echo "[$(date '+%F %T')] sd-c2 rc=$?" >> "$O/chain.out"
else
  O=$W/logs/counter_cache_size-applySimpleConfig/cluster; mkdir -p "$O"
  for spec in "c4 4MiB" "c32 32MiB" "cauto auto"; do
    set -- $spec; echo "[$(date '+%F %T')] $1 start" >> "$O/chain.out"
    OUT=$O bash "$H/cluster-run.sh" "$1" "$2" > /dev/null 2>&1; echo "[$(date '+%F %T')] $1 rc=$?" >> "$O/chain.out"
  done
fi
pgrep -f org.apache.cassandra.service.CassandraDaemon >/dev/null && echo "WARNING: CassandraDaemon left" >> "$O/chain.out" || echo "no CassandraDaemon left" >> "$O/chain.out"
echo "[$(date '+%F %T')] chain done" >> "$O/chain.out"
