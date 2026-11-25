#!/bin/bash
# o124 unit tier driver (B2e), logs every command. Usage: run-unit.sh  (WORK must be set)
set -u
: "${WORK:?}"
cd $WORK/src || exit 1
FE=src/java/org/apache/cassandra/net/FrameEncoder.java
T=org.apache.cassandra.transport.FrameMaxSizeProbeTest
log(){ echo "+ [$(date +%s%3N)] $*"; }
runone(){ # $1=tag
  log "sed -n 41p $FE"; sed -n 41p $FE
  log "ant clean"; ant clean </dev/null > $WORK/logs/unit-$1-clean.log 2>&1; tail -2 $WORK/logs/unit-$1-clean.log
  log "ant testsome -Dtest.name=$T"; ( time ant testsome -Dtest.name=$T </dev/null ) > $WORK/logs/unit-$1-testsome.log 2>&1
  tail -8 $WORK/logs/unit-$1-testsome.log
  $WORK/harness/extract-probe.sh $WORK/logs/unit-$1-testsome.log | grep . | tee $WORK/unit-$1.txt   # defect D1 fix
  cp build/test/output/TEST-$T.xml $WORK/logs/TEST-unit-$1.xml
  [ -s $WORK/unit-$1.txt ] || { echo "NO PROBE OUTPUT for $1"; exit 2; }
}
mkdir -p $WORK/logs
log "cp test file"; cp $WORK/harness/FrameMaxSizeProbeTest.java test/unit/org/apache/cassandra/transport/
runone M17
log "sed 1<<17 -> 1<<16"; sed -i '41s/1 << 17/1 << 16/' $FE
runone M16
log "sed 1<<16 -> 1<<15"; sed -i '41s/1 << 16/1 << 15/' $FE
runone M15
log "restore 1<<15 -> 1<<17"; sed -i '41s/1 << 15/1 << 17/' $FE; sed -n 41p $FE
log "ant clean jar"; ( time ant clean jar </dev/null ) > $WORK/logs/unit-restore-jar.log 2>&1; tail -5 $WORK/logs/unit-restore-jar.log
log "leftover check"; ps -eo pid,cmd | grep '[F]rameMaxSizeProbeTest' || echo "no FrameMaxSizeProbeTest JVM left"
log "unit done"
