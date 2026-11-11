#!/usr/bin/env bash
# Unit tier (B2, amended 2026-10-25) of max_mutation_size-applySimpleConfig-max_mutation_size--autonomous.
# Adapted from harness/commitlog_segment_size-applySimpleConfig-commitlog_segment_size--autonomous/unit-run.sh (copied, then changed:
# names, clone, variants, test class, yaml edit).
# usage: source ~/Library/Caches/stage4/env.sh; unit-run.sh [p1|p2|all]
#   Program 1 (ConfigProbe, copied unchanged): (segment, max_mutation_size) variants, getter getMaxMutationSize, each its own java,
#     -Xms1G -Xmx1G, JDK 11 module flags of build.xml:244-261.
#   Mechanism (MaxMutationProbeTest): one `ant testsome` per value in $VALUES (default 1024KiB 1026KiB 2048KiB unset);
#     `max_mutation_size: <v>` appended to test/conf/cassandra.yaml (line 10 stays commitlog_segment_size: 5MiB); restored with
#     git checkout; $C/build/test/cassandra removed before each JVM.
# Clone C (default $W/cassandra-run16); probe dir P=$W/probe-mms; logs L (default $W/logs/max_mutation_size-applySimpleConfig/unit)
set -uo pipefail
WHAT=${1:-all}
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run16}; P=${P:-$W/probe-mms}
L=${L:-$W/logs/max_mutation_size-applySimpleConfig/unit}
mkdir -p "$L"
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
log "unit-run $WHAT clone=$C $(git -C "$C" describe --tags) $(git -C "$C" rev-parse HEAD); runner sha256 $(shasum -a 256 "$0" | cut -c1-16)"
pgrep -f CassandraDaemon >/dev/null && { log "ABORT: a Cassandra node is running"; exit 1; }
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
  probe() {   # probe <segment> <max_mutation_size|unset>
    local s=$1 m=$2 tag="$1-$2" y="$P/$1-$2.yaml"
    sed "s/^commitlog_segment_size:.*/commitlog_segment_size: $s/" "$P/base.yaml" > "$y"
    [ "$m" != unset ] && printf 'max_mutation_size: %s\n' "$m" >> "$y"
    diff "$P/base.yaml" "$y" > "$L/p1-yaml-diff-$tag.txt"; rm -rf "${P:?}/data"; mkdir -p "$P/data"
    log "+ java -Xms1G -Xmx1G ConfigProbe getMaxMutationSize ($tag)"
    ( cd "$P" && exec java -Xms1G -Xmx1G $JFLAGS -cp "$CP:$P/classes" -Dcassandra.config=file://$y -Dcassandra.storagedir=$P/data \
      -Dlogback.configurationFile=$C/test/conf/logback-test.xml ConfigProbe getMaxMutationSize ) > "$L/p1-$tag.out" 2>&1 < /dev/null &
    local jp=$!; for i in $(seq 1 60); do kill -0 $jp 2>/dev/null || break; sleep 1; done
    if kill -0 $jp 2>/dev/null; then kill -9 $jp; log "p1 $tag: killed after 60 s (JVM did not exit)"; fi
    wait $jp 2>/dev/null; log "p1 $tag rc=$?"
    echo "P1 $tag :: $(grep -E '^(OK|REJECT) ' "$L/p1-$tag.out" | head -1)" | tee -a "$L/summary.txt" "$L/commands.log"
  }
  probe 8MiB 4096KiB; probe 8MiB 4097KiB; probe 8MiB unset; probe 32MiB 16384KiB; probe 32MiB 16385KiB; probe 32MiB unset
  pgrep -f ConfigProbe >/dev/null && log "WARNING: ConfigProbe left" || log "no ConfigProbe left"
  rm -rf "${P:?}/data"
fi

if [ "$WHAT" = p2 ] || [ "$WHAT" = all ]; then
  mkdir -p "$C/test/unit/org/apache/cassandra/probe"
  cp "$H/MaxMutationProbeTest.java" "$C/test/unit/org/apache/cassandra/probe/"
  rm -f "$L/stage4.out"
  for v in ${VALUES:-1024KiB 1026KiB 2048KiB unset}; do
    git -C "$C" checkout -- test/conf/cassandra.yaml
    [ "$(sed -n 10p "$C/test/conf/cassandra.yaml")" = "commitlog_segment_size: 5MiB" ] || { log "ABORT: test yaml line 10 is not the expected segment line"; exit 1; }
    grep -q '^max_mutation_size' "$C/test/conf/cassandra.yaml" && { log "ABORT: test yaml already sets max_mutation_size"; exit 1; }
    [ "$v" != unset ] && printf '\nmax_mutation_size: %s\n' "$v" >> "$C/test/conf/cassandra.yaml"
    git -C "$C" diff -- test/conf/cassandra.yaml > "$L/p2-yaml-diff-$v.txt"
    rm -rf "${C:?}/build/test/cassandra"
    log "+ ant testsome MaxMutationProbeTest ($v); yaml: $(grep -E '^(commitlog_segment_size|max_mutation_size):' "$C/test/conf/cassandra.yaml" | tr '\n' ';')"
    s0=$(date +%s)
    ( cd "$C" && ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.probe.MaxMutationProbeTest -Dtest.timeout=900000 \
        -Dtest.jvm.args="-Dstage4.out=$L/stage4.out -Dstage4.label=$v" ) > "$L/ant-$v.log" 2>&1
    rc=$?; log "$v ant rc=$rc after $(( $(date +%s) - s0 )) s; $(grep -m1 'Tests run' "$L/ant-$v.log" || echo 'no Tests run line')"
    echo "P2 $v ant rc=$rc $(grep -m1 'Tests run' "$L/ant-$v.log")" >> "$L/summary.txt"
    cp "$C/build/test/output/TEST-org.apache.cassandra.probe.MaxMutationProbeTest.xml" "$L/TEST-$v.xml" 2>/dev/null
    cp "$C"/build/test/logs/*/TEST-org.apache.cassandra.probe.MaxMutationProbeTest.log "$L/TEST-$v.log" 2>/dev/null
    du -sh "$C/build/test/cassandra" >> "$L/commands.log" 2>&1
    rm -rf "${C:?}/build/test/cassandra"
    rm -f "$C"/build/test/logs/*/TEST-org.apache.cassandra.probe.MaxMutationProbeTest.log
  done
  git -C "$C" checkout -- test/conf/cassandra.yaml
  rm -f "$C/test/unit/org/apache/cassandra/probe/MaxMutationProbeTest.java"; rmdir "$C/test/unit/org/apache/cassandra/probe" 2>/dev/null
  log "clone status after cleanup: $(git -C "$C" status --short | wc -l | tr -d ' ') entries"
  grep -E "STAGE4 \S+ (run|insert|boundary|direct|workload|done)" "$L/stage4.out" | cut -c1-420 >> "$L/summary.txt"
fi
log "unit-run $WHAT done"
