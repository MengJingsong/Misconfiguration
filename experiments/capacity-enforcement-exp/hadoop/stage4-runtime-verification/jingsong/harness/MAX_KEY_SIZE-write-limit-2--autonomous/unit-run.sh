#!/usr/bin/env bash
# Unit tier (case-file B2e, with the 2026-11-25 audit amendments) for MAX_KEY_SIZE-write-limit-2--autonomous.
# Runs ON THE NODE. Usage: unit-run.sh <run-dir> [--compile-only]
#   <run-dir>/src is the per-run source copy made by copy-source.sh; the harness is in <run-dir>/harness.
# Logs every command and its output to <run-dir>/logs/unit/unit-run.log; stops at the first failed step;
# reads surefire counts (the build returns 0 on test failures); reports any surefire JVM left behind.
set -euo pipefail
RUN=${1:?usage: unit-run.sh <run-dir> [--compile-only]}
MODE=${2:-}
HERE=$RUN/harness
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
step cp "$HERE/TestBoundedLimitMemory.java" "$PKG/"
step md5sum "$HERE/TestBoundedLimitMemory.java" "$HERE/unit-run.sh"
cd "$MOD"
# Module surefire defaults (case B2a: "add nothing else") plus only the scratch-dir property.
ARGLINE="-Xmx2048m -XX:+HeapDumpOnOutOfMemoryError -Difchk.tmp=$TMPD"

if [ "$MODE" = "--compile-only" ]; then
  step mvn -B test-compile -Dmaven.javadoc.skip=true > "$OUT/compile.log" 2>&1 || { tail -40 "$OUT/compile.log"; echo "STOP: test-compile failed"; exit 1; }
  grep -E "BUILD SUCCESS|BUILD FAILURE" "$OUT/compile.log"
  ls -l target/test-classes/org/apache/hadoop/io/TestBoundedLimitMemory.class
  exit 0
fi

cat <<'EOF'
EXPECTED (B2f, frozen 2026-11-25):
 U1 lim 1024/32768/65536: writes 1/32/65, size 1000/32000/65000, msg "Reach the limit of the buffer", frame BoundedByteArrayOutputStream.write:92
 U2 cap 1 MiB: ctorAlloc ~1048576+~50 at all three lim, equal within +-1 KiB; writeAlloc < 4096
 U3 cap 64Ki/1Mi/16Mi: ctorAlloc follows cap within +-1 KiB; U3b alloc >= 204800 (~2x 262144)
 U4 prepareAppendKey(-1): 64 writes ok, 65th EOFException at write:92; Writer ctorAlloc >= 131104; writeAlloc < 8192; prepareAppendKey(65537) -> IndexOutOfBoundsException
 U5 (amended A3): fileLength ~ (2N+1) x 65,5xx + < 4 KiB (~197 KB / ~1.38 MB / ~13.2 MB); linear in N
EOF

set +e
step mvn -B test -Dtest=TestBoundedLimitMemory -DfailIfNoTests=false \
  "-Dmaven-surefire-plugin.argLine=$ARGLINE" > "$OUT/mvn-test-ifchk.log" 2>&1
rc=$?
set -e
echo "mvn rc=$rc"
grep -E "Tests run:|BUILD SUCCESS|BUILD FAILURE" "$OUT/mvn-test-ifchk.log" | tail -5
cp target/surefire-reports/*TestBoundedLimitMemory* "$OUT/" 2>/dev/null || true
OUTF=$(ls "$OUT"/*TestBoundedLimitMemory-output.txt 2>/dev/null | head -1 || true)
[ -n "$OUTF" ] || OUTF=$OUT/mvn-test-ifchk.log
echo "IFCHK source: $OUTF"
grep -a '^IFCHK' "$OUTF" > "$OUT/ifchk.csv" || true
cat "$OUT/ifchk.csv"
grep -q '^IFCHK,instr,' "$OUT/ifchk.csv" || { echo "STOP: no IFCHK,instr line (test did not run)"; tail -60 "$OUT/mvn-test-ifchk.log"; exit 2; }
if ! grep -q "Tests run: 6, Failures: 0, Errors: 0, Skipped: 0" "$OUT/mvn-test-ifchk.log"; then
  echo "STOP: a test failed or errored"
  grep -A8 "<<< FAILURE\|<<< ERROR" "$OUT"/*TestBoundedLimitMemory*.txt 2>/dev/null | head -40 || true
  exit 4
fi

# B2e step 4: existing tests as a sanity check
set +e
step mvn -B test -Dtest=TestBoundedByteArrayOutputStream,TestTFileStreams -DfailIfNoTests=false \
  "-Dmaven-surefire-plugin.argLine=$ARGLINE" > "$OUT/mvn-test-existing.log" 2>&1
rc=$?
set -e
echo "mvn rc=$rc"
grep -E "Tests run:|BUILD SUCCESS|BUILD FAILURE" "$OUT/mvn-test-existing.log" | tail -6
cp target/surefire-reports/*TestBoundedByteArrayOutputStream.txt target/surefire-reports/*TestTFileStreams.txt "$OUT/" 2>/dev/null || true

# B2e step 6: cleanup of the TFile files
step ls -la "$TMPD"
step rm -f "$TMPD"/u4-*.tfile "$TMPD"/u5-*.tfile "$TMPD"/.u4-*.crc "$TMPD"/.u5-*.crc
echo "=== done $(date '+%F %T')"
