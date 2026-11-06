#!/usr/bin/env bash
# Unit tier (case-file B2e, amended A1-A6) for MAX_KEY_SIZE-write-limit--autonomous.
# Usage: unit-run.sh <run-dir>                  (e.g. /mydata/jingsong-s4/MAX_KEY_SIZE-write-limit-run1; <run-dir>/src from copy-source.sh)
#        unit-run.sh <run-dir> --compile-only   (instrument check: copy + test-compile, no test run)
# Logs every command and its output to <run-dir>/logs/unit/unit-run.log; stops at the first failed step;
# reads surefire counts (the build returns 0 on test failures); reports any surefire JVM left behind.
set -euo pipefail
RUN=${1:?usage: unit-run.sh <run-dir> [--compile-only]}
MODE=${2:-}
HERE=$(cd "$(dirname "$0")" && pwd)
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
export PATH=$JAVA_HOME/bin:$PATH
SRC=$RUN/src
MOD=$SRC/hadoop-common-project/hadoop-common
PKG=$MOD/src/test/java/org/apache/hadoop/io
OUT=$RUN/logs/unit
TMPD=$RUN/tmp
mkdir -p "$OUT" "$TMPD"
LOG=$OUT/unit-run.log
exec > >(tee -a "$LOG") 2>&1
step(){ echo "+ [$(date '+%F %T')] $*"; "$@"; }
leftover(){ ps -eo pid,cmd | grep -E '[s]urefire' | grep -F "$RUN" || true; }
trap 'rc=$?; echo "EXIT rc=$rc at $(date "+%F %T")"; echo "leftover surefire JVMs of this run:"; leftover' EXIT

echo "=== unit-run.sh $(date '+%F %T') on $(hostname) mode=${MODE:-run}"
step java -version
step mvn -version
step git -C "$SRC" describe --tags
step cp "$HERE/TestBoundedLimitHeap.java" "$PKG/"
step md5sum "$HERE/TestBoundedLimitHeap.java" "$HERE/unit-run.sh"
step git -C "$SRC" status --short
cd "$MOD"
ARGLINE="-Xmx512m -XX:+UseSerialGC -Difchk.tmp=$TMPD"

if [ "$MODE" = "--compile-only" ]; then
  step mvn -B test-compile -Dmaven.javadoc.skip=true > "$OUT/compile.log" 2>&1 || { tail -40 "$OUT/compile.log"; echo "STOP: test-compile failed"; exit 1; }
  grep -E "BUILD SUCCESS|BUILD FAILURE" "$OUT/compile.log"
  ls -l target/test-classes/org/apache/hadoop/io/TestBoundedLimitHeap.class
  exit 0
fi

cat <<'EOF'
EXPECTED (B2f + A4, frozen): per (C,L): failIndex=L+1, sizeAtFail=L, exceptions=102400, badPasses=0, bufIdentitySame=true, bufLength=C
EXPECTED: C <= allocCtor <= C+256; allocInPerPass < 1024 and residualPerPass < 1024 (flat); retainedDelta in C +- 1 MiB; |retainedLoop| <= 1 MiB
EXPECTED: refuted if (C=16MiB) value at L=16MiB exceeds value at L=1024 by > 167762 B/pass, or allocInPerPass >= 1% of L (L >= 512KiB), or retainedLoop > 1 MiB, or identity changes
EXPECTED: TFile writeByte fails at 65537 (size 65536), decl100 at 101, writeInt at 16385; loop alloc - excCost < 1024; allocWriter >= 131072
EXPECTED (A5): control W <= allocPerPass <= 4W+1024 every row; row W=16MiB+1024 > 1000 x row W=2048
EOF

# 1. The case's test (B2e step 2)
set +e
step mvn -B test -Dtest=TestBoundedLimitHeap -DfailIfNoTests=false \
  "-Dmaven-surefire-plugin.argLine=$ARGLINE" > "$OUT/mvn-test-ifchk.log" 2>&1
rc=$?
set -e
echo "mvn rc=$rc"
grep -E "Tests run:|BUILD SUCCESS|BUILD FAILURE" "$OUT/mvn-test-ifchk.log" | tail -5
cp target/surefire-reports/*TestBoundedLimitHeap* "$OUT/" 2>/dev/null || true
OUTF=$(ls "$OUT"/*TestBoundedLimitHeap-output.txt 2>/dev/null | head -1 || true)
[ -n "$OUTF" ] || OUTF=$OUT/mvn-test-ifchk.log
echo "IFCHK source: $OUTF"
grep -a '^IFCHK' "$OUTF" > "$OUT/ifchk.csv" || true
# First-trigger check: the instrument line and at least one direct row exist.
grep -q '^IFCHK,instr,' "$OUT/ifchk.csv" || { echo "STOP: no IFCHK,instr line (test did not run)"; tail -60 "$OUT/mvn-test-ifchk.log"; exit 2; }
[ "$rc" -eq 0 ] || { echo "STOP: mvn test failed (rc=$rc)"; exit 3; }
if ! grep -q "Tests run: 3, Failures: 0, Errors: 0, Skipped: 0" "$OUT/mvn-test-ifchk.log"; then
  echo "STOP: a test failed or errored (A6: invalid run)"
  grep -A5 "<<< FAILURE\|<<< ERROR" "$OUT"/*TestBoundedLimitHeap*.txt 2>/dev/null | head -30 || true
  exit 4
fi
nd=$(grep -c '^IFCHK,direct,[0-9]' "$OUT/ifchk.csv"); nt=$(grep -c '^IFCHK,tfile,write' "$OUT/ifchk.csv"); nc=$(grep -c '^IFCHK,control,[BD]' "$OUT/ifchk.csv")
echo "rows: direct=$nd tfile=$nt control=$nc"
[ "$nd" -eq 9 ] && [ "$nt" -eq 3 ] && [ "$nc" -eq 18 ] || { echo "STOP: wrong row counts"; exit 5; }
# The surefire JVM options really applied (A1): max heap ~512 MiB, Serial GC ("Copy").
grep '^IFCHK,instr,' "$OUT/ifchk.csv"

# 2. The existing tests (B2e step 2, second command)
set +e
step mvn -B test -Dtest=TestBoundedByteArrayOutputStream,TestTFileStreams -DfailIfNoTests=false \
  "-Dmaven-surefire-plugin.argLine=$ARGLINE" > "$OUT/mvn-test-existing.log" 2>&1
rc=$?
set -e
echo "mvn rc=$rc"
grep -E "Tests run:|BUILD SUCCESS|BUILD FAILURE" "$OUT/mvn-test-existing.log" | tail -6
cp target/surefire-reports/*TestBoundedByteArrayOutputStream.txt target/surefire-reports/*TestTFileStreams.txt "$OUT/" 2>/dev/null || true
grep -qE "Tests run: [0-9]+, Failures: 0, Errors: 0, Skipped: [0-9]+$" <(grep -E "^\[(INFO|WARNING|ERROR)\] Tests run:" "$OUT/mvn-test-existing.log" | tail -1) \
  || { echo "STOP: existing tests failed (A6: invalid run)"; exit 6; }

# 3. Cleanup (B2e step 4)
step ls -la "$TMPD"
step rm -rf "$TMPD"/tfile-*
echo "=== done $(date '+%F %T')"
