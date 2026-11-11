#!/usr/bin/env bash
# run 1, cluster tier restarted after defects 3 (node A out of heap in L1M; B3e step 4 in its own lifetime L1MC) and 4 (Jmx poll ERR field)
H=~/stage4-harness-run/ime; L=~/stage4-logs/ime/run1
cd ~
echo "run1 cluster (attempt 3) start $(date -Is); harness md5:"; (cd $H && md5sum *)
for l in L1M L1MC L8M DEF; do echo "lifetime $l start $(date -Is)"; IME_RUN=run1 $H/cluster-run.py $l > $L/cluster-$l.out 2>&1; echo "lifetime $l rc=$? end $(date -Is)"; done
IME_RUN=run1 $H/cluster-run.py analyze
echo "run1 cluster end $(date -Is)"
touch $L/run1.done
