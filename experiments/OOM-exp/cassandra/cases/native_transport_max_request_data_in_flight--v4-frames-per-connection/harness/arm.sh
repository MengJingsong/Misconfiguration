#!/usr/bin/env bash
# One B9 arm from a clean regenerated single node (shipped yaml + environment keys).
#   arm.sh <name> <directMiB|auto> <W> <P> <Q> [window_s=45] [xmx=4096M] [dump=0]
# Burst of W*Q requests of 15 MiB over W*P connections, then sustain at 6/s until window_s after BURST_START.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd)
NAME=$1 DIRECT=$2 W=$3 P=$4 Q=$5 WIN=${6:-45} XMX=${7:-4096M} DUMP=${8:-0}
ROOT=/mydata/s4/b9-w1; NODE=$ROOT/node; R=$ROOT/runs/$NAME; SUM=$ROOT/runs/summary.txt
BLOB=15728640; RATE=6
export XMX DIRECT DUMP
mkdir -p "$ROOT/runs"; rm -rf "$R"; mkdir -p "$R"
pre_fail(){ echo "$NAME: PREFLIGHT FAIL $1" | tee -a "$SUM"; touch "$ROOT/STOP"; exit 1; }
pgrep -f CassandraDaemon >/dev/null && pre_fail "another CassandraDaemon running"
free_kb=$(df -k --output=avail /mydata | tail -1); [ "$free_kb" -ge $((10*1024*1024)) ] || pre_fail "/mydata free ${free_kb}KB < 10GiB"
mav=$(awk '/^MemAvailable:/{print $2}' /proc/meminfo); [ "$mav" -ge $((20*1024*1024)) ] || pre_fail "MemAvailable ${mav}KB < 20GiB"
echo "args: direct=$DIRECT W=$W P=$P Q=$Q conns=$((W*P)) burst=$((W*Q)) window=$WIN xmx=$XMX dump=$DUMP blob=$BLOB rate=$RATE" > "$R/args.txt"
echo "$(date +%s%3N) preflight ok free_kb=$free_kb memavail_kb=$mav loadavg=$(cut -d' ' -f1-3 /proc/loadavg) foreign_java=[$(pgrep -f java | while read p; do tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null | grep -q '/mydata/s4' || echo -n "$p "; done)]" >> "$R/args.txt"
"$H/ctl.sh" gen > "$R/ctl.log" 2>&1 || { echo "$NAME: GEN FAIL" | tee -a "$SUM"; exit 1; }
up=0
for attempt in 1 2; do
  "$H/ctl.sh" start >> "$R/ctl.log" 2>&1
  for _ in $(seq 90); do grep -q "Starting listening for CQL clients" $NODE/logs/system.log 2>/dev/null && { up=1; break; }; sleep 2; done
  [ $up = 1 ] && break
  "$H/ctl.sh" stop >> "$R/ctl.log" 2>&1; echo "start attempt $attempt failed" >> "$R/args.txt"
  [ $attempt = 1 ] && { "$H/ctl.sh" gen >> "$R/ctl.log" 2>&1; }
done
VPID=$("$H/ctl.sh" pid); CG=$("$H/ctl.sh" cg)
if [ $up != 1 ] || [ -z "$VPID" ]; then echo "$NAME: START FAIL" | tee -a "$SUM"; "$H/ctl.sh" stop; touch "$ROOT/STOP"; exit 1; fi
echo "$(date +%s%3N) listening vpid=$VPID cg=$CG" >> "$R/args.txt"
"$H/load.sh" schema 127.0.0.81 > "$R/schema.log" 2>&1
cp $NODE/yaml.diff "$R/V-yaml.diff"; tr '\0' '\n' < /proc/$VPID/cmdline > "$R/V-cmdline.txt"
taskset -c 6-7 jcmd $VPID VM.flags 2>/dev/null | tr ' ' '\n' | grep -E "MaxDirectMemorySize|MaxHeapSize|UseG1GC" > "$R/V-flags.txt"
"$H/nmt.sh" $VPID "$CG" "$R" > "$R/nmt.err" 2>&1 & NMP=$!
"$H/load.sh" sample 7299 500 "$R" > "$R/sampler.err" 2>&1 & SMP=$!
sleep 10   # idle baseline
echo "$(date +%s%3N) load start" >> "$R/args.txt"
SRC=$(for i in $(seq 1 "$W"); do printf '127.0.1.%d,' $i; done); SRC=${SRC%,}
JOPTS="-Dkeys=16 -Dsrcips=$SRC" timeout $((WIN+180)) "$H/load.sh" run $BLOB "$P" "$Q" "$WIN" $RATE 127.0.0.81 > "$R/load.log" 2>&1
echo "$(date +%s%3N) load end" >> "$R/args.txt"
sleep 15   # idle observation
kill $SMP 2>/dev/null; wait $SMP 2>/dev/null
if ls $NODE/dumps/*.hprof >/dev/null 2>&1; then
  for _ in $(seq 100); do kill -0 $VPID 2>/dev/null || break; sleep 3; done
  mv $NODE/dumps/*.hprof "$R/" 2>/dev/null; ls -la "$R"/*.hprof >> "$R/args.txt"
fi
if kill -0 $VPID 2>/dev/null; then st=alive; else st=DEAD; fi
mkdir -p "$R/V-logs"; cp -p $NODE/logs/system.log $NODE/logs/debug.log $NODE/logs/gc.log* $NODE/logs/launch.log $NODE/logs/hs_err* "$R/V-logs/" 2>/dev/null
"$H/ctl.sh" stop > "$R/stop.log" 2>&1
kill $NMP 2>/dev/null; pkill -f "nmt.sh $VPID" 2>/dev/null; wait $NMP 2>/dev/null
grep -v "JVM Arguments" "$R/V-logs/system.log" | grep -m1 -B3 -A40 "OutOfMemoryError\|OutOfDirectMemoryError" > "$R/first-oom.txt" 2>/dev/null
grep -E "^ *[0-9]+: +[0-9]+ +[0-9]+ +(io.netty.buffer.PoolChunk|org.apache.cassandra.transport.Envelope|\[B) " "$R/V-logs/system.log" > "$R/histo.txt" 2>/dev/null
peaks=$(python3 "$H/b9peaks.py" "$R" 2>&1 | tail -1)
mmd=$(grep -o "MaxDirectMemorySize=[0-9]*" "$R/V-flags.txt" | grep -o "[0-9]*$" | head -1)
line="$NAME direct=$DIRECT(resolved $((${mmd:-0}/1048576))MiB) xmx=$XMX W=$W P=$P Q=$Q conns=$((W*P)) | V=$st | $peaks | client: $(grep FINAL "$R/load.log" 2>/dev/null)"
echo "$line" > "$R/outcome.txt"; echo "$line" >> "$SUM"; echo "$line"
rm -rf $NODE/data $NODE/commitlog $NODE/hints $NODE/saved_caches $NODE/dumps
