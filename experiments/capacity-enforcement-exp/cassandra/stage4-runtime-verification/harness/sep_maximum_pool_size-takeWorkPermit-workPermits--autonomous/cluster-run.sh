#!/usr/bin/env bash
# Cluster tier (B3, as amended 2026-10-26) of sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous.
# Structure adapted from harness/coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous/cluster-run.sh.
# usage: cluster-run.sh <outdir-name> <plan>
#   plan run1:  populate; knobs 16 64 128 256 (idle 30, C8 180, drain, C400 180, drain; at 256 also shrink -> 16,
#               postshrink-idle 60, postshrink-C400 60, drain); control X (knob 256, -Xss1m: idle 30, C400 180, drain)
#   plan shake: populate; knob 256 (idle 10, C8 20, C400 40, shrink, postshrink-idle 10, postshrink-C400 20); knob 16
#               (idle 10, C400 40). Harness check only; readings not used.
# One node on 127.0.0.1 from $W/cassandra-run29, directories under $W/node-sep (wiped at the end).
# Logs: $W/logs/sep_maximum_pool_size-takeWorkPermit/cluster-<outdir>/
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
H=$(cd "$(dirname "$0")" && pwd)
RUN=${1:?outdir}; PLAN=${2:?plan}
L=$W/logs/sep_maximum_pool_size-takeWorkPermit/cluster-$RUN
[ -e "$L" ] && mv "$L" "$L.attempt-$(date +%s)"
mkdir -p "$L"; CL=$L/commands.log; S=$L/summary.txt; PH=$L/phases.txt; : > "$CL"; : > "$S"; : > "$PH"
C=${SEP_C:-$W/cassandra-run29}; N=${SEP_NODE:-$W/node-sep}; PID=""; CUR=""; SPID=""; D=""  # H1 (2026-10-28): clone and node from the environment; defaults = run 1
HB=$W/harness-bin-sep
DRV=$(ls "$C"/lib/cassandra-driver-internal-only-*.zip | head -1)
NTRB='org.apache.cassandra.transport:type=Native-Transport-Requests'
NTRG='org.apache.cassandra.metrics:type=ThreadPools,path=transport,scope=Native-Transport-Requests,name=MaxPoolSize'
now() { date '+%Y-%m-%dT%H:%M:%S%z'; }
ems() { perl -MTime::HiRes=time -e 'printf "%d\n", time*1000'; }
log() { echo "[$(now)] $*" >> "$CL"; }
say() { echo "$*" >> "$S"; log "SUMMARY $*"; }
tmo() { perl -e '$t=shift; $p=fork; if(!$p){exec @ARGV; exit 127} $SIG{ALRM}=sub{kill 9,$p; waitpid $p,0; exit 124}; alarm $t; waitpid $p,0; exit($?>>8)' "$@"; }
nt()  { tmo 300 "$C/bin/nodetool" -h 127.0.0.1 -p 7199 "$@"; }
run() { log "+ $*"; "$@" >> "$CL" 2>&1; local rc=$?; log "  exit=$rc"; return $rc; }
jmx() { tmo 60 java -cp "$HB" Jmx "$@" 2>&1; }
phase() { echo "$1" > "$D/phase"; echo "$CUR $1 start=$(ems)" >> "$PH"; log "phase $1"; }

make_conf() {   # make_conf key=value ...
  rm -rf "$N/conf"; mkdir -p "$N/data" "$N/commitlog" "$N/hints" "$N/saved_caches" "$N/cdc_raw"
  cp -R "$C/conf" "$N/conf"
  git -C "$C" show HEAD:conf/cassandra.yaml > "$N/shipped.yaml"
  { echo "cluster_name: sep"; echo "num_tokens: 16"
    echo "listen_address: 127.0.0.1"; echo "rpc_address: 127.0.0.1"
    echo "data_file_directories:"; echo "    - $N/data"
    echo "commitlog_directory: $N/commitlog"; echo "hints_directory: $N/hints"; echo "saved_caches_directory: $N/saved_caches"
    echo "cdc_raw_directory: $N/cdc_raw"
    echo "read_request_timeout: 300000ms"; echo "range_request_timeout: 300000ms"; echo "native_transport_timeout: 300s"
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
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 sep lines ----\n' + '\n'.join(add) + '\n')
PY
  say "YAML $CUR $(sed -n '/^# ---- stage4 sep lines/,$p' $N/conf/cassandra.yaml | grep -v '^#' | grep -v '^    - ' | grep -v directory | tr '\n' ';')"
}
start_node() {  # start_node <label> <extra jvm opts>
  CUR=$1; D=$L/$1; mkdir -p "$D/samples"; echo starting > "$D/phase"
  local x="-XX:NativeMemoryTracking=summary -Dcassandra.set_sep_thread_name=false $2"
  log "+ start node $1 (conf $N/conf, logs $D) JVM_EXTRA_OPTS=$x"
  CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$D MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M JVM_EXTRA_OPTS="$x" \
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
# B3d sampler: Sampler.java (runbook fixes 2026-10-26, defects 2 and 3) -- one persistent JMX connection: tpstats gauges every
# 1 s (tpjmx.log); Thread.print and VM.native_memory summary through the DiagnosticCommand MBean every 5 s (samples/).
start_sampler() { rm -f "$D/stop"; java -cp "$HB" Sampler "$D" "$PID" > "$D/sampler.err" 2>&1 & SPID=$!; log "sampler pid $SPID"; }
stop_sampler() { [ -n "$SPID" ] && { touch "$D/stop"; wait $SPID 2>/dev/null; SPID=""; log "sampler stopped"; }; }
readback() {  # readback <tag>
  jmx get $NTRB MaximumPoolSize $NTRB CorePoolSize $NTRG Value > "$D/readback-$1.txt"
  say "READBACK $CUR $1 $(sed 's/^org.apache.cassandra.//' "$D/readback-$1.txt" | tr '\n' ';')"
}
flags() {
  tmo 60 jcmd $PID VM.flags > "$D/vmflags.txt" 2>&1
  say "FLAGS $CUR $(tr ' ' '\n' < "$D/vmflags.txt" | grep -E 'ThreadStackSize|NativeMemoryTracking|MaxHeapSize|AlwaysPreTouch' | tr '\n' ' ') xss_on_cmdline=[$(ps -o command= -p $PID | tr ' ' '\n' | grep -E '^-Xss' | tr '\n' ' ')] set_sep_thread_name_false=$(ps -o command= -p $PID | grep -c 'set_sep_thread_name=false')"
}
idle() {  # idle <name> <secs>
  phase "$1"; sleep "$2"; echo "$CUR $1 end=$(ems)" >> "$PH"
}
load() {  # load <name> <nproc> <perproc> <secs>
  local out=$D/$1
  phase "$1"
  log "+ loadclient run $2 $3 $4 $out"
  tmo 900 python3 "$H/loadclient.py" "$DRV" run "$2" "$3" "$4" "$out" > "$D/client-$1.out" 2>&1
  local rc=$?; log "  client exit=$rc"
  echo "$CUR $1 end=$(ems) client_t_start=$(python3 -c "import json;print(json.load(open('$out/phase.json'))['t_start'])") client_t_end=$(python3 -c "import json;print(json.load(open('$out/phase.json'))['t_end'])")" >> "$PH"
  say "CLIENT $CUR $1 rc=$rc $(grep '^RUN ' "$D/client-$1.out" | tail -1)"
  drain "drain-$1"
}
drain() {  # drain <name>: until NTR and ReadStage Active = Pending = 0 twice in a row, at most 600 s
  phase "$1"; local t0 ok=0; t0=$(date +%s)
  while :; do
    local tp; tp=$(nt tpstats 2>/dev/null)
    local z; z=$(echo "$tp" | awk '($1=="Native-Transport-Requests"||$1=="ReadStage") && $2==0 && $3==0 {n++} END{print n+0}')
    if [ "$z" = 2 ]; then ok=$((ok+1)); else ok=0; fi
    [ $ok -ge 2 ] && break
    [ $(( $(date +%s) - t0 )) -ge 600 ] && { say "DRAIN $CUR $1 not idle after 600 s"; break; }
    sleep 5
  done
  echo "$CUR $1 end=$(ems) secs=$(( $(date +%s) - t0 ))" >> "$PH"
  say "DRAIN $CUR $1 secs=$(( $(date +%s) - t0 ))"
}
stop_node() {
  stop_sampler
  [ -z "$PID" ] && return 0
  if kill -0 $PID 2>/dev/null; then
    run nt drain
    kill $PID 2>/dev/null; for i in $(seq 1 90); do kill -0 $PID 2>/dev/null || break; sleep 1; done
    kill -0 $PID 2>/dev/null && { log "kill -9 $PID"; kill -9 $PID; sleep 1; }
  fi
  PID=""; log "node stopped"
}
end_start() {
  say "LOG $CUR errors=$(grep -c '^ERROR' "$D/system.log" 2>/dev/null) warn=$(grep -c '^WARN' "$D/system.log" 2>/dev/null) resized=[$(grep -h -o 'Resized .*maximum pool size from [0-9]* to [0-9]*' "$D/system.log" 2>/dev/null | tr '\n' ';')] samples=$(( $(wc -l < "$D/samples.csv") - 1 ))"
  python3 "$H/summarize.py" "$D" >> "$S" 2>> "$CL"
}
final_check() {
  local d s; d=$(ps -eo command | grep '[C]assandraDaemon'); s=$(ps -eo command | grep '[s]tress.Stress')
  say "final Cassandra processes: ${d:-none}; stress processes: ${s:-none}"
  rm -rf "$N"; say "node-sep wiped: $([ -e "$N" ] && echo no || echo yes)"
}
die() { say "ABORT: $*"; stop_node; final_check; exit 1; }
trap 'die "interrupted"' INT TERM

up() {  # up <label> <extra jvm opts> key=value...
  local lab=$1 x=$2; shift 2
  say "== $lab start $(now)"
  CUR=$lab; D=$L/$lab; mkdir -p "$D"; make_conf "$@"
  start_node "$lab" "$x"; wait_up || die "$lab: node did not start"
  say "STARTUP $CUR up_secs=$(( $(date +%s) - T0 )) pid=$PID"
  flags
  start_sampler
  readback start
}
populate() {
  up populate ""
  log "+ (cd $W && tools/bin/cassandra-stress write n=$1 no-warmup -rate threads=64 -schema 'replication(factor=1)' -node 127.0.0.1)"
  ( cd "$W" && tmo 1800 "$C/tools/bin/cassandra-stress" write "n=$1" no-warmup -rate threads=64 -schema 'replication(factor=1)' -node 127.0.0.1 ) > "$D/stress.log" 2>&1
  local rc=$?; log "  stress exit=$rc"
  say "STRESS rc=$rc $(grep -E 'Total partitions|Total errors|Op rate' "$D/stress.log" | head -3 | tr -s ' ' | tr '\n' ';')"
  [ $rc = 0 ] || die "stress failed"
  run nt flush keyspace1; run nt compact keyspace1
  tmo 600 python3 "$H/loadclient.py" "$DRV" count > "$D/count.out" 2>&1; say "ROWS $(cat "$D/count.out" | tail -1)"
  nt tablestats keyspace1.standard1 > "$D/tablestats.txt" 2>&1
  say "TABLE $(grep -E 'SSTable count|Space used \(live\)' "$D/tablestats.txt" | tr -s ' ' | tr '\n' ';')"
  stop_node; end_start
}
knob() {  # knob <label> <knob> <xss-opts> <idle> <c8secs> <c400secs> <shrink 0|1> <pidle> <pc400>
  local lab=$1 k=$2 x=$3 idl=$4 c8=$5 c4=$6 sh=$7 pidl=$8 pc4=$9
  up "$lab" "$x" native_transport_max_threads=$k
  idle idle "$idl"
  [ "$c8" -gt 0 ] && load C8 1 8 "$c8"
  load C400 4 100 "$c4"
  if [ "$sh" = 1 ]; then
    phase shrink
    jmx set $NTRB MaximumPoolSize int:16 > "$D/shrink-set.txt"; say "SHRINK $CUR t=$(ems) $(cat "$D/shrink-set.txt" | tr '\n' ';')"
    readback after-shrink
    idle postshrink-idle "$pidl"
    load postshrink-C400 4 100 "$pc4"
    readback end
  fi
  stop_node; end_start
  say "== $lab end $(now)"
}

say "cluster-run $RUN plan $PLAN start $(now); runner sha256 $(shasum -a 256 "$0" | cut -c1-16); clone $C; node $N; driver $DRV"
say "harness sha256: $(cd "$H" && shasum -a 256 loadclient.py Jmx.java Sampler.java summarize.py | awk '{print $2"="substr($1,1,16)}' | tr '\n' ' ')"
say "clone $(git -C $C describe --tags) $(git -C $C rev-parse --short HEAD)"
d=$(ps -eo command | grep '[C]assandraDaemon'); [ -n "$d" ] && { say "ABORT: a Cassandra node is running"; exit 1; }
for p in 7000 7199 9042 9091; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { say "ABORT: port $p busy"; exit 1; }; done
fg=$(df -g $W | tail -1 | awk '{print $4}'); [ "$fg" -ge 20 ] || { say "ABORT: only $fg GiB free"; exit 1; }
say "pre-checks: no Cassandra node; ports 7000 7199 9042 9091 free; free disk ${fg} GiB; loopback $(ifconfig lo0 | grep -c 'inet 127.0.0.') addresses; ulimit -n $(ulimit -n); somaxconn $(sysctl -n kern.ipc.somaxconn)"
rm -rf "$HB" && mkdir -p "$HB" && javac -d "$HB" "$H/Jmx.java" "$H/Sampler.java" || { say "ABORT: Jmx compile failed"; exit 1; }
rm -rf "$N"

case $PLAN in
  timing)
    populate 200000
    knob k16 16 "" 10 0 90 0 0 0
    ;;
  probe)   # 2026-10-28, before the re-run's amendment: diagnostic start with the observe-only rules of sep-worker-origin.btm
    populate 200000
    BT="-javaagent:$C/build/lib/jars/byteman-4.0.20.jar=script:$H/sep-worker-origin.btm"
    up kp "$BT" native_transport_max_threads=16
    idle idle "${PROBE_IDLE:-90}"
    stop_node; end_start
    cp "$L/kp/node.out" "$L/kp-node.out.copy" 2>/dev/null
    ;;
  shake)
    populate 200000
    knob k256 256 "" 10 20 40 1 10 20
    knob k16 16 "" 10 0 40 0 0 0
    ;;
  run1)
    populate 200000
    knob k16 16 "" 30 180 180 0 0 0
    knob k64 64 "" 30 180 180 0 0 0
    knob k128 128 "" 30 180 180 0 0 0
    knob k256 256 "" 30 180 180 1 60 60
    knob X 256 "-Xss1m" 30 0 180 0 0 0
    python3 "$H/summarize.py" --cross "$L" >> "$S" 2>> "$CL"
    ;;
  *) say "unknown plan $PLAN"; exit 2;;
esac
final_check
say "cluster-run $RUN end $(now)"
