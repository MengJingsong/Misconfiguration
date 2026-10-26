#!/usr/bin/env bash
# Unit tier (B2) of hints-CompressedChecksummedDataInput-readBuffer-uncompressedSize--autonomous.
# usage (on the run node): unit-run.sh [run-name] [shake]     output: ~/stage4-logs/hu/<run-name, default run1>/unit/
# Compiles ReaderBufferGrowthTest against the local copy's build (CASSANDRA_HOME, default ~/s4-hu; `ant build-test` done),
# then starts one fresh JVM per case (audit R6) with a conf directory whose cassandra.yaml is test/conf/cassandra.yaml plus
# `file_cache_size: <n>MiB`. Cases per file_cache_size n in {1, 16, 512}:
#   LZ4 single block, blob 1 KiB 100 KiB 120 KiB 128 KiB 129 KiB 1 MiB 16 MiB-1 KiB; orders [1 KiB, X] and [X, 1 KiB] for X in
#   100 KiB, 1 MiB; Deflate single block 100 KiB, 1 MiB; the positive control (400 x 64 KiB held). Once (n = 16): the forged
#   header (a 2 KiB block whose Z is rewritten to 512 MiB; audit R4). `shake` runs three cases only (instrument check).
# Nothing in the repository is changed; the harness class is compiled to $L/classes. Every JVM is a foreground child.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/s4-hu}; RUN=${1:-run1}; MODE=${2:-full}
L=$HOME/stage4-logs/hu/$RUN/unit; mkdir -p "$L/cases" "$L/classes"; S=$L/summary.txt; : > "$S"; : > "$L/test.out"
say() { echo "$*" | tee -a "$S"; }
cd "$C"
say "unit-run $(date -Is) host $(hostname -s) clone $(git describe --tags) java $(java -version 2>&1 | head -1) mode $MODE"
say "harness md5 $(cd "$H" && md5sum ReaderBufferGrowthTest.java unit-run.sh | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
CP="$C/build/test/classes:$C/build/classes/main:$C/build/lib/jars/*:$C/build/test/lib/jars/*:$C/test/conf"
javac -nowarn -d "$L/classes" -cp "$CP" "$H/ReaderBufferGrowthTest.java" > "$L/javac.log" 2>&1 || { say "javac FAILED"; cat "$L/javac.log"; exit 1; }
say "javac ok"
JAMM=$(ls "$C"/build/lib/jars/jamm-*.jar | head -1)
OPENS="--add-exports java.base/jdk.internal.misc=ALL-UNNAMED --add-exports java.base/jdk.internal.ref=ALL-UNNAMED --add-exports java.base/sun.nio.ch=ALL-UNNAMED --add-exports java.management.rmi/com.sun.jmx.remote.internal.rmi=ALL-UNNAMED --add-exports java.rmi/sun.rmi.registry=ALL-UNNAMED --add-exports java.rmi/sun.rmi.server=ALL-UNNAMED --add-exports java.rmi/sun.rmi.transport.tcp=ALL-UNNAMED --add-exports java.sql/java.sql=ALL-UNNAMED --add-opens java.base/java.lang.module=ALL-UNNAMED --add-opens java.base/java.net=ALL-UNNAMED --add-opens java.base/jdk.internal.loader=ALL-UNNAMED --add-opens java.base/jdk.internal.ref=ALL-UNNAMED --add-opens java.base/jdk.internal.reflect=ALL-UNNAMED --add-opens java.base/jdk.internal.math=ALL-UNNAMED --add-opens java.base/jdk.internal.module=ALL-UNNAMED --add-opens java.base/jdk.internal.util.jar=ALL-UNNAMED --add-opens jdk.management/com.sun.management.internal=ALL-UNNAMED --add-opens java.base/java.nio=ALL-UNNAMED --add-opens java.base/java.lang=ALL-UNNAMED"

run_case() {   # label mode args...
  local label=$1; shift; local fcs=$1; shift
  local conf=$L/conf-$fcs
  if [ ! -d "$conf" ]; then mkdir -p "$conf"; cp "$C/test/conf/cassandra.yaml" "$conf/cassandra.yaml"; printf '\nfile_cache_size: %sMiB\n' "$fcs" >> "$conf/cassandra.yaml"; fi
  local cpx="$L/classes:$conf:$CP"
  rm -rf "$C/build/test/cassandra"
  timeout 600 java -Xmx2g -XX:MaxDirectMemorySize=1g -ea -javaagent:"$JAMM" -Dstorage-config="$C/test/conf" \
      -Dcassandra.config=file://$conf/cassandra.yaml -Dio.netty.tryReflectionSetAccessible=true -Dstage4.out="$L/test.out" \
      -Dstage4.maxdirect=1g $OPENS -cp "$cpx" org.apache.cassandra.hints.ReaderBufferGrowthTest "$@" > "$L/cases/$label.log" 2>&1 < /dev/null
  local rc=$?
  say "case $label rc=$rc $(grep -h '^STAGE4 summary' "$L/cases/$label.log" | sed 's/STAGE4 summary [^ ]* //')"
}

B1=1024; B100=102400; B120=122880; B128=131072; B129=132096; BM=1048576; B16=16776192
if [ "$MODE" = shake ]; then
  run_case shake_1m 16 read shake_1m LZ4 16 $BM
  run_case shake_ctl 16 control shake_ctl 16
  run_case shake_order 512 read shake_order LZ4 512 $B1,$BM
else
  for n in 1 16 512; do
    for x in 1:$B1 100:$B100 120:$B120 128:$B128 129:$B129 1m:$BM 16m:$B16; do
      run_case "f${n}_lz4_${x%%:*}" $n read "f${n}_lz4_${x%%:*}" LZ4 $n ${x##*:}
    done
    run_case "f${n}_lz4_1k_100" $n read "f${n}_lz4_1k_100" LZ4 $n $B1,$B100
    run_case "f${n}_lz4_100_1k" $n read "f${n}_lz4_100_1k" LZ4 $n $B100,$B1
    run_case "f${n}_lz4_1k_1m" $n read "f${n}_lz4_1k_1m" LZ4 $n $B1,$BM
    run_case "f${n}_lz4_1m_1k" $n read "f${n}_lz4_1m_1k" LZ4 $n $BM,$B1
    run_case "f${n}_deflate_100" $n read "f${n}_deflate_100" Deflate $n $B100
    run_case "f${n}_deflate_1m" $n read "f${n}_deflate_1m" Deflate $n $BM
    run_case "f${n}_control" $n control "f${n}_control" $n
  done
  run_case "f16_forged" 16 read "f16_forged" LZ4 16 2048 536870912
fi
say "checks: $(grep -c '^STAGE4 check' "$L/test.out") ok: $(grep -c '^STAGE4 check.* ok$' "$L/test.out") MISMATCH: $(grep -c '^STAGE4 check.* MISMATCH$' "$L/test.out") errors: $(grep -c '^STAGE4 error' "$L/test.out")"
grep '^STAGE4 check.* MISMATCH$' "$L/test.out" | tee -a "$S"
grep '^STAGE4 case' "$L/test.out" >> "$S"
say "left over java: $(ps -eo pid,cmd | grep '[R]eaderBufferGrowthTest' | wc -l)"
say "done $(date -Is)"
