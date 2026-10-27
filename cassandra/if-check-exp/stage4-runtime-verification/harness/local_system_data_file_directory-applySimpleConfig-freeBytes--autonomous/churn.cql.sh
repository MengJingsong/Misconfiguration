#!/usr/bin/env bash
# Schema churn for the cluster tier: passes of 200 CREATE TABLE then 200 DROP TABLE through one cqlsh -f each, until $STOPFLAG exists or $MAXS seconds pass.
# Usage: churn.cql.sh <tree> <ip> <outdir> <stopflag> <max-seconds>
T=$1; IP=$2; O=$3; STOP=$4; MAXS=$5
mkdir -p "$O"; cd "$T" || exit 1
{ echo "CREATE KEYSPACE IF NOT EXISTS churnks WITH replication={'class':'SimpleStrategy','replication_factor':1};"
  for i in $(seq 1 200); do echo "CREATE TABLE IF NOT EXISTS churnks.t$i (k int PRIMARY KEY, v text);"; done; } > "$O/create.cql"
{ for i in $(seq 1 200); do echo "DROP TABLE IF EXISTS churnks.t$i;"; done; } > "$O/drop.cql"
END=$(( $(date +%s) + MAXS )); P=0
while [ ! -e "$STOP" ] && [ $(date +%s) -lt $END ]; do
  P=$((P+1))
  bin/cqlsh --request-timeout=120 "$IP" 9042 -f "$O/create.cql" > "$O/pass$P.create.out" 2>&1; rc1=$?
  bin/cqlsh --request-timeout=120 "$IP" 9042 -f "$O/drop.cql" > "$O/pass$P.drop.out" 2>&1; rc2=$?
  echo "$(date +%s%3N) pass=$P create_rc=$rc1 drop_rc=$rc2 create_err_lines=$(grep -c -i 'error\|timeout' "$O/pass$P.create.out") drop_err_lines=$(grep -c -i 'error\|timeout' "$O/pass$P.drop.out")" >> "$O/churn.log"
done
echo "churn done passes=$P" >> "$O/churn.log"
