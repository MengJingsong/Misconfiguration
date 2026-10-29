#!/usr/bin/env bash
# usage: unit-run.sh <variant|stock> <modes> [label] [Xmx]     Unit tier (B2). The variant class directory ~/s4-ew-var/<variant>/ goes first on the class path.
# One JVM per call through the plain java launcher (same flags as the row_overhead harness); output $OUT/<label>.out (PROBE lines) and .log.
set -uo pipefail
v=$1; modes=$2; label=${3:-$v-$modes}; xmx=${4:-3g}
C=${CASSANDRA_HOME:-$HOME/s4-ew}; H=$(cd "$(dirname "$0")" && pwd); OUT=${OUT:-$HOME/stage4-logs/ew/unit}
mkdir -p "$OUT" "$HOME/stage4-tmp/ew" "$HOME/s4-ew-var/_probe"
VC=""; [ "$v" != stock ] && VC="$HOME/s4-ew-var/$v:"
CP="${VC}$C/build/classes/main:$C/build/lib/jars/*:$C/lib/*"
javac -nowarn -proc:none -cp "$CP" -d "$HOME/s4-ew-var/_probe" "$H/WasteProbe.java" 2>&1 | grep -v '^Note:'
grep -E "^--(add|illegal)" "$C/conf/jvm11-server.options" > "$OUT/jvm11-opens.args"
: > "${OUT:?}/${label:?}.out"
echo "== $label variant=$v modes=$modes $(date -u +%FT%TZ)" | tee "$OUT/$label.log"
cd "$HOME/stage4-tmp/ew" || exit 1   # the unit yaml has relative storage paths (build/test/cassandra/...): keep them off the repository
java @"$OUT/jvm11-opens.args" -Xmx$xmx -Dcassandra.config=file://$C/test/conf/cassandra.yaml -Dcassandra.storagedir=$HOME/stage4-tmp/ew/storage \
  -Dcassandra.logdir=$HOME/stage4-tmp/ew/logs -cp "$HOME/s4-ew-var/_probe:$CP" org.apache.cassandra.db.partitions.WasteProbe "$OUT/$label.out" "$modes" 2>&1 | tee -a "$OUT/$label.log" | grep -v '^PROBE' | tail -15
echo "== exit ${PIPESTATUS[0]} $(date -u +%FT%TZ)" | tee -a "$OUT/$label.log"
