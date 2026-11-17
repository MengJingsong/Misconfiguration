#!/usr/bin/env bash
# One U1 arm from a clean single node (shipped yaml + environment keys).
#   arm.sh <name> <directMiB|auto> <blobBytes> <writers> <inflightPerWriter> <rate/s> [W seconds, default 90]
# env: XMX (2048M), VEXTRA (yaml "k=v ..." control/intervention only), VJVM (extra JVM opts), KEYS (200),
#      JSTACK=1 (jcmd Thread.print every 5 s, MutationStage classification; diagnostic arms only)
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd)
NAME=$1 DIRECT=$2 BLOB=$3 WRITERS=$4 INFL=$5 RATE=$6 W=${7:-90}
KEYS=${KEYS:-200} JSTACK=${JSTACK:-0}; export XMX=${XMX:-2048M} DIRECT VEXTRA=${VEXTRA:-} VJVM=${VJVM:-}
NODE=/mydata/u1/node; R=/mydata/u1/runs/$NAME; rm -rf "$R"; mkdir -p "$R"
foreign(){ echo "$(date +%T) $1 loadavg=$(cut -d' ' -f1-3 /proc/loadavg) foreign_java=[$(pgrep -f java | while read p; do tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null | grep -q '/mydata/u1' || echo -n "$p:$(ps -o comm= -p $p) "; done)] cassandra_daemons=$(pgrep -fc CassandraDaemon)" >> "$R/foreign.txt"; }
foreign start
echo "args: direct=$DIRECT blob=$BLOB writers=$WRITERS infl/writer=$INFL rate=$RATE W=$W keys=$KEYS xmx=$XMX vextra=[$VEXTRA] vjvm=[$VJVM] jstack=$JSTACK" > "$R/args.txt"
if pgrep -f CassandraDaemon >/dev/null; then echo "$NAME: ABORT another CassandraDaemon running" | tee -a /mydata/u1/runs/summary.txt; exit 1; fi
"$H/ctl.sh" gen > "$R/ctl.log" 2>&1 || { echo "$NAME: GEN FAIL" | tee -a /mydata/u1/runs/summary.txt; exit 1; }
"$H/ctl.sh" start >> "$R/ctl.log" 2>&1
up=0; for _ in $(seq 90); do grep -q "Starting listening for CQL clients" $NODE/logs/system.log 2>/dev/null && { up=1; break; }; sleep 2; done
VPID=$("$H/ctl.sh" pid); CG=$("$H/ctl.sh" cg)
if [ $up != 1 ] || [ -z "$VPID" ]; then echo "$NAME: START FAIL" | tee -a /mydata/u1/runs/summary.txt; "$H/ctl.sh" stop; exit 1; fi
"$H/load.sh" schema 127.0.0.71 > "$R/schema.log" 2>&1
echo "vpid=$VPID cg=$CG" >> "$R/args.txt"
cp $NODE/yaml.diff "$R/V-yaml.diff"; tr '\0' '\n' < /proc/$VPID/cmdline > "$R/V-cmdline.txt"
jcmd $VPID VM.flags 2>/dev/null | tr ' ' '\n' | grep -E "MaxDirectMemorySize|MaxHeapSize|UseG1GC" > "$R/V-flags.txt"
grep -E "INFO .*(DatabaseDescriptor|Config)" $NODE/logs/system.log | head -3 > /dev/null
( echo "epoch_ms,mem_current,anon,file,oom,oom_kill" > "$R/cg.csv"
  while kill -0 $VPID 2>/dev/null; do
    echo "$(date +%s%3N),$(cat $CG/memory.current 2>/dev/null),$(awk '/^anon /{print $2}' $CG/memory.stat 2>/dev/null),$(awk '/^file /{print $2}' $CG/memory.stat 2>/dev/null),$(awk '/^oom /{print $2}' $CG/memory.events 2>/dev/null),$(awk '/^oom_kill /{print $2}' $CG/memory.events 2>/dev/null)" >> "$R/cg.csv"; sleep 1
  done; cp $CG/memory.events "$R/memory.events.final" 2>/dev/null ) &
CGP=$!
"$H/load.sh" sample 7271 1000 "$R" > "$R/sampler.err" 2>&1 & SMP=$!
JSP=""
if [ "$JSTACK" = 1 ]; then
  ( echo "epoch_ms,mut,cl_add,expand,serialize,seg_wait,sync_wait,other_in_add,memtable_wait,idle" > "$R/jstack.csv"; i=0
    while kill -0 $VPID 2>/dev/null; do i=$((i+1)); jcmd $VPID Thread.print > "$R/.td" 2>/dev/null && python3 "$H/jstk.py" < "$R/.td" >> "$R/jstack.csv"; [ $((i % 6)) = 3 ] && cp "$R/.td" "$R/threads-$i.txt"; sleep 5; done ) & JSP=$!
fi
sleep 5
echo "$(date +%s%3N) load start" >> "$R/args.txt"
SRC=$(for i in $(seq 1 "$WRITERS"); do printf '127.0.0.%d,' $((100+i)); done); SRC=${SRC%,}
JOPTS="-Dkeys=$KEYS -Dsrcips=$SRC" "$H/load.sh" run "$BLOB" "$INFL" "$W" "$RATE" 127.0.0.71 > "$R/load.log" 2>&1
echo "$(date +%s%3N) load end" >> "$R/args.txt"
foreign mid
sleep 20
kill $SMP 2>/dev/null; wait $SMP 2>/dev/null; [ -n "$JSP" ] && { kill $JSP 2>/dev/null; wait $JSP 2>/dev/null; rm -f "$R/.td"; }
if ls $NODE/dumps/*.hprof >/dev/null 2>&1; then
  for _ in $(seq 100); do kill -0 $VPID 2>/dev/null || break; sleep 3; done
  mv $NODE/dumps/*.hprof "$R/" 2>/dev/null; ls -la "$R"/*.hprof >> "$R/args.txt"
fi
if kill -0 $VPID 2>/dev/null; then st=alive; else st=DEAD; fi
mkdir -p "$R/V-logs"; cp -p $NODE/logs/system.log $NODE/logs/gc.log* $NODE/logs/launch.log $NODE/logs/hs_err* "$R/V-logs/" 2>/dev/null
"$H/ctl.sh" stop > "$R/stop.log" 2>&1
kill $CGP 2>/dev/null; wait $CGP 2>/dev/null
oomd=$(grep -c "OutOfMemoryError: Direct buffer memory" "$R/V-logs/system.log" 2>/dev/null)
oomh=$(grep -c "OutOfMemoryError: Java heap" "$R/V-logs/system.log" 2>/dev/null)
oomn=$(grep -c "OutOfDirectMemoryError" "$R/V-logs/system.log" 2>/dev/null)
grep -v "JVM Arguments" "$R/V-logs/system.log" | grep -n -m1 -B3 -A30 "OutOfMemoryError\|OutOfDirectMemoryError" > "$R/first-oom.txt" 2>/dev/null
peaks=$(python3 "$H/peaks.py" "$R" 2>&1)
mmd=$(grep -o "MaxDirectMemorySize *= *[0-9]*\|MaxDirectMemorySize=[0-9]*" "$R/V-flags.txt" | grep -o "[0-9]*$" | head -1)
foreign end
line="$NAME direct=$DIRECT(resolved $((${mmd:-0}/1048576))MiB) blob=$BLOB writers=$WRITERS infl=$INFL rate=$RATE vextra=[$VEXTRA] vjvm=[$VJVM] | V=$st directOOM=$oomd heapOOM=$oomh nettyOOM=$oomn oom_kill=$(awk '/^oom_kill /{print $2}' "$R/memory.events.final" 2>/dev/null) | $peaks | client: $(grep FINAL "$R/load.log" 2>/dev/null)"
echo "$line" > "$R/outcome.txt"; echo "$line" >> /mydata/u1/runs/summary.txt; echo "$line"
rm -rf $NODE/data $NODE/commitlog $NODE/hints $NODE/saved_caches
