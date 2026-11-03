#!/usr/bin/env bash
# Cluster tier (B3, as amended 2026-10-26) of min_index_interval-validate-minIndexInterval--autonomous.
# usage: cluster-run.sh <run> <N>
#   cluster-run.sh run1  4000000     run 1 (B3c: 4M partitions per keyspace)
#   cluster-run.sh shake 100000      shakedown (not judged)
# One node on 127.0.0.1 from $W/cassandra-run43, MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M, concurrent_compactors 1, data under
# $W/node-mii43 (wiped at start and end). Order (B3e amendment):
#   lifetime 1 (index_summary_resize_interval null): create five keyspaces (compaction disabled by table option) -> per keyspace
#   stress + flush + record P1 -> boundary ALTERs + read-back -> drain, stop;
#   lifetime 2 (resize interval 1m, default capacity): phase 2a snapshots every 60 s until >= 2 "Completed resizing" lines -> record P2a
#   -> setcap 0 -> phase 2b 5 snapshots at 60 s -> record P2b -> step 6 ALTER ii_m512 max 2048, wait 2 redistributions, record S6a ->
#   ALTER max 256, wait, record S6b -> drain, stop, check, wipe.
# record <label> <ks>: nodetool tablestats, stat -f %z of every Summary.db, ls -l, sstablemetadata of every Data.db, process RSS.
# snapshot <label>: MiiProbe snap (IndexSummaries attributes, the five gauges, IndexIntervals map).
# Logs: $W/logs/min_index_interval-validate-minIndexInterval/cluster-<run>/
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
RUN=${1:?run}; N=${2:?N}
H=$(cd "$(dirname "$0")" && pwd)
L=$W/logs/min_index_interval-validate-minIndexInterval/cluster-$RUN
rm -rf "$L"; mkdir -p "$L/snaps"; CL=$L/commands.log; S=$L/summary.txt; : > "$CL"; : > "$S"
C=$W/cassandra-run43; NODE=$W/node-mii43; PB=$W/harness-bin-mii
PID=""; NLOG=""
KS="ii_1:1:2048 ii_16:16:2048 ii_128:128:2048 ii_512:512:2048 ii_m512:128:512"
now() { date '+%Y-%m-%dT%H:%M:%S%z'; }
log() { echo "[$(now)] $*" >> "$CL"; }
say() { echo "$*" >> "$S"; log "SUMMARY $*"; }
tmo() { perl -e '$t=shift; $p=fork; if(!$p){exec @ARGV; exit 127} $SIG{ALRM}=sub{kill 9,$p; waitpid $p,0; exit 124}; alarm $t; waitpid $p,0; exit($?>>8)' "$@"; }
nt()  { tmo 600 "$C/bin/nodetool" -h 127.0.0.1 -p 7199 "$@"; }
cq()  { HOME=$W/home tmo 300 "$C/bin/cqlsh" 127.0.0.1 --request-timeout=120 "$@"; }
run() { log "+ $*"; "$@" >> "$CL" 2>&1; local rc=$?; log "  exit=$rc"; return $rc; }
probe() { tmo 120 java -cp "$PB" MiiProbe "$@"; }
die() { say "ABORT: $*"; stop_node; final_check; exit 1; }
stop_node() {
  [ -z "$PID" ] && return 0
  kill -0 $PID 2>/dev/null || { PID=""; return 0; }
  run tmo 180 "$C/bin/nodetool" -h 127.0.0.1 -p 7199 drain
  kill $PID 2>/dev/null; for i in $(seq 1 60); do kill -0 $PID 2>/dev/null || break; sleep 1; done
  kill -0 $PID 2>/dev/null && { log "kill -9 $PID"; kill -9 $PID; sleep 1; }
  PID=""; log "node stopped"
}
final_check() {
  local d; d=$(ps -eo command | grep "[C]assandra""Daemon"); say "final daemon processes: ${d:-none}"
  pgrep -f "[S]tress" >/dev/null && say "WARNING: a stress JVM is still running" || say "no stress JVM left"
  pgrep -f cqlsh >/dev/null && say "WARNING: cqlsh still running" || say "no cqlsh left"
  run rm -rf "$NODE"; say "node-mii43 wiped: $([ -e "$NODE" ] && echo no || echo yes)"
}
start_node() {   # start_node <logdir>
  NLOG=$1; mkdir -p "$NLOG"
  log "+ start node CASSANDRA_CONF=$NODE/conf CASSANDRA_LOG_DIR=$NLOG MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M bin/cassandra -f"
  CASSANDRA_CONF=$NODE/conf CASSANDRA_LOG_DIR=$NLOG MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M nohup "$C/bin/cassandra" -f > "$NLOG/node.out" 2>&1 < /dev/null &
  PID=$!; disown; log "pid $PID"
  local t0; t0=$(date +%s)
  while :; do
    kill -0 $PID 2>/dev/null || die "node died during start"
    if nt status 2>/dev/null | grep -q '^UN  127.0.0.1 ' && [ "$(nt statusbinary 2>/dev/null)" = running ]; then log "up after $(( $(date +%s) - t0 )) s"; break; fi
    [ $(( $(date +%s) - t0 )) -ge 360 ] && die "node not up in 360 s"
    sleep 3
  done
  say "JVM $(grep -m1 -o 'JVM Arguments: .*' $NLOG/system.log | grep -o -- '-Xm[sx][^,]*\|-XX:+UseG1GC\|-Xmn[^,]*' | tr '\n' ' ')"
  say "ISM $(grep -m1 -o 'Initializing index summary manager.*' $NLOG/system.log)"
}
completed() { grep -c 'Completed resizing of index summaries' "$NLOG/system.log"; }
snapshot() {   # snapshot <label>
  probe snap 7199 "$1" > "$L/snaps/$1.txt" 2>&1
  say "SNAP $1 $(date +%H:%M:%S) $(grep -m1 '^SNAP' "$L/snaps/$1.txt" | cut -d' ' -f4-) | $(grep '^GAUGE' "$L/snaps/$1.txt" | cut -d' ' -f2- | tr '\n' ',') | completed=$(completed)"
}
record() {   # record <label> <ks>
  local lab=$1 ks=$2 d=$L/$1/$2 f tot=0 n=0
  mkdir -p "$d"
  nt tablestats "$ks.standard1" > "$d/tablestats.txt" 2>&1
  : > "$d/summary-files.txt"
  for f in "$NODE"/data/$ks/standard1-*/*-Summary.db; do
    [ -e "$f" ] || continue
    echo "$(stat -f %z "$f") $f" >> "$d/summary-files.txt"
  done
  ls -l "$NODE"/data/$ks/standard1-*/ > "$d/ls-l.txt" 2>&1
  local datas; datas=$(ls "$NODE"/data/$ks/standard1-*/*-Data.db 2>/dev/null)
  if [ -n "$datas" ]; then tmo 300 "$C/tools/bin/sstablemetadata" $datas > "$d/sstablemetadata.txt" 2>&1; else : > "$d/sstablemetadata.txt"; fi
  echo "$(ps -o rss= -p $PID | tr -d ' ') KiB" > "$d/rss.txt"
  while read -r sz _; do tot=$((tot+sz)); n=$((n+1)); done < "$d/summary-files.txt"
  say "REC $lab/$ks $(date +%H:%M:%S) sstables=$(awk -F': ' '/SSTable count/{print $2; exit}' "$d/tablestats.txt") offheap=$(awk -F': ' '/Index summary off heap memory used/{print $2; exit}' "$d/tablestats.txt") summarydb_files=$n summarydb_bytes=$tot totalRows=$(awk '/^totalRows:/{s+=$2} END{print s+0}' "$d/sstablemetadata.txt") rss=$(cat "$d/rss.txt" | tr -d ' ')"
}
record_all() { local kv; snapshot "$1"; for kv in $KS; do record "$1" "${kv%%:*}"; done; }
wait_completed() {   # wait_completed <base> <need> <max s> <label>: snapshot every 60 s (phase 2a) or poll every 5 s
  local base=$1 need=$2 max=$3 lab=$4 t0; t0=$(date +%s)
  while [ $(( $(completed) - base )) -lt "$need" ]; do
    [ $(( $(date +%s) - t0 )) -ge "$max" ] && { say "WARNING: $lab: only $(( $(completed) - base )) Completed lines after ${max} s"; return 1; }
    kill -0 $PID 2>/dev/null || die "node died ($lab)"
    sleep 5
  done
  say "WAIT $lab: $(( $(completed) - base )) Completed lines after $(( $(date +%s) - t0 )) s"
}
stress() {   # stress <ks>
  local ks=$1 out=$L/stress-$1.txt
  log "+ cassandra-stress write n=$N cl=ONE -pop seq=1..$N -col n=FIXED(1) size=FIXED(16) -schema keyspace=$ks -rate threads=64 -node 127.0.0.1 > $out"
  tmo 3600 "$C/tools/bin/cassandra-stress" write n=$N cl=ONE -pop seq=1..$N -col 'n=FIXED(1)' 'size=FIXED(16)' -schema keyspace=$ks -rate threads=64 -node 127.0.0.1 > "$out" 2>&1 < /dev/null
  local rc=$?
  say "STRESS $ks exit=$rc $(grep -m1 'Total partitions' "$out" | tr -s ' ') | $(grep -m1 'Total errors' "$out" | tr -s ' ') | $(grep -m1 'Op rate' "$out" | tr -s ' ') | $(grep -m1 'Total operation time' "$out" | tr -s ' ')"
  run nt flush "$ks" standard1 || die "flush $ks failed"
}

say "cluster-run $RUN N=$N start $(now) clone $(git -C $C describe --tags) $(git -C $C rev-parse --short HEAD)"
[ -n "$(ps -eo command | grep "[C]assandra""Daemon")" ] && { say "ABORT: a daemon is already running"; exit 1; }
for p in 7000 7199 9042; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { say "ABORT: port $p busy"; exit 1; }; done
rm -rf "$NODE"

# ---- lifetime 1: phase 1 (no redistribution) ----
run "$H/make-node-conf.sh" concurrent_compactors=1 index_summary_resize_interval= || die "conf 1"
sed -n '/^# ---- stage4 mii43 lines/,$p' "$NODE/conf/cassandra.yaml" > "$L/yaml-tail-1.txt"
grep -n '^index_summary' "$NODE/conf/cassandra.yaml" > "$L/yaml-is-1.txt"
start_node "$L/node1"
for kv in $KS; do
  ks=${kv%%:*}; r=${kv#*:}; m=${r%%:*}; M=${r#*:}
  run cq -e "CREATE KEYSPACE $ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE $ks.standard1 (key blob PRIMARY KEY, \"C0\" blob) WITH compression = {} AND compaction = {'class':'SizeTieredCompactionStrategy','enabled':'false'} AND min_index_interval = $m AND max_index_interval = $M;" || die "create $ks"
done
cq -e "SELECT keyspace_name, min_index_interval, max_index_interval, compaction, compression FROM system_schema.tables WHERE keyspace_name IN ('ii_1','ii_16','ii_128','ii_512','ii_m512');" > "$L/schema.txt" 2>&1
say "SCHEMA $(grep -c 'ii_' "$L/schema.txt") ii_ rows"
for kv in $KS; do
  ks=${kv%%:*}
  stress "$ks"
  record P1 "$ks"
done
snapshot P1
for kv in $KS; do record P1end "${kv%%:*}"; done
say "FORMAT data files: $(ls "$NODE"/data/ii_*/standard1-*/*-Data.db | sed 's/.*\///' | sed 's/-[0-9]*-/-N-/' | sort | uniq -c | tr -s ' ' | tr '\n' ',')"

# step 3: boundary ALTERs
for v in "min_index_interval = 0" "max_index_interval = 64"; do
  tag=$(echo "$v" | tr -d ' =')
  cq -e "ALTER TABLE ii_128.standard1 WITH $v;" > "$L/alter-$tag.txt" 2>&1; rc=$?
  log "+ ALTER TABLE ii_128.standard1 WITH $v -> exit=$rc"
  say "ALTER $v exit=$rc $(tr '\n' ' ' < "$L/alter-$tag.txt" | cut -c1-300)"
done
cq -e "SELECT min_index_interval, max_index_interval FROM system_schema.tables WHERE keyspace_name='ii_128' AND table_name='standard1';" > "$L/readback-ii_128.txt" 2>&1
say "READBACK ii_128 $(tr -s ' \n' ' ' < "$L/readback-ii_128.txt")"
nt compactionhistory > "$L/compactionhistory-1.txt" 2>&1
say "COMPACTIONHISTORY 1 ii_lines=$(grep -c ' ii_' "$L/compactionhistory-1.txt")"
say "LIFETIME1 Redistributing lines: $(grep -c 'Redistributing index summaries' "$L/node1/system.log")"
grep -c '^ERROR' "$L/node1/system.log" > "$L/error-count-1.txt"; say "node1 system.log ERROR lines: $(cat "$L/error-count-1.txt")"
stop_node

# ---- lifetime 2: phase 2 (resize interval 1m) ----
run "$H/make-node-conf.sh" concurrent_compactors=1 index_summary_resize_interval=1m || die "conf 2"
sed -n '/^# ---- stage4 mii43 lines/,$p' "$NODE/conf/cassandra.yaml" > "$L/yaml-tail-2.txt"
grep -n '^index_summary' "$NODE/conf/cassandra.yaml" > "$L/yaml-is-2.txt"
start_node "$L/node2"
snapshot P2a-start
# phase 2a: default capacity, snapshot every 60 s until >= 2 Completed lines (max 240 s)
t0=$(date +%s); i=0
while [ "$(completed)" -lt 2 ]; do
  [ $(( $(date +%s) - t0 )) -ge 240 ] && { say "WARNING: phase 2a: only $(completed) Completed lines after 240 s"; break; }
  kill -0 $PID 2>/dev/null || die "node died (2a)"
  sleep 60; i=$((i+1)); snapshot "P2a-$i"
done
say "PHASE2a Completed lines: $(completed) after $(( $(date +%s) - t0 )) s"
record_all P2a
# phase 2b: capacity 0
probe setcap 7199 0 > "$L/setcap.txt" 2>&1; say "SETCAP $(tr '\n' ' ' < "$L/setcap.txt")"
base=$(completed); log "phase 2b base Completed=$base"
for i in 1 2 3 4 5; do sleep 60; kill -0 $PID 2>/dev/null || die "node died (2b)"; snapshot "P2b-$i"; done
say "PHASE2b Completed lines after setcap: $(( $(completed) - base ))"
record_all P2b
# step 6
for v in 2048 256; do
  lab=$([ $v = 2048 ] && echo S6a || echo S6b)
  base=$(completed)
  run cq -e "ALTER TABLE ii_m512.standard1 WITH max_index_interval = $v;" || say "WARNING: ALTER ii_m512 max $v failed"
  cq -e "SELECT min_index_interval, max_index_interval FROM system_schema.tables WHERE keyspace_name='ii_m512' AND table_name='standard1';" > "$L/readback-ii_m512-$v.txt" 2>&1
  say "READBACK ii_m512 $v $(tr -s ' \n' ' ' < "$L/readback-ii_m512-$v.txt")"
  wait_completed "$base" 2 200 "$lab"
  record_all "$lab"
done
grep 'index summaries: downsample\|Redistributing index summaries\|Completed resizing\|Beginning redistribution' "$L/node2/system.log" > "$L/redistribution-lines-2.txt"
say "LIFETIME2 redistribution log lines: $(wc -l < "$L/redistribution-lines-2.txt" | tr -d ' ')"
nt compactionhistory > "$L/compactionhistory-2.txt" 2>&1
say "COMPACTIONHISTORY 2 ii_lines=$(grep -c ' ii_' "$L/compactionhistory-2.txt")"
grep -c '^ERROR' "$L/node2/system.log" > "$L/error-count-2.txt"; say "node2 system.log ERROR lines: $(cat "$L/error-count-2.txt")"
stop_node
final_check
say "end $(now)"
