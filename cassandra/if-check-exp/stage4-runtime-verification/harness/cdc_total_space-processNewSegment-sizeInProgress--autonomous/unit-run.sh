#!/usr/bin/env bash
# Stage 4 run 1, unit tier: cdc_total_space-processNewSegment-sizeInProgress--autonomous, case B2.
#   unit-run.sh check   instrument check only (N=96 non-blocking; not a reading)
#   unit-run.sh all     matrix: {blocking, nonblocking} x N=96,192,1024 x 3 repeats + controls (cdc=false table, both modes, N=96)
# Run on the measured node from a local copy (CLONE) and a copy of the harness (HARNESS, with SHA256SUMS).
set -uo pipefail
HARNESS=${HARNESS:-$HOME/s4-cdc/harness}
C=${CLONE:-$HOME/s4-cdc/clone}
L=${LOGDIR:-$HOME/s4-cdc/logs/unit}
T=test/unit/org/apache/cassandra/db/commitlog
CLASS=org.apache.cassandra.db.commitlog.CdcTotalSpaceProbeTest
mkdir -p "$L"; S=$L/summary.txt
exec > >(tee -a "$L/session.log") 2>&1
log() { echo "[$(date '+%F %T')] $*"; }
fail() { log "FAIL: $*"; exit 3; }
cd "$C" || fail "no clone"
[ "$(git describe --tags)" = cassandra-5.0.9 ] || fail "clone not at cassandra-5.0.9"
pgrep -f "[j]ava.*$C" > /dev/null && fail "a java process runs from this clone"
( cd "$HARNESS" && sha256sum -c SHA256SUMS ) || fail "harness copy differs"
cp "$HARNESS/CdcTotalSpaceProbeTest.java" "$T/CdcTotalSpaceProbeTest.java"
cmp "$HARNESS/CdcTotalSpaceProbeTest.java" "$T/CdcTotalSpaceProbeTest.java" || fail "test copy differs"
# B2a: DEBUG logger so that line 351 ("Freed up ...") is logged (idempotent)
grep -q 'CommitLogSegmentManagerCDC' test/conf/logback-test.xml || sed -i 's#<logger name="org.apache.cassandra.db.monitoring" level="DEBUG"/>#&\n  <logger name="org.apache.cassandra.db.commitlog.CommitLogSegmentManagerCDC" level="DEBUG"/>#' test/conf/logback-test.xml
grep -n 'CommitLogSegmentManagerCDC' test/conf/logback-test.xml
log "unit yaml segment size: $(grep -E '^commitlog_segment_size' test/conf/cassandra.yaml); df: $(df -h --output=avail "$HOME" | tail -1)"

jvm() {   # label, then key=value test settings
  local label=$1; shift
  local d=$L/$label args="" kv
  rm -rf "$d"; mkdir -p "$d"
  for kv in "$@"; do args="$args -Dstage4.cdc.$kv"; done
  args="$args -Dstage4.unit.out=$d/readings.txt -javaagent:$C/build/lib/jars/byteman-4.0.20.jar=script:$HARNESS/cdc-verdict.btm -Dstage4.byteman.out=$d/cdc-verdict.txt"
  log "=== $label: $args"
  rm -f build/test/output/TEST-$CLASS*.xml; rm -rf build/test/logs/* 2> /dev/null
  ant testsome -Dtest.name=$CLASS -Dtest.jvm.args="$args" > "$d/ant.txt" 2>&1 < /dev/null
  local rc=$?
  cp build/test/output/TEST-$CLASS*.xml "$d/junit.xml" 2> /dev/null
  grep -rh 'Freed up' build/test/logs 2> /dev/null > "$d/freed-up.txt"
  local line; line=$(grep -E 'Testsuite:.*Tests run:|Tests run:.*Time elapsed' "$d/ant.txt" | head -1)
  echo "$label ant_exit=$rc $line | freedUpLines=$(wc -l < "$d/freed-up.txt") | $(grep -h ' RESULT ' "$d/readings.txt" 2> /dev/null | sed -E 's/^ms=[0-9]+ //')" | tee -a "$S"
  [ -s "$d/readings.txt" ] || fail "$label produced no readings"
  rm -rf build/test/cassandra/data* build/test/cassandra/commitlog* build/test/cassandra/cdc_raw* 2> /dev/null
  du -sh build/test/cassandra 2> /dev/null | sed 's/^/    test dir: /'
}

case ${1:-} in
  check)
    jvm check-nb96 totalSpaceMiB=96 mode=nonblocking ;;
  all)
    for r in 1 2 3; do
      for n in 96 192 1024; do
        jvm "b$n-r$r"  totalSpaceMiB=$n mode=blocking
        jvm "nb$n-r$r" totalSpaceMiB=$n mode=nonblocking
      done
    done
    # B2h / B2f controls: non-CDC table at N=96, both modes (2 repeats)
    for r in 1 2; do
      jvm "plain-b96-r$r"  totalSpaceMiB=96 mode=blocking    table=plain
      jvm "plain-nb96-r$r" totalSpaceMiB=96 mode=nonblocking table=plain
    done ;;
  *) echo "usage: $0 check|all"; exit 2 ;;
esac
pgrep -f "[j]ava.*$C" > /dev/null && log "WARNING: java running from the clone"
log "done"
