#!/usr/bin/env bash
# Unit tier (B2) of file_cache_size-chunk_cache_eviction-weighted_size--autonomous.
# usage: bash unit-run.sh <run-name> [F values...]   (default F: 32 33 64 160)
# Copies the probe into the local copy, runs one `ant testsome` (fresh JVM) per F, collects the PROBE lines, removes the probe.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=/mydata/jingsong-cass-s4/o06/src; RUN=${1:-run1}; shift || true
FS=${*:-32 33 64 160}
L=/mydata/jingsong-cass-s4/o06/logs/$RUN/unit; mkdir -p "$L"; S=$L/summary.txt; : > "$S"
say() { echo "$*" | tee -a "$S"; }
cd "$C" || exit 1
say "unit-run $(date -u +%FT%TZ) host $(hostname -s) tree $(git describe --tags) $(java -version 2>&1 | head -1)"
say "harness md5 $(cd "$H" && md5sum ChunkCacheCapProbeTest.java unit-run.sh | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
D=test/unit/org/apache/cassandra/cache; CLS=ChunkCacheCapProbeTest
cp "$H/$CLS.java" "$D/$CLS.java"
OUT=$L/probe-lines.txt; : > "$OUT"
for F in $FS; do
  say "--- F=$F start $(date -u +%FT%TZ)"
  t0=$(date +%s)
  PROBE_FCS=$F PROBE_OUT=$OUT ant testsome -Dtest.name=org.apache.cassandra.cache.$CLS > "$L/ant-$F.log" 2>&1 < /dev/null
  rc=$?
  say "F=$F ant exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant-$F.log") $(( $(date +%s) - t0 )) s"
  cp build/test/output/TEST-org.apache.cassandra.cache.$CLS.xml "$L/junit-$F.xml" 2>/dev/null || true
  grep "F=$F" "$OUT" | tee -a "$S"
  say "leftover ccprobe files: $(ls build/tmp 2>/dev/null | grep -c ccprobe)"
done
rm -f "$D/$CLS.java"; rm -f build/tmp/ccprobe* 2>/dev/null
say "cleanup: probe source removed; leftover test JVMs: $(ps -eo args | grep -c "[j]unit.*$CLS")"
say "done $(date -u +%FT%TZ)"
