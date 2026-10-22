#!/usr/bin/env bash
# Unit tier (B2, amendments U1-U4) of maximumPoolSize-setMaximumPoolSize-deltaWorkPermits--autonomous.
# usage: bash unit-run.sh [run-name]   output: ~/stage4-logs/mps2/<run>/unit/   (rep1..rep3 = three JVMs, U2)
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-mps2}; RUN=${1:-run1}
L=$HOME/stage4-logs/mps2/$RUN/unit; mkdir -p "$L" "$HOME/stage4-mps2/probe"; S=$L/summary.txt; : > "$S"
say() { echo "$*" | tee -a "$S"; }
cd "$C"
CP="$HOME/stage4-mps2/probe:build/classes/main:build/classes/stress:$(ls build/lib/jars/*.jar lib/*.jar | tr '\n' ':')"
javac -cp "$CP" -d "$HOME/stage4-mps2/probe" "$H/SepCapProbe.java" || { say "javac failed"; exit 1; }
say "unit-run $(date -Is) host $(hostname -s) cpus $(nproc) load $(cut -d' ' -f1-3 /proc/loadavg) clone $(git describe --tags) $(git rev-parse --short HEAD) java $(java -version 2>&1 | head -1)"
say "harness md5 $(cd "$H" && md5sum SepCapProbe.java unit-run.sh unit-analyze.py | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
for rep in rep1 rep2 rep3; do
  t0=$(date +%s)
  java -Xmx2g -Xms2g -Xss256k -XX:+UseG1GC -XX:G1HeapRegionSize=4m -XX:NativeMemoryTracking=summary \
       -Xlog:gc:file="$L/gc-$rep.log" -cp "$CP" SepCapProbe $rep > "$L/$rep.probe" 2> "$L/$rep.err" < /dev/null
  rc=$?
  say "$rep exit=$rc $(( $(date +%s) - t0 )) s; lines PROBE=$(grep -c '^PROBE ' "$L/$rep.probe") CTRL=$(grep -c '^CTRL ' "$L/$rep.probe") RESIZE=$(grep -c '^RESIZE ' "$L/$rep.probe"); stderr lines $(wc -l < "$L/$rep.err")"
done
say "leftover SepCapProbe JVMs: $(ps -eo args | grep -c '[S]epCapProbe')"
python3 "$H/unit-analyze.py" "$L" | tee -a "$S"
say "done $(date -Is)"
