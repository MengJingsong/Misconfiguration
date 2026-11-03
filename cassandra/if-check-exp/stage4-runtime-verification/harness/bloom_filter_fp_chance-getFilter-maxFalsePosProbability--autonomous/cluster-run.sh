#!/usr/bin/env bash
# Cluster tier (B3, as amended 2026-10-27, C1-C6) of bloom_filter_fp_chance-getFilter-maxFalsePosProbability--autonomous.
# usage: cluster-run.sh <run> <N>
#   cluster-run.sh r1    2000000   run 1 (B3c: N = 2M into keyspace1; the ks_ctl control loads 2N = 4M)
#   cluster-run.sh shake 200000    shakedown (not judged)
# One node on 127.0.0.1 from $W/cassandra-run59, MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M, conf/data under $W/node-bfgf (wiped at start
# and end), JVM_EXTRA_OPTS = NMT summary + Byteman agent with bf-node.btm (observe-only; "BMBF ..." lines on node.out / node2.out).
# The STDOUT appender is removed from the node's logback.xml so node.out carries the Byteman lines only (system.log is unchanged).
# Sequence C3: start; stress N; flush; disableautocompaction; compact; idle -> R0; per fp 0.001 0.1 0.5 1.0 0.01: ALTER, read back,
# upgradesstables -a, idle -> F<fp>; ALTER 1.0 -> S5a; restart -> S5b; stress 2N into ks_ctl, flush, compact, idle -> CTRL; stop, check, wipe.
# Node mechanics (tmo, nt, cq, run, stop_node, final_check, wait_up, idle_wait, sample, alter) adapted from
# harness/bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous/cluster-run.sh (that file is not modified).
# Runbook-defect fix D1 (2026-10-27): idle_wait no longer requires pending tasks 0 (stale under disableautocompaction).
# Logs: $W/logs/bloom_filter_fp_chance-getFilter-maxFalsePosProbability--autonomous/cluster-<run>/
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
RUN=${1:?run}; N=${2:?N}
H=$(cd "$(dirname "$0")" && pwd)
L=$W/logs/bloom_filter_fp_chance-getFilter-maxFalsePosProbability--autonomous/cluster-$RUN
rm -rf "$L"; mkdir -p "$L/node"; CL=$L/commands.log; S=$L/summary.txt; : > "$CL"; : > "$S"
C=$W/cassandra-run59; NODE=$W/node-bfgf
PID=""; NMTBASE=0; OUT=$L/node/node.out
XO="-XX:NativeMemoryTracking=summary -javaagent:$C/build/lib/jars/byteman-4.0.20.jar=script:$H/bf-node.btm"
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
  run rm -rf "$NODE"; say "node-bfgf wiped: $([ -e "$NODE" ] && echo no || echo yes)"
}
start_node() {   # start_node <stdout file>
  OUT=$1
  log "+ start node CASSANDRA_CONF=$NODE/conf MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M JVM_EXTRA_OPTS=$XO > $OUT"
  CASSANDRA_CONF=$NODE/conf CASSANDRA_LOG_DIR=$L/node MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M JVM_EXTRA_OPTS="$XO" nohup "$C/bin/cassandra" -f > "$OUT" 2>&1 < /dev/null &
  PID=$!; disown; log "pid $PID"; NMTBASE=0
  wait_up
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
idle_wait() {   # idle_wait <ks> : (D1 fix, 2026-10-27) no active compaction listed and SSTable count 1 for <ks>.standard1, then 5 s
  local ks=$1 t0; t0=$(date +%s)
  while :; do
    local p a c cs
    cs=$(nt compactionstats 2>/dev/null)
    p=$(echo "$cs" | awk '/^pending tasks/{print $NF; exit}')
    a=$(echo "$cs" | grep -c 'compaction type')
    c=$(nt tablestats $ks.standard1 2>/dev/null | awk -F': ' '/SSTable count/{print $2; exit}' | tr -d ' ')
    if [ "$a" = 0 ] && [ "$c" = 1 ]; then log "idle after $(( $(date +%s) - t0 )) s (active $a, pending $p (not used, D1), sstables $c)"; sleep 5; return 0; fi
    [ $(( $(date +%s) - t0 )) -ge 1800 ] && { say "WARNING: not idle after 1800 s (active $a, pending $p, sstables $c)"; return 1; }
    sleep 3
  done
}
live_bitset() {   # live bit-set bytes (>= 65536 per bit set) in $OUT before byte offset $1
  head -c "$1" "$OUT" | awk '$1=="BMBF" && ($2=="BA"||$2=="BC") && $3>=65536 {if($2=="BA") s+=$3; else s-=$3} END{print s+0}'
}
sample() {   # sample <label> <ks>
  local lab=$1 ks=$2 d=$L/$1 f tot=0 n=0 off
  mkdir -p "$d"
  off=$(stat -f %z "$OUT"); echo "$(basename "$OUT") $off" > "$d/nodeout-offset.txt"
  nt tablestats $ks.standard1 > "$d/tablestats.txt" 2>&1
  : > "$d/filter-files.txt"
  for f in "$NODE"/data/$ks/standard1-*/*-Filter.db; do [ -e "$f" ] && echo "$(stat -f %z "$f") $f" >> "$d/filter-files.txt"; done
  : > "$d/data-files.txt"
  for f in "$NODE"/data/$ks/standard1-*/*-Data.db; do [ -e "$f" ] && echo "$(stat -f %z "$f") $f" >> "$d/data-files.txt"; done
  local datas; datas=$(ls "$NODE"/data/$ks/standard1-*/*-Data.db 2>/dev/null)
  if [ -n "$datas" ]; then tmo 600 "$C/tools/bin/sstablemetadata" $datas > "$d/sstablemetadata.txt" 2>&1; else : > "$d/sstablemetadata.txt"; fi
  if [ "$NMTBASE" = 1 ]; then jcmd $PID VM.native_memory summary.diff > "$d/nmt-diff.txt" 2>&1; else jcmd $PID VM.native_memory summary > "$d/nmt.txt" 2>&1; fi
  echo "$(ps -o rss= -p $PID | tr -d ' ') KiB" > "$d/rss.txt"
  while read -r sz _; do tot=$((tot+sz)); n=$((n+1)); done < "$d/filter-files.txt"
  say "SAMPLE $lab ks=$ks $(date +%H:%M:%S) sstables=$(awk -F': ' '/SSTable count/{print $2; exit}' "$d/tablestats.txt") n_est=$(awk -F': ' '/Number of partitions \(estimate\)/{print $2; exit}' "$d/tablestats.txt") offheap=$(awk -F': ' '/Bloom filter off heap memory used/{print $2; exit}' "$d/tablestats.txt") space=$(awk -F': ' '/Bloom filter space used/{print $2; exit}' "$d/tablestats.txt") filterdb_files=$n filterdb_bytes=$tot live_bitset=$(live_bitset "$off") data=$(sed 's/.*\///' "$d/data-files.txt" | tr '\n' ',') totalRows=$(awk '/^totalRows:/{s+=$2} END{print s+0}' "$d/sstablemetadata.txt") fpchance=$(awk '/^Bloom Filter FP chance:/{print $5}' "$d/sstablemetadata.txt" | tr '\n' ',') nmt_other=$(grep -m1 -- '- *Other' "$d/nmt-diff.txt" "$d/nmt.txt" 2>/dev/null | tr -s ' ') out=$(basename "$OUT"):$off rss=$(tr -d ' ' < "$d/rss.txt")"
}
stress() {   # stress <n> <tag> [extra args]
  local n=$1 tag=$2; shift 2; local out=$L/stress-$tag.txt
  log "+ cassandra-stress write n=$n cl=ONE -rate threads=32 -node 127.0.0.1 $* > $out"
  tmo 7200 "$C/tools/bin/cassandra-stress" write n=$n cl=ONE -rate threads=32 -node 127.0.0.1 "$@" > "$out" 2>&1 < /dev/null
  local rc=$?
  say "STRESS $tag exit=$rc $(grep -m1 'Total partitions' "$out" | tr -s ' ') | $(grep -m1 'Total errors' "$out" | tr -s ' ') | $(grep -m1 'Op rate' "$out" | tr -s ' ') | $(grep -m1 'Total operation time' "$out" | tr -s ' ')"
  return $rc
}
alter() {   # alter <fp> <tag>
  cq -e "ALTER TABLE keyspace1.standard1 WITH bloom_filter_fp_chance = $1;" > "$L/alter-$2.txt" 2>&1; local rc=$?
  log "+ ALTER TABLE keyspace1.standard1 WITH bloom_filter_fp_chance = $1 -> exit=$rc"
  readback keyspace1 "$2"
  say "ALTER $2 value=$1 exit=$rc out=[$(tr '\n' ' ' < "$L/alter-$2.txt" | cut -c1-300)] readback=[$(tr -s ' \n' ' ' < "$L/readback-$2.txt")]"
  return $rc
}
readback() { cq -e "SELECT keyspace_name, table_name, bloom_filter_fp_chance FROM system_schema.tables WHERE keyspace_name='$1' AND table_name='standard1';" > "$L/readback-$2.txt" 2>&1; }

say "cluster-run $RUN N=$N start $(now) clone $(git -C $C describe --tags) $(git -C $C rev-parse --short HEAD) bf-node.btm sha256 $(shasum -a 256 "$H/bf-node.btm" | cut -c1-16)"
[ -n "$(ps -eo command | grep "[C]assandra""Daemon")" ] && { say "ABORT: a daemon is already running"; exit 1; }
rm -rf "$NODE"
run "$H/make-node-conf.sh" || die "conf"
sed -i '' 's#<appender-ref ref="STDOUT" */>##' "$NODE/conf/logback.xml"
say "logback STDOUT refs left: $(grep -c 'appender-ref ref="STDOUT"' "$NODE/conf/logback.xml")"
sed -n '/^# ---- stage4 bfgf lines/,$p' "$NODE/conf/cassandra.yaml" > "$L/yaml-tail.txt"
say "yaml sstable lines: $(grep -n '^ *sstable:\|^ *selected_format' "$NODE/conf/cassandra.yaml" | tr '\n' ';')"
start_node "$L/node/node.out"
say "JVM $(grep -m1 -o 'JVM Arguments: .*' $L/node/system.log | grep -o -- '-Xm[sx][^,]*\|-XX:NativeMemoryTracking=[a-z]*\|-javaagent:[^,]*' | tr '\n' ' ')"
say "BMBF lines at start: $(grep -c '^BMBF ' "$OUT")"

# (2) load
stress "$N" LOAD || die "stress LOAD failed"
run nt flush keyspace1 || die "flush failed"
run nt disableautocompaction keyspace1 || die "disableautocompaction failed"
run ntl compact keyspace1 standard1 || die "compact failed"
idle_wait keyspace1 || die "not idle after load"
readback keyspace1 R0
say "SCHEMA R0 $(tr -s ' \n' ' ' < "$L/readback-R0.txt")"
run jcmd $PID VM.native_memory baseline && NMTBASE=1
# (3)
sample R0 keyspace1
# (4) per fp
for fp in 0.001 0.1 0.5 1.0 0.01; do
  alter "$fp" "F$fp" || die "ALTER $fp failed"
  echo "$(stat -f %z "$OUT")" > "$L/rewrite-start-F$fp.txt"
  run ntl upgradesstables -a keyspace1 standard1 || die "upgradesstables at $fp failed"
  idle_wait keyspace1 || die "not idle after rewrite at $fp"
  sample "F$fp" keyspace1
  say "GF lines in the F$fp rewrite window: $(tail -c +$(( $(cat "$L/rewrite-start-F$fp.txt") + 1 )) "$OUT" | head -c $(( $(awk '{print $2}' "$L/F$fp/nodeout-offset.txt") - $(cat "$L/rewrite-start-F$fp.txt") )) | grep '^BMBF GF ' | awk '$3>=1000' | sort | uniq -c | tr -s ' ' | tr '\n' ';')"
done
# (5) restart-only check
alter 1.0 S5 || die "ALTER 1.0 (step 5) failed"
sample S5a keyspace1
stop_node
start_node "$L/node/node2.out"
say "BMBF lines at restart: $(grep -c '^BMBF ' "$OUT")"
sample S5b keyspace1
# (6) positive control
stress $((2*N)) CTRL -schema keyspace=ks_ctl || die "stress CTRL failed"
run nt flush ks_ctl || die "flush ks_ctl failed"
run ntl compact ks_ctl standard1 || die "compact ks_ctl failed"
idle_wait ks_ctl || die "not idle after ks_ctl load"
readback ks_ctl CTRL
say "SCHEMA CTRL $(tr -s ' \n' ' ' < "$L/readback-CTRL.txt")"
sample CTRL ks_ctl

grep -c '^ERROR' "$L/node/system.log" > "$L/error-count.txt"; say "system.log ERROR lines: $(cat "$L/error-count.txt")"
say "BMBF lines total: node.out $(grep -c '^BMBF ' $L/node/node.out), node2.out $(grep -c '^BMBF ' $L/node/node2.out); other lines: $(grep -vc '^BMBF ' $L/node/node.out) / $(grep -vc '^BMBF ' $L/node/node2.out)"
stop_node
final_check
say "end $(now)"
