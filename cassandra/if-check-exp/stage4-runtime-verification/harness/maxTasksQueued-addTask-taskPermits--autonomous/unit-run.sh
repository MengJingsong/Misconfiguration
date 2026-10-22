#!/usr/bin/env bash
# Unit tier (B2 + audit amendments U1-U4) of maxTasksQueued-addTask-taskPermits--autonomous.
# usage: unit-run.sh [run-name] [quick]      output: ~/stage4-logs/mta/<run>/unit/
# Compiles SepQueueProbe outside the clone (~/stage4-mta/probe), then one fresh JVM (-Xms2g -Xmx2g G1, -Xlog:gc) per
# configuration: sep c{1,8} x P{64,1024} x N{1e4,1e5,1e6,4e6}, tpe controls (c{1,8}, P=1024, N=1e6), base. quick = N<=1e5.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-mta}; RUN=${1:-run1}; QUICK=${2:-}
P=$HOME/stage4-mta/probe; L=$HOME/stage4-logs/mta/$RUN/unit; mkdir -p "$L" "$P/classes"; S=$L/summary.txt; : > "$S"
say() { echo "$*" | tee -a "$S"; }
CP="$C/build/classes/main:$C/build/classes/thrift:$(ls $C/build/lib/jars/*.jar $C/lib/*.jar | tr '\n' ':')"
OPTS="--add-exports java.base/jdk.internal.misc=ALL-UNNAMED --add-exports java.base/jdk.internal.ref=ALL-UNNAMED --add-exports java.base/sun.nio.ch=ALL-UNNAMED --add-opens java.base/jdk.internal.ref=ALL-UNNAMED --add-opens java.base/java.lang.reflect=ALL-UNNAMED -Djdk.attach.allowAttachSelf=true"
say "unit-run $(date -Is) host $(hostname -s) clone $(git -C $C describe --tags) $(git -C $C rev-parse --short HEAD) java $(java -version 2>&1 | head -1) cores $(nproc) load $(cut -d' ' -f1-3 /proc/loadavg)"
say "harness md5 $(cd "$H" && md5sum SepQueueProbe.java unit-run.sh unit-analyze.py | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
javac -d "$P/classes" -cp "$CP" "$H/SepQueueProbe.java" 2>&1 | tee -a "$S"
run1() {  # mode c P N [histo]
  local tag="$1-c$2-P$3-N$4"
  ( ulimit -v unlimited; timeout 900 java -Xms2g -Xmx2g -XX:+UseG1GC -Xlog:gc:file=$L/gc-$tag.log $OPTS \
      -Dcassandra.config=file://$C/conf/cassandra.yaml -Dcassandra.storagedir=$P/sd \
      -cp "$P/classes:$CP" org.apache.cassandra.concurrent.SepQueueProbe "$@" > "$L/out-$tag.txt" 2>&1 )
  local rc=$?
  grep -E '^(PROBE|DRAIN|HISTO)' "$L/out-$tag.txt" | sed "s/^/  /" | tee -a "$S"
  say "  [$tag] exit=$rc"
}
if [ "$QUICK" = oom ]; then   # rerun of the two OOM configurations only (defect H1)
  for c in 1 8; do run1 sep $c 1024 4000000; done
  say "leftover probe JVMs: $(ps -eo args | grep -c "^java .*[S]epQueueProbe")"; python3 "$H/unit-analyze.py" "$L" | tee -a "$S"; say "done $(date -Is)"; exit 0
fi
run1 base 0 0 0
Ns="10000 100000 1000000 4000000"; [ "$QUICK" = quick ] && Ns="10000 100000"
for c in 1 8; do for p in 64 1024; do for n in $Ns; do
  h=""; [ "$n" = 1000000 ] && h=histo
  run1 sep $c $p $n $h
done; done; done
[ "$QUICK" = quick ] || for c in 1 8; do run1 tpe $c 1024 1000000; done
[ "$QUICK" = quick ] && run1 tpe 1 1024 100000
say "leftover probe JVMs: $(ps -eo args | grep -c "^java .*[S]epQueueProbe")"
python3 "$H/unit-analyze.py" "$L" | tee -a "$S"
say "done $(date -Is)"
