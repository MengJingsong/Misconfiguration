#!/usr/bin/env bash
# Stage-4 unit tier (B2e + A1, A2) for dfs.client.socketcache.capacity-putInternal-capacity--autonomous.
# Run on the stage-4 node:  unit-run.sh <R> <harness-dir>
# Logs every command and its output to <R>/logs/unit/unit-run.log; per-run surefire output to <R>/logs/unit/.
set -uo pipefail
R=${1:?R}; HD=${2:?harness dir}
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64 PATH=/usr/lib/jvm/java-8-openjdk-amd64/bin:$PATH YARN_IGNORE_ENGINES=true
ulimit -n 65536
L=$R/logs/unit; mkdir -p "$L"; LOG=$L/unit-run.log
run() { echo "+ $*" | tee -a "$LOG"; "$@" 2>&1 | tee -a "$LOG"; return ${PIPESTATUS[0]}; }
echo "=== unit-run start $(date -Is) host=$(hostname) ulimit-n=$(ulimit -n)" | tee -a "$LOG"
run java -version
run mvn -version
run md5sum "$HD/TestPeerCacheCapacityProbe.java" "$0"
T=$R/src/hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs
run cp "$HD/TestPeerCacheCapacityProbe.java" "$T/"
run git -C "$R/src" status --short
M=$R/src/hadoop-hdfs-project/hadoop-hdfs
cd "$M" || exit 1
SR=$M/target/surefire-reports
OUT=$L/histo; mkdir -p "$OUT"
one() {  # one Maven invocation = one fresh surefire JVM
  local test=$1 tag=$2 C=$3 REP=$4
  rm -rf "$SR"
  echo "--- $tag start $(date -Is)" | tee -a "$LOG"
  run mvn -B -o test -Dtest="TestPeerCacheCapacityProbe#$test" -DfailIfNoTests=false -Dmaven.javadoc.skip=true \
      -Dmaven-surefire-plugin.argLine="-Xmx2g -XX:+UseSerialGC -Dprobe.capacity=$C -Dprobe.rep=$REP -Dprobe.out=$OUT" \
      > "$L/mvn-$tag.log" 2>&1
  echo "mvn exit $? ($tag)" | tee -a "$LOG"
  grep -E "Tests run:|BUILD|ERROR" "$L/mvn-$tag.log" | head -8 | tee -a "$LOG"
  cp "$SR/org.apache.hadoop.hdfs.TestPeerCacheCapacityProbe-output.txt" "$L/output-$tag.txt" 2>/dev/null
  cp "$SR/TEST-org.apache.hadoop.hdfs.TestPeerCacheCapacityProbe.xml" "$L/TEST-$tag.xml" 2>/dev/null
  grep -hE "^(PART|HISTO)" "$L/output-$tag.txt" | tee -a "$LOG"
  rm -rf "$M/target/test/data"
  echo "--- $tag end $(date -Is); leftover surefire JVMs: $(ps -eo cmd | grep -c '[s]urefirebooter')" | tee -a "$LOG"
}
one operandBound part1 16 1
for REP in 1 2; do for C in 0 16 256 1024; do one realPeers "part2-C$C-r$REP" $C $REP; done; done
echo "--- PART lines" | tee -a "$LOG"
grep -hE "^PART" "$L"/output-*.txt | tee "$L/part-lines.txt" | tee -a "$LOG"
grep -hE "^HISTO" "$L"/output-*.txt > "$L/histo-lines.txt"
echo "=== unit-run end $(date -Is)" | tee -a "$LOG"
