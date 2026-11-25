#!/usr/bin/env bash
# Stage-4 unit tier (B2e with A1-A3), order 9 PriorityQueue_maxSize-insert-maxSize--autonomous, Jingsong, node pc75.
# Usage (on the node): unit-run.sh <run-folder> <harness-dir>
# Logs every command and its output to <run>/unit/unit-run.log; stops at the first failed step.
set -u
R=${1:?run folder}; H=${2:?harness dir}
S=$R/src; U=$R/unit; mkdir -p "$U"
exec > >(tee -a "$U/unit-run.log") 2>&1
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64 PATH=/usr/lib/jvm/java-8-openjdk-amd64/bin:$PATH YARN_IGNORE_ENGINES=true
COMMON=$S/hadoop-common-project/hadoop-common
CORE=$S/hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core
JOBC=$S/hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-jobclient
ARG="-Xmx512m -XX:+UseCompressedOops -XX:-UseTLAB"
DBG="-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=5005"
step() { echo; echo "=== $(date '+%F %T %Z') STEP: $*"; }
die() { echo "=== STOP: $*"; exit 1; }
surefire() { # module class -> print surefire counts from the report
  local f; f=$(ls "$1"/target/surefire-reports/TEST-*"$2".xml 2>/dev/null | head -1)
  [ -n "$f" ] && grep -o '<testsuite[^>]*' "$f" | grep -oE '(tests|failures|errors|skipped)="[0-9]+"' | tr '\n' ' '; echo
}
debugged() { # name module mvn-args... : run mvn test under the debug agent and count jdb hits
  local name=$1 mod=$2; shift 2
  step "debugged run $name in $mod: mvn $*"
  ( cd "$mod" && mvn -B test "$@" -Dmaven.surefire.debug="$DBG" -DfailIfNoTests=false ) > "$U/mvn-$name.log" 2>&1 &
  local mp=$!
  bash "$H/jdbcount.sh" 5005 "$U/jdb-$name.log" 900 | tee "$U/count-$name.txt"
  wait $mp; echo "mvn exit $?"
  grep -E "Tests run:|BUILD|PQCAP" "$U/mvn-$name.log" | tail -8
}

step "environment"; date; hostname; uname -r; java -version; mvn -version | head -1; df -h /mydata | tail -1
step "install harness test classes into the private copy"
cp -v "$H/TestPriorityQueueInsertCap.java" "$COMMON/src/test/java/org/apache/hadoop/util/" || die copy
cp -v "$H/TestSequenceFileSorterMerge.java" "$COMMON/src/test/java/org/apache/hadoop/io/" || die copy
md5sum "$H"/*
git -C "$S" status --short

step "Part 1 (B2e step 3): TestPriorityQueueInsertCap, argLine $ARG"
( cd "$COMMON" && mvn -B test -Dtest=TestPriorityQueueInsertCap -Dmaven-surefire-plugin.argLine="$ARG" -DfailIfNoTests=false ) > "$U/mvn-part1.log" 2>&1
echo "mvn exit $?"; grep -E "BUILD|Tests run:" "$U/mvn-part1.log" | tail -3
grep -h "PQCAP" "$COMMON"/target/surefire-reports/*TestPriorityQueueInsertCap-output.txt "$U/mvn-part1.log" 2>/dev/null | sort -u > "$U/part1-readings.txt"
wc -l "$U/part1-readings.txt"; grep -q "PQCAP row 3 65536" "$U/part1-readings.txt" || die "Part 1 readings missing"

step "jdb known answer (A2 vi)"
debugged jdbcheck "$COMMON" -Dtest='TestPriorityQueueInsertCap#testJdbKnownAnswer' -Dmaven-surefire-plugin.argLine="-Dpqcap.jdbcheck=true"
grep -q "insert=5 initialize=1 attached=yes" "$U/count-jdbcheck.txt" || die "jdb known answer failed"

for f in 2 100; do
  debugged sorter-f$f "$COMMON" -Dtest=TestSequenceFileSorterMerge -Dmaven-surefire-plugin.argLine="-Xmx512m -Dpqcap.factor=$f"
  echo "surefire: $(surefire "$COMMON" TestSequenceFileSorterMerge)"
  grep -h "PQCAP" "$COMMON"/target/surefire-reports/*TestSequenceFileSorterMerge-output.txt "$U/mvn-sorter-f$f.log" 2>/dev/null | sort -u | tee "$U/sorter-f$f-readings.txt"
done
debugged TestMerger "$CORE" -Dtest=TestMerger
echo "surefire: $(surefire "$CORE" TestMerger)"
debugged TestSequenceFileMergeProgress "$JOBC" -Dtest=TestSequenceFileMergeProgress
echo "surefire: $(surefire "$JOBC" TestSequenceFileMergeProgress)"

step "static scan (B2e step 5 / A3)"
python3 -I "$H/scan_insert.py" "$COMMON/target/test-classes" > "$U/scan-known-answer.txt"; grep -E "HIT|SUMMARY|SUBCLASS" "$U/scan-known-answer.txt"
python3 -I "$H/scan_insert.py" "$COMMON/target/classes" "$CORE/target/classes" > "$U/scan-main.txt"; cat "$U/scan-main.txt"

step "leftover check"
ps -eo pid,cmd | grep -E "[s]urefire|[j]db |[j]dwp" | cut -c1-160 || true
step "done"
