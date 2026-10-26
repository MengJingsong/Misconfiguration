#!/usr/bin/env bash
# Unit tier (B2) of max-cloned-size-allocate-size--autonomous. usage: bash unit-run.sh <run> [instrument]
# Compiles SlabCapProbe outside the tree (~/s4-b7-mc-logs/classes), one JVM per scenario.
# Output ~/s4-b7-mc-logs/<run>/unit/{<scenario>.out,summary.txt}. "instrument" runs only known-answer checks (not readings).
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/s4-b7-mc}; LG=$HOME/s4-b7-mc-logs
RUN=${1:?run name}; MODE=${2:-full}; L=$LG/$RUN/unit; mkdir -p "$L"; S=$L/summary.txt; : > "$S"
CL=$LG/classes; mkdir -p "$CL"
say() { echo "$*" | tee -a "$S"; }
CP="$C/build/classes/main:$C/build/classes/thrift:$C/build/lib/jars/*:$C/conf"
javac -nowarn -d "$CL" -cp "$CP" "$H/SlabCapProbe.java" > "$L/javac.log" 2>&1 || { say "javac failed"; head -20 "$L/javac.log"; exit 1; }
say "unit-run $RUN $MODE $(date -Is) host $(hostname -s) tree $C $(git -C $C describe --tags) java $(java -version 2>&1 | head -1)"
say "harness md5 $(md5sum "$H/SlabCapProbe.java" | cut -c1-32)"
JOPTS="-Xmx1g -XX:MaxDirectMemorySize=1g -XX:NativeMemoryTracking=summary -Dcassandra.config=file://$C/conf/cassandra.yaml -Dcassandra.storagedir=$LG/$RUN/storage --add-exports java.base/jdk.internal.misc=ALL-UNNAMED --add-exports java.base/jdk.internal.ref=ALL-UNNAMED --add-opens java.base/jdk.internal.ref=ALL-UNNAMED --add-exports java.base/sun.nio.ch=ALL-UNNAMED --add-exports java.management.rmi/com.sun.jmx.remote.internal.rmi=ALL-UNNAMED --add-exports java.rmi/sun.rmi.registry=ALL-UNNAMED --add-exports java.rmi/sun.rmi.server=ALL-UNNAMED --add-exports java.sql/java.sql=ALL-UNNAMED --add-opens java.base/java.lang.module=ALL-UNNAMED --add-opens java.base/jdk.internal.loader=ALL-UNNAMED --add-opens java.base/jdk.internal.reflect=ALL-UNNAMED --add-opens java.base/jdk.internal.math=ALL-UNNAMED --add-opens java.base/jdk.internal.module=ALL-UNNAMED --add-opens java.base/jdk.internal.util.jar=ALL-UNNAMED --add-opens jdk.management/com.sun.management.internal=ALL-UNNAMED"
run1() { local mode=$1 l=$2 s=$3; local tag=$mode-L$l-S$s
  timeout 120 java $JOPTS -cp "$CL:$CP" org.apache.cassandra.utils.memory.SlabCapProbe $mode $l $s > "$L/$tag.out" 2>&1; local rc=$?
  say "$tag exit=$rc checks=$(grep -c '^STAGE4 check' "$L/$tag.out") ok=$(grep -c '^STAGE4 check.* ok ' "$L/$tag.out") MISMATCH=$(grep -c '^STAGE4 check.* MISMATCH ' "$L/$tag.out") done=$(grep -c '^STAGE4 done' "$L/$tag.out")"
  grep ' MISMATCH ' "$L/$tag.out" | tee -a "$S"; }
if [ "$MODE" = instrument ]; then
  # hand-computed known answers, L = 4 MiB: S = 1 MiB/9 -> use S=116736: N1 = floor(2 MiB/116736) = 17 -> 3 regions (8+8+1); plateau N = 35 -> 5 regions (8*4+3) = 5 MiB
  run1 fill 4 116736
  o=$L/fill-L4-S116736.out
  grep -q 'reading p1_n=17$' $o && grep -q 'reading p1_direct_delta=3145728$' $o && grep -q 'reading n=35$' $o && grep -q 'reading direct_delta=5242880$' $o && grep -q 'reading count_delta=5$' $o \
    && say "EXPECTED instrument known answer (S=116736, L=4 MiB: p1 17 allocations in 3 regions, plateau 35 in 5 regions = 5 MiB): ok" || say "EXPECTED instrument known answer: MISMATCH"
  run1 fill 4 131073
  o=$L/fill-L4-S131073.out
  grep -q 'reading n=31$' $o && grep -q 'reading used=4063263$' $o && grep -q 'reading direct_delta=4063263$' $o && grep -q 'reading count_delta=31$' $o \
    && say "EXPECTED instrument known answer (S=131073, L=4 MiB: 31 dedicated buffers, 4,063,263 B): ok" || say "EXPECTED instrument known answer oversize: MISMATCH"
  exit 0
fi
# first-trigger check: the plateau must be reached in the first run, else stop
run1 fill 64 102400
grep -q '^STAGE4 check fill-reached-limit ok' "$L/fill-L64-S102400.out" || { say "first-trigger check failed: stop"; exit 1; }
for l in 32 64 128; do for s in 65536 102400 116736 131072 131073 163840 262144; do [ $l = 64 -a $s = 102400 ] && continue; run1 fill $l $s; done; done
for s in 102400 262144; do run1 blocking 64 $s; done
for s in 102400 131072 131073 262144; do run1 control 64 $s; done
say "EXPECTED all runs finished with done=1 and MISMATCH=0 (B2f as amended)"
tot=$(grep -h '^STAGE4 check' "$L"/*.out | wc -l); mm=$(grep -h '^STAGE4 check.* MISMATCH ' "$L"/*.out | wc -l)
say "unit-run end $(date -Is) total checks $tot MISMATCH $mm"
