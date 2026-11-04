#!/usr/bin/env bash
# Unit tier (B2, amendments U1-U8 of 2026-10-27) of native_transport_max_frame_size-decode-bytesToDiscard--autonomous.
# usage: source ~/Library/Caches/stage4/env.sh; unit-run.sh <label> [value ...]
#   r1:    unit-run.sh r1                      (values 4MiB 8MiB 16MiB, default sub-runs, frozen sizes)
#   shake: EXTRA="-Dprobe.L=2097152 -Dprobe.ctrlL=262144 -Dprobe.subruns=MAIN,CTRL1M,C436,EDGE" unit-run.sh shake 1MiB 2MiB
# Copies FrameSizeDiscardProbeTest.java into clone C (default $W/cassandra-run54), runs one ant testsome JVM per value, copies
# each JVM's TEST log before the next overwrites it, extracts CONFIG/PROBE/DONE lines, removes the copied test.
# Logs: $W/logs/native_transport_max_frame_size-decode-bytesToDiscard--autonomous/unit-<label>/
# (structure adapted from harness/native_transport_max_concurrent_connections-channelActive-limit--autonomous/unit-run.sh)
set -uo pipefail
LABEL=$1; shift
VALUES=${*:-4MiB 8MiB 16MiB}
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run54}; EXTRA=${EXTRA:-}
CLS=org.apache.cassandra.transport.FrameSizeDiscardProbeTest
L=$W/logs/native_transport_max_frame_size-decode-bytesToDiscard--autonomous/unit-$LABEL; mkdir -p "$L"; rm -rf "$L"/*
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
log "unit-run $LABEL values=[$VALUES] extra=[$EXTRA] clone=$C $(git -C "$C" describe --tags) $(git -C "$C" rev-parse HEAD) test_sha=$(shasum -a 256 "$H/FrameSizeDiscardProbeTest.java" | cut -c1-16) script_sha=$(shasum -a 256 "$0" | cut -c1-16)"
pgrep -f 'org.apache.cassandra.service.Cassandra[D]aemon' >/dev/null && { log "ABORT: a node is running"; exit 1; }
T=$C/test/unit/org/apache/cassandra/transport/FrameSizeDiscardProbeTest.java
cp "$H/FrameSizeDiscardProbeTest.java" "$T"
: > "$L/probe.txt"
for v in $VALUES; do
  rm -rf "$C"/build/test/logs "$C"/build/test/output/TEST-$CLS*.xml
  JA="-Dprobe.mfs=$v $EXTRA"
  log "+ ant -Dlocal.repository=\$W/m2 testsome -Dtest.name=$CLS -Dtest.jvm.args=\"$JA\""
  s0=$(date +%s)
  ( cd "$C" && ant -Dlocal.repository=$W/m2 testsome -Dtest.name=$CLS "-Dtest.jvm.args=$JA" ) > "$L/ant-$v.log" 2>&1
  rc=$?
  log "ant rc=$rc after $(( $(date +%s) - s0 )) s; $(grep -m1 'Tests run' "$L/ant-$v.log" || echo 'no Tests run line'); $(grep -m1 'BUILD' "$L/ant-$v.log")"
  cp "$C"/build/test/output/TEST-$CLS*.xml "$L/TEST-$v.xml" 2>/dev/null || log "no JUnit XML for $v"
  TL=$(find "$C/build/test/logs" -name "TEST-$CLS*.log" 2>/dev/null | head -1)
  if [ -n "$TL" ]; then cp "$TL" "$L/TEST-$v.log"; else log "no TEST log for $v; using ant log"; cp "$L/ant-$v.log" "$L/TEST-$v.log"; fi
  grep -h -o -E '(CONFIG|PROBE|DONE),.*$' "$L/TEST-$v.log" | awk '!seen[$0]++' > "$L/probe-$v.txt"
  cat "$L/probe-$v.txt" >> "$L/probe.txt"
  log "value $v: CONFIG [$(grep '^CONFIG,' "$L/probe-$v.txt")] PROBE lines $(grep -c '^PROBE,' "$L/probe-$v.txt") DONE [$(grep '^DONE,' "$L/probe-$v.txt")]"
  grep -q "^CONFIG,$v," "$L/probe-$v.txt" || { log "STOP CONDITION: no CONFIG line for $v (tier invalid)"; break; }
  grep -A3 'FAILED\|Exception' "$L/ant-$v.log" | head -10 | while read -r l; do log "  ant: $l"; done
done
rm -f "$T"; rm -rf "$C/build/test/classes/org/apache/cassandra/transport/FrameSizeDiscardProbeTest"*.class
log "copied test removed; clone git status lines: $(git -C "$C" status --short | wc -l | tr -d ' ')"
pgrep -f 'FrameSizeDiscardProbeTest' >/dev/null && log "WARNING: a test JVM is still running" || log "no test JVM left"
log "unit-run $LABEL done"
