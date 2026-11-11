#!/usr/bin/env bash
# Unit tier (case-file B2, amended A1-A3) for
# fs.s3a.prefetch.max.blocks.count-addToLinkedListAndEvictIfRequired-maxBlocksCount--autonomous.
# Usage: unit-run.sh <run-dir> [--compile-only]   (<run-dir>/src from copy-source.sh)
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
PKG=$MOD/src/test/java/org/apache/hadoop/fs/impl/prefetch
OUT=$RUN/logs/unit
TMPD=$RUN/tmp-unit
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
step cp "$HERE/TestBlockCacheLruCap.java" "$PKG/"
step md5sum "$HERE/TestBlockCacheLruCap.java" "$HERE/unit-run.sh"
step git -C "$SRC" status --short
cd "$MOD"
ARGLINE="-Xmx1024m -Difchk.tmp=$TMPD"

if [ "$MODE" = "--compile-only" ]; then
  step mvn -B test-compile -Dmaven.javadoc.skip=true > "$OUT/compile.log" 2>&1 || { tail -40 "$OUT/compile.log"; echo "STOP: test-compile failed"; exit 1; }
  grep -E "BUILD SUCCESS|BUILD FAILURE" "$OUT/compile.log"
  ls -l target/test-classes/org/apache/hadoop/fs/impl/prefetch/TestBlockCacheLruCap.class
  exit 0
fi

cat <<'EOF'
EXPECTED (B2f, frozen): files after put b = min(b+1,max); after 20 puts files = max (1000: 20), bytes = files x 1048576;
EXPECTED: peak in put = max+1 (1000: 20); evictions = 20-max (1000: 0); cacheSize == files == entryListSize; files after close 0
EXPECTED: LRU (max 4): containsBlock(0)=true, containsBlock(1)=false
EXPECTED: bypass (max 2): put2 ~5000 ms, files 3, cacheSize 3, evictions 0, entryListSize 3; after puts 3,4: files 3, entryListSize 3, evictions 2, containsBlock(0) true; close 0
EOF

set +e
step mvn -B test -Dtest=TestBlockCacheLruCap -DfailIfNoTests=false \
  "-Dmaven-surefire-plugin.argLine=$ARGLINE" > "$OUT/mvn-test-ifchk.log" 2>&1
rc=$?
set -e
echo "mvn rc=$rc"
grep -E "Tests run:|BUILD SUCCESS|BUILD FAILURE" "$OUT/mvn-test-ifchk.log" | tail -5
cp target/surefire-reports/*TestBlockCacheLruCap* "$OUT/" 2>/dev/null || true
OUTF=$(ls "$OUT"/*TestBlockCacheLruCap-output.txt 2>/dev/null | head -1 || true)
[ -n "$OUTF" ] || OUTF=$OUT/mvn-test-ifchk.log
echo "IFCHK source: $OUTF"
grep -a '^IFCHK' "$OUTF" > "$OUT/ifchk.csv" || true
grep -q '^IFCHK,instr,' "$OUT/ifchk.csv" || { echo "STOP: no IFCHK,instr line (test did not run)"; tail -60 "$OUT/mvn-test-ifchk.log"; exit 2; }
[ "$rc" -eq 0 ] || { echo "STOP: mvn test failed (rc=$rc)"; exit 3; }
if ! grep -q "Tests run: 3, Failures: 0, Errors: 0, Skipped: 0" "$OUT/mvn-test-ifchk.log"; then
  echo "STOP: a test failed or errored"
  grep -A8 "<<< FAILURE\|<<< ERROR" "$OUT"/*TestBlockCacheLruCap*.txt 2>/dev/null | head -40 || true
  exit 4
fi
echo "rows: cap=$(grep -c '^IFCHK,cap,' "$OUT/ifchk.csv") close=$(grep -c '^IFCHK,close,' "$OUT/ifchk.csv") lru=$(grep -c '^IFCHK,lru,' "$OUT/ifchk.csv") bypass=$(grep -c '^IFCHK,bypass,' "$OUT/ifchk.csv")"
grep -a "deletion would not be attempted" "$OUTF" > "$OUT/lock-timeout-errors.txt" || true
echo "lock-timeout ERROR lines: $(wc -l < "$OUT/lock-timeout-errors.txt")"
step ls -la "$TMPD"
step rm -f "$PKG/TestBlockCacheLruCap.java"
step git -C "$SRC" status --short
echo "=== done $(date '+%F %T')"
