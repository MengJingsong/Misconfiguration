#!/usr/bin/env bash
# Unit tier (B2, amended 2026-10-25) of index_summary_capacity-applySimpleConfig-indexSummaryCapacityInMiB--autonomous.
# Adapted from harness/counter_cache_size-applySimpleConfig-counterCacheSizeInMiB--autonomous/unit-run.sh (names, clone, knob,
# variants, test class, timeout, test-data wipe).
# usage: source ~/Library/Caches/stage4/env.sh; unit-run.sh [p1|p2|all]
#   Program 1 (ConfigProbe, copied unchanged from the counter_cache_size-applySimpleConfig harness): yaml variants
#     -1MiB, 0MiB, 512KiB, 1024KiB, unset (auto), each its own java process, -Xms1G -Xmx1G, JDK 11 module flags of build.xml:244-261.
#   Mechanism (IndexSummaryCapProbeTest): one `ant testsome` per startup value {auto (no line), 2MiB}, -Xms1024m,
#     -Dtest.timeout=1800000, knob appended to test/conf/cassandra.yaml (no such line there), restored with git checkout;
#     $C/build/test/cassandra removed before each JVM.
# Clone C (default $W/cassandra-run14); probe dir P=$W/probe-isc; logs L=$W/logs/index_summary_capacity-applySimpleConfig/unit
set -uo pipefail
WHAT=${1:-all}
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run14}; P=${P:-$W/probe-isc}
L=${L:-$W/logs/index_summary_capacity-applySimpleConfig/unit}
mkdir -p "$L"
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
log "unit-run $WHAT clone=$C $(git -C "$C" describe --tags) $(git -C "$C" rev-parse HEAD)"
pgrep -f CassandraDaemon >/dev/null && { log "ABORT: a CassandraDaemon is running"; exit 1; }
df -h "$W" | tail -1 >> "$L/commands.log"

if [ "$WHAT" = p1 ] || [ "$WHAT" = all ]; then
  rm -rf "${P:?}"; mkdir -p "$P/classes" "$P/data"
  CP="$C/build/classes/main:$C/build/lib/jars/*"
  JFLAGS="--add-exports java.base/jdk.internal.misc=ALL-UNNAMED --add-exports java.base/jdk.internal.ref=ALL-UNNAMED --add-exports java.base/sun.nio.ch=ALL-UNNAMED --add-exports java.management.rmi/com.sun.jmx.remote.internal.rmi=ALL-UNNAMED --add-exports java.rmi/sun.rmi.registry=ALL-UNNAMED --add-exports java.rmi/sun.rmi.server=ALL-UNNAMED --add-exports java.rmi/sun.rmi.transport.tcp=ALL-UNNAMED --add-exports java.sql/java.sql=ALL-UNNAMED --add-opens java.base/java.lang.module=ALL-UNNAMED --add-opens java.base/java.net=ALL-UNNAMED --add-opens java.base/jdk.internal.loader=ALL-UNNAMED --add-opens java.base/jdk.internal.ref=ALL-UNNAMED --add-opens java.base/jdk.internal.reflect=ALL-UNNAMED --add-opens java.base/jdk.internal.math=ALL-UNNAMED --add-opens java.base/jdk.internal.module=ALL-UNNAMED --add-opens java.base/jdk.internal.util.jar=ALL-UNNAMED --add-opens jdk.management/com.sun.management.internal=ALL-UNNAMED"
  log "+ javac ConfigProbe.java"; javac -cp "$CP" -d "$P/classes" "$H/ConfigProbe.java" >> "$L/commands.log" 2>&1 || { log "ABORT: javac failed"; exit 1; }
  grep -v -E '^(data_file_directories|commitlog_directory|saved_caches_directory|hints_directory|cdc_raw_directory):' "$C/conf/cassandra.yaml" \
    | grep -v -E '^    - /var/lib/cassandra/data$' > "$P/base.yaml"
  { echo; echo "# stage-4 directories"; echo "data_file_directories:"; echo "    - $P/data/data"
    echo "commitlog_directory: $P/data/commitlog"; echo "saved_caches_directory: $P/data/saved_caches"
    echo "hints_directory: $P/data/hints"; echo "cdc_raw_directory: $P/data/cdc_raw"; } >> "$P/base.yaml"
  grep -n '^index_summary_capacity:' "$P/base.yaml" | tee -a "$L/commands.log"
  for v in -1MiB 0MiB 512KiB 1024KiB unset; do
    y="$P/$v.yaml"
    if [ $v = unset ]; then cp "$P/base.yaml" "$y"; else sed "s/^index_summary_capacity:.*/index_summary_capacity: $v/" "$P/base.yaml" > "$y"; fi
    diff "$P/base.yaml" "$y" > "$L/p1-yaml-diff-$v.txt"; rm -rf "${P:?}/data"; mkdir -p "$P/data"
    log "+ java -Xms1G -Xmx1G ConfigProbe getIndexSummaryCapacityInMiB ($v)"
    ( cd "$P" && exec java -Xms1G -Xmx1G $JFLAGS -cp "$CP:$P/classes" -Dcassandra.config=file://$y -Dcassandra.storagedir=$P/data \
      -Dlogback.configurationFile=$C/test/conf/logback-test.xml ConfigProbe getIndexSummaryCapacityInMiB ) > "$L/p1-$v.out" 2>&1 < /dev/null &
    jp=$!; for i in $(seq 1 60); do kill -0 $jp 2>/dev/null || break; sleep 1; done
    if kill -0 $jp 2>/dev/null; then kill -9 $jp; log "p1 $v: killed after 60 s (JVM did not exit)"; fi
    wait $jp 2>/dev/null; log "p1 $v rc=$?"
    echo "P1 $v :: $(grep -E '^(OK|REJECT) ' "$L/p1-$v.out" | head -1)" | tee -a "$L/summary.txt" "$L/commands.log"
  done
  pgrep -f ConfigProbe >/dev/null && log "WARNING: ConfigProbe left" || log "no ConfigProbe left"
  rm -rf "${P:?}/data"
fi

if [ "$WHAT" = p2 ] || [ "$WHAT" = all ]; then
  mkdir -p "$C/test/unit/org/apache/cassandra/probe"
  cp "$H/IndexSummaryCapProbeTest.java" "$C/test/unit/org/apache/cassandra/probe/"
  rm -f "$L/stage4.out"
  for v in ${VALUES:-auto 2MiB}; do
    git -C "$C" checkout -- test/conf/cassandra.yaml
    grep -q '^index_summary_capacity' "$C/test/conf/cassandra.yaml" && { log "ABORT: test yaml already has index_summary_capacity"; exit 1; }
    [ $v = auto ] || printf '\nindex_summary_capacity: %s\n' "$v" >> "$C/test/conf/cassandra.yaml"
    git -C "$C" diff -- test/conf/cassandra.yaml > "$L/p2-yaml-diff-$v.txt"
    rm -rf "${C:?}/build/test/cassandra"
    log "+ ant testsome IndexSummaryCapProbeTest ($v); yaml line: $(grep '^index_summary_capacity:' "$C/test/conf/cassandra.yaml" || echo '(none = auto)')"
    s0=$(date +%s)
    ( cd "$C" && ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.probe.IndexSummaryCapProbeTest -Dtest.timeout=1800000 \
        -Dtest.jvm.args="-Xms1024m -Dstage4.out=$L/stage4.out -Dstage4.label=$v" ) > "$L/ant-$v.log" 2>&1
    rc=$?; log "$v ant rc=$rc after $(( $(date +%s) - s0 )) s; $(grep -m1 'Tests run' "$L/ant-$v.log" || echo 'no Tests run line')"
    echo "P2 $v ant rc=$rc $(grep -m1 'Tests run' "$L/ant-$v.log")" >> "$L/summary.txt"
    cp "$C/build/test/output/TEST-org.apache.cassandra.probe.IndexSummaryCapProbeTest.xml" "$L/TEST-$v.xml" 2>/dev/null
    # harness fix H1 (after run 1): the test log is build/test/logs/_jdk<N>/TEST-<class>.log (both JVMs append to it); the readback is its last Initializing line
    grep -h 'Initializing index summary manager\|Redistributing index summaries\|Completed resizing of index summaries\|index summaries: downsample' \
      "$C"/build/test/logs/*/*IndexSummaryCapProbeTest*/system.log "$C"/build/test/logs/*/TEST-*IndexSummaryCapProbeTest*.log 2>/dev/null | cut -c1-260 > "$L/ism-lines-$v.txt"
    grep 'Initializing index summary manager' "$L/ism-lines-$v.txt" | tail -1 | sed "s/^/READBACK $v: /" >> "$L/summary.txt"
    du -sh "$C/build/test/cassandra" >> "$L/commands.log" 2>&1
    rm -rf "${C:?}/build/test/cassandra"
  done
  git -C "$C" checkout -- test/conf/cassandra.yaml
  rm -f "$C/test/unit/org/apache/cassandra/probe/IndexSummaryCapProbeTest.java"; rmdir "$C/test/unit/org/apache/cassandra/probe" 2>/dev/null
  log "clone status after cleanup: $(git -C "$C" status --short | wc -l | tr -d ' ') entries"
  grep -E "STAGE4 (run|reads|reading|done)" "$L/stage4.out" | cut -c1-400 >> "$L/summary.txt"
fi
log "unit-run $WHAT done"
