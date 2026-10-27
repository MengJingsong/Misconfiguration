#!/bin/bash
# Usage: LC_TREE=<tree> lcmt_chain.sh <outdir>   -- the whole cluster tier: two fixture builds (in parallel, slot 5 .1 and .2), then
# LCS and STCS-control runs for N = 32, 4, 64, 16 (alternating). Stops at the first failed step.
set -u
H=$(cd "$(dirname "$0")" && pwd); OUT=${1:?outdir}; : "${LC_TREE:?}"; export LC_TREE LC_OUT=$OUT
MNT=${LC_MNT:-/mnt/s4lc}
mkdir -p "$OUT"
sudo mkdir -p "$MNT" && (mountpoint -q "$MNT" || sudo mount -t tmpfs -o size=40g tmpfs "$MNT") && sudo chown "$(id -u):$(id -g)" "$MNT" || exit 1
echo "$(date -Is) chain start"
if [ -z "${LC_SKIP_BUILD:-}" ]; then   # run 2 sets LC_SKIP_BUILD=1 (and LC_SAMPLER=v2): same fixtures, new runs
python3 "$H/lcmt_cluster.py" build lcs > "$OUT/build-lcs.out" 2>&1 & p1=$!
python3 "$H/lcmt_cluster.py" build stcs > "$OUT/build-stcs.out" 2>&1 & p2=$!
wait $p1; r1=$?; wait $p2; r2=$?
echo "$(date -Is) builds rc lcs=$r1 stcs=$r2"
[ $r1 -eq 0 ] && [ $r2 -eq 0 ] || { echo "CHAIN FAILED in build"; exit 1; }
fi
for N in ${LC_NS:-32 4 64 16}; do
  for role in lcs stcs; do
    echo "$(date -Is) run $role N=$N"
    python3 "$H/lcmt_cluster.py" run $role $N > "$OUT/run-$role-N$N.out" 2>&1 || { echo "CHAIN FAILED in run $role N=$N"; exit 1; }
  done
done
echo "$(date -Is) CHAIN DONE"
