#!/bin/bash
# Runs R1..R5 of B3b one after another. Copy this folder to a fresh run directory first and run it from there:
# bash edits to a script that is executing change what the running shell reads next (lesson of run 1, 2026-10-21).
H=$(cd "$(dirname "$0")" && pwd)
for a in "R1 128" "R2 512" "R3 1024" "R4 512 0.15" "R5 512 0.66"; do bash $H/cluster-run.sh $a > /dev/null 2>&1; done
echo done > $HOME/stage4-logs/ncl/ALL-DONE
