#!/bin/bash
# Case B2e + amendment A6: run the probe in each copy, rejoin the split stdout pieces.
set -euo pipefail
W=/mydata/jingsong-cass-s4/o120; H=$W/harness; O=$W/run1/unit
mkdir -p $O
exec > >(tee -a $O/unit-run.log) 2>&1
log(){ echo "[$(date +%s%3N) $(date '+%F %T %Z')] $*"; }
run(){ log "+ $*"; "$@"; }
for v in v64 v32 v1m; do
  run cp $H/MaxBufferSizeProbeTest.java $W/s3probe/$v/test/unit/org/apache/cassandra/io/util/
  cd $W/s3probe/$v
  log "+ ant testsome -Dtest.name=org.apache.cassandra.io.util.MaxBufferSizeProbeTest > $O/unit-$v.log"
  set +e
  ant testsome -Dtest.name=org.apache.cassandra.io.util.MaxBufferSizeProbeTest </dev/null > $O/unit-$v.log 2>&1
  rc=$?
  set -e
  log "ant rc=$rc for $v"
  for x in $W/s3probe/$v/build/test/output/TEST-org.apache.cassandra.io.util.MaxBufferSizeProbeTest*.xml; do [ -f "$x" ] && cp "$x" $O/TEST-probe-$v-$(basename "$x"); done || true
  python3 -I $H/rejoin.py $O/unit-$v.log > $O/probe-$v.txt
  run cat $O/probe-$v.txt
  [ $rc -eq 0 ] || { log "FAIL: ant testsome failed for $v"; exit 1; }
  [ $(grep -c '^PROBE strategy=' $O/probe-$v.txt) -eq 16 ] || { log "FAIL: expected 16 PROBE rows for $v"; exit 1; }
done
log "UNIT-ALL-OK"
