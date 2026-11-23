#!/usr/bin/env bash
# C10 one clean lifetime on pc91 (3 instances + client on the same node, loopback).
#   run-arm.sh <label> <A|I|I4> <heap1> <test|M> <steps "Q:secs,..."> [trace]
# 1 refuse if a CassandraDaemon runs; fresh clones of the templates; start ring (one retry if not ready)
# 2 30 s idle; optional traces (IC); node-1 reading; 3 client in the background; readings every 10 s until the client
#   ends or node 1 dies; L/M/I labels: one GC.class_histogram at load second 120 if alive; netstats every 30 s
# 4 outcome (OOM lines, hprof, scope memory.events), stop survivors (drain + SIGTERM by PID), copy small files.
set -uo pipefail
L=$1 ARM=$2 HEAP=$3 QRY=$4 STEPS=$5 TRACE=${6:-}
ROOT=/mydata/s4/c10; H=$ROOT/harness; R=$ROOT/runs/$L
REPO=/proj/misconfiguration-PG0/git-repos/Misconfiguration/experiments/OOM-exp/cassandra/cases/max_concurrent_range_requests--empty-first-batch-full-page-fanout
C="bash $H/ring-ctl.sh"
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
log "ARM $L arm=$ARM heap1=$HEAP query=$QRY steps=$STEPS"
ok=0
for try in 1 2; do
  if $C start "$L" "$ARM" "$HEAP"; then ok=1; break; fi
  log "invalid start (try $try)"; $C stop "$L"; [ -d "$R" ] && { rm -rf "$R.badstart$try"; mv "$R" "$R.badstart$try"; }
done
[ $ok = 1 ] || { mkdir -p "$R"; echo "INVALID not-ready" > "$R/outcome"; exit 1; }
cp /mydata/s4/c10/runs/LOAD/{subranges.csv,T_hot} "$R"/ 2>/dev/null
sleep 30
if [ -n "$TRACE" ]; then
  for k in 1 2 3; do bash "$H/client.sh" "$L-tr$k" trace 127.0.0.1 test >> "$R/trace-test.txt" 2>&1; done
  bash "$H/client.sh" "$L-trM" trace 127.0.0.1 M >> "$R/trace-M.txt" 2>&1
  grep -h '^trace\|concurren\|Submitt\|Didn' "$R"/trace-*.txt | cut -c1-200
fi
$C drops "$L" before >/dev/null
$C read "$L" base | cut -c1-240
( cd "$R" && setsid nohup bash "$H/client.sh" "$L" run 127.0.0.1 8 "$STEPS" "$QRY" > client.csv 2> client.err < /dev/null & )
sleep 3; CP=$(pgrep -f "C10Load run 127.0.0.1 8 $STEPS $QRY" | head -1); echo "$CP" > "$R/client.pid"
log "client pid $CP"
t0=$(date +%s); dead=0; histd=0; lastd=0
while true; do
  sleep 10
  el=$(( $(date +%s) - t0 ))
  $C events "$L"
  if [ "$($C alive "$L" 1)" != ALIVE ]; then log "NODE 1 DEAD at +${el}s"; dead=1; break; fi
  for i in 2 3; do [ "$($C alive "$L" $i)" != ALIVE ] && log "WARNING replica n$i DEAD at +${el}s (invalid lifetime)"; done
  $C read "$L" "t+$el" | cut -c1-260
  tail -1 "$R/client.csv" | cut -c1-200
  if [[ $L =~ ^[LMI] ]] && [ $histd = 0 ] && [ $el -ge 120 ]; then $C hist "$L" t120; histd=1; fi
  if [ $(( el - lastd )) -ge 30 ]; then $C drops "$L" "t+$el" > /dev/null; lastd=$el; fi
  kill -0 "$CP" 2>/dev/null || break
done
for i in $(seq 1 40); do kill -0 "$CP" 2>/dev/null || break; sleep 1; done
kill "$CP" 2>/dev/null; sleep 1; kill -9 "$CP" 2>/dev/null
grep SUMMARY "$R/client.csv"; tail -3 "$R/client.err"
$C drops "$L" end > /dev/null
$C stop "$L"
# outcome
oomtype=$(grep -h -o -m1 "java\.lang\.OutOfMemoryError: [A-Za-z ]*" "$R/n1/logs/system.log" "$R/n1/stdout.log" 2>/dev/null | head -1)
lastQ=$(grep -E '^[0-9]{13},' "$R/client.csv" | tail -1 | cut -d, -f2)
if [ $dead = 1 ] && [ -n "$oomtype" ]; then
  ls_t=$(grep -E '^[0-9]{13},[0-9]' "$R/samples.csv" | awk -F, '$2>0' | tail -1 | cut -d, -f1)
  sc=$(awk -F, -v t="$ls_t" '/^[0-9]{13},/ && $1 >= t {print $2; exit}' "$R/client.csv")
  ntr=$(grep -E '^[0-9]{13},[0-9]' "$R/samples.csv" | awk -F, '$2>0' | tail -1 | cut -d, -f5)
  echo "OOM Q=$sc ntrActiveLast=$ntr type=\"$oomtype\" at+${el}s" > "$R/outcome"
elif [ $dead = 1 ]; then
  echo "DEAD-noOOM at+${el}s (scope events: $(cat $R/memory.events.last 2>/dev/null | tr '\n' ' '))" > "$R/outcome"
else
  echo "SURVIVED last_Q=$lastQ" > "$R/outcome"
fi
for i in 2 3; do grep -q "java\.lang\.OutOfMemoryError" "$R/n$i/logs/system.log" "$R/n$i/stdout.log" 2>/dev/null && echo "INVALID replica n$i OOM" >> "$R/outcome"; done
cat "$R/outcome"
D=$REPO/logs/$L; mkdir -p "$D"
cp "$R"/{readings.csv,samples.csv,run.meta,outcome,memory.events.last,netstats.txt,trace-test.txt,trace-M.txt} "$D"/ 2>/dev/null
cp "$R/n1/yaml.diff" "$D/n1.yaml.diff"; cp "$R/n1/env.diff" "$D/n1.env.diff"
grep -E '^(t,|[0-9]{13},|SUMMARY)' "$R/client.csv" > "$D/client.csv"
tail -20 "$R/client.err" > "$D/client.err.tail" 2>/dev/null; [ -s "$D/client.err.tail" ] || rm -f "$D/client.err.tail"
grep -h -m3 -B2 -A30 'java\.lang\.OutOfMemoryError' "$R/n1/logs/system.log" "$R/n1/stdout.log" 2>/dev/null | head -120 > "$D/oom-excerpt.txt"
[ -s "$D/oom-excerpt.txt" ] || rm -f "$D/oom-excerpt.txt"
for i in 2 3; do grep -h -i 'overloaded\|dropping message' "$R/n$i/logs/system.log" 2>/dev/null | tail -5 | cut -c1-300 | sed "s/^/n$i: /"; done > "$D/replica-drops.txt"
[ -s "$D/replica-drops.txt" ] || rm -f "$D/replica-drops.txt"
[ -f "$R/histo-t120.txt" ] && head -40 "$R/histo-t120.txt" > "$D/histo-t120-top.txt"
python3 "$H/gcwin.py" "$R/n1" > "$D/gcwin.txt"
python3 "$H/steps.py" "$D" > "$D/steps.txt" 2>&1
ls -la "$R/n1" | grep -i 'hprof\|hs_err' > "$D/hprof.ls" || rm -f "$D/hprof.ls"
log "END $L $(cat "$R/outcome")"
