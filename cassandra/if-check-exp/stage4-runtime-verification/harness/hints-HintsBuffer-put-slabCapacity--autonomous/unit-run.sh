#!/usr/bin/env bash
# Unit tier (B2) of hints-HintsBuffer-put-slabCapacity--autonomous. usage: bash unit-run.sh <run> ; output ~/s4-hb-logs/<run>/unit/
# Copies HintsSlabCapTest into the tree (~/s4-hb, untracked), runs it once per n in 1 2 3 5 (one forked JVM per value), then the derive scenario once per max_mutation_size in 4 16 24 40 MiB,
# -XX:MaxDirectMemorySize=1g, -Dstage4.out per n. Also runs upstream HintsBufferTest and HintsBufferPoolTest once (context).
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/s4-hb}
RUN=${1:?run name}; L=$HOME/s4-hb-logs/$RUN/unit; mkdir -p "$L"; S=$L/summary.txt; : > "$S"
for p in /proc/[0-9]*; do
  if [ "$(readlink $p/cwd 2>/dev/null)" = "$C" ] && grep -q CassandraDaemon $p/cmdline 2>/dev/null; then echo "a node runs from $C; not running ant" | tee -a "$S"; exit 1; fi
done
cp "$H/HintsSlabCapTest.java" "$C/test/unit/org/apache/cassandra/hints/"
cd "$C"; ulimit -n 100000
say() { echo "$*" | tee -a "$S"; }
say "unit-run $RUN $(date -Is) host $(hostname -s) tree $C $(git describe --tags) java $(java -version 2>&1 | head -1)"
say "harness md5 $(md5sum "$H/HintsSlabCapTest.java" | cut -c1-32)"
run() { local cls=$1 tag=$2; shift 2
  ant testsome -Dtest.name=$cls "$@" > "$L/$tag.ant.log" 2>&1 < /dev/null; local rc=$?
  cp build/test/output/TEST-$cls*.xml "$L/$tag.xml" 2>/dev/null || true
  say "$tag exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/$tag.ant.log")"; }
run org.apache.cassandra.hints.HintsBufferTest upstream-HintsBufferTest
run org.apache.cassandra.hints.HintsBufferPoolTest upstream-HintsBufferPoolTest
for n in 1 2 3 5; do
  rm -f "$L/n$n.out"
  run org.apache.cassandra.hints.HintsSlabCapTest n$n -Dtest.jvm.args="-Dcassandra.MAX_HINT_BUFFERS=$n -Dstage4.out=$L/n$n.out -XX:MaxDirectMemorySize=1g"
  say "n=$n checks: $(grep -c '^STAGE4 check' $L/n$n.out) ok: $(grep -c '^STAGE4 check.* ok ' $L/n$n.out) MISMATCH: $(grep -c '^STAGE4 check.* MISMATCH ' $L/n$n.out)"
  grep ' MISMATCH ' "$L/n$n.out" | tee -a "$S"
done
for m in 4 16 24 40; do
  rm -f "$L/derive$m.out"
  run org.apache.cassandra.hints.HintsSlabCapTest derive$m -Dtest.jvm.args="-Dstage4.only=derive -Dstage4.mms=$m -Dstage4.out=$L/derive$m.out -XX:MaxDirectMemorySize=1g"
  say "derive m=$m checks: $(grep -c '^STAGE4 check' $L/derive$m.out) ok: $(grep -c '^STAGE4 check.* ok ' $L/derive$m.out) MISMATCH: $(grep -c '^STAGE4 check.* MISMATCH ' $L/derive$m.out)"
  grep ' MISMATCH ' "$L/derive$m.out" | tee -a "$S"
done
say "unit-run end $(date -Is)"
