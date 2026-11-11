#!/usr/bin/env bash
# Unit tier (case-file B2, amended A1-A6) for DF_getAvailable-getLocalPathForWrite-maxCapacity--autonomous.
# Usage: unit-run.sh <run-dir>                 full run (setup if needed, 4 runs: baseline/ablated x 2)
#        unit-run.sh <run-dir> --compile-only  instrument check: setup + test-compile both copies
# <run-dir> = /mydata/jingsong-s4/DF_getAvailable-getLocalPathForWrite-maxCapacity-run1 on pc41.
# Logs every command and its output to <run-dir>/logs/unit/unit-run.log; stops at the first failed step.
# Unmounts the loop filesystems at the end (the CSVs are outside them); images are deleted after the self-check.
set -euo pipefail
RUN=${1:?usage: unit-run.sh <run-dir> [--compile-only]}
MODE=${2:-}
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../../../../../../.." && pwd)
COPY=$REPO/experiments/if-check-exp/hadoop/stage4-runtime-verification/jingsong/copy-source.sh
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
export PATH=$JAVA_HOME/bin:$PATH
OUT=$RUN/logs/unit
mkdir -p "$OUT"
LOG=$OUT/unit-run.log
exec > >(tee -a "$LOG") 2>&1
step(){ echo "+ [$(date '+%F %T')] $*"; "$@"; }
REL=hadoop-common-project/hadoop-common
LDA=src/main/java/org/apache/hadoop/fs/LocalDirAllocator.java
TPKG=src/test/java/org/apache/hadoop/fs
M0=$RUN/mnt/ldA0; M1=$RUN/mnt/ldA1
cleanup(){
  rc=$?
  echo "EXIT rc=$rc at $(date '+%F %T')"
  for m in "$M0" "$M1"; do mountpoint -q "$m" && sudo umount "$m" && echo "unmounted $m" || true; done
  echo "leftover surefire JVMs:"; jps -l | grep -i surefire || echo none
}
trap cleanup EXIT

echo "=== unit-run.sh $(date '+%F %T') on $(hostname) mode=${MODE:-run}"
[ "$(hostname -s)" = node0 ] || { echo "STOP: not pc41/node0"; exit 1; }
step java -version
step mvn -version
step md5sum "$HERE"/TestLdaMaxCapacity.java "$HERE"/unit-run.sh

# A1: two copies, ablation of lines 528-530 in src-ablated only
for v in baseline ablated; do
  [ -d "$RUN/src-$v" ] || step "$COPY" "$RUN/src-$v"
  step git -C "$RUN/src-$v" describe --tags
done
if git -C "$RUN/src-ablated" diff --quiet -- "$REL/$LDA"; then
  step sed -n '528,530p' "$RUN/src-ablated/$REL/$LDA"
  [ "$(sed -n '528p' "$RUN/src-ablated/$REL/$LDA" | tr -d ' ')" = "if(capacity>maxCapacity){" ] || { echo "STOP: line 528 not the check"; exit 1; }
  step sed -i '528,530d' "$RUN/src-ablated/$REL/$LDA"
fi
step git -C "$RUN/src-ablated" diff --numstat
[ "$(git -C "$RUN/src-ablated" diff --numstat | awk '{print $1" "$2}')" = "0 3" ] || { echo "STOP: ablation is not exactly 3 deleted lines"; exit 1; }
step git -C "$RUN/src-ablated" diff
git -C "$RUN/src-baseline" diff --quiet || { echo "STOP: baseline copy modified"; exit 1; }
for v in baseline ablated; do step cp "$HERE/TestLdaMaxCapacity.java" "$RUN/src-$v/$REL/$TPKG/"; done

# A1: loop filesystems under $RUN
mkdir -p "$RUN/ldA" "$M0" "$M1"
for i in 0 1; do
  img=$RUN/ldA/img$i; m=$RUN/mnt/ldA$i; sz=$([ $i = 0 ] && echo 256M || echo 512M)
  if ! mountpoint -q "$m"; then
    [ -f "$img" ] || { step truncate -s "$sz" "$img"; step mkfs.ext4 -q -F "$img"; }
    step sudo mount -o loop "$img" "$m"
    step sudo chown jason92 "$m"
  fi
  mkdir -p "$m/lda"
done
step df -B1 "$M0" "$M1"
export LDA_DIR0=$M0/lda LDA_DIR1=$M1/lda

if [ "$MODE" = "--compile-only" ]; then
  for v in baseline ablated; do
    cd "$RUN/src-$v/$REL"
    step mvn -o -B test-compile -Dmaven.javadoc.skip=true > "$OUT/compile-$v.log" 2>&1 || { tail -40 "$OUT/compile-$v.log"; echo "STOP: test-compile failed ($v)"; exit 1; }
    grep -E "BUILD SUCCESS|BUILD FAILURE" "$OUT/compile-$v.log"
    ls -l target/test-classes/org/apache/hadoop/fs/TestLdaMaxCapacity.class
  done
  exit 0
fi

cat <<'EOF'
EXPECTED (B2f, frozen with A5): outcomes and histograms equal baseline vs ablated; 1k and min-64M succeed 200/200
(2 dirs ~100/100); max-64M succeeds 200/200 in dir1 (2 dirs) / dir0 ({dir0}, = min-64M); max+64M and longmax-1 fail
200/200; baseline msgN = max avail (+-1 MiB), ablated msgN = 0; written files as large as written (> size).
EOF

for rep in 1 2; do
  for v in baseline ablated; do
    echo "=== $v rep $rep"
    rm -rf "${LDA_DIR0:?}"/* "${LDA_DIR1:?}"/*
    export LDA_VARIANT=$v LDA_OUT=$OUT/$v-rep$rep.csv
    R=$OUT/$v-rep$rep; mkdir -p "$R"
    cd "$RUN/src-$v/$REL"
    set +e
    step mvn -o -B test -Dtest=TestLdaMaxCapacity -DfailIfNoTests=false -Dmaven.javadoc.skip=true > "$R/mvn-test.log" 2>&1
    rc=$?
    set -e
    echo "mvn rc=$rc"
    grep -E "Tests run:|BUILD SUCCESS|BUILD FAILURE" "$R/mvn-test.log" | tail -4
    cp target/surefire-reports/*TestLdaMaxCapacity* "$R/" 2>/dev/null || true
    [ "$rc" -eq 0 ] || { echo "STOP: mvn failed rc=$rc ($v rep $rep)"; tail -40 "$R/mvn-test.log"; exit 3; }
    grep -q "Tests run: 1, Failures: 0, Errors: 0, Skipped: 0" "$R/mvn-test.log" || { echo "STOP: test failed ($v rep $rep)"; grep -A20 "<<< FAILURE\|<<< ERROR" "$R"/*.txt | head -40 || true; exit 4; }
    [ -s "$LDA_OUT" ] || { echo "STOP: no CSV"; exit 5; }
    echo "rows: $(($(wc -l < "$LDA_OUT") - 1))"
    OUTF=$(ls "$R"/*TestLdaMaxCapacity-output.txt 2>/dev/null | head -1 || true)
    [ -n "$OUTF" ] || OUTF=$R/mvn-test.log
    grep -a '^LDA ' "$OUTF" | cut -c1-400 || true
  done
done
step python3 -I "$HERE/unit-analyze.py" "$OUT" | tee "$OUT/unit-summary.txt"
echo "=== done $(date '+%F %T')"
