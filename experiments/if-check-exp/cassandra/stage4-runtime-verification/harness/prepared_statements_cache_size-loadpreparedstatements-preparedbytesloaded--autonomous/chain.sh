#!/usr/bin/env bash
# Cluster tier chain: seed once, then the measured starts (caps 1, 4, 10 MiB x arms A, B; the 1 MiB pair once more), then `down`.
# Output ~/stage4-logs/pthr/cluster/<tag>/ and ~/stage4-logs/pthr/chain.status
H=$(cd "$(dirname "$0")" && pwd); S=~/stage4-logs/pthr; mkdir -p $S/cluster
"$H/cluster-run.py" seed 20000 > $S/chain-seed.out 2>&1 || { echo "seed FAILED rc=$?" >> $S/chain.status; exit 1; }
for spec in "A 1 A-cap1-r1" "B 1 B-cap1-r1" "A 4 A-cap4-r1" "B 4 B-cap4-r1" "A 10 A-cap10-r1" "B 10 B-cap10-r1" "A 1 A-cap1-r2" "B 1 B-cap1-r2"; do
  set -- $spec
  "$H/cluster-run.py" run $1 $2 $3 > $S/chain-$3.out 2>&1 || echo "run $3 FAILED rc=$?" >> $S/chain.status
done
"$H/cluster-run.py" down >> $S/chain.status 2>&1; echo "chain done $(date +%T)" >> $S/chain.status
