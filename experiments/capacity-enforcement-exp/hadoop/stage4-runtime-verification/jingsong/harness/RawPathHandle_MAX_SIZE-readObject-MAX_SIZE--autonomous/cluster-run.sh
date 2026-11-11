#!/usr/bin/env bash
# Cluster tier (case-file B3 as amended by A7) for RawPathHandle_MAX_SIZE-readObject-MAX_SIZE--autonomous.
# The shipped distribution jar via `hadoop jar`, no daemons, no ports. Usage: cluster-run.sh <run-dir> [--check]
# --check: copy the distribution, compile the probe, one known-answer read (R1 with N=10), then stop.
set -euo pipefail
RUN=${1:?usage: cluster-run.sh <run-dir> [--check]}
MODE=${2:-}
HERE=$(cd "$(dirname "$0")" && pwd)
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
export PATH=$JAVA_HOME/bin:$PATH
DIST=/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2
export HADOOP_HOME=$RUN/hadoop
export HADOOP_CONF_DIR=$HADOOP_HOME/etc/hadoop
OUT=$RUN/logs/cluster
export HADOOP_LOG_DIR=$OUT HADOOP_PID_DIR=$RUN/pids
P=$RUN/probe
mkdir -p "$OUT" "$RUN/pids" "$RUN/tmp" "$P"
LOG=$OUT/cluster-run.log
exec > >(tee -a "$LOG") 2>&1
step(){ echo "+ [$(date '+%F %T')] $*"; "$@"; }
leftover(){ ps -eo pid,cmd | grep -E '[R]awPathHandleProbe' || true; }
trap 'rc=$?; echo "EXIT rc=$rc at $(date "+%F %T")"; echo "leftover probe JVMs:"; leftover' EXIT

echo "=== cluster-run.sh $(date '+%F %T') on $(hostname) mode=${MODE:-run}"
step java -version
step md5sum "$HERE/RawPathHandleProbe.java" "$HERE/cluster-run.sh" "$HERE/analyze.py"
if [ ! -d "$HADOOP_HOME" ]; then step cp -a "$DIST" "$HADOOP_HOME"; fi
step "$HADOOP_HOME/bin/hadoop" version
JAR=$HADOOP_HOME/share/hadoop/common/hadoop-common-3.4.2.jar
step md5sum "$JAR" "$DIST/share/hadoop/common/hadoop-common-3.4.2.jar"
# The shipped class has the check: bytecode of readObject compares with 1048576 (ldc) before newarray.
( cd "$RUN/tmp" && unzip -o -q "$JAR" org/apache/hadoop/fs/RawPathHandle.class && javap -c -p -constants org/apache/hadoop/fs/RawPathHandle.class | sed -n '/void readObject(java.io.ObjectInputStream)/,/return$/p' ) > "$OUT/javap-readObject.txt"
cat "$OUT/javap-readObject.txt"
step cp "$HERE/RawPathHandleProbe.java" "$P/"
mkdir -p "$P/classes"
step javac -cp "$JAR" -d "$P/classes" "$P/RawPathHandleProbe.java"
step jar cf "$P/probe.jar" -C "$P/classes" .
H=$HADOOP_HOME/bin/hadoop
write(){ HADOOP_HEAPSIZE_MAX=512m HADOOP_OPTS="-Djava.io.tmpdir=$RUN/tmp" step "$H" jar "$P/probe.jar" RawPathHandleProbe write "$@"; }
read1(){ # id file N keep
  HADOOP_HEAPSIZE_MAX=128m HADOOP_OPTS="-Xloggc:$OUT/gc-$1.log -XX:+PrintGCDetails -XX:+PrintGCDateStamps -Djava.io.tmpdir=$RUN/tmp" \
    step timeout 600 "$H" jar "$P/probe.jar" RawPathHandleProbe read "$@" | tee -a "$OUT/probe-results.csv"
}
write raw g 1024 "$P/s-R1.bin"
if [ "$MODE" = "--check" ]; then read1 CHK "$P/s-R1.bin" 10 keep; exit 0; fi
: > "$OUT/probe-results.csv"
write raw g 1048576 "$P/s-R3.bin"
write raw g 1048577 "$P/s-R4.bin"
write raw g 16777216 "$P/s-R5.bin"
write raw p 2147483647 "$P/s-R6.bin"
write ctl g 16777216 "$P/s-X5.bin"
write ctl p 536870912 "$P/s-X9.bin"
write ctl p 2147483647 "$P/s-X6.bin"
step ls -l "$P"
read1 R1 "$P/s-R1.bin" 1000 keep
read1 R3 "$P/s-R3.bin" 1000 drop
read1 R4 "$P/s-R4.bin" 1000 drop
read1 R5 "$P/s-R5.bin" 1000 drop
read1 R6 "$P/s-R6.bin" 1000 drop
read1 X5 "$P/s-X5.bin" 1000 drop
read1 X9 "$P/s-X9.bin" 1000 drop
read1 X6 "$P/s-X6.bin" 1000 drop
step python3 -I "$HERE/analyze.py" cluster "$OUT/probe-results.csv" | tee "$OUT/analysis.txt"
step rm -f "$P"/s-*.bin
step ls -la /tmp | grep -i -E 'hadoop-unjar|jason92' || true
echo "=== done $(date '+%F %T')"
