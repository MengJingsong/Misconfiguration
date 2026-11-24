#!/usr/bin/env bash
# U8 3-b confirm: one clean lifetime on ms0640 with PasswordAuthenticator + CassandraAuthorizer (victim node + clients on
# the same node, loopback). Adapted from the case's run-arm.sh (stage 2).
#   run-arm.sh <label> <A|G> <heap> <json|plain|none> <N> <R>
# 1 refuse if a CassandraDaemon runs; empty node dir; start; ready (one retry if not ready)
# 2 superuser (cassandra/cassandra) only: roles u8atk / u8victim / u8nogrant, GRANT CREATE ON ALL KEYSPACES TO u8atk, the
#   victim's keyspace/table + SELECT/MODIFY grants, read-backs (LIST, system_views.settings)
# 3 claim probes (no credentials, wrong password, cross-role access, data role DDL)
# 4 attacker u8atk: CREATE KEYSPACE u8, CREATE TABLE u8.t vector<boolean,16000000>, one 16 MB INSERT, verify (no nodetool
#   flush: an operator step, not a client step; the row stays in the memtable)
# 5 victim role u8victim: 20 ops/s on victimks.kv from 60 s before the attack until 60 s after its end / node death
# 6 attack client as u8atk (N connections, barrier per round, R rounds); alive check every 2 s; readings every 10 s
# 7 stop at client end, victim death or 600 s; outcome; stop a survivor; dump scan (hprofhist/hprofstacks) then delete it
# mode none (arm G, guardrail claim probe): steps 1-4 only, the load as the attacker and then as the superuser.
set -uo pipefail
L=$1 ARM=$2 HEAP=$3 MODE=$4 N=$5 RR=$6
D=16000000
ROOT=/mydata/s4/3b-U8; H=$ROOT/harness; R=$ROOT/runs/$L; O=$ROOT/out/$L
J=$ROOT/tree/build/lib/jars
CCP="$ROOT/cls:$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$ROOT/tree/lib/*"
SU="-Du8.user=cassandra -Du8.pass=cassandra"; ATK="-Du8.user=u8atk -Du8.pass=atk-3bU8"; VIC="-Du8.user=u8victim -Du8.pass=vic-3bU8"
JC="java -Xmx512m -cp $CCP"
V="bash $H/victim-ctl.sh"
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
log "ARM $L arm=$ARM heap=$HEAP mode=$MODE N=$N R=$RR D=$D (auth on)"
ok=0
for try in 1 2; do
  $V start "$L" "$ARM" "$HEAP" auto || exit 1
  if $V ready "$L"; then ok=1; break; fi
  log "invalid start (try $try)"; $V stop "$L"; [ -d "$R" ] && mv "$R" "$R.badstart$try"
done
[ $ok = 1 ] || { echo "INVALID not-ready" > "$R/outcome"; exit 1; }
grep -E '^(authenticator|authorizer|role_manager|vector_dimensions)' "$R/conf/cassandra.yaml" | tee "$R/auth-yaml.txt"
log "superuser setup"; $JC $SU U8Client su 127.0.0.1 $H/setup-su.cql > "$R/setup-su.out" 2>&1
grep -E '^(>|  OK|  FAIL)' "$R/setup-su.out" | grep -v 'system_views.settings' | head -40
grep -E 'name=(authenticator|authorizer|role_manager|network_authorizer|vector_|native_transport_max_threads|native_transport_max_frame_size|commitlog_segment_size|max_mutation_size|read_thresholds_enabled|column_value_size|coordinator_read_size|native_transport_rate_limiting_enabled|native_transport_max_concurrent_connections |native_transport_max_request_data_in_flight|memtable_allocation_type|memtable_heap_space)' "$R/setup-su.out" > "$R/settings-readback.txt"
grep -q 'FAIL' "$R/setup-su.out" && { log "superuser setup had a FAIL"; }
if [ "$MODE" = none ]; then
  log "guardrail probe: attacker, then superuser, create the 16M-dimension table"
  {
    java -Xmx256m -cp "$CCP" $ATK U8Client try 127.0.0.1 "CREATE KEYSPACE u8 WITH replication = {'class':'SimpleStrategy','replication_factor':1}"
    java -Xmx256m -cp "$CCP" $ATK U8Client try 127.0.0.1 "CREATE TABLE u8.t (pk int PRIMARY KEY, v vector<boolean, 16000000>)"
    java -Xmx256m -cp "$CCP" $ATK U8Client try 127.0.0.1 "CREATE TABLE u8.t8k (pk int PRIMARY KEY, v vector<boolean, 8192>)"
    java -Xmx256m -cp "$CCP" $SU U8Client try 127.0.0.1 "CREATE TABLE u8.tsu (pk int PRIMARY KEY, v vector<boolean, 16000000>)"
  } > "$R/probes.out" 2>&1
  grep -E '^(# as|>|  RESULT)' "$R/probes.out"
  grep -i guardrail "$R/logs/system.log" | cut -c1-300 | head -5 > "$R/guardrail-log.txt"; cat "$R/guardrail-log.txt"
  echo "PROBE-ONLY" > "$R/outcome"
else
log "probes"
{
  java -Xmx256m -cp "$CCP" -Du8.user= U8Client try 127.0.0.1 "SELECT release_version FROM system.local"
  java -Xmx256m -cp "$CCP" -Du8.user=u8atk -Du8.pass=wrong U8Client try 127.0.0.1 "SELECT release_version FROM system.local"
  java -Xmx256m -cp "$CCP" $ATK U8Client try 127.0.0.1 "SELECT k FROM victimks.kv LIMIT 1"
  java -Xmx256m -cp "$CCP" $VIC U8Client try 127.0.0.1 "CREATE TABLE victimks.x (pk int PRIMARY KEY, v vector<boolean, 16000000>)"
  java -Xmx256m -cp "$CCP" $VIC U8Client try 127.0.0.1 "CREATE KEYSPACE u8v WITH replication = {'class':'SimpleStrategy','replication_factor':1}"
  java -Xmx256m -cp "$CCP" -Du8.user=u8nogrant -Du8.pass=nog-3bU8 U8Client try 127.0.0.1 "CREATE KEYSPACE u8n WITH replication = {'class':'SimpleStrategy','replication_factor':1}"
} > "$R/probes.out" 2>&1
grep -E '^(# as|>|  RESULT)' "$R/probes.out"
log "attacker load (u8atk)"
$JC -Xmx1g $ATK U8Client load 127.0.0.1 $D > "$R/load.out" 2>&1; tail -2 "$R/load.out"
$JC $ATK U8Client verify 127.0.0.1 >> "$R/load.out" 2>&1; tail -1 "$R/load.out"
$JC $SU U8Client su 127.0.0.1 $H/post-su.cql > "$R/post-su.out" 2>&1; grep -E '^(  row|  FAIL)' "$R/post-su.out"
grep -q "verify len=$D" "$R/load.out" || { log "verify failed"; echo "INVALID load/verify" > "$R/outcome"; }
fi
if [ ! -f "$R/outcome" ]; then
( cd "$R" && setsid nohup java -Xmx256m -cp "$CCP" $VIC U8Client victim 127.0.0.1 20 "$R/victim.stop" "$R/victim.csv" > victim.out 2>&1 < /dev/null & )
sleep 2; VP=$(pgrep -f "U8Client victim 127.0.0.1" | head -1); echo "$VP" > "$R/victim.pid"; log "victim client pid $VP; 60 s baseline"
sleep 60
$V read "$L" base | cut -c1-240
( cd "$R" && setsid nohup java -Xmx8g -XX:MaxDirectMemorySize=8g -cp "$CCP" $ATK U8Client run 127.0.0.1 "$MODE" "$N" "$RR" > client.csv 2> client.err < /dev/null & )
t0ms=$(date +%s%3N); echo "$t0ms" > "$R/attack_t0_ms"
sleep 1; CP=$(pgrep -f "U8Client run 127.0.0.1 $MODE $N $RR" | head -1); echo "$CP" > "$R/client.pid"
log "attack client pid $CP (t0 $t0ms)"
t0=$(date +%s); dead=0; lastread=0; deathms=0
while true; do
  el=$(( $(date +%s) - t0 ))
  if [ "$($V alive "$L")" != ALIVE ]; then deathms=$(date +%s%3N); log "VICTIM NODE DEAD at +${el}s"; dead=1; break; fi
  if ! kill -0 "$CP" 2>/dev/null; then grep -q "down=true" "$R/client.csv" 2>/dev/null || break; [ -f "$R/watch.flag" ] || { log "client gave up (down=true); watching node to 600 s"; touch "$R/watch.flag"; }; fi
  [ $el -ge 600 ] && { log "600 s stop"; break; }
  if [ $(( el - lastread )) -ge 10 ]; then $V read "$L" "t+$el" | cut -c1-240; lastread=$el; fi
  sleep 2
done
echo "$deathms" > "$R/death_ms"
for i in $(seq 1 30); do kill -0 "$CP" 2>/dev/null || break; sleep 1; done
kill "$CP" 2>/dev/null; sleep 1; kill -9 "$CP" 2>/dev/null
grep SUMMARY "$R/client.csv"; tail -3 "$R/client.err"
if [ $dead = 0 ] && [ "$($V alive "$L")" = ALIVE ]; then sleep 3; $V read "$L" end | cut -c1-240; fi
log "victim client: 60 s more"; sleep 60; touch "$R/victim.stop"
for i in $(seq 1 30); do kill -0 "$VP" 2>/dev/null || break; sleep 1; done; kill -9 "$VP" 2>/dev/null
python3 $H/victimsum.py "$R/victim.csv" "$t0ms" "$deathms" "$R/victim" > /dev/null
fi
log "OOM/GC check"; $V oom "$L" > "$R/oom-check.txt" 2>&1; head -40 "$R/oom-check.txt"
$V stop "$L"
el=${el:-0}
oomtype=$(grep -h -o -m1 "java.lang.OutOfMemoryError: [A-Za-z ]*" "$R/logs/system.log" "$R/stdout.log" 2>/dev/null | head -1)
done_n=$(grep -cE '^[0-9]{13},[0-9]{13},[0-9]+,[0-9]+,[0-9]+,$' "$R/client.csv" 2>/dev/null)
err_n=$(grep -cE '^[0-9]{13},[0-9]{13},[0-9]+,[0-9]+,-?[0-9]+,.+' "$R/client.csv" 2>/dev/null)
lens=$(grep -E '^[0-9]{13},' "$R/client.csv" 2>/dev/null | cut -d, -f5 | sort | uniq -c | tr '\n' ' ')
if [ -f "$R/outcome" ]; then :
elif [ $dead = 1 ] && [ -n "$oomtype" ]; then echo "OOM type=\"$oomtype\" at+${el}s completed=$done_n errors=$err_n lens=[$lens]" > "$R/outcome"
elif [ $dead = 1 ]; then echo "DEAD-noOOM at+${el}s completed=$done_n (scope: $(tr '\n' ' ' < $R/memory.events.last 2>/dev/null))" > "$R/outcome"
elif [ "${err_n:-0}" -gt 0 ]; then echo "ALIVE-noOOM (requests failed) completed=$done_n errors=$err_n lens=[$lens] wall=${el}s" > "$R/outcome"
else echo "SURVIVED completed=$done_n errors=$err_n lens=[$lens] wall=${el}s" > "$R/outcome"; fi
cat "$R/outcome"
for hp in "$R"/*.hprof; do
  [ -f "$hp" ] || continue
  ls -la "$hp" > "$R/hprof.ls"; log "dump scan $(basename "$hp")"
  nice -n 10 python3 $H/hprofhist.py "$hp" 30 > "$R/dump-hist.txt" 2>&1
  nice -n 10 python3 $H/hprofstacks.py "$hp" VectorType > "$R/dump-stacks.txt" 2>&1
  rm -f -- "$hp"; log "dump deleted"
done
mkdir -p "$O"; find "${O:?}" -maxdepth 1 -type f -delete
cp "$R"/{readings.csv,samples.csv,yaml.diff,run.meta,outcome,oom-check.txt,load.out,setup-su.out,post-su.out,probes.out,settings-readback.txt,auth-yaml.txt,guardrail-log.txt,victim-summary.json,victim-per-second.csv,victim.out,attack_t0_ms,death_ms,hprof.ls,dump-hist.txt,dump-stacks.txt} "$O"/ 2>/dev/null
cp "$R/memory.events.last" "$O/memory.events" 2>/dev/null
grep -E '^(start_ms|[0-9]{13},|SUMMARY)' "$R/client.csv" > "$O/client.csv" 2>/dev/null
tail -20 "$R/client.err" > "$O/client.err.tail" 2>/dev/null; [ -s "$O/client.err.tail" ] || rm -f "$O/client.err.tail"
grep -h -m3 -B2 -A30 'java\.lang\.OutOfMemoryError' "$R/logs/system.log" "$R/stdout.log" 2>/dev/null | head -120 > "$O/oom-excerpt.txt"; [ -s "$O/oom-excerpt.txt" ] || rm -f "$O/oom-excerpt.txt"
grep -h 'Pause' "$R"/gc.log* 2>/dev/null | grep -E 'ms$' | tail -40 > "$O/gc-pauses-tail.txt"
grep -h -E 'Pause (Full|Young).*ms$' "$R"/gc.log* 2>/dev/null | sed -n 's/.*->\([0-9]*\)M(\([0-9]*\)M).*/\1 \2/p' | sort -n | tail -1 > "$O/gc-max-after.txt"
grep -h -E 'Pause Full.*ms$' "$R"/gc.log* 2>/dev/null | tail -10 > "$O/gc-full-tail.txt"
python3 "$H/gcwin.py" "$R" > "$O/gcwin.txt" 2>&1
grep -i 'exception\|error\|guardrail\|Unauthorized' "$R/logs/system.log" 2>/dev/null | grep -v 'OutOfMemory' | head -20 | cut -c1-400 > "$O/system-errors.txt"; [ -s "$O/system-errors.txt" ] || rm -f "$O/system-errors.txt"
log "END $L $(cat "$R/outcome")"
