#!/usr/bin/env bash
# Cluster tier, run 1: arm M (main), then C48 and C96 (controls on M's data). On the node:  bash run-all.sh
set -u
ulimit -n 100000
export CM_RUN=${CM_RUN:-run1}
H=$(cd "$(dirname "$0")" && pwd)
mkdir -p $HOME/s4-cm-logs
for a in M C48 C96; do python3 -I $H/cluster-run.py $a > $HOME/s4-cm-logs/$CM_RUN-$a.out 2>&1; echo "$a rc=$? $(date -u +%FT%TZ)" >> $HOME/s4-cm-logs/$CM_RUN-all.log; done
echo ALLDONE >> $HOME/s4-cm-logs/$CM_RUN-all.log
