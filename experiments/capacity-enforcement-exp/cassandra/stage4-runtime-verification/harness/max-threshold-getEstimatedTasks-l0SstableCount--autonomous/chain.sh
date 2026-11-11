#!/bin/bash
# Usage: chain.sh <tree> <outdir>   runs the six arms one after another; each arm stops its own node on any exit
TREE=${1:?tree}; OUT=${2:?outdir}; HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUT"
for a in mt4 mt32 mt128 mt32b c64 d32; do
  echo "$(date -u +%FT%TZ) arm $a start" >> "$OUT/chain.log"
  MT_TREE=$TREE MT_OUT=$OUT python3 "$HERE/cluster-run.py" $a < /dev/null > "$OUT/$a.out" 2>&1
  echo "$(date -u +%FT%TZ) arm $a rc=$?" >> "$OUT/chain.log"
done
echo "$(date -u +%FT%TZ) chain done" >> "$OUT/chain.log"
