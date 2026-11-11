#!/usr/bin/env bash
# run 1 cluster tier: the four knob values in sequence (1 MiB with the restart check), then `down`. Output ~/stage4-logs/psc/cluster/k<MiB>/
H=$(cd "$(dirname "$0")" && pwd)
for v in "1 restart" 4 16 64; do "$H/cluster-run.py" $v > ~/stage4-logs/psc/chain-${v%% *}.out 2>&1 || echo "value $v FAILED rc=$?" >> ~/stage4-logs/psc/chain.status; done
"$H/cluster-run.py" down >> ~/stage4-logs/psc/chain.status 2>&1; echo "chain done $(date +%T)" >> ~/stage4-logs/psc/chain.status
