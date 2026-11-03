#!/usr/bin/env bash
# Run 1, cluster tier (B3e amended order): c2 (2MiB, 1m), c8 (8MiB, 1m), cauto (auto = 102 MiB at -Xmx2G, 1m), c2null (2MiB, null).
# usage: cluster-chain.sh [shakedown]   (shakedown: one 1MiB/1m lifetime with NW=1500000, NR=100000 under .../shakedown/; not evidence)
# Needs: source ~/Library/Caches/stage4/env.sh. Output: $W/logs/index_summary_capacity-applySimpleConfig/cluster/<label>/
H=$(cd "$(dirname "$0")" && pwd)
if [ "${1:-}" = shakedown ]; then
  O=$W/logs/index_summary_capacity-applySimpleConfig/shakedown; mkdir -p "$O"
  echo "[$(date '+%F %T')] sd-c1 start" >> "$O/chain.out"
  OUT=$O NW=1500000 NR=100000 bash "$H/cluster-run.sh" sd-c1 1MiB 1m > /dev/null 2>&1; echo "[$(date '+%F %T')] sd-c1 rc=$?" >> "$O/chain.out"
else
  O=$W/logs/index_summary_capacity-applySimpleConfig/cluster; mkdir -p "$O"
  for spec in "c2 2MiB 1m" "c8 8MiB 1m" "cauto auto 1m" "c2null 2MiB null"; do
    set -- $spec; echo "[$(date '+%F %T')] $1 start" >> "$O/chain.out"
    OUT=$O bash "$H/cluster-run.sh" "$1" "$2" "$3" > /dev/null 2>&1; echo "[$(date '+%F %T')] $1 rc=$?" >> "$O/chain.out"
  done
fi
pgrep -f org.apache.cassandra.service.CassandraDaemon >/dev/null && echo "WARNING: CassandraDaemon left" >> "$O/chain.out" || echo "no CassandraDaemon left" >> "$O/chain.out"
echo "[$(date '+%F %T')] chain done" >> "$O/chain.out"
