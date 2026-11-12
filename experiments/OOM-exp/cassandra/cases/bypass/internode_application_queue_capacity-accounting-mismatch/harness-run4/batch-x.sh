#!/usr/bin/env bash
# B6 run 4, phase X (diagnostic): as phase D plus 60 s write and native-transport timeouts on all
# instances; no Byteman (storage stall on V1+V2). Upward budget search 2 -> 4 -> 8 -> 12 -> 16 GiB
# (n=1 until the first survival, survival confirmed once), then x3 map (incl. the search arm), blob x3
# and send+receive endpoint reserves 8 MiB x3 at the largest failing budget (design §5).
set -u
H=$(cd "$(dirname "$0")" && pwd); H2=$H/../harness-run2
T="write_request_timeout=60000ms native_transport_timeout=60000ms"
RSV="internode_application_send_queue_reserve_endpoint_capacity=8MiB internode_application_receive_queue_reserve_endpoint_capacity=8MiB"
fails=0
run(){ local n=$1; shift
  echo "=== $(date '+%F %T') $n"
  out=$("$H/arm.sh" "$n" "$@"); echo "$out"
  [ -d /mydata/b6/runs4/$n/S-logs ] && python3 -I "$H/gcwin.py" /mydata/b6/runs4/$n/S-logs | tee -a /mydata/b6/runs4/$n/outcome.txt
  if grep -q "RING FAIL" <<< "$out"; then fails=$((fails+1)); [ $fails -ge 2 ] && { echo ABORT; "$H/ctl.sh" stop all; "$H2/slowdisk.sh" set 0; exit 1; }; else fails=0; fi
}
failed(){ grep -q "S DEAD\|service_loss(all STW)=MET\|oom_marks=HeapDumper" /mydata/b6/runs4/$1/outcome.txt; }
export HEAPDUMP=1
last=""; for b in 2 4 8 12 16; do
  run R4X_S${b}g_map_r1 map 1000 ${b}G 30000 $T
  if failed R4X_S${b}g_map_r1; then last=$b; else
    run R4X_S${b}g_map_r2 map 1000 ${b}G 30000 $T      # confirm the survival
    failed R4X_S${b}g_map_r2 && { last=$b; continue; }
    break
  fi
done
echo "=== largest failing budget in search: ${last:-none} GiB"
[ -z "$last" ] && { "$H/ctl.sh" stop all; "$H2/slowdisk.sh" set 0; exit 0; }
for r in 2 3; do [ -d /mydata/b6/runs4/R4X_S${last}g_map_r$r ] || run R4X_S${last}g_map_r$r map 1000 ${last}G 30000 $T; done
export HEAPDUMP=0
for r in 1 2 3; do run R4X_S${last}g_blob_r$r blob 11000 ${last}G 30000 $T; done
for r in 1 2 3; do run R4X_S${last}g_map_rsv8m_r$r map 1000 ${last}G 30000 $T $RSV; done
"$H/ctl.sh" stop all; "$H2/slowdisk.sh" set 0
echo "=== $(date '+%F %T') BATCH DONE"; pgrep -a java || echo "no java left"
