#!/usr/bin/env bash
# Cluster tier (B3, as amended 2026-10-26) of indexing_target_page_size-calculateIndexingPageSize-meanPartitionSize--autonomous.
# usage: source ~/Library/Caches/stage4/env.sh; cluster-run.sh
#   shakedown: ROWS=1200 REPS=1 OUT=$W/logs/<stem>/shakedown-cluster cluster-run.sh
# One node from the built clone $W/cassandra-run38 (never built while it runs), conf/data/commitlog/hints/saved_caches/logs
# under $W/node-itp (amendment B3a). MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M; gc log line added to the node's jvm11-server.options;
# Byteman itp.btm (observe-only; amendment B3d) through JVM_EXTRA_OPTS.
# Phase 1 (K1 unset): keyspace, tables a and b, disableautocompaction + table option enabled=false (fix D1), COPY 12000 rows each, flush, CREATE INDEX a_s / b_s,
#   wait for both initial builds (ITP END lines), TRACE logging for SecondaryIndexManager, then rebuild_index b x REPS and
#   a x REPS, each with a 0.5 s GC.heap_info sampler and epoch-ms marks; drain, stop.
# Phase 2 (K1 = -Dcassandra.force_default_indexing_page_size=true): restart on the same data, TRACE again, rebuild b x REPS; drain, stop.
# Marks are epoch ms and byte offsets of node.out (the ITP lines) and of logs/debug.log. Env: C, OUT, ROWS, REPS.
set -uo pipefail
S=indexing_target_page_size-calculateIndexingPageSize-meanPartitionSize--autonomous
ROWS=${ROWS:-12000}; REPS=${REPS:-3}
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run38}
N=$W/node-itp
OUT=${OUT:-$W/logs/$S/cluster}
mkdir -p "$OUT"; rm -rf "${OUT:?}"/*
export CASSANDRA_HOME=$C
DPAT='cassandra.service.Cassandra''Daemon'      # split so this script's own command line never matches
BMJAR=$C/build/lib/jars/byteman-4.0.20.jar
NO=$OUT/node.out
log() { echo "[$(date '+%F %T')] $*" | tee -a "$OUT/commands.log"; }
note() { echo "$*" >> "$OUT/summary.txt"; log "$*"; }
nowms() { python3 -c 'import time; print(int(time.time()*1000))'; }
off() { wc -c < "$NO" | tr -d ' '; }
doff() { wc -c < "$N/logs/debug.log" 2>/dev/null | tr -d ' ' || echo 0; }
pgrep -f "$DPAT" >/dev/null && { log "ABORT: a Cassandra daemon is already running"; exit 1; }
for p in 7000 7199 9042; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { log "ABORT: port $p busy"; exit 1; }; done
[ -f "$BMJAR" ] || { log "ABORT: no $BMJAR"; exit 1; }
( cd "$W" && java -cp "$BMJAR:$C/build/classes/main:$C/build/lib/jars/*" org.jboss.byteman.check.TestScript -v "$H/itp.btm" ) > "$OUT/btm-check.txt" 2>&1
grep -q 'TestScript: no errors' "$OUT/btm-check.txt" || { log "ABORT: btm rules do not type-check (btm-check.txt)"; exit 1; }
note "RUN ROWS=$ROWS REPS=$REPS clone=$(git -C "$C" rev-parse HEAD) status_entries=$(git -C "$C" status --short | wc -l | tr -d ' ') itp_btm_sha256=$(shasum -a 256 "$H/itp.btm" | cut -c1-16) start_epoch=$(date +%s)"
NT() { (cd "$C" && bin/nodetool "$@"); }
CQ() { (cd "$C" && HOME=$W/home bin/cqlsh 127.0.0.1 --request-timeout=600 "$@"); }
NPID=; SPID=
stop_sampler() { [ -n "$SPID" ] || return 0; touch "$OUT/sampler.stop"; for i in $(seq 1 20); do kill -0 "$SPID" 2>/dev/null || break; sleep 0.5; done; kill "$SPID" 2>/dev/null; SPID=; }
stop_node() {
  [ -z "$NPID" ] && return 0
  log "stopping node (pid $NPID)"
  if kill -0 "$NPID" 2>/dev/null; then
    NT drain >> "$OUT/commands.log" 2>&1 & local dp=$!
    for i in $(seq 1 90); do kill -0 "$dp" 2>/dev/null || break; sleep 1; done
    kill "$dp" 2>/dev/null; kill "$NPID" 2>/dev/null
    for i in $(seq 1 60); do kill -0 "$NPID" 2>/dev/null || break; sleep 1; done
    kill -0 "$NPID" 2>/dev/null && { log "node still alive after 60 s: kill -9"; kill -9 "$NPID"; sleep 2; }
  fi
  NPID=; }
stop_all() { stop_sampler; stop_node; sleep 2; local left; left=$(pgrep -f "$DPAT")
  [ -n "$left" ] && { log "WARNING: daemon still running ($left): kill -9"; kill -9 $left; sleep 2; }
  pgrep -f "$DPAT" >/dev/null && log "WARNING: daemon still running" || log "no Cassandra daemon left"; }
trap 'stop_all; [ -d "$N/logs" ] && cp -R "$N/logs" "$OUT/node-logs-trap"; rm -rf "$N"; log "node dir wiped (trap)"' EXIT

# node dir and conf (amendment B3a)
rm -rf "$N"; mkdir -p "$N"/{data,commitlog,hints,saved_caches,cdc_raw,logs}; cp -R "$C/conf" "$N/conf"
Y=$N/conf/cassandra.yaml
grep -v -E '^(hints_directory|data_file_directories|commitlog_directory|saved_caches_directory|cdc_raw_directory):' "$C/conf/cassandra.yaml" > "$Y"
{ echo; echo "# stage-4 overrides (indexing_target_page_size): directories only, defaults otherwise (B3a)"
  echo "data_file_directories:"; echo "    - $N/data"
  echo "commitlog_directory: $N/commitlog"; echo "hints_directory: $N/hints"
  echo "saved_caches_directory: $N/saved_caches"; echo "cdc_raw_directory: $N/cdc_raw"; } >> "$Y"
echo "-Xlog:gc*:file=$N/gc.log:time,uptime" >> "$N/conf/jvm11-server.options"
tail -8 "$Y" > "$OUT/yaml-overrides.txt"; tail -2 "$N/conf/jvm11-server.options" > "$OUT/jvm11-options-added.txt"
diff "$C/conf/cassandra.yaml" "$Y" > "$OUT/yaml-diff.txt"

launch() { # $1 extra JVM opts
  log "+ MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$N/logs JVM_EXTRA_OPTS=\"-javaagent:$BMJAR=script:$H/itp.btm $1\" bin/cassandra -f"
  ( cd "$C" && MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_CONF="$N/conf" CASSANDRA_LOG_DIR="$N/logs" JVM_EXTRA_OPTS="-javaagent:$BMJAR=script:$H/itp.btm $1" exec bin/cassandra -f ) >> "$NO" 2>&1 < /dev/null &
  NPID=$!; log "launcher pid $NPID"
  for i in $(seq 1 120); do
    kill -0 "$NPID" 2>/dev/null || { log "ABORT: node died during start"; exit 1; }
    if NT status 2>/dev/null | grep -q "^UN  127.0.0.1" && [ "$(NT statusbinary 2>/dev/null)" = running ]; then
      log "node UN, statusbinary running; pid $NPID: $(ps -o command= -p "$NPID" | cut -c1-50)"; return 0; fi
    sleep 3
  done
  log "ABORT: node not UN/running within 360 s"; exit 1; }
readback() { # $1 label
  note "JVMARGS $1 | $(grep -o 'JVM Arguments: .*' "$N/logs/system.log" | tail -1 | grep -o -E -- '-Xm[sxn][0-9]*[GMm]|-XX:\+UseG1GC|-Xlog:gc[^ ,]*|-javaagent:[^ ,]*byteman[^ ,]*|-Dcassandra.force_default_indexing_page_size=[a-z]*' | tr '\n' ' ')"
  note "HEAP $1 | $(grep -E 'Heap size|HEAP_NEWSIZE has erroneously' "$NO" "$N/logs/system.log" | tail -2 | cut -c1-200 | tr '\n' ' ')"; }

rebuild() { # $1 phase, $2 table, $3 rep
  local lab="$1-$2-$3" t0 t1 rc
  rm -f "$OUT/sampler.stop"
  ( while [ ! -f "$OUT/sampler.stop" ]; do
      echo "#SAMPLE t=$(nowms)"; jcmd "$NPID" GC.heap_info 2>&1 | grep -E 'garbage-first heap|region size|young|survivor' | head -3; sleep 0.5
    done ) > "$OUT/heapinfo-$lab.txt" 2>&1 &
  SPID=$!
  note "MARK $lab rebuild-start ms=$(nowms) off=$(off) doff=$(doff)"
  NT rebuild_index ks "$2" "$2_s" >> "$OUT/commands.log" 2>&1; rc=$?
  note "MARK $lab rebuild-end ms=$(nowms) off=$(off) doff=$(doff) rc=$rc"
  stop_sampler
  NT compactionstats > "$OUT/compactionstats-$lab.txt" 2>&1
  note "SAMPLES $lab $(grep -c '^#SAMPLE' "$OUT/heapinfo-$lab.txt")"
  sleep 5; }

# ---- phase 1: K1 unset
: > "$NO"
note "PHASE k1unset start ms=$(nowms)"
launch ""
readback k1unset
python3 -I "$H/gencsv.py" "$N/a.csv" "$ROWS" a; python3 -I "$H/gencsv.py" "$N/b.csv" "$ROWS" b
note "CSV a=$(wc -l < "$N/a.csv" | tr -d ' ') lines $(stat -f %z "$N/a.csv") B; b=$(wc -l < "$N/b.csv" | tr -d ' ') lines $(stat -f %z "$N/b.csv") B"
CQ -e "CREATE KEYSPACE ks WITH replication={'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE ks.a (pk int, ck text, s int static, PRIMARY KEY (pk, ck)); CREATE TABLE ks.b (pk int, ck text, s int static, v int, PRIMARY KEY (pk, ck));" >> "$OUT/commands.log" 2>&1; note "SCHEMA-RC $?"
NT disableautocompaction ks >> "$OUT/commands.log" 2>&1; note "DISABLEAUTOCOMPACTION-RC $?"
# runbook-defect fix D1 (2026-10-26): the nodetool switch does not survive the phase-2 restart; the table option does
CQ -e "ALTER TABLE ks.a WITH compaction = {'class':'SizeTieredCompactionStrategy','enabled':'false'}; ALTER TABLE ks.b WITH compaction = {'class':'SizeTieredCompactionStrategy','enabled':'false'};" >> "$OUT/commands.log" 2>&1; note "ALTER-COMPACTION-RC $?"
compread() { note "COMPACTION-OPTION $1 | $(CQ -e "SELECT table_name, compaction FROM system_schema.tables WHERE keyspace_name='ks'" 2>&1 | grep -E '^ +[ab] ' | tr -s ' ' | tr '
' ';')"; }
compread k1unset
for T in b a; do
  if [ $T = b ]; then COLS="pk,ck,s,v"; else COLS="pk,ck,s"; fi
  note "MARK load-$T start ms=$(nowms)"
  log "+ cqlsh -e \"COPY ks.$T ($COLS) FROM '$N/$T.csv' WITH MAXBATCHSIZE=1 AND CHUNKSIZE=50\""
  CQ -e "COPY ks.$T ($COLS) FROM '$N/$T.csv' WITH MAXBATCHSIZE=1 AND CHUNKSIZE=50" > "$OUT/copy-$T.log" 2>&1; rc=$?
  note "COPY $T rc=$rc | $(grep -E 'rows imported|Failed|rror' "$OUT/copy-$T.log" | tail -3 | tr '\n' ' ')"
  note "MARK load-$T end ms=$(nowms)"
done
NT flush ks >> "$OUT/commands.log" 2>&1; note "FLUSH-RC $?"
for T in a b; do note "COUNT $T $(CQ -e "SELECT count(*) FROM ks.$T WHERE pk=0" 2>&1 | grep -E '^ +[0-9]+$' | tr -d ' ')"; done
NT tablestats ks > "$OUT/tablestats-before-index.txt" 2>&1
note "TABLESTATS | $(grep -E 'Table: |SSTable count|Space used \(live\)|Compacted partition maximum bytes|Compacted partition mean bytes' "$OUT/tablestats-before-index.txt" | sed 's/^[[:space:]]*//' | tr '\n' ';')"
ls -l "$N"/data/ks/*/ > "$OUT/sstables-before-index.txt" 2>&1
rm -f "$N/a.csv" "$N/b.csv"
note "MARK create-index ms=$(nowms) off=$(off)"
CQ -e "CREATE INDEX a_s ON ks.a (s); CREATE INDEX b_s ON ks.b (s);" >> "$OUT/commands.log" 2>&1; note "CREATE-INDEX-RC $?"
for i in $(seq 1 120); do [ "$(grep -c '^ITP END' "$NO")" -ge 2 ] && break; sleep 2; done
note "INITIAL-BUILDS ITP_END=$(grep -c '^ITP END' "$NO") ms=$(nowms) off=$(off)"
NT setlogginglevel org.apache.cassandra.index.SecondaryIndexManager TRACE >> "$OUT/commands.log" 2>&1; note "LOGLEVEL-RC $? $(NT getlogginglevels 2>&1 | grep SecondaryIndexManager | tr -s ' ')"
sleep 10
for r in $(seq 1 "$REPS"); do rebuild k1unset b "$r"; done
for r in $(seq 1 "$REPS"); do rebuild k1unset a "$r"; done
stop_node
cp "$N/logs/system.log" "$OUT/system-k1unset.log"; cp "$N/logs/debug.log" "$OUT/debug-k1unset.log"; cp "$N/gc.log" "$OUT/gc-k1unset.log"
note "PHASE k1unset end ms=$(nowms) off=$(off)"

# ---- phase 2: K1 = true, same data
note "PHASE k1true start ms=$(nowms) off=$(off)"
launch "-Dcassandra.force_default_indexing_page_size=true"
readback k1true
compread k1true
NT setlogginglevel org.apache.cassandra.index.SecondaryIndexManager TRACE >> "$OUT/commands.log" 2>&1; note "LOGLEVEL-RC $? $(NT getlogginglevels 2>&1 | grep SecondaryIndexManager | tr -s ' ')"
sleep 10
for r in $(seq 1 "$REPS"); do rebuild k1true b "$r"; done
stop_node
cp "$N/logs/system.log" "$OUT/system-k1true.log"; cp "$N/logs/debug.log" "$OUT/debug-k1true.log"; cp "$N/gc.log" "$OUT/gc-k1true.log"
note "PHASE k1true end ms=$(nowms) off=$(off)"
grep '^ITP' "$NO" > "$OUT/itp.txt"
grep -h 'Calculated page size' "$OUT/debug-k1true.log" > "$OUT/calculated-page-size-lines.txt"   # debug.log is appended across the restart: this copy holds both phases
note "COMPACTIONS-KS | $(grep -c -E 'Compacting .*/data/ks/(a|b)-[0-9a-f]+/nb' "$OUT/debug-k1true.log") compaction tasks on ks.a/ks.b data in debug.log (both phases)"
note "ITP lines=$(wc -l < "$OUT/itp.txt" | tr -d ' ') PAGE=$(grep -c '^ITP PAGE' "$OUT/itp.txt") agent_errors=$(grep -c -E 'Rule\.execute called for|org\.jboss\.byteman.*(Exception|Error)|TypeException' "$NO") calc_lines=$(wc -l < "$OUT/calculated-page-size-lines.txt" | tr -d ' ')"
for P in k1unset k1true; do
  note "ERRORS $P ERROR=$(grep -c '^ERROR' "$OUT/system-$P.log") OOM=$(grep -v -E 'CompileCommand|JVM Arguments' "$OUT/system-$P.log" | grep -c 'java.lang.OutOfMemoryError')"
  grep -E '^(ERROR|WARN)' "$OUT/system-$P.log" | cut -c1-300 > "$OUT/error-warn-$P.txt"; done
trap - EXIT; stop_all; rm -rf "$N"
note "END end_epoch=$(date +%s) daemons_left=$(pgrep -f "$DPAT" | wc -l | tr -d ' ') clone_status_entries=$(git -C "$C" status --short | wc -l | tr -d ' ')"
