#!/usr/bin/env bash
# Run 1 cluster tier: the six lifetimes one after another, then analyze. Stops at the first failed lifetime (cluster-run.py exits 1 and stops its node).
H=$(cd "$(dirname "$0")" && pwd); export MR_RUN=${1:-run1}; LG=$HOME/s4-b7-mr-logs/$MR_RUN; mkdir -p $LG
cd $HOME
for a in ${ARMS:-m1024 m256 m4096 m1024b o128 o256}; do
  echo "$(date -u +%FT%TZ) chain $a start" >> $LG/chain.log
  python3 -I $H/cluster-run.py $a > $LG/chain-$a.out 2>&1 || { echo "$(date -u +%FT%TZ) chain $a FAILED" >> $LG/chain.log; exit 1; }
  echo "$(date -u +%FT%TZ) chain $a end" >> $LG/chain.log
done
python3 -I $H/cluster-run.py analyze > $LG/chain-analyze.out 2>&1
echo "$(date -u +%FT%TZ) chain done" >> $LG/chain.log
