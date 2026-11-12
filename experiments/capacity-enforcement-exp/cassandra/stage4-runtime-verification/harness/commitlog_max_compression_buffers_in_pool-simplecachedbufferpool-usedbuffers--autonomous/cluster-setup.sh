#!/usr/bin/env bash
# One-time cluster-tier setup on apt138 (B3a as amended by M4). Run after the unit tier (no ant runs in parallel).
# Builds stress in the build tree if missing, copies the built tree to the node tree, keeps the original yaml,
# moves JMX to 7499, compiles the JMX poller. Log: /mydata/jingsong-cass-s4/o45/logs/cluster-setup.log
set -euo pipefail
B=/mydata/jingsong-cass-s4/o45; H=$B/harness
exec > >(tee -a $B/logs/cluster-setup.log) 2>&1
echo "cluster-setup $(date -u +%FT%TZ)"
cd $B/src
if ! ls build/classes/stress/org >/dev/null 2>&1; then echo "+ ant stress-build"; ant stress-build < /dev/null | tail -3; fi
[ ! -e $B/node ] || { echo "$B/node exists"; exit 1; }
cp -a $B/src $B/node
rm -rf $B/node/build/test/cassandra $B/node/data $B/node/logs
cp $B/node/conf/cassandra.yaml $B/node/conf/cassandra.yaml.orig
sed -i 's/^JMX_PORT="7199"/JMX_PORT="7499"/' $B/node/conf/cassandra-env.sh
grep -n '^JMX_PORT=' $B/node/conf/cassandra-env.sh
mkdir -p $B/harness-classes && javac -d $B/harness-classes $H/O45Jmx.java && ls $B/harness-classes
ls $B/node/build/classes/stress | head -3
echo "done $(date -u +%FT%TZ)"
