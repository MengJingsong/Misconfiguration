#!/usr/bin/env bash
# 3-b R24 attack lifetime on pc72 (2026-11-24), from stage 2's run-arm.sh: auth on; fresh clone of the LOAD templates (roles, grants,
# attacker-loaded w2k, victim's vks.kv); node 1 (coordinator) 2G / direct auto, node 2 16G; thresholds read back; sampler;
# victim (role victim, V1 node 1 QUORUM, V2 node 2 QUORUM, V3 node 2 ONE, 20 ops/s each) 30 s before the attack;
# attack client as role ATTACKER: w2k QUORUM F = 128, steps 1:20,7:160 (the verified T arm); readings every 10 s until the client ends or
# node 1 dies; after a death 60 s more of victim; stop everything; small evidence to the repo; hprof scanned then deleted.
#   run-arm.sh <label> [steps] [attacker-user] [attacker-pass]
set -uo pipefail
L=$1 STEPS=${2:-"1:20,7:160"} AU=${3:-attacker} AP=${4:-atk-r24-pw}
TBL=w2k CL=QUORUM HEAP=2G DIRECT=auto F=128
ROOT=/mydata/s4/3b-R24; H=$ROOT/harness; R=$ROOT/runs/$L
REPO=/proj/misconfiguration-PG0/git-repos/Misconfiguration/experiments/OOM-exp/cassandra/stage3b-client-trigger/logs/R24
export WT=w2k ST=w2k
V="bash $H/ctl.sh"
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
log "ARM $L table=$TBL CL=$CL heap=$HEAP direct=$DIRECT steps=$STEPS fetch=$F attacker=$AU"
ok=0
for try in 1 2; do
  $V prep "$L" CLONE || exit 1
  if $V start "$L" 1 "$HEAP" "$DIRECT" && $V ready "$L" 1 && $V start "$L" 2 16G auto && $V ready "$L" 2 && $V ring "$L"; then ok=1; break; fi
  log "invalid start (try $try)"; $V stop "$L"; [ -d "$R" ] && mv "$R" "$R.badstart$try"
done
[ $ok = 1 ] || { mkdir -p "$R"; echo "INVALID not-ready" > "$R/outcome"; exit 1; }
echo "arm conf=${CONF:-conf-auth} vopts=${VOPTS:-} table=$TBL CL=$CL steps=$STEPS fetch=$F attacker=$AU jar=$(sha256sum $ROOT/tree/build/apache-cassandra-*.jar | cut -c1-16)" >> "$R/run.meta"
grep -E '^(authenticator|authorizer|role_manager|network_authorizer):' "$R/n1/conf/cassandra.yaml" >> "$R/run.meta"
TABLES=w2k $V rfpk "$L" start > /dev/null
$V sampler "$L"
sleep 5; $V gc "$L"; sleep 3; $V read "$L" base | cut -c1-260
VP=""
if [ -z "${NOVICTIM:-}" ]; then   # NOVICTIM=1: stage 2's T as it ran (no victim client), diagnostic only
( cd "$R" && JOPTS="-Dr24.user=victim -Dr24.pass=vic-r24-pw ${VOPTS:-}" XMX=-Xmx2g CLS=R24Victim setsid nohup bash "$H/client.sh" "$L-v" run 20 900 "$R/victim.stop" > victim.csv 2> victim.err < /dev/null & )
sleep 3; VP=$(pgrep -f "R24Victim run 20 900 $R/victim.stop" | head -1); echo "$VP" > "$R/victim.pid"; log "victim pid $VP"
else echo "novictim=1" >> "$R/run.meta"; log "no victim (NOVICTIM)"; fi
sleep 30
date +%s%3N > "$R/attack.start"
( cd "$R" && JOPTS="-Dr24.user=$AU -Dr24.pass=$AP" setsid nohup bash "$H/client.sh" "$L" run 127.0.0.1 "$TBL" "$CL" "$F" "$STEPS" "$R/queries.csv" > client.csv 2> client.err < /dev/null & )
sleep 3; CP=$(pgrep -f "R24Load run 127.0.0.1 $TBL $CL $F $STEPS" | head -1); echo "$CP" > "$R/client.pid"
log "attack client pid $CP (role $AU)"
t0=$(date +%s); dead=0; histd=0; el=0
while true; do
  sleep 10
  el=$(( $(date +%s) - t0 ))
  if [ "$($V alive "$L" 1)" != ALIVE ]; then log "NODE 1 DEAD at +${el}s"; dead=1; break; fi
  [ "$($V alive "$L" 2)" != ALIVE ] && log "PEER n2 DEAD at +${el}s"
  $V read "$L" "t+$el" | cut -c1-300
  tail -1 "$R/client.csv" | cut -c1-220; grep '^[0-9]' "$R/victim.csv" | tail -3 | cut -c1-200
  if [ $histd = 0 ] && [ $el -ge 60 ]; then $V hist "$L" t60; histd=1; fi
  kill -0 "$CP" 2>/dev/null || break
done
if [ $dead = 1 ]; then log "victim keeps running 60 s after node 1's death"; sleep 60; fi
for i in $(seq 1 30); do kill -0 "$CP" 2>/dev/null || break; sleep 1; done
kill "$CP" 2>/dev/null; sleep 1; kill -9 "$CP" 2>/dev/null
date +%s%3N > "$R/attack.end"
grep SUMMARY "$R/client.csv"; tail -3 "$R/client.err"
if [ $dead = 0 ] && [ "$($V alive "$L" 1)" = ALIVE ]; then
  sleep 30; $V read "$L" end-idle | cut -c1-260; TABLES=w2k $V rfpk "$L" end > /dev/null
  $V gc "$L"; sleep 3; $V read "$L" end-postgc | cut -c1-260
fi
[ "$($V alive "$L" 1)" != ALIVE ] && [ $dead = 0 ] && { dead=1; log "node 1 dead after the load"; }
touch "$R/victim.stop"; [ -n "$VP" ] && for i in $(seq 1 15); do kill -0 "$VP" 2>/dev/null || break; sleep 1; done; kill "$VP" 2>/dev/null; sleep 1; [ -n "$VP" ] && kill -9 "$VP" 2>/dev/null
grep SUMMARY "$R/victim.csv" 2>/dev/null
peer=$($V alive "$L" 2)
$V stop "$L"
N1=$R/n1
oomtype=$(grep -h -o -m1 "java.lang.OutOfMemoryError: [A-Za-z ]*" "$N1/logs/system.log" "$N1/stdout.log" 2>/dev/null | head -1)
if [ $dead = 1 ] && [ -n "$oomtype" ]; then echo "OOM type=\"$oomtype\" at+${el}s peer=$peer" > "$R/outcome"
elif [ $dead = 1 ]; then echo "DEAD-noOOM at+${el}s (scope events: $(cat $R/memory.events.last 2>/dev/null | tr '\n' ' ')) peer=$peer" > "$R/outcome"
else echo "SURVIVED peer=$peer" > "$R/outcome"; fi
cat "$R/outcome"
D=$REPO/$L; mkdir -p "$D"
cp "$R"/{readings.csv,samples.csv,run.meta,outcome,rfpk.txt,ring.txt,attack.start,attack.end} "$D"/ 2>/dev/null
cp "$N1/yaml.diff" "$D/yaml-n1.diff"; cp "$R/n2/yaml.diff" "$D/yaml-n2.diff"; cp "$R/n2/env.diff" "$D/env-n2.diff"
cp "$R/memory.events.last" "$D/memory.events" 2>/dev/null
grep -E '^(t,|[0-9]{13},|SUMMARY)' "$R/client.csv" > "$D/client.csv"
grep -E '^(t,|[0-9]{13},|SUMMARY)' "$R/victim.csv" > "$D/victim.csv"
python3 "$H/qsum.py" "$R/queries.csv" > "$D/queries-summary.txt" 2>&1
tail -20 "$R/client.err" > "$D/client.err.tail" 2>/dev/null; [ -s "$D/client.err.tail" ] || rm -f "$D/client.err.tail"
tail -20 "$R/victim.err" > "$D/victim.err.tail" 2>/dev/null; [ -s "$D/victim.err.tail" ] || rm -f "$D/victim.err.tail"
grep -h -m3 -B2 -A30 'java\.lang\.OutOfMemoryError' "$N1/logs/system.log" "$N1/stdout.log" 2>/dev/null | head -150 > "$D/oom-excerpt.txt"
[ -s "$D/oom-excerpt.txt" ] || rm -f "$D/oom-excerpt.txt"
grep -h 'Replica filtering protection\|Oversized\|overloaded; dropping\|cached over' "$N1/logs/system.log" "$R/n2/logs/system.log" 2>/dev/null | cut -c1-400 | head -20 > "$D/rfp-excerpt.txt"
echo "rfp-warn-lines n1: $(grep -c 'Replica filtering protection has cached over' "$N1/logs/system.log")  dropping-lines n1/n2: $(grep -c 'overloaded; dropping' "$N1/logs/system.log")/$(grep -c 'overloaded; dropping' "$R/n2/logs/system.log")  fail-threshold(ERROR cached over) n1: $(grep 'ERROR' "$N1/logs/system.log" | grep -c 'cached over')" >> "$D/rfp-excerpt.txt"
grep -h -i 'unauthorized\|AuthenticationException\|PermissionsCache\|RolesCache\|system_auth\|AuthCache\|Cannot achieve consistency' "$N1/logs/system.log" "$N1/logs/debug.log" "$R/n2/logs/system.log" 2>/dev/null | cut -c1-400 | head -40 > "$D/auth-excerpt.txt"
echo "auth-related lines n1 system/debug, n2 system: $(grep -ci 'unauthorized\|AuthenticationException\|PermissionsCache\|RolesCache\|AuthCache' "$N1/logs/system.log") / $(grep -ci 'unauthorized\|AuthenticationException\|PermissionsCache\|RolesCache\|AuthCache' "$N1/logs/debug.log") / $(grep -ci 'unauthorized\|AuthenticationException\|PermissionsCache\|RolesCache\|AuthCache' "$R/n2/logs/system.log")" >> "$D/auth-excerpt.txt"
grep -h -m3 -A12 'OutOfMemoryError' "$R/n2/logs/system.log" > "$D/n2-oom.txt" 2>/dev/null; [ -s "$D/n2-oom.txt" ] || rm -f "$D/n2-oom.txt"
[ -f "$R/histo-t60.txt" ] && head -40 "$R/histo-t60.txt" > "$D/histo-t60-top.txt"
python3 "$H/gcwin.py" "$N1/logs" > "$D/gcwin.txt"
python3 "$H/gcpost.py" "$N1/logs" > "$D/gcpost.txt" 2>&1
python3 "$H/steps.py" "$D" > "$D/steps.txt" 2>&1
python3 "$H/victimsum.py" "$D" "$R" > "$D/victim-summary.txt" 2>&1
ls -la "$N1" "$R/n2" | grep -i 'hprof\|hs_err' > "$D/hprof.ls" || rm -f "$D/hprof.ls"
for f in "$N1"/*.hprof; do
  [ -f "$f" ] || continue
  log "scanning $f"; sha256sum "$f" | cut -c1-16 >> "$D/hprof.ls"
  nice -n 10 python3 "$H/hprofhist.py" "$f" 30 > "$D/hprofhist.txt" 2>&1
  nice -n 10 python3 "$H/hprofstacks.py" "$f" > "$R/hprofstacks-all.txt" 2>&1
  grep -B1 -A16 'OutOfMemory\|ReplicaFilteringProtection\|ReadResponse\|DataOutputBuffer\|Auth\|Permission' "$R/hprofstacks-all.txt" | head -250 > "$D/hprofstacks.txt"
  rm -f "$f"; log "deleted $f"
done
log "END $L $(cat "$R/outcome")"
