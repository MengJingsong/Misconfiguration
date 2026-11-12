#!/usr/bin/env bash
# B6 run 4, final batch (design amendment A2).
set -u
H=$(cd "$(dirname "$0")" && pwd); H2=$H/../harness-run2
T="write_request_timeout=60000ms native_transport_timeout=60000ms"
RSV="internode_application_send_queue_reserve_endpoint_capacity=8MiB internode_application_receive_queue_reserve_endpoint_capacity=8MiB"
run(){ local n=$1; shift; echo "=== $(date '+%F %T') $n"; "$H/arm.sh" "$n" "$@"
  [ -d /mydata/b6/runs4/$n/S-logs ] && python3 -I "$H/gcwin.py" /mydata/b6/runs4/$n/S-logs | tee -a /mydata/b6/runs4/$n/outcome.txt; }
failed(){ grep -q "S DEAD\|service_loss(all STW)=MET\|oom_marks=HeapDumper" /mydata/b6/runs4/$1/outcome.txt; }
mv /mydata/b6/runs4/R4D_S512m_blob_r3 /mydata/b6/runs4/R4D_S512m_blob_r3_interrupted
HEAPDUMP=0 run R4D_S512m_blob_r3 blob 11000 512M 30000
HEAPDUMP=1 BUILD=/mydata/b6/cassandra-p4 run R4D_S512m_map_patch_dump map 1000 512M 30000
HEAPDUMP=1 run R4D_S512m_map_rsv8m_dump map 1000 512M 30000 $RSV
export HEAPDUMP=1
run R4X_S6g_map_r1 map 1000 6G 30000 $T
if failed R4X_S6g_map_r1; then run R4X_S6g_map_r2 map 1000 6G 30000 $T; run R4X_S6g_map_r3 map 1000 6G 30000 $T
else run R4X_S6g_map_r2 map 1000 6G 30000 $T; fi
"$H/ctl.sh" stop all; "$H2/slowdisk.sh" set 0
echo "=== $(date '+%F %T') BATCH DONE"; pgrep -af java | grep -c ring4 || true
