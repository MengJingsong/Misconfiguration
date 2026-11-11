#!/usr/bin/env bash
# usage: cluster-run.sh <arm> <rows> <index yes|no> <heap e.g. 2G> <format big|bti> <commitlog MiB> [threads=48]    (B3e, as amended 2026-10-28, C1-C5)
# One arm end to end: fresh data dir under $T, one node (-Xmx heap, -Xlog:gc to $T/logs/gc.log), table ks.t (id bigint PK, v text, payload blob),
# SASI index on v when asked, a 500 ms JMX heap sampler and a 2 s disk sampler, cassandra-stress for <rows> inserts, nodetool flush,
# nodetool compact until one sstable, then the readings (file sizes, tablestats, log greps), stop, delete the node dir.
# Output: $OUT/<arm>/ . EXPECTED lines compare to B3f/C5. A size whose free-space guard fails is not run (C2).
set -uo pipefail
arm=$1; rows=$2; idx=$3; heap=$4; fmt=$5; clmb=$6; thr=${7:-48}
HARN=$(cd "$(dirname "$0")" && pwd); . "$HARN/lib.sh"
JCLS=$HOME/s4-b34/cls-mo; mkdir -p "$JCLS"; [ -f "$JCLS/Jmx.class" ] || javac -d "$JCLS" "$HARN/Jmx.java"
T=$HOME/s4-b34/node-mo; OUT=${OUT:-$HOME/stage4-logs/b34/maxoffset/run1/cluster}/$arm; mkdir -p "$OUT"; cd "$C"; ulimit -n 100000
exec > >(tee -a "$OUT/cmdlog.txt") 2>&1
echo "== $arm rows=$rows index=$idx heap=$heap format=$fmt commitlog=${clmb}MiB threads=$thr start $(ts)"
payload_gb=$(( rows * 1000 / 1000000000 + 1 ))
need_kb=$(( rows * 1000 * 22 / 10 / 1024 + 8000000 )); free_kb=$(df --output=avail / | tail -1 | tr -d ' ')
echo "guard: free ${free_kb} KB, need ${need_kb} KB (2.2 x payload + 8 GB)"
if [ "$free_kb" -lt "$need_kb" ]; then echo "GUARD FAILED: arm $arm not run (runbook defect C2)"; echo "EXPECTED arm_ran: yes  got no  FAIL"; exit 3; fi
echo "daemons before: $(daemons)"
rm -rf "$T"; mkdir -p "$T"
{ base_yaml "$T"; echo "commitlog_total_space: ${clmb}MiB"; [ "$fmt" = bti ] && printf 'storage_compatibility_mode: NONE\nsstable:\n  selected_format: bti\n'; } > "$T/lines.yaml"
mk_conf "$T" "$T/lines.yaml"
XOPT="-XX:NativeMemoryTracking=summary"
echo "$XOPT heap=$heap" > "$OUT/jvm-extra.txt"
start_node "$T" "$heap" 1G "$XOPT" || { cp "$T/logs/system.log" "$OUT/system.log" 2>/dev/null; exit 1; }
PID=$(cat "$T/cassandra.pid"); echo "node up $(ts) pid $PID"
tr '\0' '\n' < /proc/$PID/cmdline | grep -E "Xmx|selected_format|storagedir" | tee "$OUT/proc-args.txt"
grep -E "^(sasi_indexes_enabled|commitlog_total_space|compaction_throughput|storage_compatibility_mode)|selected_format" "$T/conf/cassandra.yaml" | tee "$OUT/yaml-lines.txt"
S1=" CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1};"
S2=" CREATE TABLE IF NOT EXISTS ks.t (id bigint PRIMARY KEY, v text, payload blob);"
S3=""; [ "$idx" = yes ] && S3=" CREATE CUSTOM INDEX IF NOT EXISTS t_v ON ks.t (v) USING 'org.apache.cassandra.index.sasi.SASIIndex';"
bin/cqlsh 127.0.0.1 -e "$S1 $S2 $S3 DESCRIBE TABLE ks.t" > "$OUT/schema.txt" 2>&1; tail -12 "$OUT/schema.txt"
rm -f "$OUT/stop"
java -cp "$JCLS" Jmx 7199 poll 500 10000000 "$OUT/stop" java.lang:type=Memory HeapMemoryUsage > "$OUT/heap.csv" 2>"$OUT/sampler.err" &
SP=$!
disk_sampler "$T" "$OUT/stop" "$OUT/disk.csv" &
DP=$!
sleep 2
echo "load start $(ts) free_kb=$(df --output=avail / | tail -1)"
tools/bin/cassandra-stress user profile="$HARN/sasi.yaml" "ops(insert=1)" n=$rows no-warmup -pop seq=1..$rows -rate threads=$thr -mode native cql3 -node 127.0.0.1 > "$OUT/stress.txt" 2>&1
echo "load end $(ts) rc=$?"; grep -E "Total errors|Op rate|Partition rate" "$OUT/stress.txt" | head -5
bin/nodetool flush ks t; echo "flush done $(ts)"
sleep 3; bin/nodetool tablestats ks.t > "$OUT/tablestats-before-compact.txt" 2>&1
echo "compact start $(ts)"; echo "COMPACT_START $(ts)" > "$OUT/windows.txt"
bin/nodetool compact ks t > "$OUT/compact.txt" 2>&1; echo "compact rc=$? end $(ts)"
wait_one_sstable ks.t 1800 && echo "one sstable" || echo "NOT one sstable"
echo "COMPACT_END $(ts)" >> "$OUT/windows.txt"
sleep 5
bin/nodetool tablestats ks.t > "$OUT/tablestats.txt" 2>&1
D=$(ls -d "$T"/data/ks/t-*/ | head -1); ls -l "$D" > "$OUT/ls-sstable-dir.txt"
echo "sizes (bytes):"; for pat in '*-Data.db' '*-Index.db' '*SI_*.db'; do printf '%s ' "$pat"; cat $D$pat 2>/dev/null | wc -c; done | tee "$OUT/sizes.txt"
echo "data_dir_bytes $(bytes "$T/data")" | tee -a "$OUT/sizes.txt"
grep -E "AssertionError|cannot be greater|^ERROR|OutOfMemory" "$T/logs/system.log" | grep -v "JVM Arguments" | head -20 > "$OUT/log-errors.txt"; echo "log error lines: $(wc -l < "$OUT/log-errors.txt")"
touch "$OUT/stop"; sleep 3; wait $SP $DP 2>/dev/null
cp "$T/logs/system.log" "$OUT/system.log"; cp "$T/logs/gc.log" "$OUT/gc.log" 2>/dev/null
stop_node "$T"
sleep 3; cp "$T/logs/system.log" "$OUT/system.log"
rm -rf "$T"; echo "== $arm end $(ts)"
