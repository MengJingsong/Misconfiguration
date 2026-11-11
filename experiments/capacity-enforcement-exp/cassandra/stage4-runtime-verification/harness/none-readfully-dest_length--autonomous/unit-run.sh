#!/usr/bin/env bash
# Unit tier (B2, amended 2026-10-29) of none-readfully-dest_length--autonomous (float, line 69).
# usage (on pc41): unit-run.sh [run-name] [shake]    output: ~/stage4-logs/none/readfully/<run>/   CASSANDRA_HOME default ~/s4-none (build-test done)
# One fresh JVM per (N, pass): pass A no agent, pass B Byteman counter at line 72. mode shake = N=1536 only.
set -uo pipefail
STEM=none-readfully-dest_length--autonomous; KIND=float; SHORT=readfully; RULES=raa.btm
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/s4-none}; RUN=${1:-run1}; MODE=${2:-full}
L=$HOME/stage4-logs/none/$SHORT/$RUN; mkdir -p "$L/classes" "$L/tmp"; S=$L/summary.txt; : > "$S"; rm -f "$L/test-A.out" "$L/test-B.out"; : > "$L/test-A.out"; : > "$L/test-B.out"
say() { echo "$*" | tee -a "$S"; }
cd "$C"
say "unit-run $(date -Is) host $(hostname -s) clone $(git describe --tags) java $(java -version 2>&1 | head -1) mode $MODE"
say "harness md5 $(cd "$H" && md5sum RaaProbe.java Count.java $RULES unit-run.sh | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
CP="$C/build/test/classes:$C/build/classes/main:$C/build/lib/jars/*:$C/build/test/lib/jars/*:$C/test/conf"
javac -nowarn -d "$L/classes" -cp "$CP" "$H/Count.java" "$H/RaaProbe.java" > "$L/javac.log" 2>&1 || { say "javac FAILED"; cat "$L/javac.log"; exit 1; }
say "javac ok"
BM=$(ls "$C"/build/lib/jars/byteman-4.*.jar | grep -v submit | grep -v install | grep -v bmunit | head -1)
java -cp "$BM:$L/classes:$CP" org.jboss.byteman.check.TestScript "$H/$RULES" > "$L/testscript.log" 2>&1
say "TestScript: $(grep -c 'Type checked rule' "$L/testscript.log") rules type checked; $(grep -i 'error\|exception' "$L/testscript.log" | head -2)"
cp "$C/test/conf/cassandra.yaml" "$L/cassandra.yaml"
OPENS="--add-exports java.base/jdk.internal.misc=ALL-UNNAMED --add-exports java.base/jdk.internal.ref=ALL-UNNAMED --add-exports java.base/sun.nio.ch=ALL-UNNAMED --add-exports java.management.rmi/com.sun.jmx.remote.internal.rmi=ALL-UNNAMED --add-exports java.rmi/sun.rmi.registry=ALL-UNNAMED --add-exports java.rmi/sun.rmi.server=ALL-UNNAMED --add-exports java.rmi/sun.rmi.transport.tcp=ALL-UNNAMED --add-exports java.sql/java.sql=ALL-UNNAMED --add-opens java.base/java.lang.module=ALL-UNNAMED --add-opens java.base/java.net=ALL-UNNAMED --add-opens java.base/jdk.internal.loader=ALL-UNNAMED --add-opens java.base/jdk.internal.ref=ALL-UNNAMED --add-opens java.base/jdk.internal.reflect=ALL-UNNAMED --add-opens java.base/jdk.internal.math=ALL-UNNAMED --add-opens java.base/jdk.internal.module=ALL-UNNAMED --add-opens java.base/jdk.internal.util.jar=ALL-UNNAMED --add-opens jdk.management/com.sun.management.internal=ALL-UNNAMED --add-opens java.base/java.nio=ALL-UNNAMED --add-opens java.base/java.lang=ALL-UNNAMED"
if [ "$MODE" = shake ]; then NS="1536"; else NS="32 128 1536 16384 131072 1048576"; fi
for n in $NS; do
  for pass in A B; do
    AG=""; FLAG=0
    if [ $pass = B ]; then AG="-javaagent:$BM=script:$H/$RULES"; FLAG=1; fi
    OUT=$L/test-$pass.out
    timeout 900 java -Xmx512m -ea $AG -Dcassandra.config=file://$L/cassandra.yaml -Dcassandra.storagedir=$L/tmp/storage -Dstage4.out="$OUT" -Dstage4.tmp="$L/tmp" \
        $OPENS -cp "$L/classes:$CP" org.apache.cassandra.index.sai.disk.v1.vector.RaaProbe ${KIND}-${n}-$pass $KIND $n $FLAG > "$L/jvm-$KIND-$n-$pass.log" 2>&1 < /dev/null
    say "N=$n pass=$pass rc=$? $(grep -h 'STAGE4 summary' "$OUT" | tail -1 | sed 's/STAGE4 summary //')"
  done
done
say "checks: MISMATCH lines: $(cat "$L/test-A.out" "$L/test-B.out" | grep -c 'MISMATCH$')"
say "left over java: $(ps -eo pid,args | grep '[R]aaProbe' | wc -l)"
say "done $(date -Is)"
