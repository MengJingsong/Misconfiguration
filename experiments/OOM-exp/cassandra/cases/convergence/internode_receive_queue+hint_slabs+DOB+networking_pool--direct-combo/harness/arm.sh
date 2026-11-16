#!/usr/bin/env bash
# One S1 arm from a clean 11-instance ring (derived from C1 run-4 arm.sh; condition D = shipped yaml).
#   arm.sh <name> <N> <rate/s> <directMiB> [W seconds, default 90]
# env: BLOB (bytes per c1 mutation, default 1 MiB), KEYS (key modulus, 2000), INFL (in-flight per coordinator, 256),
#      LAYER=1 (stage-2 layers: Dn stopped; client -> V on s1h 1 MiB at LRATE/s [100]; nodetool flush @+20 s, compact c1 @+40 s),
#      HEAPDUMP=1 (victim -XX:+HeapDumpOnOutOfMemoryError), VEXTRA (victim-only yaml)
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd)
NAME=$1 N=$2 RATE=$3 DIRECT=$4 W=${5:-90}
INFL=${INFL:-256} BLOB=${BLOB:-1048576} KEYS=${KEYS:-2000} LAYER=${LAYER:-0} LRATE=${LRATE:-100}
export DEFAULTS=1 HEAPDUMP=${HEAPDUMP:-0}
NT=/mydata/b6/cassandra/bin/nodetool
R=/mydata/s1/runs/$NAME; rm -rf "$R"; mkdir -p "$R"
RING=/mydata/s1/ring
foreign(){ echo "$(date +%T) $1 loadavg=$(cut -d' ' -f1-3 /proc/loadavg) foreign_java=[$(pgrep -f java | while read p; do tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null | grep -q '/mydata/s1' || echo -n "$p:$(ps -o comm= -p $p) "; done)] top_foreign=[$(ps -eo pcpu,args --sort=-pcpu | grep -v /mydata/s1 | awk 'NR>1 && $1>50{printf "%s:%s ", $1, substr($2,1,40)}' | head -c 300)]" >> "$R/foreign.txt"; }
foreign start
echo "defaults=1 args: N=$N rate=$RATE direct=${DIRECT}MiB W=$W infl=$INFL blob=$BLOB keys=$KEYS layer=$LAYER lrate=$LRATE heapdump=$HEAPDUMP vextra=[${VEXTRA:-}] heap=2G" > "$R/args.txt"
DIRECT=$DIRECT VEXTRA=${VEXTRA:-} "$H/ring-up.sh" > "$R/ring-up.log" 2>&1
if ! grep -q "schema ok" "$R/ring-up.log"; then echo "$NAME: RING FAIL" | tee -a /mydata/s1/runs/summary.txt; "$H/ctl.sh" stop all >/dev/null; exit 1; fi
VPID=$("$H/ctl.sh" pid V); CG=$("$H/ctl.sh" cg)
echo "vpid=$VPID cg=$CG" >> "$R/args.txt"
cp "$RING/V/yaml.diff" "$R/V-yaml.diff"
"$H/ctl.sh" stop Dn >> "$R/args.txt" 2>&1     # Dn always stopped: same ring state in every arm
for _ in $(seq 30); do $NT -p 7251 status 2>/dev/null | grep -q '^DN  127.0.0.59' && break; sleep 1; done
$NT -p 7251 status > "$R/status-before-load.txt" 2>&1
( echo "epoch_ms,mem_current,anon,oom,oom_kill,hints_dir_kb" > "$R/cg.csv"
  while kill -0 $VPID 2>/dev/null; do
    echo "$(date +%s%3N),$(cat $CG/memory.current 2>/dev/null),$(awk '/^anon /{print $2}' $CG/memory.stat 2>/dev/null),$(awk '/^oom /{print $2}' $CG/memory.events 2>/dev/null),$(awk '/^oom_kill /{print $2}' $CG/memory.events 2>/dev/null),$(du -sk /mydata/s1/shm/V/hints 2>/dev/null | cut -f1)" >> "$R/cg.csv"; sleep 1
  done; cp $CG/memory.events "$R/memory.events.final" 2>/dev/null ) &
CGP=$!
"$H/load.sh" sample 127.0.0.51 7251 1000 "$R" > "$R/sampler.err" 2>&1 & SMP=$!
sleep 5
echo "$(date +%s%3N) load start" >> "$R/args.txt"
LP=""; MP=""
if [ "$LAYER" = 1 ]; then
  JOPTS="-Dks=s1h" "$H/load.sh" run 1048576 256 "$W" "$LRATE" 127.0.0.51 > "$R/layer-load.log" 2>&1 & LP=$!
  ( sleep 20; echo "$(date +%s%3N) flush start" ; timeout 60 $NT -p 7251 flush; echo "$(date +%s%3N) flush end rc=$?"
    sleep 15; echo "$(date +%s%3N) compact start"; timeout 60 $NT -p 7251 compact c1; echo "$(date +%s%3N) compact end rc=$?" ) > "$R/maint.log" 2>&1 & MP=$!
fi
if [ "$N" -gt 0 ]; then
  HOSTS=$(for i in $(seq 1 "$N"); do printf '127.0.0.%d,' $((60+i)); done); HOSTS=${HOSTS%,}
  echo "hosts=$HOSTS" >> "$R/args.txt"
  JOPTS="-Dkeys=$KEYS" "$H/load.sh" run "$BLOB" "$INFL" "$W" "$RATE" "$HOSTS" > "$R/load.log" 2>&1
fi
[ -n "$LP" ] && wait $LP; [ -n "$MP" ] && wait $MP
echo "$(date +%s%3N) load end" >> "$R/args.txt"
foreign mid
sleep 30
kill $SMP 2>/dev/null; wait $SMP 2>/dev/null
if ls $RING/V/dumps/*.hprof >/dev/null 2>&1; then
  for _ in $(seq 100); do kill -0 $VPID 2>/dev/null || break; sleep 3; done
  mv $RING/V/dumps/*.hprof "$R/" 2>/dev/null; ls -la "$R"/*.hprof >> "$R/args.txt"
fi
mkdir -p "$R/V-logs"; cp -p $RING/V/logs/system.log $RING/V/logs/gc.log* $RING/V/logs/launch.log "$R/V-logs/" 2>/dev/null
cp $CG/memory.events "$R/memory.events.final" 2>/dev/null
if kill -0 $VPID 2>/dev/null; then st=alive; else st=DEAD; fi
oomd=$(grep -c "OutOfMemoryError: Direct buffer memory" "$R/V-logs/system.log" 2>/dev/null)
oomh=$(grep -c "OutOfMemoryError: Java heap" "$R/V-logs/system.log" 2>/dev/null)
oomn=$(grep -c "OutOfDirectMemoryError" "$R/V-logs/system.log" 2>/dev/null)
others=""
for c in F C1 C2 C3 C4 C5 C6 C7 C8; do
  k=$(grep -v "JVM Arguments" $RING/$c/logs/system.log 2>/dev/null | grep -c "java.lang.OutOfMemoryError"); [ "${k:-0}" -gt 0 ] && others="$others $c:OOM$k"
  p=$("$H/ctl.sh" pid $c); kill -0 "$p" 2>/dev/null || { others="$others $c:DOWN"; mkdir -p "$R/peer-logs"; tail -60 $RING/$c/logs/system.log > "$R/peer-logs/$c-system-tail.log" 2>/dev/null; tail -20 $RING/$c/logs/launch.log > "$R/peer-logs/$c-launch-tail.log" 2>/dev/null; }
done
grep -v "JVM Arguments" "$R/V-logs/system.log" | grep -n -m1 -B2 -A25 "OutOfMemoryError\|OutOfDirectMemoryError" > "$R/first-oom.txt" 2>/dev/null
peaks=$(python3 "$H/peaks.py" "$R" 2>&1)
hk=$(awk -F, 'NR>1 && $6!=""{if($6>m)m=$6}END{print m+0}' "$R/cg.csv")
foreign end
"$H/ctl.sh" stop all > "$R/stop.log" 2>&1
kill $CGP 2>/dev/null
line="$NAME N=$N rate=$RATE blob=$BLOB direct=$DIRECT layer=$LAYER vextra=[${VEXTRA:-}] | V=$st directOOM=$oomd heapOOM=$oomh nettyOOM=$oomn oom_kill=$(awk '/^oom_kill /{print $2}' "$R/memory.events.final" 2>/dev/null) others=[${others}] | $peaks hints_dir_peak_kB=$hk | client: $(grep FINAL "$R/load.log" 2>/dev/null) | layer: $(grep FINAL "$R/layer-load.log" 2>/dev/null)"
echo "$line" > "$R/outcome.txt"; echo "$line" >> /mydata/s1/runs/summary.txt; echo "$line"
