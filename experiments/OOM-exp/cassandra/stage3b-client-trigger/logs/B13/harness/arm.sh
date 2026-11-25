#!/usr/bin/env bash
# One B13 arm from a clean regenerated single node (shipped yaml + environment keys) with the data template restored.
#   arm.sh <name> <base|int> <directMiB|auto> <stall|drain> <C> <R> <window_s> [dump=0] [period=1] [w=1] [burst_after=-1] [burst=0] [xmx=2048M]
# Window: from LOAD_START until the first OOM line + 20 s, or the process death + 5 s, else <window_s>.
# 3-b confirm (ms0611, 2026-11-24): auth on (ctl.sh); stall5.py logs in per the caller's env (B13_USER/B13_PASS, or
# B13_PREAUTH=1; B13_QUERY); the stage-2 probe is replaced by the victim tenant (victim.py, role tenant, own table vic.kv,
# 20 ops/s) from 60 s before the attack until 30 s after the node died (or the window end); superuser reads
# system_views.clients once at +8 s (instrumentation). Only build base (the tree copy).
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd)
NAME=$1 BUILD=$2 DIRECT=$3 MODE=$4 C=$5 RPC=$6 WIN=$7 DUMP=${8:-0} PERIOD=${9:-1} W=${10:-1} BA=${11:--1} BU=${12:-0} XMX=${13:-2048M}
ROOT=/mydata/s4/3b-B13; NODE=$ROOT/node; R=$ROOT/runs/$NAME; SUM=$ROOT/runs/summary.txt
export BUILD XMX DIRECT DUMP CASSANDRA_HOME=$ROOT/tree
mkdir -p "$ROOT/runs"; rm -rf "$R"; mkdir -p "$R"
pre_fail(){ echo "$NAME: PREFLIGHT FAIL $1" | tee -a "$SUM"; touch "$ROOT/STOP"; exit 1; }
pgrep -f CassandraDaemon >/dev/null && pre_fail "another CassandraDaemon running"
free_kb=$(df -k --output=avail /mydata | tail -1); [ "$free_kb" -ge $((10*1024*1024)) ] || pre_fail "/mydata free ${free_kb}KB < 10GiB"
mav=$(awk '/^MemAvailable:/{print $2}' /proc/meminfo); [ "$mav" -ge $((30*1024*1024)) ] || pre_fail "MemAvailable ${mav}KB < 30GiB"
[ -d $ROOT/tmpl/data ] || pre_fail "no template"
echo "auth: user=${B13_USER:-none} preauth=${B13_PREAUTH:-0} query=${B13_QUERY:-stage-2 default}" > "$R/auth-args.txt"
echo "args: build=$BUILD direct=$DIRECT mode=$MODE C=$C R=$RPC total=$((C*RPC)) window=$WIN dump=$DUMP period=$PERIOD w=$W burst_after=$BA burst=$BU xmx=$XMX" > "$R/args.txt"
echo "$(date +%s%3N) preflight ok free_kb=$free_kb memavail_kb=$mav loadavg=$(cut -d' ' -f1-3 /proc/loadavg)" >> "$R/args.txt"
"$H/ctl.sh" gen > "$R/ctl.log" 2>&1 || { echo "$NAME: GEN FAIL" | tee -a "$SUM"; exit 1; }
cp -a $ROOT/tmpl/data/. $NODE/data/
up=0
for attempt in 1 2; do
  "$H/ctl.sh" start >> "$R/ctl.log" 2>&1
  for _ in $(seq 90); do grep -q "Starting listening for CQL clients" $NODE/logs/system.log 2>/dev/null && { up=1; break; }; sleep 2; done
  [ $up = 1 ] && break
  "$H/ctl.sh" stop >> "$R/ctl.log" 2>&1; echo "start attempt $attempt failed" >> "$R/args.txt"
  [ $attempt = 1 ] && { "$H/ctl.sh" gen >> "$R/ctl.log" 2>&1; cp -a $ROOT/tmpl/data/. $NODE/data/; }
done
VPID=$("$H/ctl.sh" pid); CG=$("$H/ctl.sh" cg)
if [ $up != 1 ] || [ -z "$VPID" ]; then echo "$NAME: START FAIL" | tee -a "$SUM"; "$H/ctl.sh" stop; touch "$ROOT/STOP"; exit 1; fi
echo "$(date +%s%3N) listening vpid=$VPID cg=$CG" >> "$R/args.txt"
cp $NODE/yaml.diff "$R/V-yaml.diff"; cp $NODE/build "$R/V-build.txt"; tr '\0' '\n' < /proc/$VPID/cmdline > "$R/V-cmdline.txt"
taskset -c 6-7 jcmd $VPID VM.flags 2>/dev/null | tr ' ' '\n' | grep -E "MaxDirectMemorySize|MaxHeapSize|UseG1GC" > "$R/V-flags.txt"
grep -m1 "Global buffer pool limit" $NODE/logs/system.log > "$R/V-bufferpool.txt"
grep -m1 "Node configuration" $NODE/logs/system.log | grep -o "networking_cache_size=[^;]*;\|file_cache_enabled=[^;]*;\|native_transport_max_threads=[^;]*;" > "$R/V-nodeconf.txt"
STOPF=$R/stop.flag
"$H/nmt.sh" $VPID "$CG" "$R" > "$R/nmt.err" 2>&1 & NMP=$!
"$H/jv.sh" sample 7313 500 "$R" > "$R/sampler.err" 2>&1 & SMP=$!
"$H/ss.sh" $VPID "$R" > /dev/null 2>&1 & SSP=$!
VIC_USER=tenant VIC_PASS=ten-3b-B13 taskset -c 6-7 python3 "$H/victim.py" 127.0.0.131 20 3600 2 > "$R/victim.csv" 2> "$R/victim.err" & PRP=$!
echo "$(date +%s%3N) victim started" >> "$R/args.txt"
sleep 60   # victim before the attack (the last 11 s are the idle baseline)
echo "$(date +%s%3N) attack.start (stall5 launched)" >> "$R/args.txt"
( sleep 8; timeout 20 $ROOT/tree/bin/cqlsh 127.0.0.131 -u cassandra -p cassandra -e "SELECT address, port, username, protocol_version, request_count FROM system_views.clients;" > "$R/clients-view.txt" 2>&1 ) &
taskset -c 6-7 python3 "$H/stall5.py" 127.0.0.131 "$C" "$RPC" "$W" "$PERIOD" "$MODE" "$STOPF" $BA $BU > "$R/load.log" 2> "$R/load.err" & LDP=$!
for _ in $(seq 60); do grep -q LOAD_START "$R/load.log" && break; sleep 0.5; done
LS=$(awk '/^LOAD_START/{print $2}' "$R/load.log"); [ -z "$LS" ] && { echo "no LOAD_START" >> "$R/args.txt"; LS=$(date +%s%3N); }
END=$(( LS + WIN*1000 )); oom=0; dead=0
while [ "$(date +%s%3N)" -lt "$END" ]; do
  if [ $oom = 0 ] && [ "$(cat $NODE/logs/system.log $NODE/logs/launch.log 2>/dev/null | grep -vE "JVM Arguments|CompileCommand" | grep -cE "OutOfMemoryError:|OutOfDirectMemoryError")" -gt 0 ]; then
    oom=1; T=$(date +%s%3N); echo "$T OOM line seen" >> "$R/args.txt"
    taskset -c 6-7 jcmd $VPID GC.class_histogram > "$R/hist-at-oom.txt" 2>&1
    taskset -c 6-7 jcmd $VPID VM.native_memory summary > "$R/nmt-at-oom.txt" 2>&1
    ss -tmnp '( sport = :9042 )' > "$R/ss-at-oom.txt" 2>&1
    N=$(( $(date +%s%3N) + 20000 )); [ $N -lt $END ] && END=$N
  fi
  if [ $dead = 0 ] && ! kill -0 $VPID 2>/dev/null; then
    dead=1; echo "$(date +%s%3N) V process gone" >> "$R/args.txt"; N=$(( $(date +%s%3N) + 5000 )); [ $N -lt $END ] && END=$N
  fi
  sleep 1
done
echo "$(date +%s%3N) window end oom=$oom dead=$dead" >> "$R/args.txt"
[ $dead = 1 ] && sleep 25   # victim view: 30 s after the death
# one last pool/ss snapshot at window end (before the clients close)
ss -tmn '( sport = :9042 )' > "$R/ss-at-end.txt" 2>&1
touch "$STOPF"; sleep 5
kill $LDP $PRP 2>/dev/null; wait $LDP $PRP 2>/dev/null; echo "$(date +%s%3N) victim and attacker stopped" >> "$R/args.txt"
kill $SMP 2>/dev/null; wait $SMP 2>/dev/null
if ls $NODE/dumps/*.hprof >/dev/null 2>&1; then
  for _ in $(seq 100); do kill -0 $VPID 2>/dev/null || break; pgrep -f "jcmd|HeapDump" >/dev/null; sleep 3; done
  mv $NODE/dumps/*.hprof "$R/" 2>/dev/null; ls -la "$R"/*.hprof >> "$R/args.txt"
fi
if kill -0 $VPID 2>/dev/null; then st=alive; else st=DEAD; fi
mkdir -p "$R/V-logs"; cp -p $NODE/logs/system.log $NODE/logs/debug.log $NODE/logs/gc.log* $NODE/logs/launch.log $NODE/logs/hs_err* "$R/V-logs/" 2>/dev/null
"$H/ctl.sh" stop > "$R/stop.log" 2>&1
kill $NMP $SSP 2>/dev/null; pkill -f "nmt.sh $VPID" 2>/dev/null; pkill -f "ss.sh $VPID" 2>/dev/null; wait $NMP $SSP 2>/dev/null
SRC="$R/V-logs/system.log"; [ "$(grep -vE "JVM Arguments|CompileCommand" "$SRC" | grep -cE "OutOfMemoryError:|OutOfDirectMemoryError")" -gt 0 ] || SRC="$R/V-logs/launch.log"
grep -vE "JVM Arguments|CompileCommand" "$SRC" | grep -m1 -B5 -A60 -E "OutOfMemoryError:|OutOfDirectMemoryError" > "$R/first-oom.txt" 2>/dev/null
grep -c "A task raised an exception" "$R/V-logs/system.log" > "$R/task-raised-count.txt" 2>/dev/null
grep -m3 "Maximum memory usage reached" "$R/V-logs/system.log" > "$R/max-usage-lines.txt" 2>/dev/null
peaks=$(python3 "$H/b13peaks.py" "$R" 2>&1 | tail -1)
mmd=$(grep -o "MaxDirectMemorySize=[0-9]*" "$R/V-flags.txt" | grep -o "[0-9]*$" | head -1)
line="$NAME build=$BUILD direct=$DIRECT(resolved $((${mmd:-0}/1048576))MiB) mode=$MODE C=$C R=$RPC | V=$st | $peaks | $(grep -E '^SENT_ALL' "$R/load.log" | head -1)"
echo "$line" > "$R/outcome.txt"; echo "$line" >> "$SUM"; echo "$line"
rm -rf $NODE/data $NODE/commitlog $NODE/hints $NODE/saved_caches $NODE/dumps
