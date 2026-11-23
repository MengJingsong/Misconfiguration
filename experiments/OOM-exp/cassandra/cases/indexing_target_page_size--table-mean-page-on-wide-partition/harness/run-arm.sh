#!/usr/bin/env bash
# B20 one lifetime (ms0640, design §2.5 "Lifetime"): run-arm.sh <label> <T|C|I|SHAKE> <heap> <direct> [nodump]
#   T: pristine-T, unmodified      C: pristine-C, SecondaryIndexManager TRACE after startup      SHAKE: as C (harness check)
#   I: pristine-T + Byteman rule harness/b20-intervention.btm (trace file <run>/btm.txt)
#   nodump: add -XX:-HeapDumpOnOutOfMemoryError (budget-search lifetimes after the first at a heap)
# Trigger: CREATE INDEX t_ck ON ks.t (ck). Endpoint: first java.lang.OutOfMemoryError in stdout.log/system.log, JVM exit,
# or 'Index build of t_ck complete'; limit 8 min after the trigger. On OOM: wait for a stable hprof (10 s, <= 300 s).
set -uo pipefail
L=$1 ARM=$2 HEAP=$3 DIRECT=$4 OPT=${5:-}
ROOT=/mydata/s4/b20; H=$ROOT/harness; RD=$ROOT/runs/$L; BUILD=$ROOT/tree
export CASSANDRA_HOME=$BUILD
NT="$BUILD/bin/nodetool -h 127.0.0.1"
case $ARM in T|I) SET=T;; C|SHAKE) SET=C;; *) echo "bad arm"; exit 2;; esac
EXTRA=""
mkdir -p "$ROOT/btm"
[ "$ARM" = I ] && { sed "s|<run dir>|$RD|" "$H/b20-intervention.btm" > "$ROOT/btm/$L.btm"; EXTRA="-javaagent:$BUILD/build/lib/jars/byteman-4.0.20.jar=script:$ROOT/btm/$L.btm"; }
[ "$OPT" = nodump ] && EXTRA="$EXTRA -XX:-HeapDumpOnOutOfMemoryError"

rm -rf "$ROOT/work"; bash "$H/clone.sh" "$ROOT/pristine-$SET" "$ROOT/work" > /tmp/b20-clone.out 2>&1 || { cat /tmp/b20-clone.out; exit 1; }
bash "$H/victim-ctl.sh" start "$L" "$HEAP" "$DIRECT" "$EXTRA" || exit 1
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*" | tee -a "$RD/run.log"; }
res(){ echo "$*" >> "$RD/result.txt"; }
: > "$RD/run.log"; : > "$RD/result.txt"
cat /tmp/b20-clone.out >> "$RD/run.log"
[ "$ARM" = I ] && cp "$ROOT/btm/$L.btm" "$RD/"
res "label=$L arm=$ARM set=$SET heap=$HEAP direct=$DIRECT opt=$OPT"
bash "$H/victim-ctl.sh" ready "$L" | tee -a "$RD/run.log" || { res "outcome=START_FAILED"; bash "$H/victim-ctl.sh" stop "$L"; exit 1; }
P=$(cat "$RD/cass.pid")
alive(){ kill -0 "$P" 2>/dev/null; }
oomseen(){ grep -qF "java.lang.OutOfMemoryError" "$RD/stdout.log" "$RD/logs/system.log" 2>/dev/null; }
donestr(){ grep -q "Index build of t_ck complete" "$RD/logs/system.log" 2>/dev/null; }

# no compaction may overlap the build
timeout 60 $NT compactionstats > "$RD/cstats-pre.txt" 2>&1
res "pre_compactionstats: $(head -1 "$RD/cstats-pre.txt") active=$(grep -cE 'ks +t ' "$RD/cstats-pre.txt")"
ls -l "$ROOT"/work/data/ks/t-*/ > "$RD/listing-pre.txt" 2>&1

# samplers: jcmd GC.heap_info + RssAnon every 2 s; nodetool compactionstats every 3 s
touch "$RD/sampler.run"
( setsid nohup bash -c "while [ -f '$RD/sampler.run' ] && kill -0 $P 2>/dev/null; do
    t=\$(date +%s.%N); h=\$(timeout 10 jcmd $P GC.heap_info 2>/dev/null | grep -m1 -E 'garbage-first heap' | tr -s ' ');
    ra=\$(awk '/RssAnon/{print \$2}' /proc/$P/status 2>/dev/null);
    echo \"\$t|\$h|rssAnonKB=\$ra\" >> '$RD/heap.csv'; sleep 2; done" < /dev/null > /dev/null 2>&1 & echo $! > "$RD/sampler1.pid" )
( setsid nohup bash -c "while [ -f '$RD/sampler.run' ] && kill -0 $P 2>/dev/null; do
    echo \"=== \$(date +%s.%N)\" >> '$RD/cstats.log'; timeout 15 $NT compactionstats >> '$RD/cstats.log' 2>&1; sleep 3; done" < /dev/null > /dev/null 2>&1 & echo $! > "$RD/sampler2.pid" )

sleep 30
timeout 60 jcmd "$P" GC.heap_info > "$RD/baseline.txt" 2>&1
timeout 120 jcmd "$P" GC.class_histogram > "$RD/histo-pre.txt" 2>&1
res "baseline_histo_total: $(tail -1 "$RD/histo-pre.txt")"
if [ "$ARM" = C ] || [ "$ARM" = SHAKE ]; then
  timeout 60 $NT setlogginglevel org.apache.cassandra.index.SecondaryIndexManager TRACE
  log "TRACE set for SecondaryIndexManager"
fi
T0=$(date +%s.%N)
log "trigger: CREATE INDEX t_ck ON ks.t (ck)"
( timeout 120 "$BUILD/bin/cqlsh" --protocol-version=4 --request-timeout=60 127.0.0.1 -e "CREATE INDEX t_ck ON ks.t (ck)" > "$RD/trigger.out" 2>&1; echo "rc=$?" >> "$RD/trigger.out" ) &
OUT=""
while :; do
  sleep 2
  if oomseen; then OUT=OOM; break; fi
  if ! alive; then OUT=DIED; break; fi
  if donestr; then OUT=COMPLETED; break; fi
  python3 -c "import sys,time; sys.exit(0 if time.time()-$T0 >= 480 else 1)" && { OUT=TIMEOUT; break; }
done
TE=$(date +%s.%N)
res "trigger_epoch=$T0"
res "endpoint_seconds=$(python3 -c "print(round($TE-$T0,1))")"
log "outcome $OUT"; res "outcome=$OUT"
wait 2>/dev/null
res "trigger: $(tr '\n' ' ' < "$RD/trigger.out" | cut -c1-300)"

case $OUT in
  OOM)
    grep -n -m1 -F "java.lang.OutOfMemoryError" "$RD/stdout.log" "$RD/logs/system.log" 2>/dev/null | head -2 | sed 's/^/first_oom: /' >> "$RD/result.txt"
    # dump (if on), then the shipped OnOutOfMemoryError kill -9; then a stable hprof
    last=-1; stable=0
    for i in $(seq 1 150); do
      hp=$(ls "$RD"/*.hprof 2>/dev/null | head -1); sz=$( [ -n "$hp" ] && stat -c %s "$hp" || echo 0)
      if [ "$sz" = "$last" ]; then stable=$((stable+2)); else stable=0; fi; last=$sz
      if ! alive && [ $stable -ge 10 ]; then break; fi
      sleep 2
    done
    if alive; then kill "$P"; for i in $(seq 1 30); do alive || break; sleep 1; done; alive && kill -9 "$P"; fi
    ;;
  COMPLETED)
    sleep 10
    timeout 60 jcmd "$P" GC.heap_info > "$RD/heap-post.txt" 2>&1
    python3 "$H/writer.py" cql "SELECT count(*) FROM ks.t WHERE ck = 1" 120 > "$RD/useful.txt" 2>&1
    res "useful_ck1: $(tail -1 "$RD/useful.txt" | cut -c1-200)"
    bash "$H/victim-ctl.sh" stop "$L" >> "$RD/run.log"
    ;;
  *)
    bash "$H/victim-ctl.sh" stop "$L" >> "$RD/run.log"
    ;;
esac
alive && kill -9 "$P"
rm -f "$RD/sampler.run"; sleep 3
for f in sampler1 sampler2; do kill "$(cat "$RD/$f.pid" 2>/dev/null)" 2>/dev/null; done
grep -h "Calculated page size" "$RD"/logs/debug.log* 2>/dev/null | head -3 | sed 's/^/trace: /' >> "$RD/result.txt"
[ -f "$RD/btm.txt" ] && sed 's/^/btm: /' "$RD/btm.txt" | head -5 >> "$RD/result.txt"
grep -h -E "Submitting index build of t_ck|Index build of t_ck complete|became queryable|failed build" "$RD/logs/system.log" | cut -c1-260 | sed 's/^/syslog: /' >> "$RD/result.txt"

# analysis (after the JVM is gone)
hp=$(ls "$RD"/*.hprof 2>/dev/null | head -1)
if [ -n "$hp" ]; then
  res "hprof=$hp size=$(stat -c %s "$hp")"
  python3 "$H/hprofhist.py" "$hp" 30 > "$RD/hprofhist.txt" 2>&1
  python3 "$H/hprofstacks.py" "$hp" SecondaryIndexManager > "$RD/hprofstacks.txt" 2>&1
  rm -f "$hp"; res "hprof deleted after analysis"
fi
python3 "$H/gcwin.py" "$RD/logs" > "$RD/gcwin.txt" 2>&1
python3 "$H/summarize.py" "$RD" > "$RD/summary.txt" 2>&1
du -sh "$ROOT/work" >> "$RD/run.log" 2>&1
rm -rf "$ROOT/work"
log "done $L"
