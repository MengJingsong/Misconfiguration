#!/usr/bin/env bash
# Unit tier (B2, amended 2026-10-25) of max_value_size-applySimpleConfig-max_value_size--autonomous.
# Adapted from harness/max_mutation_size-applySimpleConfig-max_mutation_size--autonomous/unit-run.sh (copied, then changed: names,
# clone, variants, getter; the mechanism is a plain java program, ValueReadProbe, not an ant testsome).
# usage: source ~/Library/Caches/stage4/env.sh; unit-run.sh [p1|p2|all] [values...]
#   p1: ConfigProbe (copied unchanged) for max_value_size in 0MiB 1MiB 2047MiB 2048MiB unset, getter getMaxValueSize,
#       each its own java -Xms1G -Xmx1G.
#   p2: ValueReadProbe, one java -Xms1G -Xmx3G per value (default 1MiB 4MiB unset).
#   Both: JDK 11 module flags of build.xml:244-261; working directory $P; probe yaml = the clone's conf/cassandra.yaml with the five
#   directories under $P/data and a max_value_size line appended when set. The clone's test yaml is not touched.
# Clone C (default $W/cassandra-run20); probe dir P=$W/probe-mvs; logs L (default $W/logs/max_value_size-applySimpleConfig/unit)
set -uo pipefail
WHAT=${1:-all}; shift || true
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run20}; P=${P:-$W/probe-mvs}
L=${L:-$W/logs/max_value_size-applySimpleConfig/unit}
mkdir -p "$L"
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
log "unit-run $WHAT clone=$C $(git -C "$C" describe --tags) $(git -C "$C" rev-parse HEAD); runner sha256 $(shasum -a 256 "$0" | cut -c1-16)"
log "harness sha256: $(cd "$H" && shasum -a 256 ConfigProbe.java ValueReadProbe.java | awk '{print $2"="substr($1,1,16)}' | tr '\n' ' ')"
pgrep -f CassandraDaemon >/dev/null && { log "ABORT: a Cassandra node is running"; exit 1; }
df -h "$W" | tail -1 >> "$L/commands.log"

rm -rf "${P:?}"; mkdir -p "$P/classes" "$P/data"
CP="$C/build/classes/main:$C/build/lib/jars/*"
JFLAGS="--add-exports java.base/jdk.internal.misc=ALL-UNNAMED --add-exports java.base/jdk.internal.ref=ALL-UNNAMED --add-exports java.base/sun.nio.ch=ALL-UNNAMED --add-exports java.management.rmi/com.sun.jmx.remote.internal.rmi=ALL-UNNAMED --add-exports java.rmi/sun.rmi.registry=ALL-UNNAMED --add-exports java.rmi/sun.rmi.server=ALL-UNNAMED --add-exports java.rmi/sun.rmi.transport.tcp=ALL-UNNAMED --add-exports java.sql/java.sql=ALL-UNNAMED --add-opens java.base/java.lang.module=ALL-UNNAMED --add-opens java.base/java.net=ALL-UNNAMED --add-opens java.base/jdk.internal.loader=ALL-UNNAMED --add-opens java.base/jdk.internal.ref=ALL-UNNAMED --add-opens java.base/jdk.internal.reflect=ALL-UNNAMED --add-opens java.base/jdk.internal.math=ALL-UNNAMED --add-opens java.base/jdk.internal.module=ALL-UNNAMED --add-opens java.base/jdk.internal.util.jar=ALL-UNNAMED --add-opens jdk.management/com.sun.management.internal=ALL-UNNAMED"
log "+ javac ConfigProbe.java ValueReadProbe.java"
javac -cp "$CP" -d "$P/classes" "$H/ConfigProbe.java" "$H/ValueReadProbe.java" >> "$L/commands.log" 2>&1 || { log "ABORT: javac failed"; exit 1; }
grep -v -E '^(data_file_directories|commitlog_directory|saved_caches_directory|hints_directory|cdc_raw_directory):' "$C/conf/cassandra.yaml" \
  | grep -v -E '^    - /var/lib/cassandra/data$' > "$P/base.yaml"
{ echo; echo "# stage-4 directories"; echo "data_file_directories:"; echo "    - $P/data/data"
  echo "commitlog_directory: $P/data/commitlog"; echo "saved_caches_directory: $P/data/saved_caches"
  echo "hints_directory: $P/data/hints"; echo "cdc_raw_directory: $P/data/cdc_raw"; } >> "$P/base.yaml"
grep -n '^max_value_size\|^# max_value_size' "$P/base.yaml" | tee -a "$L/commands.log"

jrun() {   # jrun <tag> <xmx> <yaml> <out> <main> [args]
  local tag=$1 xmx=$2 y=$3 out=$4; shift 4
  log "+ java -Xms1G -Xmx$xmx $* ($tag)"
  ( cd "$P" && exec java -Xms1G -Xmx$xmx $JFLAGS -cp "$CP:$P/classes" -Dcassandra.config=file://$y -Dcassandra.storagedir=$P/data \
    -Dlogback.configurationFile=$C/test/conf/logback-test.xml "$@" ) > "$out" 2>&1 < /dev/null &
  local jp=$!; for i in $(seq 1 120); do kill -0 $jp 2>/dev/null || break; sleep 1; done
  if kill -0 $jp 2>/dev/null; then kill -9 $jp; log "$tag: killed after 120 s (JVM did not exit)"; fi
  wait $jp 2>/dev/null; local rc=$?; log "$tag rc=$rc"; return 0
}
mkyaml() {  # mkyaml <value|unset> -> path
  local v=$1 y="$P/mvs-$1.yaml"
  cp "$P/base.yaml" "$y"; [ "$v" != unset ] && printf '\nmax_value_size: %s\n' "$v" >> "$y"
  diff "$P/base.yaml" "$y" > "$L/yaml-diff-$v.txt"; echo "$y"
}

if [ "$WHAT" = p1 ] || [ "$WHAT" = all ]; then
  for v in 0MiB 1MiB 2047MiB 2048MiB unset; do
    y=$(mkyaml $v); rm -rf "${P:?}/data"; mkdir -p "$P/data"
    jrun "p1-$v" 1G "$y" "$L/p1-$v.out" ConfigProbe getMaxValueSize
    echo "P1 $v :: $(grep -E '^(OK|REJECT) ' "$L/p1-$v.out" | head -1)" | tee -a "$L/summary.txt" >> "$L/commands.log"
  done
fi

if [ "$WHAT" = p2 ] || [ "$WHAT" = all ]; then
  VALUES=${*:-1MiB 4MiB unset}
  for v in $VALUES; do
    y=$(mkyaml $v); rm -rf "${P:?}/data"; mkdir -p "$P/data"
    jrun "p2-$v" 3G "$y" "$L/p2-$v.out" ValueReadProbe "$v"
    grep '^STAGE4 ' "$L/p2-$v.out" | sed "s/^/P2 $v :: /" | cut -c1-400 >> "$L/summary.txt"
  done
fi
pgrep -f 'ConfigProbe|ValueReadProbe' >/dev/null && log "WARNING: probe JVM left" || log "no probe JVM left"
rm -rf "${P:?}/data"
log "clone status: $(git -C "$C" status --short | wc -l | tr -d ' ') entries"
log "unit-run $WHAT done"
