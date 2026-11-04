#!/usr/bin/env bash
# Cluster tier (B3, as amended 2026-10-26) of batchlog_DEFAULT_PAGE_SIZE-processBatchlogEntries-positionInPage--autonomous.
# usage: cluster-run.sh <outdir-name> <n_big> <n_small> <case> [<case> ...]
#   cluster-run.sh run1 512 4000 A B C      the run (B3c as amended: stress n counts partitions, 2 per batch)
#   cluster-run.sh shake 40 40 A B C        harness shakedown with small loads (not judged)
# One node (127.0.0.1, JMX 7199) from $W/cassandra-run28, 4 GiB heap, Byteman agent with bl.btm, data under $W/node-bl/n1
# (wiped before every case: each case is a fresh node). Per case (B3e as amended): start; C only: small load + flush
# system.batches; big load; flush bl; B only: flush system.batches; preconditions (count(*), tablestats); three baseline
# class histograms 10 s apart; note the node.out offset; start the samplers (class histogram every 10 s, GC.heap_info every
# 2 s); touch go; nodetool replaybatchlog; count(*) after; one post histogram; stop samplers; stop the node.
# Logs: $W/logs/batchlog_DEFAULT_PAGE_SIZE-processBatchlogEntries/cluster-<outdir-name>/
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
H=$(cd "$(dirname "$0")" && pwd)
RUN=${1:?outdir}; NBIG=${2:?n_big}; NSMALL=${3:?n_small}; shift 3; CASES="$*"; [ -n "$CASES" ] || { echo "no cases" >&2; exit 2; }
L=$W/logs/batchlog_DEFAULT_PAGE_SIZE-processBatchlogEntries/cluster-$RUN
rm -rf "$L"; mkdir -p "$L"; CL=$L/commands.log; S=$L/summary.txt; : > "$CL"; : > "$S"
C=$W/cassandra-run28; NB=$W/node-bl; GO=$NB/go
BMJAR=$C/build/lib/jars/byteman-4.0.20.jar
PID=""; SPIDS=""
now() { date '+%Y-%m-%dT%H:%M:%S%z'; }
log() { echo "[$(now)] $*" >> "$CL"; }
say() { echo "$*" >> "$S"; log "SUMMARY $*"; }
tmo() { perl -e '$t=shift; $p=fork; if(!$p){exec @ARGV; exit 127} $SIG{ALRM}=sub{kill 9,$p; waitpid $p,0; exit 124}; alarm $t; waitpid $p,0; exit($?>>8)' "$@"; }
nt()  { tmo 1200 "$C/bin/nodetool" -h 127.0.0.1 -p 7199 "$@"; }
cq()  { tmo 600 "$C/bin/cqlsh" --request-timeout=300 127.0.0.1 -e "$1" 2>&1; }
run() { log "+ $*"; "$@" >> "$CL" 2>&1; local rc=$?; log "  exit=$rc"; return $rc; }
hist() { tmo 120 jcmd $PID GC.class_histogram > "$1" 2>&1; }
total() { awk '$1=="Total"{print $3}' "$1"; }
row()  { awk -v c="$2" '$4==c{i=$2; b=$3} END{printf "%d/%d", i, b}' "$1"; }
RB='org.apache.cassandra.batchlog.BatchlogManager$ReplayingBatch'; MU='org.apache.cassandra.db.Mutation'
countb() { cq "SELECT count(*) FROM system.batches" > "$1"; awk '/^ *[0-9]+ *$/{gsub(/ /,""); print; exit}' "$1"; }

stop_samplers() { for p in $SPIDS; do kill $p 2>/dev/null; done; for p in $SPIDS; do wait $p 2>/dev/null; done; SPIDS=""; }
start_node() {
  local ld=$1; mkdir -p "$ld"
  log "+ start n1 (clone $C, conf $NB/n1/conf, logs $ld) MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M JVM_EXTRA_OPTS=-javaagent:$BMJAR=script:$H/bl.btm,listener:true -Dorg.jboss.byteman.transform.all=true"
  CASSANDRA_CONF=$NB/n1/conf CASSANDRA_LOG_DIR=$ld MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M \
    JVM_EXTRA_OPTS="-javaagent:$BMJAR=script:$H/bl.btm,listener:true -Dorg.jboss.byteman.transform.all=true" \
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
  stop_samplers
  [ -z "$PID" ] && return 0
  kill -0 $PID 2>/dev/null || { PID=""; return 0; }
  run nt drain
  kill $PID 2>/dev/null; for i in $(seq 1 60); do kill -0 $PID 2>/dev/null || break; sleep 1; done
  kill -0 $PID 2>/dev/null && { log "kill -9 n1 $PID"; kill -9 $PID; sleep 1; }
  log "n1 stopped (pid $PID)"; PID=""
}
final_check() {
  local d s; d=$(ps -eo command | grep '[C]assandraDaemon'); say "final CassandraDaemon processes: ${d:-none}"
  s=$(ps -eo command | grep '[s]tress.Stress'); say "final stress processes: ${s:-none}"
  run rm -rf "$NB"; say "node-bl wiped: $([ -e "$NB" ] && echo no || echo yes)"
}
die() { say "ABORT: $*"; stop_node; final_check; exit 1; }
stress() {  # $1 profile  $2 n  $3 outfile
  log "+ (cd $W && tools/bin/cassandra-stress user profile=$1 ops(insert=1) n=$2 no-warmup -rate threads=4 -node 127.0.0.1)"
  ( cd "$W" && tmo 1800 "$C/tools/bin/cassandra-stress" user "profile=$1" "ops(insert=1)" "n=$2" no-warmup -rate threads=4 -node 127.0.0.1 ) > "$3" 2>&1
  local rc=$?; log "  stress exit=$rc"
  say "STRESS $(basename $1) n=$2 exit=$rc $(grep -m1 -E '^Total partitions' "$3" | tr -s ' ') | $(grep -m1 -E '^Op rate' "$3" | tr -s ' ') | $(grep -m1 -E '^Total errors' "$3" | tr -s ' ') | $(grep -m1 -E '^Total operation time' "$3" | tr -s ' ')"
  return $rc
}

# ------------------------------------------------------------------ pre-checks
say "cluster-run $RUN start $(now) n_big=$NBIG n_small=$NSMALL cases=[$CASES] harness md5 $(md5 -q "$0" | cut -c1-12) btm md5 $(md5 -q "$H/bl.btm" | cut -c1-12) clone $(git -C $C rev-parse --short HEAD)"
d=$(ps -eo command | grep '[C]assandraDaemon'); [ -n "$d" ] && { say "ABORT: a CassandraDaemon is running"; exit 1; }
for p in 7000 7199 9042 9091; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { say "ABORT: port $p busy"; exit 1; }; done
[ -f "$BMJAR" ] || { say "ABORT: no $BMJAR"; exit 1; }
# rule parse/type check (runbook fix 2026-10-26, defect 3: a rule that does not parse is silently not injected)
( cd "$W" && java -cp "$BMJAR:$C/build/classes/main:$C/build/lib/jars/*" org.jboss.byteman.check.TestScript -v "$H/bl.btm" ) > "$L/btm-check.txt" 2>&1
grep -q 'TestScript: no errors' "$L/btm-check.txt" || { say "ABORT: bl.btm does not parse/type-check (see btm-check.txt)"; exit 1; }
say "btm check: $(grep -c '^Type checked rule' "$L/btm-check.txt") rules type-checked, $(tail -1 "$L/btm-check.txt")"
say "pre-checks: no CassandraDaemon; ports 7000 7199 9042 9091 free; free disk $(df -h $W | tail -1 | awk '{print $4}'); byteman $BMJAR"

for CS in $CASES; do
  D=$L/$CS; mkdir -p "$D/histo"
  say "== case $CS"
  rm -rf "$NB"; run "$H/make-node-conf.sh"
  say "YAML $CS $(sed -n '/^# ---- stage4 bl lines/,$p' $NB/n1/conf/cassandra.yaml | grep -v '^#' | tr '\n' ';')"
  start_node "$D/n1"; wait_up 360 || die "n1 did not start ($CS)"
  say "HEAP $CS $(grep -m1 -o 'JVM Arguments: .*' $D/n1/system.log | grep -o -- '-Xm[sxn][0-9]*[GM]\|-javaagent:[^,]*' | tr '\n' ' ')"
  if [ "$CS" = C ]; then
    stress "$H/small.yaml" $NSMALL "$D/stress-small.log" || die "small stress failed ($CS)"
    run nt flush system batches
  fi
  stress "$H/big.yaml" $NBIG "$D/stress-big.log" || die "big stress failed ($CS)"
  run nt flush bl
  [ "$CS" = B ] && run nt flush system batches
  # preconditions
  c0=$(countb "$D/cql-count-before.txt")
  nt tablestats system.batches > "$D/tablestats-batches-before.txt" 2>&1
  say "PRE $CS count_before=$c0 sstables=$(awk -F: '/SSTable count/{gsub(/ /,"",$2); print $2; exit}' "$D/tablestats-batches-before.txt") mean_bytes=$(awk -F: '/Compacted partition mean bytes/{gsub(/ /,"",$2); print $2; exit}' "$D/tablestats-batches-before.txt") memtable_data=$(awk -F: '/Memtable data size/{gsub(/ /,"",$2); print $2; exit}' "$D/tablestats-batches-before.txt") blpage_lines_before_go=$(grep -c 'BLPAGE ' "$D/n1/node.out")"
  # baselines
  for k in 1 2 3; do hist "$D/hist-base-$k.txt"; [ $k -lt 3 ] && sleep 10; done
  b1=$(total "$D/hist-base-1.txt"); b2=$(total "$D/hist-base-2.txt"); b3=$(total "$D/hist-base-3.txt")
  say "BASE $CS totals=$b1,$b2,$b3 RB=$(row "$D/hist-base-3.txt" "$RB") MU=$(row "$D/hist-base-3.txt" "$MU")"
  # samplers
  off=$(stat -f %z "$D/n1/node.out"); echo "$off" > "$D/go-offset.txt"
  ( while :; do t=$(date +%s); tmo 120 jcmd $PID GC.class_histogram > "$D/histo/h-$t.txt" 2>&1; sleep 10; done ) & SPIDS="$SPIDS $!"
  ( while :; do echo "t=$(date +%s)"; tmo 20 jcmd $PID GC.heap_info 2>&1 | head -4; sleep 2; done ) > "$D/heap_info.log" 2>&1 & SPIDS="$SPIDS $!"
  sleep 1
  tgo=$(date +%s); touch "$GO"; log "touch $GO at $tgo"
  echo "$tgo" > "$D/go-time.txt"
  log "+ nodetool replaybatchlog"
  nt replaybatchlog > "$D/replaybatchlog.out" 2>&1; rrc=$?
  tend=$(date +%s)
  say "REPLAY $CS exit=$rrc secs=$(( tend - tgo ))"
  stop_samplers
  c1=$(countb "$D/cql-count-after.txt")
  hist "$D/hist-post.txt"
  nt tablestats system.batches > "$D/tablestats-batches-after.txt" 2>&1
  tail -c +$(( off + 1 )) "$D/n1/node.out" > "$D/node-out-after-go.txt"
  say "POST $CS count_after=$c1 total_post=$(total "$D/hist-post.txt") RB=$(row "$D/hist-post.txt" "$RB")"
  # readings from the traces written after go
  gps=$(awk '/BLPAGESIZE /{last=$0} /BLPAGE unfinished=/{print last; exit}' "$D/node-out-after-go.txt")
  say "TRACE $CS governing=[$gps] blpage_lines=$(grep -c 'BLPAGE unfinished=' "$D/node-out-after-go.txt") max_unfinished=$(grep -o 'BLPAGE unfinished=[0-9]*' "$D/node-out-after-go.txt" | cut -d= -f2 | sort -n | tail -1) unfinished_seq=$(grep -o 'BLPAGE unfinished=[0-9]*' "$D/node-out-after-go.txt" | cut -d= -f2 | tr '\n' ',' | cut -c1-300) pagesize_values_after_go=$(grep -o 'BLPAGESIZE [0-9]*' "$D/node-out-after-go.txt" | awk '{print $2}' | sort -n | uniq -c | tr -s ' ' | tr '\n' ';')"
  for f in $(ls "$D/histo" | sort); do say "SAMPLE $CS $f total=$(total "$D/histo/$f") RB=$(row "$D/histo/$f" "$RB") MU=$(row "$D/histo/$f" "$MU")"; done
  say "ERRORS $CS system.log ERROR lines=$(grep -c '^ERROR' "$D/n1/system.log") byteman_errors=$(grep -ci 'rule.*error\|TypeException\|ParseException' "$D/n1/node.out")"
  stop_node
  d=$(ps -eo command | grep '[C]assandraDaemon'); [ -n "$d" ] && die "daemon still running after stop ($CS)"
done
final_check
say "cluster-run $RUN end $(now)"
