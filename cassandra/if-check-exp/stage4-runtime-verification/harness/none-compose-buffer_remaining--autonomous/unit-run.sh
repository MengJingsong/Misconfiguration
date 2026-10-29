#!/usr/bin/env bash
# Unit tier (B2, amended 2026-10-29) of none-compose-buffer_remaining--autonomous (UDFDataType.java:177).
# usage (on pc41): unit-run.sh [run-name] [shake]    output: ~/stage4-logs/none/readfully/<run>/   CASSANDRA_HOME default ~/s4-none (build-test done)
# One fresh JVM per (pass): pass A no agent, pass B Byteman counter at UDFDataType.java:180. mode shake = same as full.
set -uo pipefail
STEM=none-compose-buffer_remaining--autonomous; KIND=compose; SHORT=compose; RULES=compose.btm
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/s4-none}; RUN=${1:-run1}; MODE=${2:-full}
L=$HOME/stage4-logs/none/$SHORT/$RUN; mkdir -p "$L/classes" "$L/tmp"; S=$L/summary.txt; : > "$S"; rm -f "$L/test-A.out" "$L/test-B.out"; : > "$L/test-A.out"; : > "$L/test-B.out"
say() { echo "$*" | tee -a "$S"; }
cd "$C"
say "unit-run $(date -Is) host $(hostname -s) clone $(git describe --tags) java $(java -version 2>&1 | head -1) mode $MODE"
say "harness md5 $(cd "$H" && md5sum ComposeProbe.java Count.java $RULES unit-run.sh | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
CP="$C/build/test/classes:$C/build/classes/main:$C/build/lib/jars/*:$C/build/test/lib/jars/*:$C/test/conf"
javac -nowarn -d "$L/classes" -cp "$CP" "$H/Count.java" "$H/ComposeProbe.java" > "$L/javac.log" 2>&1 || { say "javac FAILED"; cat "$L/javac.log"; exit 1; }
say "javac ok"
BM=$(ls "$C"/build/lib/jars/byteman-4.*.jar | grep -v submit | grep -v install | grep -v bmunit | head -1)
java -cp "$BM:$L/classes:$CP" org.jboss.byteman.check.TestScript "$H/$RULES" > "$L/testscript.log" 2>&1
say "TestScript: $(grep -c 'Type checked rule' "$L/testscript.log") rules type checked; $(grep -i 'error\|exception' "$L/testscript.log" | head -2)"
cp "$C/test/conf/cassandra.yaml" "$L/cassandra.yaml"
OPENS="--add-exports java.base/jdk.internal.misc=ALL-UNNAMED --add-exports java.base/jdk.internal.ref=ALL-UNNAMED --add-exports java.base/sun.nio.ch=ALL-UNNAMED --add-exports java.management.rmi/com.sun.jmx.remote.internal.rmi=ALL-UNNAMED --add-exports java.rmi/sun.rmi.registry=ALL-UNNAMED --add-exports java.rmi/sun.rmi.server=ALL-UNNAMED --add-exports java.rmi/sun.rmi.transport.tcp=ALL-UNNAMED --add-exports java.sql/java.sql=ALL-UNNAMED --add-opens java.base/java.lang.module=ALL-UNNAMED --add-opens java.base/java.net=ALL-UNNAMED --add-opens java.base/jdk.internal.loader=ALL-UNNAMED --add-opens java.base/jdk.internal.ref=ALL-UNNAMED --add-opens java.base/jdk.internal.reflect=ALL-UNNAMED --add-opens java.base/jdk.internal.math=ALL-UNNAMED --add-opens java.base/jdk.internal.module=ALL-UNNAMED --add-opens java.base/jdk.internal.util.jar=ALL-UNNAMED --add-opens jdk.management/com.sun.management.internal=ALL-UNNAMED --add-opens java.base/java.nio=ALL-UNNAMED --add-opens java.base/java.lang=ALL-UNNAMED"
for n in all; do
  for pass in A B; do
    AG=""; FLAG=0
    if [ $pass = B ]; then AG="-javaagent:$BM=script:$H/$RULES"; FLAG=1; fi
    OUT=$L/test-$pass.out
    timeout 900 java -Xmx1g -ea $AG -Dcassandra.config=file://$L/cassandra.yaml -Dcassandra.storagedir=$L/tmp/storage -Dstage4.out="$OUT" -Dstage4.tmp="$L/tmp" \
        $OPENS -cp "$L/classes:$CP" org.apache.cassandra.cql3.functions.ComposeProbe compose-$pass $FLAG > "$L/jvm-$pass.log" 2>&1 < /dev/null
    say "pass=$pass rc=$? $(grep -h 'STAGE4 summary' "$OUT" | tail -1 | sed 's/STAGE4 summary //')"
  done
done
say "checks: MISMATCH lines: $(cat "$L/test-A.out" "$L/test-B.out" | grep -c 'MISMATCH$')"
say "left over java: $(ps -eo pid,args | grep '[C]omposeProbe' | wc -l)"
say "done $(date -Is)"
