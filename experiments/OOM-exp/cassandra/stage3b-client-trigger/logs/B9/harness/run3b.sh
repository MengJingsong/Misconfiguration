#!/usr/bin/env bash
# B9 3-b confirm: one node lifetime with authentication on (pc75).
#   run3b.sh <name> <directMiB|auto> <atk.py args...>
# fresh node (ctl.sh gen) -> start (heap 4096M, DUMP=0) -> superuser setup (admin.py) -> checks -> samplers ->
# victim 30 s -> attack (no credentials) -> 30 s after the attack ends -> victim stop -> logs -> node stop -> summaries.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd)
NAME=$1 DIRECT=$2; shift 2
ROOT=/mydata/s4/3b-B9; NODE=$ROOT/node; R=$ROOT/runs/$NAME; PW=$(cat $ROOT/victim.pw)
export XMX=4096M DIRECT DUMP=0
mkdir -p "$R"; rm -rf "$R"/*
ms(){ date +%s%3N; }
meta(){ echo "$1 $(ms)" >> "$R/run.meta"; }
echo "name $NAME direct $DIRECT xmx $XMX atk $*" > "$R/run.meta"
pgrep -f CassandraDaemon >/dev/null && { echo "PREFLIGHT: CassandraDaemon running"; exit 1; }
mav=$(awk '/^MemAvailable:/{print $2}' /proc/meminfo); [ "$mav" -ge $((40*1024*1024)) ] || { echo "PREFLIGHT: MemAvailable $mav"; exit 1; }
echo "preflight memavail_kb $mav load $(cut -d' ' -f1-3 /proc/loadavg) mydata_free_kb $(df -k --output=avail /mydata | tail -1)" >> "$R/run.meta"
"$H/ctl.sh" gen > "$R/ctl.log" 2>&1 || { echo GEN FAIL; exit 1; }
"$H/ctl.sh" start >> "$R/ctl.log" 2>&1
up=0; for _ in $(seq 90); do grep -q "Starting listening for CQL clients" $NODE/logs/system.log 2>/dev/null && { up=1; break; }; sleep 2; done
VPID=$("$H/ctl.sh" pid); CG=$("$H/ctl.sh" cg)
[ $up = 1 ] && [ -n "$VPID" ] || { echo START FAIL; "$H/ctl.sh" stop; exit 1; }
meta listening; echo "vpid $VPID cg $CG" >> "$R/run.meta"
cp $NODE/yaml.diff "$R/yaml.diff"; tr '\0' '\n' < /proc/$VPID/cmdline > "$R/cmdline.txt"
jcmd $VPID VM.flags 2>/dev/null | tr ' ' '\n' | grep -E "MaxDirectMemorySize|MaxHeapSize|UseG1GC" > "$R/flags.txt"
cd "$H"
taskset -c 22-23 python3 admin.py setup "$PW" > "$R/admin.txt" 2>&1
taskset -c 22-23 python3 admin.py check "$PW" > "$R/authcheck.txt" 2>&1
grep -E "^(authenticator|authorizer|role_manager|network_authorizer|native_transport_idle_timeout|native_transport_max_frame_size|native_transport_max_concurrent_connections|native_transport_max_request_data_in_flight|native_transport_rate_limiting_enabled|native_transport_allow_older_protocols)" $NODE/conf/cassandra.yaml > "$R/auth-and-transport-settings.txt"
"$H/nmt.sh" $VPID "$CG" "$R" > "$R/nmt.err" 2>&1 & NMP=$!
taskset -c 24-25 java -Xmx256m -cp "$ROOT/cls" B9Sample 7299 500 "$R" > "$R/sampler.err" 2>&1 & SMP=$!
( while kill -0 $VPID 2>/dev/null; do sleep 0.2; done; echo "node_exit $(date +%s%3N)" >> "$R/run.meta" ) & DWP=$!
rm -f "$R/victim.stop"
taskset -c 22-23 python3 victim.py --pw "$PW" --rate 20 --out "$R/victim.log" --stop "$R/victim.stop" > "$R/victim.err" 2>&1 & VIP=$!
meta victim_start; sleep 30
meta attack_start
( ulimit -n 100000; timeout 900 taskset -c 6-21 python3 atk.py "$@" --out "$R" > "$R/attack.log" 2>&1 )
meta attack_end
sleep 30
touch "$R/victim.stop"; wait $VIP; meta victim_end
kill $SMP 2>/dev/null; wait $SMP 2>/dev/null
if kill -0 $VPID 2>/dev/null; then st=alive; else st=DEAD; fi
mkdir -p "$R/V-logs"; cp -p $NODE/logs/system.log $NODE/logs/debug.log $NODE/logs/gc.log* $NODE/logs/launch.log $NODE/logs/hs_err* "$R/V-logs/" 2>/dev/null
cp $CG/memory.events "$R/memory.events.last" 2>/dev/null
"$H/ctl.sh" stop > "$R/stop.log" 2>&1
kill $NMP $DWP 2>/dev/null; pkill -f "nmt.sh $VPID" 2>/dev/null; wait $NMP 2>/dev/null
grep -v "JVM Arguments" "$R/V-logs/system.log" | grep -m1 -B3 -A40 "OutOfMemoryError\|OutOfDirectMemoryError" > "$R/first-oom.txt" 2>/dev/null
echo "node_at_end $st" >> "$R/run.meta"
python3 "$H/vsum.py" "$R" > "$R/victim-summary.txt" 2>&1
python3 "$H/peaks.py" "$R" > "$R/peaks.txt" 2>&1
rm -rf $NODE/data $NODE/commitlog $NODE/hints $NODE/saved_caches $NODE/dumps
echo "== $NAME node=$st"; cat "$R/peaks.txt"; cat "$R/victim-summary.txt"; tail -3 "$R/attack.log"
