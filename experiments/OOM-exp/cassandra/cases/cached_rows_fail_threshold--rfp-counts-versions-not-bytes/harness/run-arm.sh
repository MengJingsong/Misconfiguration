#!/usr/bin/env bash
# B22 one clean lifetime on pc82 (two instances + client on the same host, loopback), adapted from U4's run-arm.sh.
#   run-arm.sh <label> <table wide|small> <CL QUORUM|ONE> <T cached_rows_fail_threshold> <Q> <victim heap> <victim direct|auto> [steps] [diag]
# 1 refuse if a CassandraDaemon runs; fresh clone of both templates; start node 1 (victim) then node 2 (peer, 16G)
#   (amendment A1: node 1 first, node 2 is not a seed); ready + 2 UN (one retry if not)
# 2 thresholds set and read back by JMX (RfpJmx), K histogram read; sampler; GC + baseline reading
# 3 client "1:20,Q:160" in the background; readings every 10 s until the client ends or the victim dies;
#   one GC.class_histogram at load second 60 (20 s warm-up + 40 s) if alive
# 4 30 s idle, outcome (OOM lines, hprof), stop survivors (drain + SIGTERM by PID), copy small files to the repo.
set -uo pipefail
L=$1 TBL=$2 CL=$3 T=$4 Q=$5 HEAP=$6 DIRECT=$7 STEPS=${8:-"1:20,$5:160"} DIAG=${9:-}
ROOT=/mydata/s4/b22; H=$ROOT/harness; R=$ROOT/runs/$L
REPO=/proj/misconfiguration-PG0/git-repos/Misconfiguration/experiments/OOM-exp/cassandra/cases/cached_rows_fail_threshold--rfp-counts-versions-not-bytes
V="bash $H/ctl.sh"
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
log "ARM $L table=$TBL CL=$CL T=$T Q=$Q heap=$HEAP direct=$DIRECT steps=$STEPS diag=${DIAG:-no}"
ok=0
for try in 1 2; do
  $V prep "$L" CLONE || exit 1
  if $V start "$L" 1 "$HEAP" "$DIRECT" "$DIAG" && $V ready "$L" 1 && $V start "$L" 2 16G auto && $V ready "$L" 2 && $V ring "$L"; then ok=1; break; fi
  log "invalid start (try $try)"; $V stop "$L"; [ -d "$R" ] && mv "$R" "$R.badstart$try"
done
[ $ok = 1 ] || { mkdir -p "$R"; echo "INVALID not-ready" > "$R/outcome"; exit 1; }
echo "arm table=$TBL CL=$CL T=$T Q=$Q steps=$STEPS" >> "$R/run.meta"
echo "set $(java -cp "$ROOT/cls" RfpJmx 127.0.0.1:7199 set "$T" 2>&1)" | tee -a "$R/rfpk.txt"
$V rfpk "$L" start > /dev/null
$V sampler "$L"
sleep 5; $V gc "$L"; sleep 3; $V read "$L" base | cut -c1-260
( cd "$R" && setsid nohup bash "$H/client.sh" "$L" run 127.0.0.1 "$TBL" "$CL" "$STEPS" > client.csv 2> client.err < /dev/null & )
sleep 3; CP=$(pgrep -f "B22Load run 127.0.0.1 $TBL $CL $STEPS" | head -1); echo "$CP" > "$R/client.pid"
log "client pid $CP"
t0=$(date +%s); dead=0; histd=0; el=0
while true; do
  sleep 10
  el=$(( $(date +%s) - t0 ))
  if [ "$($V alive "$L" 1)" != ALIVE ]; then log "VICTIM DEAD at +${el}s"; dead=1; break; fi
  [ "$($V alive "$L" 2)" != ALIVE ] && log "PEER n2 DEAD at +${el}s"
  $V read "$L" "t+$el" | cut -c1-300
  tail -1 "$R/client.csv" | cut -c1-220
  if [ $histd = 0 ] && [ $el -ge 60 ]; then $V hist "$L" t60; histd=1; fi
  kill -0 "$CP" 2>/dev/null || break
done
for i in $(seq 1 45); do kill -0 "$CP" 2>/dev/null || break; sleep 1; done
kill "$CP" 2>/dev/null; sleep 1; kill -9 "$CP" 2>/dev/null
grep SUMMARY "$R/client.csv"; tail -3 "$R/client.err"
if [ $dead = 0 ] && [ "$($V alive "$L" 1)" = ALIVE ]; then
  sleep 30; $V read "$L" end-idle | cut -c1-260; $V rfpk "$L" end > /dev/null
  $V gc "$L"; sleep 3; $V read "$L" end-postgc | cut -c1-260
fi
[ "$($V alive "$L" 1)" != ALIVE ] && [ $dead = 0 ] && { dead=1; log "victim dead after the load"; }
peer=$($V alive "$L" 2)
$V stop "$L"
# outcome
N1=$R/n1
oomtype=$(grep -h -o -m1 "java.lang.OutOfMemoryError: [A-Za-z ]*" "$N1/logs/system.log" "$N1/stdout.log" 2>/dev/null | head -1)
if [ $dead = 1 ] && [ -n "$oomtype" ]; then echo "OOM type=\"$oomtype\" at+${el}s peer=$peer" > "$R/outcome"
elif [ $dead = 1 ]; then echo "DEAD-noOOM at+${el}s (scope events: $(cat $R/memory.events.last 2>/dev/null | tr '\n' ' ')) peer=$peer" > "$R/outcome"
else echo "SURVIVED peer=$peer" > "$R/outcome"; fi
cat "$R/outcome"
# small evidence into the repo
D=$REPO/logs/$L; mkdir -p "$D"
cp "$R"/{readings.csv,samples.csv,run.meta,outcome,rfpk.txt,ring.txt} "$D"/ 2>/dev/null
cp "$N1/yaml.diff" "$D/yaml-n1.diff"; cp "$R/n2/yaml.diff" "$D/yaml-n2.diff"; cp "$R/n2/env.diff" "$D/env-n2.diff"
cp "$R/memory.events.last" "$D/memory.events" 2>/dev/null
grep -E '^(t,|[0-9]{13},|SUMMARY)' "$R/client.csv" > "$D/client.csv"
tail -20 "$R/client.err" > "$D/client.err.tail" 2>/dev/null; [ -s "$D/client.err.tail" ] || rm -f "$D/client.err.tail"
grep -h -m3 -B2 -A30 'java\.lang\.OutOfMemoryError' "$N1/logs/system.log" "$N1/stdout.log" 2>/dev/null | head -150 > "$D/oom-excerpt.txt"
[ -s "$D/oom-excerpt.txt" ] || rm -f "$D/oom-excerpt.txt"
grep -h 'Replica filtering protection\|OversizedMessage\|Oversized\|cached over' "$N1/logs/system.log" "$R/n2/logs/system.log" 2>/dev/null | cut -c1-400 | head -20 > "$D/rfp-excerpt.txt"
echo "rfp-log-lines n1: $(grep -c 'Replica filtering protection has cached over' "$N1/logs/system.log")" >> "$D/rfp-excerpt.txt"
grep -h -m3 -A12 'OutOfMemoryError' "$R/n2/logs/system.log" > "$D/n2-oom.txt" 2>/dev/null; [ -s "$D/n2-oom.txt" ] || rm -f "$D/n2-oom.txt"
[ -f "$R/histo-t60.txt" ] && head -40 "$R/histo-t60.txt" > "$D/histo-t60-top.txt"
[ -f "$R/probe.txt" ] && cp "$R/probe.txt" "$D/probe.txt"
python3 "$H/gcwin.py" "$N1/logs" > "$D/gcwin.txt"
python3 "$H/steps.py" "$D" > "$D/steps.txt" 2>&1
ls -la "$N1" "$R/n2" | grep -i 'hprof\|hs_err' > "$D/hprof.ls" || rm -f "$D/hprof.ls"
log "END $L $(cat "$R/outcome")"
