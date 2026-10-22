#!/usr/bin/env bash
# Unit tier (B2) of index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous, on pc12.
# usage: bash unit-run.sh [run-name] [partitions]     output: ~/stage4-logs/is2/<run-name>/unit/
# Copies IndexSummaryCapacityProbeTest into ~/cassandra-is2, runs ant testsome twice (rep1 = reading, rep2 = repeat, R1/R3),
# keeps probe.out, ant logs, junit XML and per-test logs, then runs unit-analyze.py. partitions != 10000 is a shakedown only.
# --remove deletes the copied test.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-is2}; RUN=${1:-run1}; NP=${2:-10000}
T=$C/test/unit/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryCapacityProbeTest.java
CLS=org.apache.cassandra.io.sstable.indexsummary.IndexSummaryCapacityProbeTest
if [ "$RUN" = "--remove" ]; then rm -f "$T"; echo "removed $T"; exit 0; fi
L=$HOME/stage4-logs/is2/$RUN/unit; mkdir -p "$L"; S=$L/summary.txt; : > "$S"
say() { echo "$*" | tee -a "$S"; }
cd "$C"
say "unit-run $(date -Is) host $(hostname -s) clone $(git describe --tags) $(git rev-parse --short HEAD) partitions=$NP java $(java -version 2>&1 | head -1)"
say "harness md5 $(cd "$H" && md5sum IndexSummaryCapacityProbeTest.java unit-run.sh unit-analyze.py | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
cp "$H/IndexSummaryCapacityProbeTest.java" "$T"
for rep in rep1 rep2; do
  rm -rf build/test/cassandra build/test/output/TEST-$CLS*.xml "$L/$rep.probe"
  t0=$(date +%s)
  ant testsome -Dtest.name=$CLS -Dtest.jvm.args="-Dprobe.out=$L/$rep.probe -Dprobe.partitions=$NP" > "$L/ant-$rep.log" 2>&1 < /dev/null
  rc=$?
  cp build/test/output/TEST-$CLS*.xml "$L/TEST-$rep.xml" 2>/dev/null || true
  cp build/test/logs/_jdk11/TEST-$CLS.log "$L/test-$rep.log" 2>/dev/null || true
  say "$rep ant exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant-$rep.log") $(( $(date +%s) - t0 )) s; probe lines $(grep -c '^PROBE' "$L/$rep.probe" 2>/dev/null)"
  sed "s/^/  $rep /" "$L/$rep.probe" 2>/dev/null | tee -a "$S"
done
say "leftover junit JVMs: $(ps -eo pid,args | awk '$2 ~ /java$/ && /IndexSummaryCapacityProbeTest/' | wc -l)"
python3 "$H/unit-analyze.py" "$L" | tee -a "$S"
say "done $(date -Is)"
