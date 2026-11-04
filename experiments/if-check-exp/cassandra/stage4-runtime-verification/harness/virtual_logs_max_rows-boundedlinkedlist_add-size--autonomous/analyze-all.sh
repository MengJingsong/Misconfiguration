#!/usr/bin/env bash
# analysis of every arm of the cluster tier (readings), ON-minus-OFF against the OFF arm. Output: stdout (kept as run1/cluster/analysis.txt)
D=${1:-$HOME/stage4-logs/vlr/run1/cluster}; H=$(cd "$(dirname "$0")" && pwd)
for a in n1000 n20000 n100000 n200000 nunset w1000; do
  echo "=================== $a"; python3 "$H/analyze.py" "$D/$a" "$D/off"
done
echo "=================== off"; python3 "$H/analyze.py" "$D/off"
