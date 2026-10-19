#!/usr/bin/env bash
# Unit tier of max_mutation_size-validateSize-MAX_MUTATION_SIZE (case 9e unit steps 1-3).
# usage (on the measured node): unit-run.sh [upstream|harness|all]   output: ~/stage4-logs/mms/unit/
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-run1}; L=$HOME/stage4-logs/mms/unit
what=${1:-all}
mkdir -p "$L"; cp "$H/MaxMutationSizeGuardTest.java" "$C/test/unit/org/apache/cassandra/db/commitlog/"
cd "$C"
if [ "$what" = upstream ] || [ "$what" = all ]; then
  ant testsome -Dtest.name=org.apache.cassandra.db.commitlog.GroupCommitLogTest > "$L/upstream.ant.log" 2>&1 < /dev/null
  echo "upstream GroupCommitLogTest exit=$? $(grep -m1 'Tests run' "$L/upstream.ant.log")"
  cp build/test/output/TEST-org.apache.cassandra.db.commitlog.GroupCommitLogTest.xml "$L/" 2>/dev/null || true
fi
if [ "$what" = harness ] || [ "$what" = all ]; then
  for spec in 256k:256KiB:262144 1m:1MiB:1048576 2m:2MiB:2097152 default:none:2621440 range:3MiB:3145728; do
    IFS=: read -r label val bytes <<< "$spec"
    y=$("$H/make-unit-yaml.sh" "$label" "$val"); rm -f "$L/$label.out"
    ant testsome -Dtest.name=org.apache.cassandra.db.commitlog.MaxMutationSizeGuardTest \
      -Dtest.jvm.args="-Dcassandra.config=file://$y -Dstage4.expect_mms=$bytes -Dstage4.out=$L/$label.out" > "$L/$label.ant.log" 2>&1 < /dev/null
    rc=$?
    cp build/test/output/TEST-org.apache.cassandra.db.commitlog.MaxMutationSizeGuardTest.xml "$L/$label.TEST.xml" 2>/dev/null || true
    if [ "$label" = range ]; then
      echo "range exit=$rc ConfigurationException: $(grep -h -m1 -o 'commitlog_segment_size must be at least twice[^<\"]*' "$L/$label.ant.log" "$L/$label.TEST.xml" 2>/dev/null | head -1) STAGE4 lines: $(grep -c STAGE4 "$L/$label.out" 2>/dev/null || echo 0)"
    else
      echo "$label exit=$rc mismatches=$(grep -c MISMATCH "$L/$label.out" 2>/dev/null) $(tail -1 "$L/$label.out" 2>/dev/null)"
    fi
  done
fi
