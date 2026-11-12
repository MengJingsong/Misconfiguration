#!/usr/bin/env bash
# Unit tier (B2) of commitlog_max_compression_buffers_in_pool-simplecachedbufferpool-usedbuffers--autonomous.
# usage: bash unit-run.sh [run-name]     (on apt138; tree /mydata/jingsong-cass-s4/o45/src, built with ant build-test)
# Output: /mydata/jingsong-cass-s4/o45/<run-name>/unit/. Copies Test 1, generates Test 2 + control (gen_test2.py),
# runs each class with ant testsome (BMUnit agent port 9391), collects stdout logs and junit XML, removes the
# test sources again, checks no test JVM is left, runs unit-analyze.py.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); B=/mydata/jingsong-cass-s4/o45; C=$B/src; RUN=${1:-run1}
L=$B/$RUN/unit; mkdir -p "$L"; S=$L/summary.txt; : > "$S"
say() { echo "$*" | tee -a "$S"; }
cd "$C" || exit 1
say "unit-run $(date -u +%FT%TZ) host $(hostname -s) tree $(git describe --tags) java $(java -version 2>&1 | head -1)"
say "harness md5 $(cd "$H" && md5sum SimpleCachedBufferPoolCapTest.java gen_test2.py unit-run.sh unit-analyze.py | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
say "df: $(df -h /mydata | tail -1)"
U=test/unit/org/apache/cassandra/io/util; CL=test/unit/org/apache/cassandra/db/commitlog
cp "$H/SimpleCachedBufferPoolCapTest.java" "$U/"
python3 "$H/gen_test2.py" "$CL/CommitLogSegmentBackpressureTest.java" "$CL" | tee -a "$S"
cp "$U/SimpleCachedBufferPoolCapTest.java" "$CL"/CommitLogBufferCap*Test.java "$L/" # the exact sources run
for T in org.apache.cassandra.io.util.SimpleCachedBufferPoolCapTest \
         org.apache.cassandra.db.commitlog.CommitLogBufferCap2Test \
         org.apache.cassandra.db.commitlog.CommitLogBufferCap3Test \
         org.apache.cassandra.db.commitlog.CommitLogBufferCap6Test \
         org.apache.cassandra.db.commitlog.CommitLogBufferCapCtlTest; do
  short=${T##*.}
  rm -rf build/test/cassandra
  t0=$(date +%s)
  say "== $short start $(date -u +%FT%TZ)"
  echo "+ ant testsome -Dtest.name=$T -Dtest.jvm.args=-Dorg.jboss.byteman.contrib.bmunit.agent.port=9391" >> "$S"
  ant testsome -Dtest.name=$T -Dtest.jvm.args=-Dorg.jboss.byteman.contrib.bmunit.agent.port=9391 > "$L/ant-$short.log" 2>&1 < /dev/null
  rc=$?
  say "$short ant exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant-$short.log") $(( $(date +%s) - t0 )) s"
  cp build/test/logs/_jdk11/TEST-$T.log "$L/" 2>/dev/null || cp build/test/logs/TEST-$T.log "$L/" 2>/dev/null || say "NO stdout log for $short"
  cp build/test/output/TEST-$T.xml "$L/" 2>/dev/null || cp build/test/output/_jdk11/TEST-$T.xml "$L/" 2>/dev/null || true
  say "$short CAP/POOL lines: $(grep -h -c '^\(CAP\|POOL\) ' "$L"/TEST-$T.log 2>/dev/null)"
done
rm -f "$U/SimpleCachedBufferPoolCapTest.java" "$CL"/CommitLogBufferCap*Test.java; rm -rf build/test/cassandra
say "cleanup: test sources removed ($(git status --short test | wc -l) changed files under test/); leftover test JVMs: $(ps -eo args | grep -c '[C]ommitLogBufferCap\|[S]impleCachedBufferPoolCapTest')"
python3 "$H/unit-analyze.py" "$L" | tee -a "$S"
say "done $(date -u +%FT%TZ)"
