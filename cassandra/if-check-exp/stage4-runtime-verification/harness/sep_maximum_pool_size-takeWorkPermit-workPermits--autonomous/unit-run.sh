#!/usr/bin/env bash
# Unit tier (B2e, as amended 2026-10-26) of sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous.
# usage: unit-run.sh <run-label> [cleanup]
#   copies SEPMaxPoolSizeFootprintTest.java into the run clone, runs ant testsome, copies XML + test log + SEPFP lines
#   to $W/logs/sep_maximum_pool_size-takeWorkPermit/unit-<label>/. With "cleanup", removes the class and build/test/cassandra
#   from the clone afterwards and records git status.
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
H=$(cd "$(dirname "$0")" && pwd)
RUN=${1:?label}
C=$W/cassandra-run29
L=$W/logs/sep_maximum_pool_size-takeWorkPermit/unit-$RUN
[ -e "$L" ] && mv "$L" "$L.attempt-$(date +%s)"
mkdir -p "$L"; CL=$L/commands.log; : > "$CL"
log() { echo "[$(date '+%Y-%m-%dT%H:%M:%S%z')] $*" >> "$CL"; }
T=org.apache.cassandra.concurrent.SEPMaxPoolSizeFootprintTest
log "unit-run $RUN; harness sha256 $(shasum -a 256 "$H/SEPMaxPoolSizeFootprintTest.java" | cut -c1-16); clone $(git -C $C rev-parse --short HEAD)"
cp "$H/SEPMaxPoolSizeFootprintTest.java" "$C/test/unit/org/apache/cassandra/concurrent/" || exit 1
rm -rf "$C/build/test/logs" "$C/build/test/output"
log "+ ant -Dlocal.repository=$W/m2 testsome -Dtest.name=$T"
( cd "$C" && ant -Dlocal.repository=$W/m2 testsome -Dtest.name=$T ) > "$L/ant.log" 2>&1
rc=$?; log "  ant exit=$rc"
cp "$C"/build/test/output/TEST-$T.xml "$L/" 2>>"$CL"
f=$(find "$C/build/test/logs" -name "TEST-$T.log" | head -1); log "test log: $f"
cp "$f" "$L/" 2>>"$CL"
grep -h -o 'SEPFP.*' "$L/TEST-$T.log" > "$L/sepfp-lines.txt" 2>>"$CL"
grep -o '<testsuite[^>]*>' "$L/TEST-$T.xml" > "$L/junit-testsuite.txt" 2>>"$CL"
log "SEPFP lines: $(wc -l < "$L/sepfp-lines.txt" | tr -d ' '); $(cat "$L/junit-testsuite.txt" | tr -d '\n' | cut -c1-300)"
if [ "${2:-}" = cleanup ]; then
  rm -f "$C/test/unit/org/apache/cassandra/concurrent/SEPMaxPoolSizeFootprintTest.java"; rm -rf "$C/build/test/cassandra"
  log "cleanup done; git status: $(git -C $C status --porcelain | tr '\n' ';')"
fi
log "end"
exit $rc
