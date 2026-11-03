#!/usr/bin/env bash
# Unit tier (B2, as amended 2026-10-25) of compressed_read_ahead_buffer_size-setCompressedReadAheadBufferSizeInKb-sizeInKb--autonomous.
# Adapted from harness/compressed_read_ahead_buffer_size-applySimpleConfig-compressed_read_ahead_buffer_size--autonomous/unit-run.sh
# (p2 part: ant testsome per run, test yaml line 55 edited and restored with git checkout). Copied, then changed: clone, test class
# and path, no knob line (the knob is set by the test through the setter), repetitions instead of arms.
# usage: source ~/Library/Caches/stage4/env.sh; unit-run.sh <outdir-name> <labels...>
#   labels: rep1 rep2 rep3 (run 1), or sd (shakedown: -Dstage4.shakedown=true -Dstage4.values=2048)
set -uo pipefail
RUN=${1:?outdir}; shift
LABELS=${*:-rep1 rep2 rep3}
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run23}
L=$W/logs/compressed_read_ahead_buffer_size-setCompressedReadAheadBufferSizeInKb/unit-$RUN
[ -e "$L" ] && mv "$L" "$L.attempt-$(date +%s)"
mkdir -p "$L"
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
log "unit-run $RUN labels=[$LABELS] clone=$C $(git -C "$C" describe --tags) $(git -C "$C" rev-parse HEAD); runner sha256 $(shasum -a 256 "$0" | cut -c1-16)"
log "harness sha256: $(cd "$H" && shasum -a 256 ReadAheadSetterTest.java | awk '{print $2"="substr($1,1,16)}')"
d=$(ps -eo command | grep '[C]assandraDaemon'); [ -n "$d" ] && { log "ABORT: a Cassandra node is running"; exit 1; }
df -h "$W" | tail -1 >> "$L/commands.log"
T=$C/test/unit/org/apache/cassandra/io/util/ReadAheadSetterTest.java
cp "$H/ReadAheadSetterTest.java" "$T"
for a in $LABELS; do
  git -C "$C" checkout -- test/conf/cassandra.yaml
  grep -q '^compressed_read_ahead_buffer_size' "$C/test/conf/cassandra.yaml" && { log "ABORT: test yaml has the knob"; exit 1; }
  [ "$(sed -n 55p "$C/test/conf/cassandra.yaml")" = "file_cache_enabled: true" ] || { log "ABORT: test yaml line 55 is not file_cache_enabled: true"; exit 1; }
  sed -i '' "55s/.*/file_cache_enabled: false/" "$C/test/conf/cassandra.yaml"
  git -C "$C" diff -- test/conf/cassandra.yaml > "$L/yaml-diff-$a.txt"
  EXTRA=""; [ $a = sd ] && EXTRA="-Dstage4.shakedown=true -Dstage4.values=2048"
  log "+ ant testsome ReadAheadSetterTest ($a); yaml: $(grep -E '^(file_cache_enabled|compressed_read_ahead_buffer_size|disk_access_mode):' "$C/test/conf/cassandra.yaml" | tr '\n' ' ')"
  s0=$(date +%s)
  ( cd "$C" && ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.io.util.ReadAheadSetterTest \
      -Dtest.jvm.args="-Dstage4.out=$L/stage4.out -Dstage4.label=$a $EXTRA" ) > "$L/ant-$a.log" 2>&1
  rc=$?; log "$a ant rc=$rc after $(( $(date +%s) - s0 )) s; $(grep -m1 'Tests run' "$L/ant-$a.log" || echo 'no Tests run line')"
  echo "UNIT $a ant rc=$rc $(grep -m1 'Tests run' "$L/ant-$a.log")" >> "$L/summary.txt"
  cp "$C/build/test/output/TEST-org.apache.cassandra.io.util.ReadAheadSetterTest.xml" "$L/TEST-$a.xml" 2>/dev/null
  grep "label=$a " "$L/stage4.out" | sed "s/^/UNIT $a :: /" >> "$L/summary.txt"
done
git -C "$C" checkout -- test/conf/cassandra.yaml
rm -f "$T"; rm -rf "$C/build/test/cassandra"
log "test yaml restored, test removed: clone status $(git -C "$C" status --short | wc -l | tr -d ' ') entries"
log "unit-run $RUN done"
