#!/usr/bin/env bash
# Cluster tier (B3, as amended 2026-10-26) of denylist_max_keys_total-getDenylistForAllTablesFromCQL-totalProcessed--autonomous.
# usage: cluster-run.sh <run> <M> <T list, comma-separated>
#   cluster-run.sh run1  1000 1,1000,2500,10000     run 1: 4 tables x 1000 keys of 32 KiB, per table 1000, phase 2 at T = 1000
#   cluster-run.sh shake 100  1,100,250,10000       shakedown (per table 100, phase 2 at T = 100; WAIT_LOADED/WAIT_BASE may be shortened)
# One node on 127.0.0.1 from $W/cassandra-run41, 2 GiB heap (G1), memtable_allocation_type offheap_buffers, file_cache_size 32MiB,
# denylist CL ONE, per table = M. Order (B3e amendment): setup (enabled false; schema, insert, row check, flush) -> B0a (enabled
# false) -> one start per T (enabled true, refresh 86400s) -> P2 (T = M, refresh 20s, two read rounds) -> B0b (enabled false).
# Each start has its own log dir. Readings: 3 x jcmd GC.class_histogram 10 s apart from Loaded + WAIT_LOADED s (enabled) or
# Startup complete + WAIT_BASE s (baseline). Phase-2 refresh evidence: nodetool profileload READS sampler. Settings read back from
# system_views.settings after the histograms. Data under $W/node-dl41 (wiped at start and end).
# Logs: $W/logs/denylist_max_keys_total-getDenylistForAllTablesFromCQL-totalProcessed/cluster-<run>/
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
H=$(cd "$(dirname "$0")" && pwd)
RUN=${1:?run}; M=${2:?M}; TLIST=${3:?T list}
WAIT_LOADED=${WAIT_LOADED:-60}; WAIT_BASE=${WAIT_BASE:-120}
L=$W/logs/denylist_max_keys_total-getDenylistForAllTablesFromCQL-totalProcessed/cluster-$RUN
rm -rf "$L"; mkdir -p "$L"; CL=$L/commands.log; S=$L/summary.txt; : > "$CL"; : > "$S"
C=$W/cassandra-run41; N=$W/node-dl41
DAEMON=Cassandra"Daemon"
PID=""
now() { date '+%Y-%m-%dT%H:%M:%S%z'; }
log() { echo "[$(now)] $*" >> "$CL"; }
say() { echo "$*" >> "$S"; log "SUMMARY $*"; }
tmo() { perl -e '$t=shift; $p=fork; if(!$p){exec @ARGV; exit 127} $SIG{ALRM}=sub{kill 9,$p; waitpid $p,0; exit 124}; alarm $t; waitpid $p,0; exit($?>>8)' "$@"; }
nt()  { tmo 300 "$C/bin/nodetool" -h 127.0.0.1 -p 7199 "$@"; }
cq()  { HOME=$W/home tmo 600 "$C/bin/cqlsh" 127.0.0.1 --request-timeout=120 "$@"; }
run() { log "+ $*"; "$@" >> "$CL" 2>&1; local rc=$?; log "  exit=$rc"; return $rc; }
die() { say "ABORT: $*"; stop_node; final_check; exit 1; }
stop_node() {
  [ -z "$PID" ] && return 0
  kill -0 $PID 2>/dev/null || { PID=""; return 0; }
  run tmo 120 "$C/bin/nodetool" -h 127.0.0.1 -p 7199 drain
  kill $PID 2>/dev/null; for i in $(seq 1 60); do kill -0 $PID 2>/dev/null || break; sleep 1; done
  kill -0 $PID 2>/dev/null && { log "kill -9 $PID"; kill -9 $PID; sleep 1; }
  PID=""; log "node stopped"
}
final_check() {
  local d; d=$(ps -eo command | grep "[C]assandra""Daemon"); say "final daemon processes: ${d:-none}"
  pgrep -f cqlsh >/dev/null && say "WARNING: cqlsh still running" || say "no cqlsh left"
  pgrep jcmd >/dev/null && say "WARNING: jcmd still running" || say "no jcmd left"
  run rm -rf "$N"; say "node-dl41 wiped: $([ -e "$N" ] && echo no || echo yes)"
}
conf() {   # conf <enabled> <T> <refresh>
  run "$H/make-node-conf.sh" partition_denylist_enabled=$1 denylist_consistency_level=ONE denylist_max_keys_per_table=$M \
      denylist_max_keys_total=$2 denylist_refresh=$3 file_cache_size=32MiB memtable_allocation_type=offheap_buffers
}
start_node() {   # start_node <dir>
  local D=$1; mkdir -p "$D/node"
  sed -n '/^# ---- stage4 dl41 lines/,$p' "$N/conf/cassandra.yaml" > "$D/yaml-tail.txt"
  log "+ start node (clone $C, conf $N/conf, logs $D/node) MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M"
  CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$D/node MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M nohup "$C/bin/cassandra" -f > "$D/node/node.out" 2>&1 < /dev/null &
  PID=$!; disown; log "pid $PID"
}
wait_line() {   # wait_line <system.log> <pattern> <timeout s>
  local t0; t0=$(date +%s)
  while :; do
    kill -0 $PID 2>/dev/null || die "node died while waiting for '$2'"
    grep -q "$2" "$1" 2>/dev/null && { log "line '$2' after $(( $(date +%s) - t0 )) s"; return 0; }
    [ $(( $(date +%s) - t0 )) -ge $3 ] && die "no '$2' in $3 s"
    sleep 1
  done
}
wait_up() {
  local t0; t0=$(date +%s)
  while :; do
    kill -0 $PID 2>/dev/null || die "node died during start"
    if nt status 2>/dev/null | grep -q '^UN  127.0.0.1 ' && [ "$(nt statusbinary 2>/dev/null)" = running ]; then log "up after $(( $(date +%s) - t0 )) s"; return 0; fi
    [ $(( $(date +%s) - t0 )) -ge 360 ] && die "node not up in 360 s"
    sleep 3
  done
}
histo() {   # histo <dir> <prefix>: 3 class histograms 10 s apart
  local i
  for i in 1 2 3; do
    log "+ jcmd $PID GC.class_histogram > $1/$2-$i.txt"
    jcmd $PID GC.class_histogram > "$1/$2-$i.txt" 2>&1
    say "HIST $(basename $1)/$2-$i $(date +%H:%M:%S) byteArray_B=$(awk '$4=="[B"{print $3; exit}' "$1/$2-$i.txt") LongToken_n=$(awk '$4=="org.apache.cassandra.dht.Murmur3Partitioner$LongToken"{print $2; exit}' "$1/$2-$i.txt") HeapByteBuffer_n=$(awk '$4=="java.nio.HeapByteBuffer"{print $2; exit}' "$1/$2-$i.txt") DenylistEntry_n=$(awk '$4=="org.apache.cassandra.schema.PartitionDenylist$DenylistEntry"{print $2; exit}' "$1/$2-$i.txt") Total_B=$(awk '$1=="Total"{print $3}' "$1/$2-$i.txt")"
    [ $i -lt 3 ] && sleep 10
  done
}
segsum() {   # counts of the denylist lines in a log file or segment
  echo "loaded=$(grep -c 'Loaded partition denylist cache in' "$1") hitlimit=$(grep -c 'Hit limit on allowable denylisted keys in total' "$1") hit_detail=[$(grep -o 'Processed [0-9]* total entries. Not adding all entries to denylist for [a-z_]*/t[0-9]' "$1" | sed -E 's/Processed ([0-9]*) .* for (.*)/\1:\2/' | tr '\n' ';')] exceeded=$(grep -c 'has exceeded the [a-z-]* allowance' "$1") exceeded_detail=[$(grep -o '[a-z_]*/t[0-9] has exceeded the [a-z-]* allowance of ([0-9]*)' "$1" | sed -E 's/ has exceeded the ([a-z-]*) allowance of \(([0-9]*)\)/:\1:\2/' | tr '\n' ';')] read_errors=$(grep -c 'Error reading partition_denylist\|Error reading full partition denylist' "$1")"
}
settings() {   # settings <dir>
  cq -e "SELECT name, value FROM system_views.settings WHERE name IN ('partition_denylist_enabled','denylist_reads_enabled','denylist_consistency_level','denylist_max_keys_per_table','denylist_max_keys_total','denylist_refresh','memtable_allocation_type','file_cache_size')" > "$1/settings.txt" 2>&1
  say "SETTINGS $(basename $1) $(grep '|' "$1/settings.txt" | grep -v ' name ' | tr -s ' ' | tr '\n' ';')"
}
config() {   # config <label> <enabled> <T> <refresh>
  local lab=$1 D=$L/$1; mkdir -p "$D"
  say "== $lab: enabled=$2 T=$3 refresh=$4 $(now)"
  conf $2 $3 $4; start_node "$D"
  if [ "$2" = true ]; then
    wait_line "$D/node/system.log" 'Loaded partition denylist cache' 360; say "LOADED $lab $(now) $(grep -m1 -o 'Loaded partition denylist cache in [0-9]*ms' $D/node/system.log)"
    log "+ sleep $WAIT_LOADED"; sleep $WAIT_LOADED
  else
    wait_line "$D/node/system.log" 'Startup complete' 360; say "STARTED $lab $(now)"
    log "+ sleep $WAIT_BASE"; sleep $WAIT_BASE
  fi
  wait_up
  say "JVM $lab $(grep -m1 -o 'JVM Arguments: .*' $D/node/system.log | grep -o -- '-Xm[sxn][0-9]*[GM]\|-XX:+UseG1GC' | tr '\n' ' ')"
}

# ------------------------------------------------------------------ pre-checks
say "cluster-run $RUN start $(now) M=$M T=[$TLIST] WAIT_LOADED=$WAIT_LOADED WAIT_BASE=$WAIT_BASE harness md5 $(md5 -q "$0" | cut -c1-12) insert md5 $(md5 -q "$H/insert_dl.py" | cut -c1-12)"
say "clone: $(git -C $C rev-parse --short HEAD)"
d=$(ps -eo command | grep "[C]assandra""Daemon"); [ -n "$d" ] && { say "ABORT: a daemon is running"; exit 1; }
for p in 7000 7199 9042; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { say "ABORT: port $p busy"; exit 1; }; done
say "pre-checks: no daemon; ports 7000 7199 9042 free; free disk $(df -h $W | tail -1 | awk '{print $4}')"
rm -rf "$N"

# ------------------------------------------------------------------ setup (B3c)
D=$L/setup; mkdir -p "$D"; say "== setup $(now)"
conf false 10000 86400s; start_node "$D"; wait_line "$D/node/system.log" 'Startup complete' 360; wait_up
run cq -e "CREATE KEYSPACE dl WITH replication={'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE dl.t1 (k blob PRIMARY KEY, v int); CREATE TABLE dl.t2 (k blob PRIMARY KEY, v int); CREATE TABLE dl.t3 (k blob PRIMARY KEY, v int); CREATE TABLE dl.t4 (k blob PRIMARY KEY, v int);"
ZIP=$(ls $C/lib/cassandra-driver-internal-only-*.zip | head -1)
log "+ python3 -I $H/insert_dl.py $ZIP $M $D/insert.txt"
tmo 1800 python3 -I "$H/insert_dl.py" "$ZIP" "$M" "$D/insert.txt" >> "$CL" 2>&1; say "INSERT exit=$? $(grep 'INS total' "$D/insert.txt")"
rows=""
for t in 1 2 3 4; do cq -e "SELECT count(*) FROM system_distributed.partition_denylist WHERE ks_name='dl' AND table_name='t$t'" > "$D/rows-t$t.txt" 2>&1; rows="$rows t$t=$(sed -n '4p' "$D/rows-t$t.txt" | tr -d ' ')"; done
say "ROWS$rows"
run nt flush system_distributed
run nt tablestats system_distributed.partition_denylist
stop_node
say "SETUP $(segsum $D/node/system.log)"

# ------------------------------------------------------------------ B0a
config B0a false 10000 86400s; histo "$L/B0a" hist; settings "$L/B0a"; say "LOG B0a $(segsum $L/B0a/node/system.log)"; stop_node

# ------------------------------------------------------------------ phase 1
for T in $(echo $TLIST | tr ',' ' '); do
  lab=T$T; config $lab true $T 86400s; histo "$L/$lab" hist; settings "$L/$lab"; say "LOG $lab $(segsum $L/$lab/node/system.log)"; stop_node
done

# ------------------------------------------------------------------ phase 2
lab=P2; D=$L/P2; config $lab true $M 20s
histo "$D" H0
off=$(stat -f %z "$D/node/system.log"); echo $off > "$D/offset-after-H0.txt"
nt tablestats system_distributed.partition_denylist > "$D/tablestats-r0.txt" 2>&1
log "+ nodetool profileload -a READS -k 20 system_distributed partition_denylist 95000 > $D/profileload.txt (background)"
nt profileload -a READS -k 20 system_distributed partition_denylist 95000 > "$D/profileload.txt" 2>&1 &
SP=$!
log "+ sleep 30"; sleep 30
for round in 1 2; do
  for t in 1 2 3 4; do cq -e "SELECT * FROM dl.t$t WHERE k=0x00" >> "$D/access.txt" 2>&1; echo "round $round t$t exit=$? $(date +%H:%M:%S)" >> "$D/access.txt"; done
  log "+ sleep 30"; sleep 30
done
wait $SP; log "  profileload exit=$?"
nt tablestats system_distributed.partition_denylist > "$D/tablestats-r1.txt" 2>&1
histo "$D" H1
settings "$D"
tail -c +$(( off + 1 )) "$D/node/system.log" > "$D/segment-after-H0.log"
say "LOG P2 whole $(segsum $D/node/system.log)"
say "LOG P2 after-H0 $(segsum $D/segment-after-H0.log)"
say "P2 access exits=[$(grep -o 'exit=[0-9]*' "$D/access.txt" | sort | uniq -c | tr -s ' ' | tr '\n' ';')] sampler_dl_reads=$(grep -E 'partition_denylist +dl:t[1-4] ' "$D/profileload.txt" | awk '{s+=$3} END{print s+0}') sampler=[$(grep -E 'partition_denylist +dl:t[1-4] ' "$D/profileload.txt" | awk '{print $2"="$3}' | tr '\n' ';')] localreads r0=$(grep -m1 'Local read count:' $D/tablestats-r0.txt | tr -dc '0-9') r1=$(grep -m1 'Local read count:' $D/tablestats-r1.txt | tr -dc '0-9')"
stop_node

# ------------------------------------------------------------------ B0b
config B0b false 10000 86400s; histo "$L/B0b" hist; settings "$L/B0b"; say "LOG B0b $(segsum $L/B0b/node/system.log)"; stop_node

final_check
say "cluster-run $RUN end $(now)"
