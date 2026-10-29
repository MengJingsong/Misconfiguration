#!/usr/bin/env bash
# cluster tier, run 1 (run node): the single node start of B3
H=$(cd "$(dirname "$0")" && pwd)
python3 $H/cluster-run.py main > ~/s4-b34/logs/mks-cluster-run1.log 2>&1
echo "exit=$?" >> ~/s4-b34/logs/mks-cluster-run1.log
ps -eo cmd | grep '[C]assandraDaemon' | wc -l >> ~/s4-b34/logs/mks-cluster-run1.log
