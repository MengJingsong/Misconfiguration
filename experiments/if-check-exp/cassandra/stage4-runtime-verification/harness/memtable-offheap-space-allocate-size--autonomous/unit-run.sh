#!/usr/bin/env bash
# Unit tier (B2) of memtable-offheap-space-allocate-size--autonomous. usage: bash unit-run.sh <run> [instrument]
# Compiles OffheapCapProbe into the tree's class dir outside the tree (~/s4-b7-mo-logs/classes), runs one JVM per scenario.
# Output ~/s4-b7-mo-logs/<run>/unit/{<scenario>.out,summary.txt}. "instrument" runs only the known-answer check (not a reading).
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/s4-b7-mo}; LG=$HOME/s4-b7-mo-logs
RUN=${1:?run name}; MODE=${2:-full}; L=$LG/$RUN/unit; mkdir -p "$L"; S=$L/summary.txt; : > "$S"
CL=$LG/classes; mkdir -p "$CL"
say() { echo "$*" | tee -a "$S"; }
CP="$C/build/classes/main:$C/build/classes/thrift:$C/build/lib/jars/*:$C/conf"
javac -nowarn -d "$CL" -cp "$CP" "$H/OffheapCapProbe.java" > "$L/javac.log" 2>&1 || { say "javac failed"; cat "$L/javac.log" | head -20; exit 1; }
say "unit-run $RUN $MODE $(date -Is) host $(hostname -s) tree $C $(git -C $C describe --tags) java $(java -version 2>&1 | head -1)"
say "harness md5 $(md5sum "$H/OffheapCapProbe.java" | cut -c1-32)"
JOPTS="-Xmx512m -XX:NativeMemoryTracking=summary -Dcassandra.config=file://$C/conf/cassandra.yaml -Dcassandra.storagedir=$LG/$RUN/storage --add-exports java.base/jdk.internal.misc=ALL-UNNAMED --add-exports java.base/jdk.internal.ref=ALL-UNNAMED --add-opens java.base/jdk.internal.ref=ALL-UNNAMED --add-exports java.base/sun.nio.ch=ALL-UNNAMED --add-exports java.management.rmi/com.sun.jmx.remote.internal.rmi=ALL-UNNAMED --add-exports java.rmi/sun.rmi.registry=ALL-UNNAMED --add-exports java.rmi/sun.rmi.server=ALL-UNNAMED --add-exports java.sql/java.sql=ALL-UNNAMED --add-opens java.base/java.lang.module=ALL-UNNAMED --add-opens java.base/jdk.internal.loader=ALL-UNNAMED --add-opens java.base/jdk.internal.ref=ALL-UNNAMED --add-opens java.base/jdk.internal.reflect=ALL-UNNAMED --add-opens java.base/jdk.internal.math=ALL-UNNAMED --add-opens java.base/jdk.internal.module=ALL-UNNAMED --add-opens java.base/jdk.internal.util.jar=ALL-UNNAMED --add-opens jdk.management/com.sun.management.internal=ALL-UNNAMED"
run1() { local mode=$1 l=$2 s=$3; local tag=$mode-L$l-S$s
  timeout 120 java $JOPTS -cp "$CL:$CP" org.apache.cassandra.utils.memory.OffheapCapProbe $mode $l $s > "$L/$tag.out" 2>&1; local rc=$?
  say "$tag exit=$rc checks=$(grep -c '^STAGE4 check' "$L/$tag.out") ok=$(grep -c '^STAGE4 check.* ok ' "$L/$tag.out") MISMATCH=$(grep -c '^STAGE4 check.* MISMATCH ' "$L/$tag.out") done=$(grep -c '^STAGE4 done' "$L/$tag.out")"
  grep ' MISMATCH ' "$L/$tag.out" | tee -a "$S"; }
if [ "$MODE" = instrument ]; then
  run1 fill 1 1024
  o=$L/fill-L1-S1024.out
  # hand-computed: n=1024, used=1048576, regions 8K..512K (7 regions, 1016 allocations) then one 1 MiB region (8 allocations): capacity 2088960, 8 regions (7 regions 8K..512K then 1 MiB)
  grep -q 'reading capacity_sum=2088960$' $o && grep -q 'reading regions=8$' $o && grep -q 'reading used=1048576$' $o && say "EXPECTED instrument known answer: ok" || say "EXPECTED instrument known answer: MISMATCH"
  exit 0
fi
# first-trigger check: the plateau must be reached in the first run, else stop
run1 fill 64 1024
grep -q '^STAGE4 check fill-reached-limit ok' "$L/fill-L64-S1024.out" || { say "first-trigger check failed: stop"; exit 1; }
for l in 32 64 128; do for s in 100 1024 102400 131072 131073 1048576; do [ $l = 64 -a $s = 1024 ] && continue; run1 fill $l $s; done; done
for s in 1024 131073; do run1 blocking 64 $s; run1 control 64 $s; run1 fill 1 $s; done
run1 control 32 100; run1 control 128 1048576
say "EXPECTED all runs finished with done=1 and MISMATCH=0 (B2f as amended)"
tot=$(grep -h '^STAGE4 check' "$L"/*.out | wc -l); mm=$(grep -h '^STAGE4 check.* MISMATCH ' "$L"/*.out | wc -l)
say "unit-run end $(date -Is) total checks $tot MISMATCH $mm"
