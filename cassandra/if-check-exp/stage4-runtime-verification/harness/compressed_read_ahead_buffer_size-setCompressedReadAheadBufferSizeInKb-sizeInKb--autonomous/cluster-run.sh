#!/usr/bin/env bash
# Cluster tier (B3, as amended 2026-10-25) of compressed_read_ahead_buffer_size-setCompressedReadAheadBufferSizeInKb-sizeInKb--autonomous.
# Adapted from harness/compressed_read_ahead_buffer_size-applySimpleConfig-compressed_read_ahead_buffer_size--autonomous/cluster-run.sh
# (copied, then changed: one long-running node with runtime sets instead of one start per value, the filed Jmx.java client and
# poller instead of CrabJmx, keyspaces ra_<label>, 16 stress runs per arm, setcompactionthroughput 16, stale and ctl-cache arms).
# usage: cluster-run.sh <outdir-name> <plan>
#   plan run1: start n1 (256KiB): set 255, set 0; arms v256 v4096 v16384 v4096b stale; stop; start cc (file_cache_enabled: true):
#              set 16384, arm cc; stop.
#   plan sd:   shakedown (harness check, not a reading): start sd (256KiB), Byteman TestScript / Submit -l, set 2048,
#              arm sd with 4 x 20,000 rows.
# Node directories under $W/node-crs (wiped before every start and at the end). Logs:
#   $W/logs/compressed_read_ahead_buffer_size-setCompressedReadAheadBufferSizeInKb/cluster-<outdir>/ : commands.log, summary.txt,
#   <start>/ (system.log, node.out, readahead.trace), <arm>/ (poll.csv, stress-*.log, tablestats-*.txt, compactionstats.txt)
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
H=$(cd "$(dirname "$0")" && pwd)
RUN=${1:?outdir}; PLAN=${2:?plan}
L=$W/logs/compressed_read_ahead_buffer_size-setCompressedReadAheadBufferSizeInKb/cluster-$RUN
[ -e "$L" ] && mv "$L" "$L.attempt-$(date +%s)"
mkdir -p "$L"; CL=$L/commands.log; S=$L/summary.txt; : > "$CL"; : > "$S"
C=$W/cassandra-run23; N=$W/node-crs; PID=""; START=""; PPID_POLL=""
BM=$C/build/lib/jars
now() { date '+%Y-%m-%dT%H:%M:%S%z'; }
ms()  { python3 -c 'import time; print(int(time.time()*1000))'; }
log() { echo "[$(now)] $*" >> "$CL"; }
say() { echo "$*" >> "$S"; log "SUMMARY $*"; }
tmo() { perl -e '$t=shift; $p=fork; if(!$p){exec @ARGV; exit 127} $SIG{ALRM}=sub{kill 9,$p; waitpid $p,0; exit 124}; alarm $t; waitpid $p,0; exit($?>>8)' "$@"; }
nt()  { tmo 600 "$C/bin/nodetool" -h 127.0.0.1 -p 7199 "$@"; }
run() { log "+ $*"; "$@" >> "$CL" 2>&1; local rc=$?; log "  exit=$rc"; return $rc; }
jmx() { tmo 60 java "$H/Jmx.java" 127.0.0.1:7199 "$@"; }

make_conf() {   # make_conf key=value ...
  rm -rf "$N"; mkdir -p "$N/data" "$N/commitlog" "$N/hints" "$N/saved_caches" "$N/cdc"
  cp -R "$C/conf" "$N/conf"
  git -C "$C" show HEAD:conf/cassandra.yaml > "$N/shipped.yaml"
  { echo "cluster_name: stage4-crs"; echo "num_tokens: 1"; echo "initial_token: 0"; echo "auto_bootstrap: false"
    echo "listen_address: 127.0.0.1"; echo "rpc_address: 127.0.0.1"
    echo "data_file_directories:"; echo "    - $N/data"
    echo "commitlog_directory: $N/commitlog"; echo "hints_directory: $N/hints"; echo "saved_caches_directory: $N/saved_caches"
    echo "cdc_raw_directory: $N/cdc"
    for kv in "$@"; do echo "${kv%%=*}: ${kv#*=}"; done; } > "$N/lines.yaml"
  python3 - "$N" <<'PY'
import re, sys
n = sys.argv[1]
add = open(n + '/lines.yaml').read().splitlines()
keys = {l.split(':', 1)[0] for l in add if re.match(r'^[A-Za-z_]+:', l)}
out, skip = [], False
for l in open(n + '/shipped.yaml').read().splitlines():
    m = re.match(r'^([A-Za-z_]+):', l)
    if m:
        skip = m.group(1) in keys
        if skip:
            continue
    elif skip and (l.startswith((' ', '\t', '-')) or l.strip() == '' or l.lstrip().startswith('#')):
        continue
    else:
        skip = False
    out.append(l)
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 crs lines ----\n' + '\n'.join(add) + '\n')
PY
  say "YAML $(sed -n '/^# ---- stage4 crs lines/,$p' $N/conf/cassandra.yaml | grep -v '^#' | grep -v '^    - ' | grep -v directory | tr '\n' ';')"
}
start_node() {  # start_node <label>
  START=$1; local D=$L/$1; mkdir -p "$D"
  log "+ start node $1 (conf $N/conf, logs $D, Byteman trace $D/readahead.trace)"
  CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$D MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M \
    JVM_EXTRA_OPTS="-javaagent:$BM/byteman-4.0.20.jar=script:$H/readahead.btm,listener:true -Dstage4.byteman.out=$D/readahead.trace" \
    nohup "$C/bin/cassandra" -f > "$D/node.out" 2>&1 < /dev/null &
  PID=$!; disown; log "  pid $PID"; T0=$(date +%s)
  while :; do
    kill -0 $PID 2>/dev/null || die "$1: pid $PID died during start"
    if nt status 2>/dev/null | grep -q '^UN  127.0.0.1 ' && [ "$(nt statusbinary 2>/dev/null)" = running ]; then log "up after $(( $(date +%s) - T0 )) s"; break; fi
    [ $(( $(date +%s) - T0 )) -ge 300 ] && die "$1: not up in 300 s"
    sleep 3
  done
  local cfg; cfg=$(grep -h -o 'Node configuration:\[.*' "$D/system.log" | head -1)
  say "READBACK $START config: $(echo "$cfg" | grep -o 'compressed_read_ahead_buffer_size=[^;]*') ; $(echo "$cfg" | grep -o 'file_cache_enabled=[^;]*') ; $(echo "$cfg" | grep -o ' disk_access_mode=[^;]*')"
  say "READBACK $START $(grep -h -o 'DiskAccessMode is .*' "$D/system.log" | head -1) ; $(ps -o command= -p $PID | tr ' ' '\n' | grep -E 'MaxDirectMemorySize|^-Xmx|^-Xms' | tr '\n' ' ') byteman_agent=$(ps -o command= -p $PID | grep -c 'byteman-4.0.20.jar')"
  say "GET $START $(tmo 60 "$C/bin/nodetool" -h 127.0.0.1 -p 7199 sjk mx -mg -b org.apache.cassandra.db:type=StorageService -f CompressedReadAheadBufferInKB 2>&1 | tr '\n' ' ' | cut -c1-200)"
}
jset() {  # jset <v> <tag>
  local o; o=$(jmx set "$1" 2>&1 | tr '\n' ' ')
  say "SET $START $2 v=$1 :: $o"
}
stress_chunks() {  # stress_chunks <arm> <n chunks> <rows per chunk>
  local arm=$1 n=$2 r=$3 D=$L/$1 i lo hi
  for i in $(seq 0 $(( n - 1 ))); do
    lo=$(( r * i + 1 )); hi=$(( r * (i + 1) ))
    local s0=$(date +%s)
    (cd "$C" && tmo 600 tools/bin/cassandra-stress write n=$r no-warmup -pop seq=$lo..$hi -rate threads=32 \
       -schema keyspace=ra_$arm compression=LZ4Compressor -node 127.0.0.1) > "$D/stress-$i.log" 2>&1
    local rc=$?
    echo "chunk=$i seq=$lo..$hi rc=$rc secs=$(( $(date +%s) - s0 )) $(grep -E '^Total partitions' "$D/stress-$i.log" | tr -s ' ' | head -1) | $(grep -E '^Total errors' "$D/stress-$i.log" | tr -s ' ' | head -1)" >> "$D/stress-summary.txt"
    log "STRESS $arm $(tail -1 "$D/stress-summary.txt")"
    [ $rc -eq 0 ] || die "$arm: stress chunk $i failed (rc $rc)"
    [ $i -eq 0 ] && { run nt disableautocompaction ra_$arm || die "$arm: disableautocompaction failed"; }
    run nt flush ra_$arm standard1 || die "$arm: flush failed"
  done
  say "STRESS $arm chunks=$n rows/chunk=$r ok=$(grep -c ' rc=0 ' "$D/stress-summary.txt") partitions=[$(grep -o 'Total partitions : [0-9,]*' "$D/stress-summary.txt" | awk '{print $4}' | sort | uniq -c | awk '{print $2"x"$1}' | tr '\n' ' ')] errors=[$(grep -o 'Total errors : [0-9,]*' "$D/stress-summary.txt" | awk '{print $4}' | sort | uniq -c | awk '{print $2"x"$1}' | tr '\n' ' ')]"
}
tstats() {  # tstats <arm> <tag>
  local D=$L/$1
  nt tablestats ra_$1.standard1 > "$D/tablestats-$2.txt" 2>&1
  say "TABLESTATS $1 $2 $(grep -E 'SSTable count|SSTable Compression Ratio|Space used \(live\)' "$D/tablestats-$2.txt" | tr -s ' ' | tr '\n' ';') datafiles=$(ls "$N"/data/ra_$1/standard1-*/*-Data.db 2>/dev/null | wc -l | tr -d ' ')"
}
compact_polled() {  # compact_polled <arm>
  local arm=$1 D=$L/$1
  run nt setcompactionthroughput 16 || die "$arm: setcompactionthroughput failed"
  log "+ java Jmx.java 127.0.0.1:7199 poll 120 > $D/poll.csv &"
  java "$H/Jmx.java" 127.0.0.1:7199 poll 120 > "$D/poll.csv" 2> "$D/poll.err" &
  PPID_POLL=$!
  sleep 5
  local t0; t0=$(ms)
  log "+ nodetool compact ra_$arm standard1"
  ( sleep 2; nt compactionstats > "$D/compactionstats.txt" 2>&1 ) &
  nt compact ra_$arm standard1 >> "$CL" 2>&1; local rc=$?; local t1; t1=$(ms)
  say "COMPACT $arm rc=$rc client_start_ms=$t0 client_end_ms=$t1 secs=$(( (t1 - t0) / 1000 ))"
  log "waiting for the poller (pid $PPID_POLL)"
  local w=0; while kill -0 $PPID_POLL 2>/dev/null && [ $w -lt 200 ]; do sleep 1; w=$((w+1)); done
  kill $PPID_POLL 2>/dev/null; PPID_POLL=""
  say "POLL $arm samples=$(grep -c '^[0-9]' "$D/poll.csv") first_ms=$(head -1 "$D/poll.csv" | cut -d, -f1) last_ms=$(tail -1 "$D/poll.csv" | cut -d, -f1) stderr_lines=$(wc -l < "$D/poll.err" | tr -d ' ')"
  say "COMPACTIONSTATS $arm $(grep -E 'Compaction|pending' "$D/compactionstats.txt" | tr -s ' ' | tr '\n' ';' | cut -c1-300)"
}
arm() {  # arm <label> <set-before-writes> <set-after-writes or -> <chunks> <rows>
  local a=$1 v1=$2 v2=$3 n=$4 r=$5; mkdir -p "$L/$a"
  say "== arm $a start $(now) (start $START)"
  jset $v1 "$a-before-writes"
  stress_chunks $a $n $r
  [ "$v2" != - ] && jset $v2 "$a-after-writes"
  tstats $a before
  compact_polled $a
  tstats $a after
  run tmo 120 "$C/bin/cqlsh" 127.0.0.1 -e "DROP KEYSPACE ra_$a" || die "$a: drop failed"
  run nt clearsnapshot --all
  say "== arm $a end $(now)"
}
stop_node() {
  [ -n "$PPID_POLL" ] && { kill $PPID_POLL 2>/dev/null; PPID_POLL=""; }
  [ -z "$PID" ] && return 0
  if kill -0 $PID 2>/dev/null; then
    run tmo 300 "$C/bin/nodetool" -h 127.0.0.1 -p 7199 drain
    kill $PID 2>/dev/null; for i in $(seq 1 60); do kill -0 $PID 2>/dev/null || break; sleep 1; done
    kill -0 $PID 2>/dev/null && { log "kill -9 $PID"; kill -9 $PID; sleep 1; }
  fi
  local D=$L/$START
  say "SETLOG $START $(grep -c 'set compressed read ahead buffer size to' "$D/system.log") INFO lines: $(grep -o 'set compressed read ahead buffer size to [0-9]*KiB' "$D/system.log" | awk '{print $NF}' | tr '\n' ' ')"
  say "LOG $START errors=$(grep -c '^ERROR' "$D/system.log") trace_lines=$(wc -l < "$D/readahead.trace" 2>/dev/null | tr -d ' ')"
  PID=""; log "node stopped"
}
final_check() {
  [ -n "$PPID_POLL" ] && kill $PPID_POLL 2>/dev/null
  pkill -f 'org.apache.cassandra.stress.Stress' 2>/dev/null
  local d; d=$(ps -eo command | grep '[C]assandraDaemon'); say "final CassandraDaemon processes: ${d:-none}"
  rm -rf "$N"; say "node-crs wiped: $([ -e "$N" ] && echo no || echo yes)"
}
die() { say "ABORT: $*"; stop_node; final_check; exit 1; }
trap 'die "interrupted"' INT TERM

say "cluster-run $RUN plan $PLAN start $(now); runner sha256 $(shasum -a 256 "$0" | cut -c1-16); clone $C; node $N"
say "harness sha256: $(cd "$H" && shasum -a 256 readahead.btm Jmx.java | awk '{print $2"="substr($1,1,16)}' | tr '\n' ' ')"
say "clone $(git -C $C describe --tags) $(git -C $C rev-parse --short HEAD)"
d=$(ps -eo command | grep '[C]assandraDaemon'); [ -n "$d" ] && { say "ABORT: a Cassandra node is running"; exit 1; }
for p in 7000 7199 9042 9091; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { say "ABORT: port $p busy"; exit 1; }; done
fg=$(df -g $W | tail -1 | awk '{print $4}'); [ "$fg" -ge 20 ] || { say "ABORT: only $fg GiB free"; exit 1; }
say "pre-checks: no Cassandra node; ports 7000 7199 9042 9091 free; free disk ${fg} GiB; loopback $(ifconfig lo0 | grep -c 'inet 127.0.0.') addresses"

case $PLAN in
  sd)
    java -classpath "$BM/byteman-4.0.20.jar:$C/build/classes/main:$C/build/lib/jars/*" org.jboss.byteman.check.TestScript "$H/readahead.btm" > "$L/testscript.txt" 2>&1
    say "TESTSCRIPT $(grep -E 'TestScript:|ERROR|WARN' "$L/testscript.txt" | tr '\n' ';')"
    make_conf compressed_read_ahead_buffer_size=256KiB
    start_node sd
    java -cp "$BM/byteman-submit-4.0.20.jar" org.jboss.byteman.agent.submit.Submit -l > "$L/submit-l.txt" 2>&1
    say "SUBMIT-L $(grep -E 'RULE|ERROR' "$L/submit-l.txt" | tr -s ' ' | tr '\n' ';' | cut -c1-400)"
    arm sd 2048 - 4 20000
    stop_node
    ;;
  run1)
    make_conf compressed_read_ahead_buffer_size=256KiB
    start_node n1
    jset 255 reject
    jset 0 reject
    arm v256 256 - 16 100000
    arm v4096 4096 - 16 100000
    arm v16384 16384 - 16 100000
    arm v4096b 4096 - 16 100000
    arm stale 256 16384 16 100000
    stop_node
    make_conf compressed_read_ahead_buffer_size=256KiB file_cache_enabled=true
    start_node cc
    arm cc 16384 - 16 100000
    stop_node
    ;;
  *) say "unknown plan $PLAN" ;;
esac
stop_node; final_check
say "cluster-run $RUN end $(now)"
