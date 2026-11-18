#!/usr/bin/env bash
# U2 stage 2 (2026-11-17): one run of the frozen design (case §2.5 item 1). Runs on pc84 from an ssh session kept open.
# usage: run.sh <run-id> <cond A|B|M> <mode partial|complete> <k> <hold_s> <yaml_extra or -> <btm on|off>
#   cond A: automatic budget (MAX_HEAP_SIZE / MAX_DIRECT_MEMORY_SIZE unset); B: 4096M / 2048M; M: 16384M / 8192M (optional run).
#   yaml_extra: one "key: value" line appended to the node's cassandra.yaml (intervention arm only), "-" for none.
# Derived from the stage-4 recheck harness (capacity-enforcement-exp/cassandra/stage4-runtime-verification/harness/
# native_transport_max_frame_size-decode-bytesToDiscard--autonomous--recheck-2026-11-17/run.sh).
set -uo pipefail
RID=$1; COND=$2; MODE=$3; K=$4; HOLD=$5; YX=$6; BTM=$7
LEN=16777207; RATE=10
H=$(cd "$(dirname "$0")" && pwd); C=${C:-/mydata/s4/u2-w1}
LG=$C/logs/$RID; mkdir -p "$LG"; rm -rf "${LG:?}"/*
export CASSANDRA_HOME=$C
log() { echo "[$(date '+%F %T') $(date +%s%3N)] $*" | tee -a "$LG/commands.log"; }
NT() { timeout 10 "$C/bin/nodetool" -h 127.0.0.1 -p 7199 "$@"; }
PID=""; JP=""; CP=""; PP=""; SP=""; NP=""; MP=""; D=""; CG=""
ndaemons() { ps -eo cmd | grep -c '[C]assandraDaemon'; }
alive() { [ -n "$JP" ] && kill -0 "$JP" 2>/dev/null; }
stop_bg() { local p; for p in $CP $PP $SP $NP $MP; do kill "$p" 2>/dev/null; done; CP=""; PP=""; SP=""; NP=""; MP=""; return 0; }
stop_node() {
  [ -z "$PID" ] && return 0
  if alive; then
    NT stopdaemon >> "$LG/commands.log" 2>&1
    local k; for k in $(seq 1 60); do alive || break; sleep 1; done
    if alive; then kill "$JP" 2>/dev/null; sleep 5; kill -9 "$JP" 2>/dev/null; log "node pid $JP killed after 60 s"; fi
  fi
  wait "$PID" 2>/dev/null; log "launcher wait rc=$? (stop_node)"
  PID=""
}
cleanup() { stop_bg; stop_node; }
trap cleanup EXIT

case $COND in
  A) BUDGET_ENV="env -u MAX_HEAP_SIZE -u MAX_DIRECT_MEMORY_SIZE" ;;
  B) BUDGET_ENV="env MAX_HEAP_SIZE=4096M MAX_DIRECT_MEMORY_SIZE=2048M" ;;
  M) BUDGET_ENV="env MAX_HEAP_SIZE=16384M MAX_DIRECT_MEMORY_SIZE=8192M" ;;
  *) echo "bad cond"; exit 2 ;;
esac
log "run $RID cond=$COND mode=$MODE k=$K hold=$HOLD yaml_extra=[$YX] btm=$BTM L=$LEN rate=$RATE C=$C host=$(hostname -s) TZ_NY=$(TZ=America/New_York date '+%F %T')"
log "sha256: run.sh $(sha256sum "$0" | cut -c1-16) client $(sha256sum "$H/stall_client.py" | cut -c1-16) probe $(sha256sum "$H/service_probe.py" | cut -c1-16) btm $(sha256sum "$H/ntfr.btm" | cut -c1-16) Probe.java $(sha256sum "$H/probe/ntfr/Probe.java" | cut -c1-16)"
log "$(uname -r); $(java -version 2>&1 | head -1); $(python3 --version 2>&1); $(nproc) cores; $(free -g | awk '/Mem:/{print $2" GiB RAM"}'); swap $(swapon --show=SIZE --noheadings | tr '\n' ' ')"
[ "$(ndaemons)" = 0 ] || { log "ABORT: a Cassandra daemon is already running"; exit 1; }
for p in 7000 7199 9042; do ss -ltnH "sport = :$p" | grep -q . && { log "ABORT: port $p busy"; exit 1; }; done
J=$C/build/lib/jars; PJ=$C/ntfr-probe
EXTRA=""
if [ "$BTM" = on ]; then
  if [ ! -f "$PJ/ntfr-probe.jar" ]; then
    rm -rf "$PJ"; mkdir -p "$PJ/classes"
    javac -cp "$J/netty-buffer-4.1.130.Final.jar:$J/netty-common-4.1.130.Final.jar" -d "$PJ/classes" "$H/probe/ntfr/Probe.java" > "$LG/probe-javac.txt" 2>&1 \
      && jar cf "$PJ/ntfr-probe.jar" -C "$PJ/classes" . || { log "ABORT: probe helper did not compile"; exit 1; }
  fi
  java -cp "$J/byteman-4.0.20.jar:$C/build/classes/main:$J/*:$PJ/ntfr-probe.jar" org.jboss.byteman.check.TestScript "$H/ntfr.btm" > "$LG/btm-check.txt" 2>&1
  grep -q 'TestScript: no errors' "$LG/btm-check.txt" || { log "ABORT: Byteman rule check failed"; exit 1; }
  log "rules type-checked: $(grep 'TestScript:' "$LG/btm-check.txt" | tail -1)"
  EXTRA="-XX:NativeMemoryTracking=summary -javaagent:$J/byteman-4.0.20.jar=script:$H/ntfr.btm,sys:$PJ/ntfr-probe.jar"
fi

# --- make node ---
D=$C/node-$RID; rm -rf "$D"; mkdir -p "$D"/data "$D"/commitlog "$D"/hints "$D"/saved_caches "$D"/cdc_raw "$D"/logs
cp -R "$C/conf" "$D/conf"; Y=$D/conf/cassandra.yaml
grep -v -E '^(listen_address|rpc_address|hints_directory|commitlog_directory|saved_caches_directory|cdc_raw_directory):' "$C/conf/cassandra.yaml" > "$Y"
cat >> "$Y" <<YAML
# --- U2 stage-2 overrides (addresses and directories only) ---
listen_address: 127.0.0.1
rpc_address: 127.0.0.1
data_file_directories:
    - $D/data
commitlog_directory: $D/commitlog
hints_directory: $D/hints
saved_caches_directory: $D/saved_caches
cdc_raw_directory: $D/cdc_raw
YAML
if [ "$YX" != "-" ]; then echo "# --- intervention arm ---" >> "$Y"; echo "$YX" >> "$Y"; fi
diff "$C/conf/cassandra.yaml" "$Y" > "$LG/yaml.diff"

# --- start node ---
UNIT="u2-w1-$RID-$(date +%s)"
( cd "$C" && ulimit -n 100000 && exec $BUDGET_ENV CASSANDRA_CONF=$D/conf CASSANDRA_LOG_DIR=$D/logs JVM_EXTRA_OPTS="$EXTRA" \
    systemd-run --user --scope --unit="$UNIT" -p MemoryMax=64G -p MemorySwapMax=0 bin/cassandra -f > "$D/node-stdout.log" 2>&1 < /dev/null ) &
PID=$!
T_START=$(date +%s)
log "started scope $UNIT, launcher pid=$PID"
up=0
for k in $(seq 1 240); do
  [ -z "$JP" ] && JP=$(pgrep -f "cassandra.logdir=$D/logs" | head -1)
  kill -0 "$PID" 2>/dev/null || { log "node died during start"; break; }
  if grep -q 'Starting listening for CQL clients' "$D/logs/system.log" 2>/dev/null && [ "$(NT statusbinary 2>/dev/null)" = "running" ]; then
    log "node: binary running after ~$(( $(date +%s) - T_START )) s"; up=1; break; fi
  sleep 2
done
[ "$up" = 1 ] || { log "INVALID: node did not start"; tail -40 "$D/node-stdout.log" >> "$LG/commands.log"; exit 1; }
JP=$(pgrep -f "cassandra.logdir=$D/logs" | head -1)
log "java pid=$JP launcher pid=$PID (same: $([ "$JP" = "$PID" ] && echo yes || echo no))"
CG=/sys/fs/cgroup$(cut -d: -f3 /proc/$JP/cgroup)
log "cgroup=$CG memory.max=$(cat $CG/memory.max) memory.swap.max=$(cat $CG/memory.swap.max) nofile=$(awk '/Max open files/{print $4}' /proc/$JP/limits)"
R=$LG
grep -o 'Node configuration:\[.*' "$D/logs/system.log" | head -1 | tr ';' '\n' | sed 's/^ //' | grep -E '^(native_transport_(max_frame_size|max_concurrent_connections|max_concurrent_connections_per_ip|idle_timeout|max_request_data_in_flight|max_request_data_in_flight_per_ip|receive_queue_capacity)|client_error_reporting_exclusions|authenticator)=' > "$R/config.txt"
jcmd "$JP" VM.flags 2>/dev/null | tr ' ' '\n' | grep -E 'MaxDirectMemorySize|MaxHeapSize|InitialHeapSize|NativeMemoryTracking|UseG1GC|AlwaysPreTouch|HeapDumpOnOutOfMemoryError|HeapDumpPath|OnOutOfMemoryError' >> "$R/config.txt"
echo "scope_memory.max=$(cat $CG/memory.max)" >> "$R/config.txt"; echo "scope_memory.swap.max=$(cat $CG/memory.swap.max)" >> "$R/config.txt"
tr '\0' '\n' < /proc/$JP/cmdline | grep -E 'MaxDirectMemorySize|Xmx|Xms|OnOutOfMemoryError|HeapDump|javaagent|NativeMemoryTracking|UseG1GC|PreTouch|io.netty' > "$R/jvm-args.txt"
log "config: $(tr '\n' ' ' < "$R/config.txt")"
log "jvm-args: $(tr '\n' ' ' < "$R/jvm-args.txt")"

# --- samplers ---
( echo -e "t_ms\talive\tmemory_current\tev_max\tev_oom_kill\trss_anon_kib\testab_9042"
  while true; do
    a=0; kill -0 "$JP" 2>/dev/null && a=1
    mc=$(cat "$CG/memory.current" 2>/dev/null || echo NA); em=$(awk '$1=="max"{print $2}' "$CG/memory.events" 2>/dev/null); eo=$(awk '$1=="oom_kill"{print $2}' "$CG/memory.events" 2>/dev/null)
    ra=$(awk '/RssAnon/{print $2}' /proc/$JP/status 2>/dev/null); es=$(ss -tnH state established '( sport = :9042 )' 2>/dev/null | wc -l)
    echo -e "$(date +%s%3N)\t$a\t$mc\t${em:-NA}\t${eo:-NA}\t${ra:-NA}\t$es"
    sleep 2
  done ) > "$R/samples.tsv" 2>/dev/null &
SP=$!
if [ "$BTM" = on ]; then
  jcmd "$JP" VM.native_memory baseline > "$R/nmt-base.txt" 2>&1
  ( while true; do t=$(date +%s%3N); NT version > /dev/null 2>&1 || echo "nt-fail $t"; sleep 5; done ) > "$R/nt-fail.txt" 2>&1 &
  NP=$!
  ( echo -e "t_ms\tnmt_other_committed_delta_kib"
    while true; do t=$(date +%s%3N); o=$(timeout 15 jcmd "$JP" VM.native_memory summary.diff 2>/dev/null | grep -E '^-? *Other \(' | head -1 | sed -n 's/.*committed=[0-9]*KB \([+-][0-9]*\)KB.*/\1/p'); echo -e "$t\t${o:-NA}"; sleep 10; done ) > "$R/nmt.tsv" 2>&1 &
  MP=$!
fi
log "samplers started (sampler=$SP nodetool=$NP nmt=$MP); idle 30 s"
sleep 30
log "base: $(tail -1 "$R/samples.tsv")"
python3 "$H/service_probe.py" 127.0.0.1 9042 > "$R/probe.out" 2>&1 &
PP=$!
sleep 20
log "P0: $(tail -1 "$R/samples.tsv"); probe P ok=$(grep -c '^P .* ok ' "$R/probe.out") N ok=$(grep -c '^N .* ok ' "$R/probe.out") err=$(grep -c ' err ' "$R/probe.out")"
( ulimit -n 100000; exec python3 "$H/stall_client.py" "$MODE" 127.0.0.1 9042 "$K" "$LEN" "$RATE" "$HOLD" ) > "$R/client.out" 2>&1 &
CP=$!
T_CLIENT=$(date +%s%3N)
log "client started pid=$CP at $T_CLIENT"

# --- endpoint watch and arm end ---
# test arm = partial frames, no yaml_extra, at k_max (cond A: k >= 1000; cond B/M: any k); else control/intervention arm.
TEST=0; [ "$MODE" = partial ] && [ "$YX" = "-" ] && [ "$K" -ge 1000 -o "$COND" != A ] && TEST=1
T_OOM=""; T_EXIT=""; T_DONE=""; RC=""; END=""
PAT='OutOfDirectMemoryError|java.lang.OutOfMemoryError|OutOfMemory error letting the JVM handle'
while true; do
  now=$(date +%s)
  if [ -z "$T_OOM" ]; then
    l=$(grep -h -E "$PAT" "$D"/logs/system*.log* "$D/node-stdout.log" 2>/dev/null | grep -v 'CompileCommand' | head -1)  # SH fix: skip the startup CompileCommand line
    [ -n "$l" ] && { T_OOM=$(date +%s); log "t_oom: first OOM line: ${l:0:400}"; }
  fi
  if [ -z "$T_EXIT" ] && ! kill -0 "$PID" 2>/dev/null; then
    wait "$PID"; RC=$?; T_EXIT=$(date +%s); PID=""; log "t_exit: node launcher exited rc=$RC"
  fi
  if [ -z "$T_DONE" ] && grep -q '^done' "$R/client.out" 2>/dev/null; then T_DONE=$(date +%s); log "client done: $(grep -E '^(holding|alive|stop)' "$R/client.out" | tr '\n' ' ')"; fi
  if [ "$TEST" = 1 ]; then
    [ -n "$T_EXIT" ] && [ $((now - T_EXIT)) -ge 10 ] && { END="node exit + 10 s"; break; }
    if [ -n "$T_OOM" ] && [ -z "$T_EXIT" ]; then
      lim=600
      if [ $((now - T_OOM)) -ge 600 ]; then
        s1=$(stat -c %s "$D"/logs/*.hprof* 2>/dev/null | paste -sd+ | bc); sleep 5; s2=$(stat -c %s "$D"/logs/*.hprof* 2>/dev/null | paste -sd+ | bc)
        [ "${s2:-0}" -gt "${s1:-0}" ] && lim=1200
      fi
      [ $((now - T_OOM)) -ge $lim ] && { END="t_oom + ${lim} s with node alive"; break; }
    fi
    [ -z "$T_OOM" ] && [ -n "$T_DONE" ] && [ $((now - T_DONE)) -ge 300 ] && { END="client done + 300 s, no OOM"; break; }
    [ -z "$T_OOM" ] && [ -z "$T_EXIT" ] && ! kill -0 "$CP" 2>/dev/null && [ -z "$T_DONE" ] && { END="client exited without done"; break; }
  else
    if ! kill -0 "$CP" 2>/dev/null; then sleep 2; END="client exited (control/intervention)"; break; fi
    [ -n "$T_EXIT" ] && [ $((now - T_EXIT)) -ge 10 ] && { END="node exit + 10 s (control arm)"; break; }
  fi
  [ $((now - T_START)) -ge 2700 ] && { END="hard per-run cap 45 min"; break; }
  sleep 2
done
log "arm end: $END"
log "last sample: $(tail -1 "$R/samples.tsv")"
stop_bg; pkill -f "$H/stall_client.py" 2>/dev/null; pkill -f "$H/service_probe.py" 2>/dev/null
NODE_ALIVE_AT_END=0; alive && NODE_ALIVE_AT_END=1
stop_node
{ echo "t_start=$T_START"; echo "t_client_ms=$T_CLIENT"; echo "t_oom=$T_OOM"; echo "t_exit=$T_EXIT"; echo "rc=$RC"; echo "t_client_done=$T_DONE"; echo "end=$END"; echo "node_alive_at_end=$NODE_ALIVE_AT_END"; echo "arm_test=$TEST"; echo "cond=$COND"; echo "mode=$MODE"; echo "k=$K"; echo "yaml_extra=$YX"; echo "btm=$BTM"; } > "$R/exit.txt"

# --- collect ---
grep -E '^NTF(DISCARD|FAIL|MEM) ' "$D/node-stdout.log" > "$R/btm-lines.txt" 2>/dev/null
for f in "$D"/logs/system*.log*; do [ -f "$f" ] && cp "$f" "$R/"; done
cp "$D/node-stdout.log" "$R/"; cp "$D/logs/debug.log" "$R/" 2>/dev/null
for f in "$D"/logs/gc.log*; do [ -f "$f" ] && tail -300 "$f" > "$R/$(basename "$f").tail"; done
grep -n -m1 -B2 -A60 -E 'ERROR.*OutOfMemory|OutOfMemory error letting' "$D/logs/system.log" > "$R/first-oom.txt" 2>/dev/null
{ echo "--- first OutOfDirectMemoryError line (any log) ---"; grep -h -n -m1 'OutOfDirectMemoryError' "$D"/logs/system*.log* "$D/node-stdout.log" 2>/dev/null | head -1; } >> "$R/first-oom.txt"
ls -l --time-style=+%s "$D"/logs/*.hprof* "$C"/*.hprof* "$D"/*.hprof* > "$R/hprof.txt" 2>&1
sudo -n journalctl -k --since "@$T_START" 2>/dev/null | grep -i -E 'oom|killed process' > "$R/kernel.txt"
log "collected; hprof: $(tr '\n' ' ' < "$R/hprof.txt")"
rm -f "$D"/logs/*.hprof* "$D"/*.hprof*
rm -rf "$D"
log "final: daemon=$(ndaemons) client=$(pgrep -fc "$H/stall_client.py") probe=$(pgrep -fc "$H/service_probe.py") 9042=$(ss -ltnH 'sport = :9042' | wc -l) scopes=$(systemctl --user list-units --type=scope --no-legend 'u2-w1-*' | wc -l)"
python3 "$H/selfcheck.py" "$R" > "$R/summary.txt" 2>&1; log "summary: $(grep '^OUTCOME' "$R/summary.txt")"
log "run $RID done"
