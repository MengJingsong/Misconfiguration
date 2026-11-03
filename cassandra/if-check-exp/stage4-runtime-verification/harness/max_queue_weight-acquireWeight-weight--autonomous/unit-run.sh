#!/usr/bin/env bash
# Unit tier (B2, as amended U1-U5 2026-10-27) of max_queue_weight-acquireWeight-weight--autonomous.
# usage: unit-run.sh <run>     (shake = shakedown, not judged; r1 = run 1)
# Copies the two test classes into $W/cassandra-run62, runs each with
#   _JAVA_OPTIONS=-Xmx4g  (build.xml:1153 appends -Xmx1024m after test.jvm.args; _JAVA_OPTIONS wins)
#   -Dtest.jvm.args=-Dcassandra.netty_use_heap_allocator=true  (U2: queued options buffers on the heap)
# copies the TEST-*.log files to the log dir, writes summary.txt (the MQW lines), and removes the classes from the clone.
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
RUN=${1:?run}
H=$(cd "$(dirname "$0")" && pwd)
C=$W/cassandra-run62
L=$W/logs/max_queue_weight-acquireWeight-weight--autonomous/unit-$RUN
rm -rf "$L"; mkdir -p "$L"; CL=$L/commands.log; S=$L/summary.txt; : > "$CL"; : > "$S"; STAMP=$L/.stamp; touch "$STAMP"; sleep 1
log() { echo "[$(date '+%Y-%m-%dT%H:%M:%S%z')] $*" >> "$CL"; }
say() { echo "$*" >> "$S"; log "SUMMARY $*"; }
T1=$C/test/unit/org/apache/cassandra/utils/concurrent/WeightedQueueCapTest.java
T2=$C/test/unit/org/apache/cassandra/utils/binlog/BinLogCapTest.java
cleanup() {
  rm -f "$T1" "$T2"
  rm -rf "$C/build/test/classes/org/apache/cassandra/utils/concurrent/WeightedQueueCapTest"*.class \
         "$C/build/test/classes/org/apache/cassandra/utils/binlog/BinLogCapTest"*.class
  rm -rf "$C/cassandra.logdir_IS_UNDEFINED"
  say "clone status after cleanup: [$(git -C "$C" status --porcelain | tr '\n' ' ')]"
}
say "unit-run $RUN start $(date '+%Y-%m-%dT%H:%M:%S%z') clone $(git -C "$C" describe --tags) $(git -C "$C" rev-parse --short HEAD)"
say "harness sha256 WeightedQueueCapTest $(shasum -a 256 "$H/WeightedQueueCapTest.java" | cut -c1-16) BinLogCapTest $(shasum -a 256 "$H/BinLogCapTest.java" | cut -c1-16)"
cp "$H/WeightedQueueCapTest.java" "$T1"; cp "$H/BinLogCapTest.java" "$T2"
rc_all=0
for cls in org.apache.cassandra.utils.concurrent.WeightedQueueCapTest org.apache.cassandra.utils.binlog.BinLogCapTest; do
  short=${cls##*.}
  rm -f "$C"/build/test/logs/*/TEST-$cls.log "$C"/build/test/output/TEST-$cls.xml   # the TEST log is appended across runs
  log "+ (cd $C && _JAVA_OPTIONS=-Xmx4g ant -Dlocal.repository=$W/m2 testsome -Dtest.name=$cls -Dtest.jvm.args=-Dcassandra.netty_use_heap_allocator=true)"
  (cd "$C" && _JAVA_OPTIONS=-Xmx4g ant -Dlocal.repository="$W/m2" testsome -Dtest.name=$cls -Dtest.jvm.args=-Dcassandra.netty_use_heap_allocator=true) > "$L/ant-$short.log" 2>&1
  rc=$?; log "  exit=$rc"; [ $rc -ne 0 ] && rc_all=$rc
  f=$(find "$C/build/test/logs" -name "TEST-$cls.log" -newer "$STAMP" | head -1)
  [ -n "$f" ] && cp "$f" "$L/" || say "WARNING: no TEST log for $cls"
  fx=$(find "$C/build/test/output" -name "TEST-$cls.xml" -newer "$STAMP" 2>/dev/null | head -1)
  [ -n "$fx" ] && cp "$fx" "$L/"
  say "ANT $short exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*' "$L/ant-$short.log")"
done
grep -h 'MQW ' "$L"/TEST-*.log | sed 's/^.*MQW /MQW /' >> "$S" 2>/dev/null
say "MQW lines: $(grep -c 'MQW ' "$L"/TEST-*.log 2>/dev/null | tr '\n' ' ')"
cleanup
say "unit-run $RUN end $(date '+%Y-%m-%dT%H:%M:%S%z') rc=$rc_all"
exit $rc_all
