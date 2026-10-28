#!/usr/bin/env bash
for a in Q-200 Q-50 Q-1000 QOFF; do python3 ~/stage4-harness/diag/cluster-run.py $a run1 > ~/stage4-logs/diag/chain-$a.out 2>&1 || echo "ARM $a FAILED" >> ~/stage4-logs/diag/chain.status; echo "$a done $(date +%T)" >> ~/stage4-logs/diag/chain.status; done
