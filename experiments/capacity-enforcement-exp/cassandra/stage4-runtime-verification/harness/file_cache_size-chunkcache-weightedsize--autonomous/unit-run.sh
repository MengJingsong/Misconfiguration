#!/usr/bin/env bash
# Unit tier (B2e) of file_cache_size-chunkcache-weightedsize--autonomous, as amended (AM6, AM7). Run on the node:
#   bash unit-run.sh <phase>   phase = build | runs
# Tree: /mydata/jingsong-cass-s4/o05/src. Logs: /mydata/jingsong-cass-s4/o05/logs/unit/. Every command and its output is logged.
set -uo pipefail
B=/mydata/jingsong-cass-s4/o05
T=$B/src
L=$B/logs/unit
H=$(cd "$(dirname "$0")" && pwd)
mkdir -p $L
exec > >(tee -a $L/session.log) 2>&1
run() { echo "[$(date -u +%FT%TZ) $(date +%s%3N)] + $*"; "$@"; local rc=$?; echo "  rc=$rc"; return $rc; }
cd $T || exit 1
case "${1:-}" in
build)
  run cp $H/ChunkCacheCapTest.java test/unit/org/apache/cassandra/io/util/ChunkCacheCapTest.java || exit 1
  run md5sum $H/ChunkCacheCapTest.java test/unit/org/apache/cassandra/io/util/ChunkCacheCapTest.java
  run ant build-test </dev/null > $L/build-test.log 2>&1; rc=$?
  tail -5 $L/build-test.log; exit $rc ;;
runs)
  for N in 32 33 64 128 256; do
    run ant testsome -Dno-build-test=true -Dtest.name=org.apache.cassandra.io.util.ChunkCacheCapTest \
        "-Dtest.jvm.args=-Dfcs.mib=$N -Xmx2G -XX:MaxDirectMemorySize=2G" </dev/null > $L/unit-$N.log 2>&1
    grep -E 'O05 (FINAL|EVID|instance)|Tests run|BUILD' $L/unit-$N.log
  done
  run ant testsome -Dno-build-test=true -Dtest.name=org.apache.cassandra.io.util.ChunkCacheCapTest \
      "-Dtest.jvm.args=-Dfcs.mib=64 -Dhold.chunks=1024 -Xmx2G -XX:MaxDirectMemorySize=2G" </dev/null > $L/unit-probe.log 2>&1
  grep -E 'O05 (FINAL|EVID)|Tests run|BUILD' $L/unit-probe.log
  echo "== extract"; grep -h 'O05 FINAL\|O05 EVID\|O05 instance' $L/unit-*.log
  echo "== leftovers"; ls build/tmp/o05*.bin 2>&1; ps -eo pid,cmd | grep '[C]hunkCacheCapTest' || echo "no ChunkCacheCapTest process"
  echo "UNIT RUNS DONE" ;;
*) echo "usage: unit-run.sh build|runs"; exit 2 ;;
esac
