#!/usr/bin/env bash
# B6 run 4, phase D at the largest failing default-timeout budget (S 512 MiB): repeats, controls,
# interventions (design/B6-run4-design.md §5). Budget-search arms (2G, 1G, 768M, 640M, 512M r1) were run
# one by one with arm.sh before this batch.
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
run R4D_S512m_map_r2 map 1000 512M 30000
run R4D_S512m_map_r3 map 1000 512M 30000
export HEAPDUMP=0
for r in 1 2 3; do run R4D_S512m_blob_r$r blob 11000 512M 30000; done
run R4D_S512m_map_nostall_r1 map 1000 512M 0
for r in 1 2 3; do run R4D_S512m_map_rsv8m_r$r map 1000 512M 30000 $RSV; done
for r in 1 2 3; do BUILD=/mydata/b6/cassandra-p4 run R4D_S512m_map_patch_r$r map 1000 512M 30000; done
"$H/ctl.sh" stop all; "$H2/slowdisk.sh" set 0
echo "=== $(date '+%F %T') BATCH DONE"; pgrep -a java || echo "no java left"
