#!/usr/bin/env bash
# Stage 4 run 1, unit tier: cdc_total_space-deleteOldLinkedCDCCommitLogSegment-bytesToFree--autonomous, case B2.
#   unit-run.sh check   instrument check only (n=48 blocking, volume 96 MiB; not in the design's matrix, not a reading)
#   unit-run.sh all     the matrix: blocking and non-blocking x n=64,128,256,512 x 3 repeats, plus the B2h controls
# Run on the measured node from a local clone (CLONE) and a copy of the harness (HARNESS, with SHA256SUMS).
# One folder per JVM under $L: ant.txt, junit.xml, readings.txt (the test's STAGE4 lines), cdc-verdict.txt (Byteman trace).
set -uo pipefail
HARNESS=${HARNESS:-$HOME/stage4-harness-run/cdc2}
C=${CLONE:-$HOME/cassandra-cdc}
L=${LOGDIR:-$HOME/stage4-logs/cdc2/unit}
T=test/unit/org/apache/cassandra/db/commitlog
CLASS=org.apache.cassandra.db.commitlog.CdcCapProbeTest
mkdir -p "$L"; S=$L/summary.txt
exec > >(tee -a "$L/session.log") 2>&1
log() { echo "[$(date '+%F %T')] $*"; }
fail() { log "FAIL: $*"; exit 3; }
cd "$C" || fail "no clone"
[ "$(git describe --tags)" = cassandra-5.0.9 ] || fail "clone not at cassandra-5.0.9"
pgrep -f '[C]assandraDaemon' > /dev/null && fail "a CassandraDaemon is running"
( cd "$HARNESS" && sha256sum -c SHA256SUMS ) || fail "harness copy differs"
cp "$HARNESS/CdcCapProbeTest.java" "$T/CdcCapProbeTest.java"
cmp "$HARNESS/CdcCapProbeTest.java" "$T/CdcCapProbeTest.java" || fail "test copy differs"
log "unit yaml segment size: $(grep -E '^commitlog_segment_size' test/conf/cassandra.yaml); df: $(df -h --output=avail "$HOME" | tail -1)"

jvm() {   # label, then key=value test settings
  local label=$1; shift
  local d=$L/$label args="" kv
  rm -rf "$d"; mkdir -p "$d"
  for kv in "$@"; do args="$args -Dstage4.cdc.$kv"; done
  args="$args -Dstage4.unit.out=$d/readings.txt -javaagent:$C/build/lib/jars/byteman-4.0.20.jar=script:$HARNESS/cdc-verdict.btm -Dstage4.byteman.out=$d/cdc-verdict.txt"
  log "=== $label: $args"
  rm -f build/test/output/TEST-$CLASS*.xml
  ant testsome -Dtest.name=$CLASS -Dtest.jvm.args="$args" > "$d/ant.txt" 2>&1 < /dev/null
  local rc=$?
  cp build/test/output/TEST-$CLASS*.xml "$d/junit.xml" 2> /dev/null
  local line; line=$(grep -E 'Testsuite:.*Tests run:|Tests run:.*Time elapsed' "$d/ant.txt" | head -1)
  echo "$label ant_exit=$rc $line | $(grep -h ' RESULT ' "$d/readings.txt" 2> /dev/null | sed -E 's/^ms=[0-9]+ //')" | tee -a "$S"
  [ -s "$d/readings.txt" ] || fail "$label produced no readings"
  rm -rf build/test/cassandra/data* build/test/cassandra/commitlog* build/test/cassandra/cdc_raw* 2> /dev/null
  du -sh build/test/cassandra 2> /dev/null | sed 's/^/    test dir: /'
}

case ${1:-} in
  check)
    jvm check-b48 totalSpaceMiB=48 mode=blocking volumeMiB=96 ;;
  all)
    for r in 1 2 3; do
      for n in 64 128 256 512; do
        jvm "b$n-r$r"  totalSpaceMiB=$n mode=blocking
        jvm "nb$n-r$r" totalSpaceMiB=$n mode=nonblocking
      done
    done
    # B2h controls
    jvm ctl-b4096  totalSpaceMiB=4096 mode=blocking    volumeMiB=384
    jvm ctl-nb4096 totalSpaceMiB=4096 mode=nonblocking volumeMiB=384
    jvm ctl-cdcoff totalSpaceMiB=128 mode=nonblocking enabled=false volumeMiB=384
    jvm ctl-plain-b128  totalSpaceMiB=128 mode=blocking table=plain volumeMiB=384
    jvm ctl-plain-nb128 totalSpaceMiB=128 mode=nonblocking table=plain volumeMiB=384
    jvm ctl-wait1s-b128 totalSpaceMiB=128 mode=blocking sampleWaitMs=1000 ;;
  *) echo "usage: $0 check|all"; exit 2 ;;
esac
pgrep -f '[C]assandraDaemon' > /dev/null && log "WARNING: CassandraDaemon running"
log "done"
