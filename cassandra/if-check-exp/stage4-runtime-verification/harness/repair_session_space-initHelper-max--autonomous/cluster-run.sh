#!/usr/bin/env bash
# Cluster tier (B3 as amended C1-C8, 2026-10-27) of repair_session_space-initHelper-max--autonomous.
# usage: cluster-run.sh <outdir-name> [stress_n] [reps] [labels]
#   cluster-run.sh run1                                  the run: n=3000000, 3 repairs per label, labels "default 1 4 16 64 1024"
#   cluster-run.sh shake 30000 1 "default 1 1024"        harness shakedown with a small load (not judged)
# Three nodes on 127.0.0.1-3 from $W/cassandra-run60; data under $W/node-rssih/nN (wiped at start and end).
# Logs: $W/logs/repair_session_space-initHelper-max--autonomous/cluster-<outdir-name>/ : commands.log, summary.txt, n1..n3 node logs,
#       stress*.log, <label>-r<k>/ (knob read-backs, node2 histograms, samples.csv, per-node debug segments and grep results, repair.log)
# Node mechanics adapted from harness/repair_session_space-applySimpleConfig-repair_session_space--autonomous/cluster-run.sh.
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
H=$(cd "$(dirname "$0")" && pwd)
RUN=${1:?outdir}; STRESS_N=${2:-3000000}; REPS=${3:-3}; LABELS=${4:-"default 1 4 16 64 1024"}
L=$W/logs/repair_session_space-initHelper-max--autonomous/cluster-$RUN
rm -rf "$L"; mkdir -p "$L"; CL=$L/commands.log; S=$L/summary.txt; : > "$CL"; : > "$S"
C1=$W/cassandra-run60
T=$W/tools-rssih
addr()  { case $1 in n1) echo 127.0.0.1;; n2) echo 127.0.0.2;; n3) echo 127.0.0.3;; esac; }
port()  { case $1 in n1) echo 7199;; n2) echo 7299;; n3) echo 7399;; esac; }
getpid() { eval echo "\${PID_$1:-}"; }
setpid() { eval "PID_$1=$2"; }
NODES="n1 n2 n3"
RS=org.apache.cassandra.db:type=RepairService
MAIN_PID=$$

ms()  { perl -MTime::HiRes=time -e 'printf("%d\n", time()*1000)'; }
now() { date '+%Y-%m-%dT%H:%M:%S%z'; }
log() { echo "[$(now)] $*" >> "$CL"; }
say() { echo "$*" >> "$S"; log "SUMMARY $*"; }
tmo() { perl -e '$t=shift; $p=fork; if(!$p){exec @ARGV; exit 127} $SIG{ALRM}=sub{kill 9,$p; waitpid $p,0; exit 124}; alarm $t; waitpid $p,0; exit($?>>8)' "$@"; }
nt()  { local n=$1; shift; tmo 120 "$C1/bin/nodetool" -h 127.0.0.1 -p $(port $n) "$@"; }
run() { log "+ $*"; "$@" >> "$CL" 2>&1; local rc=$?; log "  exit=$rc"; return $rc; }
jmx() { tmo 60 java -cp "$T" JmxAttr "$@" 2>&1 | tail -1; }
die() { say "ABORT: $*"; stop_all; final_check; exit 1; }

start_node() {   # start_node <n> <logdir>
  local n=$1 ld=$2; mkdir -p "$ld"
  log "+ start $n (clone $C1, conf $W/node-rssih/$n/conf, logs $ld)"
  CASSANDRA_CONF=$W/node-rssih/$n/conf CASSANDRA_LOG_DIR=$ld MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M \
    nohup "$C1/bin/cassandra" -f > "$ld/node.out" 2>&1 < /dev/null &
  setpid $n $!; disown; log "  $n pid $(getpid $n)"
}
wait_up() {      # wait_up <n> <seconds>: UN and statusbinary running; fails at once if the daemon dies
  local n=$1 lim=$2 t0; t0=$(date +%s)
  while :; do
    kill -0 $(getpid $n) 2>/dev/null || { log "$n pid $(getpid $n) died"; return 2; }
    if nt $n status 2>/dev/null | grep -q "^UN  $(addr $n) " && [ "$(nt $n statusbinary 2>/dev/null)" = running ]; then
      log "$n up after $(( $(date +%s) - t0 )) s"; return 0; fi
    [ $(( $(date +%s) - t0 )) -ge $lim ] && { log "$n not up in $lim s"; return 1; }
    sleep 3
  done
}
stop_node() {
  local n=$1; local p; p=$(getpid $n)
  [ -z "$p" ] && return 0
  kill -0 $p 2>/dev/null || { setpid $n ""; return 0; }
  run tmo 60 "$C1/bin/nodetool" -h 127.0.0.1 -p $(port $n) drain
  kill $p 2>/dev/null; for i in $(seq 1 30); do kill -0 $p 2>/dev/null || break; sleep 1; done
  kill -0 $p 2>/dev/null && { log "kill -9 $n $p"; kill -9 $p; sleep 1; }
  setpid $n ""; log "$n stopped"
}
stop_all() { for n in $NODES; do stop_node $n; done; pkill -9 -f cassandra-stress 2>/dev/null; }
final_check() {
  local d; d=$(ps -eo command | grep '[C]assandraDaemon'); say "final Cassandra daemon processes: ${d:-none}"
  pgrep -f cassandra-stress >/dev/null && say "WARNING: cassandra-stress still running" || say "no cassandra-stress left"
  run rm -rf "$W/node-rssih"; say "node-rssih wiped: $([ -e "$W/node-rssih" ] && echo no || echo yes)"
}
trap '[ "$$" = "$MAIN_PID" ] && [ "${BASH_SUBSHELL:-0}" = 0 ] && { stop_all; }' INT TERM
hist_parse() {   # hist_parse <file> -> leaf_inst leaf_bytes inner_inst inner_bytes
  awk '$4 ~ /MerkleTree\$OnHeapLeaf$/{li=$2; lb=$3} $4 ~ /MerkleTree\$OnHeapInner$/{ii=$2; ib=$3}
       END{printf "%d %d %d %d\n", li, lb, ii, ib}' "$1"
}
settle() {   # flush and wait: no active compaction and SSTable count unchanged for 30 s (600 s limit) on every node
  for n in $NODES; do run nt $n flush rss standard1; done
  for n in $NODES; do
    local t0 prev="" same=0 c a; t0=$(date +%s)
    while :; do
      c=$(nt $n tablestats rss.standard1 2>/dev/null | awk -F: '/SSTable count/{gsub(/ /,"",$2); print $2; exit}')
      a=$(nt $n compactionstats 2>/dev/null | grep -c ' rss ')
      if [ "$c" = "$prev" ] && [ "$a" = 0 ]; then same=$((same+5)); else same=0; fi
      prev=$c; [ $same -ge 30 ] && break
      [ $(( $(date +%s) - t0 )) -ge 600 ] && { say "WARNING $n not settled after 600 s (sstables=$c active=$a)"; break; }
      sleep 5
    done
  done
}

repair_one() {   # repair_one <label> <rep> <S|default>
  local lab=$1 rep=$2 s=$3 D=$L/$1-r$2; mkdir -p "$D/hist"
  say "== $lab r$rep s=$s"
  for n in $NODES; do
    if [ "$s" != default ]; then say "SET $lab r$rep $n $(jmx $(port $n) set $RS RepairSessionSpaceInMiB $s)"; fi
    say "KNOB $lab r$rep $n $(jmx $(port $n) get $RS RepairSessionSpaceInMiB)"
  done
  local p2; p2=$(getpid n2)
  jcmd $p2 GC.class_histogram > "$D/hist/idle.txt" 2>&1
  say "IDLE $lab r$rep n2 $(hist_parse "$D/hist/idle.txt")"
  for n in $NODES; do eval "OFF_$n=$(stat -f %z "$L/$n/debug.log")"; done
  local flag=$D/sampling; touch "$flag"
  ( while [ -e "$flag" ]; do t=$(ms); jcmd $p2 GC.class_histogram > "$D/hist/s-$t.txt" 2>&1; sleep 0.5; done ) &
  local spid=$!
  local t0; t0=$(ms)
  log "+ nodetool -p 7199 repair -full -pr rss standard1  ($lab r$rep)"
  tmo 900 "$C1/bin/nodetool" -h 127.0.0.1 -p 7199 repair -full -pr rss standard1 > "$D/repair.log" 2>&1; local rc=$?
  local t1; t1=$(ms); rm -f "$flag"; wait $spid 2>/dev/null; sleep 3
  say "REPAIR $lab r$rep exit=$rc ms=$(( t1 - t0 )) start_ms=$t0 end_ms=$t1"
  echo "ts_ms,leaf_inst,leaf_bytes,inner_inst,inner_bytes" > "$D/samples.csv"
  for f in "$D"/hist/s-*.txt; do [ -e "$f" ] || continue; t=$(basename "$f" .txt); t=${t#s-}
    echo "$t,$(hist_parse "$f" | tr ' ' ',')" >> "$D/samples.csv"; done
  for n in $NODES; do
    off=$(eval echo "\$OFF_$n"); tail -c +$(( off + 1 )) "$L/$n/debug.log" > "$D/$n-debug-segment.log"
    grep 'Prepared AEService trees of size' "$D/$n-debug-segment.log" > "$D/$n-prepared.txt"
    grep 'Created .* merkle trees with merkle trees size' "$D/$n-debug-segment.log" > "$D/$n-created.txt"
    say "PREPARED $lab r$rep $n lines=$(wc -l < "$D/$n-prepared.txt" | tr -d ' ') N=$(sed -E 's/.*Prepared AEService trees of size ([0-9]+) for.*/\1/' "$D/$n-prepared.txt" | tr '\n' ' ')"
    say "CREATED $lab r$rep $n lines=$(wc -l < "$D/$n-created.txt" | tr -d ' ') $(sed -E 's/.*Created ([0-9]+) merkle trees with merkle trees size ([0-9]+), ([0-9]+) partitions, ([0-9]+) bytes.*/trees=\1 size=\2 P=\3 B=\4/' "$D/$n-created.txt" | tr '\n' ';')"
  done
  local N2; N2=$(sed -E 's/.*Prepared AEService trees of size ([0-9]+) for.*/\1/' "$D/n2-prepared.txt" | head -1)
  read il ib ii inb < <(hist_parse "$D/hist/idle.txt")
  say "HIST $lab r$rep n2 $(awk -F, -v N=${N2:-0} -v il=$il -v ib=$ib -v ii=$ii -v inb=$inb 'NR>1{c++; l=$2-il; i=$4-ii; if(l>0)w++;
        if(l>ml){ml=l; mi=i; mh=($3-ib)+($5-inb)+48*(l+i)+24*i}
        if(N>0 && l>=N && l<=N+2 && i>=N-1 && i<=N) k++}
      END{printf "samples=%d samples_with_tree=%d peak_leaf=%d peak_inner=%d derived_bytes=%d caught_samples=%d N=%d", c, w, ml, mi, mh, k, N}' "$D/samples.csv")"
  say "LIMIT $lab r$rep s=$s"
}
caught() {       # caught <label-prefix>: 0 if some repair of the label caught the tree
  grep -E "^HIST $1 r[0-9]+ n2 " "$S" | grep -qv 'caught_samples=0 '
}

# ------------------------------------------------------------------ pre-checks
say "cluster-run $RUN start $(now) stress_n=$STRESS_N reps=$REPS labels=[$LABELS] script md5 $(md5 -q "$0" | cut -c1-12)"
say "clone $C1 $(git -C $C1 describe --tags) $(git -C $C1 rev-parse --short HEAD)"
d=$(ps -eo command | grep '[C]assandraDaemon'); [ -n "$d" ] && { say "ABORT: a Cassandra daemon is running"; exit 1; }
for p in 7000 7199 7299 7399 9042; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { say "ABORT: port $p busy"; exit 1; }; done
for a in 127.0.0.2 127.0.0.3; do ifconfig lo0 | grep -q "inet $a " || { say "ABORT: loopback alias $a missing"; exit 1; }; done
say "pre-checks: no daemon; ports free; lo0 has 127.0.0.2 127.0.0.3; free disk $(df -h $W | tail -1 | awk '{print $4}')"
mkdir -p "$T"; run javac -d "$T" "$H/JmxAttr.java" || { say "ABORT: JmxAttr does not compile"; exit 1; }
rm -rf "$W/node-rssih"
for n in $NODES; do run "$H/make-node-conf.sh" $n; done
for n in $NODES; do say "YAML $n $(sed -n '/^# ---- stage4 rssih lines/,$p' $W/node-rssih/$n/conf/cassandra.yaml | grep -v '^#' | tr '\n' ';')"; done

# ------------------------------------------------------------------ ring (C1)
for n in $NODES; do start_node $n "$L/$n"; wait_up $n 360 || die "$n did not start"; done
say "RING $(nt n1 status 2>&1 | grep -E '^(UN|DN|UJ|UL|DL)' | awk '{print $1, $2}' | tr '\n' ';')"
for n in $NODES; do say "HEAP $n $(grep -m1 -o 'Heap size: [^,]*, [^ ]*' $L/$n/system.log) $(grep -m1 -o 'JVM Arguments: .*' $L/$n/system.log | grep -o -- '-Xm[sx][0-9]*[GM]' | tr '\n' ' ') offheap_merkle=$(grep -m1 -o 'use_offheap_merkle_trees=[a-z]*' $L/$n/system.log)"; done
for n in $NODES; do run nt $n setlogginglevel org.apache.cassandra.repair DEBUG; done

# ------------------------------------------------------------------ load (C3)
stress() {   # stress <n> <logname>
  log "+ cassandra-stress write n=$1 cl=ALL -schema 'replication(factor=3)' keyspace=rss -col 'size=FIXED(64)' 'n=FIXED(1)' -rate threads=50 -node 127.0.0.1"
  tmo 3600 "$C1/tools/bin/cassandra-stress" write n=$1 cl=ALL -schema "replication(factor=3)" keyspace=rss -col "size=FIXED(64)" "n=FIXED(1)" -rate threads=50 -node 127.0.0.1 > "$L/$2" 2>&1
  say "STRESS $2 exit=$? $(grep -E '^(Total partitions|Total errors|Op rate|Total operation time)' "$L/$2" | tr -s ' ' | tr '\n' ';')"
}
stress $STRESS_N stress.log
settle
for n in $NODES; do run nt $n disableautocompaction rss standard1
  say "SSTABLES $n $(nt $n tablestats rss.standard1 2>&1 | grep -E 'SSTable count|Number of partitions \(estimate\)|Space used \(live\)' | tr -s ' ' | tr '\n' ';')"
done

# ------------------------------------------------------------------ repairs (C2, C5)
for lab in $LABELS; do
  name=$([ "$lab" = default ] && echo default || echo s$lab)
  for r in $(seq 1 $REPS); do repair_one $name $r $lab; done
done
unc=""
for lab in $LABELS; do name=$([ "$lab" = default ] && echo default || echo s$lab); caught $name || unc="$unc $lab"; done
say "UNCAUGHT labels:${unc:- none}"
if [ -n "$unc" ] && [ "$RUN" != shake ]; then
  say "FALLBACK: load n=10000000 and repeat:$unc"
  stress 10000000 stress-10M.log
  settle
  for n in $NODES; do say "SSTABLES-10M $n $(nt $n tablestats rss.standard1 2>&1 | grep -E 'SSTable count|Number of partitions \(estimate\)' | tr -s ' ' | tr '\n' ';')"; done
  for lab in $unc; do
    # the default label needs the node default back: it is restored by setting the value read in the first default repair
    s=$lab; if [ "$lab" = default ]; then s=$(grep -m1 '^KNOB default r1 n1 ' "$S" | sed -E 's/.*=([0-9]+)$/\1/'); fi
    name=$([ "$lab" = default ] && echo default || echo s$lab)-n10M
    for r in $(seq 1 $REPS); do repair_one $name $r $s; done
  done
fi

# ------------------------------------------------------------------ cleanup (C8)
stop_all
final_check
say "cluster-run $RUN end $(now)"
