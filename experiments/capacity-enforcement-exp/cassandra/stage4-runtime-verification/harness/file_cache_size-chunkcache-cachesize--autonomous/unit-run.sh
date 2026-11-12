#!/usr/bin/env bash
# Unit tier (B2) of file_cache_size-chunkcache-cachesize--autonomous.
# usage: bash unit-run.sh <run-name> [shakedown]      runs U0..U4 (fc32 fc64 fc128 fc1024 fcoff), one ant testsome (fresh JVM) each.
# Tree: $W/src (copy-source.sh, ant build-test). Output: $W/<run-name>/unit/. Makes the yaml variants per B2e.1 + amendment A2.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); W=${W:-/mydata/jingsong-cass-s4/o07}; C=$W/src; RUN=${1:?run name}; MODE=${2:-}
CLS=ChunkCacheCapProbeTest; D=test/unit/org/apache/cassandra/cache
L=$W/$RUN/unit; Y=$W/$RUN/yaml; mkdir -p "$L" "$Y"; S=$L/summary.txt; : > "$S"
say() { echo "$*" | tee -a "$S"; }
cd "$C" || exit 1
say "unit-run $(date -u +%FT%TZ) host $(hostname -s) tree $C $(git describe --tags) java $(java -version 2>&1 | head -1)"
say "harness md5 $(cd "$H" && md5sum $CLS.java unit-run.sh unit-analyze.py | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
say "df: $(df -h $W | tail -1)"
for v in 32 64 128 1024; do
  cp test/conf/cassandra.yaml $Y/fc$v.yaml
  printf 'file_cache_size: %sMiB\nstorage_port: 7300\nssl_storage_port: 7301\nnative_transport_port: 9342\n' $v >> $Y/fc$v.yaml
done
cp $Y/fc128.yaml $Y/fcoff.yaml
sed -i 's/^file_cache_enabled: true/file_cache_enabled: false/' $Y/fcoff.yaml
say "yaml check: $(for f in $Y/*.yaml; do echo -n "$(basename $f): $(grep -E '^(file_cache_enabled|file_cache_size|storage_port|native_transport_port):' $f | tr '\n' ' ')| "; done)"
cp "$H/$CLS.java" "$D/$CLS.java"
VALS=${VALS:-"32 64 128 1024 off"}
for v in $VALS; do
  rm -rf build/test/cassandra build/test/logs
  OUT=$L/unit-$v.txt; rm -f "$OUT"
  SD=""; [ "$MODE" = shakedown ] && SD="-Dfc.shakedown=true"
  t0=$(date +%s)
  say "== $v start $(date -u +%FT%TZ)"
  echo "+ ant testsome -Dtest.name=org.apache.cassandra.cache.$CLS -Dtest.jvm.args=\"-Xmx4G -Dcassandra.config=file://$Y/fc$v.yaml -Dfc.out=$OUT $SD\"" >> "$L/ant-$v.log"
  ant testsome -Dtest.name=org.apache.cassandra.cache.$CLS -Dtest.jvm.args="-Xmx4G -Dcassandra.config=file://$Y/fc$v.yaml -Dfc.out=$OUT $SD" >> "$L/ant-$v.log" 2>&1 < /dev/null
  rc=$?
  say "$v ant exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant-$v.log") $(( $(date +%s) - t0 )) s"
  cp build/test/output/TEST-org.apache.cassandra.cache.$CLS.xml "$L/unit-$v.xml" 2>/dev/null || say "$v no junit xml"
  LOG=$(find build/test/logs -name "TEST-*$CLS*.log" | head -1)
  [ -n "$LOG" ] && cp "$LOG" "$L/test-$v.log"
  say "$v pool-limit line: $(grep -h 'Global buffer pool limit' "$L/test-$v.log" 2>/dev/null | tail -1 | sed 's/.*Global/Global/')"
  say "$v lines: $(wc -l < "$OUT" 2>/dev/null)"
  rm -rf build/test/cassandra
done
rm -f "${D:?}/${CLS:?}.java"
say "cleanup: probe removed; test data removed; leftover test JVMs: $(ps -eo pid,args | grep -c "[j]ava.*$CLS")"
python3 "$H/unit-analyze.py" "$L" | tee -a "$S"
say "done $(date -u +%FT%TZ)"
