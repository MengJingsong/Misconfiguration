#!/bin/bash
# Cluster tier, the six labels in series. Usage: bash cluster-all.sh <outdir> [rows]
# Stops at the first run whose summary.json has an error key. Node and sampler are stopped by cluster-run.py on any exit.
set -u
OUT=${1:?}; ROWS=${2:-200000}; H=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUT"; ulimit -n 100000
for spec in "v1000 1000 -" "v1023 1023 -" "v1024 1024 -" "v2000 2000 -" "c1 1023 1" "c64 1023 64"; do
  set -- $spec
  echo "[$(date -u +%FT%TZ)] run $1" | tee -a "$OUT/all.log"
  python3 "$H/cluster-run.py" "$1" "$2" "$ROWS" "$3" "$OUT/$1" > "$OUT/$1.out" 2>&1
  if grep -q '"error"' "$OUT/$1/summary.json" 2>/dev/null || [ ! -f "$OUT/$1/summary.json" ]; then echo "STOP: $1 failed" | tee -a "$OUT/all.log"; exit 1; fi
done
echo "[$(date -u +%FT%TZ)] all done" | tee -a "$OUT/all.log"
