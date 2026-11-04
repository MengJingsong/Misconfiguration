#!/usr/bin/env bash
# Unit tier (B2, amended 2026-10-25) of compressed_read_ahead_buffer_size-applySimpleConfig-compressed_read_ahead_buffer_size--autonomous.
# Adapted from harness/max_value_size-applySimpleConfig-max_value_size--autonomous/unit-run.sh (p1) and
# harness/counter_cache_size-applySimpleConfig-counterCacheSizeInMiB--autonomous/unit-run.sh (p2: ant testsome per arm, test yaml
# edited and restored with git checkout). Copied, then changed: names, clone, knob, values, test class, file_cache_enabled edit.
# usage: source ~/Library/Caches/stage4/env.sh; unit-run.sh [p1|p2|all] [arms...]
#   p1: ConfigProbe (copied unchanged) for compressed_read_ahead_buffer_size in 0KiB 1KiB 255KiB 256KiB unset, getter
#       getCompressedReadAheadBufferSize, each its own java -Xms1G -Xmx1G, JDK 11 module flags of build.xml:244-261, cwd $P.
#   p2: ReadAheadProbeTest, one ant testsome per arm (default 0KiB 256KiB-chunk256 256KiB 4096KiB ctl-cache; amendment D2:
#       an arm <B>-chunk<N> uses B and a table with chunk_length_in_kb N, passed as -Dstage4.chunk_kb). Per arm: test yaml restored,
#       line 55 -> file_cache_enabled: false (ctl-cache keeps true), compressed_read_ahead_buffer_size: <B> appended (ctl-cache 4096KiB).
# Clone C (default $W/cassandra-run21); probe dir P=$W/probe-crab; logs L (default $W/logs/compressed_read_ahead_buffer_size-applySimpleConfig/unit)
set -uo pipefail
WHAT=${1:-all}; shift || true
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run21}; P=${P:-$W/probe-crab}
L=${L:-$W/logs/compressed_read_ahead_buffer_size-applySimpleConfig/unit}
mkdir -p "$L"
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
log "unit-run $WHAT clone=$C $(git -C "$C" describe --tags) $(git -C "$C" rev-parse HEAD); runner sha256 $(shasum -a 256 "$0" | cut -c1-16)"
log "harness sha256: $(cd "$H" && shasum -a 256 ConfigProbe.java ReadAheadProbeTest.java | awk '{print $2"="substr($1,1,16)}' | tr '\n' ' ')"
d=$(ps -eo command | grep '[C]assandraDaemon'); [ -n "$d" ] && { log "ABORT: a Cassandra node is running"; exit 1; }
df -h "$W" | tail -1 >> "$L/commands.log"

if [ "$WHAT" = p1 ] || [ "$WHAT" = all ]; then
  rm -rf "${P:?}"; mkdir -p "$P/classes" "$P/data"
  CP="$C/build/classes/main:$C/build/lib/jars/*"
  JFLAGS="--add-exports java.base/jdk.internal.misc=ALL-UNNAMED --add-exports java.base/jdk.internal.ref=ALL-UNNAMED --add-exports java.base/sun.nio.ch=ALL-UNNAMED --add-exports java.management.rmi/com.sun.jmx.remote.internal.rmi=ALL-UNNAMED --add-exports java.rmi/sun.rmi.registry=ALL-UNNAMED --add-exports java.rmi/sun.rmi.server=ALL-UNNAMED --add-exports java.rmi/sun.rmi.transport.tcp=ALL-UNNAMED --add-exports java.sql/java.sql=ALL-UNNAMED --add-opens java.base/java.lang.module=ALL-UNNAMED --add-opens java.base/java.net=ALL-UNNAMED --add-opens java.base/jdk.internal.loader=ALL-UNNAMED --add-opens java.base/jdk.internal.ref=ALL-UNNAMED --add-opens java.base/jdk.internal.reflect=ALL-UNNAMED --add-opens java.base/jdk.internal.math=ALL-UNNAMED --add-opens java.base/jdk.internal.module=ALL-UNNAMED --add-opens java.base/jdk.internal.util.jar=ALL-UNNAMED --add-opens jdk.management/com.sun.management.internal=ALL-UNNAMED"
  log "+ javac ConfigProbe.java"
  javac -cp "$CP" -d "$P/classes" "$H/ConfigProbe.java" >> "$L/commands.log" 2>&1 || { log "ABORT: javac failed"; exit 1; }
  grep -v -E '^(data_file_directories|commitlog_directory|saved_caches_directory|hints_directory|cdc_raw_directory):' "$C/conf/cassandra.yaml" \
    | grep -v -E '^    - /var/lib/cassandra/data$' > "$P/base.yaml"
  { echo; echo "# stage-4 directories"; echo "data_file_directories:"; echo "    - $P/data/data"
    echo "commitlog_directory: $P/data/commitlog"; echo "saved_caches_directory: $P/data/saved_caches"
    echo "hints_directory: $P/data/hints"; echo "cdc_raw_directory: $P/data/cdc_raw"; } >> "$P/base.yaml"
  grep -n 'compressed_read_ahead_buffer_size' "$P/base.yaml" | tee -a "$L/commands.log"
  for v in 0KiB 1KiB 255KiB 256KiB unset; do
    y="$P/crab-$v.yaml"; cp "$P/base.yaml" "$y"; [ $v != unset ] && printf '\ncompressed_read_ahead_buffer_size: %s\n' "$v" >> "$y"
    diff "$P/base.yaml" "$y" > "$L/p1-yaml-diff-$v.txt"; rm -rf "${P:?}/data"; mkdir -p "$P/data"
    log "+ java -Xms1G -Xmx1G ConfigProbe getCompressedReadAheadBufferSize ($v)"
    ( cd "$P" && exec java -Xms1G -Xmx1G $JFLAGS -cp "$CP:$P/classes" -Dcassandra.config=file://$y -Dcassandra.storagedir=$P/data \
      -Dlogback.configurationFile=$C/test/conf/logback-test.xml ConfigProbe getCompressedReadAheadBufferSize ) > "$L/p1-$v.out" 2>&1 < /dev/null &
    jp=$!; for i in $(seq 1 120); do kill -0 $jp 2>/dev/null || break; sleep 1; done
    if kill -0 $jp 2>/dev/null; then kill -9 $jp; log "p1 $v: killed after 120 s (JVM did not exit)"; fi
    wait $jp 2>/dev/null; log "p1 $v rc=$?"
    echo "P1 $v :: $(grep -E '^(OK|REJECT) ' "$L/p1-$v.out" | head -1)" | tee -a "$L/summary.txt" >> "$L/commands.log"
  done
  pgrep -f ConfigProbe >/dev/null && log "WARNING: ConfigProbe left" || log "no ConfigProbe left"
  rm -rf "${P:?}"
fi

if [ "$WHAT" = p2 ] || [ "$WHAT" = all ]; then
  ARMS=${*:-0KiB 256KiB-chunk256 256KiB 4096KiB ctl-cache}
  mkdir -p "$C/test/unit/org/apache/cassandra/probe"
  cp "$H/ReadAheadProbeTest.java" "$C/test/unit/org/apache/cassandra/probe/"
  for a in $ARMS; do
    CK=16
    if [ $a = ctl-cache ]; then B=4096KiB; FC=true; elif [[ $a == *-chunk* ]]; then B=${a%%-chunk*}; CK=${a##*-chunk}; FC=false; else B=$a; FC=false; fi
    git -C "$C" checkout -- test/conf/cassandra.yaml
    grep -q '^compressed_read_ahead_buffer_size' "$C/test/conf/cassandra.yaml" && { log "ABORT: test yaml already has the knob"; exit 1; }
    [ "$(sed -n 55p "$C/test/conf/cassandra.yaml")" = "file_cache_enabled: true" ] || { log "ABORT: test yaml line 55 is not file_cache_enabled: true"; exit 1; }
    sed -i '' "55s/.*/file_cache_enabled: $FC/" "$C/test/conf/cassandra.yaml"
    printf '\ncompressed_read_ahead_buffer_size: %s\n' "$B" >> "$C/test/conf/cassandra.yaml"
    git -C "$C" diff -- test/conf/cassandra.yaml > "$L/p2-yaml-diff-$a.txt"
    log "+ ant testsome ReadAheadProbeTest ($a, chunk ${CK}KiB); yaml: $(grep -E '^(file_cache_enabled|compressed_read_ahead_buffer_size|disk_access_mode):' "$C/test/conf/cassandra.yaml" | tr '\n' ' ')"
    s0=$(date +%s)
    ( cd "$C" && ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.probe.ReadAheadProbeTest \
        -Dtest.jvm.args="-Dstage4.out=$L/stage4.out -Dstage4.label=$a -Dstage4.chunk_kb=$CK" ) > "$L/ant-$a.log" 2>&1
    rc=$?; log "$a ant rc=$rc after $(( $(date +%s) - s0 )) s; $(grep -m1 'Tests run' "$L/ant-$a.log" || echo 'no Tests run line')"
    echo "P2 $a ant rc=$rc $(grep -m1 'Tests run' "$L/ant-$a.log")" >> "$L/summary.txt"
    cp "$C/build/test/output/TEST-org.apache.cassandra.probe.ReadAheadProbeTest.xml" "$L/TEST-$a.xml" 2>/dev/null
    grep "label=$a " "$L/stage4.out" | sed "s/^/P2 $a :: /" >> "$L/summary.txt"
  done
  git -C "$C" checkout -- test/conf/cassandra.yaml
  rm -rf "$C/test/unit/org/apache/cassandra/probe"
  log "test yaml restored, probe removed: clone status $(git -C "$C" status --short | wc -l | tr -d ' ') entries"
fi
log "unit-run $WHAT done"
