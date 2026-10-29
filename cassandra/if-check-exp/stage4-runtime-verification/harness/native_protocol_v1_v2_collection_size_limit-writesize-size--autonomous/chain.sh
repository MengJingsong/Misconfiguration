#!/usr/bin/env bash
# cluster tier, run 1 (run node): default node start, then the control node start
H=$(cd "$(dirname "$0")" && pwd)
for m in default control; do
  python3 $H/cluster-run.py $m $m > ~/s4-b34/logs/cs-cluster-run1-$m.log 2>&1
  echo "exit=$?" >> ~/s4-b34/logs/cs-cluster-run1-$m.log
  ps -eo cmd | grep '[C]assandraDaemon' | wc -l >> ~/s4-b34/logs/cs-cluster-run1-$m.log
done
