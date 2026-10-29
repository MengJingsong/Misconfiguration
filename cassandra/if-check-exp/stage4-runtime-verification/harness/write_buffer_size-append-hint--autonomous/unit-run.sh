#!/usr/bin/env bash
# Unit tier (B2) of write_buffer_size-append-hint--autonomous.
# usage (on the run node): unit-run.sh [run-name]   output: ~/s4-hwb/logs/write_buffer_size-append-hint--autonomous/<run-name, default run1>/unit/
# Copies WriteBufferProbeTest into the copy's test/unit/org/apache/cassandra/hints/ (the copy is ~/s4-hwb/base, made by
# copy-source.sh, built with ant build-test), runs it with ant testsome (build.xml's test heap) and a GC log, then the
# upstream HintsReaderTest as a sanity run of the same writer, and writes summary.txt (STAGE4 lines, counts).
# --remove deletes the copied test from the copy.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/s4-hwb/base}; RUN=${1:-run1}
T=$C/test/unit/org/apache/cassandra/hints/WriteBufferProbeTest.java
if [ "$RUN" = "--remove" ]; then rm -f "$T"; rm -f $C/build/test/classes/org/apache/cassandra/hints/WriteBufferProbeTest*.class; echo "removed $T"; exit 0; fi
L=$HOME/s4-hwb/logs/write_buffer_size-append-hint--autonomous/$RUN/unit; mkdir -p "$L"; S=$L/summary.txt; : > "$S"
say() { echo "$*" | tee -a "$S"; }
cd "$C"
say "unit-run $(date -Is) host $(hostname -s) copy $C $(git describe --tags) $(git rev-parse --short HEAD) java $(java -version 2>&1 | head -1)"
say "harness md5 $(cd "$H" && md5sum WriteBufferProbeTest.java unit-run.sh | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
cp "$H/WriteBufferProbeTest.java" "$T"
rm -f "$L/test.out"
rm -rf build/test/cassandra
ant testsome -Dtest.name=org.apache.cassandra.hints.WriteBufferProbeTest \
  -Dtest.jvm.args="-Dstage4.out=$L/test.out -Xlog:gc*:file=$L/gc.log" > "$L/ant.log" 2>&1 < /dev/null
rc=$?
cp build/test/output/TEST-org.apache.cassandra.hints.WriteBufferProbeTest*.xml "$L/" 2>/dev/null || true
say "probe ant exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant.log")"
ant testsome -Dtest.name=org.apache.cassandra.hints.HintsReaderTest > "$L/ant-upstream.log" 2>&1 < /dev/null
say "upstream HintsReaderTest ant exit=$? $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant-upstream.log")"
grep '^STAGE4 info\|^STAGE4 error\|^STAGE4 summary' "$L/test.out" | tee -a "$S"
grep '^STAGE4 case' "$L/test.out" >> "$S"
grep '^STAGE4 check' "$L/test.out" >> "$S"
say "checks: $(grep -c '^STAGE4 check' "$L/test.out") ok: $(grep -c '^STAGE4 check.* ok$' "$L/test.out") MISMATCH: $(grep -c '^STAGE4 check.* MISMATCH$' "$L/test.out")"
say "append lines: $(grep -c '^STAGE4 append' "$L/test.out")"
say "done $(date -Is)"
