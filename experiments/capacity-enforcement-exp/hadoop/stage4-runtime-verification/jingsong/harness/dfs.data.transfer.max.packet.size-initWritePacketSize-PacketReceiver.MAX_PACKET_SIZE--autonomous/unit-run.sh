#!/usr/bin/env bash
# Unit tier (case-file B2e, amended A1-A3, 2026-11-25) for
# dfs.data.transfer.max.packet.size-initWritePacketSize-PacketReceiver.MAX_PACKET_SIZE--autonomous.
# Usage (on the node): unit-run.sh <run-dir> [--compile-only]
#   <run-dir>/src from copy-source.sh; <run-dir>/harness holds this folder.
# Logs every command and its output to <run-dir>/logs/unit/unit-run.log; stops at the first failed step;
# reads surefire counts (the build returns 0 on test failures); reports any surefire JVM left behind.
set -euo pipefail
RUN=${1:?usage: unit-run.sh <run-dir> [--compile-only]}
MODE=${2:-}
HERE=$(cd "$(dirname "$0")" && pwd)
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
export PATH=$JAVA_HOME/bin:$PATH
SRC=$RUN/src
MOD=$SRC/hadoop-hdfs-project/hadoop-hdfs
PKG=$MOD/src/test/java/org/apache/hadoop/hdfs
RES=$MOD/src/test/resources
OUT=$RUN/logs/unit
mkdir -p "$OUT"
LOG=$OUT/unit-run.log
exec > >(tee -a "$LOG") 2>&1
step(){ echo "+ [$(date '+%F %T')] $*"; "$@"; }
leftover(){ ps -eo pid,cmd | grep -E '[s]urefire' | grep -F "$RUN" || true; }
trap 'rc=$?; echo "EXIT rc=$rc at $(date "+%F %T")"; echo "leftover surefire JVMs of this run:"; leftover' EXIT

echo "=== unit-run.sh $(date '+%F %T') on $(hostname) mode=${MODE:-run}"
step java -version
step mvn -version
step git -C "$SRC" describe --tags
step cp "$HERE/WritePacketCapRunner.java" "$HERE/TestWritePacketSizeCap.java" "$HERE/TestWritePacketSizeCap4M.java" "$PKG/"
step cp "$HERE/maxpkt-4m-site.xml" "$RES/"
step md5sum "$HERE"/*.java "$HERE/maxpkt-4m-site.xml" "$HERE/unit-run.sh"
step git -C "$SRC" status --short
cd "$SRC"

if [ "$MODE" = "--compile-only" ]; then
  step mvn -B -o -pl hadoop-hdfs-project/hadoop-hdfs test-compile -Dmaven.javadoc.skip=true > "$OUT/compile.log" 2>&1 \
    || { tail -40 "$OUT/compile.log"; echo "STOP: test-compile failed"; exit 1; }
  grep -E "BUILD SUCCESS|BUILD FAILURE" "$OUT/compile.log"
  ls -l "$MOD"/target/test-classes/org/apache/hadoop/hdfs/TestWritePacketSize*.class "$MOD"/target/test-classes/maxpkt-4m-site.xml
  exit 0
fi

cat <<'EXP'
EXPECTED (B2f, frozen): MAX=16777216:
  C=65536     wps=65536    ps0=65016     firstBuf=65049     alloc~65KB   second=65049    small ok big ok
  C=16777216  wps=16777216 ps0=16776708  firstBuf=16776741  alloc~16.78MB second=16776741 small ok big ok
  C=33554432  wps=16777216 ps0=33553932  firstBuf=33553965  alloc~33.55MB second=16776741 small ok big FAILS (DN "Incorrect value for packet payload size")
  C=268435456 wps=16777216 ps0=268435068 firstBuf=268435101 alloc~268.4MB second=none    small ok big FAILS at close
MAX=4194304:
  C=4194304   wps=4194304  ps0=4194048   firstBuf=4194081   alloc~4.19MB second=4194081 small ok big ok
  C=8388608   wps=4194304  ps0=8388096   firstBuf=8388129   alloc~8.39MB second=4194081 small ok big FAILS
WARN "Configured write packet exceeds" exactly when C > MAX.
EXP

for T in TestWritePacketSizeCap TestWritePacketSizeCap4M; do
  set +e
  step mvn -B -o -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=$T -DfailIfNoTests=false -Dmaven.javadoc.skip=true > "$OUT/mvn-test-$T.log" 2>&1
  rc=$?
  set -e
  echo "mvn rc=$rc ($T)"
  grep -E "Tests run:|BUILD SUCCESS|BUILD FAILURE" "$OUT/mvn-test-$T.log" | tail -4
  cp "$MOD"/target/surefire-reports/*$T.txt "$MOD"/target/surefire-reports/*$T-output.txt "$MOD"/target/surefire-reports/TEST-*$T.xml "$OUT/" 2>/dev/null || true
  OUTF=$OUT/org.apache.hadoop.hdfs.$T-output.txt
  [ -f "$OUTF" ] || { echo "STOP: no surefire output file for $T"; tail -60 "$OUT/mvn-test-$T.log"; exit 2; }
  grep -a '^IFCHK' "$OUTF" > "$OUT/ifchk-$T.csv" || true
  cat "$OUT/ifchk-$T.csv"
  # per-test counts of the client WARN (g) and DataNode refusal (f), between BEGIN/END markers
  python3 -I - "$OUTF" <<'PY' | tee "$OUT/logcounts-$T.txt"
import sys,re
cur=None; cnt={}
for line in open(sys.argv[1],errors='replace'):
    m=re.match(r'IFCHK,BEGIN,C=(\d+)',line)
    if m: cur=m.group(1); cnt[cur]=[0,0]; continue
    if line.startswith('IFCHK,END'): cur=None; continue
    if cur is None: continue
    if 'Configured write packet exceeds' in line: cnt[cur][0]+=1
    if 'Incorrect value for packet payload size' in line: cnt[cur][1]+=1
for c,(w,d) in cnt.items(): print(f"LOGCOUNT,C={c},clientWarn={w},dnIncorrectPayloadLines={d}")
PY
  grep -E "Tests run: [0-9]+, Failures: 0, Errors: 0" "$OUT/org.apache.hadoop.hdfs.$T.txt" \
    || { echo "STOP: a test of $T failed or errored (invalid run)"; grep -A8 "<<< FAILURE\|<<< ERROR" "$OUT/org.apache.hadoop.hdfs.$T.txt" | head -40; exit 3; }
done
echo "=== done $(date '+%F %T')"
