#!/usr/bin/env bash
# Unit tier (B2) of hints-CompressedHintsWriter-compressionBuffer-capacity--autonomous (B2a-B2e).
# usage (on the run node): bash unit-run.sh <run>          output: ~/s4-hw-logs/<run>/unit/
#   1. upstream HintsCompressionTest and HintsBufferTest (context: the tree's own tests of the same classes pass)
#   2. the harness CompressedHintsWriterCapProbeTest; STAGE4 lines in harness.out, summary.txt
# Copies the probe into the tree's test/unit/org/apache/cassandra/hints/ (left there, untracked).
# Never run while a node runs from the same tree (ant rebuilds build/). Shape from the max_mutation_size unit-run.sh.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/s4-hw}
RUN=${1:?run name}
L=$HOME/s4-hw-logs/$RUN/unit
mkdir -p "$L"; S=$L/summary.txt; : > "$S"
for p in $(ls -d /proc/[0-9]* 2>/dev/null); do
  if [ "$(readlink $p/cwd 2>/dev/null)" = "$C" ] && grep -q CassandraDaemon $p/cmdline 2>/dev/null; then echo "a node runs from $C; not running ant" | tee -a "$S"; exit 1; fi
done
cp "$H/CompressedHintsWriterCapProbeTest.java" "$C/test/unit/org/apache/cassandra/hints/"
cd "$C"
say() { echo "$*" | tee -a "$S"; }
say "unit-run $RUN $(date -Is) host $(hostname -s) tree $C $(git describe --tags) $(git rev-parse --short HEAD) java $(java -version 2>&1 | head -1)"
say "harness md5 $(md5sum "$H/CompressedHintsWriterCapProbeTest.java" | cut -c1-32) (copied: $(md5sum test/unit/org/apache/cassandra/hints/CompressedHintsWriterCapProbeTest.java | cut -c1-32))"
run() {   # run <class> [extra ant args...]
  local cls=$1; shift
  ant testsome -Dtest.name=$cls "$@" > "$L/${cls##*.}.ant.log" 2>&1 < /dev/null
  local rc=$?
  cp build/test/output/TEST-$cls*.xml "$L/" 2>/dev/null || true
  say "$cls exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/${cls##*.}.ant.log")"
}
run org.apache.cassandra.hints.HintsCompressionTest
run org.apache.cassandra.hints.HintsBufferTest
rm -f "$L/harness.out"; rm -rf "$L/data"; mkdir -p "$L/data"
run org.apache.cassandra.hints.CompressedHintsWriterCapProbeTest -Dtest.jvm.args="-Dstage4.out=$L/harness.out -Dstage4.dir=$L/data -XX:MaxDirectMemorySize=1g"
say "STAGE4 checks: $(grep -c '^STAGE4 check' "$L/harness.out" 2>/dev/null) ok: $(grep -c '^STAGE4 check.* ok ' "$L/harness.out" 2>/dev/null) MISMATCH: $(grep -c '^STAGE4 check.* MISMATCH ' "$L/harness.out" 2>/dev/null)"
grep ' MISMATCH ' "$L/harness.out" 2>/dev/null | tee -a "$S"
grep '^STAGE4 summary' "$L/harness.out" 2>/dev/null | tee -a "$S"
rm -rf "$L/data"
say "unit-run end $(date -Is)"
