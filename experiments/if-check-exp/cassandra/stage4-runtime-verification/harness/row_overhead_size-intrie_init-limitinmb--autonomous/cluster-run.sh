#!/usr/bin/env bash
# usage: cluster-run.sh <label> <knob-MB|default> <n_keys> <offheap_buffers|heap_buffers> <shards 1|default> <trie|skiplist> [threads=16]
#   (case B3e, as amended 2026-10-27).  One arm: fresh data dir, one node (MAX_HEAP_SIZE 16G, MaxDirectMemorySize 10g, NMT, the knob
#   -Dcassandra.memtable.row_overhead_size, -Dcassandra.memtable.shard.count=1 unless shards=default), the table created by cqlsh
#   with the given memtable, JMX poll every 100 ms of the direct pool, the heap, MemtableOffHeapSize and MemtableOnHeapSize,
#   cassandra-stress user profile trie.yaml (n_keys inserts), tablestats, system.log, drain, stop. Output: $OUT/<label>/.
set -uo pipefail
label=$1; knob=$2; n=$3; alloc=$4; shards=$5; mt=$6; thr=${7:-16}
HARN=$(cd "$(dirname "$0")" && pwd)
C=${CASSANDRA_HOME:-$HOME/c4-ros}; T=$HOME/stage4-ros/node; export T; OUT=${OUT:-$HOME/stage4-logs/ros/run1/cluster}/$label
mkdir -p "$OUT"; cd "$C"; ulimit -n 100000
exec > >(tee -a "$OUT/cmdlog.txt") 2>&1
ts() { date +%s%3N; }
daemons() { ps -eo pid,comm,args | awk '$2=="java" && /CassandraDaemon/' | wc -l; }
echo "== $label knob=$knob n=$n alloc=$alloc shards=$shards memtable=$mt start $(ts)"; echo "daemons before: $(daemons)"
rm -rf "$T"; "$HARN/make-node.sh" "$alloc"
EXTRA="-XX:MaxDirectMemorySize=10g -XX:NativeMemoryTracking=summary"
[ "$shards" = 1 ] && EXTRA="$EXTRA -Dcassandra.memtable.shard.count=1"
[ "$knob" != default ] && EXTRA="$EXTRA -Dcassandra.memtable.row_overhead_size=$knob"
echo "JVM_EXTRA_OPTS=$EXTRA MAX_HEAP_SIZE=16G"; echo "$EXTRA" > "$OUT/jvm-extra.txt"
CASSANDRA_CONF=$T/conf CASSANDRA_LOG_DIR=$T/logs MAX_HEAP_SIZE=16G HEAP_NEWSIZE=2G JVM_EXTRA_OPTS="$EXTRA" bin/cassandra -p $T/cassandra.pid > $T/stdout.txt 2>&1
for i in $(seq 1 120); do
  s=$(bin/nodetool statusbinary 2>/dev/null | tr -d '\n'); [ "$s" = running ] && break
  pgrep -F $T/cassandra.pid >/dev/null 2>&1 || { echo "daemon died at start"; tail -30 $T/stdout.txt; cp $T/logs/system.log "$OUT/system.log" 2>/dev/null; exit 1; }; sleep 3
done
echo "node up $(ts): $(bin/nodetool statusbinary)"
PID=$(cat $T/cassandra.pid); echo "pid $PID"
jcmd $PID VM.flags | tr ' ' '\n' | grep -E "MaxHeapSize|MaxDirectMemorySize" | tee "$OUT/vmflags.txt"
tr '\0' '\n' < /proc/$PID/cmdline | grep -E "row_overhead|shard.count|Xmx" | tee "$OUT/proc-args.txt"
bin/cqlsh 127.0.0.1 -e "CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1} AND durable_writes = false; CREATE TABLE IF NOT EXISTS ks.t (k blob PRIMARY KEY, v blob) WITH memtable = '$mt'; DESCRIBE TABLE ks.t" > "$OUT/schema.txt" 2>&1; tail -14 "$OUT/schema.txt"
if ! grep -q "memtable = '$mt'" "$OUT/schema.txt"; then
  echo "TABLE NOT CREATED with memtable=$mt"
  bin/cqlsh 127.0.0.1 -e "CREATE TABLE IF NOT EXISTS ks.t (k blob PRIMARY KEY, v blob) WITH memtable = '$mt'" > "$OUT/schema-retry.txt" 2>&1; tail -5 "$OUT/schema-retry.txt"
  bin/cqlsh 127.0.0.1 -e "DESCRIBE KEYSPACE ks" > "$OUT/describe-ks.txt" 2>&1; head -12 "$OUT/describe-ks.txt"
  [ "$knob" = 2048 ] && NOTABLE=1
fi
rm -f "$OUT/stop"; javac -d "$HARN/cls" "$HARN/Jmx.java" 2>/dev/null || { mkdir -p "$HARN/cls" && javac -d "$HARN/cls" "$HARN/Jmx.java"; }
java -cp "$HARN/cls" Jmx 7199 poll 100 1000000 "$OUT/stop" java.nio:type=BufferPool,name=direct MemoryUsed java.lang:type=Memory HeapMemoryUsage org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=t,name=MemtableOffHeapSize Value org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=t,name=MemtableOnHeapSize Value > "$OUT/samples.csv" 2>"$OUT/sampler.err" &
SP=$!
sleep 3
echo "workload start $(ts)"
if [ -z "${NOTABLE:-}" ]; then
  tools/bin/cassandra-stress user profile="$HARN/trie.yaml" "ops(insert=1)" n=$n no-warmup -pop seq=1..$n -rate threads=$thr -mode native cql3 -node 127.0.0.1 > "$OUT/stress.txt" 2>&1
  echo "workload end $(ts) rc=$?"
else
  echo "no table: the workload is skipped (the table could not be created)"
fi
sleep 5
bin/nodetool tablestats ks.t > "$OUT/tablestats.txt" 2>&1
touch "$OUT/stop"; sleep 2; wait $SP
cp $T/logs/system.log "$OUT/system.log" 2>/dev/null
bin/nodetool drain > "$OUT/drain.txt" 2>&1; bin/nodetool stopdaemon > /dev/null 2>&1
for i in $(seq 1 60); do pgrep -F $T/cassandra.pid >/dev/null 2>&1 || break; sleep 2; done
sleep 3; cp $T/logs/system.log "$OUT/system.log"; du -sh $T/data > "$OUT/du-data.txt"
echo "daemons left: $(daemons)"
rm -rf "$T"; echo "== $label end $(ts)"
