#!/usr/bin/env bash
# Unit tier (B2) of max-region-size-region-allocate-capacity--autonomous. usage: bash unit-run.sh <run> [instrument]
# Trees (copy-source.sh copies, one constant edited, built with ant): ~/s4-b7-mr (stock 1 MiB), ~/s4-b7-mr-m256, ~/s4-b7-mr-m4096.
# Compiles RegionCapProbe outside the trees (~/s4-b7-mr-logs/classes-<tree>), one JVM per scenario, cwd = the run's unit dir
# (the Cassandra logger otherwise creates cassandra.logdir_IS_UNDEFINED in the cwd). Output ~/s4-b7-mr-logs/<run>/unit/{<tag>.out,summary.txt}.
# "instrument" runs only the hand-computed known answer (not a reading).
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); LG=$HOME/s4-b7-mr-logs
RUN=${1:?run name}; MODE=${2:-full}; L=$LG/$RUN/unit; mkdir -p "$L"; S=$L/summary.txt; : > "$S"
say() { echo "$*" | tee -a "$S"; }
opts() { local C=$1; echo "-Xmx512m -Dcassandra.config=file://$C/conf/cassandra.yaml -Dcassandra.storagedir=$LG/$RUN/storage --add-exports java.base/jdk.internal.misc=ALL-UNNAMED --add-exports java.base/jdk.internal.ref=ALL-UNNAMED --add-opens java.base/jdk.internal.ref=ALL-UNNAMED --add-exports java.base/sun.nio.ch=ALL-UNNAMED --add-exports java.management.rmi/com.sun.jmx.remote.internal.rmi=ALL-UNNAMED --add-exports java.rmi/sun.rmi.registry=ALL-UNNAMED --add-exports java.rmi/sun.rmi.server=ALL-UNNAMED --add-exports java.sql/java.sql=ALL-UNNAMED --add-opens java.base/java.lang.module=ALL-UNNAMED --add-opens java.base/jdk.internal.loader=ALL-UNNAMED --add-opens java.base/jdk.internal.reflect=ALL-UNNAMED --add-opens java.base/jdk.internal.math=ALL-UNNAMED --add-opens java.base/jdk.internal.module=ALL-UNNAMED --add-opens java.base/jdk.internal.util.jar=ALL-UNNAMED --add-opens jdk.management/com.sun.management.internal=ALL-UNNAMED"; }
declare -A TREE=( [stock]=$HOME/s4-b7-mr [m256]=$HOME/s4-b7-mr-m256 [m4096]=$HOME/s4-b7-mr-m4096 )
cd "$L"
for v in stock m256 m4096; do
  C=${TREE[$v]}; CL=$LG/classes-$v; mkdir -p "$CL"
  CP="$C/build/classes/main:$C/build/classes/thrift:$C/build/lib/jars/*:$C/conf"
  javac -nowarn -d "$CL" -cp "$CP" "$H/RegionCapProbe.java" > "$L/javac-$v.log" 2>&1 || { say "javac failed ($v)"; head -20 "$L/javac-$v.log"; exit 1; }
done
say "unit-run $RUN $MODE $(date -Is) host $(hostname -s) java $(java -version 2>&1 | head -1)"
say "harness md5 $(md5sum "$H/RegionCapProbe.java" | cut -c1-32)"
for v in stock m256 m4096; do say "tree $v ${TREE[$v]} $(git -C ${TREE[$v]} describe --tags) $(grep -o 'MAX_REGION_SIZE = [0-9 *]*' ${TREE[$v]}/src/java/org/apache/cassandra/utils/memory/NativeAllocator.java)"; done
run1() { local v=$1 mode=$2 a1=$3 s=$4; local tag=$mode-$v-$a1-$s; local C=${TREE[$v]} CL=$LG/classes-$v
  local CP="$C/build/classes/main:$C/build/classes/thrift:$C/build/lib/jars/*:$C/conf"
  timeout 180 java $(opts $C) -cp "$CL:$CP" org.apache.cassandra.utils.memory.RegionCapProbe $mode $a1 $s > "$L/$tag.out" 2>&1; local rc=$?
  say "$tag exit=$rc checks=$(grep -c '^STAGE4 check' "$L/$tag.out") ok=$(grep -c '^STAGE4 check.* ok ' "$L/$tag.out") MISMATCH=$(grep -c '^STAGE4 check.* MISMATCH ' "$L/$tag.out") done=$(grep -c '^STAGE4 done' "$L/$tag.out")"
  grep ' MISMATCH ' "$L/$tag.out" | tee -a "$S"; }
if [ "$MODE" = instrument ]; then
  run1 stock fill 1024 1024
  o=$L/fill-stock-1024-1024.out
  # hand-computed: 1024 allocations of 1024 B: regions 8K,16K,...,512K hold 8+16+...+512 = 1016, then 8 in one 1 MiB region: 7 regions of sum 1,040,384 plus 1,048,576 = 2,088,960 in 8 regions, max capacity 1,048,576
  grep -q 'reading capacity_sum=2088960$' $o && grep -q 'reading regions=8$' $o && grep -q 'reading max_capacity=1048576$' $o && grep -q 'reading used=1048576$' $o && say "EXPECTED instrument known answer (2088960 in 8 regions, max 1048576, used 1048576): ok" || say "EXPECTED instrument known answer: MISMATCH"
  exit 0
fi
# first-trigger check: the first run must show the region structure the B2f literal predicts (more than one region), else stop
run1 stock fill 1000 100000
grep -q '^STAGE4 check B2f-literal-capacity-and-regions ok' "$L/fill-stock-1000-100000.out" || { say "first-trigger check failed: stop"; exit 1; }
for v in stock m256 m4096; do
  for c in "2000000 100" "1000 100000" "1000 131072" "1000 131073"; do
    [ "$v $c" = "stock 1000 100000" ] && continue
    run1 $v fill $c
  done
done
run1 stock threads 400000 100
run1 stock limit 16 100000
say "EXPECTED all runs finished with done=1 and MISMATCH=0 (B2f as amended)"
tot=$(grep -h '^STAGE4 check' "$L"/*.out | wc -l); mm=$(grep -h '^STAGE4 check.* MISMATCH ' "$L"/*.out | wc -l)
say "unit-run end $(date -Is) total checks $tot MISMATCH $mm"
