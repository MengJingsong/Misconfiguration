#!/bin/bash
# Unit tier (B2e) of memtable_heap_space-needsCleaning-nextClean--autonomous.
# Usage: bash unit-run.sh <clone> <harness dir> <log dir>
set -u
C=${1:-$HOME/cassandra-ncl}; H=${2:-$HOME/stage4-harness-run/ncl}; LOG=${3:-$HOME/stage4-logs/ncl}
mkdir -p $LOG
exec > >(tee -a $LOG/unit-run.log) 2>&1
echo "== $(date -Is) unit tier start; clone $C ($(git -C $C rev-parse HEAD))"
set -x
cp $H/NextCleanBoundaryTest.java $C/test/unit/org/apache/cassandra/utils/memory/
sha256sum $C/test/unit/org/apache/cassandra/utils/memory/NextCleanBoundaryTest.java
cd $C && ant testsome -Dtest.name=org.apache.cassandra.utils.memory.NextCleanBoundaryTest </dev/null > $LOG/unit-ant.log 2>&1
rc=$?
set +x
echo "ant rc=$rc"
grep -h 'NCB ' $LOG/unit-ant.log > $LOG/unit-ncb.txt
cp $C/build/test/output/TEST-org.apache.cassandra.utils.memory.NextCleanBoundaryTest.xml $LOG/ 2>/dev/null
grep -E 'Tests run|BUILD' $LOG/unit-ant.log
echo "leftover:"; ps -eo pid,args | grep '[j]ava' | grep NextCleanBoundaryTest || echo none
echo "== $(date -Is) unit tier end"
