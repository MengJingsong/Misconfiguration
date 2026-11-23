#!/usr/bin/env bash
# B21 one clean lifetime on ms0604 (victim + client on the same node, loopback), adapted from B17's run-arm.sh.
#   run-arm.sh <label> <A|I> <heap> <seq-spec> [hist=<c>:<sec>|0] [verify|noverify]
# 1 refuse if a CassandraDaemon runs (bounded wait <= 20 min); fresh clone of the template; start; ready (one retry)
# 2 GC + baseline reading; with "verify": B21Load verify first; 3 client "seq" in the background; readings (RssAnon,
#   scope memory, last JMX sample) every 5 s until the client ends or the victim dies (then the client is stopped by PID);
#   optional one GC.class_histogram once the client has spent <sec> seconds at step c=<c>
# 4 outcome (OOM lines, hprof, memory.events), stop a survivor (tpstats, drain, SIGTERM by PID), small files to out/<label>/.
set -uo pipefail
L=$1 ARM=$2 HEAP=$3 SPEC=$4 HIST=${5:-0} VER=${6:-noverify}
ROOT=/mydata/s4/b21; H=$ROOT/harness; R=$ROOT/runs/$L; D=$ROOT/out/$L
V="bash $H/victim-ctl.sh"
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
log "ARM $L arm=$ARM heap=$HEAP spec=$SPEC hist=$HIST $VER"
for i in $(seq 1 240); do pgrep -f 'java.*CassandraDaemon' >/dev/null || break; [ $i = 1 ] && log "waiting: a CassandraDaemon runs"; sleep 5; done
pgrep -f 'java.*CassandraDaemon' >/dev/null && { log "REFUSE: CassandraDaemon still running after 20 min"; exit 1; }
ok=0
for try in 1 2; do
  $V start "$L" "$ARM" "$HEAP" || exit 1
  if $V ready "$L"; then ok=1; break; fi
  log "invalid start (try $try)"; $V stop "$L"; [ -d "$R" ] && mv "$R" "$R.badstart$try"
done
[ $ok = 1 ] || { echo "INVALID not-ready" > "$R/outcome"; exit 1; }
sleep 5; $V gc "$L"; sleep 3; $V read "$L" base; tail -1 "$R/readings.csv" | cut -c1-250
if [ "$VER" = verify ]; then bash "$H/client.sh" "$L-verify" verify 127.0.0.1 > "$R/verify.txt" 2>&1; cat "$R/verify.txt"; fi
( cd "$R" && setsid nohup bash "$H/client.sh" "$L" seq 127.0.0.1 "$SPEC" > client.out 2> client.err < /dev/null & )
CP=""; for i in $(seq 1 20); do sleep 0.5; CP=$(pgrep -n -f "B21Load seq 127.0.0.1"); [ -n "$CP" ] && break; done
echo "$CP" > "$R/client.pid"; log "client pid $CP"
t0=$(date +%s); dead=0; histd=0; el=0
HC=${HIST%%:*}; HS=${HIST#*:}
while true; do
  sleep 5
  el=$(( $(date +%s) - t0 ))
  if [ "$($V alive "$L")" != ALIVE ]; then log "VICTIM DEAD at +${el}s"; dead=1; break; fi
  $V read "$L" "t+$el"
  if [ "$HIST" != 0 ] && [ $histd = 0 ]; then
    n=$(grep -c "^S [0-9]*,$HC," "$R/client.out" 2>/dev/null)
    if [ "${n:-0}" -ge "$HS" ]; then $V hist "$L" "c${HC}s${HS}"; histd=1; fi
  fi
  kill -0 "$CP" 2>/dev/null || break
done
if [ $dead = 1 ]; then sleep 3; fi
for i in $(seq 1 10); do kill -0 "$CP" 2>/dev/null || break; sleep 1; done
kill "$CP" 2>/dev/null; sleep 1; kill -9 "$CP" 2>/dev/null
grep -E '^(SUMMARY|HOSTGONE|STEPEND)' "$R/client.out"; tail -3 "$R/client.err"
if [ $dead = 0 ] && [ "$($V alive "$L")" = ALIVE ]; then
  sleep 3; $V read "$L" end-pre; $V gc "$L"; sleep 3; $V read "$L" end-post
fi
log "OOM/GC check"; $V oom "$L" > "$R/oom-check.txt" 2>&1; head -40 "$R/oom-check.txt"
$V stop "$L"
oomtype=$(grep -h -o -m1 "java.lang.OutOfMemoryError: [A-Za-z ]*" "$R/logs/system.log" "$R/stdout.log" 2>/dev/null | head -1)
lastq=$(grep -E '^Q ' "$R/client.out" | tail -1 | cut -c1-200)
drops=$(grep -c "overloaded; dropping" "$R/logs/system.log" 2>/dev/null)
oversz=$(grep -c "OversizedMessageException\|exceeds allowed maximum" "$R/logs/system.log" 2>/dev/null)
if [ $dead = 1 ] && [ -n "$oomtype" ]; then echo "OOM type=\"$oomtype\" at+${el}s overload_drop_lines=$drops oversized=$oversz last=[$lastq]" > "$R/outcome"
elif [ $dead = 1 ]; then echo "DEAD-noOOM at+${el}s (memory.events: $(tr '\n' ' ' < $R/memory.events.last 2>/dev/null))" > "$R/outcome"
else echo "SURVIVED overload_drop_lines=$drops oversized=$oversz" > "$R/outcome"; fi
cat "$R/outcome"
rm -rf "$D"; mkdir -p "$D"
cp "$R"/{readings.csv,samples.csv,yaml.diff,run.meta,outcome,oom-check.txt,verify.txt,tpstats.end,sampler.out} "$D"/ 2>/dev/null
cp "$R/memory.events.last" "$D/memory.events" 2>/dev/null
grep -E '^(ITEM|Q|S|SUMMARY|HOSTGONE|STEPEND)' "$R/client.out" > "$D/client.out"
tail -20 "$R/client.err" > "$D/client.err.tail" 2>/dev/null; [ -s "$D/client.err.tail" ] || rm -f "$D/client.err.tail"
grep -h -m3 -B2 -A30 'java\.lang\.OutOfMemoryError' "$R/logs/system.log" "$R/stdout.log" 2>/dev/null | head -150 > "$D/oom-excerpt.txt"
[ -s "$D/oom-excerpt.txt" ] || rm -f "$D/oom-excerpt.txt"
grep -h -m5 -A3 'overloaded; dropping\|OversizedMessage\|exceeds allowed maximum' "$R/logs/system.log" "$R/logs/debug.log" 2>/dev/null | cut -c1-400 > "$D/internode-excerpt.txt"
[ -s "$D/internode-excerpt.txt" ] || rm -f "$D/internode-excerpt.txt"
grep -h -m5 -A3 'Query cancelled (timeout)\|QueryCancelled' "$R/logs/debug.log" 2>/dev/null | cut -c1-300 > "$D/cancel-excerpt.txt"
[ -s "$D/cancel-excerpt.txt" ] || rm -f "$D/cancel-excerpt.txt"
grep -v 'Node configuration' "$R/logs/system.log" | grep -h -m5 -i 'read_size\|local_read_size\|exceeded\|ReadSize\|Top-K' 2>/dev/null | cut -c1-400 > "$D/threshold-excerpt.txt"
[ -s "$D/threshold-excerpt.txt" ] || rm -f "$D/threshold-excerpt.txt"
for f in "$R"/histo-*.txt; do [ -f "$f" ] && head -45 "$f" > "$D/$(basename "$f" .txt)-top.txt"; done
python3 "$H/gcwin.py" "$R" > "$D/gcwin.txt"
grep -h "Humongous regions" "$R"/gc.log* 2>/dev/null | awk '{print $NF}' | sort -t'>' -k2 -n | tail -1 > "$D/humongous-max.txt"
python3 "$H/qsum.py" "$D" > "$D/qsum.txt" 2>&1
ls -la "$R" | grep -i 'hprof\|hs_err' > "$D/hprof.ls" || rm -f "$D/hprof.ls"
log "END $L $(cat "$R/outcome")"
