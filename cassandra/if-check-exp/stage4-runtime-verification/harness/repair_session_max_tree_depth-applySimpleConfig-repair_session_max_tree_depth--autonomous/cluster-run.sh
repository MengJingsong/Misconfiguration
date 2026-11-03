#!/usr/bin/env bash
# Cluster tier (B3, as amended 2026-10-24) of repair_session_max_tree_depth-applySimpleConfig-repair_session_max_tree_depth--autonomous.
# usage: cluster-run.sh <outdir-name> [stress_n]
#   cluster-run.sh run1            the run: stress n=2000000, labels default d10 d14 d18 ctl-s4-d18, startup with depth 9 on n1
#   cluster-run.sh shake 30000     harness shakedown with a small load (not judged)
# Three nodes on this host (127.0.0.1-3), one clone each, repair_session_space 1024MiB, data under $W/node-rsmtd/nN (wiped
# at start and end). Adapted from harness/repair_session_space-applySimpleConfig-repair_session_space--autonomous/cluster-run.sh.
# Logs: $W/logs/repair_session_max_tree_depth-applySimpleConfig/cluster-<outdir-name>/ : commands.log, summary.txt,
#       n1..n3 node logs, <label>/ (histograms per node per sample, samples.csv, n*-prepared.txt, n*-created.txt, repair.log),
#       stress.log, startup-depth9/
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
H=$(cd "$(dirname "$0")" && pwd)
RUN=${1:?outdir}; STRESS_N=${2:-2000000}
SPACE=1024
L=$W/logs/repair_session_max_tree_depth-applySimpleConfig/cluster-$RUN
rm -rf "$L"; mkdir -p "$L"; CL=$L/commands.log; S=$L/summary.txt; : > "$CL"; : > "$S"
C1=$W/cassandra-run7
# bash 3.2 (macOS): no associative arrays
addr()  { case $1 in n1) echo 127.0.0.1;; n2) echo 127.0.0.2;; n3) echo 127.0.0.3;; esac; }
port()  { case $1 in n1) echo 7199;; n2) echo 7299;; n3) echo 7399;; esac; }
clone() { case $1 in n1) echo $W/cassandra-run7;; n2) echo $W/cassandra-run7-n2;; n3) echo $W/cassandra-run7-n3;; esac; }
getpid() { eval echo "\${PID_$1:-}"; }
setpid() { eval "PID_$1=$2"; }
NODES="n1 n2 n3"
RS=org.apache.cassandra.db:type=RepairService
SS=org.apache.cassandra.db:type=StorageService

ms()  { perl -MTime::HiRes=time -e 'printf("%d\n", time()*1000)'; }
now() { date '+%Y-%m-%dT%H:%M:%S%z'; }
log() { echo "[$(now)] $*" >> "$CL"; }
say() { echo "$*" >> "$S"; log "SUMMARY $*"; }
tmo() { perl -e '$t=shift; $p=fork; if(!$p){exec @ARGV; exit 127} $SIG{ALRM}=sub{kill 9,$p; waitpid $p,0; exit 124}; alarm $t; waitpid $p,0; exit($?>>8)' "$@"; }
nt()  { local n=$1; shift; tmo 120 "$C1/bin/nodetool" -h 127.0.0.1 -p $(port $n) "$@"; }
run() { log "+ $*"; "$@" >> "$CL" 2>&1; local rc=$?; log "  exit=$rc"; return $rc; }
die() { say "ABORT: $*"; stop_all; final_check; exit 1; }

start_node() {   # start_node <n> <logdir>
  local n=$1 ld=$2; mkdir -p "$ld"
  log "+ start $n (clone $(clone $n), conf $W/node-rsmtd/$n/conf, logs $ld)"
  CASSANDRA_CONF=$W/node-rsmtd/$n/conf CASSANDRA_LOG_DIR=$ld MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M \
    nohup "$(clone $n)/bin/cassandra" -f > "$ld/node.out" 2>&1 < /dev/null &
  setpid $n $!; disown; log "  $n pid $(getpid $n)"
}
wait_up() {      # wait_up <n> <seconds>: UN and statusbinary running; fails at once if the daemon dies
  local n=$1 lim=$2 t0=$(date +%s)
  while :; do
    kill -0 $(getpid $n) 2>/dev/null || { log "$n pid $(getpid $n) died"; return 2; }
    if nt $n status 2>/dev/null | grep -q "^UN  $(addr $n) " && [ "$(nt $n statusbinary 2>/dev/null)" = running ]; then
      log "$n up after $(( $(date +%s) - t0 )) s"; return 0; fi
    [ $(( $(date +%s) - t0 )) -ge $lim ] && { log "$n not up in $lim s"; return 1; }
    sleep 3
  done
}
stop_node() {
  local n=$1; local p; p=$(getpid $n)   # separate: in bash 3.2 'local n=$1 p=$(getpid $n)' expands $n before n is set
  [ -z "$p" ] && return 0
  kill -0 $p 2>/dev/null || { setpid $n ""; return 0; }
  run tmo 60 "$C1/bin/nodetool" -h 127.0.0.1 -p $(port $n) drain
  kill $p 2>/dev/null; for i in $(seq 1 30); do kill -0 $p 2>/dev/null || break; sleep 1; done
  kill -0 $p 2>/dev/null && { log "kill -9 $n $p"; kill -9 $p; sleep 1; }
  setpid $n ""; log "$n stopped"
}
stop_all() { for n in $NODES; do stop_node $n; done; pkill -9 -f cassandra-stress 2>/dev/null; }
final_check() {
  local d; d=$(ps -eo command | grep '[C]assandraDaemon'); say "final CassandraDaemon processes: ${d:-none}"
  pgrep -f cassandra-stress >/dev/null && say "WARNING: cassandra-stress still running" || say "no cassandra-stress left"
  run rm -rf "$W/node-rsmtd"; say "node-rsmtd wiped: $([ -e "$W/node-rsmtd" ] && echo no || echo yes)"
}
knob_read() {    # knob_read <n> <bean> <attr>
  nt $1 sjk mx -b "$2" -mg -f "$3" 2>&1 | tr -d '\r' | grep -v '^$' | tail -1
}
hist_parse() {   # hist_parse <file> -> leaf_inst leaf_bytes inner_inst inner_bytes total_bytes
  awk '/MerkleTree\$OnHeapLeaf( |$)/{li=$2; lb=$3} /MerkleTree\$OnHeapInner( |$)/{ii=$2; ib=$3} /^Total/{tb=$3}
       END{printf "%d %d %d %d %d\n", li, lb, ii, ib, tb}' "$1"
}
repair_label() {  # repair_label <label> <depth|default> <space>   (B3b/B3e as amended: attribute set, read back)
  local lab=$1 d=$2 s=$3 D=$L/$1; mkdir -p "$D/hist"
  say "== $lab: depth=$d space=$s"
  for n in $NODES; do
    [ "$d" != default ] && run nt $n sjk mx -b $SS -ms -f RepairSessionMaxTreeDepth -v $d
    run nt $n sjk mx -b $RS -ms -f RepairSessionSpaceInMiB -v $s
    say "KNOB $lab $n RepairSessionMaxTreeDepth=$(knob_read $n $SS RepairSessionMaxTreeDepth) RepairSessionSpaceInMiB=$(knob_read $n $RS RepairSessionSpaceInMiB)"
  done
  for n in $NODES; do
    jcmd $(getpid $n) GC.class_histogram > "$D/hist/$n-idle.txt" 2>&1
    say "IDLE $lab $n $(hist_parse "$D/hist/$n-idle.txt")"
    eval "OFF_$n=$(stat -f %z "$L/$n/debug.log")"
  done
  local flag=$D/sampling; touch "$flag"; local spids=""
  for n in $NODES; do
    ( p=$(getpid $n); while [ -e "$flag" ]; do t=$(ms); ( jcmd $p GC.class_histogram > "$D/hist/$n-$t.txt" 2>&1 & ); sleep 1; done ) &
    spids="$spids $!"
  done
  local t0=$(ms)
  log "+ nodetool -p 7199 repair -full keyspace1 standard1  (label $lab)"
  tmo 900 "$C1/bin/nodetool" -h 127.0.0.1 -p 7199 repair -full keyspace1 standard1 > "$D/repair.log" 2>&1; local rc=$?
  local t1=$(ms); rm -f "$flag"; wait $spids 2>/dev/null; sleep 5
  say "REPAIR $lab exit=$rc ms=$(( t1 - t0 )) start_ms=$t0 end_ms=$t1 completed=$(grep -c 'Repair completed successfully' "$D/repair.log")"
  echo "node,ts_ms,leaf_inst,leaf_bytes,inner_inst,inner_bytes,total_bytes" > "$D/samples.csv"
  for n in $NODES; do
    for f in "$D"/hist/$n-[0-9]*.txt; do [ -e "$f" ] || continue; t=$(basename "$f" .txt); t=${t#$n-}
      echo "$n,$t,$(hist_parse "$f" | tr ' ' ',')" >> "$D/samples.csv"; done
    off=$(eval echo "\$OFF_$n"); tail -c +$(( off + 1 )) "$L/$n/debug.log" > "$D/$n-debug-segment.log"
    grep 'Created .* merkle trees with merkle trees size' "$D/$n-debug-segment.log" > "$D/$n-created.txt"
    grep 'Prepared AEService trees of size' "$D/$n-debug-segment.log" > "$D/$n-prepared.txt"   # B3d amendment: S after init()
    say "PREPARED $lab $n lines=$(wc -l < "$D/$n-prepared.txt" | tr -d ' ') S=$(sed -E 's/.*Prepared AEService trees of size ([0-9]+) for.*/\1/' "$D/$n-prepared.txt" | tr '\n' ' ')"
    say "CREATED $lab $n lines=$(wc -l < "$D/$n-created.txt" | tr -d ' ') $(sed -E 's/.*(Created [0-9]+ merkle trees with merkle trees size [0-9]+, [0-9]+ partitions, [0-9]+ bytes).*/\1/' "$D/$n-created.txt" | tr '\n' ';')"
    say "HIST $lab $n $(awk -F, -v n=$n '$1==n{c++; b=$4+$6; if(b>m)m=b; if($3+0>lm)lm=$3+0; if($3+0>0)w++} END{printf "samples=%d samples_with_tree=%d H_max_bytes=%d Lmax=%d", c, w, m, lm}' "$D/samples.csv")"
  done
}

# ------------------------------------------------------------------ pre-checks
say "cluster-run $RUN start $(now) stress_n=$STRESS_N space=${SPACE}MiB harness md5 $(md5 -q "$0" | cut -c1-12)"
say "clones: $(for n in $NODES; do echo -n "$n=$(git -C $(clone $n) rev-parse --short HEAD) "; done)"
d=$(ps -eo command | grep '[C]assandraDaemon'); [ -n "$d" ] && { say "ABORT: a CassandraDaemon is running"; exit 1; }
for p in 7000 7199 7299 7399 9042; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { say "ABORT: port $p busy"; exit 1; }; done
for a in 127.0.0.2 127.0.0.3; do ifconfig lo0 | grep -q "inet $a " || { say "ABORT: loopback alias $a missing"; exit 1; }; done
say "pre-checks: no CassandraDaemon; ports 7000 7199 7299 7399 9042 free; lo0 has 127.0.0.2 127.0.0.3; free disk $(df -h $W | tail -1 | awk '{print $4}')"
rm -rf "$W/node-rsmtd"
for n in $NODES; do run "$H/make-node-conf.sh" $n repair_session_space=${SPACE}MiB; done
for n in $NODES; do say "YAML $n $(sed -n '/^# ---- stage4 rsmtd7 lines/,$p' $W/node-rsmtd/$n/conf/cassandra.yaml | grep -v '^#' | tr '\n' ';')"; done

# ------------------------------------------------------------------ ring
for n in $NODES; do start_node $n "$L/$n"; wait_up $n 360 || die "$n did not start"; done
say "RING $(nt n1 status 2>&1 | grep -E '^(UN|DN|UJ)' | awk '{print $1, $2}' | tr '\n' ';')"
for n in $NODES; do say "HEAP $n $(grep -m1 -o 'Heap size: [^,]*, [^ ]*' $L/$n/system.log) $(grep -m1 -o 'JVM Arguments: .*' $L/$n/system.log | grep -o -- '-Xm[sx][0-9]*[GM]' | tr '\n' ' ')"; done
for n in $NODES; do say "STARTWARN $n $(grep -h -o 'A repair_session_space of [^ ]* mebibytes is likely to cause heap pressure' $L/$n/system.log | sort -u | tr '\n' ';')"; done

# ------------------------------------------------------------------ load (B3c)
log "+ cassandra-stress write n=$STRESS_N cl=ALL -col 'n=FIXED(1)' 'size=FIXED(32)' -schema 'replication(factor=3)' -node 127.0.0.1"
tmo 1800 "$C1/tools/bin/cassandra-stress" write n=$STRESS_N cl=ALL -col 'n=FIXED(1)' 'size=FIXED(32)' -schema 'replication(factor=3)' -node 127.0.0.1 > "$L/stress.log" 2>&1
say "STRESS exit=$? $(grep -E '^(Total partitions|Total errors|Op rate|Total operation time)' "$L/stress.log" | tr -s ' ' | tr '\n' ';')"
for n in $NODES; do run nt $n flush keyspace1 standard1; done
for n in $NODES; do t0=$(date +%s)
  until nt $n compactionstats 2>/dev/null | grep -Eq '^pending tasks: *0 *$|^pending tasks +0 *$'; do [ $(( $(date +%s) - t0 )) -ge 600 ] && { say "WARNING $n compactions pending after 600 s"; break; }; sleep 5; done
  run nt $n disableautocompaction keyspace1 standard1
  say "SSTABLES $n $(nt $n tablestats keyspace1.standard1 2>&1 | grep -E 'SSTable count|Number of partitions \(estimate\)|Space used \(live\)' | tr -s ' ' | tr '\n' ';')"
done

# ------------------------------------------------------------------ repairs (B3b, B3e, B3h)
repair_label default default $SPACE
for d in 10 14 18; do repair_label d$d $d $SPACE; done
repair_label ctl-s4-d18 18 4
for n in $NODES; do run nt $n sjk mx -b $RS -ms -f RepairSessionSpaceInMiB -v $SPACE; say "RESTORE $n RepairSessionSpaceInMiB=$(knob_read $n $RS RepairSessionSpaceInMiB) RepairSessionMaxTreeDepth=$(knob_read $n $SS RepairSessionMaxTreeDepth)"; done

# ------------------------------------------------------------------ startup check on n1 (B3e)
stop_node n1
run "$H/make-node-conf.sh" n1 repair_session_space=${SPACE}MiB repair_session_max_tree_depth=9
say "YAML-startup n1 $(sed -n '/^# ---- stage4 rsmtd7 lines/,$p' $W/node-rsmtd/n1/conf/cassandra.yaml | grep -E 'repair_session' | tr '\n' ';')"
start_node n1 "$L/startup-depth9"; t0=$(date +%s)
while kill -0 $(getpid n1) 2>/dev/null && [ $(( $(date +%s) - t0 )) -lt 120 ]; do sleep 1; done
if kill -0 $(getpid n1) 2>/dev/null; then say "STARTUP depth9: process alive at 120 s"; stop_node n1; else say "STARTUP depth9: process exited after $(( $(date +%s) - t0 )) s"; setpid n1 ""; fi
say "STARTUP depth9 lines: $(grep -h -o 'repair_session_max_tree_depth should not be < 10[^"]*' "$L/startup-depth9/system.log" "$L/startup-depth9/node.out" 2>/dev/null | sort -u | tr '\n' ';') startup-complete=$(grep -c 'Startup complete' "$L/startup-depth9/system.log" 2>/dev/null)"

# ------------------------------------------------------------------ cleanup
stop_all
final_check
say "cluster-run $RUN end $(now)"
