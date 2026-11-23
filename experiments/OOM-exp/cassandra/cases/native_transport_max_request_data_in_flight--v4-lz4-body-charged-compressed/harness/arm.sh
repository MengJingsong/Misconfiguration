#!/usr/bin/env bash
# One B19 arm from a clean regenerated node (template data restored).
#   arm.sh <name> <kind> <xmx> <dump> [vextra] [build]
# kind: zero | rand | "bogus <L>". Flood E=4 Q=256 for 90 s (bogus: frame(s), then 30 s observation).
# Name prefix C2_ -> bogus frame sent 50 times (fresh connection each, 200 ms apart).
# Name prefix I2_ -> after the observation: flood zero 1 1 5 and an uncompressed probe (useful work check).
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd)
NAME=$1 KIND=$2 XMX=$3 DUMP=$4 VEXTRA=${5:-} BUILD=${6:-/mydata/s4/cassandra-base}
ROOT=/mydata/s4/B19; NODE=$ROOT/node; R=$ROOT/runs/$NAME; SUM=$ROOT/runs/summary.txt
WIN=${WIN:-90}
export XMX DUMP VEXTRA BUILD
mkdir -p "$ROOT/runs"; rm -rf "$R"; mkdir -p "$R"
pre_fail(){ echo "$NAME: PREFLIGHT FAIL $1" | tee -a "$SUM"; touch "$ROOT/STOP"; exit 1; }
pgrep -f CassandraDaemon >/dev/null && pre_fail "another CassandraDaemon running"
free_kb=$(df -k --output=avail /mydata | tail -1); [ "$free_kb" -ge $((8*1024*1024)) ] || pre_fail "/mydata free ${free_kb}KB < 8GiB"
mav=$(awk '/^MemAvailable:/{print $2}' /proc/meminfo); [ "$mav" -ge $((30*1024*1024)) ] || pre_fail "MemAvailable ${mav}KB < 30GiB"
hm=$(TZ=America/New_York date +%H%M); [ "$hm" -lt 1315 ] || pre_fail "time $hm EST >= 13:15"
echo "args: kind=[$KIND] xmx=$XMX dump=$DUMP vextra=[$VEXTRA] build=$BUILD win=$WIN" > "$R/args.txt"
echo "$(date +%s%3N) preflight ok free_kb=$free_kb memavail_kb=$mav loadavg=$(cut -d' ' -f1-3 /proc/loadavg) est=$(TZ=America/New_York date +%T)" >> "$R/args.txt"
"$H/ctl.sh" gen > "$R/ctl.log" 2>&1 || { echo "$NAME: GEN FAIL" | tee -a "$SUM"; exit 1; }
"$H/ctl.sh" start >> "$R/ctl.log" 2>&1
up=0; for _ in $(seq 90); do grep -q "Starting listening for CQL clients" $NODE/logs/system.log 2>/dev/null && { up=1; break; }; sleep 2; done
VPID=$("$H/ctl.sh" pid); CG=$("$H/ctl.sh" cg)
if [ $up != 1 ] || [ -z "$VPID" ]; then echo "$NAME: START FAIL" | tee -a "$SUM"; "$H/ctl.sh" stop >> "$R/ctl.log" 2>&1; exit 1; fi
echo "$(date +%s%3N) listening vpid=$VPID cg=$CG" >> "$R/args.txt"
"$H/cli.sh" probe > "$R/probe.log" 2>&1
cp $NODE/yaml.diff "$R/V-yaml.diff"; tr '\0' '\n' < /proc/$VPID/cmdline > "$R/V-cmdline.txt"
taskset -c 6-7 jcmd $VPID VM.flags 2>/dev/null | tr ' ' '\n' | grep -E "MaxDirectMemorySize|MaxHeapSize|UseG1GC|G1HeapRegionSize" > "$R/V-flags.txt"
bash "$H/cg.sh" $VPID "$CG" "$R" > /dev/null 2>&1 & CGP=$!
taskset -c 6-7 java -cp /mydata/s4/B19/cls B19Sample 7319 500 "$R" > "$R/sampler.err" 2>&1 & SMP=$!
sleep 10   # idle baseline
echo "$(date +%s%3N) flood start" >> "$R/args.txt"
case "$KIND" in
  bogus*)
    JO=""; case "$NAME" in C2_*) JO="-Dreps=50 -Dgapms=200";; esac
    JOPTS="$JO" timeout 1900 "$H/cli.sh" flood "$KIND" > "$R/client.log" 2>&1
    for _ in $(seq 30); do sleep 1; done   # 30 s observation
    if [[ "$NAME" == I2_* ]] && kill -0 $VPID 2>/dev/null; then
      "$H/cli.sh" flood zero 1 1 5 > "$R/post-flood.log" 2>&1
      "$H/cli.sh" probe > "$R/post-probe.log" 2>&1
    fi
    kill -0 $VPID 2>/dev/null && taskset -c 6-7 jcmd $VPID GC.class_histogram > "$R/histo-end.txt" 2>&1
    ;;
  *)
    ( for _ in $(seq 200); do grep -q FLOOD_START "$R/client.log" 2>/dev/null && break; sleep 0.5; done
      sleep 75; kill -0 $VPID 2>/dev/null && taskset -c 6-7 jcmd $VPID GC.class_histogram > "$R/histo-end.txt" 2>&1; echo "$(date +%s%3N)" > "$R/histo-end.ms" ) &
    HP=$!
    timeout $((WIN+120)) "$H/cli.sh" flood "$KIND" 4 256 $WIN > "$R/client.log" 2>&1
    wait $HP 2>/dev/null
    ;;
esac
echo "$(date +%s%3N) flood end" >> "$R/args.txt"
sleep 10   # idle
kill $SMP 2>/dev/null; wait $SMP 2>/dev/null
# wait for a dump in progress (OnOutOfMemoryError kill follows the dump)
for _ in $(seq 120); do kill -0 $VPID 2>/dev/null || break; ls $NODE/dumps/*.hprof >/dev/null 2>&1 || break; sleep 2; done
if kill -0 $VPID 2>/dev/null; then st=alive; else st=DEAD; fi
mkdir -p "$R/V-logs"; cp -p $NODE/logs/system.log $NODE/logs/debug.log $NODE/logs/gc.log* $NODE/logs/stdout.log $NODE/logs/launch.log $NODE/logs/hs_err* "$R/V-logs/" 2>/dev/null
"$H/ctl.sh" stop > "$R/stop.log" 2>&1
kill $CGP 2>/dev/null; wait $CGP 2>/dev/null
mv $NODE/dumps/*.hprof "$R/" 2>/dev/null && ls -la "$R"/*.hprof >> "$R/args.txt"
banner=$(grep -a -m1 "^java.lang.OutOfMemoryError" "$R/V-logs/stdout.log" 2>/dev/null)
if [ -n "$banner" ] && [ $st = DEAD ]; then cls=OOM; elif [ $st = alive ]; then cls=alive; else cls=other; fi
peaks=$(python3 -I "$H/b19peaks.py" "$R" 2>&1 | tail -1)
mmd=$(grep -o "MaxDirectMemorySize=[0-9]*" "$R/V-flags.txt" | grep -o "[0-9]*$" | head -1)
line="$NAME kind=[$KIND] xmx=$XMX direct_resolved=$((${mmd:-0}/1048576))MiB vextra=[$VEXTRA] | $cls [$banner] | $peaks | client: $(grep FINAL "$R/client.log" 2>/dev/null | cut -c1-400)"
echo "$line" > "$R/outcome.txt"; echo "$line" >> "$SUM"; echo "$line"
rm -rf $NODE/data $NODE/commitlog $NODE/hints $NODE/saved_caches $NODE/dumps
