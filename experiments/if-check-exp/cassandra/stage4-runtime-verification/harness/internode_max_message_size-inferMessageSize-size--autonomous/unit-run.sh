#!/usr/bin/env bash
# Unit tier (B2e steps 2-4) of internode_max_message_size-inferMessageSize-size--autonomous.
# usage (on the run node): unit-run.sh <run>       output: ~/stage4-logs/imm/<run>/unit/
#   1. the upstream MessageTest (its testInferMessageSize is the instrument's known-answer check)
#   2. InferMessageSizeLimitTest at the default test heap (-Xmx1024m from build.xml)
#   3. InferMessageSizeLimitTest again with a 2 GiB test heap (B2g row "result changes with -Xmx")
# The clone is CASSANDRA_HOME (default ~/cassandra-run5), built with `ant build-test`.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-run5}
run=${1:?run name, e.g. run1}
L=$HOME/stage4-logs/imm/$run/unit; mkdir -p "$L"; S=$L/summary.txt; : > "$S"
say() { echo "$*" | tee -a "$S"; }
cp "$H/InferMessageSizeLimitTest.java" "$C/test/unit/org/apache/cassandra/net/"
cd "$C"
say "unit-run $run $(date -Is) host $(hostname -s) clone $(git describe --tags) $(git rev-parse --short HEAD) java $(java -version 2>&1 | head -1 | tr -d '"') md5 $(md5sum "$H/InferMessageSizeLimitTest.java" | cut -c1-12)"
one() {   # one <tag> <class> [extra ant args...]
  local tag=$1 cls=$2; shift 2
  rm -rf build/test/cassandra
  ant ${ANTFILE:-} testsome -Dtest.name=$cls "$@" > "$L/$tag.ant.log" 2>&1 < /dev/null
  local rc=$?
  for x in build/test/output/TEST-$cls*.xml; do [ -f "$x" ] && cp "$x" "$L/$tag.$(basename "$x")"; done
  say "$tag $cls exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/$tag.ant.log")"
}
one upstream org.apache.cassandra.net.MessageTest
rm -f "$L/xmx1g.out" "$L/xmx2g.out"
one xmx1g org.apache.cassandra.net.InferMessageSizeLimitTest -Dtest.jvm.args="-Dstage4.out=$L/xmx1g.out"
# build.xml's testmacro has maxmemory="1024m", which ant appends after test.jvm.args, so -Xmx there is overridden; the
# 2g repeat uses build-stage4.xml, a copy of build.xml in the run clone with maxmemory="2048m" (nothing else changed)
sed 's/maxmemory="1024m"/maxmemory="2048m"/' build.xml > build-stage4.xml
say "build-stage4.xml: $(diff build.xml build-stage4.xml | grep -c '^>') lines differ from build.xml (maxmemory only)"
ANTFILE="-f build-stage4.xml" one xmx2g org.apache.cassandra.net.InferMessageSizeLimitTest -Dtest.jvm.args="-Dstage4.out=$L/xmx2g.out"
rm -f build-stage4.xml
for f in xmx1g xmx2g; do
  say "$f: $(grep -m1 '^STAGE4 env' "$L/$f.out" 2>/dev/null) | $(grep '^STAGE4 summary' "$L/$f.out" 2>/dev/null)"
  grep 'MISMATCH' "$L/$f.out" | tee -a "$S"
done
# the -Xmx control: every case line identical across the two heaps
if [ ! -s "$L/xmx1g.out" ] || [ ! -s "$L/xmx2g.out" ]; then
  say "xmx control: NOT RUN (an output file is missing or empty)"
elif diff <(grep '^STAGE4 case' "$L/xmx1g.out") <(grep '^STAGE4 case' "$L/xmx2g.out") > "$L/xmx-diff.txt"; then
  say "xmx control: $(grep -c '^STAGE4 case' "$L/xmx1g.out") case lines identical at 1g and 2g"
else
  say "xmx control: case lines DIFFER (see xmx-diff.txt)"
fi
rm -f "$C/test/unit/org/apache/cassandra/net/InferMessageSizeLimitTest.java"
