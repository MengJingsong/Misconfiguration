#!/bin/bash
# Runs R1..R6 of B3b (with audit amendment A-K1) one after another. Copy this folder to a fresh run directory first and
# run it from there; never edit a running script (lesson of 2026-10-21).
H=$(cd "$(dirname "$0")" && pwd)
mkdir -p $HOME/stage4-logs/sai
for a in "R1 64 sai" "R2 256 sai" "R3 64 plain" "R4 256 plain" "R5 1024 sai" "R6 1024 plain"; do
  echo "$(date -Is) start $a" >> $HOME/stage4-logs/sai/all-runs.txt
  bash $H/cluster-run.sh $a > /dev/null 2>&1
  echo "$(date -Is) end $a rc=$?" >> $HOME/stage4-logs/sai/all-runs.txt
done
echo done > $HOME/stage4-logs/sai/ALL-DONE
