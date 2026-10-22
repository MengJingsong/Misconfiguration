#!/bin/bash
# Runs the four NCS values of the cluster tier one after another (case file B3e + K4 order), from the frozen copy.
# usage: bash all-runs.sh   (output ~/stage4-logs/ncs/cluster/<label>/; driver log ~/stage4-logs/ncs/cluster/all-runs.log)
H=$HOME/stage4-harness-run/ncs
mkdir -p $HOME/stage4-logs/ncs/cluster
for v in 4 8 16 128; do
  echo "== $(date -Is) start V$v"
  bash $H/cluster-run.sh V$v $v > /dev/null 2>&1
  echo "== $(date -Is) end V$v rc=$?"
  sleep 5
done
echo "== $(date -Is) all done"
