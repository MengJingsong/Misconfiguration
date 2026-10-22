#!/usr/bin/env bash
# usage: bash run1-chain.sh <run>     the eight cluster lifetimes in order (B3e step 2-3, interleaved V order), then analyze.
# A failed lifetime stops the chain (its nodes are stopped by cluster-run.py's finally block).
set -u
RUN=${1:-run1}
H=$(cd "$(dirname "$0")" && pwd)
for L in v16k-1 v64k-1 v128k-1 ctl-1 v16k-2 v64k-2 v128k-2 ctl-2; do
  echo "=== $(date +%s%3N) lifetime $L"
  python3 "$H/cluster-run.py" "$RUN" "$L" || { echo "lifetime $L failed; chain stopped"; python3 "$H/cluster-run.py" "$RUN" down; exit 1; }
done
python3 "$H/cluster-run.py" "$RUN" analyze
echo "=== $(date +%s%3N) chain done"
