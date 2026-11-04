#!/usr/bin/env bash
ulimit -n 100000
O=~/stage4-logs/mss/run1-chain.log; mkdir -p ~/stage4-logs/mss; : > $O
echo "start $(date -Is)" >> $O
bash ~/stage4-harness-run/mss/unit-run.sh run1 >> $O 2>&1
export MSS_RUN=run1
for a in "OFF 1" "D 1" "M4 1" "M32 1" "B1 1" "D 2"; do echo "lifetime $a $(date -Is)" >> $O; python3 ~/stage4-harness-run/mss/cluster-run.py $a > /dev/null 2>> ~/stage4-logs/mss/run1-stderr.log; echo "rc=$? $a" >> $O; done
python3 ~/stage4-harness-run/mss/cluster-run.py analyze > /dev/null 2>> ~/stage4-logs/mss/run1-stderr.log
echo "CHAIN-DONE $(date -Is)" >> $O
