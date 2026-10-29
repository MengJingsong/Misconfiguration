#!/usr/bin/env bash
# usage: chain.sh <case 1|2|3|4|all> [seconds=120]   Runs the cluster cells of cells.py one after the other (cluster-run.py run ...), then `down`.
# A failed cell is logged and the chain goes on; after every cell no CassandraDaemon may be left. Console log: ~/stage4-logs/ew/chain-<case>.log
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); S=${2:-120}; mkdir -p "$HOME/stage4-logs/ew"
python3 "$H/cells.py" "$1" | while read -r tag v w heap; do
  echo "$(date -u +%FT%TZ) START $tag $v $w $heap"
  python3 "$H/cluster-run.py" run "$tag" "$v" "$w" "$heap" heap_buffers "$S" > "$HOME/stage4-logs/ew/cell-$tag.console" 2>&1 < /dev/null; rc=$?
  echo "$(date -u +%FT%TZ) END   $tag rc=$rc left=$(ps -eo cmd | grep -c '[C]assandraDaemon')"
done
python3 "$H/cluster-run.py" down
