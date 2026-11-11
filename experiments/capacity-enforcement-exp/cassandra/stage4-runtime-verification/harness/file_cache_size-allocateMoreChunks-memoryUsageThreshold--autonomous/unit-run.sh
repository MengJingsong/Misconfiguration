#!/usr/bin/env bash
# Unit tier (B2 as amended 2026-10-27, U1-U3) of file_cache_size-allocateMoreChunks-memoryUsageThreshold--autonomous.
# usage: unit-run.sh <run>     (shake = shakedown, not judged; r1 = run 1)
# Copies BufferPoolCapProbeTest into $W/cassandra-run63 and runs each @Test method in its own JVM (U2: the cap message uses one
# static NoSpamLogger statement per JVM), with -Dtest.jvm.args=-XX:MaxDirectMemorySize=2g (U2: the T = 512 MiB method holds 1 GiB
# plus padding in direct memory). Copies each method's TEST log to the log dir as TEST-<method>.log, writes summary.txt (FCSU
# lines and per-method grep counts of the cap message), and removes the class from the clone.
# Shell structure adapted from harness/max_queue_weight-acquireWeight-weight--autonomous/unit-run.sh (that file is not modified).
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
RUN=${1:?run}
H=$(cd "$(dirname "$0")" && pwd)
C=$W/cassandra-run63
L=$W/logs/file_cache_size-allocateMoreChunks-memoryUsageThreshold--autonomous/unit-$RUN
rm -rf "$L"; mkdir -p "$L"; CL=$L/commands.log; S=$L/summary.txt; : > "$CL"; : > "$S"
log() { echo "[$(date '+%Y-%m-%dT%H:%M:%S%z')] $*" >> "$CL"; }
say() { echo "$*" >> "$S"; log "SUMMARY $*"; }
CLS=org.apache.cassandra.utils.memory.BufferPoolCapProbeTest
T1=$C/test/unit/org/apache/cassandra/utils/memory/BufferPoolCapProbeTest.java
cleanup() {
  rm -f "$T1"
  rm -rf "$C/build/test/classes/org/apache/cassandra/utils/memory/BufferPoolCapProbeTest"*.class
  rm -rf "$C/cassandra.logdir_IS_UNDEFINED"
  say "clone status after cleanup: [$(git -C "$C" status --porcelain | tr '\n' ' ')]"
}
say "unit-run $RUN start $(date '+%Y-%m-%dT%H:%M:%S%z') clone $(git -C "$C" describe --tags) $(git -C "$C" rev-parse --short HEAD)"
say "harness sha256 BufferPoolCapProbeTest $(shasum -a 256 "$H/BufferPoolCapProbeTest.java" | cut -c1-16)"
cp "$H/BufferPoolCapProbeTest.java" "$T1"
rc_all=0
for m in t0 t1_5MiB t4MiB t8MiB t16MiB t512MiB; do
  find "$C/build/test/logs" "$C/build/test/output" -name "TEST-$CLS*" -exec rm -f {} + 2>/dev/null
  log "+ (cd $C && ant -Dlocal.repository=$W/m2 testsome -Dtest.name=$CLS -Dtest.methods=$m -Dtest.jvm.args=-XX:MaxDirectMemorySize=2g)"
  (cd "$C" && ant -Dlocal.repository="$W/m2" testsome -Dtest.name=$CLS -Dtest.methods=$m -Dtest.jvm.args=-XX:MaxDirectMemorySize=2g) > "$L/ant-$m.log" 2>&1
  rc=$?; log "  exit=$rc"; [ $rc -ne 0 ] && rc_all=$rc
  f=$(find "$C/build/test/logs" -name "TEST-$CLS*.log" | head -1)
  if [ -n "$f" ]; then cp "$f" "$L/TEST-$m.log"; log "  TEST log $f -> TEST-$m.log"; else say "WARNING: no TEST log for $m"; : > "$L/TEST-$m.log"; fi
  fx=$(find "$C/build/test/output" -name "TEST-$CLS*.xml" 2>/dev/null | head -1)
  [ -n "$fx" ] && cp "$fx" "$L/TEST-$m.xml"
  say "ANT $m exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*' "$L/ant-$m.log")"
  say "$(grep -h 'FCSU ' "$L/TEST-$m.log" | sed 's/^.*FCSU /FCSU /' | head -1)"
  say "$(grep -h 'FCSU-AFTER ' "$L/TEST-$m.log" | sed 's/^.*FCSU-AFTER /FCSU-AFTER /' | head -1)"
  say "CAPLOG $m total=$(grep -c 'Maximum memory usage reached' "$L/TEST-$m.log") lines=[$(grep 'Maximum memory usage reached' "$L/TEST-$m.log" | sed 's/^.*Maximum/Maximum/' | tr '\n' ';')]"
done
say "$(grep -h 'FCSU-ENV ' "$L/TEST-t0.log" | sed 's/^.*FCSU-ENV /FCSU-ENV /' | head -1)"
cleanup
say "unit-run $RUN end $(date '+%Y-%m-%dT%H:%M:%S%z') rc=$rc_all"
exit $rc_all
