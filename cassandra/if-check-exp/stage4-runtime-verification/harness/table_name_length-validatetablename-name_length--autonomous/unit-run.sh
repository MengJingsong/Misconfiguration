#!/usr/bin/env bash
# Unit tier (B2) of the two NAME_LENGTH cases. usage (on the run node): unit-run.sh <case-stem> [run-name | --remove]
#   stem = schemaconstants_name_length-validatekeyspacename-keyspacename--autonomous  (NameLengthProbeTest)
#       or table_name_length-validatetablename-name_length--autonomous               (TableNameLengthProbeTest)
# Copies the probe into the copy's test/unit/org/apache/cassandra/schema/ (the copy is $CASSANDRA_HOME, default ~/s4-b2/base, made by
# copy-source.sh and built with ant build-test), runs it with ant testsome and a GC log, then the upstream KeyspaceMetadataTest /
# TableMetadataTest as a sanity run, and writes summary.txt. Output: ~/s4-b2/logs/<stem>/<run>/unit/
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); STEM=${1:?stem}; RUN=${2:-run1}
C=${CASSANDRA_HOME:-$HOME/s4-b2/base}
case $STEM in
  schemaconstants*) CLS=NameLengthProbeTest; UP=KeyspaceMetadataTest ;;
  table_name*)      CLS=TableNameLengthProbeTest; UP=TableMetadataTest ;;
  *) echo "unknown stem" >&2; exit 2 ;;
esac
SRC=$HERE/../$STEM/$CLS.java; [ -f "$SRC" ] || SRC=$HERE/$CLS.java
T=$C/test/unit/org/apache/cassandra/schema/$CLS.java
if [ "$RUN" = "--remove" ]; then rm -f "$T" "$C"/build/test/classes/org/apache/cassandra/schema/$CLS*.class; echo "removed $T"; exit 0; fi
L=$HOME/s4-b2/logs/$STEM/$RUN/unit; mkdir -p "$L"; S=$L/summary.txt; : > "$S"
say() { echo "$*" | tee -a "$S"; }
cd "$C"
say "unit-run $(date -Is) host $(hostname -s) copy $C $(git describe --tags) java $(java -version 2>&1 | head -1)"
say "harness md5 $(md5sum "$SRC" | awk '{print substr($1,1,12)}') $CLS"
cp "$SRC" "$T"
rm -f "$L/test.out"; rm -rf build/test/cassandra
ant testsome -Dtest.name=org.apache.cassandra.schema.$CLS -Dtest.jvm.args="-Dstage4.out=$L/test.out -Xlog:gc*:file=$L/gc.log" > "$L/ant.log" 2>&1 < /dev/null
rc=$?
cp build/test/output/TEST-org.apache.cassandra.schema.$CLS*.xml "$L/" 2>/dev/null || true
say "probe ant exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant.log")"
ant testsome -Dtest.name=org.apache.cassandra.schema.$UP > "$L/ant-upstream.log" 2>&1 < /dev/null
say "upstream $UP ant exit=$? $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant-upstream.log")"
grep '^STAGE4 info\|^STAGE4 summary' "$L/test.out" | tee -a "$S"
grep '^STAGE4 case' "$L/test.out" >> "$S"
say "checks: $(grep -c '^STAGE4 check' "$L/test.out") ok: $(grep -c '^STAGE4 check.* ok$' "$L/test.out") MISMATCH: $(grep -c '^STAGE4 check.* MISMATCH$' "$L/test.out")"
say "size lines: $(grep -c '^STAGE4 size' "$L/test.out")"
say "done $(date -Is)"
