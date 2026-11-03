#!/usr/bin/env bash
# Unit tier (B2, as amended 2026-10-25) of coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous.
# usage: unit-run.sh <outdir-name> <run|shakedown>
# Copies ReadSizeCapUnitTest.java into the clone $C (default $W/cassandra-run22), runs one ant testsome (one forked JVM),
# then removes the copied test. Output: $W/logs/coordinator_read_size_fail_threshold-validateReadThresholds/unit-<outdir>/
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run22}
RUN=${1:?outdir}; MODE=${2:?run|shakedown}
L=$W/logs/coordinator_read_size_fail_threshold-validateReadThresholds/unit-$RUN
[ -e "$L" ] && mv "$L" "$L.attempt-$(date +%s)"
mkdir -p "$L"; CL=$L/commands.log; : > "$CL"
d=$(ps -eo command | grep '[C]assandraDaemon'); [ -n "$d" ] && { echo "ABORT: a Cassandra node is running" | tee "$L/summary.txt"; exit 1; }
T=$C/test/unit/org/apache/cassandra/cql3
cp "$H/ReadSizeCapUnitTest.java" "$T/"
{ echo "unit-run $RUN mode $MODE date $(date '+%F %T %z')"; echo "clone $C: $(git -C $C describe --tags) $(git -C $C rev-parse HEAD)"
  echo "harness sha256: $(shasum -a 256 "$H/ReadSizeCapUnitTest.java" | cut -c1-16)"; } | tee "$L/summary.txt"
cd "$C"
CMD="ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.cql3.ReadSizeCapUnitTest -Dtest.jvm.args=-Dstage4.out=$L/stage4.out -Dstage4.mode=$MODE"
echo "[$(date '+%F %T')] + $CMD" >> "$CL"
ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.cql3.ReadSizeCapUnitTest \
    -Dtest.jvm.args="-Dstage4.out=$L/stage4.out -Dstage4.mode=$MODE" > "$L/ant.log" 2>&1
rc=$?
echo "[$(date '+%F %T')]   exit=$rc" >> "$CL"
echo "ant rc=$rc; $(grep -m1 'Tests run' "$L/ant.log" || echo 'no Tests run line')" | tee -a "$L/summary.txt"
cp build/test/output/TEST-org.apache.cassandra.cql3.ReadSizeCapUnitTest*.xml "$L/" 2>/dev/null
cp build/test/logs/*/TEST-org.apache.cassandra.cql3.ReadSizeCapUnitTest*.log "$L/" 2>/dev/null
rm -f "$T/ReadSizeCapUnitTest.java"
echo "STAGE4 lines: $(grep -c '^STAGE4' "$L/stage4.out" 2>/dev/null || echo 0)" | tee -a "$L/summary.txt"
grep '^STAGE4' "$L/stage4.out" >> "$L/summary.txt" 2>/dev/null
echo "clone status after: $(git -C $C status --porcelain | tr '\n' ';')" | tee -a "$L/summary.txt"
d=$(ps -eo command | grep '[C]assandraDaemon'); echo "CassandraDaemon after: ${d:-none}" | tee -a "$L/summary.txt"
echo "done $(date '+%F %T %z')" | tee -a "$L/summary.txt"
