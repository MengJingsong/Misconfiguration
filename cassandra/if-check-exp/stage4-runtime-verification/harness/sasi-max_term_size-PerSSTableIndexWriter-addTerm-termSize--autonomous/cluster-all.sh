#!/bin/bash
# Cluster tier, the four labels in series. Usage: bash cluster-all.sh <outdir> [scale]
# Stops at the first label whose summary.json has an error key. cluster-run.py stops the node and sampler on any exit.
set -u
OUT=${1:?}; SC=${2:-1}; H=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUT" "$HOME/stage4-logs/pw"; ulimit -n 100000
for spec in "m m -" "c1 a 1" "c16 a 16" "tc tc -"; do
  set -- $spec
  echo "[$(date -u +%FT%TZ)] run $1" | tee -a "$OUT/all.log"
  python3 "$H/cluster-run.py" "$1" "$2" "$3" "$OUT/$1" "$SC" > "$OUT/$1.out" 2>&1
  if [ ! -f "$OUT/$1/summary.json" ] || grep -q '"error"' "$OUT/$1/summary.json"; then echo "STOP: $1 failed" | tee -a "$OUT/all.log"; exit 1; fi
done
echo "[$(date -u +%FT%TZ)] all done" | tee -a "$OUT/all.log"
