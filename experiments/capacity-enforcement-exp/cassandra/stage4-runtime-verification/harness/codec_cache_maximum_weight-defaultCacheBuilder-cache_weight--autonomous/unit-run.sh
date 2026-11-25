#!/bin/bash
# Stage-4 unit tier (B2e) for order 96. Runs on pc72 in $W/unit (patched copy).
# Every command and its output goes to $LOG; the run stops at the first failed step.
set -uo pipefail
W=/mydata/jingsong-cass-s4/o96
U=$W/unit
OUT=$W/raw/unit
LOG=$OUT/command.log
mkdir -p $OUT
exec > >(tee -a $LOG) 2>&1
T=org.apache.cassandra.cql3.functions.types.CodecCacheWeightProbeTest
echo "=== unit-run start $(date -u +%FT%TZ) epoch_ms=$(date +%s%3N) host=$(hostname) arch=$(uname -m)"

run() {   # run <tag> <method> <jvmargs>
  local tag=$1 meth=$2 args=$3
  echo "--- RUN $tag method=$meth jvmargs='$args' start=$(date -u +%FT%TZ)"
  rm -rf $U/build/test/output/TEST-$T-$meth.* 2>/dev/null
  ( cd $U && echo "+ ant testsome -Dtest.name=$T -Dtest.methods=$meth -Dtest.jvm.args=\"$args\"" && \
    ant testsome -Dtest.name=$T -Dtest.methods=$meth -Dtest.jvm.args="$args" </dev/null ) > $OUT/ant-$tag.log 2>&1
  local rc=$?
  cp $U/build/test/output/TEST-$T-$meth.xml $OUT/TEST-$tag.xml 2>/dev/null
  # S4-D1: the test JVM's System.out goes through a logger that splits one printf into tokens,
  # one log line each; join the tokens of the Standard Output block and split at "PROBE ".
  awk -F'SubstituteLogger.java:222 - ' 'NF>1{printf "%s", $2} END{print ""}' $OUT/ant-$tag.log \
    | sed 's/PROBE /\nPROBE /g' | grep '^PROBE' | sed "s/^/$tag | /" | tee $OUT/probe-$tag.txt
  grep -E 'BUILD (SUCCESSFUL|FAILED)|Tests run:' $OUT/ant-$tag.log | sed "s/^/$tag | /"
  if [ $rc -ne 0 ] || ! grep -q 'BUILD SUCCESSFUL' $OUT/ant-$tag.log || grep -qE 'Failures: [1-9]|Errors: [1-9]' $OUT/ant-$tag.log; then
    echo "!!! STOP: $tag failed (rc=$rc); see $OUT/ant-$tag.log"; exit 1
  fi
}

STEP=${1:-all}
if [ "$STEP" = smoke ]; then run smoke-narrow-k500 narrow "-Dprobe.k=500"; exit 0; fi

# B2e step 2: stock-equivalent (property unset = 1000), 3 repetitions each
for rep in 1 2 3; do
  for K in 500 1000 2000 5000; do run A-cap1000-k$K-r$rep narrow "-Dprobe.k=$K"; done
  run B-cap1000-r$rep zeroWeight ""
  for M in 1 1000 10000; do run C-cap1000-m$M-k2000-r$rep wide "-Dprobe.m=$M -Dprobe.k=2000"; done
done
# B2e step 3: knob runs (positive control on the cache's own operand), 3 repetitions each
for rep in 1 2 3; do
  run A-cap100-k2000-r$rep narrow "-Dcassandra.test.codec_cache_max_weight=100 -Dprobe.k=2000"
  run A-cap10000-k12000-r$rep narrow "-Dcassandra.test.codec_cache_max_weight=10000 -Dprobe.k=12000"
  run C-cap100-m1000-k2000-r$rep wide "-Dcassandra.test.codec_cache_max_weight=100 -Dprobe.m=1000 -Dprobe.k=2000"
  run C-cap10000-m1000-k2000-r$rep wide "-Dcassandra.test.codec_cache_max_weight=10000 -Dprobe.m=1000 -Dprobe.k=2000"
done
echo "=== unit-run end $(date -u +%FT%TZ)"
ps -eo pid,cmd | grep -E '[j]unit|[C]assandraDaemon' || echo "no junit/CassandraDaemon process left"
