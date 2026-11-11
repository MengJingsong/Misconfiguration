#!/usr/bin/env bash
# B6 sampler: every INTERVAL s, S's outbound counters toward V and F, V's inbound from S,
# and S's heap (jcmd GC.heap_info, no forced GC; jstat cannot attach: Cassandra sets -XX:+PerfDisableSharedMem). Raw cqlsh rows are kept verbatim; parse afterwards
# (C1 run-3 lesson: never sum '|' separator fields).
#   sample.sh <outdir> [interval=2]      # runs until killed
set -uo pipefail
OUT=${1:?outdir}; IV=${2:-2}
BUILD=/mydata/b6/cassandra; ROOT=/mydata/b6/ring
mkdir -p "$OUT"
SP=$(cat $ROOT/S/cass.pid)
Q="SELECT address, pending_count, pending_bytes, using_reserve_bytes, overload_count, overload_bytes, expired_count, sent_count, sent_bytes FROM system_views.internode_outbound;"
QI="SELECT address, using_bytes, using_reserve_bytes, throttled_count, received_count, processed_count, expired_count FROM system_views.internode_inbound;"
while true; do
  ts=$(date +%s)
  "$BUILD/bin/cqlsh" 127.0.0.13 -e "$Q" 2>&1 | awk -v t="$ts" '/127\.0\.0\.1[12]/{print t" OUT "$0}' >> "$OUT/out.log"
  "$BUILD/bin/cqlsh" 127.0.0.11 -e "$QI" 2>&1 | awk -v t="$ts" '/127\.0\.0\.13/{print t" VIN "$0}' >> "$OUT/vin.log"
  if kill -0 "$SP" 2>/dev/null; then
    echo "$ts $(jcmd "$SP" GC.heap_info 2>/dev/null | grep -m1 -o 'total [0-9]*K, used [0-9]*K')" >> "$OUT/heap.log"
  else
    echo "$ts S_DEAD" >> "$OUT/heap.log"
  fi
  sleep "$IV"
done
