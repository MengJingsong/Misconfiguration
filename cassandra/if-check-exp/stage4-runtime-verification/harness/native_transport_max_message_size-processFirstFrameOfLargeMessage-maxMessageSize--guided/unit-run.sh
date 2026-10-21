#!/usr/bin/env bash
# Unit tier of native_transport_max_message_size-processFirstFrameOfLargeMessage-maxMessageSize--guided (case 9a
# Procedure 1). usage (on the measured node): unit-run.sh [run-name]     output: ~/stage4-logs/nms/<run-name, default run1>/unit/
#   upstream  MessageSizeLimitTest (the knob's own upstream test: oversized refused, connection reused, no starvation)
#   harness   NativeMessageSizeHoldTest (raw v5 client, every frame but the last held, the server's LargeMessage read)
# Then a summary of the readings per step (unit-summary.py). The judgement against 9a is in the results file.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-run1}; RUN=${1:-run1}
L=$HOME/stage4-logs/nms/$RUN/unit; mkdir -p "$L"; S=$L/summary.txt; : > "$S"
say() { echo "$*" | tee -a "$S"; }
cd "$C"
say "unit-run $(date -Is) host $(hostname -s) clone $(git describe --tags) $(git rev-parse --short HEAD) java $(java -version 2>&1 | head -1)"
say "harness md5 $(cd "$H" && md5sum NativeMessageSizeHoldTest.java unit-run.sh unit-summary.py | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
cp "$H/NativeMessageSizeHoldTest.java" test/unit/org/apache/cassandra/transport/
run() {   # run <class>
  local cls=$1; shift
  rm -rf build/test/cassandra
  ant testsome -Dtest.name=$cls "$@" > "$L/$(basename ${cls//./_}).ant.log" 2>&1 < /dev/null
  local rc=$?
  cp build/test/output/TEST-$cls*.xml "$L/" 2>/dev/null || true
  say "$cls exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/$(basename ${cls//./_}).ant.log")"
}
run org.apache.cassandra.transport.MessageSizeLimitTest
rm -f "$L/harness.out"
run org.apache.cassandra.transport.NativeMessageSizeHoldTest -Dtest.jvm.args="-Dstage4.out=$L/harness.out"
if [ -f "$L/harness.out" ]; then
  say "STAGE4 checks: $(grep -c '^STAGE4 check' "$L/harness.out") ok: $(grep -c '^STAGE4 check.* ok$' "$L/harness.out") MISMATCH: $(grep -c 'MISMATCH' "$L/harness.out")"
  grep 'MISMATCH' "$L/harness.out" | tee -a "$S"
  grep '^STAGE4 info\|^STAGE4 summary' "$L/harness.out" | tee -a "$S"
  python3 "$H/unit-summary.py" "$L/harness.out" | tee -a "$S"
else
  say "FAIL: no harness.out"
fi
