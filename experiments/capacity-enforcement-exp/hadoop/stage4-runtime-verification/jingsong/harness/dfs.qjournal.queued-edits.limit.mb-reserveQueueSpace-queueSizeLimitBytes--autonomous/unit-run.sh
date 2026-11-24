#!/usr/bin/env bash
# Stage-4 unit tier (B2 + A1, A2) for dfs.qjournal.queued-edits.limit.mb-reserveQueueSpace-queueSizeLimitBytes--autonomous.
# Run on the stage-4 node:  unit-run.sh <R> <harness-dir>
# Logs every command and its output to <R>/logs/unit/unit-run.log.
set -uo pipefail
R=${1:?R}; HD=${2:?harness dir}
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64 PATH=/usr/lib/jvm/java-8-openjdk-amd64/bin:$PATH YARN_IGNORE_ENGINES=true
L=$R/logs/unit; mkdir -p "$L"; LOG=$L/unit-run.log
run() { echo "+ $*" | tee -a "$LOG"; "$@" 2>&1 | tee -a "$LOG"; return ${PIPESTATUS[0]}; }
echo "=== unit-run start $(date -Is) host=$(hostname)" | tee -a "$LOG"
run java -version
run md5sum "$HD/TestQueuedEditsCapProbe.java" "$0"
T=$R/src/hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/qjournal/client
run cp "$HD/TestQueuedEditsCapProbe.java" "$T/"
run git -C "$R/src" status --short
cd "$R/src" || exit 1
SR=hadoop-hdfs-project/hadoop-hdfs/target/surefire-reports
# probe
run mvn -B -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestQueuedEditsCapProbe -DfailIfNoTests=false -Dmaven.javadoc.skip=true > /dev/null
cp $SR/*TestQueuedEditsCapProbe* "$L/" 2>/dev/null
# reference test
run mvn -B -pl hadoop-hdfs-project/hadoop-hdfs surefire:test -Dtest='TestIPCLoggerChannel#testQueueLimiting' -DfailIfNoTests=false > /dev/null
cp $SR/*TestIPCLoggerChannel* "$L/" 2>/dev/null
echo "--- surefire summaries" | tee -a "$LOG"
grep -h "Tests run" "$L"/*.txt | tee -a "$LOG"
echo "--- IFCHK lines" | tee -a "$LOG"
grep -h "^IFCHK" "$L"/*TestQueuedEditsCapProbe-output.txt | tee "$L/ifchk.csv" | tee -a "$LOG"
echo "=== unit-run end $(date -Is)" | tee -a "$LOG"
