#!/usr/bin/env bash
# 3-b confirm U4 attack lifetime (pc91, single node + clients on loopback), auth on. Stage 2's run-arm (T arm) with:
# the attack client as role 'attacker' (SELECT + MODIFY on u4.t only); a victim client (role 'victim', U4Victim on its
# own table vks.kv) that starts 60 s before the attack and runs 60 s past the attack's end (node death or client end).
#   run-arm.sh <label> [steps=1:20,3:160] [heap=2G] [direct=auto] [fetch=5000]
set -uo pipefail
L=$1 STEPS=${2:-1:20,3:160} HEAP=${3:-2G} DIRECT=${4:-auto} FETCH=${5:-5000}
ROOT=/mydata/s4/3b-U4; H=$ROOT/harness; R=$ROOT/runs/$L; D=$ROOT/logs/$L
V="bash $H/node-ctl.sh"; VRATE=${VRATE:-40}
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
log "ARM $L heap=$HEAP direct=$DIRECT fetch=$FETCH steps=$STEPS role=attacker"
ok=0
for try in 1 2; do
  $V start "$L" A "$HEAP" "$DIRECT" || exit 1
  if $V ready "$L"; then ok=1; break; fi
  log "invalid start (try $try)"; $V stop "$L"; [ -d "$R" ] && { rm -rf "$R.badstart$try"; mv "$R" "$R.badstart$try"; }
done
[ $ok = 1 ] || { mkdir -p "$R"; echo "INVALID not-ready" > "$R/outcome"; exit 1; }
echo "attacker role=attacker (SELECT+MODIFY on u4.t) victim role=victim (vks.kv) vrate=$VRATE fetch=$FETCH steps=$STEPS" >> "$R/run.meta"
sleep 5; $V gc "$L"; sleep 3; $V read "$L" base | cut -c1-220
( cd "$R" && U4USER=victim U4PASS=vic-pw setsid nohup bash "$H/client.sh" "$L-victim" U4Victim run "$VRATE" 1200 "$R/victim.stop" > victim.csv 2> victim.err < /dev/null & )
sleep 3; VP=$(pgrep -f "U4Victim run $VRATE 1200 $R/victim.stop" | head -1); echo "$VP" > "$R/victim.pid"; log "victim pid $VP (baseline 60 s)"
sleep 57
log "ATTACK START"; date +%s%3N > "$R/attack.start"
( cd "$R" && U4USER=attacker U4PASS=att-pw setsid nohup bash "$H/client.sh" "$L" U4Load run 127.0.0.1 16 "$STEPS" 16 "$FETCH" > client.csv 2> client.err < /dev/null & )
sleep 3; CP=$(pgrep -f "U4Load run 127.0.0.1 16 $STEPS 16 $FETCH" | head -1); echo "$CP" > "$R/client.pid"
log "client pid $CP"
t0=$(date +%s); dead=0
while true; do
  sleep 10
  el=$(( $(date +%s) - t0 ))
  if [ "$($V alive "$L")" != ALIVE ]; then log "NODE DEAD at +${el}s"; dead=1; break; fi
  $V read "$L" "t+$el" | cut -c1-260
  tail -1 "$R/client.csv" | cut -c1-200; tail -1 "$R/victim.csv" | cut -c1-160
  kill -0 "$CP" 2>/dev/null || break
done
date +%s%3N > "$R/attack.end"
if [ $dead = 0 ]; then for i in $(seq 1 40); do kill -0 "$CP" 2>/dev/null || break; sleep 1; done; date +%s%3N > "$R/attack.end"; fi
log "attack ended (dead=$dead); victim continues 60 s (after)"
sleep 60
kill "$CP" 2>/dev/null; sleep 1; kill -9 "$CP" 2>/dev/null
touch "$R/victim.stop"
for i in $(seq 1 30); do kill -0 "$VP" 2>/dev/null || break; sleep 1; done
kill "$VP" 2>/dev/null; sleep 1; kill -9 "$VP" 2>/dev/null
grep SUMMARY "$R/client.csv" "$R/victim.csv"; tail -3 "$R/client.err"
if [ $dead = 0 ] && [ "$($V alive "$L")" = ALIVE ]; then $V read "$L" end | cut -c1-220; fi
$V oom "$L" > "$R/oom-check.txt" 2>&1; head -30 "$R/oom-check.txt"
$V stop "$L"
oomtype=$(grep -h -o -m1 "java\.lang\.OutOfMemoryError: [A-Za-z ]*" "$R/logs/system.log" "$R/stdout.log" 2>/dev/null | head -1)
if [ $dead = 1 ] && [ -n "$oomtype" ]; then
  ls_t=$(grep -E '^[0-9]{13},[0-9]' "$R/samples.csv" | tail -1 | cut -d, -f1)
  sc=$(awk -F, -v t="$ls_t" '/^[0-9]{13},/ && $1 >= t {print $2; exit}' "$R/client.csv")
  ntr=$(grep -E '^[0-9]{13},[0-9]' "$R/samples.csv" | tail -1 | cut -d, -f5)
  echo "OOM c=$sc ntrActiveLast=$ntr type=\"$oomtype\" at+${el}s" > "$R/outcome"
elif [ $dead = 1 ]; then
  echo "DEAD-noOOM at+${el}s (scope events: $(cat $R/memory.events.last 2>/dev/null | tr '\n' ' '))" > "$R/outcome"
else
  echo "SURVIVED" > "$R/outcome"
fi
cat "$R/outcome"
mkdir -p "$D"
cp "$R"/{readings.csv,samples.csv,run.meta,yaml.diff,outcome,oom-check.txt,attack.start,attack.end} "$D"/ 2>/dev/null
cp "$R/memory.events.last" "$D/memory.events" 2>/dev/null
grep -E '^(t,|[0-9]{13},|SUMMARY)' "$R/client.csv" > "$D/client.csv"
grep -E '^(t,|[0-9]{13},|SUMMARY)' "$R/victim.csv" > "$D/victim.csv"
tail -20 "$R/client.err" > "$D/client.err.tail" 2>/dev/null; [ -s "$D/client.err.tail" ] || rm -f "$D/client.err.tail"
tail -20 "$R/victim.err" > "$D/victim.err.tail" 2>/dev/null; [ -s "$D/victim.err.tail" ] || rm -f "$D/victim.err.tail"
python3 "$H/victimsum.py" "$D" > "$D/victim-summary.txt" 2>&1
grep -h -m3 -B2 -A25 'java\.lang\.OutOfMemoryError' "$R/logs/system.log" "$R/stdout.log" 2>/dev/null | head -120 > "$D/oom-excerpt.txt"
[ -s "$D/oom-excerpt.txt" ] || rm -f "$D/oom-excerpt.txt"
grep -h -i 'slow\|GCInspector' "$R/logs/system.log" 2>/dev/null | tail -8 | cut -c1-300 > "$D/syslog-warn.txt"; [ -s "$D/syslog-warn.txt" ] || rm -f "$D/syslog-warn.txt"
python3 "$H/gcwin.py" "$R" > "$D/gcwin.txt"
python3 "$H/steps.py" "$D" > "$D/steps.txt" 2>&1
# heap dump: histogram buckets + stacks, then delete the dump
f=$(ls "$R"/*.hprof 2>/dev/null | head -1)
if [ -n "$f" ]; then
  ls -la "$f" > "$D/hprof.ls"
  nice -n 19 python3 "$H/hprofhist.py" "$f" 30 > "$D/hprofhist.txt" 2>&1
  nice -n 19 python3 "$H/hprofstacks.py" "$f" > "$R/hprofstacks-all.txt" 2>&1
  grep -B1 -A14 'LocalDataResponse\|DataOutputBuffer\|ResultSetBuilder\|OutOfMemory' "$R/hprofstacks-all.txt" | head -120 > "$D/hprofstacks.txt"
  rm -f "$f"; echo "deleted $f" >> "$D/hprof.ls"
fi
log "END $L $(cat "$R/outcome")"
