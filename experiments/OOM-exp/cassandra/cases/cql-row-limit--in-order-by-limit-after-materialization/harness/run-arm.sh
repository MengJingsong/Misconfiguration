#!/usr/bin/env bash
# B17 one clean lifetime on pc72 (victim + client on the same node, loopback).
#   run-arm.sh <label> <A|I2> <heap> <direct> <seq-spec> [hist_at_secs]
# 1 refuse if a CassandraDaemon runs; fresh clone of the template; start; ready (one retry if not ready)
# 2 GC + baseline reading; VERIFY* labels: B17Load verify first; 3 client "seq" in the background; readings (NMT,
#   RssAnon, last JMX sample) every 5 s until the client ends or the victim dies (then the client is stopped by PID);
#   optional one GC.class_histogram at load second <hist_at_secs> if alive
# 4 outcome (OOM lines, hprof, cancellations in debug.log), stop a survivor (tpstats, drain, SIGTERM by PID), copy small files.
set -uo pipefail
L=$1 ARM=$2 HEAP=$3 DIRECT=$4 SPEC=$5 HIST=${6:-0}
ROOT=/mydata/s4/b17-w4; H=$ROOT/harness; R=$ROOT/runs/$L
REPO=/proj/misconfiguration-PG0/git-repos/Misconfiguration/experiments/OOM-exp/cassandra/cases/cql-row-limit--in-order-by-limit-after-materialization
V="bash $H/victim-ctl.sh"
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
log "ARM $L arm=$ARM heap=$HEAP direct=$DIRECT spec=$SPEC hist=$HIST"
ok=0
for try in 1 2; do
  $V start "$L" "$ARM" "$HEAP" "$DIRECT" || exit 1
  if $V ready "$L"; then ok=1; break; fi
  log "invalid start (try $try)"; $V stop "$L"; [ -d "$R" ] && mv "$R" "$R.badstart$try"
done
[ $ok = 1 ] || { echo "INVALID not-ready" > "$R/outcome"; exit 1; }
sleep 5; $V gc "$L"; sleep 3; $V read "$L" base; tail -1 "$R/readings.csv" | cut -c1-200
if [[ $L == VERIFY* ]]; then bash "$H/client.sh" "$L-verify" verify 127.0.0.1 > "$R/verify.txt" 2>&1; cat "$R/verify.txt"; fi
( cd "$R" && setsid nohup bash "$H/client.sh" "$L" seq 127.0.0.1 "$SPEC" > client.out 2> client.err < /dev/null & )
CP=""; for i in $(seq 1 20); do sleep 0.5; CP=$(pgrep -n -f "B17Load seq 127.0.0.1"); [ -n "$CP" ] && break; done
echo "$CP" > "$R/client.pid"; log "client pid $CP"
t0=$(date +%s); dead=0; histd=0; el=0
while true; do
  sleep 5
  el=$(( $(date +%s) - t0 ))
  if [ "$($V alive "$L")" != ALIVE ]; then log "VICTIM DEAD at +${el}s"; dead=1; break; fi
  $V read "$L" "t+$el"
  if [ "$HIST" -gt 0 ] && [ $histd = 0 ] && [ $el -ge "$HIST" ]; then $V hist "$L" "t$HIST"; histd=1; fi
  kill -0 "$CP" 2>/dev/null || break
done
if [ $dead = 1 ]; then sleep 3; fi
for i in $(seq 1 10); do kill -0 "$CP" 2>/dev/null || break; sleep 1; done
kill "$CP" 2>/dev/null; sleep 1; kill -9 "$CP" 2>/dev/null
grep -E '^(SUMMARY|HOSTGONE)' "$R/client.out"; tail -3 "$R/client.err"
if [ $dead = 0 ] && [ "$($V alive "$L")" = ALIVE ]; then
  sleep 3; $V read "$L" end-pre; $V gc "$L"; sleep 3; $V read "$L" end-post
fi
log "OOM/GC check"; $V oom "$L" > "$R/oom-check.txt" 2>&1; head -40 "$R/oom-check.txt"
$V stop "$L"
canc=$(grep -c "Query cancelled (timeout)" "$R/logs/debug.log" 2>/dev/null)
oomtype=$(grep -h -o -m1 "java.lang.OutOfMemoryError: [A-Za-z ]*" "$R/logs/system.log" "$R/stdout.log" 2>/dev/null | head -1)
lastq=$(grep -E '^(ITEM|Q) ' "$R/client.out" | tail -1 | cut -c1-200)
if [ $dead = 1 ] && [ -n "$oomtype" ]; then echo "OOM type=\"$oomtype\" at+${el}s cancelled=$canc last=[$lastq]" > "$R/outcome"
elif [ $dead = 1 ]; then echo "DEAD-noOOM at+${el}s cancelled=$canc (memory.events: $(tr '\n' ' ' < $R/memory.events.last 2>/dev/null))" > "$R/outcome"
else echo "SURVIVED cancelled=$canc" > "$R/outcome"; fi
cat "$R/outcome"
D=$REPO/logs/$L; mkdir -p "$D"
cp "$R"/{readings.csv,samples.csv,yaml.diff,run.meta,outcome,oom-check.txt,verify.txt,tpstats.end} "$D"/ 2>/dev/null
cp "$R/memory.events.last" "$D/memory.events" 2>/dev/null
grep -E '^(ITEM|Q|S|SUMMARY|HOSTGONE)' "$R/client.out" > "$D/client.out"
tail -20 "$R/client.err" > "$D/client.err.tail" 2>/dev/null; [ -s "$D/client.err.tail" ] || rm -f "$D/client.err.tail"
grep -h -m3 -B2 -A25 'java\.lang\.OutOfMemoryError' "$R/logs/system.log" "$R/stdout.log" 2>/dev/null | head -120 > "$D/oom-excerpt.txt"
[ -s "$D/oom-excerpt.txt" ] || rm -f "$D/oom-excerpt.txt"
grep -h -m3 -A6 'Query cancelled (timeout)' "$R/logs/debug.log" 2>/dev/null | cut -c1-300 > "$D/cancel-excerpt.txt"
[ -s "$D/cancel-excerpt.txt" ] || rm -f "$D/cancel-excerpt.txt"
grep -v 'Node configuration' "$R/logs/system.log" | grep -h -m5 -i 'read_size\|local_read_size\|exceeded\|ReadSize' 2>/dev/null | cut -c1-400 > "$D/threshold-excerpt.txt"
[ -s "$D/threshold-excerpt.txt" ] || rm -f "$D/threshold-excerpt.txt"
for f in "$R"/histo-*.txt; do [ -f "$f" ] && head -40 "$f" > "$D/$(basename "$f" .txt)-top.txt"; done
python3 "$H/gcwin.py" "$R" > "$D/gcwin.txt"
python3 "$H/qsum.py" "$D" > "$D/qsum.txt" 2>&1
ls -la "$R" | grep -i 'hprof\|hs_err' > "$D/hprof.ls" || rm -f "$D/hprof.ls"
log "END $L $(cat "$R/outcome")"
