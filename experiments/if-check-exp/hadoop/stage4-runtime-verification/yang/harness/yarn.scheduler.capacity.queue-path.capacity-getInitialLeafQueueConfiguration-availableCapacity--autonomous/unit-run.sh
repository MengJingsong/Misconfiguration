#!/usr/bin/env bash
# Unit tier (case-file B2e, amended A1/A2) for
#   yarn.scheduler.capacity.queue-path.capacity-getInitialLeafQueueConfiguration-availableCapacity--autonomous
# Usage: unit-run.sh <run-dir>   (e.g. /mydata/yang-s4/<stem>-run1; <run-dir>/src made by copy-source.sh)
#        unit-run.sh <run-dir> --compile-only   (instrument check: copy + test-compile, no test run)
# Logs every command and its output to <run-dir>/logs/unit/unit-run.log; stops at the first failed step;
# a surefire JVM left behind is reported (the test stops its MockRM in a finally block).
set -euo pipefail
RUN=${1:?usage: unit-run.sh <run-dir> [--compile-only]}
MODE=${2:-}
HERE=$(cd "$(dirname "$0")" && pwd)
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
export PATH=$JAVA_HOME/bin:$PATH
SRC=$RUN/src
MOD=$SRC/hadoop-yarn-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-resourcemanager
PKG=$MOD/src/test/java/org/apache/hadoop/yarn/server/resourcemanager/scheduler/capacity
OUT=$RUN/logs/unit
mkdir -p "$OUT"
LOG=$OUT/unit-run.log
exec > >(tee -a "$LOG") 2>&1
step(){ echo "+ [$(date '+%F %T')] $*"; "$@"; }
leftover(){ jps -l | grep -i surefire || true; }
trap 'rc=$?; echo "EXIT rc=$rc at $(date "+%F %T")"; echo "leftover surefire JVMs:"; leftover' EXIT

echo "=== unit-run.sh $(date '+%F %T') on $(hostname) mode=${MODE:-run}"
step java -version
step mvn -version
step git -C "$SRC" describe --tags
step cp "$HERE/TestIfCheckAutoQueueGuaranteeVsUsage.java" "$PKG/"
step md5sum "$HERE/TestIfCheckAutoQueueGuaranteeVsUsage.java" "$HERE/unit-run.sh"
cd "$MOD"
if [ "$MODE" = "--compile-only" ]; then
  step mvn -B test-compile -Dmaven.javadoc.skip=true > "$OUT/compile.log" 2>&1 || { tail -40 "$OUT/compile.log"; echo "STOP: test-compile failed"; exit 1; }
  grep -E "BUILD SUCCESS|BUILD FAILURE" "$OUT/compile.log"
  ls -l target/test-classes/org/apache/hadoop/yarn/server/resourcemanager/scheduler/capacity/TestIfCheckAutoQueueGuaranteeVsUsage.class
  exit 0
fi

cat <<'EOF'
EXPECTED: (B2f, frozen) U1 avail 0.2010,0.1010,0.0010; u3 leafAbsCap 0.0000 active=false; actSum after u3 0.2000; u3 effMaxMB 102400; u3 used 41984
EXPECTED: (B2f, frozen) U2 avail 0.2010,0.1510,0.1010,0.0510,0.0010; u3 0.0500 active=true; u5 0.0000 active=false; actSum 0.1500 after u3, 0.2000 after u5; u3 effMaxMB 102400; u3 used 41984
EXPECTED: (B2f, frozen) U3 avail 0.4010,0.2010,0.0010; u3 0.0000 active=false; actSum 0.4000; u3 effMaxMB 102400; u3 used 41984
EXPECTED: (B2f, frozen) U4 avail 0.2010,0.1010,0.0010; u3 0.0000 active=false; actSum 0.2000; u3 effMaxMB 25600; u3 used <= 25600 (<= 26624), >= 15 requests unsatisfied
EXPECTED: (B2f, frozen) u1 and u2 used 1024 each in all runs; Confirmed needs U1 ~ U2 ~ U3 ~ 41984 (+-1024) and U4 <= 26624
EOF

for rep in 1 2 3; do
  R=$OUT/rep$rep
  mkdir -p "$R"
  echo "=== repeat $rep"
  set +e
  step mvn -B test -Dtest=TestIfCheckAutoQueueGuaranteeVsUsage -DfailIfNoTests=false > "$R/mvn-test.log" 2>&1
  rc=$?
  set -e
  echo "mvn rc=$rc"
  grep -E "Tests run:|BUILD SUCCESS|BUILD FAILURE" "$R/mvn-test.log" | tail -5
  cp target/surefire-reports/*TestIfCheck* "$R/" 2>/dev/null || true
  # IFCHK lines come from the surefire output file (redirectTestOutputToFile) or the mvn log.
  OUTF=$(ls "$R"/*TestIfCheck*-output.txt 2>/dev/null | head -1 || true)
  [ -n "$OUTF" ] || OUTF=$R/mvn-test.log
  echo "IFCHK source: $OUTF"
  grep -a '^IFCHK' "$OUTF" > "$R/ifchk.tsv" || true
  # First-trigger check: the leaf u1 must have been auto-created under the managed parent (the check ran).
  if ! grep -qP '^IFCHK\tU1\tcreate\tu1\t' "$R/ifchk.tsv"; then
    echo "STOP: first-trigger check failed in repeat $rep: no 'IFCHK U1 create u1' line (auto-creation / the check not reached)"
    tail -60 "$R/mvn-test.log"
    exit 2
  fi
  [ "$rc" -eq 0 ] || { echo "STOP: mvn test failed (rc=$rc) in repeat $rep"; exit 3; }
  # The build ignores test failures (rc 0), so read the surefire count (added after attempt 1, defect 1).
  if ! grep -q "Tests run: 4, Failures: 0, Errors: 0, Skipped: 0" "$R/mvn-test.log"; then
    echo "STOP: a test failed or errored in repeat $rep (runbook step cannot run as written)"
    grep -A3 "<<< FAILURE\|<<< ERROR" "$R"/*TestIfCheck*.txt 2>/dev/null | head -30 || true
    exit 4
  fi
  if [ "$(grep -cP '\tend\t' "$R/ifchk.tsv")" -ne 4 ]; then echo "STOP: not 4 'end' lines in repeat $rep"; exit 5; fi
  echo "repeat $rep: $(wc -l < "$R/ifchk.tsv") IFCHK lines"
done
echo "=== done $(date '+%F %T')"
