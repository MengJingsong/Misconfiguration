#!/bin/bash
# Usage: bash cluster-chain.sh <outroot>. Order: rep 1 of unset,128,256,8192 then rep 2. Stops at the first failed arm.
OUT=${1:?}; HERE=$(cd "$(dirname "$0")" && pwd); mkdir -p $OUT
for rep in 1 2; do for arm in unset 128 256 8192; do
  echo "[$(date +%FT%T)] chain: $arm r$rep start" >> $OUT/chain.log
  bash $HERE/cluster-run.sh $OUT $arm $rep
  [ -f $OUT/$arm-r$rep/DONE ] || { echo "[$(date +%FT%T)] chain: $arm r$rep did not finish; stop" >> $OUT/chain.log; exit 1; }
done; done
echo "[$(date +%FT%T)] chain: all done" >> $OUT/chain.log
