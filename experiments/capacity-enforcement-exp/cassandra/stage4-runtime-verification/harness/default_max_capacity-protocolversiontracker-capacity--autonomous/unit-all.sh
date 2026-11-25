#!/usr/bin/env bash
# o134 unit tier (B2e as amended S4-A1/S4-A2): shakedown (known answers), then 3 x each (capacity, N), then ProtocolVersionTrackerTest.
set -uo pipefail
R=/mydata/jingsong-cass-s4/o134; T=$R/c509-unit; OUT=$R/unit; mkdir -p $OUT
exec > >(tee -a $OUT/session.log) 2>&1
log() { echo "+ $(date -u +%FT%TZ) [$(date +%s%3N)] $*"; }
cd $T
CP="s3probe/classes:build/classes/main:build/lib/jars/*"
JOPTS="-Xms4g -Xmx4g -XX:+UseG1GC"
run() {  # label cap n
  log "RUN $1: java $JOPTS ... PvtProbe $2 $3"
  local t0=$(date +%s%3N)
  java $JOPTS -cp "$CP" org.apache.cassandra.transport.PvtProbe $2 $3 > $OUT/$1.out 2> $OUT/$1.err; local rc=$?
  log "exit $rc in $(( $(date +%s%3N) - t0 )) ms"; cat $OUT/$1.out; grep -v -E '^(WARN|INFO|DEBUG)' $OUT/$1.err | head -5
  { echo "## $1 rc=$rc"; cat $OUT/$1.out; } >> $OUT/results.txt
}
log "shakedown: known answers cap=100 N=50 -> 50; cap=MAX N=101 -> 101"
run shake-c100-n50 100 50
run shake-cmax-n101 2147483647 101
for r in 1 2 3; do
  for cap in 100 1000 2147483647; do
    for n in 50 100 101 1000 10000 1000000; do run c$cap-n$n-r$r $cap $n; done
  done
done
log "ant testsome ProtocolVersionTrackerTest"
ant testsome -Dtest.name=org.apache.cassandra.transport.ProtocolVersionTrackerTest </dev/null > $OUT/ant-testsome.log 2>&1; log "exit $?"
grep -E 'Tests run|BUILD|testsome' $OUT/ant-testsome.log | tail -5
pgrep -u $(id -u) -f PvtProbe >/dev/null && log "LEFTOVER PvtProbe" || log "no PvtProbe"
log "UNIT done"
