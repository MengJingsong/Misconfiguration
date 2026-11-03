#!/usr/bin/env bash
# Unit tier (B2, as amended 2026-10-26) of prepared_statements_cache_size-getSizeOfPreparedStatementForCache-pstmntSize--autonomous.
# usage: source ~/Library/Caches/stage4/env.sh; unit-run.sh [values...]   (default: 1 4 auto 64, B2b/B2e amended order)
# One `ant testsome` (own forked JVM) per value; knob set by BSD sed on $C/test/conf/cassandra.yaml:48 (auto: line deleted).
# Rerun rule (B2c amended): if resident == n at the end at 4 MiB or auto, that value is rerun with -Dprobe.n=20000.
# Env: C (clone, default $W/cassandra-run30), L (log dir), N0 (n of the first run per value; default 3000 as filed; the shakedown only uses a smaller n).
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run30}
L=${L:-$W/logs/prepared_statements_cache_size-getSizeOfPreparedStatementForCache-pstmntSize--autonomous/unit}
VALS=${*:-1 4 auto 64}; N0=${N0:-3000}
mkdir -p "$L"
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
log "unit-run values=[$VALS] clone=$C $(git -C "$C" describe --tags) $(git -C "$C" rev-parse HEAD)"
pgrep -f 'cassandra.service.CassandraDaemon' >/dev/null && { log "ABORT: a Cassandra daemon is running"; exit 1; }
T=$C/test/unit/org/apache/cassandra/cql3/PreparedCacheCapProbeTest.java
CLS=org.apache.cassandra.cql3.PreparedCacheCapProbeTest
cp "$H/PreparedCacheCapProbeTest.java" "$T"; log "probe copied to $T (sha256 $(shasum -a 256 "$T" | cut -c1-16))"
run_one() {  # $1 value, $2 n
  local v=$1 n=$2 tag="k$1-n$2"
  git -C "$C" checkout -- test/conf/cassandra.yaml
  if [ "$v" = auto ]; then sed -i '' '/^prepared_statements_cache_size:/d' "$C/test/conf/cassandra.yaml"
  else sed -i '' "s/^prepared_statements_cache_size:.*/prepared_statements_cache_size: ${v}MiB/" "$C/test/conf/cassandra.yaml"; fi
  git -C "$C" diff -- test/conf/cassandra.yaml > "$L/yaml-diff-$tag.txt"
  log "+ ant -Dlocal.repository=\$W/m2 testsome -Dtest.name=$CLS -Dtest.jvm.args=-Dprobe.n=$n ($tag); yaml line: $(grep '^prepared_statements_cache_size:' "$C/test/conf/cassandra.yaml" || echo '(deleted)')"
  rm -rf "$C/build/test/logs" "$C/build/test/output/TEST-$CLS.xml"
  ( cd "$C" && ant -Dlocal.repository="$W/m2" testsome -Dtest.name=$CLS -Dtest.jvm.args="-Dprobe.n=$n" ) > "$L/ant-$tag.log" 2>&1
  local rc=$?
  local tl; tl=$(find "$C/build/test/logs" -name "TEST-$CLS.log" 2>/dev/null | head -1)
  [ -n "$tl" ] && cp "$tl" "$L/TEST-$tag.log"
  cp "$C/build/test/output/TEST-$CLS.xml" "$L/TEST-$tag.xml" 2>/dev/null
  grep -o 'PROBE i=.*' "$L/TEST-$tag.log" 2>/dev/null > "$L/probe-$tag.txt"
  log "$tag ant rc=$rc; $(grep -m1 -E 'Tests run' "$L/ant-$tag.log" || echo 'no Tests run line'); PROBE lines=$(wc -l < "$L/probe-$tag.txt" | tr -d ' '); last: $(tail -1 "$L/probe-$tag.txt")"
  grep -E 'IllegalStateException|InvalidRequestException|larger than allowed' "$L/TEST-$tag.log" "$L/ant-$tag.log" 2>/dev/null | head -3 >> "$L/commands.log"
  echo "$tag rc=$rc $(tail -1 "$L/probe-$tag.txt")" >> "$L/summary.txt"
}
for v in $VALS; do
  run_one "$v" "$N0"
  last=$(tail -1 "$L/probe-k$v-n$N0.txt")
  res=$(echo "$last" | sed -n 's/.*resident=\([0-9]*\).*/\1/p')
  if { [ "$v" = 4 ] || [ "$v" = auto ]; } && [ "$res" = "$N0" ] && [ "$N0" = 3000 ]; then log "rerun rule: resident == n at $v -> n=20000"; run_one "$v" 20000; fi
done
git -C "$C" checkout -- test/conf/cassandra.yaml
rm -f "$T"
log "test yaml restored, probe removed; git status: $(git -C "$C" status --short | wc -l | tr -d ' ') entries"
log "unit-run done"
