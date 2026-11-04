#!/usr/bin/env bash
# Cluster tier (B3, as amended 2026-10-26) of repair_state_size-setRepairStateSize-size--autonomous.
# usage: cluster-run.sh <outdir-name> <N> <S> [<S> ...]
#   cluster-run.sh run1 2000 50 500 100000     the run (B3e order)
#   cluster-run.sh shake 200 50                harness shakedown with a small N (not judged)
# One node (127.0.0.1, JMX 7199) from $W/cassandra-run27, 1 GiB heap, data under $NODE/n1 (kept between values, wiped at
# start and end). For each S: restart with repair_state_size: S, check the startup line, schema, settle 180 s, two baselines 60 s apart
# (count0 from system_views.repairs and repair_participates; jcmd GC.class_histogram Total = live heap), Rep.java N, wait 60 s,
# count1 and two histograms 30 s apart, the system.log segment written during the run (by byte offset), stop.
# Logs: $W/logs/repair_state_size-setRepairStateSize/cluster-<outdir-name>/
# 2026-10-28 (cluster re-run, Amendment 2026-10-28 B3d (6), B3e, B4): RSS_C (clone) and RSS_NODE (node directory) override run 1's
# $W/cassandra-run27 and $W/node-rss; with RSS_DUMP=1 the script also takes jcmd GC.heap_dump after histogram base-b (dump-base.hprof)
# and after the second count (dump-after.hprof), and after the node stops analyses both with HprofRetained.java (ret-base.txt,
# ret-after.txt; RET summary lines). Without these variables it behaves exactly as in run 1.
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
H=$(cd "$(dirname "$0")" && pwd)
RUN=${1:?outdir}; NREP=${2:?N}; shift 2; VALUES="$*"; [ -n "$VALUES" ] || { echo "no S values" >&2; exit 2; }
L=$W/logs/repair_state_size-setRepairStateSize/cluster-$RUN
rm -rf "$L"; mkdir -p "$L"; CL=$L/commands.log; S=$L/summary.txt; : > "$CL"; : > "$S"
C=${RSS_C:-$W/cassandra-run27}; NODE=${RSS_NODE:-$W/node-rss}; DUMP=${RSS_DUMP:-0}; T=$W/tools-rss; mkdir -p "$T"; cp "$H/Rep.java" "$T/Rep.java"
PID=""
now() { date '+%Y-%m-%dT%H:%M:%S%z'; }
log() { echo "[$(now)] $*" >> "$CL"; }
say() { echo "$*" >> "$S"; log "SUMMARY $*"; }
tmo() { perl -e '$t=shift; $p=fork; if(!$p){exec @ARGV; exit 127} $SIG{ALRM}=sub{kill 9,$p; waitpid $p,0; exit 124}; alarm $t; waitpid $p,0; exit($?>>8)' "$@"; }
nt()  { tmo 120 "$C/bin/nodetool" -h 127.0.0.1 -p 7199 "$@"; }
cq()  { tmo 120 "$C/bin/cqlsh" 127.0.0.1 -e "$1" 2>&1; }
cnt() { cq "SELECT count(*) FROM system_views.$1" > "$D/cql-$1-$2.txt"; awk '/^ *[0-9]+ *$/{gsub(/ /,""); print; exit}' "$D/cql-$1-$2.txt"; }   # raw output kept
hist() { tmo 120 jcmd $PID GC.class_histogram > "$1" 2>&1; }
total() { awk '$1=="Total"{print $3}' "$1"; }
row()  { awk -v c="$2" '$4==c{i=$2; b=$3} END{printf "%d/%d", i, b}' "$1"; }   # instances/bytes of class $2 in histogram $1
run() { log "+ $*"; "$@" >> "$CL" 2>&1; local rc=$?; log "  exit=$rc"; return $rc; }
die() { say "ABORT: $*"; stop_node; final_check; exit 1; }
CLASSES="org.apache.cassandra.repair.state.CoordinatorState org.apache.cassandra.repair.state.CoordinatorState\$Phase org.apache.cassandra.repair.messages.RepairOption org.apache.cassandra.repair.RepairCoordinator org.apache.cassandra.repair.state.ParticipateState com.google.common.cache.LocalCache\$StrongWriteEntry com.google.common.cache.LocalCache\$StrongAccessWriteEntry"

start_node() {
  local ld=$1; mkdir -p "$ld"
  log "+ start n1 (clone $C, conf $NODE/n1/conf, logs $ld) MAX_HEAP_SIZE=1G HEAP_NEWSIZE=200M"
  CASSANDRA_CONF=$NODE/n1/conf CASSANDRA_LOG_DIR=$ld MAX_HEAP_SIZE=1G HEAP_NEWSIZE=200M \
    nohup "$C/bin/cassandra" -f > "$ld/node.out" 2>&1 < /dev/null &
  PID=$!; disown; log "  n1 pid $PID"
}
wait_up() {
  local lim=$1 t0=$(date +%s)
  while :; do
    kill -0 $PID 2>/dev/null || { log "n1 pid $PID died"; return 2; }
    if nt status 2>/dev/null | grep -q "^UN  127.0.0.1 " && [ "$(nt statusbinary 2>/dev/null)" = running ]; then
      log "n1 up after $(( $(date +%s) - t0 )) s"; return 0; fi
    [ $(( $(date +%s) - t0 )) -ge $lim ] && { log "n1 not up in $lim s"; return 1; }
    sleep 3
  done
}
stop_node() {
  [ -z "$PID" ] && return 0
  kill -0 $PID 2>/dev/null || { PID=""; return 0; }
  run nt drain
  kill $PID 2>/dev/null; for i in $(seq 1 30); do kill -0 $PID 2>/dev/null || break; sleep 1; done
  kill -0 $PID 2>/dev/null && { log "kill -9 n1 $PID"; kill -9 $PID; sleep 1; }
  log "n1 stopped (pid $PID)"; PID=""
}
final_check() {
  pkill -f 'Rep.java' 2>/dev/null
  local d; d=$(ps -eo command | grep '[C]assandraDaemon'); say "final CassandraDaemon processes: ${d:-none}"
  pgrep -f 'Rep.java' >/dev/null && say "WARNING: Rep.java still running" || say "no Rep.java left"
  run rm -rf "$NODE"; say "node-rss wiped: $([ -e "$NODE" ] && echo no || echo yes) ($NODE)"
}

# ------------------------------------------------------------------ pre-checks
say "cluster-run $RUN start $(now) N=$NREP values=[$VALUES] harness md5 $(md5 -q "$0" | cut -c1-12) Rep md5 $(md5 -q "$H/Rep.java" | cut -c1-12) clone $(git -C $C rev-parse --short HEAD)"
[ "$C" != "$W/cassandra-run27" ] || [ "$DUMP" = 1 ] && say "re-run settings: clone $C node $NODE dumps $DUMP HprofRetained sha256 $(shasum -a 256 "$H/HprofRetained.java" | cut -c1-12) cluster-run sha256 $(shasum -a 256 "$0" | cut -c1-12)"
d=$(ps -eo command | grep '[C]assandraDaemon'); [ -n "$d" ] && { say "ABORT: a CassandraDaemon is running"; exit 1; }
for p in 7000 7199 9042; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { say "ABORT: port $p busy"; exit 1; }; done
say "pre-checks: no CassandraDaemon; ports 7000 7199 9042 free; free disk $(df -h $W | tail -1 | awk '{print $4}')"
rm -rf "$NODE"

first=1
for SV in $VALUES; do
  D=$L/S$SV; mkdir -p "$D"
  say "== S=$SV"
  run "$H/make-node-conf.sh" $SV
  say "YAML S=$SV $(sed -n '/^# ---- stage4 rss lines/,$p' $NODE/n1/conf/cassandra.yaml | grep -v '^#' | tr '\n' ';')"
  start_node "$D/n1"; wait_up 360 || die "n1 did not start (S=$SV)"
  say "STARTLINE S=$SV $(grep -h 'Storing repair state for' "$D/n1/system.log" | sed -E 's/.*(Storing repair state for .*)$/\1/' | tr '\n' ';')"
  say "HEAP S=$SV $(grep -m1 -o 'JVM Arguments: .*' $D/n1/system.log | grep -o -- '-Xm[sx][0-9]*[GM]' | tr '\n' ' ')"
  if [ $first = 1 ]; then
    cq "CREATE KEYSPACE IF NOT EXISTS rs WITH replication = {'class':'SimpleStrategy','replication_factor':2}; CREATE TABLE IF NOT EXISTS rs.t (k int PRIMARY KEY, v int);" > "$D/schema.txt"; first=0
  fi
  say "SCHEMA S=$SV $(cq "SELECT replication FROM system_schema.keyspaces WHERE keyspace_name='rs'" | grep -o "{.*}") table=$(cq "SELECT table_name FROM system_schema.tables WHERE keyspace_name='rs'" | grep -cw t)"
  log "settle 180 s (B3e amendment after the shakedown)"; sleep 180
  c0=$(cnt repairs 0); p0=$(cnt repair_participates 0)
  hist "$D/hist-base-a.txt"; ua=$(total "$D/hist-base-a.txt")
  sleep 60
  hist "$D/hist-base-b.txt"; ub=$(total "$D/hist-base-b.txt")
  say "BASE S=$SV count0=$c0 participates0=$p0 used0a=$ua used0b=$ub drift0=$(( ub - ua ))"
  if [ "$DUMP" = 1 ]; then run tmo 300 jcmd $PID GC.heap_dump "$D/dump-base.hprof"; say "DUMP S=$SV base bytes=$(stat -f %z "$D/dump-base.hprof" 2>/dev/null || echo missing)"; fi
  off=$(stat -f %z "$D/n1/system.log")
  log "+ (cd $W && java $T/Rep.java 127.0.0.1:7199 $NREP)"
  t0=$(date +%s)
  ( cd "$W" && tmo 1200 java "$T/Rep.java" 127.0.0.1:7199 $NREP ) > "$D/rep.log" 2>&1; rc=$?
  say "REP S=$SV exit=$rc secs=$(( $(date +%s) - t0 )) out=[$(tail -3 "$D/rep.log" | tr '\n' ' ')]"
  sleep 60
  c1=$(cnt repairs 1); p1=$(cnt repair_participates 1)
  hist "$D/hist-after-a.txt"; u1=$(total "$D/hist-after-a.txt")
  sleep 30
  hist "$D/hist-after-b.txt"; u1b=$(total "$D/hist-after-b.txt")
  c1b=$(cnt repairs 1b)
  if [ "$DUMP" = 1 ]; then run tmo 300 jcmd $PID GC.heap_dump "$D/dump-after.hprof"; say "DUMP S=$SV after bytes=$(stat -f %z "$D/dump-after.hprof" 2>/dev/null || echo missing)"; fi
  tail -c +$(( off + 1 )) "$D/n1/system.log" > "$D/system-segment.log"
  say "COUNT S=$SV count1=$c1 count1_after30s=$c1b participates1=$p1"
  say "USED S=$SV used1=$u1 used1_after30s=$u1b delta=$(( u1 - ub )) drift1=$(( u1b - u1 ))"
  for k in $CLASSES; do say "CLASS S=$SV $k base_b=$(row "$D/hist-base-b.txt" "$k") after_a=$(row "$D/hist-after-a.txt" "$k") after_b=$(row "$D/hist-after-b.txt" "$k")"; done
  say "LOG S=$SV starting=$(grep -c 'Starting repair command #' "$D/system-segment.log") nothing_to_repair=$(grep -c 'Nothing to repair for' "$D/system-segment.log") aborted_warn=$(grep -c '^WARN .*Repair .* aborted' "$D/system-segment.log") error_lines=$(grep -c '^ERROR' "$D/system-segment.log")"
  stop_node
  d=$(ps -eo command | grep '[C]assandraDaemon'); [ -n "$d" ] && die "daemon still running after stop (S=$SV)"
  if [ "$DUMP" = 1 ]; then
    for w in base after; do
      h=$D/hist-base-b.txt; [ $w = after ] && h=$D/hist-after-b.txt
      log "+ (cd $W && java -Xmx6g HprofRetained.java $D/dump-$w.hprof $h ActiveRepairService repairs CoordinatorState)"
      ( cd "$W" && tmo 1200 java -Xmx6g "$H/HprofRetained.java" "$D/dump-$w.hprof" "$h" org.apache.cassandra.service.ActiveRepairService repairs org.apache.cassandra.repair.state.CoordinatorState ) > "$D/ret-$w.txt" 2>&1
      say "RET S=$SV $w exit=$? $(grep -E '^(REACH|CUT|VALUE|RETAINED|UNREACHED|FALLBACK)' "$D/ret-$w.txt" | sed -E 's/^(CUT|VALUE) class=[^ ]+ /\1 /' | tr '\n' ';')"
    done
  fi
done
final_check
say "cluster-run $RUN end $(now)"
