#!/usr/bin/env bash
# U10 one clean lifetime on pc82 (victim + client on the same node, loopback), adapted from U4's run-arm.sh.
#   run-arm.sh <label> <A|I1|I2> <heap> <direct> <fetch off|5000> <kind agg|grs> <steps "c:n:secs,...">
# 1 refuse if a CassandraDaemon runs; fresh clone of the template; start; ready (one retry if not ready)
# 2 GC + baseline reading, tablestats; 3 client in the background; readings every 10 s until the client ends or the
#   victim dies; T/M/I labels: one GC.class_histogram at load second 150 if alive
# 4 outcome (OOM lines, hprof, scope memory.events, timeouts), stop a survivor (drain + SIGTERM by PID), copy small files.
set -uo pipefail
L=$1 ARM=$2 HEAP=$3 DIRECT=$4 FETCH=$5 KIND=$6 STEPS=$7
ROOT=/mydata/s4/u10-w4; H=$ROOT/harness; R=$ROOT/runs/$L
REPO=/proj/misconfiguration-PG0/git-repos/Misconfiguration/experiments/OOM-exp/cassandra/cases/default_page_size--unpaged-aggregate-whole-partition
V="bash $H/victim-ctl.sh"
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
log "ARM $L arm=$ARM heap=$HEAP direct=$DIRECT fetch=$FETCH kind=$KIND steps=$STEPS"
ok=0
for try in 1 2; do
  $V start "$L" "$ARM" "$HEAP" "$DIRECT" || exit 1
  if $V ready "$L"; then ok=1; break; fi
  log "invalid start (try $try)"; $V stop "$L"; [ -d "$R" ] && mv "$R" "$R.badstart$try"
done
[ $ok = 1 ] || { echo "INVALID not-ready" > "$R/outcome"; exit 1; }
sleep 5; $V gc "$L"; sleep 3; $V read "$L" base | cut -c1-220
$V ts "$L" | tee "$R/tablestats-before.txt"
( cd "$R" && setsid nohup bash "$H/load.sh" "$L" run 127.0.0.1 16 "$STEPS" "$FETCH" "$KIND" > client.csv 2> client.err < /dev/null & )
sleep 3; CP=$(pgrep -f "U10Load run 127.0.0.1 16 $STEPS $FETCH $KIND" | head -1); echo "$CP" > "$R/client.pid"
log "client pid $CP"
t0=$(date +%s); dead=0; histd=0; el=0
while true; do
  sleep 10
  el=$(( $(date +%s) - t0 ))
  if [ "$($V alive "$L")" != ALIVE ]; then log "VICTIM DEAD at +${el}s"; dead=1; break; fi
  $V read "$L" "t+$el" | cut -c1-260
  tail -1 "$R/client.csv" | cut -c1-200
  if [[ $L =~ ^[TMI][12]?- ]] && [ $histd = 0 ] && [ $el -ge 150 ]; then $V hist "$L" t150; histd=1; fi
  kill -0 "$CP" 2>/dev/null || break
done
for i in $(seq 1 40); do kill -0 "$CP" 2>/dev/null || break; sleep 1; done
kill "$CP" 2>/dev/null; sleep 1; kill -9 "$CP" 2>/dev/null
grep SUMMARY "$R/client.csv"; tail -3 "$R/client.err"
if [ $dead = 0 ] && [ "$($V alive "$L")" = ALIVE ]; then
  $V ts "$L" | tee "$R/tablestats-after.txt"
  sleep 5; $V read "$L" end-pre | cut -c1-220; $V gc "$L"; sleep 3; $V read "$L" end-post | cut -c1-220
fi
log "OOM/GC check"; $V oom "$L" > "$R/oom-check.txt" 2>&1; head -40 "$R/oom-check.txt"
$V stop "$L"
oomtype=$(grep -h -o -m1 "java.lang.OutOfMemoryError: [A-Za-z ]*" "$R/logs/system.log" "$R/stdout.log" 2>/dev/null | head -1)
lastline=$(grep -E '^[0-9]{13},' "$R/client.csv" | tail -1 | cut -d, -f2,3)
if [ $dead = 1 ] && [ -n "$oomtype" ]; then
  # step at death: the step in effect at the victim's last valid JMX sample (client lines are stamped at the END of
  # each second, so it is the first client line stamped >= that time; U4 amendment A3)
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
D=$REPO/logs/$L; mkdir -p "$D"
cp "$R"/{readings.csv,yaml.diff,run.meta,outcome,oom-check.txt,tablestats-before.txt,tablestats-after.txt} "$D"/ 2>/dev/null
gzip -c "$R/samples.csv" > "$D/samples.csv.gz"
cp "$R/memory.events.last" "$D/memory.events" 2>/dev/null
grep -E '^(t,|[0-9]{13},|SUMMARY)' "$R/client.csv" | gzip -c > "$D/client.csv.gz"
grep -h -m5 'Query cancelled' "$R/logs/debug.log" 2>/dev/null | cut -c1-400 > "$D/cancel-excerpt.txt"; [ -s "$D/cancel-excerpt.txt" ] || rm -f "$D/cancel-excerpt.txt"
tail -20 "$R/client.err" > "$D/client.err.tail" 2>/dev/null; [ -s "$D/client.err.tail" ] || rm -f "$D/client.err.tail"
grep -h -m3 -B2 -A25 'java\.lang\.OutOfMemoryError' "$R/logs/system.log" "$R/stdout.log" 2>/dev/null | head -120 > "$D/oom-excerpt.txt"
[ -s "$D/oom-excerpt.txt" ] || rm -f "$D/oom-excerpt.txt"
grep -v 'Node configuration' "$R/logs/system.log" | grep -h -m5 -i 'read_size\|local_read_size\|exceeded\|ReadSize' 2>/dev/null | cut -c1-400 > "$D/threshold-excerpt.txt"
[ -s "$D/threshold-excerpt.txt" ] || rm -f "$D/threshold-excerpt.txt"
[ -f "$R/histo-t150.txt" ] && head -40 "$R/histo-t150.txt" > "$D/histo-t150-top.txt"
python3 "$H/gcwin.py" "$R" > "$D/gcwin.txt"
python3 "$H/steps.py" "$R" > "$D/steps.txt" 2>&1
ls -la "$R" | grep -i 'hprof\|hs_err' > "$D/hprof.ls" || rm -f "$D/hprof.ls"
log "END $L $(cat "$R/outcome")"
