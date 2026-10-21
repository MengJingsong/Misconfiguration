#!/usr/bin/env bash
ulimit -n 100000
O=~/stage4-logs/mss/run1-chain.log
export MSS_RUN=run1
echo "lifetime D 2 (rerun: the first attempt did not start, a hung B1 node was left) $(date -Is)" >> $O
python3 ~/stage4-harness-run/mss/cluster-run.py D 2 > /dev/null 2>> ~/stage4-logs/mss/run1-stderr.log; echo "rc=$? D 2" >> $O
python3 ~/stage4-harness-run/mss/cluster-run.py analyze > /dev/null 2>> ~/stage4-logs/mss/run1-stderr.log
echo "CHAIN2-DONE $(date -Is)" >> $O
