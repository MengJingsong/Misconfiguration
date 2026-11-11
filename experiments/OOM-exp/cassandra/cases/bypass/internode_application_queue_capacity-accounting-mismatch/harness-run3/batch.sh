#!/usr/bin/env bash
# B6 run 3 batch (design/B6-run3-design.md): reruns the run-1 and run-2 conditions unchanged with
# their own harnesses; adds 3 fresh reserve-intervention arms per condition plus same-day positives.
set -u
B=$(cd "$(dirname "$0")/.." && pwd); H1=$B/harness; H2=$B/harness-run2; H3=$B/harness-run3
T="write_request_timeout=60000ms native_transport_timeout=60000ms"
RSV1="internode_application_send_queue_reserve_endpoint_capacity=8MiB internode_application_receive_queue_reserve_endpoint_capacity=8MiB"
RSV2="internode_application_receive_queue_reserve_endpoint_capacity=8MiB"
fails=0
run(){ # run <label> <cmd...>; abort after two consecutive ring failures
  echo "=== $(date '+%F %T') $1"; shift
  out=$("$@"); echo "$out"
  if grep -q "RING FAIL" <<< "$out"; then fails=$((fails+1)); [ $fails -ge 2 ] && { echo "ABORT: 2 consecutive ring failures"; cleanup; exit 1; }; else fails=0; fi
}
summ(){ # summ <dir> <instance> <heap_MiB>
  echo "    gcpeak $2: $("$H3/gcpeak.sh" "$1/$2-logs" "$3")"
}
cleanup(){ "$H2/ctl.sh" stop all >/dev/null 2>&1; "$H1/ctl.sh" stop all >/dev/null 2>&1; "$H2/slowdisk.sh" set 0; }

# ---- run-2 condition: V 8 GiB, 30 s disk stall, default timeouts, 4 coordinators ----
export HEAPDUMP=1
run R3B_V8g_map_stall_r3 "$H2/arm.sh" R3B_V8g_map_stall_r3 map 1000 8G 8G 30000
summ /mydata/b6/runs2/R3B_V8g_map_stall_r3 V 8192
mv /mydata/b6/ring2/V/dumps/*.hprof /mydata/b6/runs2/R3B_V8g_map_stall_r3/ 2>/dev/null && echo "    heap dump kept"
export HEAPDUMP=0
for r in 2 3 4; do
  n=R3B_V8g_map_stall_rsv8m_r$r
  run $n "$H2/arm.sh" $n map 1000 8G 8G 30000 $RSV2
  summ /mydata/b6/runs2/$n V 8192
done
"$H2/ctl.sh" stop all >/dev/null 2>&1; "$H2/slowdisk.sh" set 0

# ---- run-1 condition: Byteman slow V, 60 s timeouts, one instance at 2 GiB ----
for side in S V; do
  if [ $side = S ]; then SX=2G VX=8G; SH=2048; VH=8192; else SX=8G VX=2G; SH=8192; VH=2048; fi
  export HEAPDUMP=1
  n=R3A_B_${side}2g_map_pos
  run $n "$H1/arm.sh" $n map 1000 $SX $VX
  summ /mydata/b6/runs/$n S $SH; summ /mydata/b6/runs/$n V $VH
  export HEAPDUMP=0
  for r in 2 3 4; do
    n=R3A_C_${side}2g_map_rsv8m_r$r
    run $n "$H1/armx.sh" $n map 1000 $SX $VX 90 1 $T $RSV1
    summ /mydata/b6/runs/$n S $SH; summ /mydata/b6/runs/$n V $VH
  done
done
cleanup
echo "=== $(date '+%F %T') BATCH DONE"; pgrep -a java || echo "no java left"
