#!/usr/bin/env bash
# Unit tier (B2) of maximum_replication_factor-ReplicaList.add-newSize--autonomous. usage: bash unit-run.sh <run>; output ~/s4-b7-rl-logs/<run>/unit/
# Copies ReplicaListGrowthTest into the tree ~/s4-b7-rl (untracked) and runs it once (one forked 1 GiB JVM). Stops on a failed first check
# (instrument-enabled: the guardrail must be enabled at threshold 3 and failsOn(10) true, else the control is vacuous).
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/s4-b7-rl}
RUN=${1:?run name}; L=$HOME/s4-b7-rl-logs/$RUN/unit; mkdir -p "$L"; S=$L/summary.txt; : > "$S"
for p in /proc/[0-9]*; do
  if [ "$(readlink $p/cwd 2>/dev/null)" = "$C" ] && grep -q CassandraDaemon $p/cmdline 2>/dev/null; then echo "a node runs from $C; not running ant" | tee -a "$S"; exit 1; fi
done
cp "$H/ReplicaListGrowthTest.java" "$C/test/unit/org/apache/cassandra/locator/"
cd "$C"; ulimit -n 100000
say() { echo "$*" | tee -a "$S"; }
say "unit-run $RUN $(date -Is) host $(hostname -s) tree $C $(git describe --tags) java $(java -version 2>&1 | head -1)"
say "harness md5 $(md5sum "$H/ReplicaListGrowthTest.java" | cut -c1-32)"
rm -f "$L/out.txt"
ant testsome -Dtest.name=org.apache.cassandra.locator.ReplicaListGrowthTest -Dtest.jvm.args="-Dstage4.out=$L/out.txt" > "$L/ant.log" 2>&1 < /dev/null; rc=$?
cp build/test/output/TEST-org.apache.cassandra.locator.ReplicaListGrowthTest*.xml "$L/test.xml" 2>/dev/null || true
say "ant exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant.log")"
say "EXPECTED: ant exit=0, Tests run: 1, Failures: 0, Errors: 0; STAGE4 first check instrument-enabled ok; zero MISMATCH lines"
say "first check: $(grep -m1 '^STAGE4 check' "$L/out.txt")"
say "checks: $(grep -c '^STAGE4 check' "$L/out.txt") ok: $(grep -c '^STAGE4 check.* ok ' "$L/out.txt") MISMATCH: $(grep -c '^STAGE4 check.* MISMATCH ' "$L/out.txt")"
grep ' MISMATCH ' "$L/out.txt" | tee -a "$S"
grep '^STAGE4 end' "$L/out.txt" | tee -a "$S"
say "unit-run end $(date -Is)"
