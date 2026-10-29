#!/usr/bin/env bash
# Unit tier (B2) of max_keys_sparse-addinternal-keys--autonomous.
# usage (run node): unit-run.sh [run-name]   copy: ~/s4-b34/src (copy-source.sh + ant build-test)
# output: ~/s4-b34/logs/max_keys_sparse/<run>/unit/  (test.out = STAGE4 lines, ant.log, gc none)
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/s4-b34/src}; RUN=${1:-run1}
D=test/unit/org/apache/cassandra/index/sasi/disk; T=$C/$D/SparseKeysProbeTest.java
if [ "$RUN" = "--remove" ]; then rm -f "$T" $C/build/test/classes/org/apache/cassandra/index/sasi/disk/SparseKeysProbeTest*.class; echo removed; exit 0; fi
L=$HOME/s4-b34/logs/max_keys_sparse/$RUN/unit; mkdir -p "$L"; S=$L/summary.txt; : > "$S"
say() { echo "$*" | tee -a "$S"; }
cd "$C"
say "unit-run $(date -Is) host $(hostname -s) copy $C $(git describe --tags) java $(java -version 2>&1 | head -1)"
say "harness md5 $(cd "$H" && md5sum SparseKeysProbeTest.java unit-run.sh | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
cp "$H/SparseKeysProbeTest.java" "$T"; rm -f "$L/test.out"; rm -rf build/test/cassandra
mkdir -p $HOME/s4-b34/tmp
ant testsome -Dtest.name=org.apache.cassandra.index.sasi.disk.SparseKeysProbeTest \
  -Dtest.jvm.args="-Dstage4.out=$L/test.out -Xmx512m -Xms512m -Djava.io.tmpdir=$HOME/s4-b34/tmp" > "$L/ant.log" 2>&1 < /dev/null
rc=$?
cp build/test/output/TEST-org.apache.cassandra.index.sasi.disk.SparseKeysProbeTest*.xml "$L/" 2>/dev/null || true
say "probe ant exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant.log")"
ant testsome -Dtest.name=org.apache.cassandra.index.sasi.disk.OnDiskIndexTest > "$L/ant-upstream.log" 2>&1 < /dev/null
say "upstream OnDiskIndexTest ant exit=$? $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant-upstream.log")"
say "cells: $(grep -c '^STAGE4 cell' "$L/test.out") control: $(grep -c '^STAGE4 control' "$L/test.out")"
say "checks: $(grep -c '^STAGE4 check' "$L/test.out") ok: $(grep -c '^STAGE4 check.* ok$' "$L/test.out") MISMATCH: $(grep -c '^STAGE4 check.* MISMATCH$' "$L/test.out")"
grep '^STAGE4 control' "$L/test.out" | tee -a "$S"
say "leftover java: $(ps -eo cmd | grep '[S]parseKeysProbe' | wc -l)"
say "done $(date -Is)"
