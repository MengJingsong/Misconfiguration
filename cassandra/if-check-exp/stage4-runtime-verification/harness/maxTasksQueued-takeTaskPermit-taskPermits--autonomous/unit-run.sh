#!/usr/bin/env bash
# Unit tier (B2) of maxTasksQueued-takeTaskPermit-taskPermits--autonomous. usage (on the run node): unit-run.sh [run-name] [shakedown]
# Compiles SEPQueueBoundProbe against the clone's build/classes/main and runs it as a plain JVM (-Xms2g -Xmx2g G1,
# B2a; audit amendment R2: not through ant testsome, whose maxmemory="1024m" overrides -Xmx). Series: sep and control for
# P = 0 and 1024, two repetitions (rep1, rep2). Output ~/stage4-logs/mtt/<run>/unit/. Stops any leftover probe JVM at the end.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-mtt}; RUN=${1:-run1}; MODE=${2:-full}
L=$HOME/stage4-logs/mtt/$RUN/unit; mkdir -p "$L/classes" "$L/dumps"; S=$L/summary.txt; : > "$S"
say() { echo "$*" | tee -a "$S"; }
cd "$C"
CP="$C/build/classes/main:$C/build/classes/thrift:$(ls $C/build/lib/jars/*.jar | tr '\n' ':')$C/conf"
say "unit-run $(date -Is) host $(hostname -s) clone $(git describe --tags) $(git rev-parse --short HEAD) $(java -version 2>&1 | head -1)"
say "harness md5 $(cd "$H" && md5sum SEPQueueBoundProbe.java unit-run.sh unit-analyze.py | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
javac -d "$L/classes" -cp "$CP" "$H/SEPQueueBoundProbe.java" > "$L/javac.log" 2>&1 || { say "javac failed"; cat "$L/javac.log"; exit 1; }
EXPORTS=$(grep -E '^--add-(exports|opens)' "$C/conf/jvm11-server.options" | tr '\n' ' ')
JOPTS="-Xms2g -Xmx2g -XX:+UseG1GC -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=$L/dumps $EXPORTS -Dcassandra.config=file://$C/test/conf/cassandra.yaml"
say "jvm options: $JOPTS"
if [ "$MODE" = shakedown ]; then SPECS="sep:0:rep1:20000 control:1024:rep1:20000 sep:1024:rep1:20000"; else
 SPECS="sep:0:rep1 sep:1024:rep1 control:0:rep1 control:1024:rep1 sep:0:rep2 sep:1024:rep2 control:0:rep2 control:1024:rep2"; fi
for spec in $SPECS; do
  IFS=: read kind p rep mx <<< "$spec"
  f=$L/$kind-P$p-$rep.log
  java $JOPTS -cp "$L/classes:$CP" org.apache.cassandra.concurrent.SEPQueueBoundProbe $p $rep $kind $mx > "$f" 2>&1 < /dev/null
  rc=$?
  say "$kind P=$p $rep exit=$rc: $(grep -c '^PROBE ' "$f") probe lines, OOM lines $(grep -c OutOfMemoryError "$f")"
  grep -E '^PROBE |HISTO' "$f" | tee -a "$S"
done
say "leftover probe JVMs: $(ps -eo args | grep -c '[S]EPQueueBoundProbe')"
ls "$L/dumps" | head
python3 "$H/unit-analyze.py" "$L" 2>&1 | tee -a "$S"
say "done $(date -Is)"
