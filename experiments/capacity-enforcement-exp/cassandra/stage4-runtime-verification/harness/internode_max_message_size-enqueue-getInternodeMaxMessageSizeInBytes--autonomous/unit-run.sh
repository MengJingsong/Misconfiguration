#!/usr/bin/env bash
# Unit tier (B2a, B2e) of internode_max_message_size-enqueue-getInternodeMaxMessageSizeInBytes--autonomous.
# usage (on the run node): unit-run.sh <run>        output: ~/stage4-logs/ime/<run>/unit/
#   1. upstream ConnectionTest#testInsufficientSpace (the enqueue/capacity path of this clone works: a known answer)
#   2. MaxMessageSizeProbeTest at the default test heap (build.xml maxmemory 1024m = B2a's -Xmx1g)
# The clone is CASSANDRA_HOME (default ~/cassandra-run1), built with `ant build-test`. The harness test is copied into
# test/unit/org/apache/cassandra/net/ and removed at the end, so the clone is left as found.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-run1}
run=${1:?run name, e.g. run1}
L=$HOME/stage4-logs/ime/$run/unit; mkdir -p "$L"; S=$L/summary.txt; : > "$S"
say() { echo "$*" | tee -a "$S"; }
T=$C/test/unit/org/apache/cassandra/net/MaxMessageSizeProbeTest.java
cp "$H/MaxMessageSizeProbeTest.java" "$T"
trap 'rm -f "$T"' EXIT
cd "$C"
say "unit-run $run $(date -Is) host $(hostname -s) clone $(git describe --tags) $(git rev-parse --short HEAD) java $(java -version 2>&1 | head -1 | tr -d '"') md5 $(md5sum "$H/MaxMessageSizeProbeTest.java" | cut -c1-12)"
one() {   # one <tag> <class> [extra ant args...]
  local tag=$1 cls=$2; shift 2
  rm -rf build/test/cassandra
  ant testsome -Dtest.name=$cls "$@" > "$L/$tag.ant.log" 2>&1 < /dev/null
  local rc=$?
  for x in build/test/output/TEST-$cls*.xml; do [ -f "$x" ] && cp "$x" "$L/$tag.$(basename "$x")"; done
  say "$tag $cls exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/$tag.ant.log")"
}
one upstream org.apache.cassandra.net.ConnectionTest -Dtest.methods=testInsufficientSpace
rm -f "$L/probe.out"
one probe org.apache.cassandra.net.MaxMessageSizeProbeTest -Dtest.jvm.args="-Dstage4.out=$L/probe.out"
say "probe: $(grep -m1 '^STAGE4 env' "$L/probe.out" 2>/dev/null)"
say "probe: $(grep '^STAGE4 summary' "$L/probe.out" 2>/dev/null || echo 'no summary line')"
say "probe: $(grep -c '^STAGE4 case' "$L/probe.out" 2>/dev/null) case lines, $(grep -c ' ok$' "$L/probe.out" 2>/dev/null) ok, $(grep -c 'MISMATCH' "$L/probe.out" 2>/dev/null) MISMATCH"
grep 'MISMATCH' "$L/probe.out" 2>/dev/null | tee -a "$S"
rm -f "$T"
say "clone status after the run (expect empty): [$(git status --short | tr '\n' ' ')]"
