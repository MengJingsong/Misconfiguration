#!/usr/bin/env bash
# B6 run 4, amendment A3: matched blob x3 and endpoint reserves 8 MiB x3 at S 6 GiB, 60 s timeouts.
set -u
H=$(cd "$(dirname "$0")" && pwd); H2=$H/../harness-run2
T="write_request_timeout=60000ms native_transport_timeout=60000ms"
RSV="internode_application_send_queue_reserve_endpoint_capacity=8MiB internode_application_receive_queue_reserve_endpoint_capacity=8MiB"
run(){ local n=$1; shift; echo "=== $(date '+%F %T') $n"; "$H/arm.sh" "$n" "$@"
  [ -d /mydata/b6/runs4/$n/S-logs ] && python3 -I "$H/gcwin.py" /mydata/b6/runs4/$n/S-logs | tee -a /mydata/b6/runs4/$n/outcome.txt; }
grep -q "S DEAD\|service_loss(all STW)=MET\|oom_marks=HeapDumper" /mydata/b6/runs4/R4X_S6g_map_r3/outcome.txt || { echo "6G r3 survived: nothing more"; exit 0; }
export HEAPDUMP=0
for r in 1 2 3; do run R4X_S6g_blob_r$r blob 11000 6G 30000 $T; done
for r in 1 2 3; do run R4X_S6g_map_rsv8m_r$r map 1000 6G 30000 $T $RSV; done
"$H/ctl.sh" stop all; "$H2/slowdisk.sh" set 0
echo "=== $(date '+%F %T') BATCH DONE"
