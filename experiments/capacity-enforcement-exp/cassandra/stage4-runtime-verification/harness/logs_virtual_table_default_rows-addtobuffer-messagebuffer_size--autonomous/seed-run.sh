#!/usr/bin/env bash
# B3e step 1: start a stock node (build A, appender off) on empty data, seed 40 x 25 tables, drain, stop, keep the data in ~/stage4-tmp/lv/seed.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=$HOME/s4-lv; N=$HOME/stage4-tmp/lv/node; S=$HOME/stage4-tmp/lv/seed; L=$HOME/stage4-logs/lv/seed; mkdir -p $L
[ -z "$(ps -eo cmd | grep '[C]assandraDaemon')" ] || { echo "daemon already running"; exit 1; }
rm -rf $N $S; T=$N $H/make-node.sh off $C | tee $L/make-node.out
( ulimit -n 100000; cd $C; CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$N/logs MAX_HEAP_SIZE=1G HEAP_NEWSIZE=256M JVM_EXTRA_OPTS="-Dcassandra.virtual.logs.max.rows=100000" nohup bin/cassandra -f > $N/stdout.txt 2>&1 & )
for i in $(seq 1 100); do [ "$($C/bin/nodetool statusbinary 2>/dev/null)" = running ] && break; sleep 3; done
python3 $H/seed.py $C/lib 2>&1 | tee $L/seed.out
$C/bin/nodetool flush; $C/bin/nodetool drain; $C/bin/nodetool stopdaemon; sleep 10
ps -eo cmd | grep '[C]assandraDaemon' && { echo "daemon left"; pkill -f CassandraDaemon; }
mkdir -p $S; for d in data commitlog saved_caches hints; do cp -a $N/$d $S/; done
cp $N/logs/system.log $L/system.log; du -sh $S | tee $L/du.out; rm -rf $N
echo "seed done"
