#!/usr/bin/env bash
# Unit tier (case-file B2e, amended A1-A6) for RawPathHandle_MAX_SIZE-readObject-MAX_SIZE--autonomous.
# Usage: unit-run.sh <run-dir> [--compile-only]   (<run-dir>/src made by jingsong/copy-source.sh)
# Arms D (as shipped), K16 (MAX_SIZE = 1<<16), K24 (1<<24), in that order, in the same copy; the patch
# is undone after each arm. Logs every command to <run-dir>/logs/unit/unit-run.log; stops at the first
# failed step; reads surefire counts (the build returns 0 on failing tests).
set -euo pipefail
RUN=${1:?usage: unit-run.sh <run-dir> [--compile-only]}
MODE=${2:-}
HERE=$(cd "$(dirname "$0")" && pwd)
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
export PATH=$JAVA_HOME/bin:$PATH
SRC=$RUN/src
MOD=$SRC/hadoop-common-project/hadoop-common
RPH=$MOD/src/main/java/org/apache/hadoop/fs/RawPathHandle.java
OUT=$RUN/logs/unit
mkdir -p "$OUT"
LOG=$OUT/unit-run.log
exec > >(tee -a "$LOG") 2>&1
step(){ echo "+ [$(date '+%F %T')] $*"; "$@"; }
leftover(){ ps -eo pid,cmd | grep -E '[s]urefire' | grep -F "$RUN" || true; }
restore(){ git -C "$SRC" checkout -- "$RPH" 2>/dev/null || true; }
trap 'rc=$?; restore; echo "EXIT rc=$rc at $(date "+%F %T")"; echo "git status of the copy:"; git -C "$SRC" status --short; echo "leftover surefire JVMs of this run:"; leftover' EXIT

echo "=== unit-run.sh $(date '+%F %T') on $(hostname) mode=${MODE:-run}"
step java -version
step mvn -version
step git -C "$SRC" describe --tags
step cp "$HERE/TestRawPathHandleMaxSize.java" "$MOD/src/test/java/org/apache/hadoop/fs/"
step md5sum "$HERE/TestRawPathHandleMaxSize.java" "$HERE/unit-run.sh" "$HERE/analyze.py"
step git -C "$SRC" status --short
cd "$MOD"

if [ "$MODE" = "--compile-only" ]; then
  step mvn -B test-compile -Dmaven.javadoc.skip=true > "$OUT/compile.log" 2>&1 || { tail -40 "$OUT/compile.log"; echo "STOP: test-compile failed"; exit 1; }
  grep -E "BUILD SUCCESS|BUILD FAILURE" "$OUT/compile.log"
  ls -l target/test-classes/org/apache/hadoop/fs/TestRawPathHandleMaxSize*.class
  exit 0
fi

cat <<'X'
EXPECTED (A4, frozen): every RawPathHandle row: 0<=len<=M -> object x25, remaining=len, content true, med-b in [len, len+4096];
EXPECTED: else IOException "Illegal buffer length <len>" x25, med-b < 65536, max-b < 1048576, no OOM. Largest accepted = M per arm.
EXPECTED (A6): C5 object med-b >= 16777216; C8 EOFException med-b >= 67108864; C9 OOM Java heap space; C6 OOM; C8 >= 1000 x L8.
X

run_arm(){ # arm k M expectedSkipped
  local arm=$1 k=$2 M=$3 skip=$4
  echo "=== arm $arm (MAX_SIZE = 1 << $k = $M) $(date '+%F %T')"
  if [ "$k" != 20 ]; then
    step sed -i "s/MAX_SIZE = 1 << 20;/MAX_SIZE = 1 << $k;/" "$RPH"
  fi
  step git -C "$SRC" diff --stat
  git -C "$SRC" diff -- "$RPH" | grep '^[-+] ' || echo "(RawPathHandle.java unchanged)"
  grep -n 'MAX_SIZE = ' "$RPH"
  set +e
  step mvn -B test -Dtest=TestRawPathHandleMaxSize -DfailIfNoTests=false -Dmaven.javadoc.skip=true \
    "-Dmaven-surefire-plugin.argLine=-Xmx256m -XX:+UseSerialGC -Difchk.arm=$arm -Difchk.max=$M" > "$OUT/mvn-test-$arm.log" 2>&1
  local rc=$?
  set -e
  echo "mvn rc=$rc"
  grep -E "Tests run:|BUILD SUCCESS|BUILD FAILURE" "$OUT/mvn-test-$arm.log" | tail -4
  cp target/surefire-reports/org.apache.hadoop.fs.TestRawPathHandleMaxSize-output.txt "$OUT/surefire-output-$arm.txt"
  cp target/surefire-reports/org.apache.hadoop.fs.TestRawPathHandleMaxSize.txt "$OUT/surefire-$arm.txt"
  grep -a '^IFCHK' "$OUT/surefire-output-$arm.txt" > "$OUT/ifchk-$arm.csv" || true
  cat "$OUT/ifchk-$arm.csv"
  grep -q '^IFCHK,instr,' "$OUT/ifchk-$arm.csv" || { echo "STOP: no instrument line in arm $arm"; exit 2; }
  [ "$rc" -eq 0 ] || { echo "STOP: mvn failed (rc=$rc) in arm $arm"; tail -40 "$OUT/mvn-test-$arm.log"; exit 3; }
  grep -q "Tests run: 4, Failures: 0, Errors: 0, Skipped: $skip" "$OUT/surefire-$arm.txt" || {
    echo "STOP: surefire counts in arm $arm are not 4/0/0/$skip (validity assertion failed: invalid run)"; cat "$OUT/surefire-$arm.txt" | head -40; exit 4; }
  restore
  step git -C "$SRC" diff --stat
}

run_arm D 20 1048576 0
run_arm K16 16 65536 2
run_arm K24 24 16777216 2
cat "$OUT"/ifchk-D.csv "$OUT"/ifchk-K16.csv "$OUT"/ifchk-K24.csv > "$OUT/ifchk-all.csv"
step python3 -I "$HERE/analyze.py" unit "$OUT/ifchk-all.csv" | tee "$OUT/analysis.txt"
echo "=== done $(date '+%F %T')"
