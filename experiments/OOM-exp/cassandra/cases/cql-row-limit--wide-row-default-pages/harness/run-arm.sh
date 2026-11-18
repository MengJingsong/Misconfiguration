#!/usr/bin/env bash
# U4 one clean lifetime on pc75 (victim + client on the same node, loopback).
#   run-arm.sh <label> <A|I> <heap> <direct|auto> <fetch> <steps "c:secs,...">
# 1 refuse if a CassandraDaemon runs; fresh clone of the template; start; ready (one retry if not ready)
# 2 GC + baseline reading; 3 client in the background; readings every 10 s until the client ends or the victim dies;
#   T/M/I labels: one GC.class_histogram at load second 150 if alive
# 4 outcome (OOM lines, hprof, last scope memory.events), stop a survivor (drain + SIGTERM by PID), copy small files.
set -uo pipefail
L=$1 ARM=$2 HEAP=$3 DIRECT=$4 FETCH=$5 STEPS=$6
ROOT=/mydata/s4/u4-w1; H=$ROOT/harness; R=$ROOT/runs/$L
REPO=/proj/misconfiguration-PG0/git-repos/Misconfiguration/experiments/OOM-exp/cassandra/cases/cql-row-limit--wide-row-default-pages
V="bash $H/victim-ctl.sh"
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
log "ARM $L arm=$ARM heap=$HEAP direct=$DIRECT fetch=$FETCH steps=$STEPS"
ok=0
for try in 1 2; do
  $V start "$L" "$ARM" "$HEAP" "$DIRECT" || exit 1
  if $V ready "$L"; then ok=1; break; fi
  log "invalid start (try $try)"; $V stop "$L"; [ -d "$R" ] && mv "$R" "$R.badstart$try"
done
[ $ok = 1 ] || { echo "INVALID not-ready" > "$R/outcome"; exit 1; }
if [ "$L" = IC ]; then for f in 5000 500; do bash "$H/load.sh" IC-one one 127.0.0.1 0 $f | tee -a "$R/ic-one.txt"; done; fi
sleep 5; $V gc "$L"; sleep 3; $V read "$L" base | cut -c1-220
( cd "$R" && setsid nohup bash "$H/load.sh" "$L" run 127.0.0.1 16 "$STEPS" 16 "$FETCH" > client.csv 2> client.err < /dev/null & )
sleep 3; CP=$(pgrep -f "U4Load run 127.0.0.1 16 $STEPS 16 $FETCH" | head -1); echo "$CP" > "$R/client.pid"
log "client pid $CP"
t0=$(date +%s); dead=0; histd=0
while true; do
  sleep 10
  el=$(( $(date +%s) - t0 ))
  if [ "$($V alive "$L")" != ALIVE ]; then log "VICTIM DEAD at +${el}s"; dead=1; break; fi
  $V read "$L" "t+$el" | cut -c1-260
  tail -1 "$R/client.csv" | cut -c1-200
  if [[ $L =~ ^[TMI]- ]] && [ $histd = 0 ] && [ $el -ge 150 ]; then $V hist "$L" t150; histd=1; fi
  kill -0 "$CP" 2>/dev/null || break
done
# client: let it finish (it ends by itself after its steps), else stop it by PID
for i in $(seq 1 40); do kill -0 "$CP" 2>/dev/null || break; sleep 1; done
kill "$CP" 2>/dev/null; sleep 1; kill -9 "$CP" 2>/dev/null
grep SUMMARY "$R/client.csv"; tail -3 "$R/client.err"
if [ $dead = 0 ] && [ "$($V alive "$L")" = ALIVE ]; then
  sleep 5; $V read "$L" end-pre | cut -c1-220; $V gc "$L"; sleep 3; $V read "$L" end-post | cut -c1-220
fi
log "OOM/GC check"; $V oom "$L" > "$R/oom-check.txt" 2>&1; cat "$R/oom-check.txt" | head -40
$V stop "$L"
# outcome
lastc=$(grep -E '^[0-9]{13},' "$R/client.csv" | awk -F, '$6>0||$5>0' | tail -1 | cut -d, -f2)
diedc=$(grep -E '^[0-9]{13},' "$R/client.csv" | tail -1 | cut -d, -f2)
oomtype=$(grep -h -o -m1 "java.lang.OutOfMemoryError: [A-Za-z ]*" "$R/logs/system.log" "$R/stdout.log" 2>/dev/null | head -1)
if [ $dead = 1 ] && [ -n "$oomtype" ]; then
  # step at death: the step in effect at the victim's last valid JMX sample (the sampler returns -1 once the JVM stops
  # answering). Client lines are stamped at the END of each second, so it is the first client line stamped >= that time.
  # (fixed 2026-11-17 23:12 EST: the first version took the last line <= t, i.e. the previous second's step)
  ls_t=$(grep -E '^[0-9]{13},[0-9]' "$R/samples.csv" | tail -1 | cut -d, -f1)
  sc=$(awk -F, -v t="$ls_t" '/^[0-9]{13},/ && $1 >= t {print $2; exit}' "$R/client.csv")
  echo "OOM c=$sc type=\"$oomtype\" at+${el}s" > "$R/outcome"
elif [ $dead = 1 ]; then
  echo "DEAD-noOOM at+${el}s (check scope oom_kill: $(cat $R/memory.events.last 2>/dev/null | tr '\n' ' '))" > "$R/outcome"
else
  echo "SURVIVED last_c=$diedc" > "$R/outcome"
fi
cat "$R/outcome"
# copy small evidence into the repo
D=$REPO/logs/$L; mkdir -p "$D"
cp "$R"/{readings.csv,samples.csv,yaml.diff,run.meta,outcome,oom-check.txt,ic-one.txt} "$D"/ 2>/dev/null
cp "$R/memory.events.last" "$D/memory.events" 2>/dev/null
grep -E '^(t,|[0-9]{13},|SUMMARY)' "$R/client.csv" > "$D/client.csv"
tail -20 "$R/client.err" > "$D/client.err.tail" 2>/dev/null; [ -s "$D/client.err.tail" ] || rm -f "$D/client.err.tail"
grep -h -m3 -B2 -A25 'java\.lang\.OutOfMemoryError' "$R/logs/system.log" "$R/stdout.log" 2>/dev/null | head -120 > "$D/oom-excerpt.txt"
[ -s "$D/oom-excerpt.txt" ] || rm -f "$D/oom-excerpt.txt"
grep -v 'Node configuration' "$R/logs/system.log" | grep -h -m5 -i 'read_size\|local_read_size\|exceeded\|Read on table\|ReadSize' 2>/dev/null | cut -c1-400 > "$D/threshold-excerpt.txt"
[ -s "$D/threshold-excerpt.txt" ] || rm -f "$D/threshold-excerpt.txt"
[ -f "$R/histo-t150.txt" ] && head -40 "$R/histo-t150.txt" > "$D/histo-t150-top.txt"
python3 "$H/gcwin.py" "$R" > "$D/gcwin.txt"
python3 "$H/steps.py" "$D" > "$D/steps.txt" 2>&1
ls -la "$R" | grep -i 'hprof\|hs_err' > "$D/hprof.ls" || rm -f "$D/hprof.ls"
log "END $L $(cat "$R/outcome")"
