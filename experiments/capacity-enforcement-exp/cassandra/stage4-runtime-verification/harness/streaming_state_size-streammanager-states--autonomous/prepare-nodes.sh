#!/usr/bin/env bash
# Make the two node trees for the cluster tier: cp -a of the built tree (B3a, S4-A5); keeps pristine conf copies.
set -euo pipefail
B=/mydata/jingsong-cass-s4/o53
for k in 1 2; do
  [ -d $B/n$k ] || cp -a $B/src $B/n$k
  cp -n $B/n$k/conf/cassandra.yaml $B/n$k/conf/cassandra.yaml.orig
  cp -n $B/n$k/conf/cassandra-env.sh $B/n$k/conf/cassandra-env.sh.orig
  ls $B/n$k/build/apache-cassandra-*.jar
done
