#!/usr/bin/env bash
# Unit tier driver of sasi-compaction-flush-memory-ensurecapacity-tmp--autonomous.
# Usage: bash unit-run.sh <tree> <outdir> check            instrument check: ant testsome (tiny cell) + a JUnitCore run with the agent
#        bash unit-run.sh <tree> <outdir> run [parallel]   readings: one JUnitCore JVM per cell, Byteman agent attached, <parallel> JVMs at once (default 3)
# tree: a copy-source.sh tree that has been built (ant build-test); no node ever runs from it during this script.
# Writes <outdir>/session.log, <outdir>/cells/<cell>/{out.csv,trace.txt,jvm.log}. Scratch on /dev/shm. No process is left behind.
set -u
TREE=${1:?}; OUT=${2:?}; MODE=${3:?}; PAR=${4:-3}
HARN=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUT/cells"; LOG=$OUT/session.log
log() { echo "[$(date +%FT%T.%3N%z)] $*" | tee -a "$LOG"; }
TMPBASE=/dev/shm/s4-b7-st-unit
BM=$TREE/build/lib/jars/byteman-4.0.20.jar
cp "$HARN/SasiSuffixMemoryTest.java" "$TREE/test/unit/org/apache/cassandra/index/sasi/disk/" || exit 1
( cd "$HARN" && md5sum *.java *.btm *.py *.sh ) > "$OUT/harness.md5" 2>/dev/null; cat "$OUT/harness.md5" >> "$LOG"
log "unit-run $MODE tree=$TREE head=$(git -C $TREE rev-parse --short HEAD) java=$(java -version 2>&1 | head -1)"
CP="$TREE/build/classes/main:$TREE/build/test/classes:$TREE/build/lib/jars/*:$TREE/build/test/lib/jars/*:$TREE/test/conf"
JOPTS=$(grep -v '^#' $TREE/conf/jvm11-clients.options | grep -v '^$' | tr '\n' ' ')
ulimit -n 100000

# cell_run <cell> <heapMB> [extra env...]  -> runs one JVM
cell_run() {
  local cell=$1 heap=$2; shift 2
  local d=$OUT/cells/${cell//:/_}; mkdir -p "$d"
  local t=$TMPBASE/${cell//:/_}; rm -rf "$t"; mkdir -p "$t"
  local t0=$(date +%s)
  ( cd "$TREE" && env STAGE4_CELL=$cell STAGE4_OUT=$d STAGE4_TMP=$t "$@" \
    java -Xms${heap}m -Xmx${heap}m -XX:+UseG1GC $JOPTS \
      -javaagent:$BM=script:$HARN/lts.btm -Dstage4.trace=$d/trace.txt \
      -Dcassandra.config=file://$TREE/test/conf/cassandra.yaml -Dcassandra.storagedir=$t/storage \
      -Dlogback.configurationFile=file://$TREE/test/conf/logback-test.xml -Dcassandra.skip_sync=true \
      -cp "$CP" org.junit.runner.JUnitCore org.apache.cassandra.index.sasi.disk.SasiSuffixMemoryTest < /dev/null > "$d/jvm.log" 2>&1 )
  local rc=$?
  echo "cell=$cell heap=${heap}m rc=$rc secs=$(( $(date +%s) - t0 )) $(grep -m1 -E '^OK|^Tests run' "$d/jvm.log")" >> "$LOG"
  rm -rf "$t"
  return $rc
}
export -f cell_run 2>/dev/null

if [ "$MODE" = check ]; then
  # 1. ant testsome with a tiny Part 1 cell (the unit test as the protocol runs it); 2. JUnitCore with the agent: known answers.
  d=$OUT/check; mkdir -p "$d"
  log "+ ant testsome (STAGE4_CELL=p1 STAGE4_SIZES=2048,70000 STAGE4_REPEAT=1)"
  ( cd $TREE && STAGE4_CELL=p1 STAGE4_SIZES=2048,70000 STAGE4_REPEAT=1 STAGE4_OUT=$d/ant STAGE4_TMP=$TMPBASE/ant ant testsome -Dtest.name=org.apache.cassandra.index.sasi.disk.SasiSuffixMemoryTest < /dev/null ) > "$d/ant.log" 2>&1
  log "ant exit $? ; $(grep -m1 'Tests run' $d/ant.log)"; cat $d/ant/p1.csv 2>/dev/null | tee -a "$LOG"
  cell_run p1 512 STAGE4_SIZES=2048,70000,1048576 STAGE4_REPEAT=1; cat $OUT/cells/p1/p1.csv | tee -a "$LOG"; grep -c . $OUT/cells/p1/trace.txt | tee -a "$LOG"
  cell_run p2:CONTAINS:1:100:1 1024; cat $OUT/cells/p2_CONTAINS_1_100_1/*.csv | tee -a "$LOG"
  cell_run p2:PREFIX:1:100:1 1024; cat $OUT/cells/p2_PREFIX_1_100_1/*.csv | tee -a "$LOG"
  rm -rf $TMPBASE; exit 0
fi

# run: the cell list of B2b as amended (B5.9): L=16,64 x M=8,32,128; L=256,1000 x M=8,32; PREFIX control at each, and at M=128 for L=256,1000.
# heap = (14 bytes * chars * 1.7 + 1.7*1.7*M MiB) + 700 MiB, at least 1024 MiB; cells above 20 M characters run once, the others 3 times (B2h(d), B5.4)
cells=()
add_cell() { local mode=$1 M=$2 L=$3; local N=$(( (M*1048576) / (220+L) )); local chars=$(( N*L )); local heap rep=3
  heap=$(( (chars*14*17/10 + M*1048576*17/10*17/10)/1048576 + 700 )); [ $heap -lt 1024 ] && heap=1024
  [ $chars -gt 20000000 ] && rep=1
  cells+=("p2:$mode:$M:$L:$rep:$heap"); }
for L in 16 64; do for M in 8 32 128; do add_cell CONTAINS $M $L; add_cell PREFIX $M $L; done; done
for L in 256 1000; do for M in 8 32; do add_cell CONTAINS $M $L; add_cell PREFIX $M $L; done; add_cell PREFIX 128 $L; done
cells=("p1:2400" "${cells[@]}")
# largest first so the long cells start early
printf '%s\n' "${cells[@]}" | sort -t: -k6 -n -r > "$OUT/cells.list"; log "cells: $(wc -l < $OUT/cells.list)"
run_one() { c=${1%:*}; h=${1##*:}; case $c in p1) cell_run p1 $h STAGE4_REPEAT=3;; *) cell_run $c $h;; esac; }
export -f run_one
export OUT TREE HARN LOG CP JOPTS BM TMPBASE
< "$OUT/cells.list" xargs -P "$PAR" -I{} bash -c 'run_one {}'
log "all cells finished"
rm -rf $TMPBASE
