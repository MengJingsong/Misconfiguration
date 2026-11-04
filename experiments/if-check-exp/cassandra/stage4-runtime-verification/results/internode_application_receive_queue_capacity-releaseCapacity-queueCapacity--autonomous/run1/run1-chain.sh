# run 1 of internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous: unit tier, then the cluster tier
H=~/stage4-harness-run/rrc
echo "CHAIN start $(date -Is)"
bash $H/unit-run.sh run1 all
echo "UNIT-DONE $(date -Is)"
for l in s1q64k s1q4m-1 s1q32m s1q4m-2 s2q64k s2q4m s2q32m s1q4m-3 ctla-q64k ctla-q32m ctlb ctlc; do
  echo "LABEL $l $(date -Is)"
  RRC_RUN=run1 python3 $H/cluster-run.py $l
  echo "LABEL $l exit $? $(date -Is)"
done
RRC_RUN=run1 python3 $H/cluster-run.py analyze
echo "CHAIN-DONE $(date -Is)"
