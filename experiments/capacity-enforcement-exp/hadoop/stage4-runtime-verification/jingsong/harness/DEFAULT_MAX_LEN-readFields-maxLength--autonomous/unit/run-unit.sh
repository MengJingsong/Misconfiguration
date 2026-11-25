#!/usr/bin/env bash
# Stage-4 unit tier (B2) for DEFAULT_MAX_LEN-readFields-maxLength--autonomous. Runs ON the node.
# Usage: run-unit.sh <run-dir> <harness-dir>   (run-dir holds hadoop-src from copy-source.sh)
# Logs every command and its output to <run-dir>/unit/run-unit.log; stops at the first failed step.
set -euo pipefail
R=${1:?run dir}; H=${2:?harness dir}
mkdir -p "$R/unit"; LOG="$R/unit/run-unit.log"
exec > >(tee -a "$LOG") 2>&1
step() { echo; echo "=== $(date -Is) STEP: $*"; }
run() { echo "+ $*"; "$@"; }
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64 YARN_IGNORE_ENGINES=true
export PATH=$JAVA_HOME/bin:$PATH
SRC=$R/hadoop-src
TEST=hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/io/TestTextMaxLenProbe.java

step "environment"
run hostname; run uname -r; run java -version; run mvn -v | head -3
run git -C "$SRC" describe --tags; run git -C "$SRC" status --short

step "B2e.2 install the probe test"
run cp "$H/TestTextMaxLenProbe.java" "$SRC/$TEST"
run sha256sum "$SRC/$TEST"

step "B2e.3 run the test with -Xmx512m (B2a); modules from the base build are in ~/.m2 (environment.md section 3)"
cd "$SRC"
set +e
mvn -B -pl hadoop-common-project/hadoop-common test -Dtest=TestTextMaxLenProbe \
  -Dmaven-surefire-plugin.argLine="-Xmx512m" -Dmaven.javadoc.skip=true -DfailIfNoTests=false \
  > "$R/unit/mvn-test.log" 2>&1
RC=$?
set -e
echo "mvn exit code $RC"; tail -40 "$R/unit/mvn-test.log"
SR=hadoop-common-project/hadoop-common/target/surefire-reports
run ls -la "$SR" | grep -i TextMaxLen || true
cp "$SR"/*TestTextMaxLenProbe* "$R/unit/" 2>/dev/null || true
OUT="$SR/org.apache.hadoop.io.TestTextMaxLenProbe-output.txt"
if [ -f "$OUT" ]; then grep -E '^(PROBE|SUMMARY|BASELINE|MISMATCH)' "$OUT" > "$R/unit/probe-lines.txt"; else
  grep -E '^(PROBE|SUMMARY|BASELINE|MISMATCH)' "$R/unit/mvn-test.log" > "$R/unit/probe-lines.txt" || true; fi
run wc -l "$R/unit/probe-lines.txt"
grep -E '^(SUMMARY|BASELINE|MISMATCH)' "$R/unit/probe-lines.txt"

step "heap dumps (B4: delete if any)"
find "$SRC" -name '*.hprof' -printf '%p %s\n' -delete || true

step "B2e.4 remove the probe test from the local copy"
run rm -f "$SRC/$TEST"
run git -C "$SRC" status --short
echo "=== $(date -Is) DONE (mvn rc $RC)"
