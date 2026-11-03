#!/usr/bin/env bash
# Unit tier (B2, amended 2026-10-25) of commitlog_segment_size-applySimpleConfig-commitlog_segment_size--autonomous.
# Adapted from harness/index_summary_capacity-applySimpleConfig-indexSummaryCapacityInMiB--autonomous/unit-run.sh (names, clone,
# knob, variants, test class, yaml edit).
# usage: source ~/Library/Caches/stage4/env.sh; unit-run.sh [p1|p2|all]
#   Program 1 (ConfigProbe, copied unchanged): yaml variants 0MiB 1MiB 32MiB 2047MiB 2048MiB 512KiB with getter getCommitLogSegmentSize,
#     then getMaxMutationSize for 1MiB 32MiB 2047MiB; each its own java, -Xms1G -Xmx1G, JDK 11 module flags of build.xml:244-261.
#   Mechanism (SegmentSizeProbeTest): one `ant testsome` per configuration {2MiB, 8MiB, 32MiB, 2MiB+mms512KiB}; line 10 of
#     test/conf/cassandra.yaml (commitlog_segment_size: 5MiB) replaced, memtable_heap_space: 512MiB appended (and max_mutation_size:
#     512KiB for the control); restored with git checkout; $C/build/test/cassandra removed before each JVM.
# Clone C (default $W/cassandra-run15); probe dir P=$W/probe-cls; logs L=$W/logs/commitlog_segment_size-applySimpleConfig/unit
set -uo pipefail
WHAT=${1:-all}
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run15}; P=${P:-$W/probe-cls}
L=${L:-$W/logs/commitlog_segment_size-applySimpleConfig/unit}
mkdir -p "$L"
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
log "unit-run $WHAT clone=$C $(git -C "$C" describe --tags) $(git -C "$C" rev-parse HEAD); runner sha256 $(shasum -a 256 "$0" | cut -c1-16)"
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
  grep -n '^commitlog_segment_size:\|^max_mutation_size' "$P/base.yaml" | tee -a "$L/commands.log"
  probe() {   # probe <value> <getter> <tag>
    local v=$1 g=$2 tag=$3 y="$P/$1.yaml"
    sed "s/^commitlog_segment_size:.*/commitlog_segment_size: $v/" "$P/base.yaml" > "$y"
    diff "$P/base.yaml" "$y" > "$L/p1-yaml-diff-$v.txt"; rm -rf "${P:?}/data"; mkdir -p "$P/data"
    log "+ java -Xms1G -Xmx1G ConfigProbe $g ($v)"
    ( cd "$P" && exec java -Xms1G -Xmx1G $JFLAGS -cp "$CP:$P/classes" -Dcassandra.config=file://$y -Dcassandra.storagedir=$P/data \
      -Dlogback.configurationFile=$C/test/conf/logback-test.xml ConfigProbe $g ) > "$L/p1-$tag.out" 2>&1 < /dev/null &
    local jp=$!; for i in $(seq 1 60); do kill -0 $jp 2>/dev/null || break; sleep 1; done
    if kill -0 $jp 2>/dev/null; then kill -9 $jp; log "p1 $tag: killed after 60 s (JVM did not exit)"; fi
    wait $jp 2>/dev/null; log "p1 $tag rc=$?"
    echo "P1 $tag :: $(grep -E '^(OK|REJECT) ' "$L/p1-$tag.out" | head -1)" | tee -a "$L/summary.txt" "$L/commands.log"
  }
  for v in 0MiB 1MiB 32MiB 2047MiB 2048MiB 512KiB; do probe $v getCommitLogSegmentSize "$v"; done
  for v in 1MiB 32MiB 2047MiB; do probe $v getMaxMutationSize "$v-mms"; done
  pgrep -f ConfigProbe >/dev/null && log "WARNING: ConfigProbe left" || log "no ConfigProbe left"
  rm -rf "${P:?}/data"
fi

if [ "$WHAT" = p2 ] || [ "$WHAT" = all ]; then
  mkdir -p "$C/test/unit/org/apache/cassandra/probe"
  cp "$H/SegmentSizeProbeTest.java" "$C/test/unit/org/apache/cassandra/probe/"
  rm -f "$L/stage4.out"
  for cfg in ${VALUES:-2MiB 8MiB 32MiB 2MiB+mms512KiB}; do
    v=${cfg%%+*}
    git -C "$C" checkout -- test/conf/cassandra.yaml
    [ "$(sed -n 10p "$C/test/conf/cassandra.yaml")" = "commitlog_segment_size: 5MiB" ] || { log "ABORT: test yaml line 10 is not the expected knob line"; exit 1; }
    grep -q '^max_mutation_size\|^memtable_heap_space' "$C/test/conf/cassandra.yaml" && { log "ABORT: test yaml already sets max_mutation_size/memtable_heap_space"; exit 1; }
    sed -i '' "10s/.*/commitlog_segment_size: $v/" "$C/test/conf/cassandra.yaml"
    printf '\nmemtable_heap_space: 512MiB\n' >> "$C/test/conf/cassandra.yaml"
    case $cfg in *mms512KiB) printf 'max_mutation_size: 512KiB\n' >> "$C/test/conf/cassandra.yaml" ;; esac
    git -C "$C" diff -- test/conf/cassandra.yaml > "$L/p2-yaml-diff-$cfg.txt"
    rm -rf "${C:?}/build/test/cassandra"
    log "+ ant testsome SegmentSizeProbeTest ($cfg); yaml: $(grep -E '^(commitlog_segment_size|memtable_heap_space|max_mutation_size):' "$C/test/conf/cassandra.yaml" | tr '\n' ';')"
    s0=$(date +%s)
    ( cd "$C" && ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.probe.SegmentSizeProbeTest -Dtest.timeout=900000 \
        -Dtest.jvm.args="-Dstage4.out=$L/stage4.out -Dstage4.label=$cfg" ) > "$L/ant-$cfg.log" 2>&1
    rc=$?; log "$cfg ant rc=$rc after $(( $(date +%s) - s0 )) s; $(grep -m1 'Tests run' "$L/ant-$cfg.log" || echo 'no Tests run line')"
    echo "P2 $cfg ant rc=$rc $(grep -m1 'Tests run' "$L/ant-$cfg.log")" >> "$L/summary.txt"
    cp "$C/build/test/output/TEST-org.apache.cassandra.probe.SegmentSizeProbeTest.xml" "$L/TEST-$cfg.xml" 2>/dev/null
    cp "$C"/build/test/logs/*/TEST-org.apache.cassandra.probe.SegmentSizeProbeTest.log "$L/TEST-$cfg.log" 2>/dev/null
    du -sh "$C/build/test/cassandra" >> "$L/commands.log" 2>&1
    rm -rf "${C:?}/build/test/cassandra"
    rm -f "$C"/build/test/logs/*/TEST-org.apache.cassandra.probe.SegmentSizeProbeTest.log
  done
  git -C "$C" checkout -- test/conf/cassandra.yaml
  rm -f "$C/test/unit/org/apache/cassandra/probe/SegmentSizeProbeTest.java"; rmdir "$C/test/unit/org/apache/cassandra/probe" 2>/dev/null
  log "clone status after cleanup: $(git -C "$C" status --short | wc -l | tr -d ' ') entries"
  grep -E "STAGE4 \S+ (run|workload|files|segments|insert|done)" "$L/stage4.out" | cut -c1-400 >> "$L/summary.txt"
fi
log "unit-run $WHAT done"
