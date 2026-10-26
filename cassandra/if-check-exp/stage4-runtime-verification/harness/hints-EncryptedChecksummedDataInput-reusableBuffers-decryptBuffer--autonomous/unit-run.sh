#!/usr/bin/env bash
# Unit tier (B2) of hints-EncryptedChecksummedDataInput-reusableBuffers-decryptBuffer--autonomous.
# usage (on pc12): unit-run.sh [run-name] [shake]    output: ~/stage4-logs/ec/<run>/unit/    CASSANDRA_HOME default ~/s4-ec (build-test done)
# One fresh JVM per case (test yaml + max_mutation_size/commitlog_segment_size lines), -Xmx2g.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/s4-ec}; RUN=${1:-run1}; MODE=${2:-full}
L=$HOME/stage4-logs/ec/$RUN/unit; mkdir -p "$L/cases" "$L/classes"; S=$L/summary.txt; : > "$S"; : > "$L/test.out"
say() { echo "$*" | tee -a "$S"; }
cd "$C"
say "unit-run $(date -Is) host $(hostname -s) clone $(git describe --tags) java $(java -version 2>&1 | head -1) mode $MODE"
say "harness md5 $(cd "$H" && md5sum EcProbe.java unit-run.sh | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
CP="$C/build/test/classes:$C/build/classes/main:$C/build/lib/jars/*:$C/build/test/lib/jars/*:$C/test/conf"
javac -nowarn -d "$L/classes" -cp "$CP" "$H/EcProbe.java" > "$L/javac.log" 2>&1 || { say "javac FAILED"; cat "$L/javac.log"; exit 1; }
say "javac ok"
JAMM=$(ls "$C"/build/lib/jars/jamm-*.jar | head -1)
OPENS="--add-exports java.base/jdk.internal.misc=ALL-UNNAMED --add-exports java.base/jdk.internal.ref=ALL-UNNAMED --add-exports java.base/sun.nio.ch=ALL-UNNAMED --add-exports java.management.rmi/com.sun.jmx.remote.internal.rmi=ALL-UNNAMED --add-exports java.rmi/sun.rmi.registry=ALL-UNNAMED --add-exports java.rmi/sun.rmi.server=ALL-UNNAMED --add-exports java.rmi/sun.rmi.transport.tcp=ALL-UNNAMED --add-exports java.sql/java.sql=ALL-UNNAMED --add-opens java.base/java.lang.module=ALL-UNNAMED --add-opens java.base/java.net=ALL-UNNAMED --add-opens java.base/jdk.internal.loader=ALL-UNNAMED --add-opens java.base/jdk.internal.ref=ALL-UNNAMED --add-opens java.base/jdk.internal.reflect=ALL-UNNAMED --add-opens java.base/jdk.internal.math=ALL-UNNAMED --add-opens java.base/jdk.internal.module=ALL-UNNAMED --add-opens java.base/jdk.internal.util.jar=ALL-UNNAMED --add-opens jdk.management/com.sun.management.internal=ALL-UNNAMED --add-opens java.base/java.nio=ALL-UNNAMED --add-opens java.base/java.lang=ALL-UNNAMED"
run_case() {   # label mm(KiB) seg(MiB) args...
  local label=$1 mm=$2 seg=$3; shift 3
  local conf=$L/conf-$mm
  if [ ! -d "$conf" ]; then mkdir -p "$conf"; cp "$C/test/conf/cassandra.yaml" "$conf/cassandra.yaml"
    if [ "$mm" != default ]; then printf '\ncommitlog_segment_size: %sMiB\nmax_mutation_size: %sKiB\n' "$seg" "$mm" >> "$conf/cassandra.yaml"; else printf '\ncommitlog_segment_size: 32MiB\n' >> "$conf/cassandra.yaml"; fi; fi
  rm -rf "$C/build/test/cassandra"
  timeout 900 java -Xmx2g -ea -javaagent:"$JAMM" -Dstorage-config="$C/test/conf" -Dcassandra.config=file://$conf/cassandra.yaml \
      -Dio.netty.tryReflectionSetAccessible=true -Dstage4.out="$L/test.out" $OPENS -cp "$L/classes:$conf:$CP" \
      org.apache.cassandra.hints.EcProbe "$@" > "$L/cases/$label.log" 2>&1 < /dev/null
  local rc=$?
  say "case $label rc=$rc $(grep -h "^STAGE4 summary $label " "$L/test.out" | sed 's/STAGE4 summary [^ ]* //') $(grep -h "^STAGE4 case $label " "$L/test.out" | sed 's/STAGE4 case [^ ]* //')"
}
if [ "$MODE" = shake ]; then
  run_case shake_s2 default 0 read shake_s2 r:1048576:1
  run_case shake_forged default 0 read shake_forged r:1024:1 forged
else
  for r in 1 2 3; do
    run_case s1_$r default 0 read s1_$r r:1024:2000
    run_case s2_$r default 0 read s2_$r r:1048576:1
    run_case s3_$r default 0 read s3_$r r:8388608:1
    run_case s4_$r default 0 read s4_$r r:15728640:1
    run_case s6_$r default 0 read s6_$r z:256000:4
  done
  run_case s3_mm4096 4096 8 read s3_mm4096 r:8388608:1
  run_case s3_mm1024 1024 2 read s3_mm1024 r:8388608:1
  run_case s5 default 0 read s5 r:1024:1 forged
  run_case noshrink default 0 noshrink noshrink r:1024:2000 r:1024:10
  run_case c1 default 0 c1 c1
fi
say "checks: $(grep -c '^STAGE4 check' "$L/test.out") ok: $(grep -c '^STAGE4 check.* ok$' "$L/test.out") MISMATCH: $(grep -c '^STAGE4 check.* MISMATCH$' "$L/test.out") errors: $(grep -c '^STAGE4 error' "$L/test.out")"
grep '^STAGE4 check.* MISMATCH$' "$L/test.out" | tee -a "$S"
say "left over java: $(ps -eo pid,cmd | grep '[E]cProbe' | wc -l)"
say "done $(date -Is)"
