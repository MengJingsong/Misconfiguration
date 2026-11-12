#!/bin/bash
# B3e as filed, with amendment A2. Usage: bash cluster-run.sh <label> <P|default> <offheap_buffers|heap_buffers>
# Logs and readings under $WORK/run1/cluster/<label>/. Stops at the first failed check; always stops its node.
set -uo pipefail
LABEL=$1; P=$2; ALLOC=$3
WORK=/mydata/jingsong-cass-s4/o43; HARNESS=$(cd "$(dirname "$0")" && pwd)
OUT=$WORK/run1/cluster/$LABEL; mkdir -p $OUT
exec > >(tee -a $OUT/session.log) 2>&1
ts() { echo "### $(date -u +%FT%T.%3NZ) $*"; }
NT() { $WORK/src/bin/nodetool -h 127.0.0.1 -p 7499 "$@"; }
PID=""
cleanup() {
  ts "teardown"
  if [ -n "$PID" ] && kill -0 $PID 2>/dev/null; then
    NT stopdaemon || true
    for i in $(seq 1 60); do kill -0 $PID 2>/dev/null || break; sleep 1; done
    kill -0 $PID 2>/dev/null && { echo "kill $PID"; kill $PID; sleep 5; kill -9 $PID 2>/dev/null; }
  fi
  ps -eo pid,cmd | grep '[C]assandraDaemon' | grep "$WORK" && echo "LEFTOVER" || echo "no o43 CassandraDaemon left"
}
trap cleanup EXIT
fail() { ts "FAIL: $*"; exit 1; }
cd $WORK/src
ts "label=$LABEL P=$P alloc=$ALLOC"
for p in 7300 7301 7499 9342; do ss -ltn | grep -q ":$p " && fail "port $p busy"; done
bash $HARNESS/setup-conf.sh > $OUT/conf-diff.txt
sed -i "s/^memtable_allocation_type: .*/memtable_allocation_type: $ALLOC/" conf/cassandra.yaml
grep -E '^(memtable_allocation_type|row_cache_class_name|row_cache_size|memtable_heap_space|memtable_offheap_space|native_transport_port|storage_port):' conf/cassandra.yaml
rm -rf $WORK/node/{data,commitlog,hints,saved_caches,cdc}/* ; mkdir -p $WORK/node/{data,commitlog,hints,saved_caches,cdc,logs}
rm -f $WORK/node/pid
EXTRA=""; [ "$P" != default ] && EXTRA="-Dcassandra.data_output_stream_plus_temp_buffer_size=$P"
ts "start node"
env MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M MAX_DIRECT_MEMORY_SIZE=2G CASSANDRA_LOG_DIR=$WORK/node/logs JVM_EXTRA_OPTS="$EXTRA" \
  bin/cassandra -p $WORK/node/pid > $OUT/cassandra-stdout.log 2>&1 < /dev/null
for i in $(seq 1 60); do [ -s $WORK/node/pid ] && break; sleep 1; done
PID=$(cat $WORK/node/pid) || fail "no pid file"
echo "PID=$PID"
for i in $(seq 1 120); do
  kill -0 $PID 2>/dev/null || fail "daemon died during start"
  NT status 2>/dev/null | grep -q '^UN' && NT statusbinary 2>/dev/null | grep -q running && break
  sleep 2
done
NT status | grep '^UN' || fail "node not UN"
ps -o pid,args -p $PID | tr ' ' '\n' | grep -E 'Xmx|MaxDirectMemorySize|data_output_stream_plus|UseG1GC'
ts "jinfo"
jinfo -sysprops $PID | grep data_output_stream_plus || echo "P unset (default 8192)"
Z=$(ls $WORK/src/lib/cassandra-driver-internal-only-*.zip); V=$(basename $Z .zip); export PYTHONPATH=$Z/cassandra-driver-${V#cassandra-driver-internal-only-}   # defect D1 / amendment A5
ts "write 64 x 4 MiB"
python3 $HARNESS/o43.py write 64 4194304 1 > $OUT/write.log 2>&1 || { tail -20 $OUT/write.log; fail "write"; }
tail -3 $OUT/write.log
NT tablestats o43.t | grep -E 'SSTable count|Memtable data size|Memtable off heap|Off heap memory' | tee $OUT/tablestats-before.txt
ts "info before reads"; NT info | grep -E 'Row Cache|Heap Memory|Off Heap' | tee $OUT/info-before.txt
ts "H0"; jcmd $PID GC.class_histogram > $OUT/hist0-full.txt; grep -E ' \[B$' $OUT/hist0-full.txt | tee $OUT/h0.txt; grep '^Total' $OUT/hist0-full.txt
ts "JFR start"; jcmd $PID JFR.start name=o43 settings=profile filename=$WORK/run1/cluster/o43-$LABEL.jfr
ts "read 64, concurrency 32"
python3 $HARNESS/o43.py read 64 0 32 > $OUT/read.log 2>&1; cat $OUT/read.log | tail -3
ts "JFR dump/stop"; jcmd $PID JFR.dump name=o43; jcmd $PID JFR.stop name=o43
ts "info after reads"; NT info | grep -E 'Row Cache|Heap Memory|Off Heap' | tee $OUT/info-after.txt
NT tablestats o43.t | grep -E 'SSTable count' | tee $OUT/tablestats-after.txt
ts "H1"; jcmd $PID GC.class_histogram > $OUT/hist1-full.txt; grep -E ' \[B$' $OUT/hist1-full.txt | tee $OUT/h1.txt; grep '^Total' $OUT/hist1-full.txt
ts "jfr print"
jfr print --json --events 'jdk.ObjectAllocationOutsideTLAB,jdk.ObjectAllocationInNewTLAB' --stack-depth 64 $WORK/run1/cluster/o43-$LABEL.jfr > $WORK/run1/cluster/jfr-$LABEL.json
python3 $HARNESS/jfr-parse.py $WORK/run1/cluster/jfr-$LABEL.json | tee $OUT/jfr.txt
grep -E '^(ERROR|WARN)' $WORK/node/logs/system.log | grep -v -E 'jemalloc|swap|JMX is not|maximum number of memory|Using AuthenticatedUser|no supported jemalloc' | head -20 > $OUT/system-warn-error.txt || true
cp $WORK/node/logs/system.log $OUT/system.log
ts "done"
