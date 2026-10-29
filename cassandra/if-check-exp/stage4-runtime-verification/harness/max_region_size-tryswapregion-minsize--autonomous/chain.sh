#!/usr/bin/env bash
# Whole run 1 (as amended 2026-10-28): unit tier (arms R1024 on ~/s4-mrs, R256 on ~/s4-mrs256), then the cluster tier (six node starts).
# Output: $LOGS/run1/{unit,cluster}/ and $LOGS/run1/chain.log.   usage: chain.sh [unit|cluster|all]
H=$(cd "$(dirname "$0")" && pwd); LOGS=${LOGS:-$HOME/stage4-logs/mrs}; R=$LOGS/run1; mkdir -p "$R"
which=${1:-all}
{
if [ "$which" != cluster ]; then
  echo "#### unit $(date -u +%FT%TZ)"
  export OUT=$R/unit
  "$H/unit-all.sh" R1024 $HOME/s4-mrs; "$H/unit-all.sh" R256 $HOME/s4-mrs256
fi
if [ "$which" != unit ]; then
  export OUT=$R/cluster; export CASSANDRA_HOME=$HOME/s4-mrs
  # label alloc offheap_space cleanup T blob
  for arm in "big1 offheap_objects 512MiB 0.99 1 1" "big50 offheap_objects 512MiB 0.99 50 1" "big150 offheap_objects 512MiB 0.99 150 1" \
             "small150 offheap_objects 32MiB none 150 0" "heap150 heap_buffers 512MiB 0.99 150 0" "idle offheap_objects 512MiB 0.99 0 0"; do
    set -- $arm
    echo "#### cluster arm $1 $(date -u +%FT%TZ)"
    "$H/cluster-run.py" "$@" > "$R/arm-$1.out" 2>&1; echo "arm $1 rc=$?"
    grep -E "DELTA|WORKLOAD|daemons left" "$R/arm-$1.out"
    ps -eo cmd | grep '[C]assandraDaemon' && echo "LEFTOVER DAEMON"
  done
fi
echo "#### chain done $(date -u +%FT%TZ)"
} 2>&1 | tee -a "$R/chain.log"
