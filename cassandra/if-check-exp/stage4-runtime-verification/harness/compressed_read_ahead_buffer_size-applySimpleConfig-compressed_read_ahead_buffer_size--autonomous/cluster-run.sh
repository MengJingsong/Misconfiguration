#!/usr/bin/env bash
# Cluster tier (B3, as amended 2026-10-25) of compressed_read_ahead_buffer_size-applySimpleConfig-compressed_read_ahead_buffer_size--autonomous.
# Adapted from harness/max_value_size-applySimpleConfig-max_value_size--autonomous/cluster-run.sh (copied, then changed: starts,
# yaml lines, Byteman rules, stress chunks with flushes, JMX sampler/setter CrabJmx instead of the Python client).
# usage: cluster-run.sh <outdir-name> <plan>
#   plan run1: z100 (start-up refusal), c0 (0KiB), c256 (256KiB), c16m (16MiB), ctl-cache (16MiB + file_cache_enabled: true),
#              ctl-k4 (16MiB, 4 SSTables)
#   plan sd:   shakedown (harness check, not a reading): 16MiB, 4 chunks of 20,000 rows, Byteman TestScript / Submit -l.
# One node, 127.0.0.1, clone $W/cassandra-run21, node directories under $W/node-crab (wiped before every start and at the end).
# Logs: $W/logs/compressed_read_ahead_buffer_size-applySimpleConfig/cluster-<outdir>/ : commands.log, summary.txt,
#       <start>/ (system.log, debug.log, node.out, readahead.trace, jmx.csv, stress-*.log, tablestats-*.txt, ...)
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
H=$(cd "$(dirname "$0")" && pwd)
RUN=${1:?outdir}; PLAN=${2:?plan}
L=$W/logs/compressed_read_ahead_buffer_size-applySimpleConfig/cluster-$RUN
[ -e "$L" ] && mv "$L" "$L.attempt-$(date +%s)"
mkdir -p "$L"; CL=$L/commands.log; S=$L/summary.txt; : > "$CL"; : > "$S"
C=$W/cassandra-run21; N=$W/node-crab; PID=""; CUR=""; SPID=""
BM=$C/build/lib/jars; JB=$W/harness-bin-crab
now() { date '+%Y-%m-%dT%H:%M:%S%z'; }
ms()  { python3 -c 'import time; print(int(time.time()*1000))'; }
log() { echo "[$(now)] $*" >> "$CL"; }
say() { echo "$*" >> "$S"; log "SUMMARY $*"; }
tmo() { perl -e '$t=shift; $p=fork; if(!$p){exec @ARGV; exit 127} $SIG{ALRM}=sub{kill 9,$p; waitpid $p,0; exit 124}; alarm $t; waitpid $p,0; exit($?>>8)' "$@"; }
nt()  { tmo 600 "$C/bin/nodetool" -h 127.0.0.1 -p 7199 "$@"; }
run() { log "+ $*"; "$@" >> "$CL" 2>&1; local rc=$?; log "  exit=$rc"; return $rc; }
jmx() { java -cp "$JB" CrabJmx "$@"; }

make_conf() {   # make_conf key=value ...   (a value NONE removes the key: shipped default)
  rm -rf "$N"; mkdir -p "$N/data" "$N/commitlog" "$N/hints" "$N/saved_caches" "$N/cdc_raw"
  cp -R "$C/conf" "$N/conf"
  git -C "$C" show HEAD:conf/cassandra.yaml > "$N/shipped.yaml"
  { echo "cluster_name: stage4-crab"; echo "num_tokens: 1"; echo "initial_token: 0"; echo "auto_bootstrap: false"
    echo "listen_address: 127.0.0.1"; echo "rpc_address: 127.0.0.1"
    echo "data_file_directories:"; echo "    - $N/data"
    echo "commitlog_directory: $N/commitlog"; echo "hints_directory: $N/hints"; echo "saved_caches_directory: $N/saved_caches"
    echo "cdc_raw_directory: $N/cdc_raw"
    for kv in "$@"; do echo "${kv%%=*}: ${kv#*=}"; done; } > "$N/lines.yaml"
  python3 - "$N" <<'PY'
import re, sys
n = sys.argv[1]
add = open(n + '/lines.yaml').read().splitlines()
keys = {l.split(':', 1)[0] for l in add if re.match(r'^[A-Za-z_]+:', l)}
add = [l for l in add if not l.endswith(': NONE')]
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
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 crab lines ----\n' + '\n'.join(add) + '\n')
PY
}
yaml_line() { say "YAML $1 $(sed -n '/^# ---- stage4 crab lines/,$p' $N/conf/cassandra.yaml | grep -v '^#' | grep -v '^    - ' | grep -v directory | tr '\n' ';')"; }
start_node() {  # start_node <label>
  CUR=$1; local D=$L/$1; mkdir -p "$D"
  log "+ start node $1 (conf $N/conf, logs $D, Byteman trace $D/readahead.trace)"
  CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$D MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M \
    JVM_EXTRA_OPTS="-javaagent:$BM/byteman-4.0.20.jar=script:$H/readahead.btm,listener:true -Dstage4.byteman.out=$D/readahead.trace" \
    nohup "$C/bin/cassandra" -f > "$D/node.out" 2>&1 < /dev/null &
  PID=$!; disown; log "  pid $PID"; T0=$(date +%s)
}
wait_up() {
  while :; do
    kill -0 $PID 2>/dev/null || { log "pid $PID died"; return 2; }
    if nt status 2>/dev/null | grep -q '^UN  127.0.0.1 ' && [ "$(nt statusbinary 2>/dev/null)" = running ]; then log "up after $(( $(date +%s) - T0 )) s"; return 0; fi
    [ $(( $(date +%s) - T0 )) -ge 300 ] && { log "not up in 300 s"; return 1; }
    sleep 3
  done
}
readbacks() {
  local D=$L/$CUR cfg
  cfg=$(grep -h -o 'Node configuration:\[.*' "$D/system.log" | head -1)
  say "READBACK $CUR config: $(echo "$cfg" | grep -o 'compressed_read_ahead_buffer_size=[^;]*') ; $(echo "$cfg" | grep -o 'file_cache_enabled=[^;]*') ; $(echo "$cfg" | grep -o ' disk_access_mode=[^;]*') ; $(echo "$cfg" | grep -o 'file_cache_size=[^;]*')"
  say "READBACK $CUR $(grep -h -o 'DiskAccessMode is .*' "$D/system.log" | head -1) ; jmx $(jmx get 7199 2>&1 | tail -1) ; $(ps -o command= -p $PID | tr ' ' '\n' | grep -E 'MaxDirectMemorySize|^-Xmx' | tr '\n' ' ') byteman_agent=$(ps -o command= -p $PID | grep -c 'byteman-4.0.20.jar')"
}
stress_chunks() {  # stress_chunks <n chunks> <rows per chunk>
  local n=$1 r=$2 D=$L/$CUR i lo hi
  for i in $(seq 0 $(( n - 1 ))); do
    lo=$(( r * i + 1 )); hi=$(( r * (i + 1) ))
    local s0=$(date +%s)
    (cd "$C" && tmo 600 tools/bin/cassandra-stress write n=$r no-warmup -pop seq=$lo..$hi -col 'size=FIXED(256)' 'n=FIXED(1)' -schema 'compression=LZ4Compressor' \
       -rate threads=50 -node 127.0.0.1) > "$D/stress-$i.log" 2>&1
    local rc=$?
    log "STRESS $CUR chunk $i seq=$lo..$hi rc=$rc secs=$(( $(date +%s) - s0 )) $(grep -E '^Total partitions' "$D/stress-$i.log" | tr -s ' ' | head -1) | $(grep -E '^Total errors' "$D/stress-$i.log" | tr -s ' ' | head -1)"
    echo "chunk=$i seq=$lo..$hi rc=$rc $(grep -E '^Total partitions' "$D/stress-$i.log" | tr -s ' ' | head -1) | $(grep -E '^Total errors' "$D/stress-$i.log" | tr -s ' ' | head -1)" >> "$D/stress-summary.txt"
    [ $rc -eq 0 ] || die "$CUR: stress chunk $i failed (rc $rc)"
    [ $i -eq 0 ] && run nt disableautocompaction keyspace1
    run nt flush keyspace1 || die "$CUR: flush failed"
  done
  say "STRESS $CUR chunks=$n rows/chunk=$r ok=$(grep -c ' rc=0 ' "$D/stress-summary.txt") partitions=[$(grep -o 'Total partitions : [0-9,]*' "$D/stress-summary.txt" | awk '{print $4}' | sort | uniq -c | awk '{print $2"x"$1}' | tr '\n' ' ')] errors=[$(grep -o 'Total errors : [0-9,]*' "$D/stress-summary.txt" | awk '{print $4}' | sort | uniq -c | awk '{print $2"x"$1}' | tr '\n' ' ')]"
}
tstats() {  # tstats <tag>
  local D=$L/$CUR
  nt tablestats keyspace1.standard1 > "$D/tablestats-$1.txt" 2>&1
  say "TABLESTATS $CUR $1 $(grep -E 'SSTable count|SSTable Compression Ratio|Space used \(live\)' "$D/tablestats-$1.txt" | tr -s ' ' | tr '\n' ';') datafiles=$(ls "$N"/data/keyspace1/standard1-*/*-Data.db 2>/dev/null | wc -l | tr -d ' ')"
}
compact_sampled() {
  local D=$L/$CUR
  echo baseline > "$D/phase"; rm -f "$D/stop"
  java -cp "$JB" CrabJmx sample 7199 "$D/jmx.csv" "$D/phase" "$D/stop" 250 > "$D/sampler.out" 2>&1 &
  SPID=$!; log "sampler pid $SPID"
  sleep 30
  echo compact > "$D/phase"; local t0; t0=$(ms)
  log "+ nodetool compact keyspace1 standard1"
  nt compact keyspace1 standard1 >> "$CL" 2>&1; local rc=$?; local t1; t1=$(ms)
  echo after > "$D/phase"
  say "COMPACT $CUR rc=$rc client_start_ms=$t0 client_end_ms=$t1 secs=$(( (t1 - t0) / 1000 ))"
  sleep 15
  touch "$D/stop"; for i in $(seq 1 20); do kill -0 $SPID 2>/dev/null || break; sleep 0.5; done
  kill $SPID 2>/dev/null; SPID=""
  say "SAMPLES $CUR $(awk -F, 'NR>1{n[$2]++} END{for(p in n) printf "%s=%d ", p, n[p]}' "$D/jmx.csv") errors=$(grep -c ERROR "$D/jmx.csv")"
}
stop_node() {
  [ -n "$SPID" ] && { kill $SPID 2>/dev/null; SPID=""; }
  [ -z "$PID" ] && return 0
  if kill -0 $PID 2>/dev/null; then
    run tmo 300 "$C/bin/nodetool" -h 127.0.0.1 -p 7199 drain
    kill $PID 2>/dev/null; for i in $(seq 1 60); do kill -0 $PID 2>/dev/null || break; sleep 1; done
    kill -0 $PID 2>/dev/null && { log "kill -9 $PID"; kill -9 $PID; sleep 1; }
  fi
  PID=""; log "node stopped"
}
digest() {  # per-start trace digest (the self-check re-derives everything from the raw trace)
  local D=$L/$CUR
  python3 - "$D/readahead.trace" "$CUR" >> "$S" <<'PY'
import re, sys
p, cur = sys.argv[1], sys.argv[2]
try: lines = open(p).read().splitlines()
except FileNotFoundError: lines = []
own = lambda f: '/keyspace1/standard1-' in f and f.endswith('-Data.db')
A = [dict(re.findall(r'(\w+)=(\S+)', l)) for l in lines if l.startswith('alloc ')]
F = [dict(re.findall(r'(\w+)=(\S+)', l)) for l in lines if l.startswith('free ')]
oa = [a for a in A if own(a['file'])]; of = [f for f in F if own(f['file'])]
ev = sorted([(int(a['ms']), 1) for a in oa] + [(int(f['ms']), -1) for f in of])
live = mx = 0
for t, d in ev:
    live += d; mx = max(mx, live)
caps = {}
for a in oa: caps[(a['cap'], a['direct'])] = caps.get((a['cap'], a['direct']), 0) + 1
print('TRACE %s own_alloc=%d own_free=%d max_live=%d caps=%s threads=%s other_alloc=%d other_free=%d first_ms=%s last_ms=%s' % (
    cur, len(oa), len(of), mx, caps, sorted({a['thread'] for a in oa}), len(A) - len(oa), len(F) - len(of),
    min([int(a['ms']) for a in oa], default='-'), max([int(f['ms']) for f in of], default='-')))
PY
  say "LOG $CUR errors=$(grep -c '^ERROR' "$D/system.log") warn_readahead=$(grep -ci 'read.ahead' "$D/system.log")"
}
final_check() {
  [ -n "$SPID" ] && kill $SPID 2>/dev/null
  pkill -f 'org.apache.cassandra.stress.Stress' 2>/dev/null
  local d; d=$(ps -eo command | grep '[C]assandraDaemon'); say "final CassandraDaemon processes: ${d:-none}"
  rm -rf "$N"; say "node-crab wiped: $([ -e "$N" ] && echo no || echo yes)"
}
die() { say "ABORT: $*"; stop_node; final_check; exit 1; }
trap 'die "interrupted"' INT TERM

refusal() {  # refusal <label> <value>
  CUR=$1; local v=$2 D=$L/$1; mkdir -p "$D"
  say "== $CUR compressed_read_ahead_buffer_size=$v start $(now)"
  make_conf compressed_read_ahead_buffer_size=$v; yaml_line $CUR
  log "+ bin/cassandra -f (expect refusal), wait <= 120 s"
  local t0=$(date +%s)
  CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$D MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M tmo 120 "$C/bin/cassandra" -f > "$D/node.out" 2>&1 < /dev/null
  local rc=$?
  say "REFUSAL $CUR rc=$rc secs=$(( $(date +%s) - t0 )) startup_complete=$(cat "$D/node.out" "$D/system.log" 2>/dev/null | grep -c 'Startup complete')"
  say "REFUSAL-LINES $CUR $(grep -h 'compressed_read_ahead_buffer_size must' "$D/node.out" "$D/system.log" 2>/dev/null | cut -c1-240 | sort | uniq -c | tr -s ' ' | tr '\n' ';')"
  sleep 2; d=$(ps -eo command | grep '[C]assandraDaemon'); [ -n "$d" ] && die "$CUR: a Cassandra node is still running"
  rm -rf "$N"; say "== $CUR end $(now)"
}
arm() {  # arm <label> <chunks> <rows/chunk> key=value...
  local lab=$1 n=$2 r=$3; shift 3
  say "== $lab start $(now)"
  make_conf "$@"; yaml_line $lab
  start_node $lab; wait_up || die "$lab: node did not start"
  readbacks
  stress_chunks $n $r
  tstats before
  compact_sampled
  tstats after
  if [ $lab = c0 ]; then
    say "SETTER $lab $(jmx set 7199 0 2>&1 | tr '\n' ' ')"
    say "SETTER $lab $(jmx set 7199 255 2>&1 | tr '\n' ' ')"
  fi
  stop_node; digest
  rm -rf "$N"; say "== $lab end $(now)"
}

say "cluster-run $RUN plan $PLAN start $(now); runner sha256 $(shasum -a 256 "$0" | cut -c1-16); clone $C; node $N"
say "harness sha256: $(cd "$H" && shasum -a 256 readahead.btm CrabJmx.java | awk '{print $2"="substr($1,1,16)}' | tr '\n' ' ')"
say "clone $(git -C $C describe --tags) $(git -C $C rev-parse --short HEAD)"
d=$(ps -eo command | grep '[C]assandraDaemon'); [ -n "$d" ] && { say "ABORT: a Cassandra node is running"; exit 1; }
for p in 7000 7199 9042 9091; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { say "ABORT: port $p busy"; exit 1; }; done
fg=$(df -g $W | tail -1 | awk '{print $4}'); [ "$fg" -ge 20 ] || { say "ABORT: only $fg GiB free"; exit 1; }
say "pre-checks: no Cassandra node; ports 7000 7199 9042 9091 free; free disk ${fg} GiB; loopback $(ifconfig lo0 | grep -c 'inet 127.0.0.') addresses"
mkdir -p "$JB"; javac -d "$JB" "$H/CrabJmx.java" >> "$CL" 2>&1 || { say "ABORT: javac CrabJmx failed"; exit 1; }

case $PLAN in
  sd)
    java -classpath "$BM/byteman-4.0.20.jar:$C/build/classes/main:$C/build/lib/jars/*" org.jboss.byteman.check.TestScript "$H/readahead.btm" > "$L/testscript.txt" 2>&1
    say "TESTSCRIPT $(grep -E 'TestScript:|ERROR|WARN' "$L/testscript.txt" | tr '\n' ';')"
    CUR=sd; say "== sd start $(now)"; make_conf compressed_read_ahead_buffer_size=16MiB; yaml_line sd
    start_node sd; wait_up || die "sd: node did not start"
    java -cp "$BM/byteman-submit-4.0.20.jar" org.jboss.byteman.agent.submit.Submit -l > "$L/submit-l.txt" 2>&1
    say "SUBMIT-L $(grep -E 'RULE|trigger method|ERROR' "$L/submit-l.txt" | tr -s ' ' | tr '\n' ';' | cut -c1-600)"
    readbacks; stress_chunks 4 20000; tstats before; compact_sampled; tstats after
    say "SETTER sd $(jmx set 7199 0 2>&1 | tr '\n' ' ')"
    stop_node; digest; rm -rf "$N"
    ;;
  run1)
    refusal z100 100KiB
    arm c0 32 100000 compressed_read_ahead_buffer_size=0KiB
    arm c256 32 100000 compressed_read_ahead_buffer_size=256KiB
    arm c16m 32 100000 compressed_read_ahead_buffer_size=16MiB
    arm ctl-cache 32 100000 compressed_read_ahead_buffer_size=16MiB file_cache_enabled=true
    arm ctl-k4 4 100000 compressed_read_ahead_buffer_size=16MiB
    ;;
  *) say "unknown plan $PLAN" ;;
esac
stop_node; final_check
say "cluster-run $RUN end $(now)"
