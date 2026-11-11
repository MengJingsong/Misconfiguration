#!/usr/bin/env bash
# B6 run-2 sampler (raw rows kept; parse afterwards, never sum '|' separators blindly).
#   sample.sh <outdir> [interval=3]     # until killed
# vin.log : V's internode_inbound rows for S1..S4 (using, reserve, throttled, received, processed, expired)
# sout.log: S1's internode_outbound row to V (pending, reserve, overload, expired, sent)
# vstage.log: V MutationStage active/pending/completed/blocked ; vheap.log: V heap (GC.heap_info, no forced GC)
set -uo pipefail
OUT=${1:?}; IV=${2:-3}; B=/mydata/b6/cassandra; mkdir -p "$OUT"
VP=$(cat /mydata/b6/ring2/V/cass.pid)
QI="SELECT address, using_bytes, using_reserve_bytes, throttled_count, received_count, processed_count, expired_count FROM system_views.internode_inbound;"
QO="SELECT address, pending_count, pending_bytes, using_reserve_bytes, overload_count, expired_count, sent_count FROM system_views.internode_outbound;"
while true; do
  ts=$(date +%s)
  if kill -0 "$VP" 2>/dev/null; then
    echo "$ts $(timeout 6 jcmd "$VP" GC.heap_info 2>/dev/null | grep -m1 -o 'total [0-9]*K, used [0-9]*K')" >> "$OUT/vheap.log"
    timeout 6 $B/bin/nodetool -p 7211 tpstats 2>/dev/null | awk -v t="$ts" '/^MutationStage/{print t, $2, $3, $4, $5}' >> "$OUT/vstage.log"
    timeout 6 $B/bin/cqlsh 127.0.0.11 -e "$QI" 2>&1 | awk -v t="$ts" '/127\.0\.0\.1[3-6]/{print t" "$0}' >> "$OUT/vin.log"
  else
    echo "$ts V_DEAD" >> "$OUT/vheap.log"
  fi
  timeout 6 $B/bin/cqlsh 127.0.0.13 -e "$QO" 2>&1 | awk -v t="$ts" '/127\.0\.0\.11 /{print t" "$0}' >> "$OUT/sout.log"
  sleep "$IV"
done
