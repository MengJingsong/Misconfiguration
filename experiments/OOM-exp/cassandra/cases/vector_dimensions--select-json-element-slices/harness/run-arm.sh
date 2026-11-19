#!/usr/bin/env bash
# U8 one clean lifetime on ms0640 (victim + client on the same node, loopback).
#   run-arm.sh <label> <A|I> <heap> <json|plain> <N> <R>
# 1 refuse if a CassandraDaemon runs; empty node dir; start; ready (one retry if not ready)
# 2 load: schema + one vector<boolean, 16000000> row (pk 0), nodetool flush u8, verify the stored length, idle 30 s
# 3 client run in the background (N connections, barrier per round, R rounds); alive check every 2 s, readings every
#   10 s; labels D1*: jcmd GC.class_histogram baseline before the client and every 2 s while it runs (U of the list)
# 4 stop at client end, victim death or 600 s; outcome; stop a survivor (drain + SIGTERM by PID); small files to out/<label>
set -uo pipefail
L=$1 ARM=$2 HEAP=$3 MODE=$4 N=$5 RR=$6
D=16000000
ROOT=/mydata/s4/u8-w4; H=$ROOT/harness; R=$ROOT/runs/$L; O=$ROOT/out/$L
J=$ROOT/tree/build/lib/jars
CCP="$ROOT/cls:$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$ROOT/tree/lib/*"
V="bash $H/victim-ctl.sh"
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
hsum(){ # histogram file -> one line: HeapByteBuffer instances,bytes ; Object[] bytes ; byte[] bytes ; total
  # jcmd lines: "num: instances bytes class (module)"
  awk '$4=="java.nio.HeapByteBuffer"{hb=$2; hbb=$3} $4=="[Ljava.lang.Object;"{ob=$3} $4=="[B"{bb=$3} $1=="Total"{tot=$3} END{print "hbb_n="hb",hbb_B="hbb",objarr_B="ob",bytearr_B="bb",total_B="tot}' "$1"; }
log "ARM $L arm=$ARM heap=$HEAP mode=$MODE N=$N R=$RR D=$D"
ok=0
for try in 1 2; do
  $V start "$L" "$ARM" "$HEAP" auto || exit 1
  if $V ready "$L"; then ok=1; break; fi
  log "invalid start (try $try)"; $V stop "$L"; [ -d "$R" ] && mv "$R" "$R.badstart$try"
done
[ $ok = 1 ] || { echo "INVALID not-ready" > "$R/outcome"; exit 1; }
java -Xmx1g -cp "$CCP" U8Client load 127.0.0.1 $D > "$R/load.out" 2>&1; tail -2 "$R/load.out"
timeout 300 $ROOT/tree/bin/nodetool -h 127.0.0.1 flush u8 >> "$R/load.out" 2>&1; log "flushed"
java -Xmx1g -cp "$CCP" U8Client verify 127.0.0.1 >> "$R/load.out" 2>&1; tail -1 "$R/load.out"
grep -q "verify len=$D" "$R/load.out" || { log "verify failed"; echo "INVALID load/verify" > "$R/outcome"; }
if [ ! -f "$R/outcome" ]; then
sleep 30
$V read "$L" base | cut -c1-240
if [[ $L == D1* ]]; then $V hist "$L" base; hsum "$R/histo-base.txt" | sed 's/^/hist,base,/' | tee -a "$R/histsum.csv"; fi
( cd "$R" && setsid nohup java -Xmx8g -XX:MaxDirectMemorySize=8g -cp "$CCP" U8Client run 127.0.0.1 "$MODE" "$N" "$RR" > client.csv 2> client.err < /dev/null & )
sleep 1; CP=$(pgrep -f "U8Client run 127.0.0.1 $MODE $N $RR" | head -1); echo "$CP" > "$R/client.pid"
log "client pid $CP"
t0=$(date +%s); dead=0; k=0; lastread=0
while true; do
  el=$(( $(date +%s) - t0 ))
  if [ "$($V alive "$L")" != ALIVE ]; then log "VICTIM DEAD at +${el}s"; dead=1; break; fi
  # amended 2026-11-18 15:10 EST: if the client gave up because its connections failed (SUMMARY down=true) while the
  # victim is alive, keep watching the victim until the frozen per-run budget (600 s from the first request) or death:
  # the server keeps rendering the requests it already accepted.
  if ! kill -0 "$CP" 2>/dev/null; then grep -q "down=true" "$R/client.csv" 2>/dev/null || break; [ -f "$R/watch.flag" ] || { log "client gave up (down=true); watching victim to 600 s"; touch "$R/watch.flag"; }; fi
  [ $el -ge 600 ] && { log "600 s stop"; break; }
  if [[ $L == D1* ]]; then
    k=$((k+1)); $V hist "$L" s$k; echo "hist,$(date +%s%3N),s$k,$(hsum "$R/histo-s$k.txt")" | tee -a "$R/histsum.csv"; rm -f "$R/histo-s$k.txt"
  fi
  if [ $(( el - lastread )) -ge 10 ]; then $V read "$L" "t+$el" | cut -c1-240; lastread=$el; fi
  if [[ $L == D1* ]]; then sleep 0.5; else sleep 2; fi   # D1: a histogram takes ~1.5 s itself, so samples are ~2 s apart
done
for i in $(seq 1 30); do kill -0 "$CP" 2>/dev/null || break; sleep 1; done
kill "$CP" 2>/dev/null; sleep 1; kill -9 "$CP" 2>/dev/null
grep SUMMARY "$R/client.csv"; tail -3 "$R/client.err"
if [ $dead = 0 ] && [ "$($V alive "$L")" = ALIVE ]; then sleep 3; $V read "$L" end | cut -c1-240; fi
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
elif [ "${err_n:-0}" -gt 0 ]; then echo "ALIVE-noOOM (requests failed) completed=$done_n errors=$err_n lens=[$lens] wall=${el}s" > "$R/outcome"   # label added 2026-11-18 14:52 EST
else echo "SURVIVED completed=$done_n errors=$err_n lens=[$lens] wall=${el}s" > "$R/outcome"; fi
cat "$R/outcome"
mkdir -p "$O"; rm -f "$O"/*
cp "$R"/{readings.csv,samples.csv,yaml.diff,run.meta,outcome,oom-check.txt,load.out,histsum.csv} "$O"/ 2>/dev/null
cp "$R/memory.events.last" "$O/memory.events" 2>/dev/null
grep -E '^(start_ms|[0-9]{13},|SUMMARY)' "$R/client.csv" > "$O/client.csv" 2>/dev/null
tail -20 "$R/client.err" > "$O/client.err.tail" 2>/dev/null; [ -s "$O/client.err.tail" ] || rm -f "$O/client.err.tail"
grep -h -m3 -B2 -A30 'java\.lang\.OutOfMemoryError' "$R/logs/system.log" "$R/stdout.log" 2>/dev/null | head -120 > "$O/oom-excerpt.txt"; [ -s "$O/oom-excerpt.txt" ] || rm -f "$O/oom-excerpt.txt"
grep -h 'VectorType' "$R/classload.log" 2>/dev/null | head -10 > "$O/classload-vectortype.txt"
grep -h 'Pause' "$R"/gc.log* 2>/dev/null | grep -E 'ms$' | tail -40 > "$O/gc-pauses-tail.txt"
grep -h -E 'Pause (Full|Young).*ms$' "$R"/gc.log* 2>/dev/null | sed -n 's/.*->\([0-9]*\)M(\([0-9]*\)M).*/\1 \2/p' | sort -n | tail -1 > "$O/gc-max-after.txt"
python3 "$H/gcwin.py" "$R" > "$O/gcwin.txt" 2>&1
grep -i -m5 'exception\|error' "$R/logs/system.log" 2>/dev/null | grep -v 'OutOfMemory' | cut -c1-400 > "$O/system-errors.txt"; [ -s "$O/system-errors.txt" ] || rm -f "$O/system-errors.txt"
ls -la "$R" | grep -i 'hprof\|hs_err' > "$O/hprof.ls" || rm -f "$O/hprof.ls"
log "END $L $(cat "$R/outcome")"
