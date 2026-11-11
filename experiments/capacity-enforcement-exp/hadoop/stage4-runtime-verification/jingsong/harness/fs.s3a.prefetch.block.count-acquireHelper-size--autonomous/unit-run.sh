#!/usr/bin/env bash
# Unit tier (case-file B2e, amended A1-A4) for fs.s3a.prefetch.block.count-acquireHelper-size--autonomous.
# Usage: unit-run.sh <run-dir>                  (<run-dir>/src made by ../../copy-source.sh)
#        unit-run.sh <run-dir> --compile-only   (instrument check: copy + test-compile, no test run)
# Logs every command and its output to <run-dir>/logs/unit/unit-run.log; stops at the first failed step; reads surefire
# counts (the build returns 0 on test failures); reports any surefire JVM of this run left behind.
set -euo pipefail
RUN=${1:?usage: unit-run.sh <run-dir> [--compile-only]}
MODE=${2:-}
HERE=$(cd "$(dirname "$0")" && pwd)
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
export PATH=$JAVA_HOME/bin:$PATH
SRC=$RUN/src
MOD=$SRC/hadoop-tools/hadoop-aws
PKG=$MOD/src/test/java/org/apache/hadoop/fs/s3a/prefetch
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
step cp "$HERE/TestPrefetchPoolBound.java" "$PKG/"
step md5sum "$HERE/TestPrefetchPoolBound.java" "$HERE/unit-run.sh"
step git -C "$SRC" status --short
cd "$MOD"

if [ "$MODE" = "--compile-only" ]; then
  step mvn -B test-compile -Dmaven.javadoc.skip=true > "$OUT/compile.log" 2>&1 || { tail -40 "$OUT/compile.log"; echo "STOP: test-compile failed"; exit 1; }
  grep -E "BUILD SUCCESS|BUILD FAILURE" "$OUT/compile.log"
  ls -l target/test-classes/org/apache/hadoop/fs/s3a/prefetch/TestPrefetchPoolBound*.class
  exit 0
fi

cat <<'EOF'
EXPECTED (B2f + A4, frozen): per count c in {1,2,4,8,16}: printedSize = poolSize = c+1; seqMax = hookMax = c+1; rndMax <= c+1
EXPECTED: denialsAtFull == rndDenials; rndDenials >= 1 for at least one c; rndMismatches = 0; crcSeq equal for all c
EXPECTED: heap D(c)=heapPeak-heapBefore; D(c)-D(1) = (c-1) MiB +- 4 MiB; heapPeak-heapAfter >= (c+1) MiB - 4 MiB
EXPECTED: controls: inmemory hasCreated=false, bytes=524288; count0 rejected by PrefetchOptions and intOption
EOF

set +e
step mvn -B test -Dtest=TestPrefetchPoolBound -DfailIfNoTests=false > "$OUT/mvn-test.log" 2>&1
rc=$?
set -e
echo "mvn rc=$rc"
grep -E "Tests run:|BUILD SUCCESS|BUILD FAILURE" "$OUT/mvn-test.log" | tail -5
cp target/surefire-reports/*TestPrefetchPoolBound* "$OUT/" 2>/dev/null || true
OUTF=$(ls "$OUT"/*TestPrefetchPoolBound-output.txt 2>/dev/null | head -1 || true)
[ -n "$OUTF" ] || OUTF=$OUT/mvn-test.log
echo "IFCHK source: $OUTF"
grep -a '^IFCHK' "$OUTF" > "$OUT/ifchk.csv" || true
cat "$OUT/ifchk.csv"
[ "$rc" -eq 0 ] || { echo "STOP: mvn test failed (rc=$rc)"; exit 3; }
grep -q "Tests run: 6, Failures: 0, Errors: 0, Skipped: 0" "$OUT/mvn-test.log" || { echo "STOP: a test failed or errored (A4 (i): invalid run)"; grep -A8 "<<< FAILURE\|<<< ERROR" "$OUT"/*TestPrefetchPoolBound.txt 2>/dev/null | head -40 || true; exit 4; }
n=$(grep -c '^IFCHK,count,' "$OUT/ifchk.csv"); c=$(grep -c '^IFCHK-CTL,' "$OUT/ifchk.csv")
echo "rows: count=$n ctl=$c"
[ "$n" -eq 5 ] && [ "$c" -eq 2 ] || { echo "STOP: wrong row counts"; exit 5; }
echo "=== done $(date '+%F %T')"
