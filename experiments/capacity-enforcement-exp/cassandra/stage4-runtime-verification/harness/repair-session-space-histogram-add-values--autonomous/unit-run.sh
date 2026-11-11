#!/usr/bin/env bash
# Unit tier driver. usage: bash unit-run.sh <tree> <outdir> [check]
#   tree = a copy-source.sh tree built with `ant build-test` (nothing is written into it); outdir = local/tmpfs dir for logs.
# Compiles HistogramBudgetProbe against the tree's build/classes/main + jars into <outdir>/classes, then runs one JVM (-Xmx2g -Xms2g, jamm agent,
# client options of conf/jvm11-clients.options) per measurement. With `check` it runs only the known-answer instrument check (no readings of the claim).
# Writes <outdir>/unit.log (every command and output) and <outdir>/summary.txt (RESULT lines). Judging is done by unit-analyze.py (EXPECTED lines).
set -u
TREE=${1:?}; OUT=${2:?}; MODE=${3:-full}; H=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUT/classes" "$OUT/storage"; LOG=$OUT/unit.log; S=$OUT/summary.txt; : > "$LOG"; [ "$MODE" = check ] && S=$OUT/check.txt; : > "$S"
CP="$TREE/build/classes/main:$TREE/build/lib/jars/*"
JAMM=$(ls "$TREE"/build/lib/jars/jamm-*.jar | head -1)
javac -cp "$CP" -d "$OUT/classes" "$H/HistogramBudgetProbe.java" 2>&1 | tee -a "$LOG" || exit 1
( cd "$H" && md5sum HistogramBudgetProbe.java unit-run.sh ) | tee -a "$S"
java -version 2>&1 | head -1 | tee -a "$S"
CLIENT_OPTS=$(grep -v '^#' "$TREE/conf/jvm11-clients.options" | grep -v '^$' | tr '\n' ' ')
JOPTS="-Xmx2g -Xms2g -XX:+UseG1GC -javaagent:$JAMM -Dcassandra.config=file://$TREE/conf/cassandra.yaml -Dcassandra.storagedir=$OUT/storage -Dcassandra.logdir=$OUT $CLIENT_OPTS"
run() { # run <extra jvm opts> <args...>
  local x=$1; shift
  echo "+ java $JOPTS $x HistogramBudgetProbe $*" >> "$LOG"
  local out; out=$(java $JOPTS $x -cp "$OUT/classes:$CP" org.apache.cassandra.utils.HistogramBudgetProbe "$@" 2>&1)
  echo "$out" | tail -n 30 >> "$LOG"
  local r; r=$(echo "$out" | grep '^RESULT'); [ -n "$r" ] && echo "$r" | tee -a "$S" || { echo "NORESULT args=$*" | tee -a "$S"; echo "$out" | tail -n 5 | sed 's/^/  /' | tee -a "$S"; }
}
if [ "$MODE" = check ]; then
  # known-answer: builder with n adds; the allocated array must be exactly 16+8*len for len = 10*2^ceil(log2(n/10)) (arithmetic of HistogramBuilder.add)
  run "" known 10 11 1000000
  run "" tree 64 3 20 1
  exit 0
fi
run "" direct 10 11 20 21 1024 8192 131072 1048576 1048577
# every (S, RF, D) of B2b in its own JVM; reps = 3 after one warm-up
for D in 20 10; do for SV in 1 8 64 512 2047 2048 4096; do run "" tree $SV 3 $D 3; done; done
run "" tree 2047 1 20 3
run "" tree 4096 1 20 3
# RF = 2 rows: the depth the cluster tier (2 nodes, RF 2, repair -pr, rangeOwningRatio 1) should reach for S = 700 / 64 / 8 and D = 12
for SV in 700 64 8; do run "" tree $SV 2 20 3; done
run "" tree 700 2 12 3
echo "unit-run done $(date -u +%FT%TZ)" | tee -a "$S"
