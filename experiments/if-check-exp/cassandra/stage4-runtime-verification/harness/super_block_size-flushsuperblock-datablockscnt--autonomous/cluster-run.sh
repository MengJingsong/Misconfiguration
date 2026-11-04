#!/usr/bin/env bash
# usage: cluster-run.sh <arm> <option MiB> <constant 16|64|256> <SPARSE|PREFIX> [rows=5000000]     (B3e, as amended 2026-10-28, C1-C3)
# One arm end to end on a fresh node: -Xmx2G, memtable_heap_space/offheap 256MiB, unthrottled compaction, -Xlog:gc to $T/logs/gc.log and
# -Xlog:class+load to $T/logs/classload.log. For constant 16 or 256 the overlay classes (ov16, ov256: make-overlays.sh of the unit
# harness, constant only) are copied into the node's conf directory (first on the class path); 64 uses the build's own classes.
# Table ks.t (id int PK, v int) with a SASI index on v (mode, max_compaction_flush_memory_in_mb = option), rows by cassandra-stress,
# flush, then nodetool compact: that window is measured (heap sampler 500 ms, gc.log, "Flushed index segment" lines, SI file sizes).
set -uo pipefail
arm=$1; opt=$2; const=$3; imode=$4; rows=${5:-5000000}
HARN=$(cd "$(dirname "$0")" && pwd); . "$HARN/lib.sh"
JCLS=$HOME/s4-b34/cls-sb; mkdir -p "$JCLS"; [ -f "$JCLS/Jmx.class" ] || javac -d "$JCLS" "$HARN/Jmx.java"
OV=${OV:-$HOME/s4-b34/ov}
T=$HOME/s4-b34/node-sb; OUT=${OUT:-$HOME/stage4-logs/b34/superblock/run1/cluster}/$arm; mkdir -p "$OUT"; cd "$C"; ulimit -n 100000
exec > >(tee -a "$OUT/cmdlog.txt") 2>&1
echo "== $arm option=${opt}MiB constant=$const mode=$imode rows=$rows start $(ts)"; echo "daemons before: $(daemons)"
echo "free_kb $(df --output=avail / | tail -1)"
rm -rf "$T"; mkdir -p "$T"
{ base_yaml "$T"; echo "memtable_heap_space: 256MiB"; echo "memtable_offheap_space: 256MiB"; } > "$T/lines.yaml"
mk_conf "$T" "$T/lines.yaml"
if [ "$const" != 64 ]; then cp -r "$OV/ov$const/org" "$T/conf/"; echo "overlay ov$const copied into $T/conf"; fi
XOPT="-XX:NativeMemoryTracking=summary -Xlog:class+load=info:file=$T/logs/classload.log:none"
echo "$XOPT" > "$OUT/jvm-extra.txt"
start_node "$T" 2G 512M "$XOPT" || { cp "$T/logs/system.log" "$OUT/system.log" 2>/dev/null; exit 1; }
PID=$(cat "$T/cassandra.pid"); echo "node up $(ts) pid $PID"
tr '\0' '\n' < /proc/$PID/cmdline | grep -E "Xmx|Xlog" | tee "$OUT/proc-args.txt"
grep -E "^(sasi_indexes_enabled|memtable_heap_space|memtable_offheap_space|compaction_throughput)" "$T/conf/cassandra.yaml" | tee "$OUT/yaml-lines.txt"
bin/cqlsh 127.0.0.1 -e "CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE IF NOT EXISTS ks.t (id int PRIMARY KEY, v int); CREATE CUSTOM INDEX IF NOT EXISTS t_v ON ks.t (v) USING 'org.apache.cassandra.index.sasi.SASIIndex' WITH OPTIONS = {'mode': '$imode', 'max_compaction_flush_memory_in_mb': '$opt'}; DESCRIBE TABLE ks.t" > "$OUT/schema.txt" 2>&1; tail -8 "$OUT/schema.txt"
rm -f "$OUT/stop"
java -cp "$JCLS" Jmx 7199 poll 200 10000000 "$OUT/stop" java.lang:type=Memory HeapMemoryUsage > "$OUT/heap.csv" 2>"$OUT/sampler.err" &
SP=$!
disk_sampler "$T" "$OUT/stop" "$OUT/disk.csv" &
DP=$!
sleep 2
echo "load start $(ts)"
tools/bin/cassandra-stress user profile="$HARN/sasi.yaml" "ops(insert=1)" n=$rows no-warmup -pop seq=1..$rows -rate threads=48 -mode native cql3 -node 127.0.0.1 > "$OUT/stress.txt" 2>&1
echo "load end $(ts) rc=$?"; grep -E "Total errors|Op rate" "$OUT/stress.txt" | head -3
bin/nodetool flush ks t; echo "flush done $(ts)"
sleep 5; bin/nodetool tablestats ks.t > "$OUT/tablestats-before-compact.txt" 2>&1; grep "SSTable count" "$OUT/tablestats-before-compact.txt"
D=$(ls -d "$T"/data/ks/t-*/ | head -1); ls -l "$D" > "$OUT/ls-before-compact.txt"
echo "COMPACT_START $(ts)" > "$OUT/windows.txt"
bin/nodetool compact ks t > "$OUT/compact.txt" 2>&1; echo "compact rc=$?"
wait_one_sstable ks.t 1800 && echo "one sstable" || echo "NOT one sstable"
echo "COMPACT_END $(ts)" >> "$OUT/windows.txt"; sleep 5
bin/nodetool tablestats ks.t > "$OUT/tablestats.txt" 2>&1
ls -l "$D" > "$OUT/ls-sstable-dir.txt"
for pat in '*-Data.db' '*-Index.db' '*SI_*.db'; do printf '%s ' "$pat"; cat $D$pat 2>/dev/null | wc -c; done | tee "$OUT/sizes.txt"
grep -E "OnDiskIndexBuilder|OnDiskIndex " "$T/logs/classload.log" | cut -c1-300 > "$OUT/classload-ondiskindex.txt"; cat "$OUT/classload-ondiskindex.txt" | head -4
grep -E "AssertionError|^ERROR|OutOfMemory" "$T/logs/system.log" | grep -v "JVM Arguments" | head -20 > "$OUT/log-errors.txt"; echo "log error lines: $(wc -l < "$OUT/log-errors.txt")"
touch "$OUT/stop"; sleep 3; wait $SP $DP 2>/dev/null
cp "$T/logs/system.log" "$OUT/system.log"; cp "$T/logs/gc.log" "$OUT/gc.log" 2>/dev/null
stop_node "$T"
sleep 2; cp "$T/logs/system.log" "$OUT/system.log"
rm -rf "$T"; echo "== $arm end $(ts)"
