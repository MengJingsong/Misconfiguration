#!/usr/bin/env bash
# Run 1, cluster tier (B3e amended order): 0MiB (startfail), 2MiB, auto, 32MiB, then the B3h control lifetime at 32MiB.
# Needs: source ~/Library/Caches/stage4/env.sh. Output: $W/logs/prepared_statements_cache_size-applySimpleConfig/cluster/<label>/
H=$(cd "$(dirname "$0")" && pwd); O=$W/logs/prepared_statements_cache_size-applySimpleConfig/cluster; mkdir -p "$O"
for spec in "startfail-0 0MiB startfail" "k2 2MiB main" "kauto auto main" "k32 32MiB main" "ctl32 32MiB control"; do
  set -- $spec; echo "[$(date '+%F %T')] $1 start" >> "$O/chain.out"
  bash "$H/cluster-run.sh" "$1" "$2" "$3" > /dev/null 2>&1; echo "[$(date '+%F %T')] $1 rc=$?" >> "$O/chain.out"
done
pgrep -f org.apache.cassandra.service.CassandraDaemon >/dev/null && echo "WARNING: CassandraDaemon left" >> "$O/chain.out" || echo "no CassandraDaemon left" >> "$O/chain.out"
echo "[$(date '+%F %T')] chain done" >> "$O/chain.out"
