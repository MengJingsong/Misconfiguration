#!/usr/bin/env bash
# U9 stage 3-b confirm, one run (pc99): run3b.sh <label> <heap> <direct> <R>
# Stage-2 arm B (load BG: everything default, autocompaction on, no manual flush/compaction, no nodetool step) with
# authentication on. Phases:
#   1 fresh node (PasswordAuthenticator + CassandraAuthorizer + CassandraRoleManager), ready
#   2 superuser: ks.t1 (stage-2 schema), vks.vt, roles u9atk (MODIFY ON TABLE ks.t1 only) and u9vic (SELECT+MODIFY ON KEYSPACE vks)
#   3 privcheck as u9atk; samplers; victim (u9vic, 20 ops/s) for 30 s before the attack
#   4 attack as u9atk: R rows of 65,535-B clustering keys into ks.t1 pk=1, chunks of 1,000 (stage-2 writer), CL ONE
#   5 endpoint: first java.lang.OutOfMemoryError (watcher, 1 s) -> dump -> shipped kill -9; or <= 600 s after the last write
#   6 after an OOM: 60 s down, then one restart on the same data (operator's routine restart; label <label>-R),
#     watched <= 600 s for a second OOM (crash loop) or idle compaction; the victim keeps running throughout
#   7 victim stopped; dumps scanned (hprofhist/hprofstacks) and deleted; summaries
set -uo pipefail
L=$1 HEAP=$2 DIRECT=$3 R=$4
ROOT=/mydata/s4/3b-U9; H=$ROOT/harness; RD=$ROOT/runs/$L; BUILD=$ROOT/tree
export CASSANDRA_HOME=$BUILD
NT="$BUILD/bin/nodetool -h 127.0.0.1"
ms(){ date +%s%3N; }
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*" | tee -a "$RD/run.log"; }
ev(){ echo "$(ms) $*" >> "$RD/events.txt"; log "EVENT $*"; }
res(){ echo "$*" >> "$RD/result.txt"; }
DATA=$ROOT/node/data/ks

"$H/victim-ctl.sh" start "$L" "$HEAP" "$DIRECT" fresh || exit 1
: > "$RD/run.log"; : > "$RD/result.txt"; : > "$RD/events.txt"
res "label=$L arm=B-auth heap=$HEAP direct=$DIRECT R=$R tables=t1 kind=big attacker=u9atk"
ev node_start
"$H/victim-ctl.sh" ready "$L" | tee -a "$RD/run.log" || { res "outcome=START_FAILED"; "$H/victim-ctl.sh" stop "$L"; exit 1; }
ev node_ready
P=$(cat "$RD/cass.pid")

python3 "$H/writer.py" admin > "$RD/admin.log" 2>&1 || { res "outcome=ADMIN_FAILED"; "$H/victim-ctl.sh" stop "$L"; exit 1; }
python3 "$H/writer.py" privcheck > "$RD/privcheck.log" 2>&1
log "admin + privcheck done"

samplers(){ # <run dir> <pid>
  local D=$1 Q=$2
  touch "$D/sampler.run"
  ( setsid nohup bash -c "while [ -f '$D/sampler.run' ] && kill -0 $Q 2>/dev/null; do
      t=\$(date +%s.%N); h=\$(timeout 10 jcmd $Q GC.heap_info 2>/dev/null | grep -m1 -E 'garbage-first heap' | tr -s ' ');
      ra=\$(awk '/RssAnon/{print \$2}' /proc/$Q/status 2>/dev/null);
      echo \"\$t|\$h|rssAnonKB=\$ra\" >> '$D/heap.csv'; sleep 2; done" < /dev/null > /dev/null 2>&1 & echo $! > "$D/sampler1.pid" )
  ( setsid nohup bash -c "while [ -f '$D/sampler.run' ] && kill -0 $Q 2>/dev/null; do
      echo \"=== \$(date +%s.%N)\" >> '$D/cstats.log'; timeout 15 $NT compactionstats >> '$D/cstats.log' 2>&1; sleep 2; done" < /dev/null > /dev/null 2>&1 & echo $! > "$D/sampler2.pid" )
  ( setsid nohup bash -c "while [ -f '$D/sampler.run' ] && kill -0 $Q 2>/dev/null; do
      echo \"=== \$(date +%s.%N) \$(find $DATA -maxdepth 2 -name '*-Data.db' -printf '%f:%s ' 2>/dev/null) | \$(find $DATA -maxdepth 2 -name '*-Index.db' -printf '%f:%s ' 2>/dev/null)\" >> '$D/sst.log'; sleep 5; done" < /dev/null > /dev/null 2>&1 & echo $! > "$D/sampler3.pid" )
}
stop_samplers(){ local D=$1 f; rm -f "$D/sampler.run"; sleep 3; for f in sampler1 sampler2 sampler3; do kill "$(cat "$D/$f.pid" 2>/dev/null)" 2>/dev/null; done; }
# endpoint watcher: records the first OOM line and the JVM's death (1 s polling)
watcher(){ # <run dir> <pid> <tag>
  local D=$1 Q=$2 T=$3
  ( setsid nohup bash -c "o=0; while kill -0 $Q 2>/dev/null; do
      if [ \$o = 0 ] && grep -qF java.lang.OutOfMemoryError '$D/stdout.log' '$D/logs/system.log' 2>/dev/null; then echo \"\$(date +%s%3N) oom_seen$T\" >> '$RD/events.txt'; o=1; fi
      sleep 1; done; echo \"\$(date +%s%3N) jvm_dead$T\" >> '$RD/events.txt'" < /dev/null > /dev/null 2>&1 & echo $! > "$D/watcher.pid" )
}
oomseen(){ grep -qF "java.lang.OutOfMemoryError" "$1/stdout.log" "$1/logs/system.log" 2>/dev/null; }
alive(){ kill -0 "$1" 2>/dev/null; }

samplers "$RD" "$P"; watcher "$RD" "$P" ""
touch "$RD/victim.csv"; rm -f "$RD/victim.stop"
( setsid nohup python3 "$H/victim.py" "$RD/victim.csv" "$RD/victim.stop" 20 < /dev/null > "$RD/victim.out" 2>&1 & echo $! > "$RD/victim.pid" )
ev victim_start
sleep 30

# attack (u9atk, MODIFY on ks.t1 only)
export U9_USER=u9atk U9_PASS=u9atk-pw
ev attack_start
LOADFAIL=""; c=0
while [ $((c*1000)) -lt "$R" ]; do
  a=$((c*1000)); b=$(( (c+1)*1000 )); [ $b -gt "$R" ] && b=$R
  python3 "$H/writer.py" write t1 big $a $b 1 >> "$RD/load.log" 2>&1
  log "chunk $a-$b written"
  alive "$P" || { LOADFAIL="jvm dead during load of t1 at row $b"; break; }
  oomseen "$RD" && { LOADFAIL="OOM during load of t1 at row $b"; break; }
  c=$((c+1))
done
ev attack_load_end
res "load_errors=$(python3 -c "import json; print(sum(json.loads(l).get('errors',0) for l in open('$RD/load.log') if l.startswith('{\"table')))")"
res "load_ok=$(python3 -c "import json; print(sum(json.loads(l).get('ok',0) for l in open('$RD/load.log') if l.startswith('{\"table')))")"

OUT=""
if [ -n "$LOADFAIL" ]; then
  log "$LOADFAIL"; res "load_endpoint=$LOADFAIL"
  oomseen "$RD" && OUT=OOM_DURING_LOAD || OUT=DIED_DURING_LOAD
else
  T0=$(date +%s); log "BG: last write done; waiting <= 600 s for the endpoint or idle compaction"
  while :; do
    sleep 2
    if oomseen "$RD"; then OUT=OOM; break; fi
    if ! alive "$P"; then OUT=DIED; break; fi
    if [ $(( $(date +%s) - T0 )) -ge 20 ]; then
      cs=$(timeout 15 $NT compactionstats 2>/dev/null)
      echo "$cs" | grep -qE "^pending tasks:? +0 *$" && ! echo "$cs" | grep -qE "Compaction|COMPACTION" && { OUT=COMPLETED_IDLE; break; }
    fi
    [ $(( $(date +%s) - T0 )) -ge 600 ] && { OUT=TIMEOUT; break; }
  done
fi
log "outcome $OUT"; res "outcome=$OUT"

case $OUT in
  OOM|OOM_DURING_LOAD)
    grep -n -m1 -F "java.lang.OutOfMemoryError" "$RD/stdout.log" "$RD/logs/system.log" 2>/dev/null | head -2 | sed 's/^/first_oom: /' >> "$RD/result.txt"
    for i in $(seq 1 150); do alive "$P" || break; sleep 2; done   # dump, then the shipped OnOutOfMemoryError kill -9
    if alive "$P"; then kill "$P"; for i in $(seq 1 30); do alive "$P" || break; sleep 1; done; alive "$P" && kill -9 "$P"; fi
    ;;
  *)
    "$H/victim-ctl.sh" stop "$L" >> "$RD/run.log"
    ;;
esac
alive "$P" && kill -9 "$P"
stop_samplers "$RD"
find "$DATA" -maxdepth 2 -name '*-Data.db' -printf '%f %s\n' > "$RD/listing-after.txt" 2>/dev/null
find "$DATA" -maxdepth 2 -name '*-Index.db' -printf '%f %s\n' >> "$RD/listing-after.txt" 2>/dev/null
ls -la "$ROOT/node/commitlog" > "$RD/commitlog-after.txt" 2>&1

# restart on the same data (crash-loop check), only after an OOM
if [ "$OUT" = OOM ] || [ "$OUT" = OOM_DURING_LOAD ]; then
  log "node down; restart in 60 s on the same data"
  sleep 60
  L2=$L-R; RD2=$ROOT/runs/$L2
  ev restart_start
  if "$H/victim-ctl.sh" start "$L2" "$HEAP" "$DIRECT" keep >> "$RD/run.log" 2>&1; then
    P2=$(cat "$RD2/cass.pid"); : > "$RD2/result.txt"
    echo "label=$L2 restart of $L on the same node/ data, heap=$HEAP direct=$DIRECT" >> "$RD2/result.txt"
    samplers "$RD2" "$P2"; watcher "$RD2" "$P2" "_restart"
    OUT2=""
    if "$H/victim-ctl.sh" ready "$L2" >> "$RD/run.log" 2>&1; then
      ev restart_ready
      T1=$(date +%s)
      while :; do
        sleep 2
        if oomseen "$RD2"; then OUT2=OOM; break; fi
        if ! alive "$P2"; then OUT2=DIED; break; fi
        if [ $(( $(date +%s) - T1 )) -ge 60 ]; then
          cs=$(timeout 15 $NT compactionstats 2>/dev/null)
          echo "$cs" | grep -qE "^pending tasks:? +0 *$" && ! echo "$cs" | grep -qE "Compaction|COMPACTION" && { OUT2=COMPLETED_IDLE; break; }
        fi
        [ $(( $(date +%s) - T1 )) -ge 600 ] && { OUT2=TIMEOUT; break; }
      done
    else
      oomseen "$RD2" && OUT2=OOM_DURING_START || OUT2=START_FAILED
    fi
    log "restart outcome $OUT2"; echo "outcome=$OUT2" >> "$RD2/result.txt"; res "restart_outcome=$OUT2"
    case $OUT2 in
      OOM*) grep -n -m1 -F "java.lang.OutOfMemoryError" "$RD2/stdout.log" "$RD2/logs/system.log" 2>/dev/null | head -2 | sed 's/^/first_oom: /' >> "$RD2/result.txt"
            for i in $(seq 1 150); do alive "$P2" || break; sleep 2; done
            if alive "$P2"; then kill "$P2"; for i in $(seq 1 30); do alive "$P2" || break; sleep 1; done; alive "$P2" && kill -9 "$P2"; fi;;
      *) sleep 20; "$H/victim-ctl.sh" stop "$L2" >> "$RD/run.log";;
    esac
    alive "$P2" && kill -9 "$P2"
    stop_samplers "$RD2"
    find "$DATA" -maxdepth 2 -name '*-Data.db' -printf '%f %s\n' > "$RD2/listing-after.txt" 2>/dev/null
    find "$DATA" -maxdepth 2 -name '*-Index.db' -printf '%f %s\n' >> "$RD2/listing-after.txt" 2>/dev/null
  else
    res "restart_outcome=START_CMD_FAILED"
  fi
fi

# victim off (it saw the whole run)
sleep 10; touch "$RD/victim.stop"; ev victim_stop_requested
for i in $(seq 1 30); do kill -0 "$(cat "$RD/victim.pid")" 2>/dev/null || break; sleep 1; done
kill "$(cat "$RD/victim.pid")" 2>/dev/null

# analysis (after every JVM is gone); dumps are scanned and then deleted
for D in "$RD" "$ROOT/runs/$L-R"; do
  [ -d "$D" ] || continue
  hp=$(ls "$D"/*.hprof 2>/dev/null | head -1)
  if [ -n "$hp" ]; then
    echo "hprof=$hp size=$(stat -c %s "$hp")" >> "$D/result.txt"
    python3 "$H/hprofhist.py" "$hp" 30 > "$D/hprofhist.txt" 2>&1
    python3 "$H/hprofstacks.py" "$hp" DataOutputBuffer > "$D/hprofstacks.txt" 2>&1
    rm -f "$hp"; echo "hprof deleted after analysis" >> "$D/result.txt"
  fi
  python3 "$H/gcwin.py" "$D/logs" > "$D/gcwin.txt" 2>&1
  python3 "$H/summarize.py" "$D" > "$D/summary.txt" 2>&1
done
python3 "$H/victim-summary.py" "$RD" > "$RD/victim-summary.txt" 2>&1
du -sh "$ROOT/node" >> "$RD/run.log" 2>&1
log "done $L"
