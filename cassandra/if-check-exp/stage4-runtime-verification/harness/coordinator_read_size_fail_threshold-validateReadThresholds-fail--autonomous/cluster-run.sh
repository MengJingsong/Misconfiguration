#!/usr/bin/env bash
# Cluster tier (B3, as amended 2026-10-25) of coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous.
# Adapted from harness/max_value_size-applySimpleConfig-max_value_size--autonomous/cluster-run.sh (copied, then changed:
# arms, jvm options copy, Byteman rules, sampler, JMX read-backs, multi-process read client, GC baseline).
# usage: cluster-run.sh <outdir-name> <plan>
#   plan run1: load, N, C (coordinator 1MiB), L (local 1MiB), L4 (local 4MiB), Z (start-up refusal)
#   plan sd:   shakedown (harness check, not a reading): 2 partitions x 256 rows; sdN, sdL (local 2MiB), sdC (coordinator 2MiB);
#              P=128, 4 clients, 20 s, idle 10 s
# One node, 127.0.0.1, clone $W/cassandra-run22, node directories under $W/node-vrt (Z: $W/node-vrt-z).
# Logs: $W/logs/coordinator_read_size_fail_threshold-validateReadThresholds/cluster-<outdir>/
# Changed 2026-10-28 for the cluster re-run (harness change H2, results §3): clone, node directory and helper directory may be given as
# C=..., VRT_NODE=..., VRT_HB=... (defaults: run 1's); InFlight.java is compiled into the boot-class-path helper jar (vrt.btm's inflight rules).
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
H=$(cd "$(dirname "$0")" && pwd)
RUN=${1:?outdir}; PLAN=${2:?plan}
L=$W/logs/coordinator_read_size_fail_threshold-validateReadThresholds/cluster-$RUN
[ -e "$L" ] && mv "$L" "$L.attempt-$(date +%s)"
mkdir -p "$L"; CL=$L/commands.log; S=$L/summary.txt; PH=$L/phases.txt; : > "$CL"; : > "$S"; : > "$PH"
C=${C:-$W/cassandra-run22}; N=${VRT_NODE:-$W/node-vrt}; PID=""; CUR=""; SPID=""
BM=$C/build/lib/jars; HB=${VRT_HB:-$W/harness-bin-vrt}
DRV=$(ls "$C"/lib/cassandra-driver-internal-only-*.zip | head -1)
SSB='org.apache.cassandra.db:type=StorageService'
TB='org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=t,name='
now() { date '+%Y-%m-%dT%H:%M:%S%z'; }
ems() { python3 -c 'import time; print(int(time.time()*1000))'; }
log() { echo "[$(now)] $*" >> "$CL"; }
say() { echo "$*" >> "$S"; log "SUMMARY $*"; }
tmo() { perl -e '$t=shift; $p=fork; if(!$p){exec @ARGV; exit 127} $SIG{ALRM}=sub{kill 9,$p; waitpid $p,0; exit 124}; alarm $t; waitpid $p,0; exit($?>>8)' "$@"; }
nt()  { tmo 300 "$C/bin/nodetool" -h 127.0.0.1 -p 7199 "$@"; }
run() { log "+ $*"; "$@" >> "$CL" 2>&1; local rc=$?; log "  exit=$rc"; return $rc; }
cli() { log "+ vrtclient $*"; tmo 900 python3 "$H/vrtclient.py" "$DRV" "$@" > "$L/cli.tmp" 2>&1; local rc=$?; cat "$L/cli.tmp" >> "$CL"; log "  exit=$rc"; say "CLIENT $CUR $1 rc=$rc $(grep -E '^(SETTINGS|SCHEMA|LOAD|READ) ' "$L/cli.tmp" | tail -1 | cut -c1-900)"; return $rc; }
jmx() { tmo 60 java -cp "$HB" Jmx "$@" 2>&1; }

make_conf() {   # make_conf key=value ...   (a value NONE removes the key)
  rm -rf "$N/conf"; mkdir -p "$N/data" "$N/commitlog" "$N/hints" "$N/saved_caches" "$N/cdc_raw"
  cp -R "$C/conf" "$N/conf"
  git -C "$C" show HEAD:conf/cassandra.yaml > "$N/shipped.yaml"
  { echo "cluster_name: stage4-vrt"; echo "num_tokens: 1"; echo "initial_token: 0"; echo "auto_bootstrap: false"
    echo "listen_address: 127.0.0.1"; echo "rpc_address: 127.0.0.1"
    echo "data_file_directories:"; echo "    - $N/data"
    echo "commitlog_directory: $N/commitlog"; echo "hints_directory: $N/hints"; echo "saved_caches_directory: $N/saved_caches"
    echo "cdc_raw_directory: $N/cdc_raw"
    echo "read_thresholds_enabled: true"; echo "concurrent_reads: 32"
    echo "read_request_timeout: 20000ms"; echo "write_request_timeout: 20000ms"
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
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 vrt lines ----\n' + '\n'.join(add) + '\n')
PY
}
jvm_conf() {  # jvm_conf <gc log path>: 2 MiB regions, our own GC log (B3a amendment)
  local f=$N/conf/jvm11-server.options
  sed -i '' 's/^-XX:G1HeapRegionSize=16m$/-XX:G1HeapRegionSize=2m/' "$f"
  echo "-Xlog:gc*:file=$1:time,uptimemillis,tags" >> "$f"
  say "JVMOPTS $CUR $(grep -E '^-XX:G1HeapRegionSize|^-Xlog|^-XX:\+UseG1GC' "$f" | tr '\n' ' ')"
}
yaml_line() { say "YAML $1 $(sed -n '/^# ---- stage4 vrt lines/,$p' $N/conf/cassandra.yaml | grep -v '^#' | grep -v '^    - ' | grep -v directory | tr '\n' ';')"; }
start_node() {  # start_node <label>
  CUR=$1; local D=$L/$1; mkdir -p "$D"
  jvm_conf "$D/gc.log"
  log "+ start node $1 (conf $N/conf, logs $D, trace $D/vrt.trace)"
  CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$D MAX_HEAP_SIZE=4G \
    JVM_EXTRA_OPTS="-Xbootclasspath/a:$HB/stage4-helpers.jar -javaagent:$BM/byteman-4.0.20.jar=script:$H/vrt.btm,listener:true -Dstage4.byteman.out=$D/vrt.trace" \
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
start_sampler() { rm -f "$L/$CUR/stop"; java -cp "$HB" Sampler 7199 "$L/$CUR/samples.csv" "$L/$CUR/stop" > "$L/$CUR/sampler.err" 2>&1 & SPID=$!; log "sampler pid $SPID"; }
stop_sampler() { [ -n "$SPID" ] && { touch "$L/$CUR/stop"; sleep 2; kill $SPID 2>/dev/null; SPID=""; }; }
readback() {   # settings + JMX read-backs of the current start
  cli settings "$L/$CUR/settings.json"
  jmx get $SSB ReadThresholdsEnabled $SSB CoordinatorLargeReadAbortThreshold $SSB CoordinatorLargeReadWarnThreshold \
      $SSB LocalReadTooLargeAbortThreshold $SSB LocalReadTooLargeWarnThreshold $SSB RowIndexReadSizeAbortThreshold > "$L/$CUR/jmx-readback.txt"
  say "JMX-READBACK $CUR $(sed 's/^org.apache.cassandra.db:type=StorageService|//' "$L/$CUR/jmx-readback.txt" | tr '\n' ';')"
  say "PROCESS $CUR byteman_agent=$(ps -o command= -p $PID | grep -c 'byteman-4.0.20.jar') region2m=$(ps -o command= -p $PID | grep -c 'G1HeapRegionSize=2m') xmx4g=$(ps -o command= -p $PID | grep -c 'Xmx4G')"
}
meters() {  # meters <tag>
  jmx get ${TB}CoordinatorReadSizeAborts Count ${TB}LocalReadSizeAborts Count ${TB}CoordinatorReadSize Max ${TB}LocalReadSize Max > "$L/$CUR/meters-$1.txt"
  say "METERS $CUR $1 ms=$(ems) $(sed "s/^org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=t,name=//" "$L/$CUR/meters-$1.txt" | tr '\n' ';')"
}
idle_baseline() {  # idle_baseline <secs>
  local t0; t0=$(ems); log "idle $1 s"; sleep "$1"
  local tg; tg=$(ems)
  run tmo 120 jcmd $PID GC.run
  echo "$CUR idle t_start=$t0 t_gc=$tg t_end=$(ems)" >> "$PH"
}
read_phase() {  # read_phase <P> <secs> <nproc> [npk]
  local P=$1 out=$L/$CUR/read-P$1
  meters before-P$P
  cli read "$P" "$2" "$3" "$out" "${4:-8}"
  meters after-P$P
  echo "$CUR read P=$P $(python3 -c "import json;d=json.load(open('$out/phase.json'));print('t_start=%d t_end=%d returned=%d'%(d['t_start'],d['t_end'],d['returned']))")" >> "$PH"
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
  local D=$L/$CUR
  say "LOG $CUR errors=$(grep -c '^ERROR' "$D/system.log" 2>/dev/null) warn_coord_fail=$(grep -c 'exceeded the size failure threshold' "$D/system.log" 2>/dev/null) gc_pauses=$(grep -c 'Pause Young' "$D/gc.log" 2>/dev/null) trace_lines=$(wc -l < "$D/vrt.trace" 2>/dev/null | tr -d ' ')"
  python3 "$H/summarize.py" "$L" "$CUR" >> "$S" 2>> "$CL"
}
final_check() {
  local d; d=$(ps -eo command | grep '[C]assandraDaemon'); say "final CassandraDaemon processes: ${d:-none}"
  rm -rf "$N" "$N-z"; say "node-vrt wiped: $([ -e "$N" ] && echo no || echo yes)"
}
die() { say "ABORT: $*"; stop_node; final_check; exit 1; }
trap 'die "interrupted"' INT TERM

up() {  # up <label> key=value...
  local lab=$1; shift
  say "== $lab start $(now)"
  CUR=$lab; make_conf "$@"; yaml_line $lab
  start_node $lab; wait_up || die "$lab: node did not start"
  say "STARTUP $CUR up_secs=$(( $(date +%s) - T0 )) startup_complete=$(grep -c 'Startup complete' "$L/$CUR/system.log") replay=[$(grep -h -o 'Log replay complete.*\|No commitlog files found.*' "$L/$CUR/system.log" "$L/$CUR/debug.log" 2>/dev/null | head -2 | tr '\n' ';')]"
  start_sampler
  readback
}
arm() {  # arm <label> <idle> <secs> <nproc> <P...> -- key=value...
  local lab=$1 idle=$2 secs=$3 np=$4; shift 4
  local Ps=(); while [ "$1" != "--" ]; do Ps+=("$1"); shift; done; shift
  up $lab "$@"
  idle_baseline "$idle"
  local first=1
  for P in "${Ps[@]}"; do
    [ $first = 0 ] && { log "between phases: idle $idle s"; sleep "$idle"; }
    first=0
    read_phase "$P" "$secs" "$np" "$NPK"
  done
  stop_node; end_start
  say "== $lab end $(now)"
}

say "cluster-run $RUN plan $PLAN start $(now); runner sha256 $(shasum -a 256 "$0" | cut -c1-16); clone $C; node $N; driver $DRV"
say "harness sha256: $(cd "$H" && shasum -a 256 vrtclient.py vrt.btm Alloc.java InFlight.java Jmx.java Sampler.java summarize.py | awk '{print $2"="substr($1,1,16)}' | tr '\n' ' ')"
say "clone $(git -C $C describe --tags) $(git -C $C rev-parse --short HEAD)"
d=$(ps -eo command | grep '[C]assandraDaemon'); [ -n "$d" ] && { say "ABORT: a Cassandra node is running"; exit 1; }
for p in 7000 7199 9042 9091; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { say "ABORT: port $p busy"; exit 1; }; done
fg=$(df -g $W | tail -1 | awk '{print $4}'); [ "$fg" -ge 20 ] || { say "ABORT: only $fg GiB free"; exit 1; }
say "pre-checks: no Cassandra node; ports 7000 7199 9042 9091 free; free disk ${fg} GiB; loopback $(ifconfig lo0 | grep -c 'inet 127.0.0.') addresses"
rm -rf "$HB" && mkdir -p "$HB/helper" && javac -d "$HB/helper" "$H/Alloc.java" "$H/InFlight.java" && jar cf "$HB/stage4-helpers.jar" -C "$HB/helper" . \
  && javac -d "$HB" "$H/Jmx.java" "$H/Sampler.java" || { say "ABORT: helper compile failed"; exit 1; }
java -classpath "$BM/byteman-4.0.20.jar:$HB/stage4-helpers.jar:$C/build/classes/main:$C/build/lib/jars/*:$C/lib/*" org.jboss.byteman.check.TestScript "$H/vrt.btm" > "$L/testscript.txt" 2>&1
say "TESTSCRIPT $(grep -E 'TestScript:|ERROR' "$L/testscript.txt" | tr '\n' ';' | cut -c1-400)"
grep -q 'TestScript: no errors' "$L/testscript.txt" || { say "ABORT: Byteman TestScript errors"; exit 1; }

case $PLAN in
  sd)
    NPK=2
    rm -rf "$N"; up sdload
    cli schema || die "schema"; cli load 2 256 || die "load"
    run nt flush ks t; stop_node; end_start
    arm sdN 10 20 4 128 --
    arm sdL 10 20 4 128 -- local_read_size_fail_threshold=2MiB
    arm sdC 10 20 4 128 -- coordinator_read_size_fail_threshold=2MiB
    java -cp "$BM/byteman-submit-4.0.20.jar" org.jboss.byteman.agent.submit.Submit -l > "$L/submit-l.txt" 2>&1
    ;;
  run1)
    NPK=8
    rm -rf "$N"; up load
    cli schema || die "schema"; cli load 8 1024 || die "load"
    run nt flush ks t; run nt compactionstats
    ls -l "$N"/data/ks/t-*/ > "$L/load/listing.txt" 2>&1
    say "DATA load $(awk '/Data.db/{s+=$5; n++} END{print n" Data.db files, "s" bytes"}' "$L/load/listing.txt")"
    stop_node; end_start
    arm N 60 180 16 128 512 --
    arm C 60 180 16 128 512 -- coordinator_read_size_fail_threshold=1MiB
    arm L 60 180 16 128 512 -- local_read_size_fail_threshold=1MiB
    arm L4 60 180 16 128 512 -- local_read_size_fail_threshold=4MiB
    # Z: start-up refusal on an empty, separate directory (B3b/B3f)
    CUR=Z; ND=$N; N=$ND-z; rm -rf "$N"; mkdir -p "$L/Z"
    say "== Z start $(now)"
    make_conf coordinator_read_size_warn_threshold=2MiB coordinator_read_size_fail_threshold=1MiB; yaml_line Z
    jvm_conf "$L/Z/gc.log"
    t0=$(date +%s)
    CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$L/Z MAX_HEAP_SIZE=4G tmo 120 "$C/bin/cassandra" -f > "$L/Z/node.out" 2>&1 < /dev/null
    rc=$?
    say "REFUSAL Z rc=$rc secs=$(( $(date +%s) - t0 )) startup_complete=$(cat "$L/Z/node.out" "$L/Z/system.log" 2>/dev/null | grep -c 'Startup complete')"
    say "REFUSAL-LINES Z $(grep -h 'must be greater than or equal to' "$L/Z/node.out" "$L/Z/system.log" 2>/dev/null | cut -c1-260 | sort | uniq -c | tr -s ' ' | tr '\n' ';')"
    sleep 2; d=$(ps -eo command | grep '[C]assandraDaemon'); [ -n "$d" ] && die "Z: a Cassandra node is still running"
    rm -rf "$N"; N=$ND
    ;;
  *) say "unknown plan $PLAN" ;;
esac
stop_node; final_check
say "cluster-run $RUN end $(now)"
