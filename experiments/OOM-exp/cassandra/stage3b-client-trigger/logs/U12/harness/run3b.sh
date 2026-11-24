#!/usr/bin/env bash
# U12 3-b confirm: one run of the natural-path arm N with authentication on (PasswordAuthenticator + CassandraAuthorizer),
# the attack as a non-superuser data role holding only MODIFY on u12.t, and a victim role on its own keyspace.
# Adapted from the stage-2 run.sh (arm N branch). Runs ON ms0617; launch detached:
#   ( setsid nohup bash /mydata/s4/3b-U12/h/run3b.sh <run> [heapMiB=2048] [directMiB=1024] < /dev/null > /dev/null 2>&1 & )
#   env RESTART=0 skips the operator restart after the OOM (default 1: restart once on the same data, observe 300 s).
# Phases: fresh node -> superuser creates schema/roles/GRANTs -> attacker probe -> samplers + victim (60 s baseline)
#   -> attack (700 x 1 MiB appends to one map row as role attacker) -> endpoint (node exit / Compacted / 300 s)
#   -> 30 s outage seen by the victim -> restart on the same data (no client action) -> endpoint -> 30 s -> stop all.
# Instruments as stage 2: O1 JMX sampler 250 ms, O2 RssAnon/VmHWM 1 s, O3 gc.log, O4 system/debug.log, O5 heap dump
# (scanned with hprof_direct.py, then deleted), O6 compactionstats 2 s; plus victim.csv (per-second victim view).
set -uo pipefail
RUN=$1; HEAP=${2:-2048}; DIRECT=${3:-1024}; RESTART=${RESTART:-1}
U=/mydata/s4/3b-U12; H=$U/h; D=$U/inst/node; R=$U/runs/$RUN; B=$U/cassandra
J=$B/build/lib/jars; CP="$U/cls:$J/cassandra-driver-core-3.12.1-shaded.jar:$B/lib/*"
JQ="-Dlogback.configurationFile=$H/logback-quiet.xml"
APW=attacker-pw-3b; VPW=victim-pw-3b
log(){ echo "[$(TZ=America/New_York date '+%F %T')] $(date +%s%3N) $*"; }
rm -rf "$R"; mkdir -p "$R"; exec >> "$R/progress.txt" 2>&1
echo "N $RUN build=base heap=$HEAP direct=$DIRECT auth=PasswordAuthenticator/CassandraAuthorizer restart=$RESTART" > "$R/argline"
log "RUN $(cat $R/argline)"
bash $H/ctl.sh stop; bash $H/ctl.sh wipe-data
cp $D/conf/cassandra.yaml $R/cassandra.yaml.used

samplers(){ # <run-dir> <pid>
  local RR=$1 PP=$2
  ( setsid nohup java -Xmx128m -cp "$U/cls" U12Sample 7199 250 "$RR" > "$RR/sampler.err" 2>&1 < /dev/null & )
  ( setsid nohup bash -c "echo epoch_ms,rss_anon_kb,vmhwm_kb > $RR/rss.csv; while kill -0 $PP 2>/dev/null; do echo \$(date +%s%3N),\$(awk '/^RssAnon/{print \$2}' /proc/$PP/status 2>/dev/null),\$(awk '/^VmHWM/{print \$2}' /proc/$PP/status 2>/dev/null) >> $RR/rss.csv; sleep 1; done" < /dev/null > /dev/null 2>&1 & )
  ( setsid nohup bash -c "while kill -0 $PP 2>/dev/null; do echo \"@ \$(date +%s%3N)\"; $B/bin/nodetool -h 127.0.0.1 compactionstats 2>&1 | grep -v '^\$'; sleep 2; done > $RR/compactionstats.txt" < /dev/null > /dev/null 2>&1 & )
}
waitstart(){ # <run-dir> <pid>
  for i in $(seq 240); do grep -q "Startup complete" $1/logs/system.log 2>/dev/null && return 0; kill -0 $2 2>/dev/null || return 1; sleep 1; done; return 1; }
cmpstart(){ grep -q "Compacting (.*/data/u12/t-" $1/logs/debug.log 2>/dev/null || grep -q "u12 *t " $1/compactionstats.txt 2>/dev/null; }
compacted(){ grep -q "Compacted (.*/data/u12/t-" $1/logs/system.log 2>/dev/null; }
endpoint(){ # <run-dir> <pid> <wait-for-compaction-s>  -> sets END, TC
  local RR=$1 PP=$2 W=$3
  for i in $(seq $W); do cmpstart $RR && break; kill -0 $PP 2>/dev/null || break; sleep 1; done
  if cmpstart $RR; then log "compaction started [$RR]"; echo "[x] $(date +%s%3N) compaction started" >> $RR/phase.txt; else log "NO COMPACTION seen [$RR] (alive=$(kill -0 $PP 2>/dev/null && echo 1 || echo 0))"; fi
  TC=$(date +%s); END=none
  for i in $(seq 300); do kill -0 $PP 2>/dev/null || { END=exit; break; }; compacted $RR && { END=compacted; break; }; sleep 1; done
  [ "$END" = none ] && END=timeout300
  log "endpoint $END ($(( $(date +%s) - TC )) s after compaction start) [$RR]"
}

# --- phase 1: fresh node, superuser setup
bash $H/ctl.sh start $B $HEAP $DIRECT "$R"
P=$(cat $R/node.pid); log "node pid $P"
if ! waitstart $R $P; then log "INVALID: no startup"; fi
log "startup complete"
java -Xmx256m -cp "$CP" $JQ -Du12.user=cassandra -Du12.pass=cassandra U12Load admin 127.0.0.1 \
  "CREATE KEYSPACE u12 WITH replication = {'class':'SimpleStrategy','replication_factor':1}" \
  "CREATE TABLE u12.t (pk int, ck int, m map<int, blob>, PRIMARY KEY (pk, ck))" \
  "CREATE KEYSPACE vks WITH replication = {'class':'SimpleStrategy','replication_factor':1}" \
  "CREATE TABLE vks.kv (k int PRIMARY KEY, v blob)" \
  "CREATE ROLE attacker WITH PASSWORD = '$APW' AND LOGIN = true" \
  "GRANT MODIFY ON TABLE u12.t TO attacker" \
  "CREATE ROLE victim WITH PASSWORD = '$VPW' AND LOGIN = true" \
  "GRANT SELECT ON KEYSPACE vks TO victim" \
  "GRANT MODIFY ON KEYSPACE vks TO victim" \
  "LIST ROLES" "LIST ALL PERMISSIONS OF attacker" "LIST ALL PERMISSIONS OF victim" > "$R/auth-setup.log" 2>&1
rc=$?; [ $rc = 0 ] || log "INVALID: superuser setup failed"
log "superuser setup done (exit $rc)"
java -Xmx256m -cp "$CP" $JQ -Du12.user=attacker -Du12.pass=$APW U12Load probe 127.0.0.1 > "$R/probe.log" 2>&1
log "attacker probe done"

# --- phase 2: samplers, victim baseline, attack
samplers $R $P
( setsid nohup java -Xmx256m -cp "$CP" $JQ -Du12.user=victim -Du12.pass=$VPW U12Victim 127.0.0.1 $R/victim.csv $R/victim.STOP 20 > "$R/victim.log" 2>&1 < /dev/null & )
log "victim started; 60 s baseline"
sleep 60
log "ATTACK START (role attacker, 700 x 1 MiB appends to u12.t pk=0 ck=0)"; echo "[x] $(date +%s%3N) attack start" >> $R/phase.txt
( setsid nohup java -Xmx512m -Dstop_on_error=false -cp "$CP" $JQ -Du12.user=attacker -Du12.pass=$APW U12Load write 127.0.0.1 0 0 700 > "$R/load.log" 2>&1 < /dev/null & )
endpoint $R $P 600
END1=$END
if [ "$END1" = compacted ]; then  # as stage 2: for N the endpoint waits for the client's final line
  for i in $(seq 120); do grep -q "acked=[0-9]* failed=" $R/load.log 2>/dev/null && break; kill -0 $P 2>/dev/null || { END1=exit; break; }; sleep 1; done
fi
echo "[x] $(date +%s%3N) endpoint $END1" >> $R/phase.txt
log "phase-2 endpoint $END1"
sleep 30   # outage / after-window seen by the victim

# --- phase 3: operator restart on the same data (crash loop check), no client action
if [ "$END1" = exit ] && [ "$RESTART" = 1 ]; then
  pkill -f "U12Load write 127.0.0.1" 2>/dev/null
  RR=$R/restart; mkdir -p $RR
  log "OPERATOR RESTART on the same data"; echo "[x] $(date +%s%3N) restart" >> $R/phase.txt
  bash $H/ctl.sh start $B $HEAP $DIRECT "$RR"
  P2=$(cat $RR/node.pid); log "restart node pid $P2"
  samplers $RR $P2
  if waitstart $RR $P2; then log "restart: startup complete"; echo "[x] $(date +%s%3N) restart startup complete" >> $R/phase.txt; else log "restart: no 'Startup complete' (alive=$(kill -0 $P2 2>/dev/null && echo 1 || echo 0))"; fi
  endpoint $RR $P2 180
  echo "[x] $(date +%s%3N) restart endpoint $END" >> $R/phase.txt
  log "restart endpoint $END"
  grep "compaction started \[$RR\]" $R/progress.txt > $RR/progress.txt 2>/dev/null
  sleep 30
fi

# --- stop everything
touch $R/victim.STOP; sleep 4
bash $H/ctl.sh stop; sleep 2
pkill -f "U12Victim 127.0.0.1 $R/" 2>/dev/null; pkill -f "U12Load write 127.0.0.1" 2>/dev/null
pkill -f "U12Sample 7199 250 $R" 2>/dev/null
for RR in $R $R/restart; do
  [ -d $RR/logs ] || continue
  grep -n -m1 -B2 -A45 "OutOfMemoryError" $RR/logs/system.log > $RR/first-oom.txt 2>/dev/null
  ls -la $RR/dumps > $RR/dumps.txt 2>/dev/null
  d=$(ls $RR/dumps/*.hprof 2>/dev/null | head -1)
  if [ -n "$d" ]; then python3 $H/hprof_direct.py $d 6 > $RR/direct-holders.txt 2>&1 < /dev/null; ls -la $d >> $RR/dumps.txt; rm -f $d; log "dump scanned and deleted: $d"; fi
  python3 $H/analyze.py $RR > $RR/outcome.txt 2>&1
done
echo "END=$END1 restart_end=${END:-na}" >> $R/outcome.txt
ls -l $D/data/u12/t-*/*Data.db > "$R/datadb-final.txt" 2>/dev/null
echo "$RUN $(cat $R/argline) | $(head -1 $R/outcome.txt) | END=$END1" >> $U/runs/summary.txt
bash $H/ctl.sh wipe-data
log "DONE"
