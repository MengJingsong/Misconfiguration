#!/usr/bin/env bash
# Cluster tier (B3, as amended C1-C6 2026-10-27) of max_queue_weight-acquireWeight-weight--autonomous.
# usage: cluster-run.sh <run> <n> <plateau_s> <gap_s> <blocking_duration> "<M list>" <control_M>
#   cluster-run.sh r1 500000 60 65 100s "16777216 134217728 268435456 1073741824" 1073741824     run 1 (C2/C4)
#   cluster-run.sh shake 40000 5 5 15s "16777216" 16777216                                      shakedown (not judged)
# One node on 127.0.0.1 from $W/cassandra-run62, MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M, conf/data/fql under $W/node-mqw (wiped at start
# and end). Every start has -Dcassandra.netty_use_heap_allocator=true; the Byteman phase adds the agent with slow-binlog.btm (filed rule)
# and mqw-observe.btm (observe-only MQWP/MQWW lines on node.out; the STDOUT appender is removed from logback.xml).
# Sequence C4: start; schema stress (FQL off); flush; disableautocompaction keyspace1; baseline histogram; per M: enable (blocking false),
# stress + 5-s histogram sampler, flush, H_full, disable, H_empty, gap; blocking pass (M=128 MiB, duration); restart without agent;
# control (control_M, blocking false); drain, stop, check, wipe.
# Runbook-defect fixes D2 (w_obs = MQWW values >= 4096) and D3 (plateau sample = stress has not printed Results: yet), 2026-10-27.
# Node mechanics (tmo, nt, run, stop_node, final_check, wait_up) adapted from
# harness/bloom_filter_fp_chance-getFilter-maxFalsePosProbability--autonomous/cluster-run.sh (that file is not modified).
# Logs: $W/logs/max_queue_weight-acquireWeight-weight--autonomous/cluster-<run>/
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
RUN=${1:?run}; NOPS=${2:?n}; PLAT=${3:?plateau}; GAP=${4:?gap}; BDUR=${5:?blocking duration}; MLIST=${6:?M list}; CTRLM=${7:?control M}
H=$(cd "$(dirname "$0")" && pwd)
L=$W/logs/max_queue_weight-acquireWeight-weight--autonomous/cluster-$RUN
rm -rf "$L"; mkdir -p "$L/node"; CL=$L/commands.log; S=$L/summary.txt; : > "$CL"; : > "$S"
C=$W/cassandra-run62; NODE=$W/node-mqw; FQL=$NODE/fql
BM=$C/build/lib/jars/byteman-4.0.20.jar
XO_BM="-Dcassandra.netty_use_heap_allocator=true -javaagent:$BM=script:$H/slow-binlog.btm,script:$H/mqw-observe.btm"
XO_PLAIN="-Dcassandra.netty_use_heap_allocator=true"
PID=""; OUT=$L/node/node.out; SYSLOG=$L/node/system.log
echo "run=$RUN n=$NOPS plateau_s=$PLAT gap_s=$GAP blocking_duration=$BDUR mlist=$MLIST control_m=$CTRLM" > "$L/params.txt"
now() { date '+%Y-%m-%dT%H:%M:%S%z'; }
ms()  { perl -MTime::HiRes=time -e 'printf "%d\n", time*1000'; }
log() { echo "[$(now)] $*" >> "$CL"; }
say() { echo "$*" >> "$S"; log "SUMMARY $*"; }
tmo() { perl -e '$t=shift; $p=fork; if(!$p){exec @ARGV; exit 127} $SIG{ALRM}=sub{kill 9,$p; waitpid $p,0; exit 124}; alarm $t; waitpid $p,0; exit($?>>8)' "$@"; }
nt()  { tmo 600 "$C/bin/nodetool" -h 127.0.0.1 -p 7199 "$@"; }
run() { log "+ $*"; "$@" >> "$CL" 2>&1; local rc=$?; log "  exit=$rc"; return $rc; }
die() { say "ABORT: $*"; [ -n "${SPID:-}" ] && kill "$SPID" 2>/dev/null; stop_node; final_check; exit 1; }
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
  run rm -rf "$NODE"; say "node-mqw wiped: $([ -e "$NODE" ] && echo no || echo yes)"
}
start_node() {   # start_node <stdout file> <JVM_EXTRA_OPTS>
  OUT=$1
  log "+ start node CASSANDRA_CONF=$NODE/conf MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M JVM_EXTRA_OPTS=$2 > $OUT"
  CASSANDRA_CONF=$NODE/conf CASSANDRA_LOG_DIR=$L/node MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M JVM_EXTRA_OPTS="$2" nohup "$C/bin/cassandra" -f > "$OUT" 2>&1 < /dev/null &
  PID=$!; disown; log "pid $PID"
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
hist() {   # hist <file> : class histogram (forces a full GC; live objects only); prints "<N_q> <total bytes>"
  jcmd $PID GC.class_histogram > "$1" 2>&1
  local nq tot
  nq=$(awk '$4=="org.apache.cassandra.fql.FullQueryLogger$Query"{print $2; exit}' "$1"); tot=$(awk '$1=="Total"{print $3; exit}' "$1")
  echo "${nq:-0} ${tot:-NA}"
}
stress_bg() {   # stress_bg <tag> <count arg> : stress in the background, sets SPID and SOUT
  SOUT=$L/stress-$1.txt
  log "+ cassandra-stress write $2 no-warmup cl=ONE -col size=FIXED(4096) n=FIXED(1) -rate threads=64 throttle=5000/s -node 127.0.0.1 > $SOUT"
  tmo 1800 "$C/tools/bin/cassandra-stress" write "$2" no-warmup cl=ONE -col 'size=FIXED(4096)' 'n=FIXED(1)' -rate threads=64 throttle=5000/s -node 127.0.0.1 > "$SOUT" 2>&1 < /dev/null &
  SPID=$!
}
stress_summary() { echo "$(grep -m1 'Total partitions' "$1" | tr -s ' ') | $(grep -m1 'Total errors' "$1" | tr -s ' ') | $(grep -m1 'Op rate' "$1" | tr -s ' ') | $(grep -m1 'Total operation time' "$1" | tr -s ' ')"; }
fqlrun() {   # fqlrun <label> <M> <blocking true|false> <count arg>
  local lab=$1 M=$2 blk=$3 cnt=$4 d=$L/$1 i=0 t0 ts te alive res r rc
  mkdir -p "$d"
  run rm -rf "$FQL"
  echo "system.log $(stat -f %z "$SYSLOG") node.out $(stat -f %z "$OUT")" > "$d/offsets.txt"
  run nt enablefullquerylog --path "$FQL" --blocking "$blk" --max-queue-weight "$M" --max-log-size 2147483648 || die "enable $lab failed"
  nt getfullquerylog > "$d/getfullquerylog.txt" 2>&1
  t0=$(ms); echo "$t0" > "$d/stress-start-ms.txt"
  stress_bg "$lab" "$cnt"
  : > "$d/samples.txt"
  while kill -0 $SPID 2>/dev/null; do
    ts=$(ms); r=$(hist "$d/hist-$(printf %03d $i).txt"); te=$(ms)
    kill -0 $SPID 2>/dev/null && alive=1 || alive=0
    grep -q '^Results:' "$SOUT" && res=1 || res=0   # D3: stress has finished its operations once it prints Results:
    echo "$i $((ts - t0)) $((te - t0)) $r $alive $res" >> "$d/samples.txt"
    i=$((i+1))
    local next=$(( t0 + i*5000 )) nowms; nowms=$(ms)
    [ $next -gt $nowms ] && sleep "$(perl -e "printf '%.3f', ($next-$nowms)/1000")"
  done
  wait $SPID; rc=$?; echo "$(ms)" > "$d/stress-end-ms.txt"; SPID=""
  say "STRESS $lab exit=$rc $(stress_summary "$SOUT")"
  [ $rc -ne 0 ] && die "stress $lab exit $rc"
  run nt flush keyspace1
  r=$(hist "$d/full.txt"); echo "$r" > "$d/full-summary.txt"
  run nt disablefullquerylog
  local re; re=$(hist "$d/empty.txt"); echo "$re" > "$d/empty-summary.txt"
  local so no; read -r _ so _ no < "$d/offsets.txt"
  tail -c +$((so + 1)) "$SYSLOG" | grep 'Dropped .* binary log samples' > "$d/drops.txt"
  tail -c +$((so + 1)) "$SYSLOG" | grep 'Attempting to configure bin log' > "$d/binlog-config.txt"
  tail -c +$((no + 1)) "$OUT" | grep '^MQW[PW] ' > "$d/mqw-lines.txt"
  say "RUN $lab M=$M blocking=$blk samples=$i plateau_samples=$(awk -v p=$PLAT '$2>=p*1000 && $6==1 && $7==0' "$d/samples.txt" | wc -l | tr -d ' ') nq_plateau=[$(awk -v p=$PLAT '$2>=p*1000 && $6==1 && $7==0{printf "%s,", $4}' "$d/samples.txt")] full=[$r] empty=[$re] drops=$(wc -l < "$d/drops.txt" | tr -d ' ') mqwp=$(grep -c '^MQWP' "$d/mqw-lines.txt") mqww=$(grep -c '^MQWW' "$d/mqw-lines.txt") w_all=[$(awk '$1=="MQWW"{print $3}' "$d/mqw-lines.txt" | sort -n | uniq -c | awk '{printf "%sx%s,", $2, $1}')] maxWeight=[$(awk '$1=="MQWP"{print $4}' "$d/mqw-lines.txt" | sort -u | tr '\n' ',')] getfql=[$(tr -s ' \n' ' ' < "$d/getfullquerylog.txt" | cut -c1-300)]"
}

say "cluster-run $RUN start $(now) clone $(git -C $C describe --tags) $(git -C $C rev-parse --short HEAD) slow-binlog.btm $(shasum -a 256 "$H/slow-binlog.btm" | cut -c1-16) mqw-observe.btm $(shasum -a 256 "$H/mqw-observe.btm" | cut -c1-16)"
say "params $(cat "$L/params.txt")"
[ -n "$(ps -eo command | grep "[C]assandra""Daemon")" ] && { say "ABORT: a daemon is already running"; exit 1; }
rm -rf "$NODE"
run "$H/make-node-conf.sh" || die "conf"
sed -i '' 's#<appender-ref ref="STDOUT" */>##' "$NODE/conf/logback.xml"
say "logback STDOUT refs left: $(grep -c 'appender-ref ref="STDOUT"' "$NODE/conf/logback.xml")"
sed -n '/^# ---- stage4 mqw lines/,$p' "$NODE/conf/cassandra.yaml" > "$L/yaml-tail.txt"

# (1) Byteman phase
start_node "$L/node/node.out" "$XO_BM"
say "JVM $(grep -m1 -o 'JVM Arguments: .*' "$SYSLOG" | grep -o -- '-Xm[sx][^,]*\|-Dcassandra.netty_use_heap_allocator=[a-z]*\|-javaagent:[^,]*\|-XX:+Use[A-Za-z1]*GC' | tr '\n' ' ')"
stress_bg schema "n=$NOPS"; wait $SPID; rc=$?; SPID=""
say "STRESS schema exit=$rc $(stress_summary "$L/stress-schema.txt")"; [ $rc -ne 0 ] && die "schema stress"
run nt flush keyspace1
run nt disableautocompaction keyspace1
say "BASELINE $(hist "$L/baseline.txt")"
# (2) sweep
first=1
for M in $MLIST; do
  [ $first = 1 ] || { log "gap $GAP s"; sleep "$GAP"; }; first=0
  fqlrun "M$M" "$M" false "n=$NOPS"
done
# (3) blocking pass
log "gap $GAP s"; sleep "$GAP"
fqlrun "B134217728" 134217728 true "duration=$BDUR"
# (4) control without Byteman
stop_node
echo "system.log $(stat -f %z "$SYSLOG")" > "$L/restart-offset.txt"
start_node "$L/node/node2.out" "$XO_PLAIN"
say "JVM2 $(tail -c +$(( $(awk '{print $2}' "$L/restart-offset.txt") + 1 )) "$SYSLOG" | grep -m1 -o 'JVM Arguments: .*' | grep -o -- '-Xm[sx][^,]*\|-Dcassandra.netty_use_heap_allocator=[a-z]*\|-javaagent:[^,]*' | tr '\n' ' ')"
fqlrun "CTRL$CTRLM" "$CTRLM" false "n=$NOPS"
# (5)
stop_node
final_check
say "cluster-run $RUN end $(now)"
