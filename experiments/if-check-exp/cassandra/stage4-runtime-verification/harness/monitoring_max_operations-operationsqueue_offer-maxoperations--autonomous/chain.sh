#!/usr/bin/env bash
# Cluster tier chain: N = 0, 50, 5000, -1, then 50 and -1 again, then down. Output ~/stage4-logs/mon/cluster/<tag>/ and ~/stage4-logs/mon/chain.status
H=$(cd "$(dirname "$0")" && pwd); S=~/stage4-logs/mon
for spec in "0 N0-r1" "50 N50-r1" "5000 N5000-r1" "-1 Nm1-r1" "50 N50-r2" "-1 Nm1-r2"; do
  set -- $spec; "$H/cluster-run.py" run $1 $2 > $S/chain-$2.out 2>&1 || echo "run $2 FAILED rc=$?" >> $S/chain.status
done
"$H/cluster-run.py" down >> $S/chain.status 2>&1; echo "chain done $(date +%T)" >> $S/chain.status
