#!/usr/bin/env bash
# usage: cluster-run.sh <label> <knob-MB|default> <offheap_space_MiB> <n_keys> [threads=16]       (case B3e steps 1-7)
# One arm: fresh data dir, start one node (MAX_HEAP_SIZE 16G, MaxDirectMemorySize 10g, NMT, shard.count=1, knob), create the
# schema through cassandra-stress, sample JMX at 1 Hz, run the workload, drain, stop, verify no CassandraDaemon, delete data.
# Output: $OUT/<label>/.
set -uo pipefail
label=$1; knob=$2; off=$3; n=$4; thr=${5:-16}
HARN=$(cd "$(dirname "$0")" && pwd)
C=${CASSANDRA_HOME:-$HOME/cassandra-run1}; T=$HOME/stage4-trie2gb/node; OUT=${OUT:-$HOME/stage4-logs/trie2gb/run1/cluster}/$label
mkdir -p "$OUT"; cd "$C"
exec > >(tee -a "$OUT/cmdlog.txt") 2>&1
ts() { date +%s%3N; }
echo "== $label knob=$knob offheap=${off}MiB n=$n threads=$thr start $(ts)"
rm -rf "$T"; "$HARN/make-node.sh" "$off"
EXTRA="-Dcassandra.memtable.shard.count=1 -XX:MaxDirectMemorySize=10g -XX:NativeMemoryTracking=summary"
[ "$knob" != default ] && EXTRA="$EXTRA -Dcassandra.memtable.row_overhead_size=$knob"
echo "JVM_EXTRA_OPTS=$EXTRA MAX_HEAP_SIZE=16G"
CASSANDRA_CONF=$T/conf CASSANDRA_LOG_DIR=$T/logs MAX_HEAP_SIZE=16G HEAP_NEWSIZE=2G JVM_EXTRA_OPTS="$EXTRA" bin/cassandra -p $T/cassandra.pid > $T/stdout.txt 2>&1
for i in $(seq 1 120); do
  s=$(bin/nodetool statusbinary 2>/dev/null | tr -d '\n'); [ "$s" = running ] && break
  pgrep -F $T/cassandra.pid >/dev/null 2>&1 || { echo "daemon died at start"; tail -30 $T/stdout.txt; exit 1; }; sleep 3
done
echo "node up $(ts): $(bin/nodetool statusbinary)"
PID=$(cat $T/cassandra.pid); echo "pid $PID"; echo "$EXTRA" > "$OUT/jvm-extra.txt"
jcmd $PID VM.flags | tr ' ' '\n' | grep -E "MaxHeapSize|MaxDirectMemorySize|NativeMemoryTracking" | tee "$OUT/vmflags.txt"
# schema + sampler
bin/cqlsh 127.0.0.1 -e "CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1} AND durable_writes = false; CREATE TABLE IF NOT EXISTS ks.t (k blob PRIMARY KEY, v blob) WITH memtable = 'trie'; DESCRIBE TABLE ks.t" > "$OUT/schema.txt" 2>&1; tail -12 "$OUT/schema.txt"
rm -f "$OUT/stop"; javac -d "$HARN/cls" "$HARN/Jmx.java" 2>/dev/null || mkdir -p "$HARN/cls" && javac -d "$HARN/cls" "$HARN/Jmx.java"
java -cp "$HARN/cls" Jmx 7199 poll 1000 100000 "$OUT/stop" java.nio:type=BufferPool,name=direct MemoryUsed java.lang:type=Memory HeapMemoryUsage org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=t,name=MemtableOffHeapSize Value > "$OUT/samples.csv" 2>"$OUT/sampler.err" &
SP=$!
sleep 3; jcmd $PID VM.native_memory summary > "$OUT/nmt-before.txt"
echo "workload start $(ts)"
tools/bin/cassandra-stress user profile="$HARN/trie.yaml" "ops(insert=1)" n=$n no-warmup -pop seq=1..$n -rate threads=$thr -mode native cql3 -node 127.0.0.1 > "$OUT/stress.txt" 2>&1
echo "workload end $(ts) rc=$?"
jcmd $PID VM.native_memory summary > "$OUT/nmt-after-write.txt"
sleep 20; jcmd $PID VM.native_memory summary > "$OUT/nmt-after-settle.txt"
bin/nodetool tablestats ks.t > "$OUT/tablestats.txt" 2>&1
touch "$OUT/stop"; sleep 2; wait $SP
cp $T/logs/system.log "$OUT/system.log" 2>/dev/null
bin/nodetool drain > "$OUT/drain.txt" 2>&1; bin/nodetool stopdaemon > /dev/null 2>&1
for i in $(seq 1 60); do pgrep -F $T/cassandra.pid >/dev/null 2>&1 || break; sleep 2; done
sleep 2; cp $T/logs/system.log "$OUT/system.log"; du -sh $T/data > "$OUT/du-data.txt"
ps -eo cmd | grep '[C]assandraDaemon' | wc -l | sed 's/^/CassandraDaemon processes left: /'
rm -rf "$T"; echo "== $label end $(ts)"
