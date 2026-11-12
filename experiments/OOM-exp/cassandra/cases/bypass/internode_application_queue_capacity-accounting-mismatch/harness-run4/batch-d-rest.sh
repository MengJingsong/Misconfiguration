#!/usr/bin/env bash
# B6 run 4, phase D remainder after batch-d.sh was stopped by the agent tool time limit during blob r3
# (2026-11-11 22:43): no-stall control, reserves x3, patch x3 at S 512 MiB.
set -u
H=$(cd "$(dirname "$0")" && pwd); H2=$H/../harness-run2
RSV="internode_application_send_queue_reserve_endpoint_capacity=8MiB internode_application_receive_queue_reserve_endpoint_capacity=8MiB"
fails=0
run(){ local n=$1; shift
  echo "=== $(date '+%F %T') $n"
  out=$("$H/arm.sh" "$n" "$@"); echo "$out"
  [ -d /mydata/b6/runs4/$n/S-logs ] && python3 -I "$H/gcwin.py" /mydata/b6/runs4/$n/S-logs | tee -a /mydata/b6/runs4/$n/outcome.txt
  if grep -q "RING FAIL" <<< "$out"; then fails=$((fails+1)); [ $fails -ge 2 ] && { echo ABORT; "$H/ctl.sh" stop all; "$H2/slowdisk.sh" set 0; exit 1; }; else fails=0; fi
}
export HEAPDUMP=1

export HEAPDUMP=0

run R4D_S512m_map_nostall_r1 map 1000 512M 0
for r in 1 2 3; do run R4D_S512m_map_rsv8m_r$r map 1000 512M 30000 $RSV; done
for r in 1 2 3; do BUILD=/mydata/b6/cassandra-p4 run R4D_S512m_map_patch_r$r map 1000 512M 30000; done
"$H/ctl.sh" stop all; "$H2/slowdisk.sh" set 0
echo "=== $(date '+%F %T') BATCH DONE"; pgrep -a java || echo "no java left"
