#!/bin/bash
# Run 1 of group-per-partition-limit-incrementGroupInCurrentPartitionCount-groupPerPartitionLimit--autonomous (tag g80, node pc12, slot 10). Usage: bash run1-chain.sh <unit-tree> <node-tree> <logdir>
# unit tier, then cluster tier (stops at the first failed first-trigger check); appends the timing lines. The cluster data (load) must already exist in /dev/shm/s4-b11-g80.
set -u
UT=${1:?}; NT=${2:?}; LD=${3:?}; H=$(cd "$(dirname "$0")" && pwd); T=/proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/stage4-runtime-verification/timing/set-A-batch-11.log
ulimit -n 100000; mkdir -p $LD
echo "$(date -u +%FT%TZ) S4 g80 unit-run start" >> $T
bash $H/unit-run.sh $UT $LD/unit; urc=$?
echo "$(date -u +%FT%TZ) S4 g80 unit-run end" >> $T
echo "$(date -u +%FT%TZ) S4 g80 cluster-run start" >> $T
python3 -I $H/cluster-run.py $NT /dev/shm/s4-b11-g80 $LD/cluster run > $LD/cluster-run.out 2>&1; crc=$?
echo "$(date -u +%FT%TZ) S4 g80 cluster-run end" >> $T
python3 -I $H/analyze_cluster.py $LD/cluster/arms 200000 > $LD/cluster-summary.txt 2>&1
echo "chain done unit_rc=$urc cluster_rc=$crc" > $LD/CHAIN_DONE
