#!/usr/bin/env bash
# OOM-exp convergence run 8: DOB_MAX_RECYCLE_BYTES + MAX_HINT_BUFFERS.
# Shared budget: the JVM's direct-buffer budget, -XX:MaxDirectMemorySize, on node N1.
# Both pools are java.nio.DirectByteBuffers (ByteBuffer.allocateDirect -> Bits.reserveMemory),
# so unlike runs 4-7 (JNA malloc pools) the JVM flag itself is the budget both draw on.
#   DOB_MAX_RECYCLE_BYTES (-Dcassandra.dob_max_recycle_bytes=L): every thread's scratch
#     DataOutputBuffer is kept between uses if its capacity <= L; a 14 MiB mutation grows it
#     to 2(S-1) ~ 28 MiB on each MutationStage worker that applies one (CommitLog.add).
#   MAX_HINT_BUFFERS (-Dcassandra.MAX_HINT_BUFFERS=n): the hints pool creates up to n direct
#     slabs of max(2*max_mutation_size, 32 MiB) = 32 MiB and never frees them (recycled).
# Topology: N1 127.0.0.2 (dc1, node under test, JMX 7199), N2 127.0.0.3 (dc2, JMX 7200).
# Keyspaces: dobks {dc1:1} (no hints), hintks {dc1:1, dc2:1} (every write hints for N2).
# N2 is up only while the ring and schema are created, then kill -9'd before any reading.
# Usage: oom-run.sh arm <name> <budget_MiB> <L_bytes> <n_buffers> <workloads: hints,dob> [schedule]
#   schedule: dobfirst (start dob, start hints DOB_LEAD s later, both run together)
#             seq (default: one workload after the other, in the order given)
#             overlap (start hints, start dob after HINT_LEAD seconds, both run together)
set -Eeuo pipefail
CH=$HOME/cassandra-run1; BASE=$HOME/oom-direct-run8; L=$BASE/logs
N1DIR=$BASE/N1; N2DIR=$BASE/N2; N1CONF=$BASE/N1-conf; N2CONF=$BASE/N2-conf
N1LOGS=$BASE/N1-logs; N2LOGS=$BASE/N2-logs
XMX=${XMX:-3072M}; XMX2=${XMX2:-1024M}
N_HINTS=${N_HINTS:-1500000}; HINT_THREADS=${HINT_THREADS:-64}; HINT_SECS=${HINT_SECS:-240}
N_DOB=${N_DOB:-400}; DOB_THREADS=${DOB_THREADS:-8}; DOB_SIZE=${DOB_SIZE:-4000000}; DOB_SECS=${DOB_SECS:-300}
HINT_LEAD=${HINT_LEAD:-60}; DOB_LEAD=${DOB_LEAD:-10}
D=""; S=""; PID=""
log()  { echo "[$(date '+%F %T')] $*" >&2; }
note() { printf '%s\n' "$*" | tee -a "$S"; }
fail() { log "FAIL: $*"; exit 1; }
check(){ local d=$1; shift; if "$@"; then log "CHECK PASS: $d"; else fail "CHECK FAILED: $d"; fi; }
wait_for() { local d=$1 t=$2 i=0; shift 2; until "$@"; do sleep 1; i=$((i+1)); [ "$i" -ge "$t" ] && fail "timeout ${t}s: $d"; done; log "ok: $d (${i}s)"; }
pid_of() { pgrep -f "[o]rg.apache.cassandra.service.CassandraDaemon" | while read -r p; do tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null | grep -q -- "-Dcassandra.logdir=$1 " && echo "$p"; done | head -1; }
n1_pid() { pid_of "$N1LOGS"; }
n2_pid() { pid_of "$N2LOGS"; }
n1_up() { [ -n "$(n1_pid)" ]; }
any_daemon() { pgrep -f '[o]rg.apache.cassandra.service.CassandraDaemon' >/dev/null; }
nt1() { CASSANDRA_HOME=$CH CASSANDRA_CONF=$N1CONF "$CH/bin/nodetool" -h 127.0.0.1 -p 7199 "$@"; }
cleanup() { local rc=$?; trap - EXIT ERR
  pkill -f '[o]rg.apache.cassandra.stress.Stress' 2>/dev/null || true
  for p in $(n1_pid) $(n2_pid); do kill -9 "$p" 2>/dev/null || true; done
  for _ in $(seq 60); do any_daemon || break; sleep 1; done; exit "$rc"; }
trap 'log "ERR line $LINENO: $BASH_COMMAND"' ERR; trap cleanup EXIT
start_log() { mkdir -p "$L"; [ -e "$D" ] && mv "$D" "$D.attempt-$(date +%s)"; mkdir -p "$D"; S=$D/summary.txt
  exec > >(tee -a "$D/session.log") 2>&1; log "script: $0 $*"; log "host: $(hostname)"; }

# ---------------------------------------------------------------- configuration
make_conf() { # <conf> <addr> <dir> <dc> <jmx_port>
  local conf=$1 addr=$2 dir=$3 dc=$4 jmx=$5
  rm -rf "$conf"; mkdir -p "$conf"; git -C "$CH" archive HEAD conf | tar -x -C "$conf" --strip-components=1
  sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$jmx\"/" "$conf/cassandra-env.sh"
  grep -q "^JMX_PORT=\"$jmx\"" "$conf/cassandra-env.sh" || fail "JMX port edit missing in $conf"
  printf 'dc=%s\nrack=rack1\n' "$dc" > "$conf/cassandra-rackdc.properties"
  rm -rf "$dir"; mkdir -p "$dir"/{data,commitlog,hints,saved_caches,cdc_raw}
  cat > "$conf/lines.yaml" <<EOF
cluster_name: oom-exp-direct-run8
num_tokens: 1
initial_token: $([ "$addr" = 127.0.0.2 ] && echo -9223372036854775808 || echo 0)
auto_bootstrap: false
listen_address: $addr
rpc_address: $addr
broadcast_rpc_address: $addr
endpoint_snitch: GossipingPropertyFileSnitch
seed_provider:
  - class_name: org.apache.cassandra.locator.SimpleSeedProvider
    parameters:
      - seeds: "127.0.0.2:7000"
data_file_directories:
    - $dir/data
commitlog_directory: $dir/commitlog
hints_directory: $dir/hints
saved_caches_directory: $dir/saved_caches
cdc_raw_directory: $dir/cdc_raw
max_hint_window: 24h
EOF
  python3 - "$conf" <<'PY'
import re, sys
n = sys.argv[1]
add = open(n + '/lines.yaml').read().splitlines()
keys = {l.split(':', 1)[0] for l in add if re.match(r'^[A-Za-z_]+:', l)}
out, skip = [], False
for l in open(n + '/cassandra.yaml').read().splitlines():
    m = re.match(r'^([A-Za-z_]+):', l)
    if m:
        skip = m.group(1) in keys
        if skip: continue
    elif skip and (l.startswith((' ', '\t', '-')) or l.strip() == '' or l.lstrip().startswith('#')):
        continue
    else:
        skip = False
    out.append(l)
open(n + '/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- run8 lines ----\n' + '\n'.join(add) + '\n')
PY
}
start_node() { # <conf> <dir> <logs> <xmx> <extra jvm opts> <tag>
  local conf=$1 dir=$2 logs=$3 xmx=$4 extra=$5 tag=$6
  rm -rf "$logs"; mkdir -p "$logs"
  CASSANDRA_HOME=$CH CASSANDRA_CONF=$conf CASSANDRA_LOG_DIR=$logs MAX_HEAP_SIZE=$xmx HEAP_NEWSIZE= JVM_EXTRA_OPTS="$extra" \
    "$CH/bin/cassandra" -p "$dir/cassandra.pid" > "$D/$tag-stdout.txt" 2>&1
  ready() { [ -n "$(pid_of "$logs")" ] || return 1; grep -q 'Starting listening for CQL clients' "$logs/system.log" 2>/dev/null; }
  wait_for "$tag CQL up" 300 ready; }

ring_up() { local budget=$1 Lb=$2 n=$3
  check "no daemon running" bash -c '! pgrep -f "[o]rg.apache.cassandra.service.CassandraDaemon" >/dev/null'
  check "ports free" bash -c '! ss -ltn | grep -qE "127.0.0.[23]:(7000|9042)|:(7199|7200)\b"'
  make_conf "$N1CONF" 127.0.0.2 "$N1DIR" dc1 7199; make_conf "$N2CONF" 127.0.0.3 "$N2DIR" dc2 7200
  cp "$N1CONF/cassandra.yaml" "$D/n1-cassandra.yaml"; diff <(git -C "$CH" show HEAD:conf/cassandra.yaml) "$N1CONF/cassandra.yaml" > "$D/n1-cassandra.yaml.diff" || true
  local opts="-XX:MaxDirectMemorySize=${budget}m -Dcassandra.dob_max_recycle_bytes=$Lb -Dcassandra.MAX_HINT_BUFFERS=$n -XX:NativeMemoryTracking=summary"
  start_node "$N1CONF" "$N1DIR" "$N1LOGS" "$XMX" "$opts" n1
  PID=$(n1_pid); tr '\0' '\n' < /proc/$PID/cmdline > "$D/n1-jvm-args.txt"
  for a in "-Xmx$XMX" "-XX:MaxDirectMemorySize=${budget}m" "-Dcassandra.dob_max_recycle_bytes=$Lb" "-Dcassandra.MAX_HINT_BUFFERS=$n"; do
    check "N1 arg $a" grep -qx -- "$a" "$D/n1-jvm-args.txt"; done
  start_node "$N2CONF" "$N2DIR" "$N2LOGS" "$XMX2" "" n2
  wait_for "both UN" 120 bash -c "CASSANDRA_HOME=$CH CASSANDRA_CONF=$N1CONF $CH/bin/nodetool -h 127.0.0.1 -p 7199 status 2>/dev/null | grep -c '^UN' | grep -qx 2"
  "$CH/bin/cqlsh" 127.0.0.2 --request-timeout=120 -e "
    CREATE KEYSPACE dobks WITH replication = {'class':'NetworkTopologyStrategy','dc1':1};
    CREATE TABLE dobks.standard1 (key blob PRIMARY KEY, \"C0\" blob);
    CREATE KEYSPACE hintks WITH replication = {'class':'NetworkTopologyStrategy','dc1':1,'dc2':1};
    CREATE TABLE hintks.standard1 (key blob PRIMARY KEY, \"C0\" blob);" > "$D/cqlsh-schema.txt" 2>&1 || fail "schema creation failed"
  wait_for "schema agreement" 60 bash -c "CASSANDRA_HOME=$CH CASSANDRA_CONF=$N1CONF $CH/bin/nodetool -h 127.0.0.1 -p 7199 describecluster 2>/dev/null | grep -A3 'Schema versions' | grep -c '127.0.0' | grep -qx 1"
  nt1 status > "$D/status-ring.txt" 2>&1 || true
  local p2; p2=$(n2_pid); kill -9 "$p2"; note "N2 (pid $p2) killed at $(date '+%T')"
  wait_for "N1 sees N2 DN" 120 bash -c "CASSANDRA_HOME=$CH CASSANDRA_CONF=$N1CONF $CH/bin/nodetool -h 127.0.0.1 -p 7199 status 2>/dev/null | grep -q '^DN  127.0.0.3'"
  nt1 status > "$D/status-n2-down.txt" 2>&1 || true
  note "N1 pid $PID: -Xmx$XMX MaxDirectMemorySize=${budget}MiB dob_max_recycle_bytes=$Lb MAX_HINT_BUFFERS=$n; N2 DN"
  sleep 10; }

# ---------------------------------------------------------------- instruments
direct() { nt1 sjk mx -mg -b 'java.nio:type=BufferPool,name=direct' -f MemoryUsed 2>/dev/null | grep -Eo '^[0-9]+' | head -1; }
directcount() { nt1 sjk mx -mg -b 'java.nio:type=BufferPool,name=direct' -f Count 2>/dev/null | grep -Eo '^[0-9]+' | head -1; }
sample() { local tag=$1
  [ -r "/proc/$PID/status" ] || { note "s $tag: N1 GONE"; return 1; }
  local du dc nmt rss heap
  du=$(direct || true); dc=$(directcount || true)
  nmt=$(jcmd "$PID" VM.native_memory summary 2>/dev/null | grep -A1 -E '^-\s+Other' | grep -Eo 'committed=[0-9]+KB' | head -1 || true)
  rss=$(awk '/^RssAnon/{print $2}' /proc/$PID/status 2>/dev/null || true)
  heap=$(jcmd "$PID" GC.heap_info 2>/dev/null | grep -Eo 'total [0-9]+K, used [0-9]+K' | head -1 || true)
  note "s $tag $(date +%T): directMiB=$(( ${du:-0} / 1048576 )) direct=${du:-?} count=${dc:-?} nmtOther=${nmt:-?} rssAnonKB=${rss:-?} heap=[${heap:-?}]"; }
hints_pool() { local tag=$1; local f="$D/jstack-$tag.txt"
  jstack "$PID" > "$f" 2>/dev/null || { note "jstack $tag failed"; return 0; }
  note "pool $tag: threads parked in HintsBufferPool.switchCurrentBuffer take()=$(grep -B4 'HintsBufferPool.switchCurrentBuffer' "$f" | grep -c 'LinkedBlockingQueue.take' || true), blocked on pool monitor=$(grep -c 'HintsBufferPool.switchCurrentBuffer' "$f" || true)"; }
histo() { local tag=$1
  jcmd "$PID" GC.class_histogram > "$D/histo-$tag.txt" 2>/dev/null || { note "histo $tag failed"; return 0; }
  note "histo $tag: $(grep -E ' org.apache.cassandra.hints.HintsBuffer$| java.nio.DirectByteBuffer$' "$D/histo-$tag.txt" | awk '{print $4"="$2}' | tr '\n' ' ')"; }

# ---------------------------------------------------------------- workloads
stress() { CASSANDRA_HOME=$CH "$CH/tools/bin/cassandra-stress" "$@" -node 127.0.0.2 -port native=9042 jmx=7199 -mode native cql3 protocolVersion=4; }
run_hints() { log "+ hints workload: $N_HINTS x 1 KiB rows into hintks (RF dc1:1,dc2:1, N2 down), $HINT_THREADS threads, cap ${HINT_SECS}s"
  timeout --signal=INT "$HINT_SECS" bash -c "$(declare -f stress); CH=$CH; BASE=$BASE; stress user profile=$BASE/hints.yaml 'ops(insert=1)' n=$N_HINTS cl=ONE no-warmup -pop seq=1..$N_HINTS -errors retries=10 -rate threads=$HINT_THREADS" > "$D/stress-hints.txt" 2>&1; }
run_dob() { log "+ dob workload: $N_DOB x $DOB_SIZE-byte values into dobks (dc1 only), $DOB_THREADS threads, cap ${DOB_SECS}s"
  timeout --signal=INT "$DOB_SECS" bash -c "$(declare -f stress); CH=$CH; BASE=$BASE; stress user profile=$BASE/dob.yaml 'ops(insert=1)' n=$N_DOB cl=ONE no-warmup -pop seq=1..$N_DOB -errors retries=50 -rate threads=$DOB_THREADS" > "$D/stress-dob.txt" 2>&1; }
monitor() { local p=$1 pre=$2 i=0
  while kill -0 "$p" 2>/dev/null; do sleep 5; i=$((i+1)); sample "$pre$i" || return 1; [ $((i % 3)) = 0 ] && hints_pool "$pre$i"; done; return 0; }
tablecounts() { local tag=$1
  nt1 tablestats dobks.standard1 hintks.standard1 > "$D/tablestats-$tag.txt" 2>&1 || true
  note "tables $tag: $(grep -E 'Table:|Write Count' "$D/tablestats-$tag.txt" | tr -s ' \t' ' ' | tr '\n' '|')"
  note "hints dir $tag: $(du -sm "$N1DIR/hints" | cut -f1) MiB"; }

cmd_arm() { local name=$1 budget=$2 Lb=$3 n=$4 WL=$5 sched=${6:-seq}
  D=$L/$name; start_log "$@"; ring_up "$budget" "$Lb" "$n"; local alive=1
  sample idle1; sleep 10; sample idle2; histo idle
  if [ "$sched" = dobfirst ]; then
    # dob client first, so its schema step (stress always issues CREATE KEYSPACE) runs on an idle node;
    # the hints load starts DOB_LEAD s later and both run together
    run_dob & local dp=$!
    for i in $(seq $((DOB_LEAD / 5))); do sleep 5; sample "d$i" || { alive=0; break; }; done
    if [ $alive = 1 ]; then run_hints & local hp=$!
      local i=0; while kill -0 "$dp" 2>/dev/null || kill -0 "$hp" 2>/dev/null; do sleep 5; i=$((i+1)); sample "b$i" || { alive=0; break; }; [ $((i % 3)) = 0 ] && hints_pool "b$i"; done
      wait "$hp" 2>/dev/null || true; fi
    wait "$dp" 2>/dev/null || true
  elif [ "$sched" = overlap ]; then
    run_hints & local hp=$!
    for i in $(seq $((HINT_LEAD / 5))); do sleep 5; sample "h$i" || { alive=0; break; }; done
    [ $alive = 1 ] && hints_pool lead
    if [ $alive = 1 ]; then run_dob & local dp=$!; monitor "$dp" d || alive=0; wait "$dp" 2>/dev/null || true; fi
    [ $alive = 1 ] && { monitor "$hp" hh || alive=0; }; wait "$hp" 2>/dev/null || true
  else
    for w in ${WL//,/ }; do [ $alive = 1 ] || break
      case $w in hints) run_hints & ;; dob) run_dob & ;; esac; local wp=$!
      monitor "$wp" "${w:0:1}" || alive=0; wait "$wp" 2>/dev/null || true
      [ $alive = 1 ] && { sample "after-$w" || alive=0; }; [ $alive = 1 ] && { hints_pool "after-$w"; tablecounts "after-$w"; }
    done
  fi
  if [ $alive = 1 ]; then for h in 1 2 3 4 5 6; do sleep 5; sample "hold$h" || { alive=0; break; }; done; fi
  [ $alive = 1 ] && { histo final; sample final || alive=0; }
  for w in hints dob; do [ -f "$D/stress-$w.txt" ] && note "stress-$w: $(grep -E 'Total partitions|Total errors|Op rate' "$D/stress-$w.txt" | tr -s ' ' | tr '\n' '|')"; done
  grep -c '^ERROR' "$N1LOGS/system.log" > "$D/error-count.txt" 2>/dev/null || echo 0 > "$D/error-count.txt"
  grep -E '^ERROR' "$N1LOGS/system.log" | head -20 > "$D/error-lines.txt" || true
  grep -hE 'java.lang.OutOfMemoryError: ' "$D/n1-stdout.txt" "$N1LOGS/system.log" 2>/dev/null | head -10 > "$D/oom-jvm.txt" || true
  sudo -n dmesg -T 2>/dev/null | grep -E "Killed process|invoked oom-killer" | tail -5 > "$D/dmesg-kills-tail.txt" || true
  cp "$N1LOGS/system.log" "$D/n1-system.log" 2>/dev/null || true; ls -la "$N1DIR"/*.hprof "$CH"/*.hprof 2>/dev/null > "$D/hprof.txt" || true
  note "ERROR lines: $(cat "$D/error-count.txt"); JVM OOM lines: $(wc -l < "$D/oom-jvm.txt"); N1 alive at end: $(n1_up && echo yes || echo NO)"
  pkill -f '[o]rg.apache.cassandra.stress.Stress' 2>/dev/null || true
  for p in $(n1_pid); do nt1 stopdaemon >/dev/null 2>&1 || true; for _ in $(seq 60); do n1_up || break; sleep 1; done; n1_up && kill -9 "$p" 2>/dev/null || true; done
  for _ in $(seq 60); do any_daemon || break; sleep 1; done
  check "no daemon left" bash -c '! pgrep -f "[o]rg.apache.cassandra.service.CassandraDaemon" >/dev/null'
  check "no stress left" bash -c '! pgrep -f "[o]rg.apache.cassandra.stress.Stress" >/dev/null'
  log "ARM $name DONE"; }
case "${1:-}" in arm) shift; cmd_arm "$@" ;; *) echo "usage: $0 arm <name> <budget_MiB> <L_bytes> <n> <workloads> [seq|overlap]"; exit 2 ;; esac
