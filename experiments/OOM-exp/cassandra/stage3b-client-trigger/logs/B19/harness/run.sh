#!/usr/bin/env bash
# B19 3-b confirm (ms0625, 2026-11-23): one node lifetime of the stage-2 T2 arm with authentication + authorization on.
#   run.sh <name> [L=2040109465]
# Fresh node dir (empty data: T2 needs no schema or data) -> start (2,048 MiB heap, direct auto, DUMP=1, shipped OOM
# handling) -> superuser creates the tenant role, vic.kv and its grants (B19Admin) -> tenant writes 1,000 keys ->
# auth claim checks (B19AuthClient authcheck) -> samplers -> tenant open loop 20 w/s + 20 r/s -> 60 s baseline ->
# ATTACK: B19AuthClient flood "bogus L" WITHOUT credentials (STARTUP lz4 -> AUTHENTICATE left unanswered -> one 22-byte
# frame) -> wait for JVM death (<= 60 s) -> 30 s more tenant observation -> stop everything -> dump scan -> delete dump.
set -uo pipefail
NAME=$1; L=${2:-2040109465}
ROOT=/mydata/s4/3b-B19; H=$ROOT/h; NODE=$ROOT/node; R=$ROOT/runs/$NAME; SUM=$ROOT/runs/summary.txt
TPASS=ten-3b-B19
export XMX=2048M DUMP=1 VEXTRA= BUILD=$ROOT/tree
J=$BUILD/build/lib/jars
DCP="$ROOT/cls:$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$J/slf4j-api-2.0.17.jar:$BUILD/lib/failureaccess-1.0.1.jar"
RAW="$BUILD/lib/lz4-java-1.10.1.jar:$ROOT/cls"
ms(){ date +%s%3N; }
note(){ echo "$(ms) $(TZ=America/New_York date '+%T') $*" | tee -a "$R/steps.txt"; }
mkdir -p "$ROOT/runs"; rm -rf "$R"; mkdir -p "$R"
pre_fail(){ echo "$NAME: PREFLIGHT FAIL $1" | tee -a "$SUM"; exit 1; }
pgrep -f CassandraDaemon >/dev/null && pre_fail "another CassandraDaemon running"
free_kb=$(df -k --output=avail /mydata | tail -1); [ "$free_kb" -ge $((8*1024*1024)) ] || pre_fail "/mydata free ${free_kb}KB < 8GiB"
mav=$(awk '/^MemAvailable:/{print $2}' /proc/meminfo); [ "$mav" -ge $((30*1024*1024)) ] || pre_fail "MemAvailable ${mav}KB < 30GiB"
note "preflight ok name=$NAME L=$L free_kb=$free_kb memavail_kb=$mav loadavg=$(cut -d' ' -f1-3 /proc/loadavg)"
md5sum "$BUILD/build/apache-cassandra-5.0.9-SNAPSHOT.jar" >> "$R/steps.txt"
"$H/ctl.sh" gen > "$R/ctl.log" 2>&1 || { echo "$NAME: GEN FAIL" | tee -a "$SUM"; exit 1; }
"$H/ctl.sh" start >> "$R/ctl.log" 2>&1
up=0; for _ in $(seq 90); do grep -q "Starting listening for CQL clients" $NODE/logs/system.log 2>/dev/null && { up=1; break; }; sleep 2; done
VPID=$("$H/ctl.sh" pid); CG=$("$H/ctl.sh" cg)
if [ $up != 1 ] || [ -z "$VPID" ]; then echo "$NAME: START FAIL" | tee -a "$SUM"; "$H/ctl.sh" stop >> "$R/ctl.log" 2>&1; exit 1; fi
note "listening vpid=$VPID cg=$CG"
cp $NODE/yaml.diff "$R/V-yaml.diff"; tr '\0' '\n' < /proc/$VPID/cmdline > "$R/V-cmdline.txt"
taskset -c 6-7 jcmd $VPID VM.flags 2>/dev/null | tr ' ' '\n' | grep -E "MaxDirectMemorySize|MaxHeapSize|UseG1GC|G1HeapRegionSize" > "$R/V-flags.txt"
echo "memory.max=$(cat $CG/memory.max) swap.max=$(cat $CG/memory.swap.max)" >> "$R/V-flags.txt"
# --- superuser: roles, admin schema, grants only ---
taskset -c 6-7 java -Xmx256m -Duser=cassandra -Dpass=cassandra -cp "$DCP" B19Admin 127.0.0.19 "$TPASS" > "$R/admin.txt" 2>&1
note "admin setup rc=$? $(grep -c 'ADMIN ok' "$R/admin.txt") statements"
grep -q "ADMIN ok: GRANT MODIFY" "$R/admin.txt" || { note "ADMIN SETUP FAILED: abort"; "$H/ctl.sh" stop >> "$R/ctl.log" 2>&1; echo "$NAME: SETUP FAIL" >> "$SUM"; exit 1; }
taskset -c 6-7 java -Xmx256m -Duser=tenant -Dpass=$TPASS -cp "$DCP" B19Victim setup 127.0.0.19 1000 > "$R/victim-setup.txt" 2>&1
note "tenant setup: $(grep 'victim setup' "$R/victim-setup.txt")"
# --- claim checks: authentication enforced; LZ4 pre-auth path ---
taskset -c 6-7 java -Xmx256m -Duser=tenant -Dpass=$TPASS -cp "$RAW" B19AuthClient authcheck > "$R/authcheck.txt" 2>&1
note "authcheck done"; kill -0 $VPID 2>/dev/null || { note "node died during setup"; }
# --- samplers ---
bash "$H/cg.sh" $VPID "$CG" "$R" > /dev/null 2>&1 & CGP=$!
taskset -c 6-7 java -cp "$ROOT/cls" B19Sample 7319 500 "$R" > "$R/sampler.err" 2>&1 & SMP=$!
# --- tenant (victim) open loop in its own scope ---
systemd-run --user --scope --quiet --unit="b3b19-tenant-$(date +%s)" -p MemoryMax=2G -p MemorySwapMax=0 \
  taskset -c 6-7 java -Xmx512m -Duser=tenant -Dpass=$TPASS -cp "$DCP" B19Victim run 127.0.0.19 20 20 "$R/victim.stop" 400 > "$R/victim.out" 2> "$R/victim.err" &
VICP=$!
note "tenant started"; ms > "$R/victim.start"
sleep 60   # tenant baseline
# --- ATTACK: no credentials ---
ms > "$R/attack.start"; note "ATTACK start (no credentials): flood bogus $L"
taskset -c 6-7 java -Xmx256m -cp "$RAW" B19AuthClient flood "bogus $L" > "$R/client.log" 2>&1 &
ATP=$!
dead=""; for _ in $(seq 600); do kill -0 $VPID 2>/dev/null || { dead=$(ms); break; }; sleep 0.1; done
[ -n "$dead" ] && { echo "$dead" > "$R/death.ms"; note "JVM $VPID gone at +$(( dead - $(cat $R/attack.start) )) ms after attack start"; } || note "JVM alive 60 s after attack start"
wait $ATP; ms > "$R/attack.end"; note "attack client exited: $(grep FINAL "$R/client.log")"
sleep 30   # tenant observation after
touch "$R/victim.stop"; wait $VICP 2>/dev/null; note "tenant stopped: $(grep VSUMMARY "$R/victim.out")"
kill $SMP 2>/dev/null; wait $SMP 2>/dev/null
for _ in $(seq 120); do kill -0 $VPID 2>/dev/null || break; ls $NODE/dumps/*.hprof >/dev/null 2>&1 || break; sleep 2; done
if kill -0 $VPID 2>/dev/null; then st=alive; else st=DEAD; fi
mkdir -p "$R/V-logs"; cp -p $NODE/logs/system.log $NODE/logs/debug.log $NODE/logs/gc.log* $NODE/logs/stdout.log $NODE/logs/launch.log $NODE/logs/hs_err* "$R/V-logs/" 2>/dev/null
"$H/ctl.sh" stop > "$R/stop.log" 2>&1
kill $CGP 2>/dev/null; wait $CGP 2>/dev/null
mv $NODE/dumps/*.hprof "$R/" 2>/dev/null && ls -la "$R"/*.hprof | tee "$R/hprof.ls" >> "$R/steps.txt"
banner=$(grep -a -m1 "^java.lang.OutOfMemoryError" "$R/V-logs/stdout.log" 2>/dev/null)
if [ -n "$banner" ] && [ $st = DEAD ]; then cls=OOM; elif [ $st = alive ]; then cls=alive; else cls=other; fi
f=$(ls $R/*.hprof 2>/dev/null | head -1)
if [ -n "$f" ]; then
  taskset -c 6-7 python3 -I "$H/hprofhist.py" "$f" 30 > "$R/hprofhist.txt" 2>&1
  taskset -c 6-7 python3 -I "$H/hprof_oome_thread.py" "$f" 30 > "$R/oome-thread.txt" 2>&1
  rm -f "$R"/*.hprof; note "dump scanned and deleted"
fi
line="$NAME L=$L auth=on | $cls [$banner] | gone_after_attack_start_ms=$([ -n "$dead" ] && echo $(( dead - $(cat $R/attack.start) )) || echo NA) | client: $(grep -E 'HANDSHAKE|FINAL' "$R/client.log" | tr '\n' ' ' | cut -c1-400)"
echo "$line" > "$R/outcome.txt"; echo "$line" >> "$SUM"; echo "$line"
rm -rf $NODE/data $NODE/commitlog $NODE/hints $NODE/saved_caches $NODE/dumps
note "RUN DONE"
