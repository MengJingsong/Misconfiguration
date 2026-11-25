#!/usr/bin/env bash
# B26 one clean lifetime on pc91 (victim + client on the same node, loopback), per the frozen "Lifetime procedure".
#   run-arm.sh <label> <A|IV> <heap|AUTO> <S16|S30> <t1[,t2..]> <c> <session> [RET]
#     session: nodetool arguments started at main-client second 10, e.g. "profileload b26 t1", or "tpstats" (arm M).
#     RET: retention measurement (CAL-RET): after nodetool returns, stop the client, wait 5 s, M1 (jmap -histo:live,
#          GC.heap_info), then "profileload b26 t1 1000 -a LOCAL_READ_TIME" (replaces the queue), wait 5 s, M2.
#     env NTHEAP: nodetool client heap (unset = shipped 128m).
# 1 refuse if a CassandraDaemon runs; fresh clone of the template; start; ready (one retry)
# 2 GC + baseline reading; warm-up client run 20 s without sampling; 10 s idle
# 3 main client run 120 s in the background; at its second 10 the session command in the background
# 4 readings every 2 s until the client ends or the victim dies (then the client and nodetool are stopped by PID)
# 5 outcome (OOM lines, hprof), stop a survivor (tpstats, drain, SIGTERM by PID), copy small files to the repo logs/.
set -uo pipefail
L=$1 ARM=$2 HEAP=$3 SHAPE=$4 TABLES=$5 C=$6 SESSION=$7 RET=${8:-}
ROOT=/mydata/s4/b26; H=$ROOT/harness; R=$ROOT/runs/$L
REPO=/proj/misconfiguration-PG0/git-repos/Misconfiguration/experiments/OOM-exp/cassandra/cases/profileload-capacity--local-read-time-sampler-cql-strings
V="bash $H/victim-ctl.sh"
NTB="$ROOT/tree/bin/nodetool -h 127.0.0.1"
NTENV=""; [ -n "${NTHEAP:-}" ] && NTENV="MAX_HEAP_SIZE=$NTHEAP"
nt(){ env $NTENV $NTB "$@"; }   # fixed 2026-11-24 12:03 EST: was a shell function called through timeout (not found)
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
log "ARM $L arm=$ARM heap=$HEAP shape=$SHAPE tables=$TABLES c=$C session=[$SESSION] ret=$RET ntheap=${NTHEAP:-default}"
ok=0
for try in 1 2; do
  $V start "$L" "$ARM" "$HEAP" || exit 1
  if $V ready "$L"; then ok=1; break; fi
  log "invalid start (try $try)"; $V stop "$L"; [ -d "$R" ] && mv "$R" "$R.badstart$try"
done
[ $ok = 1 ] || { echo "INVALID not-ready" > "$R/outcome"; exit 1; }
sleep 5; $V gc "$L"; sleep 3; $V read "$L" base
timeout 60 env $NTENV $NTB tpstats > "$R/tpstats.begin" 2>&1
log "warm-up 20 s"
timeout 150 bash $H/client.sh "$L-warm" run 127.0.0.1 "$SHAPE" "$TABLES" "$C" 20 > "$R/warm.out" 2> "$R/warm.err"
grep SUMMARY "$R/warm.out"
sleep 10; $V read "$L" pre-main
( cd "$R" && setsid nohup bash $H/client.sh "$L-main" run 127.0.0.1 "$SHAPE" "$TABLES" "$C" 120 > client.out 2> client.err < /dev/null & )
CP=""; for i in $(seq 1 40); do sleep 0.25; CP=$(pgrep -n -f "B26Load run 127.0.0.1 $SHAPE $TABLES $C 120"); [ -n "$CP" ] && break; done
echo "$CP" > "$R/client.pid"; log "client pid $CP"
for i in $(seq 1 300); do grep -q '^S 10,' "$R/client.out" 2>/dev/null && break; sleep 0.2; done
log "session start: nodetool $SESSION"; echo "$(date -u +%s.%N) session-start" >> "$R/events"
# fixed 2026-11-24 15:20 EST (stage-2 retry session): bin/nodetool expands its arguments unquoted ([ ! $1 ], $ARGS), so a
# literal '*' was globbed against the files of $R (CAL-15872M/CAL-AUTO of the first attempt ran no session). Run it from an
# empty directory so '*' stays literal.
( set -f; mkdir -p "$R/ntcwd" && cd "$R/ntcwd" && if [ -n "${NTHEAP:-}" ]; then export MAX_HEAP_SIZE=$NTHEAP; fi; setsid nohup $NTB $SESSION > "$R/nodetool.out" 2> "$R/nodetool.err" < /dev/null & echo $! > "$R/nodetool.pid" )
NP=$(cat "$R/nodetool.pid")
t0=$(date +%s); dead=0; el=0; ntdone=0
while true; do
  sleep 2
  el=$(( $(date +%s) - t0 ))
  if [ "$($V alive "$L")" != ALIVE ]; then log "VICTIM DEAD at session+${el}s"; echo "$(date -u +%s) victim-dead" >> "$R/events"; dead=1; break; fi
  $V read "$L" "s+$el"
  if [ $ntdone = 0 ] && ! kill -0 "$NP" 2>/dev/null; then ntdone=1; log "nodetool returned at session+${el}s"; echo "$(date -u +%s) nodetool-returned" >> "$R/events"
    if [ "$RET" = RET ]; then kill "$CP" 2>/dev/null; log "RET: client stopped"; sleep 5
      $V read "$L" M1-pre; $V hist "$L" M1; $V read "$L" M1-post
      timeout 120 env $NTENV $NTB profileload b26 t1 1000 -a LOCAL_READ_TIME > "$R/nodetool-ret2.out" 2>&1; sleep 5
      $V read "$L" M2-pre; $V hist "$L" M2; $V read "$L" M2-post
      break
    fi
  fi
  kill -0 "$CP" 2>/dev/null || break
done
if [ $dead = 1 ]; then sleep 3; fi
kill "$CP" 2>/dev/null; sleep 1; kill -9 "$CP" 2>/dev/null
pkill -f "B26Load run 127.0.0.1 $SHAPE $TABLES $C 120" 2>/dev/null
for i in $(seq 1 30); do kill -0 "$NP" 2>/dev/null || break; sleep 1; done; kill -9 "$NP" 2>/dev/null
if [ $dead = 0 ] && [ "$($V alive "$L")" = ALIVE ] && [ "$RET" != RET ]; then
  sleep 3; $V read "$L" end-pre; $V gc "$L"; sleep 3; $V read "$L" end-post
fi
# wait for a heap dump in progress to finish (process gone)
for i in $(seq 1 240); do [ "$($V alive "$L")" = ALIVE ] && [ $dead = 1 ] || break; sleep 1; done
log "OOM/GC check"; $V oom "$L" > "$R/oom-check.txt" 2>&1; head -30 "$R/oom-check.txt"
$V stop "$L"
oomtype=$(grep -h -o -m1 "java.lang.OutOfMemoryError: [A-Za-z ]*" "$R/logs/system.log" "$R/stdout.log" 2>/dev/null | head -1)
slow=$(grep -c "operations were slower than" "$R/logs/debug.log" 2>/dev/null)
canc=$(grep -c "Query cancelled" "$R/logs/debug.log" 2>/dev/null)
lastS=$(grep '^S ' "$R/client.out" | tail -1)
if [ $dead = 1 ] && [ -n "$oomtype" ]; then echo "OOM type=\"$oomtype\" at session+${el}s slow=$slow cancelled=$canc lastS=[$lastS]" > "$R/outcome"
elif [ $dead = 1 ]; then echo "DEAD-noOOM at session+${el}s (memory.events: $(tr '\n' ' ' < $R/memory.events.last 2>/dev/null))" > "$R/outcome"
else echo "SURVIVED slow=$slow cancelled=$canc" > "$R/outcome"; fi
cat "$R/outcome"
D=$REPO/logs/$L; mkdir -p "$D"
cp "$R"/{readings.csv,samples.csv,yaml.diff,run.meta,outcome,oom-check.txt,tpstats.begin,tpstats.end,events,warm.out,client.out,nodetool.err,nodetool-ret2.out} "$D"/ 2>/dev/null
cp "$R/memory.events.last" "$D/memory.events" 2>/dev/null
tail -20 "$R/client.err" > "$D/client.err.tail" 2>/dev/null; [ -s "$D/client.err.tail" ] || rm -f "$D/client.err.tail"
# nodetool output: size and the first 300 bytes of each line only
if [ -f "$R/nodetool.out" ]; then
  { echo "bytes=$(wc -c < "$R/nodetool.out") lines=$(wc -l < "$R/nodetool.out")"; awk '{print length($0) "\t" substr($0,1,300)}' "$R/nodetool.out" | head -120; } > "$D/nodetool.out.head"
fi
grep -h -m3 -B2 -A30 'java\.lang\.OutOfMemoryError' "$R/logs/system.log" "$R/stdout.log" 2>/dev/null | cut -c1-400 | head -120 > "$D/oom-excerpt.txt"
[ -s "$D/oom-excerpt.txt" ] || rm -f "$D/oom-excerpt.txt"
grep -h -m5 -A4 'operations were slower than\|Query cancelled' "$R/logs/debug.log" 2>/dev/null | cut -c1-300 > "$D/slow-excerpt.txt"
[ -s "$D/slow-excerpt.txt" ] || rm -f "$D/slow-excerpt.txt"
for f in "$R"/histo-*.txt "$R"/heapinfo-*.txt; do [ -f "$f" ] && head -40 "$f" > "$D/$(basename "$f" .txt)-top.txt"; done
grep -E 'Humongous regions|Pause Full|To-space|humongous' "$R"/gc.log* 2>/dev/null | tail -40 | cut -c1-250 > "$D/gc-humongous-tail.txt"
grep -h -m1 'Heap Region Size\|Heap region size' "$R"/gc.log* > "$D/gc-header.txt" 2>/dev/null
python3 "$H/gcwin.py" "$R" > "$D/gcwin.txt"
ls -la "$R" | grep -i 'hprof\|hs_err' > "$D/hprof.ls" || rm -f "$D/hprof.ls"
log "END $L $(cat "$R/outcome")"
