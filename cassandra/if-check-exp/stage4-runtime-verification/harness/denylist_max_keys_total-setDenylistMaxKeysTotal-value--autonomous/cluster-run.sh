#!/usr/bin/env bash
# Cluster tier (B3, as amended 2026-10-26) of denylist_max_keys_total-setDenylistMaxKeysTotal-value--autonomous.
# usage: cluster-run.sh <outdir-name> <M> <T list...>
#   cluster-run.sh run1 4000 4000 20000 4000     the run (B3c/B3e): 5 tables x M keys of 8 KiB, P = M, T = 4000, 20000, 4000
#   cluster-run.sh shake 400 400 2000 400        harness shakedown with a small load (not judged)
# One node on 127.0.0.1 from $W/cassandra-run26, 2 GiB heap (G1), partition_denylist_enabled true, denylist_consistency_level ONE,
# denylist_max_keys_per_table = M, denylist_refresh 20s, denylist_max_keys_total default (10000) and set over JMX; data under
# $W/node-dlmt (wiped at start and end).
# Instruments: Jmx.java (B3b verbatim) for set and load; read-back from system_views.settings (cqlsh); used heap after GC = Total of
# jcmd GC.class_histogram after GC.run x2 (heap_info recorded); Local read count of system_distributed.partition_denylist (nodetool
# tablestats) around each load and the quiet window, the READS sampler (nodetool profileload) for the access phase (runbook fix
# 2026-10-26, defect 1); system.log segments (byte offset) for the denylist ERROR / Loaded lines.
# Adapted from the sister case's cluster-run.sh (not modified there).
# Logs: $W/logs/denylist_max_keys_total-setDenylistMaxKeysTotal/cluster-<outdir-name>/
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
H=$(cd "$(dirname "$0")" && pwd)
RUN=${1:?outdir}; M=${2:?M}; shift 2; TLIST="$*"
L=$W/logs/denylist_max_keys_total-setDenylistMaxKeysTotal/cluster-$RUN
rm -rf "$L"; mkdir -p "$L"; CL=$L/commands.log; S=$L/summary.txt; : > "$CL"; : > "$S"
C=$W/cassandra-run26; N=$W/node-dlmt
TO=$W/tools-dlmt; mkdir -p "$TO"; cp "$H/Jmx.java" "$TO/Jmx.java"
PID=""
now() { date '+%Y-%m-%dT%H:%M:%S%z'; }
log() { echo "[$(now)] $*" >> "$CL"; }
say() { echo "$*" >> "$S"; log "SUMMARY $*"; }
tmo() { perl -e '$t=shift; $p=fork; if(!$p){exec @ARGV; exit 127} $SIG{ALRM}=sub{kill 9,$p; waitpid $p,0; exit 124}; alarm $t; waitpid $p,0; exit($?>>8)' "$@"; }
nt()  { tmo 300 "$C/bin/nodetool" -h 127.0.0.1 -p 7199 "$@"; }
cq()  { tmo 1800 "$C/bin/cqlsh" 127.0.0.1 --request-timeout=120 "$@"; }
jmx() { ( cd "$W" && tmo 300 java "$TO/Jmx.java" 127.0.0.1:7199 "$@" 2>&1 ); }
run() { log "+ $*"; "$@" >> "$CL" 2>&1; local rc=$?; log "  exit=$rc"; return $rc; }
die() { say "ABORT: $*"; stop_node; final_check; exit 1; }
readback() { cq -e "SELECT value FROM system_views.settings WHERE name='denylist_max_keys_total'" > "$1" 2>&1; sed -n '4p' "$1" | tr -d ' \r'; }
readcount() { nt tablestats system_distributed.partition_denylist > "$1" 2>&1; grep -m1 'Local read count:' "$1" | tr -dc '0-9'; }
stop_node() {
  [ -z "$PID" ] && return 0
  kill -0 $PID 2>/dev/null || { PID=""; return 0; }
  run tmo 120 "$C/bin/nodetool" -h 127.0.0.1 -p 7199 drain
  kill $PID 2>/dev/null; for i in $(seq 1 30); do kill -0 $PID 2>/dev/null || break; sleep 1; done
  kill -0 $PID 2>/dev/null && { log "kill -9 $PID"; kill -9 $PID; sleep 1; }
  PID=""; log "node stopped"
}
final_check() {
  local d; d=$(ps -eo command | grep '[C]assandraDaemon'); say "final CassandraDaemon processes: ${d:-none}"
  pgrep -f 'Jmx.java' >/dev/null && say "WARNING: Jmx client still running" || say "no Jmx client left"
  pgrep -f cqlsh >/dev/null && say "WARNING: cqlsh still running" || say "no cqlsh left"
  pgrep jcmd >/dev/null && say "WARNING: jcmd still running" || say "no jcmd left"
  run rm -rf "$N"; say "node-dlmt wiped (incl. the CSV): $([ -e "$N" ] && echo no || echo yes)"
}
heap_used_k() { jcmd $PID GC.heap_info 2>&1 | tee -a "$1" | grep -o 'used [0-9]*K' | head -1 | tr -dc '0-9'; }
measure() {   # measure <label>: 5 s, GC.run x2, heap_info (recorded), class histogram (Total = used heap after GC)
  local lab=$1 D=$L/$1; mkdir -p "$D"; sleep 5
  run jcmd $PID GC.run; run jcmd $PID GC.run
  local u; u=$(heap_used_k "$D/heap_info.txt")
  jcmd $PID GC.class_histogram > "$D/histogram.txt" 2>&1
  local b; b=$(awk '$4=="[B"{print $3; exit}' "$D/histogram.txt")
  local tot; tot=$(awk '$1=="Total"{print $3}' "$D/histogram.txt")
  local de; de=$(awk '$4 ~ /PartitionDenylist\$DenylistEntry$/{print $2; exit}' "$D/histogram.txt")
  say "HEAP $lab live_Total_B=$tot heap_info_used_K=$u byteArray_bytes=$b DenylistEntry_instances=${de:-0}"
}
seg_from() { tail -c +$(( $1 + 1 )) "$L/node/system.log"; }
segsum() {   # segsum <file> : counts of the denylist lines in a segment
  echo "loaded=[$(grep -o 'Loaded partition denylist cache in [0-9]*ms' "$1" | tr '\n' ';')] hitlimit=$(grep -c 'Hit limit on allowable denylisted keys in total' "$1") hitlimit_detail=[$(grep -o 'Processed [0-9]* total entries. Not adding all entries to denylist for [a-z_]*/t[0-9]' "$1" | sed -E 's/Processed ([0-9]*) .* for (.*)/\1:\2/' | tr '\n' ';')] exceeded=$(grep -c 'has exceeded the [a-z-]* allowance' "$1") read_errors=$(grep -c 'Error reading partition_denylist\|Error reading full partition denylist' "$1") other_ERROR=$(grep '^ERROR' "$1" | grep -vc 'Hit limit on allowable\|has exceeded the [a-z-]* allowance')"
}
access() {   # access phase (B3c step 4): SELECT on each table, twice, 5 s apart
  local D=$1
  for round in 1 2; do
    for t in 1 2 3 4 5; do cq -e "SELECT * FROM dl.t$t WHERE k=0x00" >> "$D/access.txt" 2>&1; echo "round $round t$t exit=$?" >> "$D/access.txt"; done
    [ $round = 1 ] && sleep 5
  done
}
label() {   # label <label> <T>
  local lab=$1 T=$2 D=$L/$1; mkdir -p "$D"
  say "== $lab: T=$T"
  jmx set DenylistMaxKeysTotal $T > "$D/set.txt"
  say "SET $lab jmx=[$(tr '\n' ' ' < "$D/set.txt")] readback=$(readback "$D/readback.txt")"
  # Runbook fix 2026-10-26 (defect 1): r0 is read after the cqlsh read-back, so no CQL client runs between r0 and r1
  local r0; r0=$(readcount "$D/tablestats-r0.txt")
  local off; off=$(stat -f %z "$L/node/system.log")
  local t0; t0=$(perl -MTime::HiRes=time -e 'printf("%d",time()*1000)')
  jmx load > "$D/load.txt"; local t1; t1=$(perl -MTime::HiRes=time -e 'printf("%d",time()*1000)')
  sleep 1
  local r1; r1=$(readcount "$D/tablestats-r1.txt")
  say "LOAD $lab jmx=[$(tr '\n' ' ' < "$D/load.txt")] ms=$(( t1 - t0 )) reads_r0=$r0 reads_r1=$r1 load_reads=$(( r1 - r0 ))"
  measure "$lab/A"
  log "+ sleep 25 (> denylist_refresh 20 s)"; sleep 25
  local r2; r2=$(readcount "$D/tablestats-r2.txt")
  seg_from $off > "$D/segment-A.log"
  say "SEGA $lab $(segsum "$D/segment-A.log") quiet_reads=$(( r2 - r1 ))"
  local off2; off2=$(stat -f %z "$L/node/system.log")
  # Runbook fix 2026-10-26 (defect 1): the dl-table refresh reads are counted by the READS sampler (it samples only non-empty
  # partitions, SinglePartitionReadCommand.java:911-917, :1052-1055, so the empty denylist partitions of the system_schema tables that
  # each cqlsh connection adds to the cache are not counted); it runs 40 s from 1 s before the access phase, which ends >= 10 s before it.
  log "+ nodetool profileload -a READS -k 20 system_distributed partition_denylist 40000 > $D/profileload-access.txt (background)"
  nt profileload -a READS -k 20 system_distributed partition_denylist 40000 > "$D/profileload-access.txt" 2>&1 &
  local sp=$!; sleep 1
  local a0; a0=$(date +%s); access "$D"; local a1; a1=$(date +%s)
  log "+ sleep 10"; sleep 10
  wait $sp; log "  profileload exit=$?"
  local dlreads; dlreads=$(grep -E 'partition_denylist +dl:t[1-5] ' "$D/profileload-access.txt" | awk '{s+=$3} END{print s+0}')
  local r3; r3=$(readcount "$D/tablestats-r3.txt")
  seg_from $off2 > "$D/segment-B.log"
  say "SEGB $lab $(segsum "$D/segment-B.log") access_s=$(( a1 - a0 )) access_exits=[$(grep -o 'exit=[0-9]*' "$D/access.txt" | sort | uniq -c | tr -s ' ' | tr '\n' ';')] reads_r2=$r2 reads_r3=$r3 local_read_count_delta=$(( r3 - r2 )) dl_refresh_reads_sampler=$dlreads sampler=[$(grep -E 'partition_denylist +dl:t[1-5] ' "$D/profileload-access.txt" | awk '{print $2"="$3}' | tr '\n' ';')]"
  measure "$lab/B"
}

# ------------------------------------------------------------------ pre-checks
say "cluster-run $RUN start $(now) M=$M P=$M T=[$TLIST] harness md5 $(md5 -q "$0" | cut -c1-12) Jmx md5 $(md5 -q "$H/Jmx.java" | cut -c1-12)"
say "clone: $(git -C $C rev-parse --short HEAD)"
d=$(ps -eo command | grep '[C]assandraDaemon'); [ -n "$d" ] && { say "ABORT: a CassandraDaemon is running"; exit 1; }
for p in 7000 7199 9042; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { say "ABORT: port $p busy"; exit 1; }; done
say "pre-checks: no CassandraDaemon; ports 7000 7199 9042 free; free disk $(df -h $W | tail -1 | awk '{print $4}')"
rm -rf "$N"
run "$H/make-node-conf.sh" partition_denylist_enabled=true denylist_consistency_level=ONE denylist_max_keys_per_table=$M denylist_refresh=20s
say "YAML $(sed -n '/^# ---- stage4 dlmt lines/,$p' $N/conf/cassandra.yaml | grep -v '^#' | tr '\n' ';')"

# ------------------------------------------------------------------ start
mkdir -p "$L/node"
log "+ start node (clone $C, conf $N/conf) MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M"
CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$L/node MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M nohup "$C/bin/cassandra" -f > "$L/node/node.out" 2>&1 < /dev/null &
PID=$!; disown; log "pid $PID"
t0=$(date +%s)
while :; do
  kill -0 $PID 2>/dev/null || die "node died during start"
  if nt status 2>/dev/null | grep -q '^UN  127.0.0.1 ' && [ "$(nt statusbinary 2>/dev/null)" = running ]; then log "up after $(( $(date +%s) - t0 )) s"; break; fi
  [ $(( $(date +%s) - t0 )) -ge 360 ] && die "node not up in 360 s"
  sleep 3
done
say "JVM $(grep -m1 -o 'JVM Arguments: .*' $L/node/system.log | grep -o -- '-Xm[sxn][0-9]*[GM]\|-XX:+UseG1GC' | tr '\n' ' ') initialLoad: $(grep -c 'Loaded partition denylist cache' $L/node/system.log) Loaded lines at start"
cq -e "SELECT name, value FROM system_views.settings WHERE name IN ('partition_denylist_enabled','denylist_reads_enabled','denylist_writes_enabled','denylist_range_reads_enabled','denylist_consistency_level','denylist_max_keys_per_table','denylist_max_keys_total','denylist_refresh','denylist_initial_load_retry')" > "$L/settings.txt" 2>&1
say "SETTINGS $(grep '|' "$L/settings.txt" | grep -v ' name ' | tr -s ' ' | tr '\n' ';')"
run cq -e "CREATE KEYSPACE dl WITH replication={'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE dl.t1 (k blob PRIMARY KEY, v int); CREATE TABLE dl.t2 (k blob PRIMARY KEY, v int); CREATE TABLE dl.t3 (k blob PRIMARY KEY, v int); CREATE TABLE dl.t4 (k blob PRIMARY KEY, v int); CREATE TABLE dl.t5 (k blob PRIMARY KEY, v int);"

# ------------------------------------------------------------------ B3e step 1: empty load (used_pre, recorded only)
off=$(stat -f %z "$L/node/system.log"); jmx load > "$L/pre-load.txt"; sleep 1
seg_from $off > "$L/pre-segment.log"
say "PRE load jmx=[$(tr '\n' ' ' < "$L/pre-load.txt")] $(segsum "$L/pre-segment.log")"
measure pre

# ------------------------------------------------------------------ B3e step 2: rejection
jmx set DenylistMaxKeysTotal 0 > "$L/set0.txt"
say "SET0 jmx=[$(tr '\n' ' ' < "$L/set0.txt")] readback=$(readback "$L/set0-readback.txt")"

# ------------------------------------------------------------------ B3e step 3: insert and flush (B3c)
log "+ generate 5 x $M keys of 8192 random bytes -> $N/dl.csv"
python3 -I -c "import os,sys;f=open(sys.argv[1],'w');[f.write('dl,t%d,0x%s\n'%(t,os.urandom(8192).hex())) for t in range(1,6) for _ in range(int(sys.argv[2]))]" "$N/dl.csv" "$M"
say "CSV lines=$(wc -l < "$N/dl.csv" | tr -d ' ') bytes=$(stat -f %z "$N/dl.csv")"
log "+ cqlsh COPY system_distributed.partition_denylist FROM $N/dl.csv WITH MAXBATCHSIZE=1 AND CHUNKSIZE=50"
cq -e "COPY system_distributed.partition_denylist (ks_name, table_name, key) FROM '$N/dl.csv' WITH MAXBATCHSIZE=1 AND CHUNKSIZE=50" > "$L/copy.log" 2>&1
say "COPY exit=$? $(grep -E 'rows imported|Processed:|Failed' "$L/copy.log" | tail -2 | tr '\n' ';')"
run nt flush system_distributed
: > "$L/rows.txt"; rows=""
for t in 1 2 3 4 5; do cq -e "SELECT count(*) FROM system_distributed.partition_denylist WHERE ks_name='dl' AND table_name='t$t'" > "$L/rows-t$t.txt" 2>&1; rows="$rows t$t=$(sed -n '4p' "$L/rows-t$t.txt" | tr -d ' ')"; done
say "ROWS$rows"
measure ingest
log "+ sleep 30 (drift control)"; sleep 30
measure ingest2

# ------------------------------------------------------------------ B3e step 4
i=0; for T in $TLIST; do i=$((i+1)); label "L$i-T$T" $T; done

# ------------------------------------------------------------------ cleanup (B4)
stop_node
final_check
say "cluster-run $RUN end $(now)"
