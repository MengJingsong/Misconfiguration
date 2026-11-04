#!/usr/bin/env bash
# Cluster tier (B3, as amended 2026-10-26) of row_cache_size-setRowCacheCapacityInMB-capacity--autonomous.
# usage: cluster-run.sh run1     N=300000, control 512 MiB, capped 128 64 32 (runtime set), yaml repeat 64, RT 1..200000 then shrink to 64
#        cluster-run.sh shake    N=30000, control 64, capped 8 4 2, yaml repeat 4, RT 1..20000 then shrink to 4 (not judged)
# One node on 127.0.0.1 from $W/cassandra-run44, MAX_HEAP_SIZE=1G HEAP_NEWSIZE=200M, data under $W/node-rcs44 (wiped at start and end).
# Order (B3e amendment): write phase -> BASE -> R<ctrl> -> R<c> x3 -> Y<yc> -> RT; a fresh node per run.
# Runbook defect 2 (2026-10-26): BASE sets caching ALL after its read, before its stop; R<ctrl> sets nothing.
# Runbook defect 1 (2026-10-26): reads carry -col size=FIXED(200) n=FIXED(5) (B3c amendment).
# Logs: $W/logs/row_cache_size-setRowCacheCapacityInMB-capacity/cluster-<run>/
# Cluster re-run (case-file amendments 2026-10-27, after run 1, authorised by the user):
#   run2 / shake2 = the values of run1 / shake; RCS_C (clone), RCS_NODE (node dir) override the run-1 paths;
#   RCS_BM=1: every node starts with the Byteman agent (rcs-ledger.btm + RcsLedger helper, observe only), TestScript check first,
#   per-run agent check, ledger one-shots (RcsJmx ledger) at start / end and in RT before the set, after it and after the misses.
#   Without these variables the script behaves as in run 1.
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
RUN=${1:?run}
case $RUN in
  run1|run2)   N=300000; CTRL=512; CAPS="128 64 32"; YC=64; RTC=64; NRT1=200000 ;;
  shake|shake2) N=30000;  CTRL=64;  CAPS="8 4 2";     YC=4;  RTC=4;  NRT1=20000 ;;
  *) echo "unknown run"; exit 2 ;;
esac
H=$(cd "$(dirname "$0")" && pwd)
L=$W/logs/row_cache_size-setRowCacheCapacityInMB-capacity/cluster-$RUN
rm -rf "$L"; mkdir -p "$L"; CL=$L/commands.log; S=$L/summary.txt; : > "$CL"; : > "$S"
C=${RCS_C:-$W/cassandra-run44}; NODE=${RCS_NODE:-$W/node-rcs44}; HB=$W/harness-bin-rcs
BM=${RCS_BM:-0}; BMJAR=$C/build/lib/jars/byteman-4.0.20.jar; LB=$W/harness-bin-rcs-ledger
export RCS_C=$C RCS_NODE=$NODE
PID=""; SPID=""; POLLDIR=""
now() { date '+%Y-%m-%dT%H:%M:%S%z'; }
log() { echo "[$(now)] $*" >> "$CL"; }
say() { echo "$*" >> "$S"; log "SUMMARY $*"; }
tmo() { perl -e '$t=shift; $p=fork; if(!$p){exec @ARGV; exit 127} $SIG{ALRM}=sub{kill 9,$p; waitpid $p,0; exit 124}; alarm $t; waitpid $p,0; exit($?>>8)' "$@"; }
nt()  { tmo 600 "$C/bin/nodetool" -h 127.0.0.1 -p 7199 "$@"; }
cq()  { HOME=$W/home tmo 300 "$C/bin/cqlsh" 127.0.0.1 --request-timeout=120 "$@"; }
run() { log "+ $*"; "$@" >> "$CL" 2>&1; local rc=$?; log "  exit=$rc"; return $rc; }
jx()  { java -cp "$HB" RcsJmx "$@"; }
die() { say "ABORT: $*"; stop_poller; stop_node; final_check; exit 1; }
stop_poller() { [ -n "$SPID" ] && { touch "$POLLDIR/stop" 2>/dev/null; wait $SPID 2>/dev/null; SPID=""; }; return 0; }
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
  pgrep -f "[R]csJmx" >/dev/null && say "WARNING: poller still running" || say "no poller left"
  run rm -rf "$NODE"; say "$(basename "$NODE") wiped: $([ -e "$NODE" ] && echo no || echo yes)"
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
start_node() {   # start_node <dir> <yamlC>
  local d=$1
  run "$H/make-node-conf.sh" row_cache_size=${2}MiB row_cache_save_period=0s key_cache_size=0MiB counter_cache_size=0MiB file_cache_enabled=false concurrent_compactors=1 || die "conf"
  sed -n '/^# ---- stage4 rcs44 lines/,$p' "$NODE/conf/cassandra.yaml" > "$d/yaml-tail.txt"
  tail -1 "$NODE/conf/jvm-server.options" >> "$d/yaml-tail.txt"
  rm -rf "$NODE/saved_caches"; mkdir -p "$NODE/saved_caches"
  say "$(basename $d) saved_caches entries at start: $(ls -A "$NODE/saved_caches" | wc -l | tr -d ' ')"
  mkdir -p "$d/node"
  local xo=""; [ "$BM" = 1 ] && xo="-javaagent:$BMJAR=script:$H/rcs-ledger.btm,boot:$BMJAR,sys:$LB/rcs-ledger.jar"
  log "+ start node CASSANDRA_CONF=$NODE/conf MAX_HEAP_SIZE=1G HEAP_NEWSIZE=200M JVM_EXTRA_OPTS=[$xo]"
  CASSANDRA_CONF=$NODE/conf CASSANDRA_LOG_DIR=$d/node MAX_HEAP_SIZE=1G HEAP_NEWSIZE=200M JVM_EXTRA_OPTS="$xo" nohup "$C/bin/cassandra" -f > "$d/node/node.out" 2>&1 < /dev/null &
  PID=$!; disown; log "pid $PID"
  wait_up
  if [ "$BM" = 1 ]; then
    say "BM-AGENT $(basename $d) javaagent_in_jvm_args=$(grep -m1 -o 'JVM Arguments: .*' $d/node/system.log | grep -c -o -- '-javaagent:[^ ,]*byteman') registered=$(grep -c '^RCSLEDGER registered' $d/node/node.out) agent_errors=$(grep -c -E 'TypeException|Rule\.execute called for|org\.jboss\.byteman.*(Exception|Error)|RCSLEDGER register failed' $d/node/node.out)"
  fi
  say "$(basename $d) pid=$PID JVM $(grep -m1 -o 'JVM Arguments: .*' $d/node/system.log | grep -o -- '-Xm[sx][^,]*\|-XX:NativeMemoryTracking[^,]*' | tr '\n' ' ') rowcache_init: $(grep -m1 -o 'Initializing row cache with capacity of [0-9]* MiBs' $d/node/system.log)"
}
stress_read() {   # stress_read <dir> <tag> <from> <to>
  local out=$1/stress-$2.txt n=$(( $4 - $3 + 1 ))
  log "+ cassandra-stress read n=$n cl=ONE -col size=FIXED(200) n=FIXED(5) -pop seq=$3..$4 -rate threads=50 -node 127.0.0.1 > $out"
  tmo 1800 "$C/tools/bin/cassandra-stress" read n=$n cl=ONE -col 'size=FIXED(200)' 'n=FIXED(5)' -pop seq=$3..$4 -rate threads=50 -node 127.0.0.1 > "$out" 2>&1 < /dev/null
  local rc=$?
  say "STRESS $(basename $1)/$2 exit=$rc $(grep -m1 'Total partitions' "$out" | tr -s ' ') | $(grep -m1 'Total errors' "$out" | tr -s ' ') | $(grep -m1 'Op rate' "$out" | tr -s ' ')"
}
info() {   # info <dir> <tag>
  nt info > "$1/info-$2.txt" 2>&1
  say "INFO $(basename $1)/$2 $(grep -E '^(Key|Row|Counter|Chunk) Cache' "$1/info-$2.txt" | tr -s ' ' | tr '\n' ';')"
}
rss() { ps -o rss= -p $PID | tr -d ' '; }
ledger() {   # ledger <dir> <tag>   (re-run: one JMX session: size, entries, capacity, ledger attributes; then the histogram)
  [ "$BM" = 1 ] || return 0
  jx ledger > "$1/ledger-$2.txt" 2>&1
  say "LEDGER $(basename $1)/$2 $(head -1 "$1/ledger-$2.txt")"
}
poll_start() { POLLDIR=$1; rm -f "$1/stop"; java -cp "$HB" RcsJmx poll "$1/samples.csv" "$1/stop" $PID > "$1/poller.err" 2>&1 & SPID=$!; sleep 1; }
post_run() {   # post_run <dir>
  local d=$1
  nt tablestats keyspace1.standard1 > "$d/tablestats.txt" 2>&1
  nt compactionhistory > "$d/compactionhistory.txt" 2>&1
  cq -e "SELECT caching, compaction FROM system_schema.tables WHERE keyspace_name='keyspace1' AND table_name='standard1';" > "$d/schema.txt" 2>&1
  grep -c '^ERROR' "$d/node/system.log" > "$d/error-count.txt"
  say "$(basename $d) sstables=$(awk -F': ' '/SSTable count/{print $2; exit}' "$d/tablestats.txt") ks1_compactions=$(grep -c ' keyspace1 ' "$d/compactionhistory.txt") errors=$(cat "$d/error-count.txt") schema: $(grep -o "{'keys'[^}]*}" "$d/schema.txt" | head -1) $(grep -o "'enabled': '[a-z]*'" "$d/schema.txt" | head -1)"
}
measure() {   # measure <label> <yamlC> <caching: NONE|ALL|-> <setC or ->
  local d=$L/$1; mkdir -p "$d"
  say "=== run $1 yaml=$2 caching=$3 set=$4 $(now)"
  start_node "$d" "$2"
  [ "$3" != "-" ] && { run cq -e "ALTER TABLE keyspace1.standard1 WITH caching = {'keys':'NONE','rows_per_partition':'$3'};" || die "alter caching"; }
  if [ "$4" != "-" ]; then
    run nt setcachecapacity 0 "$4" 0; say "$1 setcachecapacity 0 $4 0 exit=$?"
  fi
  say "$1 jmx after set: $(jx get)"
  sleep 60
  local r0; r0=$(rss); jcmd $PID VM.native_memory summary > "$d/nmt-before.txt" 2>&1; info "$d" start
  ledger "$d" start
  poll_start "$d"
  stress_read "$d" read 1 "$N"
  stop_poller "$d"
  ledger "$d" end
  local r1; r1=$(rss); jcmd $PID VM.native_memory summary > "$d/nmt-after.txt" 2>&1; info "$d" end
  echo "rss0_kib=$r0 rss1_kib=$r1" > "$d/rss.txt"
  say "$1 RSS0=$r0 KiB RSS1=$r1 KiB dRSS=$(( r1 - r0 )) KiB; jmx end: $(jx get)"
  post_run "$d"
  if [ "$1" = BASE ]; then   # runbook defect 2: set ALL back before the stop, so later nodes preload their statements with it
    run cq -e "ALTER TABLE keyspace1.standard1 WITH caching = {'keys':'NONE','rows_per_partition':'ALL'};" || die "alter caching ALL after BASE"
  fi
  stop_node
}

say "cluster-run $RUN N=$N CTRL=$CTRL CAPS=$CAPS YC=$YC RTC=$RTC NRT1=$NRT1 start $(now) clone $C $(git -C $C describe --tags) $(git -C $C rev-parse --short HEAD) node $NODE BM=$BM"
say "harness sha256: $(cd "$H" && shasum -a 256 cluster-run.sh make-node-conf.sh RcsJmx.java RcsLedger.java rcs-ledger.btm | awk '{printf "%s %s; ", substr($1,1,8), $2}')"
[ -n "$(ps -eo command | grep "[C]assandra""Daemon")" ] && { say "ABORT: a daemon is already running"; exit 1; }
mkdir -p "$HB"; run javac -d "$HB" "$H/RcsJmx.java" || { say "ABORT: javac"; exit 1; }
if [ "$BM" = 1 ]; then
  rm -rf "$LB/cls"; mkdir -p "$LB/cls"
  run javac -d "$LB/cls" -cp "$BMJAR:$C/build/lib/jars/jna-5.13.0.jar" "$H/RcsLedger.java" || { say "ABORT: javac RcsLedger"; exit 1; }
  ( cd "$LB/cls" && jar cf ../rcs-ledger.jar . ) || { say "ABORT: jar"; exit 1; }
  ( cd "$C" && java -classpath "$BMJAR:$LB/rcs-ledger.jar:build/classes/main:build/lib/jars/*" org.jboss.byteman.check.TestScript "$H/rcs-ledger.btm" ) > "$L/testscript.txt" 2>&1
  say "TESTSCRIPT $(grep -E 'TestScript:|ERROR|Type checked|WARN' "$L/testscript.txt" | tr '\n' ' ')"
  grep -q 'TestScript: no errors' "$L/testscript.txt" || { say "ABORT: TestScript reports errors"; exit 1; }
fi
rm -rf "$NODE"

# write phase
d=$L/write; mkdir -p "$d"; say "=== write phase $(now)"
start_node "$d" "$CTRL"
out=$d/stress-write.txt
log "+ cassandra-stress write n=$N cl=ONE -col size=FIXED(200) n=FIXED(5) -rate threads=50 -node 127.0.0.1 > $out"
tmo 1800 "$C/tools/bin/cassandra-stress" write n=$N cl=ONE -col 'size=FIXED(200)' 'n=FIXED(5)' -rate threads=50 -node 127.0.0.1 > "$out" 2>&1 < /dev/null
say "STRESS write exit=$? $(grep -m1 'Total partitions' "$out" | tr -s ' ') | $(grep -m1 'Total errors' "$out" | tr -s ' ') | $(grep -m1 'Op rate' "$out" | tr -s ' ')"
run cq -e "ALTER TABLE keyspace1.standard1 WITH caching = {'keys':'NONE','rows_per_partition':'ALL'};" || die "alter caching ALL"
run nt flush keyspace1 || die "flush"
run nt compact keyspace1 || die "compact"
run cq -e "ALTER TABLE keyspace1.standard1 WITH compaction = {'class':'SizeTieredCompactionStrategy','enabled':'false'};" || die "alter compaction"
run cq -e "ALTER TABLE keyspace1.standard1 WITH caching = {'keys':'NONE','rows_per_partition':'NONE'};" || die "alter caching NONE"
post_run "$d"
du -sk "$NODE/data/keyspace1" > "$d/du.txt"; say "write data on disk: $(cat "$d/du.txt")"
stop_node

measure BASE "$CTRL" - -
measure R$CTRL "$CTRL" - -
for c in $CAPS; do measure R$c "$CTRL" - "$c"; done
measure Y$YC "$YC" - -

# RT: runtime shrink of a full cache, then misses; then the negative value
d=$L/RT; mkdir -p "$d"; say "=== run RT yaml=$CTRL shrink to $RTC $(now)"
start_node "$d" "$CTRL"
sleep 60
r0=$(rss); info "$d" start
poll_start "$d"
stress_read "$d" read1 1 "$NRT1"
say "RT before set: $(jx get)"
ledger "$d" beforeset
run nt setcachecapacity 0 "$RTC" 0; say "RT setcachecapacity 0 $RTC 0 exit=$? at $(date +%s)000"
for i in 1 2 3; do say "RT after set sample $i $(date +%s): $(jx get)"; sleep 2; done
ledger "$d" afterset
stress_read "$d" read2 $(( NRT1 + 1 )) "$N"
say "RT after misses: $(jx get)"
ledger "$d" aftermisses
stop_poller "$d"
jx neg > "$d/neg.txt" 2>&1; say "RT neg: $(tr '\n' ' ' < "$d/neg.txt")"
say "RT after neg: $(jx get)"
r1=$(rss); info "$d" end; echo "rss0_kib=$r0 rss1_kib=$r1" > "$d/rss.txt"; say "RT RSS0=$r0 RSS1=$r1"
post_run "$d"
stop_node
final_check
say "end $(now)"
