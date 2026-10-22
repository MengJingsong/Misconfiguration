#!/bin/bash
# Runs the four B3 arms one after another, control first (B3e): 8192, 128, 256, 512 MiB.
OUT=${1:?outroot}; N=${2:-1000000}; shift 2 || true
ARMS=("$@"); [ ${#ARMS[@]} -eq 0 ] && ARMS=(8192 128 256 512)
mkdir -p $OUT
H=$HOME/stage4-harness-run/cl2
echo "EXPECTED: B3f (S=32 MiB, du apparent): 128 peak<=256MiB settled<=128 CLD>=5 | 256 peak<=384 settled<=256 CLD>=3 | 512 peak<=640 settled<=512 CLD>=1 | 8192 ~1.0-1.1GiB rising, settled~peak, CLD=0 | MEMTABLE_LIMIT 0 everywhere; du ~ metric +-1 segment" | tee -a $OUT/chain.log
for a in "${ARMS[@]}"; do
  echo "[$(date +%FT%T)] arm $a" >> $OUT/chain.log
  bash $H/cluster-run.sh $OUT $a $N >> $OUT/chain.log 2>&1
  [ -f $OUT/$a/DONE ] || { echo "arm $a did not finish" >> $OUT/chain.log; break; }
done
touch $OUT/CHAIN_DONE
