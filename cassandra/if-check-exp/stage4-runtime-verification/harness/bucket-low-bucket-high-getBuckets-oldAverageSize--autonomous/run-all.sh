#!/bin/bash
# Usage: run-all.sh <tree> <outdir> unit|cluster     one tier; the cluster tier runs the four arms n d w wc one after another and stops at the first failed arm.
set -u
TREE=${1:?tree}; OUT=${2:?outdir}; TIER=${3:?unit|cluster}; HERE=$(cd "$(dirname "$0")" && pwd)
TIMING=/proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/stage4-runtime-verification/timing/set-A-batch-10.log
ulimit -n 100000
mkdir -p "$OUT"
if [ "$TIER" = unit ]; then
  echo "$(date -u +%FT%TZ) S4 sb unit-run start" >> "$TIMING"
  bash "$HERE/unit-run.sh" "$TREE" "$OUT/unit"
  python3 "$HERE/unit-analyze.py" "$OUT/unit/readings.txt" > "$OUT/unit/analysis.txt" 2>&1; tail -1 "$OUT/unit/analysis.txt"
  echo "$(date -u +%FT%TZ) S4 sb unit-run end" >> "$TIMING"
else
  echo "$(date -u +%FT%TZ) S4 sb cluster-run start" >> "$TIMING"
  mkdir -p "$OUT/cluster"
  for a in n d w wc; do
    SB_TREE=$TREE SB_OUT=$OUT/cluster python3 "$HERE/cluster-run.py" $a < /dev/null > "$OUT/cluster/$a.out" 2>&1
    rc=$?; echo "arm $a rc=$rc"
    [ $rc -eq 0 ] || break
  done
  [ -d "$OUT/cluster/wc" ] && [ -f "$OUT/cluster/wc/phase-end.json" ] && python3 "$HERE/cluster-analyze.py" "$OUT/cluster" > "$OUT/cluster/analysis.txt" 2>&1; tail -1 "$OUT/cluster/analysis.txt"
  echo "$(date -u +%FT%TZ) S4 sb cluster-run end" >> "$TIMING"
fi
echo "done $TIER"
