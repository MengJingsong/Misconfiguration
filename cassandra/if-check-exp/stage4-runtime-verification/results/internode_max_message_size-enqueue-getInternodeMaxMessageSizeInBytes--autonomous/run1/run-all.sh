#!/usr/bin/env bash
# run 1 of internode_max_message_size-enqueue-getInternodeMaxMessageSizeInBytes--autonomous on pc12
H=~/stage4-harness-run/ime; L=~/stage4-logs/ime/run1
cd ~
echo "run1 start $(date -Is); harness md5:"; (cd $H && md5sum *)
$H/unit-run.sh run1
for l in L1M L8M DEF; do echo "lifetime $l start $(date -Is)"; IME_RUN=run1 $H/cluster-run.py $l > $L/cluster-$l.out 2>&1; echo "lifetime $l rc=$? end $(date -Is)"; done
IME_RUN=run1 $H/cluster-run.py analyze
echo "run1 end $(date -Is)"
touch $L/run1.done
