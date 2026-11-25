#!/usr/bin/env bash
# o134 setup on the run node (B2a, B3a as amended S4-A1): three copies of the built base, the uncapped edit + ant jar,
# compile both probes, and the instrument checks. Logs everything to $R/logs/setup.log.
set -uo pipefail
R=/mydata/jingsong-cass-s4/o134; H=$R/harness; BASE=/mydata/s4/cassandra-base
mkdir -p $R/logs; exec > >(tee -a $R/logs/setup.log) 2>&1
log() { echo "+ $(date -u +%FT%TZ) [$(date +%s%3N)] $*"; }
die() { log "FAIL: $*"; exit 1; }
log "node $(hostname) arch $(uname -m) kernel $(uname -r)"; java -version 2>&1 | head -1; ant -version
for d in c509-unit c509-stock c509-uncapped; do
  [ -e $R/$d ] && die "$R/$d exists"
  log "cp -a $BASE $R/$d"; cp -a $BASE $R/$d || die "copy $d"
done
F=src/java/org/apache/cassandra/transport/ProtocolVersionTracker.java
log "uncapped edit of line 36"; sed -n 36p $R/c509-uncapped/$F
sed -i '36s/DEFAULT_MAX_CAPACITY = 100;/DEFAULT_MAX_CAPACITY = 1_000_000;/' $R/c509-uncapped/$F
sed -n 36p $R/c509-uncapped/$F | grep -q '1_000_000' || die "edit not applied"
(cd $R/c509-uncapped && diff -u $BASE/$F $F) > $R/logs/uncapped.diff; cat $R/logs/uncapped.diff
log "ant jar (uncapped)"; (cd $R/c509-uncapped && ant jar </dev/null > $R/logs/ant-jar-uncapped.log 2>&1); log "exit $?"
tail -3 $R/logs/ant-jar-uncapped.log
log "instrument check: the constant compiled into each build's jar and classes"
for d in c509-stock c509-uncapped c509-unit; do
  for cp in build/apache-cassandra-5.0.9-SNAPSHOT.jar build/classes/main; do
    v=$(javap -c -p -constants -cp $R/$d/$cp org.apache.cassandra.transport.ProtocolVersionTracker | grep -A2 'ProtocolVersionTracker();' | grep -E 'bipush|ldc|sipush' | head -1)
    log "$d $cp : $v"
  done
done
log "compile PvtProbe (unit copy)"
cd $R/c509-unit && mkdir -p s3probe/org/apache/cassandra/transport s3probe/classes && cp $H/PvtProbe.java s3probe/org/apache/cassandra/transport/
javac -cp "build/classes/main:build/lib/jars/*" -d s3probe/classes s3probe/org/apache/cassandra/transport/PvtProbe.java; log "exit $?"
log "compile StartupFlood"; mkdir -p $R/s3client && cp $H/StartupFlood.java $R/s3client/ && javac -d $R/s3client $R/s3client/StartupFlood.java; log "exit $?"
ls -l $R/c509-unit/s3probe/classes/org/apache/cassandra/transport/ $R/s3client
df -h /mydata | tail -1
log "SETUP done"
