#!/usr/bin/env bash
# run 1, cluster tier: five lifetimes in sequence, then analyze
cd ~/stage4-harness-run/rsv
export RSV_RUN=run1
for l in g4 g32 g512 ctlq16 base; do
  python3 cluster-run.py $l > ~/stage4-logs/rsv/run1-$l.out 2>&1 < /dev/null
  echo "$l exit $?" >> ~/stage4-logs/rsv/run1-chain.txt
done
python3 cluster-run.py analyze > ~/stage4-logs/rsv/run1-analyze.out 2>&1 < /dev/null
echo "analyze exit $?" >> ~/stage4-logs/rsv/run1-chain.txt
