#!/bin/bash
# Unit tier (B2e) of memtable_heap_space-adjustMemtableSize-0--autonomous: U1/U2 at 512MiB, U3 at 32MiB and 96MiB.
# Usage: bash unit-run.sh [<clone>] [<harness copy>] [<log dir>] [<out dir>]
# Environment deviations (shared host pc07): $WORK -> ~/cassandra-sai (clone), ~/stage4-sai (csv), ~/stage4-logs/sai/unit (logs).
set -u
C=${1:-$HOME/cassandra-sai}; H=${2:-$HOME/stage4-harness-run/sai}; LOG=${3:-$HOME/stage4-logs/sai/unit}; OUTD=${4:-$HOME/stage4-sai}
mkdir -p $LOG $OUTD
exec > >(tee -a $LOG/unit-run.log) 2>&1
trap "exit 1" INT TERM
echo "== $(date -Is) unit tier start; clone $C ($(git -C $C rev-parse HEAD))"
CSV=$OUTD/unit.csv
rm -f $CSV
T=$C/test/unit/org/apache/cassandra/index/sai/memory/SaiMemtableChargeTest.java
cp $H/SaiMemtableChargeTest.java $T
sha256sum $H/SaiMemtableChargeTest.java $T
# the unit JVM binds 127.0.0.1:7012; another agent's unit test on this host may hold it: wait (bounded)
waitport() { for i in $(seq 1 120); do ss -ltn | grep -q '127.0.0.1:7012\b' || return 0; echo "port 7012 busy, waiting"; sleep 10; done; echo "FAIL: 7012 busy"; exit 1; }
run() {  # $1 label, $2 L, $3 methods, $4 rows, $5 build flag
  local lab=$1 L=$2 M=$3 N=$4 NB=$5
  waitport
  echo "== $(date -Is) $lab L=$L methods=$M rows=$N"
  local mark=$LOG/.mark-$lab; touch $mark; sleep 1
  ( cd $C && ant testsome $NB -Dtest.name=org.apache.cassandra.index.sai.memory.SaiMemtableChargeTest -Dtest.methods=$M \
      -Dtest.jvm.args="-Dcassandra.config.allow_system_properties=true -Dcassandra.settings.memtable_heap_space=$L -Dcassandra.settings.memtable_allocation_type=unslabbed_heap_buffers -Dsai.rows=$N -Dsai.out=$CSV" \
      </dev/null > $LOG/ant-$lab.log 2>&1 )
  echo "ant rc=$?"
  grep -E 'Tests run|BUILD|Testsuite|Skipped|skipped' $LOG/ant-$lab.log | head
  for x in $(find $C/build/test/output -name 'TEST-org.apache.cassandra.index.sai.memory.SaiMemtableChargeTest*.xml' -newer $mark); do
    cp $x $LOG/junit-$lab.xml; grep -o '<testsuite [^>]*>' $x; grep -c '<skipped' $x | sed 's/^/skipped elements: /'; done
  echo "threshold lines:"; grep -rh 'Global memtable on-heap threshold is enabled at' $LOG/ant-$lab.log $(find $C/build/test/logs -type f -newer $mark 2>/dev/null) 2>/dev/null | sort | uniq -c
  echo "allocation type lines:"; grep -rhoE 'Memtables allocating with [a-z -]+' $LOG/ant-$lab.log $(find $C/build/test/logs -type f -newer $mark 2>/dev/null) 2>/dev/null | sort | uniq -c
  echo "leftover test JVM: $(ps -eo pid,args | grep '[j]ava' | grep cassandra-sai | grep -c SaiMemtableChargeTest)"
}
run U1U2 512MiB testChargeAndFootprint 100000 ""
run U3-32 32MiB testCapBindsSai,testCapBindsPlain 400000 -Dno-build-test=true
run U3-96 96MiB testCapBindsSai,testCapBindsPlain 400000 -Dno-build-test=true
cp $CSV $LOG/unit.csv
echo "csv lines: $(wc -l < $CSV)"
grep -E '^U1U2|^U3MAX' $CSV
rm -rf $C/build/test/cassandra
echo "== $(date -Is) unit tier end"
