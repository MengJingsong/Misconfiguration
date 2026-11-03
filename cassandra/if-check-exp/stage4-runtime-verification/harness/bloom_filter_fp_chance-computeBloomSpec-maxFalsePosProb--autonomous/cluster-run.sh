#!/usr/bin/env bash
# Cluster tier (B3, as amended 2026-10-27, C1-C6) of bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous.
# usage: cluster-run.sh <run> <N>
#   cluster-run.sh r1    10000000   run 1 (B3c: 10M partitions; CTRL adds another 10M)
#   cluster-run.sh shake 200000     shakedown (not judged)
# One node on 127.0.0.1 from $W/cassandra-run58, MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M, conf/data under $W/node-bfcs (wiped at start
# and end), JVM_EXTRA_OPTS = NMT summary + Byteman agent with bf.btm (observe-only; lines "BMBF ..." on node.out). The STDOUT
# appender is removed from the node's logback.xml so node.out carries the Byteman lines only (system.log is unchanged).
# Order (C4): stress, flush, compact, idle -> LOAD; NMT baseline -> B0; per fp ALTER, read back, upgradesstables -a, idle -> F<fp>;
# ALTER 0.00006 (expect refusal) + read back; ALTER 0.01, stress seq N+1..2N, flush, compact, idle -> CTRL; drain, stop, check, wipe.
# Node mechanics (tmo, nt, cq, run, stop_node, final_check, wait_up) adapted from
# harness/bloom_filter_fp_chance-validate-bloomFilterFpChance--autonomous/cluster-run.sh (that file is not modified).
# Logs: $W/logs/bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous/cluster-<run>/
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
RUN=${1:?run}; N=${2:?N}
H=$(cd "$(dirname "$0")" && pwd)
L=$W/logs/bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous/cluster-$RUN
rm -rf "$L"; mkdir -p "$L"; CL=$L/commands.log; S=$L/summary.txt; : > "$CL"; : > "$S"
export C; C=${C:-$W/cassandra-run58}; NODE=$W/node-bfcs   # C overridable (cluster re-run 2026-10-27: C=$W/cassandra-run69)
PID=""; NMTBASE=0
FPS="1.0 0.5 0.1 0.01 0.001 0.0001"
now() { date '+%Y-%m-%dT%H:%M:%S%z'; }
log() { echo "[$(now)] $*" >> "$CL"; }
say() { echo "$*" >> "$S"; log "SUMMARY $*"; }
tmo() { perl -e '$t=shift; $p=fork; if(!$p){exec @ARGV; exit 127} $SIG{ALRM}=sub{kill 9,$p; waitpid $p,0; exit 124}; alarm $t; waitpid $p,0; exit($?>>8)' "$@"; }
nt()  { tmo 600 "$C/bin/nodetool" -h 127.0.0.1 -p 7199 "$@"; }
ntl() { tmo 3600 "$C/bin/nodetool" -h 127.0.0.1 -p 7199 "$@"; }
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
  run rm -rf "$NODE"; say "node-bfcs wiped: $([ -e "$NODE" ] && echo no || echo yes)"
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
idle_wait() {   # pending tasks 0 and SSTable count 1, then 5 s
  local t0; t0=$(date +%s)
  while :; do
    local p c
    p=$(nt compactionstats 2>/dev/null | awk '/^pending tasks/{print $NF; exit}')
    c=$(nt tablestats keyspace1.standard1 2>/dev/null | awk -F': ' '/SSTable count/{print $2; exit}' | tr -d ' ')
    if [ "$p" = 0 ] && [ "$c" = 1 ]; then log "idle after $(( $(date +%s) - t0 )) s (pending $p, sstables $c)"; sleep 5; return 0; fi
    [ $(( $(date +%s) - t0 )) -ge 1800 ] && { say "WARNING: not idle after 1800 s (pending $p, sstables $c)"; return 1; }
    sleep 3
  done
}
sample() {   # sample <label>
  local lab=$1 d=$L/$1 f tot=0 n=0
  mkdir -p "$d"
  echo "$(stat -f %z "$L/node/node.out")" > "$d/nodeout-offset.txt"
  nt tablestats keyspace1.standard1 > "$d/tablestats.txt" 2>&1
  : > "$d/filter-files.txt"
  for f in "$NODE"/data/keyspace1/standard1-*/*-Filter.db; do [ -e "$f" ] && echo "$(stat -f %z "$f") $f" >> "$d/filter-files.txt"; done
  : > "$d/data-files.txt"
  for f in "$NODE"/data/keyspace1/standard1-*/*-Data.db; do [ -e "$f" ] && echo "$(stat -f %z "$f") $f" >> "$d/data-files.txt"; done
  local datas; datas=$(ls "$NODE"/data/keyspace1/standard1-*/*-Data.db 2>/dev/null)
  if [ -n "$datas" ]; then tmo 600 "$C/tools/bin/sstablemetadata" $datas > "$d/sstablemetadata.txt" 2>&1; else : > "$d/sstablemetadata.txt"; fi
  [ "$NMTBASE" = 1 ] && jcmd $PID VM.native_memory summary.diff > "$d/nmt-diff.txt" 2>&1
  echo "$(ps -o rss= -p $PID | tr -d ' ') KiB" > "$d/rss.txt"
  while read -r sz _; do tot=$((tot+sz)); n=$((n+1)); done < "$d/filter-files.txt"
  say "SAMPLE $lab $(date +%H:%M:%S) sstables=$(awk -F': ' '/SSTable count/{print $2; exit}' "$d/tablestats.txt") n_est=$(awk -F': ' '/Number of partitions \(estimate\)/{print $2; exit}' "$d/tablestats.txt") offheap=$(awk -F': ' '/Bloom filter off heap memory used/{print $2; exit}' "$d/tablestats.txt") space=$(awk -F': ' '/Bloom filter space used/{print $2; exit}' "$d/tablestats.txt") filterdb_files=$n filterdb_bytes=$tot data=$(sed 's/.*\///' "$d/data-files.txt" | tr '\n' ',') totalRows=$(awk '/^totalRows:/{s+=$2} END{print s+0}' "$d/sstablemetadata.txt") fpchance=$(awk '/^Bloom Filter FP chance:/{print $5}' "$d/sstablemetadata.txt" | tr '\n' ',') nmt_other=$(grep -m1 -- '- *Other' "$d/nmt-diff.txt" 2>/dev/null | tr -s ' ') offset=$(cat "$d/nodeout-offset.txt") rss=$(cat "$d/rss.txt" | tr -d ' ')"
}
stress() {   # stress <from> <to> <tag>
  local a=$1 b=$2 out=$L/stress-$3.txt
  log "+ cassandra-stress write n=$((b-a+1)) no-warmup cl=ONE -pop seq=$a..$b -col n=FIXED(1) size=FIXED(16) -rate threads=50 -node 127.0.0.1 > $out"
  tmo 7200 "$C/tools/bin/cassandra-stress" write n=$((b-a+1)) no-warmup cl=ONE -pop seq=$a..$b -col 'n=FIXED(1)' 'size=FIXED(16)' -rate threads=50 -node 127.0.0.1 > "$out" 2>&1 < /dev/null
  local rc=$?
  say "STRESS $3 exit=$rc $(grep -m1 'Total partitions' "$out" | tr -s ' ') | $(grep -m1 'Total errors' "$out" | tr -s ' ') | $(grep -m1 'Op rate' "$out" | tr -s ' ') | $(grep -m1 'Total operation time' "$out" | tr -s ' ')"
  run nt flush keyspace1 standard1 || die "flush failed"
  run ntl compact keyspace1 standard1 || die "compact failed"
  idle_wait || die "not idle after load"
}
alter() {   # alter <fp> <tag>
  cq -e "ALTER TABLE keyspace1.standard1 WITH bloom_filter_fp_chance = $1;" > "$L/alter-$2.txt" 2>&1; local rc=$?
  log "+ ALTER TABLE keyspace1.standard1 WITH bloom_filter_fp_chance = $1 -> exit=$rc"
  cq -e "SELECT bloom_filter_fp_chance FROM system_schema.tables WHERE keyspace_name='keyspace1' AND table_name='standard1';" > "$L/readback-$2.txt" 2>&1
  say "ALTER $2 value=$1 exit=$rc out=[$(tr '\n' ' ' < "$L/alter-$2.txt" | cut -c1-300)] readback=[$(tr -s ' \n' ' ' < "$L/readback-$2.txt")]"
  return $rc
}

say "cluster-run $RUN N=$N start $(now) clone $(git -C $C describe --tags) $(git -C $C rev-parse --short HEAD) bf.btm sha256 $(shasum -a 256 "$H/bf.btm" | cut -c1-16)"
[ -n "$(ps -eo command | grep "[C]assandra""Daemon")" ] && { say "ABORT: a daemon is already running"; exit 1; }
rm -rf "$NODE"
run "$H/make-node-conf.sh" auto_snapshot=false || die "conf"
sed -i '' 's#<appender-ref ref="STDOUT" */>##' "$NODE/conf/logback.xml"
say "logback STDOUT refs left: $(grep -c 'appender-ref ref="STDOUT"' "$NODE/conf/logback.xml")"
sed -n '/^# ---- stage4 bfcs lines/,$p' "$NODE/conf/cassandra.yaml" > "$L/yaml-tail.txt"
mkdir -p "$L/node"
XO="-XX:NativeMemoryTracking=summary -javaagent:$C/build/lib/jars/byteman-4.0.20.jar=script:$H/bf.btm"
log "+ start node CASSANDRA_CONF=$NODE/conf MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M JVM_EXTRA_OPTS=$XO"
CASSANDRA_CONF=$NODE/conf CASSANDRA_LOG_DIR=$L/node MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M JVM_EXTRA_OPTS="$XO" nohup "$C/bin/cassandra" -f > "$L/node/node.out" 2>&1 < /dev/null &
PID=$!; disown; log "pid $PID"
wait_up
say "JVM $(grep -m1 -o 'JVM Arguments: .*' $L/node/system.log | grep -o -- '-Xm[sx][^,]*\|-XX:NativeMemoryTracking=[a-z]*\|-javaagent:[^,]*' | tr '\n' ' ')"
say "auto_snapshot: $(grep -m1 -o 'auto_snapshot=[a-z]*' $L/node/system.log)"
say "BMBF lines at start: $(grep -c '^BMBF ' $L/node/node.out)"

# (2) load
stress 1 "$N" LOAD
cq -e "SELECT keyspace_name, table_name, bloom_filter_fp_chance, compaction FROM system_schema.tables WHERE keyspace_name='keyspace1';" > "$L/schema.txt" 2>&1
say "SCHEMA $(tr -s ' \n' ' ' < "$L/schema.txt" | cut -c1-400)"
sample LOAD
# (3) baseline
run jcmd $PID VM.native_memory baseline; NMTBASE=1
sample B0
# (4) per fp
for fp in $FPS; do
  alter "$fp" "F$fp" || say "WARNING: ALTER $fp failed"
  run ntl upgradesstables -a keyspace1 standard1 || say "WARNING: upgradesstables at $fp failed"
  idle_wait
  sample "F$fp"
done
# (5) below the minimum
alter 0.00006 REJ
# (6) positive control
alter 0.01 CTRL || say "WARNING: ALTER 0.01 failed"
stress $((N+1)) $((2*N)) CTRL
sample CTRL

grep -c '^ERROR' "$L/node/system.log" > "$L/error-count.txt"; say "system.log ERROR lines: $(cat "$L/error-count.txt")"
say "BMBF lines total: $(grep -c '^BMBF ' $L/node/node.out); other node.out lines: $(grep -vc '^BMBF ' $L/node/node.out)"
stop_node
final_check
say "end $(now)"
