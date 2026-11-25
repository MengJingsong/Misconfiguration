#!/bin/bash
# Runs of case B3e, one after another; stops at the first failed run.
W=/mydata/jingsong-cass-s4/o120; H=$W/harness
exec >> $W/run1/cluster-all.log 2>&1
echo "[$(date +%s%3N)] cluster-all start: $*"
for spec in "$@"; do
  set -- $(echo $spec | tr ',' ' ')
  bash $H/cluster-run.sh "$@" || { echo "[$(date +%s%3N)] STOP after failed run $spec"; exit 1; }
done
echo "[$(date +%s%3N)] CLUSTER-ALL-OK"
