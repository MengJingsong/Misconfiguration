#!/usr/bin/env bash
# Stage-4 harness: memtable_heap_space-LeafBuilder-allocated--autonomous, unit tier (B2 as amended U1-U5, 2026-10-27).
# usage: unit-run.sh instrument|shake|shake1|v0|v1
#   instrument  copy the test files into both clones, build-test both, type-check the Byteman rules (TestScript)
#   shake       V0 clone, 200 partitions, all 12 combinations (harness shakedown, not judged)
#   shake1      V1 clone, 200 partitions, rows 256 (harness shakedown, not judged)
#   v0          V0 clone ($W/cassandra-run61), 5,000 partitions, classes x rows {4,256} x modes {single,batch}
#   v1          V1 clone ($W/cassandra-run61v1, lines 2683/2736 -> allocated += 0), 5,000 partitions, rows 256 x modes x classes
# Heap: _JAVA_OPTIONS=-Xmx4g (build.xml:1153 appends -Xmx1024m after -Dtest.jvm.args, so a -Xmx there does not win; U1).
# Output: $W/logs/memtable_heap_space-LeafBuilder-allocated--autonomous/unit-<mode>/ (commands.log, summary.txt, stage4.out, ant log)
# Re-run (amendment of 2026-10-27 after run 1, authorised by the user): env C0/C1 select the clones (default run 1's), LBASE the log
# folder (<LBASE>/<mode>), ROWOVH pins -Dcassandra.memtable.row_overhead_size in every JVM (unset = run 1's behaviour).
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
H=$(cd "$(dirname "$0")" && pwd); C0=${C0:-$W/cassandra-run61}; C1=${C1:-$W/cassandra-run61v1}; ROWOVH=${ROWOVH:-}
what=${1:?instrument|shake|v0|v1}
if [ -n "${LBASE:-}" ]; then L=$LBASE/$what; else L=$W/logs/memtable_heap_space-LeafBuilder-allocated--autonomous/unit-$what; fi
rm -rf "$L"; mkdir -p "$L"; S=$L/summary.txt; CL=$L/commands.log; : > "$S"; : > "$CL"
say() { echo "$*" | tee -a "$S" >> "$CL"; }
cmd() { echo "+ $*" >> "$CL"; "$@" >> "$CL" 2>&1; local rc=$?; echo "  exit=$rc" >> "$CL"; return $rc; }
T=test/unit/org/apache/cassandra/db/memtable
P=org.apache.cassandra.db.memtable.WideMemtableSizeTest
say "unit-run $what $(date '+%Y-%m-%dT%H:%M:%S%z') test md5 $(md5 -q "$H/WideMemtableSizeTest.java" | cut -c1-12) counters md5 $(md5 -q "$H/WideLeafCounters.java" | cut -c1-12) btm md5 $(md5 -q "$H/unit-counters.btm" | cut -c1-12) C0=$C0 C1=$C1 ROWOVH=${ROWOVH:-unset}"
for c in $C0 $C1; do
  cmd cp "$H/WideMemtableSizeTest.java" "$H/WideLeafCounters.java" "$c/$T/"
  say "clone $c $(git -C $c describe --tags) $(git -C $c rev-parse --short HEAD) BTree:2683 [$(sed -n 2683p $c/src/java/org/apache/cassandra/utils/btree/BTree.java | sed 's/^ *//')] BTree:2736 [$(sed -n 2736p $c/src/java/org/apache/cassandra/utils/btree/BTree.java | sed 's/^ *//')]"
done
run() {   # run <clone> <variant> <extra test props>
  local c=$1 v=$2 props=$3
  local log="$L/WideMemtableSizeTest-$v.ant.log"
  find "$c/build/test/logs" -name "TEST-$P.log" -delete 2>/dev/null   # the test log appends across runs
  local args="-javaagent:$c/build/lib/jars/byteman-4.0.20.jar=script:$H/unit-counters.btm -Dstage4.out=$L/stage4.out -Dstage4.variant=$v $props${ROWOVH:+ -Dcassandra.memtable.row_overhead_size=$ROWOVH}"
  echo "+ (cd $c && _JAVA_OPTIONS=-Xmx4g ant -Dlocal.repository=$W/m2 testsome -Dtest.name=$P -Dtest.timeout=7200000 -Dtest.jvm.args=\"$args\") > $log" >> "$CL"
  (cd "$c" && _JAVA_OPTIONS=-Xmx4g ant -Dlocal.repository=$W/m2 testsome -Dtest.name=$P -Dtest.timeout=7200000 -Dtest.jvm.args="$args" > "$log" 2>&1 < /dev/null)
  local rc=$?
  cp "$c"/build/test/output/TEST-$P*.xml "$L/" 2>/dev/null || true
  find "$c/build/test/logs" -name "TEST-$P.log" -exec cp {} "$L/TEST-$P-$v.log" \; 2>/dev/null || true
  say "$P $v exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$log") $(grep -m1 -o 'Total time: .*' "$log") picked-up: $(grep -c 'Picked up _JAVA_OPTIONS: -Xmx4g' "$log")"
}
case $what in
  instrument)
    for c in $C0 $C1; do
      (cd "$c" && cmd ant -Dlocal.repository=$W/m2 build-test) && say "build-test $c: BUILD SUCCESSFUL" || say "build-test $c FAILED"
      CP="$c/build/classes/main:$c/build/test/classes:$(ls $c/build/lib/jars/*.jar | tr '\n' ':')"
      echo "+ java -cp byteman:classes org.jboss.byteman.check.TestScript $H/unit-counters.btm ($c)" >> "$CL"
      java -cp "$CP" org.jboss.byteman.check.TestScript "$H/unit-counters.btm" > "$L/testscript-unit-$(basename $c).txt" 2>&1
      say "TestScript unit-counters.btm on $(basename $c): exit=$? $(grep -E 'TestScript: no errors|ERROR|WARNING|type checked' "$L/testscript-unit-$(basename $c).txt" | tr '\n' ' ' | cut -c1-300)"
      java -cp "$CP" org.jboss.byteman.check.TestScript "$H/node-counters.btm" > "$L/testscript-node-$(basename $c).txt" 2>&1
      say "TestScript node-counters.btm on $(basename $c): exit=$? $(grep -E 'TestScript: no errors|ERROR|WARNING|type checked' "$L/testscript-node-$(basename $c).txt" | tr '\n' ' ' | cut -c1-300)"
    done ;;
  shake) run $C0 V0 "-Dstage4.partitions=200" ;;
  shake1) run $C1 V1 "-Dstage4.partitions=200 -Dstage4.rows=256" ;;
  v0)    run $C0 V0 "" ;;
  v1)    run $C1 V1 "-Dstage4.rows=256" ;;
esac
if [ "$what" != instrument ]; then
  say "STAGE4 readings: $(grep -c '^STAGE4 reading' "$L/stage4.out" 2>/dev/null)"
  cat "$L/stage4.out" >> "$S" 2>/dev/null
fi
say "end $(date '+%Y-%m-%dT%H:%M:%S%z')"
