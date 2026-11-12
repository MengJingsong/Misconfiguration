#!/usr/bin/env bash
# Stage 4 unit tier (B2e as amended M1) for commitlog_max_compression_buffers_in_pool-...-bufferpool--autonomous.
# usage: unit-run.sh <outdir>   (background job; logs every command)
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd)
SRC=/mydata/jingsong-cass-s4/o44/src
OUT=${1:?outdir}
mkdir -p "$OUT"
exec > >(tee -a "$OUT/session.log") 2>&1
run() { echo "+ $*"; "$@"; local rc=$?; echo "rc=$rc"; return $rc; }
echo "start unit $(date -u +%FT%TZ)"
cd "$SRC" || exit 1
md5sum "$H"/*.java "$H"/*.sh
run cp "$H/PoolCapManagerTest.java" "$H/PoolQueueCapacityTest.java" test/unit/org/apache/cassandra/db/commitlog/ || exit 1
run ant build-test </dev/null > "$OUT/build-test.log" 2>&1; tail -3 "$OUT/build-test.log"
grep -q "BUILD SUCCESSFUL" "$OUT/build-test.log" || { echo "STOP: build-test failed"; exit 1; }
BM="-Dtest.jvm.args=-Dorg.jboss.byteman.contrib.bmunit.agent.port=9491"
for N in 3 5 8; do
  for C in PoolCapManagerTest PoolQueueCapacityTest; do
    echo "=== N=$N $C $(date -u +%FT%TZ)"
    CAP_N=$N ant testsome -Dno-build-test=true "$BM" -Dtest.name=org.apache.cassandra.db.commitlog.$C </dev/null > "$OUT/ant-$C-$N.log" 2>&1
    echo "ant rc=$?"; grep -E "Tests run|BUILD" "$OUT/ant-$C-$N.log"
    T=build/test/logs/_jdk11/TEST-org.apache.cassandra.db.commitlog.$C.log
    [ -f "$T" ] || T=$(ls -t build/test/logs/*/TEST-org.apache.cassandra.db.commitlog.$C.* 2>/dev/null | head -1)
    run cp "$T" "$OUT/test-$C-$N.log"
    grep "O44" "$OUT/test-$C-$N.log"
  done
done
echo "leftover JVMs:"; ps -eo pid,cmd | grep -E "[P]oolCapManagerTest|[P]oolQueueCapacityTest" || echo none
echo "end unit $(date -u +%FT%TZ)"
