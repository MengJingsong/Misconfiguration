#!/usr/bin/env bash
# Cluster tier run 1 (B3e) of flushLowWaterMark-doRun-flushLowWaterMark--autonomous: ten lifetimes, the two repetitions
# interleaved (V0..V4 rep 1, then V0..V4 rep 2), then the cross-lifetime analysis. A failed lifetime is logged and the chain
# goes on (each lifetime stops its own nodes). Usage: bash run1-chain.sh <run>
H=$(cd "$(dirname "$0")" && pwd)
run=${1:-run1}
for rep in 1 2; do
  for v in V0 V1 V2 V3 V4; do
    echo "=== $(date -u +%FT%TZ) lifetime $v rep $rep"
    python3 "$H/cluster-run.py" "$run" "$v" "$rep"
    echo "=== $(date -u +%FT%TZ) lifetime $v rep $rep exit $?"
  done
done
python3 "$H/cluster-run.py" "$run" analyze
echo "=== $(date -u +%FT%TZ) chain end"
