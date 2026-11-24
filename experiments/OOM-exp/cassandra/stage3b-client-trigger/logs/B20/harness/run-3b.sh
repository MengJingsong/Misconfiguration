#!/usr/bin/env bash
# 3-b confirm B20 (pc75): one attack run from a clean start, authentication on, adapted from the case's run-arm.sh (T).
#   run-3b.sh <label> [dump|nodump]   (dump|nodump applies to the restart lifetime; the attack lifetime always dumps)
# Lifetime <label>-a: fresh work/ (empty data dir), node at the T2 budget (2G heap / 1024M direct, shipped defaults,
#   PasswordAuthenticator + CassandraAuthorizer + CassandraRoleManager). Superuser only creates roles/keyspaces/grants.
#   Victim tenant (role victim, vks.kv) runs from before the attack to the end. Attacker (role attacker, only
#   CREATE ON KEYSPACE atk) creates atk.t, writes the wide partition and 1,000,000 small ones over CQL with NO nodetool
#   step (autocompaction on, natural flushes, no drain/restart), waits 60 s, then CREATE INDEX t_ck ON atk.t (ck).
# Lifetime <label>-r: after the endpoint, the node is restarted on the same work/ (operator restart, same budget) to
#   test the crash-loop claim (unbuilt index rebuilt at startup). No client action in -r.
# Instruments (operator side, read-only, not attack steps): jcmd GC.heap_info + RssAnon every 2 s, nodetool
#   compactionstats every 5 s, one GC.class_histogram before the trigger (as T), sstablemetadata + kcalc offline K.
set -uo pipefail
L=$1 RDUMP=${2:-nodump}
ROOT=/mydata/s4/3b-B20; H=$ROOT/harness; BUILD=$ROOT/tree; RD=$ROOT/runs/$L
export CASSANDRA_HOME=$BUILD
NT="$BUILD/bin/nodetool -h 127.0.0.1"
HEAP=2G; DIRECT=1024M
WIDE_N=${WIDE_N:-4000}; SMALL_N=${SMALL_N:-1000000}; BASE_S=${BASE_S:-60}; SETTLE_S=${SETTLE_S:-60}   # SHAKE overrides
LA=$L-a; LR=$L-r; DA=$ROOT/runs/$LA; DR=$ROOT/runs/$LR
rm -rf "$RD"; mkdir -p "$RD"
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*" | tee -a "$RD/run.log"; }
phase(){ echo "$(date +%s.%N) $1" >> "$RD/phases.txt"; log "phase $1"; }
ATK(){ python3 "$H/attacker.py" "$@"; }

samplers(){ local D=$1 P=$2; touch "$D/sampler.run"
  ( setsid nohup bash -c "while [ -f '$D/sampler.run' ] && kill -0 $P 2>/dev/null; do
      t=\$(date +%s.%N); h=\$(timeout 10 jcmd $P GC.heap_info 2>/dev/null | grep -m1 -E 'garbage-first heap' | tr -s ' ');
      ra=\$(awk '/RssAnon/{print \$2}' /proc/$P/status 2>/dev/null);
      echo \"\$t|\$h|rssAnonKB=\$ra\" >> '$D/heap.csv'; sleep 2; done" < /dev/null > /dev/null 2>&1 & echo $! > "$D/sampler1.pid" )
  ( setsid nohup bash -c "while [ -f '$D/sampler.run' ] && kill -0 $P 2>/dev/null; do
      echo \"=== \$(date +%s.%N)\" >> '$D/cstats.log'; timeout 15 $NT compactionstats >> '$D/cstats.log' 2>&1; sleep 5; done" < /dev/null > /dev/null 2>&1 & echo $! > "$D/sampler2.pid" ); }
stop_samplers(){ rm -f "$1/sampler.run"; sleep 3; local f; for f in sampler1 sampler2; do kill "$(cat "$1/$f.pid" 2>/dev/null)" 2>/dev/null; done; }
wait_endpoint(){ local D=$1 P=$2 LIM=$3 T0=$4
  while :; do
    sleep 2
    grep -qF "java.lang.OutOfMemoryError" "$D/stdout.log" "$D/logs/system.log" 2>/dev/null && { echo OOM; return; }
    kill -0 "$P" 2>/dev/null || { echo DIED; return; }
    grep -q "Index build of t_ck complete" "$D/logs/system.log" 2>/dev/null && { echo COMPLETED; return; }
    python3 -c "import sys,time; sys.exit(0 if time.time()-$T0 >= $LIM else 1)" && { echo TIMEOUT; return; }
  done; }
post_oom(){ local D=$1 P=$2 last=-1 stable=0 i hp sz   # dump (if on), shipped kill -9, then a stable hprof
  for i in $(seq 1 150); do
    hp=$(ls "$D"/*.hprof 2>/dev/null | head -1); sz=$( [ -n "$hp" ] && stat -c %s "$hp" || echo 0)
    if [ "$sz" = "$last" ]; then stable=$((stable+2)); else stable=0; fi; last=$sz
    if ! kill -0 "$P" 2>/dev/null && [ $stable -ge 10 ]; then break; fi
    sleep 2
  done
  kill -0 "$P" 2>/dev/null && { kill -9 "$P"; echo "post_oom: SIGKILL sent" >> "$D/result.txt"; }; }
endpoint_report(){ local D=$1 OUT=$2 T0=$3 TE=$4
  echo "outcome=$OUT" >> "$D/result.txt"; echo "trigger_epoch=$T0" >> "$D/result.txt"
  echo "endpoint_seconds=$(python3 -c "print(round($TE-$T0,1))")" >> "$D/result.txt"
  grep -n -m1 -F "java.lang.OutOfMemoryError" "$D/stdout.log" "$D/logs/system.log" 2>/dev/null | head -2 | cut -c1-300 | sed 's/^/first_oom: /' >> "$D/result.txt"
  grep -h -E "Submitting index build of t_ck|Index build of t_ck complete|became queryable|failed build|Starting listening for CQL" "$D/logs/system.log" 2>/dev/null | cut -c1-400 | sed 's/^/syslog: /' >> "$D/result.txt"; }
kcalc_from_log(){ local D=$1 tag=$2 f n=0   # offline K over the sstables the build was submitted with
  mkdir -p "$RD/meta-$tag"
  for f in $(grep -h -m1 "Submitting index build of t_ck" "$D/logs/system.log" | grep -oE "/[^' ]*-Data\.db"); do
    n=$((n+1)); ls -l "$f" >> "$RD/meta-$tag/listing.txt" 2>&1
    "$BUILD/tools/bin/sstablemetadata" "$f" > "$RD/meta-$tag/$(basename "$f" .db).txt" 2>&1
  done
  python3 "$H/kcalc.py" "$RD"/meta-$tag/*-Data.txt > "$RD/kcalc-$tag.txt" 2>&1
  log "kcalc-$tag ($n sstables): $(grep RESULT "$RD/kcalc-$tag.txt")"; }

# ---- node check and clean start
for jp in $(pgrep -x java); do
  tr '\0' ' ' < /proc/$jp/cmdline | grep -q CassandraDaemon && { log "REFUSE: CassandraDaemon running (pid $jp)"; exit 1; }
done
log "run $L start; free $(df -h /mydata | tail -1 | awk '{print $4}') on /mydata; $(free -g | awk '/Mem:/{print "RAM avail "$7" GiB"}')"
rm -rf "$ROOT/work"; mkdir -p "$ROOT/work"/{data,commitlog,hints,saved_caches,cdc_raw}
bash "$H/victim-ctl.sh" start "$LA" "$HEAP" "$DIRECT" >> "$RD/run.log" 2>&1 || { log "start failed"; exit 1; }
bash "$H/victim-ctl.sh" ready "$LA" >> "$RD/run.log" 2>&1 || { log "not ready"; bash "$H/victim-ctl.sh" stop "$LA"; exit 1; }
PA=$(cat "$DA/cass.pid"); : > "$DA/result.txt"; echo "label=$LA heap=$HEAP direct=$DIRECT lifetime=attack" >> "$DA/result.txt"
samplers "$DA" "$PA"
python3 "$H/admin.py" setup > "$RD/admin-setup.txt" 2>&1; log "admin setup rc=$? ($(grep -c '^cql>' "$RD/admin-setup.txt") statements)"
( setsid nohup python3 "$H/victim.py" "$RD/victim.csv" 50 > "$RD/victim.out" 2>&1 < /dev/null & echo $! > "$RD/victim.pid" )
sleep 5
phase baseline; sleep $BASE_S; log "sizes: wide $WIDE_N rows, small $SMALL_N partitions"

# ---- the attack, all as role attacker over CQL
phase schema
ATK schema > "$RD/attacker.log" 2>&1; ATK negative > "$RD/negative.txt" 2>&1
python3 "$H/admin.py" perms > "$RD/admin-perms.txt" 2>&1
log "schema: $(tail -1 "$RD/attacker.log"); negative: $(cat "$RD/negative.txt" | cut -c1-300)"
phase load-wide
CH=$(( (WIDE_N + 7) / 8 ))
for c in $(seq 0 7); do
  a=$((c*CH)); b=$(((c+1)*CH)); [ $b -gt $WIDE_N ] && b=$WIDE_N; [ $a -ge $b ] && break
  ATK wide $a $b >> "$RD/attacker.log" 2>&1
  log "wide chunk $c: $(tail -1 "$RD/attacker.log" | cut -c1-260); node $(bash "$H/victim-ctl.sh" alive "$LA")"
  [ "$(bash "$H/victim-ctl.sh" alive "$LA")" = DEAD ] && break
done
if [ "$(bash "$H/victim-ctl.sh" alive "$LA")" = ALIVE ]; then
  phase load-small
  for i in 0 1 2 3; do ATK small $((1 + i*SMALL_N/4)) $((1 + (i+1)*SMALL_N/4)) 25 > "$RD/small-$i.log" 2>&1 & done; wait
  for i in 0 1 2 3; do log "small part $i: $(tail -1 "$RD/small-$i.log" | cut -c1-260)"; done
  phase settle; sleep $SETTLE_S
fi
if [ "$(bash "$H/victim-ctl.sh" alive "$LA")" = DEAD ]; then
  log "node died before the trigger"; OUT=DIED_BEFORE_TRIGGER
else
  ls -l "$ROOT"/work/data/atk/t-*/ > "$RD/listing-pre.txt" 2>&1
  timeout 60 $NT compactionstats > "$RD/cstats-pre.txt" 2>&1
  timeout 120 $NT tablestats atk.t > "$RD/tablestats-pre.txt" 2>&1
  log "pre-trigger: $(ls "$ROOT"/work/data/atk/t-*/*-Data.db 2>/dev/null | wc -l) sstables; compactions: $(grep -cE 'atk +t ' "$RD/cstats-pre.txt") active"
  timeout 60 jcmd "$PA" GC.heap_info > "$DA/baseline.txt" 2>&1
  timeout 120 jcmd "$PA" GC.class_histogram > "$DA/histo-pre.txt" 2>&1
  echo "baseline_histo_total: $(tail -1 "$DA/histo-pre.txt")" >> "$DA/result.txt"
  phase trigger
  T0=$(date +%s.%N)
  ( timeout 120 "$BUILD/bin/cqlsh" --protocol-version=4 --request-timeout=60 -u attacker -p attacker-pw 127.0.0.1 \
      -e "CREATE INDEX t_ck ON atk.t (ck)" > "$RD/trigger.out" 2>&1; echo "rc=$?" >> "$RD/trigger.out" ) &
  OUT=$(wait_endpoint "$DA" "$PA" 900 "$T0"); TE=$(date +%s.%N)
  wait
  endpoint_report "$DA" "$OUT" "$T0" "$TE"; echo "trigger: $(tr '\n' ' ' < "$RD/trigger.out" | cut -c1-300)" >> "$DA/result.txt"
  log "attack endpoint: $OUT after $(grep endpoint_seconds "$DA/result.txt")"
fi
case $OUT in
  OOM|DIED|DIED_BEFORE_TRIGGER)
    phase down; post_oom "$DA" "$PA"; stop_samplers "$DA"
    kcalc_from_log "$DA" attack
    sleep 45
    # ---- operator restart on the same data (crash-loop claim)
    phase restart
    EXTRA=""; [ "$RDUMP" = nodump ] && EXTRA="-XX:-HeapDumpOnOutOfMemoryError"
    T1=$(date +%s.%N)
    if bash "$H/victim-ctl.sh" start "$LR" "$HEAP" "$DIRECT" "$EXTRA" >> "$RD/run.log" 2>&1; then
      PR=$(cat "$DR/cass.pid"); : > "$DR/result.txt"; echo "label=$LR heap=$HEAP direct=$DIRECT extra=[$EXTRA] lifetime=restart" >> "$DR/result.txt"
      samplers "$DR" "$PR"
      OUT2=$(wait_endpoint "$DR" "$PR" 900 "$T1"); TE2=$(date +%s.%N)
      grep -q "concurrent_index_builders=" "$DR/logs/system.log" && bash "$H/victim-ctl.sh" meta "$LR"
      endpoint_report "$DR" "$OUT2" "$T1" "$TE2"
      log "restart endpoint: $OUT2 after $(grep endpoint_seconds "$DR/result.txt") (from restart command)"
      if [ "$OUT2" = OOM ] || [ "$OUT2" = DIED ]; then
        phase restart-down; post_oom "$DR" "$PR"; stop_samplers "$DR"; kcalc_from_log "$DR" restart; sleep 30
      else
        phase after; sleep 30
        python3 "$H/attacker.py" cql "SELECT count(*) FROM atk.t WHERE ck = 1" 120 > "$DR/useful.txt" 2>&1
        stop_samplers "$DR"; bash "$H/victim-ctl.sh" stop "$LR" >> "$RD/run.log" 2>&1
      fi
    else log "restart start failed"; fi
    ;;
  COMPLETED)
    phase after; sleep 10
    ATK cql "SELECT count(*) FROM atk.t WHERE ck = 1" 120 > "$DA/useful.txt" 2>&1
    sleep 20; stop_samplers "$DA"; bash "$H/victim-ctl.sh" stop "$LA" >> "$RD/run.log" 2>&1
    ;;
  *)
    phase after; stop_samplers "$DA"; bash "$H/victim-ctl.sh" stop "$LA" >> "$RD/run.log" 2>&1
    ;;
esac
phase end
touch "$RD/victim.csv.stop"; for i in $(seq 1 20); do kill -0 "$(cat "$RD/victim.pid")" 2>/dev/null || break; sleep 1; done
kill -9 "$(cat "$RD/victim.pid")" 2>/dev/null
for D in "$DA" "$DR"; do [ -d "$D" ] || continue
  P=$(cat "$D/cass.pid" 2>/dev/null); [ -n "$P" ] && kill -0 "$P" 2>/dev/null && { log "WARN: $D pid $P alive at end; SIGKILL"; kill -9 "$P"; }
  hp=$(ls "$D"/*.hprof 2>/dev/null | head -1)
  if [ -n "$hp" ]; then
    echo "hprof=$hp size=$(stat -c %s "$hp")" >> "$D/result.txt"
    python3 "$H/hprofhist.py" "$hp" 30 > "$D/hprofhist.txt" 2>&1
    python3 "$H/hprofstacks.py" "$hp" SecondaryIndexManager > "$D/hprofstacks.txt" 2>&1
    rm -f "$hp"; echo "hprof deleted after analysis" >> "$D/result.txt"
  fi
  python3 "$H/gcwin.py" "$D/logs" > "$D/gcwin.txt" 2>&1
  python3 "$H/summarize.py" "$D" > "$D/summary.txt" 2>&1
done
python3 "$H/victsum.py" "$RD" > "$RD/victim-summary.txt" 2>&1
du -sh "$ROOT/work" >> "$RD/run.log" 2>&1
rm -rf "$ROOT/work"
log "done $L"
