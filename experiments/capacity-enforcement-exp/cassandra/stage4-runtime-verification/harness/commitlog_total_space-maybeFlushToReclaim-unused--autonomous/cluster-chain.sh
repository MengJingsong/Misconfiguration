#!/bin/bash
# Runs the four B3 arms one after another (B3e order: 256, 1024, 16384, then the 256p probe).
OUT=${1:?outroot}; mkdir -p $OUT
H=$HOME/stage4-harness-run/cts
echo "EXPECTED: B3f (S=32 MiB, du -sb): 256 peak<=384MiB settle<=288MiB CLD>=8 ML=0 | 1024 peak<=1152 settle<=1056 CLD>=2 ML=0 | 16384 peak>=2.8GiB rising, CLD=0 ML=0 | 256p 384<peak<1024 settle<=288 CLD>=8 ML=0" | tee $OUT/chain.log
for a in "256 256 1" "1024 1024 1" "16384 16384 1" "256p 256 0"; do
  set -- $a; echo "[$(date +%FT%T)] arm $1" >> $OUT/chain.log
  bash $H/cluster-run.sh $OUT $1 $2 $3 >> $OUT/chain.log 2>&1
  [ -f $OUT/$1/DONE ] || { echo "arm $1 did not finish" >> $OUT/chain.log; break; }
done
touch $OUT/CHAIN_DONE
