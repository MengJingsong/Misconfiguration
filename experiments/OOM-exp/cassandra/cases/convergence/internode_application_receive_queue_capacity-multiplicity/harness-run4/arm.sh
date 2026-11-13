#!/usr/bin/env bash
# One C1 run-4 arm from a clean ring.
#   arm.sh <name> <N> <rate/s> <directMiB> <btm-file|none> [W seconds, default 110]
# env: VEXTRA="k=v ..." yaml for the victim only (intervention arms), INFL (in-flight per host, default 256)
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd)
NAME=$1 N=$2 RATE=$3 DIRECT=$4 BTM=$5 W=${6:-110}
INFL=${INFL:-256}
R=/mydata/c1r4/runs/$NAME; rm -rf "$R"; mkdir -p "$R"
RING=/mydata/c1r4/ring
foreign(){ echo "$(date +%T) $1 loadavg=$(cut -d' ' -f1-3 /proc/loadavg) foreign_java=[$(pgrep -f java | while read p; do tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null | grep -q 'c1r4' || echo -n "$p:$(ps -o comm= -p $p) "; done)] top_foreign=[$(ps -eo pcpu,args --sort=-pcpu | grep -v c1r4 | awk 'NR>1 && $1>50{printf "%s:%s ", $1, substr($2,1,40)}' | head -c 300)]" >> "$R/foreign.txt"; }
foreign start
[ "$BTM" = none ] && BTM=""
echo "defaults=${DEFAULTS:-0} args: N=$N rate=$RATE direct=${DIRECT}MiB btm=${BTM:-none} W=$W infl=$INFL vextra=[${VEXTRA:-}] heap=2G" > "$R/args.txt"
DIRECT=$DIRECT BYTEMAN=$BTM VEXTRA=${VEXTRA:-} "$H/ring-up.sh" > "$R/ring-up.log" 2>&1
if ! grep -q "schema ok" "$R/ring-up.log"; then echo "$NAME: RING FAIL" | tee -a /mydata/c1r4/runs/summary.txt; "$H/ctl.sh" stop all >/dev/null; exit 1; fi
VPID=$("$H/ctl.sh" pid V); CG=$("$H/ctl.sh" cg)
echo "vpid=$VPID cg=$CG" >> "$R/args.txt"
cp "$RING/V/yaml.diff" "$R/V-yaml.diff"
# cgroup sampler
( echo "epoch_ms,mem_current,anon,oom,oom_kill" > "$R/cg.csv"
  while kill -0 $VPID 2>/dev/null; do
    echo "$(date +%s%3N),$(cat $CG/memory.current 2>/dev/null),$(awk '/^anon /{print $2}' $CG/memory.stat 2>/dev/null),$(awk '/^oom /{print $2}' $CG/memory.events 2>/dev/null),$(awk '/^oom_kill /{print $2}' $CG/memory.events 2>/dev/null)" >> "$R/cg.csv"; sleep 1
  done; cp $CG/memory.events "$R/memory.events.final" 2>/dev/null ) &
CGP=$!
"$H/load.sh" sample 127.0.0.21 7221 1000 "$R" > "$R/sampler.err" 2>&1 & SMP=$!
sleep 5
HOSTS=$(for i in $(seq 1 "$N"); do printf '127.0.0.%d,' $((30+i)); done); HOSTS=${HOSTS%,}
echo "$(date +%s%3N) load start hosts=$HOSTS" >> "$R/args.txt"
"$H/load.sh" run 1048576 "$INFL" "$W" "$RATE" "$HOSTS" > "$R/load.log" 2>&1
echo "$(date +%s%3N) load end" >> "$R/args.txt"
foreign mid
sleep 30
kill $SMP 2>/dev/null; wait $SMP 2>/dev/null
# amendment 4: if a heap dump is being written, wait for it (<= 300 s), then keep it in the run dir
if ls $RING/V/dumps/*.hprof >/dev/null 2>&1; then
  for _ in $(seq 100); do kill -0 $VPID 2>/dev/null || break; sleep 3; done
  mv $RING/V/dumps/*.hprof "$R/" 2>/dev/null; ls -la "$R"/*.hprof >> "$R/args.txt"
fi
mkdir -p "$R/V-logs"; cp -p $RING/V/logs/system.log $RING/V/logs/gc.log* $RING/V/logs/launch.log "$R/V-logs/" 2>/dev/null
cp $CG/memory.events "$R/memory.events.final" 2>/dev/null
if kill -0 $VPID 2>/dev/null; then st=alive; else st=DEAD; fi
oomd=$(grep -c "OutOfMemoryError: Direct buffer memory" "$R/V-logs/system.log" 2>/dev/null)
oomh=$(grep -c "OutOfMemoryError: Java heap" "$R/V-logs/system.log" 2>/dev/null)
others=""
for c in F C1 C2 C3 C4 C5 C6 C7 C8; do
  k=$(grep -v "JVM Arguments" $RING/$c/logs/system.log 2>/dev/null | grep -c "java.lang.OutOfMemoryError"); [ "${k:-0}" -gt 0 ] && others="$others $c:OOM$k"
  "$H/ctl.sh" pid $c >/dev/null; p=$("$H/ctl.sh" pid $c); kill -0 "$p" 2>/dev/null || others="$others $c:DOWN"
done
grep -v "JVM Arguments" "$R/V-logs/system.log" | grep -n -m1 -B2 -A25 "java.lang.OutOfMemoryError" > "$R/first-oom.txt" 2>/dev/null
peaks=$(python3 "$H/peaks.py" "$R" 2>&1)
foreign end
"$H/ctl.sh" stop all > "$R/stop.log" 2>&1
kill $CGP 2>/dev/null
line="$NAME D=${DEFAULTS:-0} N=$N rate=$RATE direct=$DIRECT btm=$( [ -n "$BTM" ] && basename $BTM || echo none) vextra=[${VEXTRA:-}] | V=$st directOOM=$oomd heapOOM=$oomh oom_kill=$(awk '/^oom_kill /{print $2}' "$R/memory.events.final" 2>/dev/null) others=[${others}] | $peaks | client: $(grep FINAL "$R/load.log")"
echo "$line" > "$R/outcome.txt"; echo "$line" >> /mydata/c1r4/runs/summary.txt; echo "$line"
