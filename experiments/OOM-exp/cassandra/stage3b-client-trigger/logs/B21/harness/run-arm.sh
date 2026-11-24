#!/usr/bin/env bash
# B21 3-b confirm (pc72, 2026-11-23): stage-2 run-arm.sh plus authentication and two roles. The attack client logs in as
# ATK_ROLE (default attacker: SELECT, MODIFY on b21.docs); a victim-tenant client (role tenant: SELECT, MODIFY on vic.kv)
# runs at a fixed light rate (VIC_W writes/s + VIC_R reads/s, default 20 + 20) from 60 s before the attack until 30 s
# after the node dies (or 60 s after the attack ends if it survives), logging per-second success/errors/latency.
#   run-arm.sh <label> <AUTH|A|I> <heap> <seq-spec> [hist=<c>:<sec>|0] [verify|noverify]
# Stage-2 header:
# B21 one clean lifetime on ms0604 (victim + client on the same node, loopback), adapted from B17's run-arm.sh.
# 1 refuse if a CassandraDaemon runs (bounded wait <= 20 min); fresh clone of the template; start; ready (one retry)
# 2 GC + baseline reading; with "verify": B21Load verify first; 3 client "seq" in the background; readings (RssAnon,
#   scope memory, last JMX sample) every 5 s until the client ends or the victim dies (then the client is stopped by PID);
#   optional one GC.class_histogram once the client has spent <sec> seconds at step c=<c>
# 4 outcome (OOM lines, hprof, memory.events), stop a survivor (tpstats, drain, SIGTERM by PID), small files to out/<label>/.
set -uo pipefail
L=$1 ARM=$2 HEAP=$3 SPEC=$4 HIST=${5:-0} VER=${6:-noverify}
ROOT=/mydata/s4/3b-B21; H=$ROOT/harness; R=$ROOT/runs/$L; D=$ROOT/out/$L
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
ATK=${ATK_ROLE:-attacker}; VW=${VIC_W:-20}; VR=${VIC_R:-20}
if [ "$VER" = verify ]; then bash "$H/client.sh" "$L-verify" "$ATK" B21Load verify 127.0.0.1 > "$R/verify.txt" 2>&1; cat "$R/verify.txt"; fi
# victim tenant: start, then a 60 s "before" window
( cd "$R" && setsid nohup bash "$H/client.sh" "$L-vic" tenant B21Victim run 127.0.0.1 $VW $VR "$R/victim.stop" 3600 > victim.out 2> victim.err < /dev/null & )
VP=""; for i in $(seq 1 20); do sleep 0.5; VP=$(pgrep -n -f "B21Victim run 127.0.0.1"); [ -n "$VP" ] && break; done
echo "$VP" > "$R/victim-client.pid"; log "victim tenant client pid $VP (role tenant, ${VW} w/s + ${VR} r/s)"
for i in $(seq 1 12); do sleep 5; $V read "$L" "pre+$((i*5))"; done
grep -c '^V ' "$R/victim.out" | sed 's/^/victim seconds before attack: /'
log "ATTACK START role=$ATK"; date +%s%3N > "$R/attack.start"
( cd "$R" && setsid nohup bash "$H/client.sh" "$L" "$ATK" B21Load seq 127.0.0.1 "$SPEC" > client.out 2> client.err < /dev/null & )
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
date +%s%3N > "$R/attack.end"
if [ $dead = 1 ]; then sleep 3; fi
for i in $(seq 1 10); do kill -0 "$CP" 2>/dev/null || break; sleep 1; done
kill "$CP" 2>/dev/null; sleep 1; kill -9 "$CP" 2>/dev/null
# victim tenant "after" window: 30 s after the node died, 60 s after the attack ended on a survivor
if [ $dead = 1 ]; then sleep 27; else for i in $(seq 1 12); do sleep 5; $V read "$L" "post+$((i*5))"; done; fi
touch "$R/victim.stop"; for i in $(seq 1 15); do kill -0 "$VP" 2>/dev/null || break; sleep 1; done
kill "$VP" 2>/dev/null; sleep 1; kill -9 "$VP" 2>/dev/null
grep '^VSUMMARY' "$R/victim.out"
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
cp "$R"/{attack.start,attack.end} "$D"/ 2>/dev/null
grep -E '^(V |VSUMMARY)' "$R/victim.out" > "$D/victim.out"; tail -5 "$R/victim.err" > "$D/victim.err.tail" 2>/dev/null; [ -s "$D/victim.err.tail" ] || rm -f "$D/victim.err.tail"
python3 "$H/vsum.py" "$D" > "$D/vsum.txt" 2>&1; cat "$D/vsum.txt"
ls -la "$R" | grep -i 'hprof\|hs_err' > "$D/hprof.ls" || rm -f "$D/hprof.ls"
log "END $L $(cat "$R/outcome")"
