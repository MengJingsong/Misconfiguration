#!/usr/bin/env bash
# U10 3-b confirm: one clean lifetime on ms0640 with PasswordAuthenticator + CassandraAuthorizer (node + clients on loopback),
# adapted from the case's run-arm.sh (stage 2).
#   run-arm.sh <label> <steps "c:n:secs,..."> [P=2]
# 1 refuse if a CassandraDaemon runs; fresh clone of the template (made by load-data.sh); start 2048M/1024M; ready
# 2 superuser read-backs only (roles, permissions, system_views.settings); GC + baseline reading, tablestats
# 3 victim role u10victim: 20 ops/s on victimks.kv, 60 s baseline before the attack
# 4 attack client as u10atk: the case's closed loop (16 connections, paging off, agg = SELECT count(v) FROM u10.t WHERE pk = ?
#   AND ck < ?, pk = i mod P); alive check every 2 s, readings every 10 s; one GC.class_histogram at +150 s if alive
# 5 victim 60 s more after node death / client end; outcome (as the case); stop a survivor; dump scan, then delete the dump
set -uo pipefail
L=$1 STEPS=$2 P=${3:-2}; export U10_PARTS=$P
ROOT=/mydata/s4/3b-U10; H=$ROOT/harness; R=$ROOT/runs/$L; O=$ROOT/out/$L
V="bash $H/victim-ctl.sh"; C="bash $H/load.sh $L"
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
log "ARM $L heap=2048M direct=1024M fetch=off kind=agg steps=$STEPS P=$P (auth on)"
ok=0
for try in 1 2; do
  $V start "$L" A 2048M 1024M || exit 1
  if $V ready "$L"; then ok=1; break; fi
  log "invalid start (try $try)"; $V stop "$L"; [ -d "$R" ] && mv "$R" "$R.badstart$try"
done
[ $ok = 1 ] || { echo "INVALID not-ready" > "$R/outcome"; exit 1; }
grep -E '^(authenticator|authorizer|role_manager|network_authorizer)' "$R/conf/cassandra.yaml" | tee "$R/auth-yaml.txt"
$C su su 127.0.0.1 $H/readback-su.cql > "$R/readback-su.out" 2>&1
grep -E '^(>|  FAIL|  row: role|  row: role=)' "$R/readback-su.out" | head -20
grep -E 'row: role=|row: name=(authenticator|authorizer|role_manager|read_thresholds_enabled|local_read_size_fail|page_size_fail|read_request_timeout)' "$R/readback-su.out" | cut -c1-200
sleep 5; $V gc "$L"; sleep 3; $V read "$L" base | cut -c1-220
$V ts "$L" | tee "$R/tablestats-before.txt"
( cd "$R" && setsid nohup bash $H/load.sh "$L-vic" vic victim 127.0.0.1 20 "$R/victim.stop" "$R/victim.csv" > victim.out 2>&1 < /dev/null & )
sleep 3; VP=$(pgrep -f "U10Load victim 127.0.0.1 20 $R/victim.stop" | head -1); echo "$VP" > "$R/victim.pid"; log "victim client pid $VP; 60 s baseline"
sleep 57; tail -2 "$R/victim.csv"
( cd "$R" && setsid nohup bash $H/load.sh "$L" atk run 127.0.0.1 16 "$STEPS" off agg > client.csv 2> client.err < /dev/null & )
t0ms=$(date +%s%3N); echo "$t0ms" > "$R/attack_t0_ms"
sleep 2; CP=$(pgrep -f "U10Load run 127.0.0.1 16 $STEPS off agg" | head -1); echo "$CP" > "$R/client.pid"
log "attack client pid $CP (t0 $t0ms)"
t0=$(date +%s); dead=0; histd=0; el=0; lastread=0; deathms=0
while true; do
  sleep 2
  el=$(( $(date +%s) - t0 ))
  if [ "$($V alive "$L")" != ALIVE ]; then deathms=$(date +%s%3N); log "VICTIM NODE DEAD at +${el}s"; dead=1; break; fi
  if [ $(( el - lastread )) -ge 10 ]; then $V read "$L" "t+$el" | cut -c1-260; tail -1 "$R/client.csv" | cut -c1-200; lastread=$el; fi
  if [ $histd = 0 ] && [ $el -ge 150 ]; then $V hist "$L" t150; histd=1; fi
  kill -0 "$CP" 2>/dev/null || break
  [ $el -ge 900 ] && { log "900 s stop"; break; }
done
echo "$deathms" > "$R/death_ms"
for i in $(seq 1 40); do kill -0 "$CP" 2>/dev/null || break; sleep 1; done
kill "$CP" 2>/dev/null; sleep 1; kill -9 "$CP" 2>/dev/null
grep SUMMARY "$R/client.csv"; tail -3 "$R/client.err"
if [ $dead = 0 ] && [ "$($V alive "$L")" = ALIVE ]; then
  $V ts "$L" | tee "$R/tablestats-after.txt"; sleep 3; $V read "$L" end | cut -c1-220
fi
log "victim client: 60 s more"; sleep 60; touch "$R/victim.stop"
for i in $(seq 1 30); do kill -0 "$VP" 2>/dev/null || break; sleep 1; done; kill -9 "$VP" 2>/dev/null
python3 $H/victimsum.py "$R/victim.csv" "$t0ms" "$deathms" "$R/victim" > /dev/null
log "OOM/GC check"; $V oom "$L" > "$R/oom-check.txt" 2>&1; head -40 "$R/oom-check.txt"
$V stop "$L"
oomtype=$(grep -h -o -m1 "java.lang.OutOfMemoryError: [A-Za-z ]*" "$R/logs/system.log" "$R/stdout.log" 2>/dev/null | head -1)
lastline=$(grep -E '^[0-9]{13},' "$R/client.csv" | tail -1 | cut -d, -f2,3)
if [ $dead = 1 ] && [ -n "$oomtype" ]; then
  ls_t=$(grep -E '^[0-9]{13},[0-9]' "$R/samples.csv" | tail -1 | cut -d, -f1)
  sc=$(awk -F, -v t="$ls_t" '/^[0-9]{13},/ && $1 >= t {print $2 " n=" $3; exit}' "$R/client.csv")
  [ -z "$sc" ] && sc="$(echo $lastline | sed 's/,/ n=/')"
  echo "OOM c=$sc type=\"$oomtype\" at+${el}s" > "$R/outcome"
elif [ $dead = 1 ]; then
  echo "DEAD-noOOM at+${el}s (check scope oom_kill: $(cat $R/memory.events.last 2>/dev/null | tr '\n' ' '))" > "$R/outcome"
else
  echo "SURVIVED last_c=$(echo $lastline | sed 's/,/ n=/')" > "$R/outcome"
fi
cat "$R/outcome"
for hp in "$R"/*.hprof; do
  [ -f "$hp" ] || continue
  ls -la "$hp" > "$R/hprof.ls"; log "dump scan $(basename "$hp")"
  nice -n 10 python3 $H/hprofhist.py "$hp" 30 > "$R/hprofhist.txt" 2>&1
  nice -n 10 python3 $H/hprofstacks.py "$hp" > "$R/hprofstacks-all.txt" 2>&1
  grep -B1 -A14 'LocalDataResponse\|DataOutputBuffer\|AggregationQueryPager\|OutOfMemory' "$R/hprofstacks-all.txt" | head -150 > "$R/hprofstacks.txt"
  rm -f -- "$hp"; log "dump deleted"
done
mkdir -p "$O"; find "${O:?}" -maxdepth 1 -type f -delete
cp "$R"/{readings.csv,yaml.diff,run.meta,outcome,oom-check.txt,tablestats-before.txt,tablestats-after.txt,auth-yaml.txt,readback-su.out,victim-summary.json,victim-per-second.csv,victim.out,attack_t0_ms,death_ms,hprof.ls,hprofhist.txt,hprofstacks.txt} "$O"/ 2>/dev/null
gzip -c "$R/samples.csv" > "$O/samples.csv.gz"; gzip -c "$R/victim.csv" > "$O/victim.csv.gz"
cp "$R/memory.events.last" "$O/memory.events" 2>/dev/null
grep -E '^(t,|[0-9]{13},|SUMMARY)' "$R/client.csv" | gzip -c > "$O/client.csv.gz"
tail -20 "$R/client.err" > "$O/client.err.tail" 2>/dev/null; [ -s "$O/client.err.tail" ] || rm -f "$O/client.err.tail"
grep -h -m3 -B2 -A25 'java\.lang\.OutOfMemoryError' "$R/logs/system.log" "$R/stdout.log" 2>/dev/null | head -120 > "$O/oom-excerpt.txt"; [ -s "$O/oom-excerpt.txt" ] || rm -f "$O/oom-excerpt.txt"
grep -h -m5 'Query cancelled' "$R/logs/debug.log" 2>/dev/null | cut -c1-400 > "$O/cancel-excerpt.txt"; [ -s "$O/cancel-excerpt.txt" ] || rm -f "$O/cancel-excerpt.txt"
[ -f "$R/histo-t150.txt" ] && head -40 "$R/histo-t150.txt" > "$O/histo-t150-top.txt"
python3 "$H/gcwin.py" "$R" > "$O/gcwin.txt" 2>&1
python3 "$H/steps.py" "$R" > "$O/steps.txt" 2>&1
log "END $L $(cat "$R/outcome")"
