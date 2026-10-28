#!/usr/bin/env bash
for a in S-200 S-50 S-1000 L-200 L-50 L-1000 OFF; do python3 ~/stage4-harness/diag/cluster-run.py $a run1 > ~/stage4-logs/diag/chain-$a.out 2>&1 || echo "ARM $a FAILED" >> ~/stage4-logs/diag/chain.status; echo "$a done $(date +%T)" >> ~/stage4-logs/diag/chain.status; done
