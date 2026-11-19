#!/usr/bin/env bash
# U9 one lifetime (pc91): run-arm.sh <label> <arm T|C|I|S|M|B> <heap> <direct> <R>
#   T, S: 1 table of R large-key rows, load L, major compaction      C: same with small-key rows (matched control)
#   I: as T with column_index_size: 4MiB                             M: 2 tables (t1, t2), load L each, both compactions within 1 s
#   B: 1 table, autocompaction on, no manual flush/compaction (load BG), wait <= 600 s after the last write
# Load L: disableautocompaction; chunks of 1,000 rows, nodetool flush after each; first-trigger check after the first flush.
# Endpoint: first OutOfMemoryError in stdout.log/system.log -> wait for a stable hprof (10 s, <= 300 s) -> kill by PID.
set -uo pipefail
L=$1 ARM=$2 HEAP=$3 DIRECT=$4 R=$5
ROOT=/mydata/s4/u9-w4; H=$ROOT/harness; RD=$ROOT/runs/$L; BUILD=$ROOT/tree
export CASSANDRA_HOME=$BUILD
NT="$BUILD/bin/nodetool -h 127.0.0.1"
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*" | tee -a "$RD/run.log"; }
res(){ echo "$*" >> "$RD/result.txt"; }
KIND=big; [ "$ARM" = C ] && KIND=small
TABLES=t1; [ "$ARM" = M ] && TABLES="t1 t2"

"$H/victim-ctl.sh" start "$L" "$ARM" "$HEAP" "$DIRECT" || exit 1
: > "$RD/run.log"; : > "$RD/result.txt"
res "label=$L arm=$ARM heap=$HEAP direct=$DIRECT R=$R tables=$TABLES kind=$KIND"
"$H/victim-ctl.sh" ready "$L" | tee -a "$RD/run.log" || { res "outcome=START_FAILED"; "$H/victim-ctl.sh" stop "$L"; exit 1; }
P=$(cat "$RD/cass.pid")

# samplers (2 s): jcmd GC.heap_info + RssAnon; nodetool compactionstats
touch "$RD/sampler.run"
( setsid nohup bash -c "while [ -f '$RD/sampler.run' ] && kill -0 $P 2>/dev/null; do
    t=\$(date +%s.%N); h=\$(timeout 10 jcmd $P GC.heap_info 2>/dev/null | grep -m1 -E 'garbage-first heap' | tr -s ' ');
    ra=\$(awk '/RssAnon/{print \$2}' /proc/$P/status 2>/dev/null);
    echo \"\$t|\$h|rssAnonKB=\$ra\" >> '$RD/heap.csv'; sleep 2; done" < /dev/null > /dev/null 2>&1 & echo $! > "$RD/sampler1.pid" )
( setsid nohup bash -c "while [ -f '$RD/sampler.run' ] && kill -0 $P 2>/dev/null; do
    echo \"=== \$(date +%s.%N)\" >> '$RD/cstats.log'; timeout 15 $NT compactionstats >> '$RD/cstats.log' 2>&1; sleep 2; done" < /dev/null > /dev/null 2>&1 & echo $! > "$RD/sampler2.pid" )

DATA=$ROOT/node/data/ks
sizes(){ # <table> -> "data index count"
  local d; d=$(ls -d "$DATA/$1"-* 2>/dev/null | head -1)
  find "$d" -maxdepth 1 -name '*-Data.db' -printf '%s\n' 2>/dev/null | awk '{s+=$1;n++} END{printf "%d ", s+0}'
  find "$d" -maxdepth 1 -name '*-Index.db' -printf '%s\n' 2>/dev/null | awk '{s+=$1;n++} END{printf "%d %d\n", s+0, n+0}'
}
alive(){ kill -0 "$P" 2>/dev/null; }
oomseen(){ grep -qF "java.lang.OutOfMemoryError" "$RD/stdout.log" "$RD/logs/system.log" 2>/dev/null; }

for t in $TABLES; do
  python3 "$H/writer.py" schema "$t" >> "$RD/load.log" 2>&1 || { res "outcome=SCHEMA_FAILED"; }
  [ "$ARM" != B ] && $NT disableautocompaction ks "$t"
done
log "schema done: $TABLES"

FT=ok; LOADFAIL=""
for t in $TABLES; do
  seed=1; [ "$t" = t2 ] && seed=2
  c=0
  while [ $((c*1000)) -lt "$R" ]; do
    a=$((c*1000)); b=$(( (c+1)*1000 )); [ $b -gt "$R" ] && b=$R
    python3 "$H/writer.py" write "$t" "$KIND" $a $b $seed >> "$RD/load.log" 2>&1
    alive || { LOADFAIL="jvm dead during load of $t at row $b"; break 2; }
    oomseen && { LOADFAIL="OOM during load of $t at row $b"; break 2; }
    if [ "$ARM" != B ]; then
      timeout 300 $NT flush ks "$t" >> "$RD/load.log" 2>&1
      if [ $c -eq 0 ]; then
        read -r dsz isz n <<< "$(sizes "$t")"
        ratio=$(python3 -c "print(round($isz/$dsz,4) if $dsz else -1)")
        res "first_trigger_$t: Data=$dsz Index=$isz sstables=$n ratio=$ratio"
        case $ARM in
          C) python3 -c "import sys; sys.exit(0 if 0<=$ratio<=0.01 else 1)" || FT=fail;;
          I) python3 -c "import sys; sys.exit(0 if 0<=$ratio<=0.05 else 1)" || FT=fail;;
          *) python3 -c "import sys; sys.exit(0 if 1.85<=$ratio<=2.15 else 1)" || FT=fail;;
        esac
        [ $FT = fail ] && { log "FIRST-TRIGGER CHECK FAILED ratio=$ratio"; break 2; }
      fi
    fi
    c=$((c+1))
  done
  log "loaded $t: $(sizes "$t")"
  res "loaded_$t: $(sizes "$t")"
done
res "load_errors=$(python3 -c "import json,sys; print(sum(json.loads(l).get('errors',0) for l in open('$RD/load.log') if l.startswith('{\"table')))")"

OUT=""
if [ -n "$LOADFAIL" ]; then
  log "$LOADFAIL"; res "load_endpoint=$LOADFAIL"
  oomseen && OUT=OOM_DURING_LOAD || OUT=DIED_DURING_LOAD
elif [ $FT = fail ]; then
  OUT=FIRST_TRIGGER_FAIL
fi

if [ -z "$OUT" ]; then
  timeout 30 jcmd "$P" GC.heap_info > "$RD/baseline.txt" 2>&1
  grep "Pause" "$RD"/logs/gc.log 2>/dev/null | tail -1 >> "$RD/baseline.txt"
  for t in $TABLES; do ls -l "$(ls -d "$DATA/$t"-* | head -1)" > "$RD/listing-pre-$t.txt"; done
  T0=$(date +%s)
  if [ "$ARM" != B ]; then
    for t in $TABLES; do
      ( setsid nohup bash -c "timeout 600 $NT compact ks $t > '$RD/compact-$t.out' 2>&1; echo \$? > '$RD/compact-$t.rc'" < /dev/null > /dev/null 2>&1 & )
    done
    log "nodetool compact started: $TABLES"
  else
    log "BG: last write done; waiting <= 600 s for the endpoint or idle compaction"
  fi
  while :; do
    sleep 2
    if oomseen; then OUT=OOM; break; fi
    if ! alive; then OUT=DIED; break; fi
    if [ "$ARM" != B ]; then
      done_all=1; for t in $TABLES; do [ -f "$RD/compact-$t.rc" ] || done_all=0; done
      [ $done_all = 1 ] && { OUT=COMPLETED; break; }
    else
      if [ $(( $(date +%s) - T0 )) -ge 20 ]; then
        cs=$(timeout 15 $NT compactionstats 2>/dev/null)
        echo "$cs" | grep -q "^pending tasks: 0" && ! echo "$cs" | grep -qE "Compaction|COMPACTION" && { OUT=COMPLETED_IDLE; break; }
      fi
    fi
    [ $(( $(date +%s) - T0 )) -ge 600 ] && { OUT=TIMEOUT; break; }
  done
  res "endpoint_seconds=$(( $(date +%s) - T0 ))"
fi
log "outcome $OUT"; res "outcome=$OUT"

case $OUT in
  OOM|OOM_DURING_LOAD)
    grep -n -m1 -F "java.lang.OutOfMemoryError" "$RD/stdout.log" "$RD/logs/system.log" 2>/dev/null | head -2 | sed 's/^/first_oom: /' >> "$RD/result.txt"
    for i in $(seq 1 150); do alive || break; sleep 2; done   # dump, then the shipped OnOutOfMemoryError kill -9
    if alive; then kill "$P"; for i in $(seq 1 30); do alive || break; sleep 1; done; alive && kill -9 "$P"; fi
    ;;
  COMPLETED|COMPLETED_IDLE)
    sleep 8   # obsolete input sstables are deleted asynchronously after the transaction commits
    for t in $TABLES; do ls -l "$(ls -d "$DATA/$t"-* | head -1)" > "$RD/listing-post-$t.txt"; res "post_$t: $(sizes "$t")"; done
    timeout 120 jcmd "$P" GC.class_histogram > "$RD/histo-post.txt" 2>&1
    "$H/victim-ctl.sh" stop "$L" >> "$RD/run.log"
    ;;
  *)
    "$H/victim-ctl.sh" stop "$L" >> "$RD/run.log"
    ;;
esac
alive && kill -9 "$P"
rm -f "$RD/sampler.run"; sleep 3
for f in sampler1 sampler2; do kill "$(cat "$RD/$f.pid" 2>/dev/null)" 2>/dev/null; done
for t in $TABLES; do [ -f "$RD/compact-$t.rc" ] && res "compact_rc_$t=$(cat "$RD/compact-$t.rc")"; done
pkill -f "nodetool.*compact ks" 2>/dev/null

# analysis (after the JVM is gone)
hp=$(ls "$RD"/*.hprof 2>/dev/null | head -1)
if [ -n "$hp" ]; then
  res "hprof=$hp size=$(stat -c %s "$hp")"
  python3 "$H/hprofhist.py" "$hp" 30 > "$RD/hprofhist.txt" 2>&1
  python3 "$H/hprofstacks.py" "$hp" DataOutputBuffer > "$RD/hprofstacks.txt" 2>&1
  case $L in *-1) ;; *) rm -f "$hp"; res "hprof deleted after analysis (only run 1 of an arm is kept)";; esac
fi
python3 "$H/gcwin.py" "$RD/logs" > "$RD/gcwin.txt" 2>&1
python3 "$H/summarize.py" "$RD" > "$RD/summary.txt" 2>&1
du -sh "$ROOT/node" >> "$RD/run.log" 2>&1
rm -rf "$ROOT/node"
log "done $L"
