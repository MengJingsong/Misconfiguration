#!/usr/bin/env bash
# usage: cluster-run.sh <label> <N|unset> <wide_cdc|wide_plain> [heapB=2G]      (case B3e steps 4-6, as amended 2026-10-27)
# One arm: A restored from $R/A-backup (the data, loaded by prep-data.sh), B new and empty; B (127.0.0.3) is the receiver and runs with
# -Dcassandra.repair.mutation_repair_rows_per_batch=<N>, the Byteman rules bm.btm, a GC log and NMT summary; node A (127.0.0.2) is the
# sender and runs without the property. Then "nodetool -p 7103 repair -full ks <table>" on B while a sampler takes a collecting class
# histogram of B every 4 s (live bytes in total and of the update-related classes) and the heap used. Output: $OUT/<label>/.
set -uo pipefail
label=$1; N=$2; table=$3; heap=${4:-2G}
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/c4-mrb}; R=${R:-$HOME/stage4-mrb}; OUT=${OUT:-$HOME/stage4-logs/mrb/run1/cluster}/$label
mkdir -p "$OUT"; cd "$C"; exec > >(tee -a "$OUT/cmdlog.txt") 2>&1
ts() { date +%s%3N; }
echo "== $label N=$N table=$table heapB=$heap start $(ts)"
"$H/node.sh" stop B; "$H/node.sh" stop A; echo "daemons before: $("$H/node.sh" status)"
rm -rf "$R/A" "$R/B"; "$H/make-node.sh" A | tail -1; "$H/make-node.sh" B | tail -1
cp -a "$R/A-backup/." "$R/A/data/" || exit 1
"$H/node.sh" start A || exit 1
BM=$C/build/lib/jars/byteman-4.0.20.jar
EXTRA="-javaagent:$BM=script:$H/bm.btm -Xlog:gc*:file=$OUT/gc-B.log:time,uptime -XX:NativeMemoryTracking=summary"
[ "$N" != unset ] && EXTRA="$EXTRA -Dcassandra.repair.mutation_repair_rows_per_batch=$N"
echo "B JVM_EXTRA_OPTS=$EXTRA heap=$heap"; echo "$EXTRA" > "$OUT/jvm-extra-B.txt"
HEAP=$heap "$H/node.sh" start B $EXTRA || { cp $R/B/logs/system.log "$OUT/system-B.log" 2>/dev/null; "$H/node.sh" stop A; exit 1; }
PIDB=$(cat $R/B/cassandra.pid); PIDA=$(cat $R/A/cassandra.pid); echo "pidA=$PIDA pidB=$PIDB"
tr '\0' '\n' < /proc/$PIDB/cmdline | grep -E "mutation_repair|Xmx|javaagent" | tee "$OUT/proc-args-B.txt"
tr '\0' '\n' < /proc/$PIDA/cmdline | grep -cE "mutation_repair" | sed 's/^/A has the property (lines): /'
bin/nodetool -p 7102 status | tee "$OUT/status-before.txt"
bin/nodetool -p 7103 tablestats ks.$table 2>&1 | grep -E "SSTable count|Space used \(live\)|Number of partitions" | sed 's/^/B before: /' | tee "$OUT/tablestats-B-before.txt"
# sampler
rm -f "$OUT/stop"
( while [ ! -f "$OUT/stop" ]; do
    t=$(ts); tot=$(jcmd $PIDB GC.class_histogram 2>/dev/null | tee "$OUT/hist-last.txt" | awk '/^Total/{print $3}')
    cell=$(grep -E "BufferCell|ArrayClustering|BTreeRow| \[B$" "$OUT/hist-last.txt" | awk '{printf "%s=%s ", $4, $3}')
    hu=$(jcmd $PIDB GC.heap_info 2>/dev/null | grep -m1 -oE "used [0-9]+K" | tr -dc 0-9)
    echo "$t total_live_bytes=$tot heap_used_K=$hu $cell"; sleep 4
  done > "$OUT/samples.txt" ) &
SP=$!
echo "repair start $(ts)"
timeout 3000 bin/nodetool -p 7103 repair -full ks $table > "$OUT/repair.txt" 2>&1; echo "repair rc=$? end $(ts)"
sleep 20
touch "$OUT/stop"; wait $SP
tail -5 "$OUT/repair.txt"
bin/nodetool -p 7103 tablestats ks.$table 2>&1 | grep -E "SSTable count|Space used \(live\)|Number of partitions|Memtable" | tee "$OUT/tablestats-B-after.txt"
bin/cqlsh --request-timeout=900 127.0.0.3 -e "CONSISTENCY LOCAL_ONE; SELECT count(*) FROM ks.$table WHERE pk = 1" > "$OUT/count-B.txt" 2>&1; tail -n 6 "$OUT/count-B.txt"
cp $R/B/logs/system.log "$OUT/system-B.log"; cp $R/B/logs/debug.log "$OUT/debug-B.log" 2>/dev/null; cp $R/B/stdout.txt "$OUT/stdout-B.txt"
grep -c S4BATCH "$OUT/stdout-B.txt" | sed 's/^/S4BATCH lines: /'; grep S4THROTTLE "$OUT/stdout-B.txt" | head -3
"$H/node.sh" stop B; "$H/node.sh" stop A
echo "daemons left: $("$H/node.sh" status)"
du -sh $R/B/data $R/B/cdc_raw $R/B/commitlog 2>/dev/null | tee "$OUT/du-B.txt"
rm -rf "$R/A" "$R/B"; echo "== $label end $(ts)"
