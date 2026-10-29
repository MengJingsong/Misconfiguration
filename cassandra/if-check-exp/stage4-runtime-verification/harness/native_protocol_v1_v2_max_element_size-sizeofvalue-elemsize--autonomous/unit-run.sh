#!/usr/bin/env bash
# Unit tier (B2) of native_protocol_v1_v2_max_element_size-sizeofvalue-elemsize--autonomous.
# usage (run node): unit-run.sh [run-name]   copy: ~/s4-b34/src (copy-source.sh + ant build-test)
# output: ~/s4-b34/logs/max_element_size/<run>/unit/  (test.out = STAGE4 lines, ant.log, summary.txt)
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/s4-b34/src}; RUN=${1:-run1}
D=test/unit/org/apache/cassandra/cql3/functions/types; CLS=ElementSizeProbeTest; T=$C/$D/$CLS.java
if [ "$RUN" = "--remove" ]; then rm -f "$T" $C/build/test/classes/org/apache/cassandra/cql3/functions/types/$CLS*.class; echo removed; exit 0; fi
L=$HOME/s4-b34/logs/max_element_size/$RUN/unit; mkdir -p "$L"; S=$L/summary.txt; : > "$S"
say() { echo "$*" | tee -a "$S"; }
cd "$C"
say "unit-run $(date -Is) host $(hostname -s) copy $C $(git describe --tags) java $(java -version 2>&1 | head -1)"
say "harness md5 $(cd "$H" && md5sum $CLS.java unit-run.sh | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
mkdir -p "$(dirname "$T")"; cp "$H/$CLS.java" "$T"; rm -f "$L/test.out"; rm -rf build/test/cassandra
ant testsome -Dtest.name=org.apache.cassandra.cql3.functions.types.$CLS \
  -Dtest.jvm.args="-Dstage4.out=$L/test.out -Xmx512m -Xms512m" > "$L/ant.log" 2>&1 < /dev/null
rc=$?
cp build/test/output/TEST-org.apache.cassandra.cql3.functions.types.$CLS*.xml "$L/" 2>/dev/null || true
say "probe ant exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant.log")"
say "cells: $(grep -c '^STAGE4 cell' "$L/test.out")"
say "leftover java: $(ps -eo cmd | grep "[${CLS:0:1}]${CLS:1}" | wc -l)"
say "done $(date -Is)"
