#!/usr/bin/env bash
# Cluster tier (B3, as amended 2026-10-26) of bloom_filter_fp_chance-validate-bloomFilterFpChance--autonomous.
# usage: cluster-run.sh <run> <N>
#   cluster-run.sh run1  4000000     run 1 (B3c: 4M partitions per keyspace, phase 2 another 4M into bf_001)
#   cluster-run.sh shake 100000      shakedown (not judged)
# One node on 127.0.0.1 from $W/cassandra-run42, MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M, concurrent_compactors 1, data under
# $W/node-bf42 (wiped at start and end). Order (B3e amendment): create six keyspaces (compaction disabled by nodetool) ->
# per keyspace stress + flush + record -> record ALL -> step 4 boundary ALTERs + read-back -> step 5 phase 2 on bf_001 ->
# step 6 ALTER bf_001 to 0.1 + record, upgradesstables -a + record -> drain, stop, check, wipe.
# record <label> <ks>: nodetool tablestats, stat -f %z of every Filter.db, sstablemetadata of every Data.db, process RSS.
# Logs: $W/logs/bloom_filter_fp_chance-validate-bloomFilterFpChance/cluster-<run>/
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
RUN=${1:?run}; N=${2:?N}
H=$(cd "$(dirname "$0")" && pwd)
L=$W/logs/bloom_filter_fp_chance-validate-bloomFilterFpChance/cluster-$RUN
rm -rf "$L"; mkdir -p "$L"; CL=$L/commands.log; S=$L/summary.txt; : > "$CL"; : > "$S"
C=$W/cassandra-run42; NODE=$W/node-bf42
PID=""
KS="bf_1:1.0 bf_01:0.1 bf_001:0.01 bf_0001:0.001 bf_00001:0.0001 bf_00007:0.00007"
now() { date '+%Y-%m-%dT%H:%M:%S%z'; }
log() { echo "[$(now)] $*" >> "$CL"; }
say() { echo "$*" >> "$S"; log "SUMMARY $*"; }
tmo() { perl -e '$t=shift; $p=fork; if(!$p){exec @ARGV; exit 127} $SIG{ALRM}=sub{kill 9,$p; waitpid $p,0; exit 124}; alarm $t; waitpid $p,0; exit($?>>8)' "$@"; }
nt()  { tmo 600 "$C/bin/nodetool" -h 127.0.0.1 -p 7199 "$@"; }
cq()  { HOME=$W/home tmo 300 "$C/bin/cqlsh" 127.0.0.1 --request-timeout=120 "$@"; }
run() { log "+ $*"; "$@" >> "$CL" 2>&1; local rc=$?; log "  exit=$rc"; return $rc; }
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
  run rm -rf "$NODE"; say "node-bf42 wiped: $([ -e "$NODE" ] && echo no || echo yes)"
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
record() {   # record <label> <ks>
  local lab=$1 ks=$2 d=$L/$1/$2 f tot=0 n=0
  mkdir -p "$d"
  nt tablestats "$ks.standard1" > "$d/tablestats.txt" 2>&1
  : > "$d/filter-files.txt"
  for f in "$NODE"/data/$ks/standard1-*/*-Filter.db; do
    [ -e "$f" ] || continue
    echo "$(stat -f %z "$f") $f" >> "$d/filter-files.txt"
  done
  ls -l "$NODE"/data/$ks/standard1-*/ > "$d/ls-l.txt" 2>&1
  local datas; datas=$(ls "$NODE"/data/$ks/standard1-*/*-Data.db 2>/dev/null)
  if [ -n "$datas" ]; then tmo 300 "$C/tools/bin/sstablemetadata" $datas > "$d/sstablemetadata.txt" 2>&1; else : > "$d/sstablemetadata.txt"; fi
  echo "$(ps -o rss= -p $PID | tr -d ' ') KiB" > "$d/rss.txt"
  while read -r sz _; do tot=$((tot+sz)); n=$((n+1)); done < "$d/filter-files.txt"
  say "REC $lab/$ks $(date +%H:%M:%S) sstables=$(awk -F': ' '/SSTable count/{print $2; exit}' "$d/tablestats.txt") offheap=$(awk -F': ' '/Bloom filter off heap memory used/{print $2; exit}' "$d/tablestats.txt") space=$(awk -F': ' '/Bloom filter space used/{print $2; exit}' "$d/tablestats.txt") filterdb_files=$n filterdb_bytes=$tot totalRows=$(awk '/^totalRows:/{s+=$2} END{print s+0}' "$d/sstablemetadata.txt") fpchances=$(awk '/^Bloom Filter FP chance:/{print $5}' "$d/sstablemetadata.txt" | sort | uniq -c | tr -s ' ' | tr '\n' ',') rss=$(cat "$d/rss.txt" | tr -d ' ')"
}
stress() {   # stress <ks> <from> <to> <tag>
  local ks=$1 a=$2 b=$3 out=$L/stress-$4-$1.txt
  log "+ cassandra-stress write n=$((b-a+1)) cl=ONE -pop seq=$a..$b -schema keyspace=$ks -rate threads=64 -node 127.0.0.1 > $out"
  tmo 3600 "$C/tools/bin/cassandra-stress" write n=$((b-a+1)) cl=ONE -pop seq=$a..$b -schema keyspace=$ks -rate threads=64 -node 127.0.0.1 > "$out" 2>&1 < /dev/null
  local rc=$?
  say "STRESS $4/$ks exit=$rc $(grep -m1 'Total partitions' "$out" | tr -s ' ') | $(grep -m1 'Total errors' "$out" | tr -s ' ') | $(grep -m1 'Op rate' "$out" | tr -s ' ') | $(grep -m1 'Total operation time' "$out" | tr -s ' ')"
  run nt flush "$ks" standard1 || die "flush $ks failed"
}

say "cluster-run $RUN N=$N start $(now) clone $(git -C $C describe --tags) $(git -C $C rev-parse --short HEAD)"
[ -n "$(ps -eo command | grep "[C]assandra""Daemon")" ] && { say "ABORT: a daemon is already running"; exit 1; }
rm -rf "$NODE"
run "$H/make-node-conf.sh" concurrent_compactors=1 || die "conf"
sed -n '/^# ---- stage4 bf42 lines/,$p' "$NODE/conf/cassandra.yaml" > "$L/yaml-tail.txt"
mkdir -p "$L/node"
log "+ start node CASSANDRA_CONF=$NODE/conf MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M"
CASSANDRA_CONF=$NODE/conf CASSANDRA_LOG_DIR=$L/node MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M nohup "$C/bin/cassandra" -f > "$L/node/node.out" 2>&1 < /dev/null &
PID=$!; disown; log "pid $PID"
wait_up
say "JVM $(grep -m1 -o 'JVM Arguments: .*' $L/node/system.log | grep -o -- '-Xm[sx][^,]*\|-XX:+UseG1GC\|-Xmn[^,]*' | tr '\n' ' ')"

# step 2: keyspaces and tables
for kv in $KS; do
  ks=${kv%%:*}; fp=${kv#*:}
  run cq -e "CREATE KEYSPACE $ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE $ks.standard1 (key blob PRIMARY KEY, \"C0\" blob, \"C1\" blob, \"C2\" blob, \"C3\" blob, \"C4\" blob) WITH bloom_filter_fp_chance = $fp AND compression = {};" || die "create $ks"
  run nt disableautocompaction "$ks" standard1 || die "disableautocompaction $ks"
done
cq -e "SELECT keyspace_name, bloom_filter_fp_chance, compression, compaction FROM system_schema.tables WHERE keyspace_name IN ('bf_1','bf_01','bf_001','bf_0001','bf_00001','bf_00007');" > "$L/schema.txt" 2>&1
say "SCHEMA $(grep -c 'bf_' "$L/schema.txt") bf_ rows"

# step 3: per keyspace stress, flush, record
for kv in $KS; do
  ks=${kv%%:*}
  stress "$ks" 1 "$N" P1
  record P1 "$ks"
done
for kv in $KS; do record ALL "${kv%%:*}"; done
nt compactionhistory > "$L/compactionhistory-ALL.txt" 2>&1
say "COMPACTIONHISTORY ALL bf_lines=$(grep -c ' bf_' "$L/compactionhistory-ALL.txt")"
say "FORMAT data files: $(ls "$NODE"/data/bf_*/standard1-*/*-Data.db | sed 's/.*\///' | sed 's/-[0-9]*-/-N-/' | sort | uniq -c | tr -s ' ' | tr '\n' ',')"

# step 4: boundary ALTERs
for v in 0.0000671 1.01; do
  cq -e "ALTER TABLE bf_01.standard1 WITH bloom_filter_fp_chance = $v;" > "$L/alter-$v.txt" 2>&1; rc=$?
  log "+ ALTER TABLE bf_01.standard1 WITH bloom_filter_fp_chance = $v -> exit=$rc"
  say "ALTER $v exit=$rc $(tr '\n' ' ' < "$L/alter-$v.txt" | cut -c1-300)"
done
cq -e "SELECT bloom_filter_fp_chance FROM system_schema.tables WHERE keyspace_name='bf_01' AND table_name='standard1';" > "$L/readback-bf_01.txt" 2>&1
say "READBACK bf_01 $(tr -s ' \n' ' ' < "$L/readback-bf_01.txt")"

# step 5: phase 2 on bf_001
stress bf_001 $((N+1)) $((2*N)) P2
record P2 bf_001

# step 6: ALTER to 0.1, then upgradesstables -a
run cq -e "ALTER TABLE bf_001.standard1 WITH bloom_filter_fp_chance = 0.1;" || say "WARNING: ALTER bf_001 to 0.1 failed"
cq -e "SELECT bloom_filter_fp_chance FROM system_schema.tables WHERE keyspace_name='bf_001' AND table_name='standard1';" > "$L/readback-bf_001.txt" 2>&1
say "READBACK bf_001 $(tr -s ' \n' ' ' < "$L/readback-bf_001.txt")"
sleep 5
record S6a bf_001
nt compactionhistory > "$L/compactionhistory-S6a.txt" 2>&1
say "COMPACTIONHISTORY S6a bf_lines=$(grep -c ' bf_' "$L/compactionhistory-S6a.txt")"
run nt upgradesstables -a bf_001 standard1 || say "WARNING: upgradesstables failed"
sleep 5
record S6b bf_001
nt compactionhistory > "$L/compactionhistory-S6b.txt" 2>&1
say "COMPACTIONHISTORY S6b bf_lines=$(grep -c ' bf_' "$L/compactionhistory-S6b.txt")"

grep -c '^ERROR' "$L/node/system.log" > "$L/error-count.txt"; say "system.log ERROR lines: $(cat "$L/error-count.txt")"
stop_node
final_check
say "end $(now)"
