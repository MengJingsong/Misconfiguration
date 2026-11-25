#!/usr/bin/env bash
# Stage-4 prep for dfs.client.mmap.cache.size-demoteOldEvictableMmaped-maxEvictableMmapedSize--autonomous on pc91:
# source copy + native hadoop-common build (libhadoop) in the case copy. Logged.
set -uo pipefail
STEM=dfs.client.mmap.cache.size-demoteOldEvictableMmaped-maxEvictableMmapedSize--autonomous
RUNDIR=/mydata/jingsong-s4/$STEM-run1
SRC=$RUNDIR/src; LOGS=$RUNDIR/logs/prep
REPO=/proj/misconfiguration-PG0/git-repos/Misconfiguration
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64 PATH=/usr/lib/jvm/java-8-openjdk-amd64/bin:$PATH YARN_IGNORE_ENGINES=true
mkdir -p "$LOGS"
exec > >(tee -a "$LOGS/prep.log") 2>&1
run() { echo "+ $*  [$(date '+%F %T')]"; "$@"; local rc=$?; echo "  rc=$rc"; return $rc; }
echo "=== prep.sh start $(date '+%F %T %Z') host=$(hostname)"
run java -version; run mvn -v; run cmake --version; run uname -r; run ulimit -n
st=$(git -C "$REPO" status --short systems/hadoop/source); echo "+ repo source status: ${st:-<clean>}"
[ -z "$st" ] || { echo "STOP: repository source not clean"; exit 1; }
echo "+ repo HEAD $(git -C "$REPO" rev-parse --short HEAD)"
[ -d "$SRC" ] || run "$REPO/experiments/capacity-enforcement-exp/hadoop/stage4-runtime-verification/jingsong/copy-source.sh" "$SRC" || exit 1
cd "$SRC" || exit 1
run mvn -B -pl hadoop-common-project/hadoop-common package -Pnative -DskipTests -Dmaven.javadoc.skip=true > "$LOGS/native-build.log" 2>&1
grep -E "BUILD (SUCCESS|FAILURE)|Total time" "$LOGS/native-build.log"
run ls -l "$SRC/hadoop-common-project/hadoop-common/target/native/target/usr/local/lib"
echo "=== prep.sh end $(date '+%F %T %Z')"
