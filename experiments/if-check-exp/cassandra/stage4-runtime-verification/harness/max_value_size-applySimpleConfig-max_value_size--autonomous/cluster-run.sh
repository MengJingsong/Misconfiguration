#!/usr/bin/env bash
# Cluster tier (B3, as amended 2026-10-25) of max_value_size-applySimpleConfig-max_value_size--autonomous.
# Adapted from harness/max_mutation_size-applySimpleConfig-max_mutation_size--autonomous/cluster-run.sh (copied, then changed: starts,
# held-fixed yaml lines, Byteman agent, client, no JMX reader, no stress, no wipe between phase 1 and phase 2).
# usage: cluster-run.sh <outdir-name> <plan>
#   plan run1: z0 z2048 (start-up refusals), p1 (write phase, default 256MiB), r1 (1MiB), r8 (8MiB), r256 (default; control)
#   plan sd:   shakedown (harness check, not a reading): default settings, one 307,200 B value, Byteman TestScript / Submit -l,
#              flush, drain, restart on the same data, read again.
# One node, 127.0.0.1, clone $W/cassandra-run20, node directories under $W/node-mvs.
# Logs: $W/logs/max_value_size-applySimpleConfig/cluster-<outdir>/ : commands.log, summary.txt, req.txt, written.json,
#       <start>/ (system.log, debug.log, node.out, alloc.trace, ...)
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
H=$(cd "$(dirname "$0")" && pwd)
RUN=${1:?outdir}; PLAN=${2:?plan}
L=$W/logs/max_value_size-applySimpleConfig/cluster-$RUN
[ -e "$L" ] && mv "$L" "$L.attempt-$(date +%s)"
mkdir -p "$L"; CL=$L/commands.log; S=$L/summary.txt; REQ=$L/req.txt; WR=$L/written.json; : > "$CL"; : > "$S"; : > "$REQ"
C=$W/cassandra-run20; N=$W/node-mvs; PID=""; CUR=""
BM=$C/build/lib/jars
DRV=$(ls "$C"/lib/cassandra-driver-internal-only-*.zip | head -1)
now() { date '+%Y-%m-%dT%H:%M:%S%z'; }
log() { echo "[$(now)] $*" >> "$CL"; }
say() { echo "$*" >> "$S"; log "SUMMARY $*"; }
tmo() { perl -e '$t=shift; $p=fork; if(!$p){exec @ARGV; exit 127} $SIG{ALRM}=sub{kill 9,$p; waitpid $p,0; exit 124}; alarm $t; waitpid $p,0; exit($?>>8)' "$@"; }
nt()  { tmo 120 "$C/bin/nodetool" -h 127.0.0.1 -p 7199 "$@"; }
run() { log "+ $*"; "$@" >> "$CL" 2>&1; local rc=$?; log "  exit=$rc"; return $rc; }
cl()  { log "+ mvsclient $CUR $*"; tmo 300 python3 "$H/mvsclient.py" "$DRV" "$CUR" "$REQ" "$WR" "$@" >> "$CL" 2>&1; local rc=$?; say "$(tail -1 "$REQ" | cut -c1-700)"; return $rc; }

make_conf() {   # make_conf key=value ...   (a value NONE removes the key: shipped default)
  rm -rf "$N/conf"; mkdir -p "$N/data" "$N/commitlog" "$N/hints" "$N/saved_caches" "$N/cdc_raw"
  cp -R "$C/conf" "$N/conf"
  git -C "$C" show HEAD:conf/cassandra.yaml > "$N/shipped.yaml"
  { echo "cluster_name: stage4-mvs"; echo "num_tokens: 1"; echo "initial_token: 0"; echo "auto_bootstrap: false"
    echo "listen_address: 127.0.0.1"; echo "rpc_address: 127.0.0.1"
    echo "data_file_directories:"; echo "    - $N/data"
    echo "commitlog_directory: $N/commitlog"; echo "hints_directory: $N/hints"; echo "saved_caches_directory: $N/saved_caches"
    echo "cdc_raw_directory: $N/cdc_raw"
    echo "read_request_timeout: 10000ms"; echo "range_request_timeout: 10000ms"; echo "write_request_timeout: 10000ms"
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
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 mvs lines ----\n' + '\n'.join(add) + '\n')
PY
}
yaml_line() { say "YAML $1 $(sed -n '/^# ---- stage4 mvs lines/,$p' $N/conf/cassandra.yaml | grep -v '^#' | grep -v '^    - ' | grep -v directory | tr '\n' ';')"; }
start_node() {  # start_node <label>
  CUR=$1; local D=$L/$1; mkdir -p "$D"
  log "+ start node $1 (conf $N/conf, logs $D, Byteman trace $D/alloc.trace)"
  CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$D MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M \
    JVM_EXTRA_OPTS="-javaagent:$BM/byteman-4.0.20.jar=script:$H/value-alloc.btm,listener:true -Dstage4.byteman.out=$D/alloc.trace" \
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
startup_lines() {  # after wait_up: replay and start-up lines of the current start
  local D=$L/$CUR
  local before; before=$(awk '/Startup complete/{exit} {print}' "$D/system.log" | grep -c 'Corrupt value length')
  say "STARTUP $CUR up_secs=$(( $(date +%s) - T0 )) startup_complete=$(grep -c 'Startup complete' "$D/system.log") corrupt_before_startup=$before replay=[$(grep -h -o 'Log replay complete.*\|No commitlog files found.*' "$D/system.log" "$D/debug.log" 2>/dev/null | head -2 | tr '\n' ';')] byteman_agent=$(ps -o command= -p $PID | grep -c 'byteman-4.0.20.jar')"
}
stop_node() {
  [ -z "$PID" ] && return 0
  if kill -0 $PID 2>/dev/null; then
    run tmo 300 "$C/bin/nodetool" -h 127.0.0.1 -p 7199 drain
    kill $PID 2>/dev/null; for i in $(seq 1 60); do kill -0 $PID 2>/dev/null || break; sleep 1; done
    kill -0 $PID 2>/dev/null && { log "kill -9 $PID"; kill -9 $PID; sleep 1; }
  fi
  PID=""; log "node stopped"; say "COMMITLOG after stop $CUR: $(ls -l $N/commitlog 2>/dev/null | grep -c CommitLog) segment file(s)"
}
end_start() {  # per-start log digest
  local D=$L/$CUR
  grep -h 'Corrupt value length' "$D/system.log" 2>/dev/null | cut -c1-400 > "$D/guard-lines.txt"
  say "LOG $CUR corrupt_value_length=$(grep -c 'Corrupt value length' "$D/system.log") corrupt_sstable=$(grep -c 'CorruptSSTableException' "$D/system.log") errors=$(grep -c '^ERROR' "$D/system.log")"
  say "TRACE $CUR lines=$(grep -c '^alloc ' "$D/alloc.trace" 2>/dev/null || echo 0) lengths=[$(grep -o 'length=[0-9]*' "$D/alloc.trace" 2>/dev/null | sort | uniq -c | awk '{print $2"x"$1}' | tr '\n' ' ')]"
}
final_check() {
  local d; d=$(ps -eo command | grep '[C]assandraDaemon'); say "final CassandraDaemon processes: ${d:-none}"
  rm -rf "$N"; say "node-mvs wiped: $([ -e "$N" ] && echo no || echo yes)"
}
die() { say "ABORT: $*"; stop_node; final_check; exit 1; }
trap 'die "interrupted"' INT TERM

refusal() {  # refusal <label> <max_value_size>
  CUR=$1; local v=$2 D=$L/$1; mkdir -p "$D"
  say "== $CUR max_value_size=$v start $(now)"
  rm -rf "$N"; make_conf max_value_size=$v; yaml_line $CUR
  log "+ bin/cassandra -f (expect refusal), wait <= 120 s"
  local t0=$(date +%s)
  CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$D MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M tmo 120 "$C/bin/cassandra" -f > "$D/node.out" 2>&1 < /dev/null
  local rc=$?
  say "REFUSAL $CUR rc=$rc secs=$(( $(date +%s) - t0 )) startup_complete=$(cat "$D/node.out" "$D/system.log" 2>/dev/null | grep -c 'Startup complete')"
  say "REFUSAL-LINES $CUR $(grep -h 'max_value_size' "$D/node.out" "$D/system.log" 2>/dev/null | cut -c1-220 | sort | uniq -c | tr -s ' ' | tr '\n' ';')"
  sleep 2; d=$(ps -eo command | grep '[C]assandraDaemon'); [ -n "$d" ] && die "$CUR: a Cassandra node is still running"
  rm -rf "$N"; say "== $CUR end $(now)"
}
up() {  # up <label> key=value...
  local lab=$1; shift
  say "== $lab start $(now)"
  make_conf "$@"; yaml_line $lab
  start_node $lab; wait_up || die "$lab: node did not start"
  startup_lines
  cl settings
}

say "cluster-run $RUN plan $PLAN start $(now); runner sha256 $(shasum -a 256 "$0" | cut -c1-16); clone $C; node $N; driver $DRV"
say "harness sha256: $(cd "$H" && shasum -a 256 mvsclient.py value-alloc.btm | awk '{print $2"="substr($1,1,16)}' | tr '\n' ' ')"
say "clone $(git -C $C describe --tags) $(git -C $C rev-parse --short HEAD)"
d=$(ps -eo command | grep '[C]assandraDaemon'); [ -n "$d" ] && { say "ABORT: a Cassandra node is running"; exit 1; }
for p in 7000 7199 9042 9091; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { say "ABORT: port $p busy"; exit 1; }; done
fg=$(df -g $W | tail -1 | awk '{print $4}'); [ "$fg" -ge 20 ] || { say "ABORT: only $fg GiB free"; exit 1; }
say "pre-checks: no Cassandra node; ports 7000 7199 9042 9091 free; free disk ${fg} GiB; loopback $(ifconfig lo0 | grep -c 'inet 127.0.0.') addresses"

case $PLAN in
  sd)
    java -classpath "$BM/byteman-4.0.20.jar:$C/build/classes/main:$C/build/lib/jars/*" org.jboss.byteman.check.TestScript "$H/value-alloc.btm" > "$L/testscript.txt" 2>&1
    say "TESTSCRIPT $(grep -E 'TestScript:|ERROR' "$L/testscript.txt" | tr '\n' ';')"
    rm -rf "$N"; up sd1 max_value_size=NONE
    java -cp "$BM/byteman-submit-4.0.20.jar" org.jboss.byteman.agent.submit.Submit -l > "$L/submit-l.txt" 2>&1
    say "SUBMIT-L $(grep -E 'RULE|trigger method' "$L/submit-l.txt" | tr -s ' ' | tr '\n' ';' | cut -c1-500)"
    cl schema; cl insert 100 307200; cl read 100
    run nt flush ks t; cl read 100
    end_start; stop_node
    up sd2 max_value_size=NONE
    cl read 100; cl readall
    end_start; stop_node
    ;;
  run1)
    refusal z0 0MiB
    refusal z2048 2048MiB
    rm -rf "$N"; up p1 max_value_size=NONE
    cl schema
    for kv in 1:524288 2:4194304 3:12582912 4:1048576 5:1048577 6:8388608 7:8388609; do cl insert ${kv%%:*} ${kv#*:}; done
    run nt flush ks t
    ls -l "$N"/data/ks/t-*/ > "$L/p1/listing.txt" 2>&1
    say "DATA p1 $(awk '/Data.db/{print $NF"="$5}' "$L/p1/listing.txt" | tr '\n' ' ')"
    end_start; stop_node
    up r1 max_value_size=1MiB
    for k in 1 2 3 4 5 6 7; do cl read $k; done
    cl readall
    cl insert 8 2097152; cl read 8
    end_start; stop_node
    up r8 max_value_size=8MiB
    for k in 1 2 3 4 5 6 7 8; do cl read $k; done
    cl readall
    end_start; stop_node
    up r256 max_value_size=NONE
    for k in 1 2 3 4 5 6 7 8; do cl read $k; done
    cl readall
    ls -l "$N"/data/ks/t-*/ > "$L/r256/listing.txt" 2>&1
    end_start; stop_node
    ;;
  *) say "unknown plan $PLAN" ;;
esac
stop_node; final_check
say "cluster-run $RUN end $(now)"
