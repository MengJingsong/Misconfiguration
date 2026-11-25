#!/bin/bash
# Case B2a + amendment A1: three build copies of /mydata/s4/cassandra-base, patched, realclean + build-test.
set -euo pipefail
W=/mydata/jingsong-cass-s4/o120
mkdir -p $W/run1 $W/s3probe
exec > >(tee -a $W/run1/build.log) 2>&1
log(){ echo "[$(date +%s%3N) $(date '+%F %T %Z')] $*"; }
run(){ log "+ $*"; "$@"; }
log "build.sh start on $(hostname) $(uname -m)"
for v in v64 v32 v1m; do run cp -a /mydata/s4/cassandra-base $W/s3probe/$v; done
run sed -i 's/int MAX_BUFFER_SIZE = 1 << 16;/int MAX_BUFFER_SIZE = 1 << 15;/' $W/s3probe/v32/src/java/org/apache/cassandra/io/util/DiskOptimizationStrategy.java
run sed -i 's/int MAX_BUFFER_SIZE = 1 << 16;/int MAX_BUFFER_SIZE = 1 << 20;/' $W/s3probe/v1m/src/java/org/apache/cassandra/io/util/DiskOptimizationStrategy.java
run grep -n "MAX_BUFFER_SIZE =" $W/s3probe/v64/src/java/org/apache/cassandra/io/util/DiskOptimizationStrategy.java $W/s3probe/v32/src/java/org/apache/cassandra/io/util/DiskOptimizationStrategy.java $W/s3probe/v1m/src/java/org/apache/cassandra/io/util/DiskOptimizationStrategy.java
grep -q "1 << 15;" $W/s3probe/v32/src/java/org/apache/cassandra/io/util/DiskOptimizationStrategy.java || { log "FAIL v32 patch"; exit 1; }
grep -q "1 << 20;" $W/s3probe/v1m/src/java/org/apache/cassandra/io/util/DiskOptimizationStrategy.java || { log "FAIL v1m patch"; exit 1; }
grep -q "1 << 16;" $W/s3probe/v64/src/java/org/apache/cassandra/io/util/DiskOptimizationStrategy.java || { log "FAIL v64 stock"; exit 1; }
for v in v64 v32 v1m; do
  cd $W/s3probe/$v
  t0=$(date +%s)
  run ant realclean </dev/null
  run ant build-test </dev/null
  log "built $v in $(( $(date +%s) - t0 )) s"
done
log "BUILD-ALL-OK"
