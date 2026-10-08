#!/usr/bin/env bash
# Unit tier (B2e). Run on the node after 00-setup.sh. Logs every command and its output to
# $RUN/logs/10-unit.log; stops at the first failed check.
#   1. known-answer check of the build/test harness: upstream DirectoriesTest#testFreeCompactionSpace,testHasAvailableSpace
#   2. copy MaxCompactionSpaceOperandTest.java into the local clone (B2e step 2)
#   3. ant jar (B2e step 3)
#   4. ant test -Dtest.name=MaxCompactionSpaceOperandTest (B2e step 4), readings -> $RUN/unit/readings.txt
set -euo pipefail
RUN=~/short-run/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction
SRC=$RUN/cassandra
mkdir -p "$RUN/logs" "$RUN/unit"
exec > >(tee -a "$RUN/logs/10-unit.log") 2>&1
set -x
date -u +%FT%TZ
cd "$SRC"
git rev-parse HEAD

# 1. known answer
# DirectoriesTest is @Parameterized, so -Dtest.methods matches nothing (attempt 1, harness defect H1): run the whole class.
ant testsome -Dtest.name=org.apache.cassandra.db.DirectoriesTest
cp build/test/output/TEST-org.apache.cassandra.db.DirectoriesTest*.xml "$RUN/unit/"
grep -h -E '<testsuite|<testcase name="test(FreeCompactionSpace|HasAvailableSpace)|<failure|<error' "$RUN"/unit/TEST-org.apache.cassandra.db.DirectoriesTest*.xml | cut -c1-300

# 2-3.
cp "$RUN/harness/MaxCompactionSpaceOperandTest.java" test/unit/org/apache/cassandra/db/MaxCompactionSpaceOperandTest.java
sha256sum test/unit/org/apache/cassandra/db/MaxCompactionSpaceOperandTest.java
ant jar

# 4.
rm -f "$RUN/unit/readings.txt"
rc=0
READINGS_OUT="$RUN/unit/readings.txt" ant test -Dtest.name=MaxCompactionSpaceOperandTest || rc=$?
echo "ant test rc=$rc"
ls build/test/output/ | grep MaxCompactionSpaceOperandTest || true
cp build/test/output/TEST-org.apache.cassandra.db.MaxCompactionSpaceOperandTest*.xml "$RUN/unit/" || true
grep -h -E '<testsuite|<testcase|<failure|<error' "$RUN"/unit/TEST-org.apache.cassandra.db.MaxCompactionSpaceOperandTest*.xml | cut -c1-400 || true
cat "$RUN/unit/readings.txt"
echo "MISMATCH count: $(grep -c MISMATCH "$RUN/unit/readings.txt" || true)"
# no daemon was started by this tier; check anyway
ps -eo cmd | grep '[C]assandraDaemon' || echo "no CassandraDaemon"
date -u +%FT%TZ
echo UNIT_DONE
