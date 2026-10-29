#!/usr/bin/env bash
# usage: cluster-run.sh <arm> collide <tokens t> <keys per token g>
#        cluster-run.sh <arm> rows <rows>
#        cluster-run.sh <arm> mem <max_compaction_flush_memory_in_mb>        (B3e, as amended 2026-10-28, C1-C4)
# One arm end to end on a fresh node (-Xmx1G, commitlog_total_space 256MiB, unthrottled compaction, -Xlog:gc to $T/logs/gc.log).
#  collide: Byteman trace on createOverflowEntry (overflow.btm); t x g colliding 16-byte keys from CollKeys (all v = 'x') plus 100 other rows;
#           flush; look at the sstable directory, system.log, the Byteman lines, an index query, and the commit log for 2 minutes.
#  rows:    <rows> clean rows (sasi.yaml profile), flush, compact to one sstable, sizes of Data/Index/SI files.
#  mem:     SASI option max_compaction_flush_memory_in_mb=<n>; 4 x 250,000 rows with a flush after each; compact; segments and heap in the window.
set -uo pipefail
arm=$1; mode=$2; shift 2
HARN=$(cd "$(dirname "$0")" && pwd); . "$HARN/lib.sh"
JCLS=$HOME/s4-b34/cls-ov; mkdir -p "$JCLS"; [ -f "$JCLS/Jmx.class" ] || javac -d "$JCLS" "$HARN/Jmx.java"
CP="$C/build/classes/main:$C/build/lib/jars/*:$C/lib/*"
[ -f "$JCLS/CollKeys.class" ] || javac -nowarn -d "$JCLS" -cp "$CP" "$HARN/CollKeys.java"
T=$HOME/s4-b34/node-ov; OUT=${OUT:-$HOME/stage4-logs/b34/overflow/run1/cluster}/$arm; mkdir -p "$OUT"; cd "$C"; ulimit -n 100000
exec > >(tee -a "$OUT/cmdlog.txt") 2>&1
echo "== $arm mode=$mode args=$* start $(ts)"; echo "daemons before: $(daemons)"
rm -rf "$T"; mkdir -p "$T"
{ base_yaml "$T"; echo "commitlog_total_space: 256MiB"; } > "$T/lines.yaml"
mk_conf "$T" "$T/lines.yaml"
XOPT="-XX:NativeMemoryTracking=summary"
[ "$mode" = collide ] && { sed "s#@TRACEFILE@#$T/logs/byteman.txt#" "$HARN/overflow.btm" > "$T/overflow.btm"; XOPT="$XOPT -javaagent:$C/build/lib/jars/byteman-4.0.20.jar=script:$T/overflow.btm,listener:true"; }
echo "$XOPT" > "$OUT/jvm-extra.txt"
if [ "$mode" = collide ]; then
  java -cp "$JCLS:$CP" CollKeys $1 $2 ${EXTRA:-100} "$OUT/inserts.cql" | tee "$OUT/collkeys.txt" | tail -3
  echo "EXPECTED collkeys_mismatches: 0  got $(sed -n 's/.*mismatches=//p' "$OUT/collkeys.txt")"
fi
start_node "$T" 1G 256M "$XOPT" || { cp "$T/logs/system.log" "$OUT/system.log" 2>/dev/null; exit 1; }
PID=$(cat "$T/cassandra.pid"); echo "node up $(ts) pid $PID"
tr '\0' '\n' < /proc/$PID/cmdline | grep -E "Xmx|javaagent" | tee "$OUT/proc-args.txt"
grep -E "^(sasi_indexes_enabled|commitlog_total_space|compaction_throughput)" "$T/conf/cassandra.yaml" | tee "$OUT/yaml-lines.txt"
OPT=""; [ "$mode" = mem ] && OPT=" WITH OPTIONS = {'max_compaction_flush_memory_in_mb': '$1'}"
if [ "$mode" = collide ]; then PK=blob; else PK=blob; fi
bin/cqlsh 127.0.0.1 -e "CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE IF NOT EXISTS ks.t (pk blob PRIMARY KEY, v text); CREATE CUSTOM INDEX IF NOT EXISTS t_v ON ks.t (v) USING 'org.apache.cassandra.index.sasi.SASIIndex'$OPT; DESCRIBE TABLE ks.t" > "$OUT/schema.txt" 2>&1; tail -8 "$OUT/schema.txt"
rm -f "$OUT/stop"
java -cp "$JCLS" Jmx 7199 poll 500 10000000 "$OUT/stop" java.lang:type=Memory HeapMemoryUsage > "$OUT/heap.csv" 2>"$OUT/sampler.err" &
SP=$!
disk_sampler "$T" "$OUT/stop" "$OUT/disk.csv" &
DP=$!
sleep 2
D() { ls -d "$T"/data/ks/t-*/ 2>/dev/null | head -1; }
if [ "$mode" = collide ]; then
  bin/cqlsh 127.0.0.1 -f "$OUT/inserts.cql" > "$OUT/inserts.out" 2>&1; echo "inserts rc=$?"
  bin/cqlsh 127.0.0.1 -e "SELECT token(pk), pk FROM ks.t;" > "$OUT/token-select.txt" 2>&1
  python3 - "$OUT/token-select.txt" <<'PY' | tee "$OUT/token-groups.txt"
import collections, re, sys
c = collections.Counter()
for l in open(sys.argv[1]):
    m = re.match(r'\s*(-?\d+)\s*\|', l)
    if m: c[m.group(1)] += 1
print('TOKEN-GROUPS', ' '.join('%s:%d' % (k, v) for k, v in sorted(c.items(), key=lambda kv: -kv[1]) if v > 1), 'rows=%d' % sum(c.values()))
PY
  echo "flush start $(ts)"; bin/nodetool flush ks t; echo "flush rc=$? end $(ts)"
  sleep 10
  ls -l "$(D)" > "$OUT/ls-sstable-dir.txt"; cat "$OUT/ls-sstable-dir.txt" | awk '{print $5, $9}' | tail -n +2
  bin/cqlsh 127.0.0.1 -e "SELECT pk FROM ks.t WHERE v = 'x' LIMIT 3;" > "$OUT/index-query.txt" 2>&1; head -8 "$OUT/index-query.txt"
  echo "watching the commit log for 120 s after the flush"; for i in 1 2 3 4 5 6; do sleep 20; echo "commitlog bytes $(bytes "$T/commitlog") at +$((i*20)) s"; done
  bin/nodetool tablestats ks.t > "$OUT/tablestats.txt" 2>&1
  cp "$T/logs/byteman.txt" "$OUT/byteman.txt" 2>/dev/null || : > "$OUT/byteman.txt"; echo "byteman lines: $(wc -l < "$OUT/byteman.txt") entries, throws: $(grep -c BM-OVF-THROW "$OUT/byteman.txt")"; tail -12 "$OUT/byteman.txt"
fi
if [ "$mode" = rows ]; then
  n=$1
  tools/bin/cassandra-stress user profile="$HARN/sasi.yaml" "ops(insert=1)" n=$n no-warmup -pop seq=1..$n -rate threads=32 -mode native cql3 -node 127.0.0.1 > "$OUT/stress.txt" 2>&1
  echo "load rc=$?"; grep -E "Total errors" "$OUT/stress.txt" | head -2
  bin/nodetool flush ks t; echo "COMPACT_START $(ts)" > "$OUT/windows.txt"; bin/nodetool compact ks t; wait_one_sstable ks.t 600; echo "COMPACT_END $(ts)" >> "$OUT/windows.txt"; sleep 3
  bin/nodetool tablestats ks.t > "$OUT/tablestats.txt" 2>&1
  ls -l "$(D)" > "$OUT/ls-sstable-dir.txt"
  for pat in '*-Data.db' '*-Index.db' '*SI_*.db'; do printf '%s ' "$pat"; cat $(D)$pat 2>/dev/null | wc -c; done | tee "$OUT/sizes.txt"
fi
if [ "$mode" = mem ]; then
  for k in 0 1 2 3; do
    a=$((k*250000+1)); b=$((k*250000+250000))
    tools/bin/cassandra-stress user profile="$HARN/sasi.yaml" "ops(insert=1)" n=250000 no-warmup -pop seq=$a..$b -rate threads=32 -mode native cql3 -node 127.0.0.1 > "$OUT/stress-$k.txt" 2>&1
    echo "load $k rc=$? $(grep -E 'Total errors' "$OUT/stress-$k.txt" | head -1)"; bin/nodetool flush ks t
  done
  sleep 5; bin/nodetool tablestats ks.t > "$OUT/tablestats-before-compact.txt" 2>&1; grep "SSTable count" "$OUT/tablestats-before-compact.txt"
  echo "COMPACT_START $(ts)" > "$OUT/windows.txt"; bin/nodetool compact ks t; wait_one_sstable ks.t 1200; echo "COMPACT_END $(ts)" >> "$OUT/windows.txt"; sleep 3
  bin/nodetool tablestats ks.t > "$OUT/tablestats.txt" 2>&1
  ls -l "$(D)" > "$OUT/ls-sstable-dir.txt"
  for pat in '*-Data.db' '*-Index.db' '*SI_*.db'; do printf '%s ' "$pat"; cat $(D)$pat 2>/dev/null | wc -c; done | tee "$OUT/sizes.txt"
fi
grep -E "AssertionError|cannot have more|^ERROR|OutOfMemory" "$T/logs/system.log" | grep -v "JVM Arguments" | head -20 > "$OUT/log-errors.txt"; echo "log error lines: $(wc -l < "$OUT/log-errors.txt")"; head -6 "$OUT/log-errors.txt" | cut -c1-220
touch "$OUT/stop"; sleep 3; wait $SP $DP 2>/dev/null
cp "$T/stdout.txt" "$OUT/stdout.txt"; cp "$T/logs/gc.log" "$OUT/gc.log" 2>/dev/null
stop_node "$T"
sleep 2; cp "$T/logs/system.log" "$OUT/system.log"
rm -rf "$T"; echo "== $arm end $(ts)"
