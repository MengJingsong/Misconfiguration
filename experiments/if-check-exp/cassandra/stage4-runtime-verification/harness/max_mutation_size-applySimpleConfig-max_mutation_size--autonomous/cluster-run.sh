#!/usr/bin/env bash
# Cluster tier (B3, as amended 2026-10-25) of max_mutation_size-applySimpleConfig-max_mutation_size--autonomous.
# Copied from harness/commitlog_segment_size-applySimpleConfig-commitlog_segment_size--autonomous/cluster-run.sh, then changed
# (arms, held-fixed yaml lines, JMX reader, requests, stress).
# usage: cluster-run.sh <outdir-name> [arm ...]
#   arms: a4097 (start-up refusal), m1024, m2048, mdef (no max_mutation_size line), tdef (INFO: 1024KiB, transport defaults),
#         sd (shakedown: m1024 settings, stress n=200; a harness check, not a reading)
#   default arm list: a4097 m1024 m2048 mdef tdef
# One node, 127.0.0.1, clone $W/cassandra-run16, node directories under $W/node-mms (wiped before and after every arm).
# Logs: $W/logs/max_mutation_size-applySimpleConfig/cluster-<outdir>/ : commands.log, summary.txt, <arm>/ (system.log, node.out,
#       settings.txt, req.txt, stress.log, jmx-stress.csv, readback.txt, log-lines.txt)
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
H=$(cd "$(dirname "$0")" && pwd)
RUN=${1:?outdir}; shift
ARMS=${*:-a4097 m1024 m2048 mdef tdef}
L=$W/logs/max_mutation_size-applySimpleConfig/cluster-$RUN
[ -e "$L" ] && mv "$L" "$L.attempt-$(date +%s)"
mkdir -p "$L"; CL=$L/commands.log; S=$L/summary.txt; : > "$CL"; : > "$S"
C=$W/cassandra-run16; N=$W/node-mms; PID=""
DRV=$(ls "$C"/lib/cassandra-driver-internal-only-*.zip | head -1)
now() { date '+%Y-%m-%dT%H:%M:%S%z'; }
log() { echo "[$(now)] $*" >> "$CL"; }
say() { echo "$*" >> "$S"; log "SUMMARY $*"; }
tmo() { perl -e '$t=shift; $p=fork; if(!$p){exec @ARGV; exit 127} $SIG{ALRM}=sub{kill 9,$p; waitpid $p,0; exit 124}; alarm $t; waitpid $p,0; exit($?>>8)' "$@"; }
nt()  { tmo 120 "$C/bin/nodetool" -h 127.0.0.1 -p 7199 "$@"; }
cq()  { tmo 300 "$C/bin/cqlsh" 127.0.0.1 9042 --request-timeout=120 "$@"; }
run() { log "+ $*"; "$@" >> "$CL" 2>&1; local rc=$?; log "  exit=$rc"; return $rc; }
mkdir -p "$W/harness-bin-mms"; javac -d "$W/harness-bin-mms" "$H/MMSampler.java" >> "$CL" 2>&1 || { say "ABORT: javac MMSampler"; exit 1; }
J() { java -cp "$W/harness-bin-mms" MMSampler "$@"; }

make_conf() {   # make_conf key=value ...   (a value NONE removes the key: shipped default)
  rm -rf "$N"; mkdir -p "$N/data" "$N/commitlog" "$N/hints" "$N/saved_caches" "$N/cdc_raw"
  cp -R "$C/conf" "$N/conf"
  git -C "$C" show HEAD:conf/cassandra.yaml > "$N/shipped.yaml"
  { echo "cluster_name: stage4-mms"; echo "num_tokens: 1"; echo "initial_token: 0"; echo "auto_bootstrap: false"
    echo "listen_address: 127.0.0.1"; echo "rpc_address: 127.0.0.1"
    echo "data_file_directories:"; echo "    - $N/data"
    echo "commitlog_directory: $N/commitlog"; echo "hints_directory: $N/hints"; echo "saved_caches_directory: $N/saved_caches"
    echo "cdc_raw_directory: $N/cdc_raw"; echo "commitlog_segment_size: 8MiB"; echo "commitlog_total_space: 1024MiB"
    echo "batch_size_warn_threshold: 4096KiB"; echo "batch_size_fail_threshold: 4096KiB"
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
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 mms lines ----\n' + '\n'.join(add) + '\n')
PY
}
start_node() {  # start_node <logdir>
  local ld=$1; mkdir -p "$ld"
  log "+ start node (conf $N/conf, logs $ld)"
  CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$ld MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M \
    nohup "$C/bin/cassandra" -f > "$ld/node.out" 2>&1 < /dev/null &
  PID=$!; disown; log "  pid $PID"
}
wait_up() {
  local t0=$(date +%s)
  while :; do
    kill -0 $PID 2>/dev/null || { log "pid $PID died"; return 2; }
    if nt status 2>/dev/null | grep -q '^UN  127.0.0.1 ' && [ "$(nt statusbinary 2>/dev/null)" = running ]; then log "up after $(( $(date +%s) - t0 )) s"; return 0; fi
    [ $(( $(date +%s) - t0 )) -ge 300 ] && { log "not up in 300 s"; return 1; }
    sleep 3
  done
}
stop_node() {
  [ -z "$PID" ] && return 0
  if kill -0 $PID 2>/dev/null; then
    run tmo 300 "$C/bin/nodetool" -h 127.0.0.1 -p 7199 drain
    kill $PID 2>/dev/null; for i in $(seq 1 60); do kill -0 $PID 2>/dev/null || break; sleep 1; done
    kill -0 $PID 2>/dev/null && { log "kill -9 $PID"; kill -9 $PID; sleep 1; }
  fi
  PID=""; log "node stopped"
}
final_check() {
  pkill -9 -f cassandra-stress 2>/dev/null; pkill -f 'MMSampler sample' 2>/dev/null
  local d; d=$(ps -eo command | grep '[C]assandraDaemon'); say "final CassandraDaemon processes: ${d:-none}"
  pgrep -f cassandra-stress >/dev/null && say "WARNING: cassandra-stress still running" || say "no cassandra-stress left"
  rm -rf "$N"; say "node-mms wiped: $([ -e "$N" ] && echo no || echo yes)"
}
die() { say "ABORT: $*"; stop_node; final_check; exit 1; }
trap 'die "interrupted"' INT TERM

refusal_arm() {  # refusal_arm <label> <max_mutation_size>
  local lab=$1 v=$2 D=$L/$1; mkdir -p "$D"
  say "== $lab max_mutation_size=$v start $(now)"
  make_conf max_mutation_size=$v native_transport_max_message_size=64MiB native_transport_max_request_data_in_flight=128MiB native_transport_max_request_data_in_flight_per_ip=128MiB
  say "YAML $lab $(sed -n '/^# ---- stage4 mms lines/,$p' $N/conf/cassandra.yaml | grep -v '^#' | tr '\n' ';')"
  log "+ bin/cassandra -f (expect refusal), wait <= 120 s"
  local t0=$(date +%s)
  CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$D MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M tmo 120 "$C/bin/cassandra" -f > "$D/node.out" 2>&1 < /dev/null
  local rc=$?
  say "REFUSAL $lab rc=$rc secs=$(( $(date +%s) - t0 )) startup_complete=$(cat "$D/node.out" "$D/system.log" 2>/dev/null | grep -c 'Startup complete')"
  say "REFUSAL-LINES $lab $(grep -h 'max_mutation_size' "$D/node.out" "$D/system.log" 2>/dev/null | cut -c1-220 | sort | uniq -c | tr -s ' ' | tr '\n' ';')"
  sleep 2; d=$(ps -eo command | grep '[C]assandraDaemon'); [ -n "$d" ] && die "$lab: a Cassandra node is still running"
  rm -rf "$N"; say "== $lab end $(now)"
}

arm() {   # arm <label> <stress n or 0> key=value ...
  local lab=$1 n=$2; shift 2; local D=$L/$lab; mkdir -p "$D"
  say "== $lab stress_n=$n extra=[$*] start $(now)"
  make_conf "$@"
  say "YAML $lab $(sed -n '/^# ---- stage4 mms lines/,$p' $N/conf/cassandra.yaml | grep -v '^#' | tr '\n' ';')"
  start_node "$D"; wait_up || die "$lab: node did not start"
  cq -e "SELECT name, value FROM system_views.settings WHERE name IN ('commitlog_segment_size','max_mutation_size','native_transport_max_message_size','native_transport_max_request_data_in_flight','native_transport_max_request_data_in_flight_per_ip','batch_size_fail_threshold','commitlog_total_space');" > "$D/settings.txt" 2>&1
  say "SETTINGS $lab $(grep -E '^ *(commitlog|max_mutation|native|batch)' "$D/settings.txt" | tr -s ' ' | tr '\n' ';')"
  J once 7199 > "$D/readback.txt" 2>&1; say "JMX-ONCE $lab $(tail -1 "$D/readback.txt")"
  log "+ mmwrite.py $lab"
  tmo 900 python3 "$H/mmwrite.py" "$DRV" "$lab" "$D/req.txt" java -cp "$W/harness-bin-mms" MMSampler once 7199 >> "$CL" 2>&1
  log "  exit=$?"
  while read -r l; do say "$lab $l"; done < "$D/req.txt"
  if [ "$n" -gt 0 ]; then
    local flag=$D/sampling; touch "$flag"
    J sample 7199 "$D/jmx-stress.csv" 2000 "$flag" > "$D/jmx-sampler.out" 2>&1 &
    local jpid=$!
    sleep 4
    local t0=$(date +%s)
    log "+ cassandra-stress write n=$n no-warmup -col size=FIXED(900000) n=FIXED(1) -rate threads=8 -node 127.0.0.1"
    tmo 1800 "$C/tools/bin/cassandra-stress" write n=$n no-warmup -col 'size=FIXED(900000)' 'n=FIXED(1)' -rate threads=8 -node 127.0.0.1 > "$D/stress.log" 2>&1
    local rc=$?
    say "STRESS $lab exit=$rc secs=$(( $(date +%s) - t0 )) $(grep -E '^(Op rate|Partition rate|Total partitions|Total errors|Total operation time)' "$D/stress.log" | tr -s ' ' | tr '\n' ';')"
    sleep 4; rm -f "$flag"; wait $jpid 2>/dev/null
    say "JMX-STRESS $lab first=$(sed -n 2p "$D/jmx-stress.csv") last=$(grep '^[0-9]' "$D/jmx-stress.csv" | tail -1) samples=$(grep -c '^[0-9]' "$D/jmx-stress.csv") errors=$(grep -c '^# error' "$D/jmx-stress.csv")"
  fi
  grep -h 'Rejected an oversized mutation\|Failed to apply mutation locally\|CQL Message of size\|Batch too large' "$D/system.log" 2>/dev/null | cut -c1-300 > "$D/log-lines.txt"
  say "LOGLINES $lab oversized=$(grep -c 'Rejected an oversized mutation' "$D/system.log") failed_locally=$(grep -c 'Failed to apply mutation locally' "$D/system.log") batch_too_large=$(grep -c 'Batch too large' "$D/system.log")"
  stop_node; rm -rf "$N"
  say "== $lab end $(now)"
}

T64="native_transport_max_message_size=64MiB native_transport_max_request_data_in_flight=128MiB native_transport_max_request_data_in_flight_per_ip=128MiB"
say "cluster-run $RUN start $(now) arms: $ARMS; runner sha256 $(shasum -a 256 "$0" | cut -c1-16); clone $C; node $N; driver $DRV"
say "clone $(git -C $C describe --tags) $(git -C $C rev-parse --short HEAD)"
d=$(ps -eo command | grep '[C]assandraDaemon'); [ -n "$d" ] && { say "ABORT: a Cassandra node is running"; exit 1; }
for p in 7000 7199 9042 9091; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { say "ABORT: port $p busy"; exit 1; }; done
fg=$(df -g $W | tail -1 | awk '{print $4}'); [ "$fg" -ge 20 ] || { say "ABORT: only $fg GiB free"; exit 1; }
say "pre-checks: no Cassandra node; ports 7000 7199 9042 9091 free; free disk ${fg} GiB; loopback $(ifconfig lo0 | grep -c 'inet 127.0.0.') addresses"
for a in $ARMS; do
  case $a in
    a4097) refusal_arm a4097 4097KiB ;;
    m1024) arm m1024 2000 max_mutation_size=1024KiB $T64 ;;
    m2048) arm m2048 0 max_mutation_size=2048KiB $T64 ;;
    mdef)  arm mdef 0 max_mutation_size=NONE $T64 ;;
    tdef)  arm tdef 0 max_mutation_size=1024KiB ;;
    sd)    arm sd 200 max_mutation_size=1024KiB $T64 ;;
    *) say "unknown arm $a" ;;
  esac
  say "free disk after $a: $(df -h $W | tail -1 | awk '{print $4}')"
done
stop_node; final_check
say "cluster-run $RUN end $(now)"
