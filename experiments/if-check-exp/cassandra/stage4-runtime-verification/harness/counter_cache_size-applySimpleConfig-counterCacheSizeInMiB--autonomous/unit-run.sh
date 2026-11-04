#!/usr/bin/env bash
# Unit tier (B2, amended 2026-10-25) of counter_cache_size-applySimpleConfig-counterCacheSizeInMiB--autonomous.
# Adapted from harness/key_cache_size-applySimpleConfig-keyCacheSizeInMiB--autonomous/unit-run.sh (names, clone, knob, test class).
# usage: source ~/Library/Caches/stage4/env.sh; unit-run.sh [p1|p2|all]
#   Program 1 (ConfigProbe, copied unchanged from the key_cache_size-applySimpleConfig harness): yaml variants
#     -1MiB, 0MiB, unset (auto), each its own java process, -Xms1G -Xmx1G, with the JDK 11 module flags of build.xml:244-261.
#   Mechanism (CounterCacheCapProbeTest): one `ant testsome` per value {0MiB, 1MiB, 4MiB, auto}, -Xms1024m, knob appended to
#     test/conf/cassandra.yaml (which has no counter_cache_size line), restored with git checkout.
# Clone C (default $W/cassandra-run12); probe dir P=$W/probe-ccs; logs L=$W/logs/counter_cache_size-applySimpleConfig/unit
set -uo pipefail
WHAT=${1:-all}
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run12}; P=${P:-$W/probe-ccs}
L=${L:-$W/logs/counter_cache_size-applySimpleConfig/unit}
mkdir -p "$L"
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
log "unit-run $WHAT clone=$C $(git -C "$C" describe --tags) $(git -C "$C" rev-parse HEAD)"
pgrep -f CassandraDaemon >/dev/null && { log "ABORT: a CassandraDaemon is running"; exit 1; }

if [ "$WHAT" = p1 ] || [ "$WHAT" = all ]; then
  rm -rf "$P"; mkdir -p "$P/classes" "$P/data"
  CP="$C/build/classes/main:$C/build/lib/jars/*"
  JFLAGS="--add-exports java.base/jdk.internal.misc=ALL-UNNAMED --add-exports java.base/jdk.internal.ref=ALL-UNNAMED --add-exports java.base/sun.nio.ch=ALL-UNNAMED --add-exports java.management.rmi/com.sun.jmx.remote.internal.rmi=ALL-UNNAMED --add-exports java.rmi/sun.rmi.registry=ALL-UNNAMED --add-exports java.rmi/sun.rmi.server=ALL-UNNAMED --add-exports java.rmi/sun.rmi.transport.tcp=ALL-UNNAMED --add-exports java.sql/java.sql=ALL-UNNAMED --add-opens java.base/java.lang.module=ALL-UNNAMED --add-opens java.base/java.net=ALL-UNNAMED --add-opens java.base/jdk.internal.loader=ALL-UNNAMED --add-opens java.base/jdk.internal.ref=ALL-UNNAMED --add-opens java.base/jdk.internal.reflect=ALL-UNNAMED --add-opens java.base/jdk.internal.math=ALL-UNNAMED --add-opens java.base/jdk.internal.module=ALL-UNNAMED --add-opens java.base/jdk.internal.util.jar=ALL-UNNAMED --add-opens jdk.management/com.sun.management.internal=ALL-UNNAMED"
  log "+ javac ConfigProbe.java"; javac -cp "$CP" -d "$P/classes" "$H/ConfigProbe.java" >> "$L/commands.log" 2>&1 || { log "ABORT: javac failed"; exit 1; }
  grep -v -E '^(data_file_directories|commitlog_directory|saved_caches_directory|hints_directory|cdc_raw_directory):' "$C/conf/cassandra.yaml" \
    | grep -v -E '^    - /var/lib/cassandra/data$' > "$P/base.yaml"
  { echo; echo "# stage-4 directories"; echo "data_file_directories:"; echo "    - $P/data/data"
    echo "commitlog_directory: $P/data/commitlog"; echo "saved_caches_directory: $P/data/saved_caches"
    echo "hints_directory: $P/data/hints"; echo "cdc_raw_directory: $P/data/cdc_raw"; } >> "$P/base.yaml"
  grep -n '^counter_cache_size:' "$P/base.yaml" | tee -a "$L/commands.log"
  for v in -1MiB 0MiB unset; do
    y="$P/$v.yaml"
    if [ $v = unset ]; then cp "$P/base.yaml" "$y"; else sed "s/^counter_cache_size:.*/counter_cache_size: $v/" "$P/base.yaml" > "$y"; fi
    diff "$P/base.yaml" "$y" > "$L/p1-yaml-diff-$v.txt"; rm -rf "$P/data"; mkdir -p "$P/data"
    log "+ java -Xms1G -Xmx1G ConfigProbe getCounterCacheSizeInMiB ($v)"
    # run from $P (key-cache harness fix H3) so logback-test.xml's relative build/test/logs lands outside the repo
    ( cd "$P" && exec java -Xms1G -Xmx1G $JFLAGS -cp "$CP:$P/classes" -Dcassandra.config=file://$y -Dcassandra.storagedir=$P/data \
      -Dlogback.configurationFile=$C/test/conf/logback-test.xml ConfigProbe getCounterCacheSizeInMiB ) > "$L/p1-$v.out" 2>&1 < /dev/null &
    jp=$!; for i in $(seq 1 60); do kill -0 $jp 2>/dev/null || break; sleep 1; done
    if kill -0 $jp 2>/dev/null; then kill -9 $jp; log "p1 $v: killed after 60 s (JVM did not exit)"; fi
    wait $jp 2>/dev/null; log "p1 $v rc=$?"
    echo "P1 $v :: $(grep -E '^(OK|REJECT) ' "$L/p1-$v.out" | head -1)" | tee -a "$L/summary.txt" "$L/commands.log"
  done
  pgrep -f ConfigProbe >/dev/null && log "WARNING: ConfigProbe left" || log "no ConfigProbe left"
  rm -rf "$P/data"
fi

if [ "$WHAT" = p2 ] || [ "$WHAT" = all ]; then
  mkdir -p "$C/test/unit/org/apache/cassandra/probe"
  cp "$H/CounterCacheCapProbeTest.java" "$C/test/unit/org/apache/cassandra/probe/"
  rm -f "$L/stage4.out"
  for v in ${VALUES:-0MiB 1MiB 4MiB auto}; do
    git -C "$C" checkout -- test/conf/cassandra.yaml
    grep -q '^counter_cache_size' "$C/test/conf/cassandra.yaml" && { log "ABORT: test yaml already has counter_cache_size"; exit 1; }
    [ $v = auto ] || printf '\ncounter_cache_size: %s\n' "$v" >> "$C/test/conf/cassandra.yaml"
    git -C "$C" diff -- test/conf/cassandra.yaml > "$L/p2-yaml-diff-$v.txt"
    log "+ ant testsome CounterCacheCapProbeTest ($v); yaml line: $(grep '^counter_cache_size:' "$C/test/conf/cassandra.yaml" || echo '(none = auto)')"
    s0=$(date +%s)
    ( cd "$C" && ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.probe.CounterCacheCapProbeTest \
        -Dtest.jvm.args="-Xms1024m -Dstage4.out=$L/stage4.out -Dstage4.label=$v" ) > "$L/ant-$v.log" 2>&1
    rc=$?; log "$v ant rc=$rc after $(( $(date +%s) - s0 )) s; $(grep -m1 'Tests run' "$L/ant-$v.log" || echo 'no Tests run line')"
    echo "P2 $v ant rc=$rc $(grep -m1 'Tests run' "$L/ant-$v.log")" >> "$L/summary.txt"
    cp "$C/build/test/output/TEST-org.apache.cassandra.probe.CounterCacheCapProbeTest.xml" "$L/TEST-$v.xml" 2>/dev/null
    grep -h 'Initializing counter cache with capacity' "$C"/build/test/logs/*/*CounterCacheCapProbeTest*/system.log "$C"/build/test/logs/*CounterCacheCapProbeTest*.log 2>/dev/null | tail -1 | sed "s/^/READBACK $v: /" >> "$L/summary.txt"
  done
  git -C "$C" checkout -- test/conf/cassandra.yaml
  log "test yaml restored: $(git -C "$C" status --short test/conf/cassandra.yaml | wc -l | tr -d ' ') modified files"
  grep -E "STAGE4 (run|cleared|calibration|final|control)" "$L/stage4.out" >> "$L/summary.txt"
fi
log "unit-run $WHAT done"
