#!/usr/bin/env bash
# Cluster tier chain: U default / U 2K at K=25 and 1000, P default at K=1000 (and K=25), then down. Output ~/stage4-logs/seed/cluster/
H=$(cd "$(dirname "$0")" && pwd); S=~/stage4-logs/seed
for spec in "U 25 default U-k25-tdef" "U 25 50 U-k25-t50" "U 1000 default U-k1000-tdef" "U 1000 2000 U-k1000-t2000" "P 1000 default P-k1000-tdef" "P 25 default P-k25-tdef"; do
  set -- $spec; "$H/cluster-run.py" run $1 $2 $3 $4 > $S/chain-$4.out 2>&1 || echo "run $4 FAILED rc=$?" >> $S/chain.status
done
"$H/cluster-run.py" down >> $S/chain.status 2>&1; echo "chain done $(date +%T)" >> $S/chain.status
