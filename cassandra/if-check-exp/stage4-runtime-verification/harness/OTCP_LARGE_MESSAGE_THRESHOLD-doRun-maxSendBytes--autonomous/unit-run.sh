#!/usr/bin/env bash
# usage: bash unit-run.sh <run-label> [values...]        (case file B2e; amendments S4-A1, S4-A2)
# For each V (default 16384 65536 131072) and repetition 1..3: copies LargeMessageThresholdFrameTest.java into the clone,
# runs  ant testsome -Dtest.name=org.apache.cassandra.net.LargeMessageThresholdFrameTest
#       -Dtest.jvm.args="-Dcassandra.otcp_large_message_threshold=$V -Dstage4.out=<file>"
# keeps the JUnit XML and the ant log, greps the RESULT lines (B2e step 3), and removes the test file at the end.
# Every command and its output goes to $LOG/unit-run.log. Stops at the first failed step.
set -uo pipefail
RUN=${1:?run label}; shift
VALUES=${*:-16384 65536 131072}
C=${CASSANDRA_HOME:-$HOME/cassandra-otc}
H=$(cd "$(dirname "$0")" && pwd)
LOG=$HOME/stage4-logs/otc/$RUN/unit
mkdir -p "$LOG"
exec > >(tee -a "$LOG/unit-run.log") 2>&1
TEST=org.apache.cassandra.net.LargeMessageThresholdFrameTest
DST=$C/test/unit/org/apache/cassandra/net/LargeMessageThresholdFrameTest.java
say() { echo "[$(date +%s%3N) $(date -u +%FT%TZ)] $*"; }
run() { say "\$ $*"; "$@"; local rc=$?; say "rc=$rc"; return $rc; }
cleanup() { rm -f "$DST"; say "removed $DST"; }
trap cleanup EXIT

say "unit-run $RUN values: $VALUES; clone $C ($(git -C "$C" rev-parse HEAD) $(git -C "$C" describe --tags))"
say "harness md5: $(md5sum "$H"/LargeMessageThresholdFrameTest.java "$H"/unit-run.sh | tr '\n' ' ')"
java -version 2>&1 | head -1; ant -version
run cp "$H/LargeMessageThresholdFrameTest.java" "$DST" || exit 1
for V in $VALUES; do
  for rep in 1 2 3; do
    OUT=$LOG/result-V$V-r$rep.txt; rm -f "$OUT"
    say "=== V=$V rep=$rep"
    run ant -Dno-checkstyle=true testsome -Dtest.name=$TEST \
        "-Dtest.jvm.args=-Dcassandra.otcp_large_message_threshold=$V -Dstage4.out=$OUT" \
        -f "$C/build.xml" > "$LOG/ant-V$V-r$rep.log" 2>&1 < /dev/null
    rc=$?
    tail -5 "$LOG/ant-V$V-r$rep.log"
    XML=$C/build/test/output/TEST-$TEST.xml
    [ -f "$XML" ] && cp "$XML" "$LOG/TEST-V$V-r$rep.xml"
    grep -o 'RESULT [^<]*' "$LOG/TEST-V$V-r$rep.xml" 2>/dev/null | sed 's/&#[0-9]*;//g' > "$LOG/xml-result-V$V-r$rep.txt"
    say "RESULT lines (stage4.out):"; cat "$OUT" 2>/dev/null
    n=$(grep -c '^RESULT' "$OUT" 2>/dev/null || echo 0)
    if [ $rc -ne 0 ] || ! grep -q 'BUILD SUCCESSFUL' "$LOG/ant-V$V-r$rep.log" || [ "$n" -ne 3 ]; then
      say "FAILED at V=$V rep=$rep (ant rc=$rc, RESULT lines=$n); stopping"; exit 1
    fi
    bad=$(awk -v v=$V '{for(i=1;i<=NF;i++){split($i,a,"="); if(a[1]=="V"&&a[2]!=v) print "V mismatch "$i; if(a[1]=="lmt"&&a[2]!=v-21) print "lmt mismatch "$i}}' "$OUT")
    [ -n "$bad" ] && { say "property did not reach the test JVM: $bad; stopping"; exit 1; }
  done
done
cat "$LOG"/result-V*-r*.txt > "$LOG/all-results.txt"
say "done; $(wc -l < "$LOG/all-results.txt") RESULT lines in $LOG/all-results.txt"
# leftover JUnit JVMs of this clone
ps -eo pid,args | grep '[j]ava' | grep -F "$C" | grep -i junit && say "WARNING: junit JVM left" || say "no junit JVM left"
