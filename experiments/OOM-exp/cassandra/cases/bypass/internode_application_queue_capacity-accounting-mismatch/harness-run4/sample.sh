#!/usr/bin/env bash
# B6 run-4 sampler (raw rows kept).   sample.sh <outdir> [interval=3]   # until killed
# sout.log : S's internode_outbound rows to V1/V2/F (pending_count, pending_bytes, reserve, overload, expired, sent)
# vin.log  : V1/V2 internode_inbound rows from S (using, reserve, throttled, received, processed, expired)
# sheap.log: S heap (GC.heap_info, no forced GC); vstage.log: V1/V2 MutationStage active/pending/completed/blocked
set -uo pipefail
OUT=${1:?}; IV=${2:-3}; B=/mydata/b6/cassandra; mkdir -p "$OUT"
SP=$(cat /mydata/b6/ring4/S/cass.pid)
QI="SELECT address, using_bytes, using_reserve_bytes, throttled_count, received_count, processed_count, expired_count FROM system_views.internode_inbound;"
QO="SELECT address, pending_count, pending_bytes, using_reserve_bytes, overload_count, expired_count, sent_count FROM system_views.internode_outbound;"
while true; do
  ts=$(date +%s)
  if kill -0 "$SP" 2>/dev/null; then
    echo "$ts $(timeout 6 jcmd "$SP" GC.heap_info 2>/dev/null | grep -m1 -o 'total [0-9]*K, used [0-9]*K')" >> "$OUT/sheap.log"
    timeout 6 $B/bin/cqlsh 127.0.0.13 -e "$QO" 2>&1 | awk -v t="$ts" '/127\.0\.0\.1[127] /{print t" "$0}' >> "$OUT/sout.log"
  else
    echo "$ts S_DEAD" >> "$OUT/sheap.log"
  fi
  for v in 11:7211 17:7217; do
    timeout 6 $B/bin/nodetool -p ${v#*:} tpstats 2>/dev/null | awk -v t="$ts" -v n="${v%%:*}" '/^MutationStage/{print t, n, $2, $3, $4, $5}' >> "$OUT/vstage.log"
    timeout 6 $B/bin/cqlsh 127.0.0.${v%%:*} -e "$QI" 2>&1 | awk -v t="$ts" -v n="${v%%:*}" '/127\.0\.0\.13 /{print t" V"n" "$0}' >> "$OUT/vin.log"
  done
  sleep "$IV"
done
