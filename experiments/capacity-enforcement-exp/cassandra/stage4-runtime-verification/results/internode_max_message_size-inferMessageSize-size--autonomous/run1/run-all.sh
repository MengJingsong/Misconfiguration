#!/usr/bin/env bash
# run 1 of internode_max_message_size-inferMessageSize-size--autonomous: unit tier, then the cluster tier, then analyze
set -u
H=/proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/stage4-runtime-verification/harness/internode_max_message_size-inferMessageSize-size--autonomous
export CASSANDRA_HOME=$HOME/cassandra-run5 IMM_RUN=run1
echo "run-all start $(date -Is)"
$H/unit-run.sh run1
for rep in 1 2; do for l in R0 R1 R2 R3; do
  echo "lifetime $l-$rep start $(date -Is)"
  $H/cluster-run.py $l $rep > $HOME/stage4-logs/imm/run1/$l-$rep.out 2>&1
  rc=$?; echo "lifetime $l-$rep exit=$rc $(date -Is) $(grep '^EXPECTED totals' $HOME/stage4-logs/imm/run1/cluster/$l-$rep/summary.txt)"
  [ $rc -eq 0 ] || { echo "STOP: lifetime $l-$rep failed"; $H/cluster-run.py down; exit 1; }
done; done
$H/cluster-run.py analyze
echo "run-all end $(date -Is)"
