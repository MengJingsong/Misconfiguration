#!/usr/bin/env bash
# Unit tier (B2) of slab-region-size-region-allocate-capacity--autonomous. usage: bash unit-run.sh <run> [instrument]
# Compiles SlabWasteProbe and the two REGION_SIZE variants of SlabAllocator outside the tree (~/s4-b7-sr7-logs/{classes,v512,v2048}), one JVM per scenario.
# Output ~/s4-b7-sr7-logs/<run>/unit/{<scenario>.out,summary.txt}. "instrument" runs only hand-computed known answers (not readings).
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/s4-b7-sr7}; LG=$HOME/s4-b7-sr7-logs
RUN=${1:?run name}; MODE=${2:-full}; L=$LG/$RUN/unit; mkdir -p "$L"; S=$L/summary.txt; : > "$S"
CL=$LG/classes; mkdir -p "$CL"
say() { echo "$*" | tee -a "$S"; }
CP="$C/build/classes/main:$C/build/classes/thrift:$C/build/lib/jars/*:$C/conf"
SRC=$C/src/java/org/apache/cassandra/utils/memory/SlabAllocator.java
javac -nowarn -d "$CL" -cp "$CP" "$H/SlabWasteProbe.java" > "$L/javac.log" 2>&1 || { say "javac failed"; head -20 "$L/javac.log"; exit 1; }
# REGION_SIZE variants: the one-line edit of line 51, compiled alone into its own directory (same class a rebuild would produce)
mkvariant() { local name=$1 expr=$2 d=$LG/variants/$1; rm -rf "$d" "$LG/$name"; mkdir -p "$d" "$LG/$name"; cp "$SRC" "$d/SlabAllocator.java"
  sed -i "51s|REGION_SIZE = 1024 \* 1024;|REGION_SIZE = $expr;|" "$d/SlabAllocator.java"
  diff "$SRC" "$d/SlabAllocator.java" > "$LG/$name.diff"; say "variant $name: $(grep '^>' "$LG/$name.diff")"
  [ "$(grep -c '^>' "$LG/$name.diff")" = 1 ] || { say "variant $name: edit failed"; exit 1; }
  javac -nowarn -d "$LG/$name" -cp "$CP" "$d/SlabAllocator.java" > "$L/javac-$name.log" 2>&1 || { say "javac $name failed"; head "$L/javac-$name.log"; exit 1; }; }
mkvariant v512 "512 * 1024"; mkvariant v2048 "2 * 1024 * 1024"
say "unit-run $RUN $MODE $(date -Is) host $(hostname -s) tree $C $(git -C $C describe --tags) java $(java -version 2>&1 | head -1)"
say "harness md5 $(md5sum "$H/SlabWasteProbe.java" | cut -c1-32)"
JOPTS="-Xmx1g -XX:MaxDirectMemorySize=1g -Dcassandra.config=file://$C/conf/cassandra.yaml -Dcassandra.storagedir=$LG/$RUN/storage --add-exports java.base/jdk.internal.misc=ALL-UNNAMED --add-exports java.base/jdk.internal.ref=ALL-UNNAMED --add-opens java.base/jdk.internal.ref=ALL-UNNAMED --add-exports java.base/sun.nio.ch=ALL-UNNAMED --add-exports java.management.rmi/com.sun.jmx.remote.internal.rmi=ALL-UNNAMED --add-exports java.rmi/sun.rmi.registry=ALL-UNNAMED --add-exports java.rmi/sun.rmi.server=ALL-UNNAMED --add-exports java.sql/java.sql=ALL-UNNAMED --add-opens java.base/java.lang.module=ALL-UNNAMED --add-opens java.base/jdk.internal.loader=ALL-UNNAMED --add-opens java.base/jdk.internal.reflect=ALL-UNNAMED --add-opens java.base/jdk.internal.math=ALL-UNNAMED --add-opens java.base/jdk.internal.module=ALL-UNNAMED --add-opens java.base/jdk.internal.util.jar=ALL-UNNAMED --add-opens jdk.management/com.sun.management.internal=ALL-UNNAMED"
# run1 <variant: stock|v512|v2048> <args...>   tag = variant-args
run1() { local v=$1; shift; local tag=$v-$(echo "$*" | tr ' ' '_'); local vc=""; [ "$v" = stock ] || vc="$LG/$v:"
  timeout 180 java $JOPTS -cp "$vc$CL:$CP" org.apache.cassandra.utils.memory.SlabWasteProbe "$@" > "$L/$tag.out" 2>&1; local rc=$?
  say "$tag exit=$rc checks=$(grep -c '^STAGE4 check' "$L/$tag.out") ok=$(grep -c '^STAGE4 check.* ok ' "$L/$tag.out") MISMATCH=$(grep -c '^STAGE4 check.* MISMATCH ' "$L/$tag.out") done=$(grep -c '^STAGE4 done' "$L/$tag.out")"
  grep ' MISMATCH ' "$L/$tag.out" | tee -a "$S"; }
if [ "$MODE" = instrument ]; then
  # hand-computed: S=1024, N=1024 -> 1 region exactly full (1024 x 1024 = 1 MiB, last newOffset+size == capacity is allowed): owns 1048576, real 1048576
  run1 stock waste offheap 1024 1024; o=$L/stock-waste_offheap_1024_1024.out
  grep -q 'reading regionCount=1$' $o && grep -q 'reading owns=1048576$' $o && grep -q 'reading direct_delta=1048576$' $o && say "EXPECTED instrument known answer 1 (1024 x 1 KiB: 1 region, 1 MiB): ok" || say "EXPECTED instrument known answer 1: MISMATCH"
  # hand-computed: L=4 MiB, S=116509: floor(4194304/116509)=35 (36 x 116509 = 4194324 > L); 35 allocations = 4 full regions of 8 + 3 -> 5 regions = 5 MiB
  run1 stock limit offheap 4 116509 100; o=$L/stock-limit_offheap_4_116509_100.out
  grep -q 'reading allocations_done=35$' $o && grep -q 'reading regionCount=5$' $o && grep -q 'reading real=5242880$' $o && grep -q 'reading owns=4077815$' $o && say "EXPECTED instrument known answer 2 (L 4 MiB, S 116509: 35 allocations, 5 regions): ok" || say "EXPECTED instrument known answer 2: MISMATCH"
  # variant geometry: v512 reports 524288, v2048 reports 2097152
  run1 v512 waste offheap 1024 1024; grep -q 'reading REGION_SIZE=524288$' $L/v512-waste_offheap_1024_1024.out && say "EXPECTED instrument v512 REGION_SIZE 524288: ok" || say "EXPECTED instrument v512: MISMATCH"
  run1 v2048 waste offheap 1024 1024; grep -q 'reading REGION_SIZE=2097152$' $L/v2048-waste_offheap_1024_1024.out && say "EXPECTED instrument v2048 REGION_SIZE 2097152: ok" || say "EXPECTED instrument v2048: MISMATCH"
  exit 0
fi
# first-trigger check: S=116509, N=400 on the stock build must give 50 regions, else stop
run1 stock waste offheap 116509 400
grep -q 'reading regionCount=50$' "$L/stock-waste_offheap_116509_400.out" || { say "first-trigger check failed (regionCount != 50): stop"; exit 1; }
for s in 131072 100000 4096 131073; do run1 stock waste offheap $s 400; done
for v in v512 v2048; do for s in 116509 100000; do run1 $v waste offheap $s 400; done; done
run1 stock waste heap 116509 400
run1 stock limit offheap 64 116509 1400
run1 stock limit offheap 128 116509 1400
run1 stock limit offheap 64 131072 700
run1 stock limit heap 64 116509 1400
for v in v512 v2048; do run1 $v limit offheap 64 116509 1400; done
run1 stock threads 116509 20
say "EXPECTED all runs finished with done=1 and MISMATCH=0 (B2f as amended)"
tot=$(grep -h '^STAGE4 check' "$L"/*.out | wc -l); mm=$(grep -h '^STAGE4 check.* MISMATCH ' "$L"/*.out | wc -l)
say "unit-run end $(date -Is) total checks $tot MISMATCH $mm"
