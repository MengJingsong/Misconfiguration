#!/usr/bin/env bash
# Compile-only instrument check for the unit test (step 1): copies the test into the working tree and builds the tests.
set -uo pipefail
CL=$HOME/s4-b8-pi; TOOLS=$HOME/s4-b8-pi-harness; OUT=$HOME/s4-b8-pi-logs
cp "$TOOLS/PerIpInFlightLimitTest.java" "$CL/test/unit/org/apache/cassandra/transport/" || exit 1
cd "$CL" || exit 1
ant build-test </dev/null > "$OUT/unit-compile.log" 2>&1; echo "ant exit $?"; grep -E 'error:|BUILD' "$OUT/unit-compile.log" | head -20
