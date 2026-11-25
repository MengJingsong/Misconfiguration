#!/bin/bash
# o125 cluster tier: B3e step 9 order (two sets + one stock no-stall run). Runs ON the node.
WORK=/mydata/jingsong-cass-s4/o125
exec > >(tee -a $WORK/logs/cluster-all.log) 2>&1
set -x
date -u
echo $$ > /mydata/s4/DRIVER-jingsong-c125.pid
for spec in "s1-stock stock stall" "s1-1m 1m stall" "s1-256m 256m stall" "s2-stock stock stall" "s2-1m 1m stall" "s2-256m 256m stall" "nostall-stock stock nostall"; do
  set -- $spec
  bash $WORK/harness/cluster-run.sh $1 $2 $3; rc=$?; [ $rc = 0 ] || { echo "RUN $1 FAILED rc=$rc"; exit 1; }
  ps -eo pid,cmd | grep -E '[C]assandraDaemon|[S]tress|[S]ampler 7199' && { echo "leftover processes; stopping"; exit 1; }
done
date -u
rm -f /mydata/s4/DRIVER-jingsong-c125.pid
