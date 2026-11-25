#!/usr/bin/env bash
# U17 one clean lifetime on pc75 (victim + client on the same node, loopback). Adapted from U8's run-arm.sh.
#   run-arm.sh <label> <A|I> <heap> <VEC|HEX|WB> <N> <R> [D=6000000]
# Env: READBACK=1 (S0: readback after the load), DUMPFULL=1 (T1/W1: full dump histogram + stacks; else OOME thread only)
# 1 refuse if a CassandraDaemon runs; empty node dir; start; ready (one retry if not ready)
# 2 schema (client --ddl D), idle 30 s
# 3 client in the background (N connections, rounds released together, R rounds); alive check every 2 s, readings every
#   10 s, Thread.print count every 10 s; labels D1*: jcmd GC.class_histogram baseline before the client and back to back
#   while it runs; heaps > 2 GiB (B): one GC.class_histogram -all when heap used first exceeds 85 %
# 4 stop at client end, victim death or 600 s from the first request (watch rule: if the client gave up because every
#   connection failed while the victim is alive, keep watching to 600 s or death); outcome; stop a survivor
#   (drain + SIGTERM by PID); small files to out/<label>; hprof parsed (background, nice 19) then deleted
set -uo pipefail
L=$1 ARM=$2 HEAP=$3 PAY=$4 N=$5 RR=$6 D=${7:-6000000}
ROOT=/mydata/s4/u17; H=$ROOT/harness; R=$ROOT/runs/$L; O=$ROOT/out/$L
V="bash $H/victim-ctl.sh"
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
mib(){ local v=$1; case $v in *G) echo $(( ${v%G} * 1024 ));; *M) echo "${v%M}";; esac; }
HEAPB=$(( $(mib "$HEAP") * 1048576 ))
CLS='[B [C [Ljava.lang.Object; java.lang.String java.nio.HeapByteBuffer org.antlr.runtime.CommonToken org.apache.cassandra.cql3.Constants$Literal org.apache.cassandra.cql3.Constants$Value'
hsum(){ # jcmd histogram -> "class=instances/bytes;..." for the claimed classes + total (string match, no regex)
  awk -v cls="$CLS" 'BEGIN{n=split(cls,a," "); for(i=1;i<=n;i++) want[a[i]]=1} ($4 in want){printf "%s=%s/%s;", $4, $2, $3} $1=="Total"{printf "Total=%s/%s", $2, $3}' "$1"; }
log "ARM $L arm=$ARM heap=$HEAP payload=$PAY N=$N R=$RR D=$D"
ok=0
for try in 1 2; do
  $V start "$L" "$ARM" "$HEAP" auto || exit 1
  if $V ready "$L"; then ok=1; break; fi
  log "invalid start (try $try)"; $V stop "$L"; [ -d "$R" ] && mv "$R" "$R.badstart$try"
done
[ $ok = 1 ] || { echo "INVALID not-ready" > "$R/outcome"; exit 1; }
python3 -I "$H/u17client.py" --ddl "$D" > "$R/ddl.out" 2>&1; cat "$R/ddl.out"
grep -q "ddl ok" "$R/ddl.out" || echo "INVALID ddl" > "$R/outcome"
if [ ! -f "$R/outcome" ]; then
sleep 30
$V read "$L" base | cut -c1-240
if [[ $L == D1* ]]; then $V hist "$L" base; echo "hist,base,$(date +%s%3N),$(hsum "$R/histo-base.txt")" | tee -a "$R/histsum.csv"; fi
( cd "$R" && setsid nohup python3 -I "$H/u17client.py" --payload "$PAY" --d "$D" --n "$N" --rounds "$RR" --out "$R" > client.out 2> client.err < /dev/null & )
sleep 1; CP=$(pgrep -f "u17client.py --payload $PAY --d $D --n $N --rounds $RR --out $R" | head -1); echo "$CP" > "$R/client.pid"
log "client pid $CP"
t0=$(date +%s); dead=0; k=0; lastread=-10; lastthr=-10; big=0
while true; do
  el=$(( $(date +%s) - t0 ))
  if [ "$($V alive "$L")" != ALIVE ]; then log "VICTIM DEAD at +${el}s"; dead=1; break; fi
  if ! kill -0 "$CP" 2>/dev/null; then grep -q "down=true" "$R/client.csv" 2>/dev/null || break; [ -f "$R/watch.flag" ] || { log "client gave up (down=true); watching victim to 600 s"; touch "$R/watch.flag"; }; fi
  [ $el -ge 600 ] && { log "600 s stop"; break; }
  if [[ $L == D1* ]]; then
    k=$((k+1)); $V hist "$L" s$k; echo "hist,s$k,$(date +%s%3N),$(hsum "$R/histo-s$k.txt")" | tee -a "$R/histsum.csv" | cut -c1-200
  elif [ $(( el - lastthr )) -ge 10 ]; then $V threads "$L" "t+$el" > /dev/null; lastthr=$el; fi
  if [ $(( el - lastread )) -ge 10 ]; then $V read "$L" "t+$el" | cut -c1-200; lastread=$el; fi
  if [ "$HEAPB" -gt 2147483648 ] && [ $big = 0 ]; then
    hu=$(grep -v ERR "$R/samples.csv" 2>/dev/null | tail -1 | cut -d, -f2)
    if [ -n "$hu" ] && [ "$hu" -gt 0 ] 2>/dev/null && [ $(( hu * 100 / HEAPB )) -ge 85 ]; then
      big=1; log "heap used $hu >= 85 %: GC.class_histogram -all"; $V hist "$L" at85 -all
      echo "hist,at85,$(date +%s%3N),$(hsum "$R/histo-at85.txt")" | tee -a "$R/histsum.csv" | cut -c1-200
    fi
  fi
  if [[ $L == D1* ]]; then sleep 0.2; else sleep 2; fi
done
for i in $(seq 1 30); do kill -0 "$CP" 2>/dev/null || break; sleep 1; done
kill "$CP" 2>/dev/null; sleep 1; kill -9 "$CP" 2>/dev/null
grep SUMMARY "$R/client.csv"; tail -3 "$R/client.err"
if [ $dead = 0 ] && [ "$($V alive "$L")" = ALIVE ]; then
  sleep 3; $V read "$L" end | cut -c1-200
  [ "${READBACK:-0}" = 1 ] && { python3 -I "$H/u17client.py" --readback > "$R/readback.out" 2>&1; cat "$R/readback.out"; }
fi
fi
log "OOM/GC check"; $V oom "$L" > "$R/oom-check.txt" 2>&1; head -40 "$R/oom-check.txt"
$V stop "$L"
el=${el:-0}
oomtype=$(grep -h -o -m1 "java.lang.OutOfMemoryError: [A-Za-z ]*" "$R/logs/system.log" "$R/stdout.log" 2>/dev/null | head -1)
done_n=$(grep -cE '^[0-9]+,[0-9]+,[0-9]+,[0-9]+,[0-9]+,0x08,' "$R/client.csv" 2>/dev/null)
err_n=$(grep -cE '^[0-9]+,[0-9]+,[0-9]+,[0-9]+,[0-9]+,(0x00|io_error|connect_error),' "$R/client.csv" 2>/dev/null)
codes=$(grep -E '^[0-9]+,[0-9]+,' "$R/client.csv" 2>/dev/null | cut -d, -f6,7 | sort | uniq -c | tr '\n' ' ')
if [ -f "$R/outcome" ]; then :
elif [ $dead = 1 ] && [ -n "$oomtype" ]; then echo "OOM type=\"$oomtype\" at+${el}s completed=$done_n errors=$err_n codes=[$codes]" > "$R/outcome"
elif [ $dead = 1 ]; then echo "DEAD-noOOM at+${el}s completed=$done_n (scope: $(tr '\n' ' ' < $R/memory.events.last 2>/dev/null))" > "$R/outcome"
elif [ "${err_n:-0}" -gt 0 ]; then echo "ALIVE-noOOM (requests failed) completed=$done_n errors=$err_n codes=[$codes] wall=${el}s" > "$R/outcome"
else echo "SURVIVED completed=$done_n errors=$err_n codes=[$codes] wall=${el}s" > "$R/outcome"; fi
cat "$R/outcome"
mkdir -p "$O"; rm -f "$O"/*
cp "$R"/{readings.csv,samples.csv,yaml.diff,run.meta,outcome,oom-check.txt,ddl.out,histsum.csv,threads.csv,readback.out,client.csv} "$O"/ 2>/dev/null
cp "$R/memory.events.last" "$O/memory.events" 2>/dev/null
tail -20 "$R/client.err" > "$O/client.err.tail" 2>/dev/null; [ -s "$O/client.err.tail" ] || rm -f "$O/client.err.tail"
grep -h -m3 -B2 -A30 'java\.lang\.OutOfMemoryError' "$R/logs/system.log" "$R/stdout.log" 2>/dev/null | head -120 > "$O/oom-excerpt.txt"; [ -s "$O/oom-excerpt.txt" ] || rm -f "$O/oom-excerpt.txt"
grep -h 'transport.messages.QueryMessage ' "$R/classload.log" 2>/dev/null | head -3 > "$O/classload-querymessage.txt"
grep -h 'Pause' "$R"/gc.log* 2>/dev/null | grep -E 'ms$' | tail -40 > "$O/gc-pauses-tail.txt"
grep -h -E 'Pause (Full|Young|Remark).*ms$' "$R"/gc.log* 2>/dev/null | sed -n 's/.*->\([0-9]*\)M(\([0-9]*\)M).*/\1 \2/p' | sort -n | tail -1 > "$O/gc-max-after.txt"
python3 "$H/gcwin.py" "$R" > "$O/gcwin.txt" 2>&1
grep -i -m8 'exception\|error\|too big\|Dropped\|timeout' "$R/logs/system.log" 2>/dev/null | grep -v 'OutOfMemory' | cut -c1-400 > "$O/system-errors.txt"; [ -s "$O/system-errors.txt" ] || rm -f "$O/system-errors.txt"
ls -la "$R" | grep -i 'hprof\|hs_err' > "$O/hprof.ls" || rm -f "$O/hprof.ls"
HP=$(ls "$R"/*.hprof 2>/dev/null | head -1)
if [ -n "$HP" ]; then
  if [ "${DUMPFULL:-0}" = 1 ]; then
    ( setsid nohup nice -n 19 bash -c "python3 -I $H/hprof_oome_thread.py $HP 40 > $O/dump-oome-thread.txt 2>&1; python3 -I $H/hprofstacks.py $HP Cql_Parser > $O/dump-stacks-parser.txt 2>&1; python3 -I $H/hprofstacks.py $HP Vectors > $O/dump-stacks-vectors.txt 2>&1; python3 -I $H/hprof-histo.py $HP --len-range 1 1 --top 30 > $O/dump-histo.txt 2>&1; rm -f $HP; echo done > $O/dump.done" < /dev/null > /dev/null 2>&1 & )
    log "full dump parse started in the background"
  else
    nice -n 19 python3 -I "$H/hprof_oome_thread.py" "$HP" 40 > "$O/dump-oome-thread.txt" 2>&1
    python3 -I "$H/hprofstacks.py" "$HP" Cql_Parser > "$O/dump-stacks-parser.txt" 2>&1
    rm -f "$HP"; echo done > "$O/dump.done"; head -25 "$O/dump-oome-thread.txt"
  fi
fi
rm -rf "$ROOT/node"
log "END $L $(cat "$R/outcome")"
