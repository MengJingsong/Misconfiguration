#!/usr/bin/env bash
# Cluster tier run 1 (B3e): one lifetime per label, in order, then the cross-run analysis. Run detached on the node:
#   setsid nohup bash run1-chain.sh > ~/stage4-logs/sq2/run1-chain.log 2>&1 < /dev/null &
H=$(cd "$(dirname "$0")" && pwd)
for l in c4m c64m c256m pos neg; do
  echo "=== $(date -u +%FT%TZ) label $l"
  python3 "$H/cluster-run.py" run1 "$l"; echo "=== label $l exit $?"
done
python3 "$H/cluster-run.py" run1 analyze
echo "=== chain done $(date -u +%FT%TZ)"
