#!/usr/bin/env bash
# Unit tier (B2) of cache_keys_to_save-saveCache-keysEstimate--autonomous.
# usage: unit-run.sh [run-name]     (default run1)      output: ~/s4-b8-kt-logs/<run>/unit/
# Copies KeysToSaveTest into the unit copy's test/unit/org/apache/cassandra/cache/, runs it with ant testsome (1 GiB test
# heap, B2a), then upstream AutoSavingCacheTest as a sanity run, and writes summary.txt (STAGE4 info/save/race lines, check counts).
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/s4-b8-kt/u}; RUN=${1:-run1}
L=$HOME/s4-b8-kt-logs/$RUN/unit; mkdir -p "$L"; S=$L/summary.txt; : > "$S"
say() { echo "$*" | tee -a "$S"; }
cd "$C"
T=$C/test/unit/org/apache/cassandra/cache/KeysToSaveTest.java
say "unit-run $(date -Is) host $(hostname -s) clone $(git describe --tags) java $(java -version 2>&1 | head -1)"
say "harness md5 $(cd "$H" && md5sum KeysToSaveTest.java unit-run.sh | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
cp "$H/KeysToSaveTest.java" "$T"
rm -f "$L/test.out"; rm -rf build/test/cassandra
ant testsome -Dtest.name=org.apache.cassandra.cache.KeysToSaveTest -Dtest.jvm.args="-Dstage4.out=$L/test.out" > "$L/ant.log" 2>&1 < /dev/null
rc=$?
cp build/test/output/TEST-org.apache.cassandra.cache.KeysToSaveTest*.xml "$L/" 2>/dev/null || true
grep -h -o 'Saved [A-Za-z]*Cache ([0-9]* items) in [0-9]* ms to [^ ]*' build/test/logs/_jdk11/TEST-org.apache.cassandra.cache.KeysToSaveTest.log > "$L/saved-log-lines.txt" 2>/dev/null || true
say "KeysToSaveTest ant exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant.log")"
ant testsome -Dtest.name=org.apache.cassandra.cache.AutoSavingCacheTest > "$L/ant-upstream.log" 2>&1 < /dev/null
say "upstream AutoSavingCacheTest ant exit=$? $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant-upstream.log")"
grep '^STAGE4 info\|^STAGE4 summary\|^STAGE4 race\|^STAGE4 hot\|^STAGE4 ratio\|^STAGE4 alloc' "$L/test.out" | tee -a "$S"
grep '^STAGE4 save' "$L/test.out" >> "$S"
grep '^STAGE4 check.*MISMATCH' "$L/test.out" | tee -a "$S"
say "checks: $(grep -c '^STAGE4 check' "$L/test.out") ok: $(grep -c '^STAGE4 check.* ok$' "$L/test.out") MISMATCH: $(grep -c '^STAGE4 check.* MISMATCH$' "$L/test.out")"
say "saved-log lines: $(wc -l < "$L/saved-log-lines.txt" 2>/dev/null)"
say "done $(date -Is)"
