#!/bin/bash
# Usage: cluster-chain.sh <tree> <outdir>   runs the five arms one after another (m32 first: it carries the flip), stops at the first failed arm
set -u
TREE=${1:?tree}; OUT=${2:?outdir}; HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUT"
for arm in m32 m2 m4 m16 mm4; do
  echo "== $(date -u +%FT%TZ) arm $arm"
  SM_TREE="$TREE" SM_OUT="$OUT" python3 "$HERE/cluster-run.py" $arm > "$OUT/$arm.out" 2>&1; rc=$?
  echo "== $(date -u +%FT%TZ) arm $arm rc=$rc"
  [ $rc -eq 0 ] || { echo "arm $arm failed, chain stopped"; exit $rc; }
done
python3 "$HERE/cluster-analyze.py" "$OUT" > "$OUT/analyze.txt" 2>&1; tail -3 "$OUT/analyze.txt"
echo "== chain done"
