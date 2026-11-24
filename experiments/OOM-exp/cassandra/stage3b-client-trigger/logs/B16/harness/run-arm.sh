#!/usr/bin/env bash
# B16 3-b confirm (ms0611, 2026-11-23): stage-2 run-arm.sh plus authentication and two roles. The attack client logs in
# as ATK_ROLE (default attacker: SELECT, MODIFY on b16.t, b16.m); a victim-tenant client (role tenant: SELECT, MODIFY on
# vic.kv) runs at a fixed light rate (VIC_W writes/s + VIC_R reads/s, default 20 + 20) from 60 s before the attack until
# 30 s after the node dies (60 s after the attack ends on a survivor), logging per-second success/errors/latency.
#   run-arm.sh <label> <AUTH|LOAD-AUTH> <heap> <tbl t|m> <steps "c:secs,..."> [warmSecs=15]
#   arm AUTH: fresh copy of the template (stage 2's T: warm-up 1 read on m for 15 s, then the steps on <tbl>).
#   arm LOAD-AUTH ("alone" claim check): empty node at <heap>; superuser admin-setup; tenant setup; then, as the attack,
#   the attacker writes t itself (49,999 x 12,000-B range deletes) and reads it in the same lifetime (no restart, no
#   operator step).
# After the lifetime: outcome, small files to out/<label>/, hprof scan (hprofhist.py, hprofstacks.py) then the .hprof is
# deleted (its ls -l kept).
set -uo pipefail
L=$1 ARM=$2 HEAP=$3 TBL=$4 STEPS=$5 WARM=${6:-15}
ROOT=/mydata/s4/3b-B16; H=$ROOT/harness; R=$ROOT/runs/$L; D=$ROOT/out/$L
V="bash $H/victim-ctl.sh"; C="bash $H/client.sh"
F(){ grep -v "^\s*at \|SchemaParser\|IllegalArg"; }
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
log "ARM $L arm=$ARM heap=$HEAP tbl=$TBL steps=$STEPS warm=$WARM"
ok=0
for try in 1 2; do
  $V start "$L" "$ARM" "$HEAP" || exit 1
  if $V ready "$L"; then ok=1; break; fi
  log "invalid start (try $try)"; $V stop "$L"; [ -d "$R" ] && mv "$R" "$R.badstart$try"
done
[ $ok = 1 ] || { echo "INVALID not-ready" > "$R/outcome"; exit 1; }
if [ "$ARM" = LOAD-AUTH ]; then
  $C $L-admin cassandra B16Load admin-setup 127.0.0.1 2>&1 | F > "$R/admin-setup.txt"; grep -c "^admin:" "$R/admin-setup.txt"
  $C $L-ten tenant B16Victim setup 127.0.0.1 1000 2>&1 | F | tail -2
fi
sleep 5; $V gc "$L"; sleep 3; $V read "$L" base | cut -c1-220
ATK=${ATK_ROLE:-attacker}; VW=${VIC_W:-20}; VR=${VIC_R:-20}
( cd "$R" && setsid nohup bash "$H/client.sh" "$L-vic" tenant B16Victim run 127.0.0.1 $VW $VR "$R/victim.stop" 3600 > victim.out 2> victim.err < /dev/null & )
VP=""; for i in $(seq 1 20); do sleep 0.5; VP=$(pgrep -n -f "B16Victim run 127.0.0.1"); [ -n "$VP" ] && break; done
echo "$VP" > "$R/victim-client.pid"; log "victim tenant client pid $VP (role tenant, ${VW} w/s + ${VR} r/s)"
for i in $(seq 1 6); do sleep 10; $V read "$L" "pre+$((i*10))" | cut -c1-200; done
log "victim seconds before attack: $(grep -c '^V [0-9]' "$R/victim.out")"
log "ATTACK START role=$ATK"; date +%s%3N > "$R/attack.start"
if [ "$ARM" = LOAD-AUTH ]; then
  ATT="bash $H/client.sh $L-load $ATK B16Load load 127.0.0.1 t 49999 12000 20 4 > load.out 2>&1; date +%s%3N > load.end; "
else ATT=""; fi
( cd "$R" && setsid nohup bash -c "$ATT exec bash $H/client.sh $L $ATK B16Load run 127.0.0.1 8 m $WARM $TBL $STEPS > client.csv 2> client.err" < /dev/null > /dev/null 2>&1 & )
t0=$(date +%s); dead=0; el=0; CP=""
while true; do
  sleep 5
  el=$(( $(date +%s) - t0 ))
  [ -z "$CP" ] && { CP=$(pgrep -n -f "B16Load run 127.0.0.1 8 m $WARM $TBL"); [ -n "$CP" ] && { echo "$CP" > "$R/client.pid"; log "attack read client pid $CP"; }; }
  if [ "$($V alive "$L")" != ALIVE ]; then log "VICTIM DEAD at +${el}s"; dead=1; break; fi
  $V read "$L" "t+$el" | cut -c1-240
  [ -n "$CP" ] && tail -1 "$R/client.csv" | cut -c1-200
  [ -n "$CP" ] && ! kill -0 "$CP" 2>/dev/null && break
  [ $el -gt 1800 ] && { log "attack timeout 1800 s"; break; }
done
date +%s%3N > "$R/attack.end"
[ $dead = 1 ] && sleep 3
for p in $CP $(pgrep -f "B16Load (load|run) 127.0.0.1"); do kill "$p" 2>/dev/null; done; sleep 1
for p in $(pgrep -f "B16Load (load|run) 127.0.0.1"); do kill -9 "$p" 2>/dev/null; done
if [ $dead = 1 ]; then sleep 27; else for i in $(seq 1 6); do sleep 10; $V read "$L" "post+$((i*10))" | cut -c1-200; done; fi
touch "$R/victim.stop"; for i in $(seq 1 15); do kill -0 "$VP" 2>/dev/null || break; sleep 1; done
kill "$VP" 2>/dev/null; sleep 1; kill -9 "$VP" 2>/dev/null
grep '^VSUMMARY' "$R/victim.out"; grep SUMMARY "$R/client.csv"; tail -3 "$R/client.err"
if [ $dead = 0 ] && [ "$($V alive "$L")" = ALIVE ]; then sleep 3; $V read "$L" end-pre | cut -c1-220; $V tblm "$L" end; fi
log "OOM/GC check"; $V oom "$L" > "$R/oom-check.txt" 2>&1; head -40 "$R/oom-check.txt"
$V stop "$L"
oomtype=$(grep -h -o -m1 "java.lang.OutOfMemoryError: [A-Za-z ]*" "$R/logs/system.log" "$R/stdout.log" 2>/dev/null | head -1)
if [ $dead = 1 ] && [ -n "$oomtype" ]; then
  ls_t=$(grep -E '^[0-9]{13},[0-9]' "$R/samples.csv" | tail -1 | cut -d, -f1)
  sc=$(awk -F, -v t="$ls_t" '/^[0-9]{13},/ && $1 >= t {print $2; exit}' "$R/client.csv")
  echo "OOM c=${sc:-load} type=\"$oomtype\" at+${el}s (from attack start)" > "$R/outcome"
elif [ $dead = 1 ]; then echo "DEAD-noOOM at+${el}s (memory.events: $(tr '\n' ' ' < $R/memory.events.last 2>/dev/null))" > "$R/outcome"
else echo "SURVIVED last_c=$(grep -E '^[0-9]{13},' "$R/client.csv" | tail -1 | cut -d, -f2)" > "$R/outcome"; fi
cat "$R/outcome"
rm -rf "$D"; mkdir -p "$D"
cp "$R"/{readings.csv,samples.csv,yaml.diff,run.meta,outcome,oom-check.txt,tblmetrics.txt,admin-setup.txt,attack.start,attack.end,load.end,load.out,sampler.out} "$D"/ 2>/dev/null
cp "$R/memory.events.last" "$D/memory.events" 2>/dev/null
[ -f "$R/client.csv" ] && grep -E '^(t,|[0-9]{13},|SUMMARY)' "$R/client.csv" > "$D/client.csv"
tail -20 "$R/client.err" > "$D/client.err.tail" 2>/dev/null; [ -s "$D/client.err.tail" ] || rm -f "$D/client.err.tail"
grep -E '^(V |VSUMMARY)' "$R/victim.out" > "$D/victim.out"; tail -5 "$R/victim.err" > "$D/victim.err.tail" 2>/dev/null; [ -s "$D/victim.err.tail" ] || rm -f "$D/victim.err.tail"
grep -h -m3 -B2 -A25 'java\.lang\.OutOfMemoryError' "$R/logs/system.log" "$R/stdout.log" 2>/dev/null | head -120 > "$D/oom-excerpt.txt"
[ -s "$D/oom-excerpt.txt" ] || rm -f "$D/oom-excerpt.txt"
{ echo "count 'tombstone cells' warnings: $(grep -c 'tombstone cells' "$R/logs/system.log")"; echo "count 'Scanned over': $(grep -c 'Scanned over' "$R/logs/system.log")";
  echo "count local_read_size lines: $(grep -v 'Node configuration' "$R/logs/system.log" | grep -c -i 'local_read_size\|LocalReadSize')";
  grep -h 'tombstone cells\|Scanned over' "$R/logs/system.log" | cut -c1-300 | tail -3; } > "$D/threshold-excerpt.txt"
grep -h "Enqueuing flush\|Completed flushing\|Flushing largest" "$R/logs/system.log" "$R/logs/debug.log" 2>/dev/null | cut -c1-250 | tail -15 > "$D/flush-lines.txt"; [ -s "$D/flush-lines.txt" ] || rm -f "$D/flush-lines.txt"
python3 "$H/gcwin.py" "$R" > "$D/gcwin.txt"
[ -f "$D/client.csv" ] && python3 "$H/steps.py" "$D" > "$D/steps.txt" 2>&1
python3 "$H/vsum16.py" "$D" > "$D/vsum.txt" 2>&1; cat "$D/vsum.txt"
HP=$(ls "$R"/*.hprof 2>/dev/null | head -1)
if [ -n "$HP" ]; then
  ls -l "$R" | grep -i 'hprof\|hs_err' > "$D/hprof.ls"
  log "hprof scan $HP"
  nice -n 19 python3 "$H/hprofhist.py" "$HP" 30 > "$D/hprofhist.txt" 2>&1
  nice -n 19 python3 "$H/hprofstacks.py" "$HP" expandToFit > "$D/hprofstacks.txt" 2>&1
  [ -s "$D/hprofstacks.txt" ] || nice -n 19 python3 "$H/hprofstacks.py" "$HP" LocalDataResponse > "$D/hprofstacks.txt" 2>&1
  rm -f "$HP"; log "hprof deleted"
fi
log "END $L $(cat "$R/outcome")"
