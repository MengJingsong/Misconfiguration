#!/usr/bin/env bash
# OOM-exp R6-V (2026-11-12, apt179): DOB_MAX_RECYCLE_BYTES + MAX_HINT_BUFFERS, both at defaults, at an
# acceptable direct budget (>= 512 MiB, standing budget rule). Derived from default run 1's oom-run.sh
# (../../DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--default/oom-run.sh) and the R2 recheck changes
# (heap dump into the arm folder, gc log copy, swap/avail sampling), plus:
#   - heap 2048M default; build and data on /mydata/r6v;
#   - up to four concurrent workloads: H (hints.yaml, or local.yaml for the no-hints control), F (fill:
#     extra 1 KiB writes into dobks to drive more shared-pool workers), D (S-byte values into dobks,
#     started D_LEAD s after H/F), all with time caps;
#   - DOB value size is a parameter (dob profile generated per arm);
#   - thread count of N1 per sample; optional end-of-arm heap dump (END_DUMP=1) for the holder breakdown.
# Both constraints stay at defaults: the harness fails the arm if either -D appears on N1's command line.
# Topology: N1 127.0.0.2 (dc1, node under test, JMX 7199), N2 127.0.0.3 (dc2, JMX 7200), N2 kill -9'd
# after schema creation. Keyspaces: dobks {dc1:1}, hintks {dc1:1, dc2:1}.
# Usage: oom-run.sh arm <name> <direct_budget_MiB>
#   env: H_PROFILE (hints.yaml|local.yaml|none) H_THREADS H_N H_POP; F_THREADS F_N; D_THREADS D_N D_SIZE D_LEAD;
#        SECS (cap for H/F), D_SECS (cap for D), XMX, END_DUMP
set -Eeuo pipefail
CH=/mydata/r6v/cassandra; BASE=/mydata/r6v; L=$BASE/logs
N1DIR=$BASE/N1; N2DIR=$BASE/N2; N1CONF=$BASE/N1-conf; N2CONF=$BASE/N2-conf
N1LOGS=$BASE/N1-logs; N2LOGS=$BASE/N2-logs
XMX=${XMX:-2048M}; XMX2=${XMX2:-1024M}
H_PROFILE=${H_PROFILE:-hints.yaml}; H_THREADS=${H_THREADS:-64}; H_N=${H_N:-6000000}; H_POP=${H_POP:-1}
F_THREADS=${F_THREADS:-0}; F_N=${F_N:-6000000}
R_THREADS=${R_THREADS:-0}; D_THREADS=${D_THREADS:-0}; D_N=${D_N:-12000}; D_SIZE=${D_SIZE:-523000}; D_LEAD=${D_LEAD:-20}
 F_WITH_D=${F_WITH_D:-0}  # 1: fill starts with D (lets the hints pool fill first)
SECS=${SECS:-150}; D_SECS=${D_SECS:-120}; END_DUMP=${END_DUMP:-0}
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
  exec > >(tee -a "$D/session.log") 2>&1; log "script: $0 $*"; log "host: $(hostname)"
  note "params: XMX=$XMX H_PROFILE=$H_PROFILE H_THREADS=$H_THREADS H_N=$H_N F_THREADS=$F_THREADS F_N=$F_N F_WITH_D=$F_WITH_D R_THREADS=$R_THREADS D_THREADS=$D_THREADS D_N=$D_N D_SIZE=$D_SIZE D_LEAD=$D_LEAD SECS=$SECS D_SECS=$D_SECS END_DUMP=$END_DUMP"; }

# ---------------------------------------------------------------- configuration
make_conf() { # <conf> <addr> <dir> <dc> <jmx_port>
  local conf=$1 addr=$2 dir=$3 dc=$4 jmx=$5
  rm -rf "$conf"; mkdir -p "$conf"; git -C "$CH" archive HEAD conf | tar -x -C "$conf" --strip-components=1
  sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$jmx\"/" "$conf/cassandra-env.sh"
  grep -q "^JMX_PORT=\"$jmx\"" "$conf/cassandra-env.sh" || fail "JMX port edit missing in $conf"
  printf 'dc=%s\nrack=rack1\n' "$dc" > "$conf/cassandra-rackdc.properties"
  rm -rf "$dir"; mkdir -p "$dir"/{data,commitlog,hints,saved_caches,cdc_raw}
  cat > "$conf/lines.yaml" <<EOF
cluster_name: oom-exp-r6v
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
open(n + '/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- r6v environment lines ----\n' + '\n'.join(add) + '\n')
PY
}
start_node() { # <conf> <dir> <logs> <xmx> <extra jvm opts> <tag>
  local conf=$1 dir=$2 logs=$3 xmx=$4 extra=$5 tag=$6
  rm -rf "$logs"; mkdir -p "$logs"
  CASSANDRA_HOME=$CH CASSANDRA_CONF=$conf CASSANDRA_LOG_DIR=$logs CASSANDRA_HEAPDUMP_DIR=$D MAX_HEAP_SIZE=$xmx HEAP_NEWSIZE= JVM_EXTRA_OPTS="$extra" \
    "$CH/bin/cassandra" -p "$dir/cassandra.pid" > "$D/$tag-stdout.txt" 2>&1
  ready() { [ -n "$(pid_of "$logs")" ] || return 1; grep -q 'Starting listening for CQL clients' "$logs/system.log" 2>/dev/null; }
  wait_for "$tag CQL up" 300 ready; }

ring_up() { local budget=$1
  check "no daemon running" bash -c '! pgrep -f "[o]rg.apache.cassandra.service.CassandraDaemon" >/dev/null'
  check "ports free" bash -c '! ss -ltn | grep -qE "127.0.0.[23]:(7000|9042)|:(7199|7200)\b"'
  make_conf "$N1CONF" 127.0.0.2 "$N1DIR" dc1 7199; make_conf "$N2CONF" 127.0.0.3 "$N2DIR" dc2 7200
  cp "$N1CONF/cassandra.yaml" "$D/n1-cassandra.yaml"; diff <(git -C "$CH" show HEAD:conf/cassandra.yaml) "$N1CONF/cassandra.yaml" > "$D/n1-cassandra.yaml.diff" || true
  local opts="-XX:MaxDirectMemorySize=${budget}m -XX:NativeMemoryTracking=summary"
  start_node "$N1CONF" "$N1DIR" "$N1LOGS" "$XMX" "$opts" n1
  PID=$(n1_pid); tr '\0' '\n' < /proc/$PID/cmdline > "$D/n1-jvm-args.txt"
  check "N1 arg -Xmx$XMX" grep -qx -- "-Xmx$XMX" "$D/n1-jvm-args.txt"
  check "N1 last MaxDirectMemorySize is ${budget}m" bash -c "[ \"\$(grep -E -- '^-XX:MaxDirectMemorySize=' $D/n1-jvm-args.txt | tail -1)\" = '-XX:MaxDirectMemorySize=${budget}m' ]"
  check "N1 has no -D for either constraint (defaults)" bash -c "! grep -qiE -- 'dob_max_recycle_bytes|MAX_HINT_BUFFERS' $D/n1-jvm-args.txt"
  start_node "$N2CONF" "$N2DIR" "$N2LOGS" "$XMX2" "" n2
  wait_for "both UN" 120 bash -c "CASSANDRA_HOME=$CH CASSANDRA_CONF=$N1CONF $CH/bin/nodetool -h 127.0.0.1 -p 7199 status 2>/dev/null | grep -c '^UN' | grep -qx 2"
  "$CH/bin/cqlsh" 127.0.0.2 --request-timeout=120 -e "
    CREATE KEYSPACE dobks WITH replication = {'class':'NetworkTopologyStrategy','dc1':1};
    CREATE TABLE dobks.standard1 (key blob PRIMARY KEY, \"C0\" blob);
    CREATE KEYSPACE hintks WITH replication = {'class':'NetworkTopologyStrategy','dc1':1,'dc2':1};
    CREATE TABLE hintks.standard1 (key blob PRIMARY KEY, \"C0\" blob);" > "$D/cqlsh-schema.txt" 2>&1 || fail "schema creation failed"
  wait_for "schema agreement" 60 bash -c "CASSANDRA_HOME=$CH CASSANDRA_CONF=$N1CONF $CH/bin/nodetool -h 127.0.0.1 -p 7199 describecluster 2>/dev/null | grep -A3 'Schema versions' | grep -c '127.0.0' | grep -qx 1"
  local p2; p2=$(n2_pid); kill -9 "$p2"; note "N2 (pid $p2) killed at $(date '+%T')"
  wait_for "N1 sees N2 DN" 120 bash -c "CASSANDRA_HOME=$CH CASSANDRA_CONF=$N1CONF $CH/bin/nodetool -h 127.0.0.1 -p 7199 status 2>/dev/null | grep -q '^DN  127.0.0.3'"
  nt1 status > "$D/status-n2-down.txt" 2>&1 || true
  note "N1 pid $PID: -Xmx$XMX MaxDirectMemorySize=${budget}MiB, dob_max_recycle_bytes and MAX_HINT_BUFFERS unset (defaults 1 MiB, 3); N2 DN"
  sleep 5; }

# ---------------------------------------------------------------- instruments
direct() { nt1 sjk mx -mg -b 'java.nio:type=BufferPool,name=direct' -f MemoryUsed 2>/dev/null | grep -Eo '^[0-9]+' | head -1; }
directcount() { nt1 sjk mx -mg -b 'java.nio:type=BufferPool,name=direct' -f Count 2>/dev/null | grep -Eo '^[0-9]+' | head -1; }
PEAK=0
sample() { local tag=$1
  [ -r "/proc/$PID/status" ] || { note "s $tag: N1 GONE"; return 1; }
  local du dc rss heap thr swp
  du=$(direct || true); dc=$(directcount || true)
  rss=$(awk '/^RssAnon/{print $2}' /proc/$PID/status 2>/dev/null || true); thr=$(awk '/^Threads/{print $2}' /proc/$PID/status 2>/dev/null || true)
  swp="$(awk '/^VmSwap/{print $2}' /proc/$PID/status 2>/dev/null)/$(free -m | awk '/^Mem/{print $7}')"
  heap=$(jcmd "$PID" GC.heap_info 2>/dev/null | grep -Eo 'total [0-9]+K, used [0-9]+K' | head -1 || true)
  local mib=$(( ${du:-0} / 1048576 )); [ "$mib" -gt "$PEAK" ] && PEAK=$mib
  note "s $tag $(date +%T): directMiB=$mib direct=${du:-?} count=${dc:-?} threads=${thr:-?} rssAnonKB=${rss:-?} swapKB/availMiB=${swp:-?} heap=[${heap:-?}]"; }
hints_pool() { local tag=$1; local f="$D/jstack-$tag.txt"
  jstack "$PID" > "$f" 2>/dev/null || { note "jstack $tag failed"; return 0; }
  note "pool $tag: parked in HintsBufferPool take()=$(grep -B4 'HintsBufferPool.switchCurrentBuffer' "$f" | grep -c 'LinkedBlockingQueue.take' || true); threads by prefix: $(grep -Eo '^"[A-Za-z-]+' "$f" | sort | uniq -c | sort -rn | head -6 | awk '{printf "%s=%s ", $2, $1}')"; }
histo() { local tag=$1
  jcmd "$PID" GC.class_histogram > "$D/histo-$tag.txt" 2>/dev/null || { note "histo $tag failed"; return 0; }
  note "histo $tag: $(grep -E ' org.apache.cassandra.hints.HintsBuffer$| java.nio.DirectByteBuffer$' "$D/histo-$tag.txt" | awk '{print $4"="$2}' | tr '\n' ' ')"; }

# ---------------------------------------------------------------- workloads
stress() { CASSANDRA_HOME=$CH "$CH/tools/bin/cassandra-stress" "$@" -node 127.0.0.2 -port native=9042 jmx=7199 -mode native cql3 protocolVersion=4; }
mk_dob_profile() { sed "s/__SIZE__/$D_SIZE/" "$BASE/dob.yaml.in" > "$D/dob.yaml"; }
run_w() { # <tag> <profile> <n> <pop_start> <threads> <cap> [ops]
  local tag=$1 prof=$2 n=$3 pop=$4 thr=$5 cap=$6 ops=${7:-insert=1}
  note "$tag start $(date +%T.%N | cut -c1-12): profile=$(basename "$prof") n=$n threads=$thr cap=${cap}s"
  timeout --signal=INT "$cap" bash -c "$(declare -f stress); CH=$CH; stress user profile=$prof 'ops($ops)' n=$n cl=ONE no-warmup -pop seq=$pop..$((pop + n - 1)) -errors retries=10 -rate threads=$thr" > "$D/stress-$tag.txt" 2>&1 || true
  note "$tag end $(date +%T)"; }
tablecounts() { local tag=$1
  nt1 tablestats dobks.standard1 hintks.standard1 > "$D/tablestats-$tag.txt" 2>&1 || true
  note "tables $tag: $(grep -E 'Table:|Write Count' "$D/tablestats-$tag.txt" | tr -s ' \t' ' ' | tr '\n' '|')"
  note "hints dir $tag: $(du -sm "$N1DIR/hints" | cut -f1) MiB"; }

cmd_arm() { local name=$1 budget=$2
  D=$L/$name; start_log "$@"; ring_up "$budget"; local alive=1 pids=() dp=""
  [ "$D_THREADS" -gt 0 ] && mk_dob_profile
  sample idle1; sleep 5; sample idle2; histo idle
  [ "$H_PROFILE" != none ] && { run_w H "$BASE/$H_PROFILE" "$H_N" "$H_POP" "$H_THREADS" "$SECS" & pids+=($!); }
  [ "$F_THREADS" -gt 0 ] && [ "$F_WITH_D" = 0 ] && { run_w F "$BASE/local.yaml" "$F_N" 50000001 "$F_THREADS" "$SECS" & pids+=($!); }
  local i=0 t0=$SECONDS
  while :; do
    if [ -z "$dp" ] && [ "$D_THREADS" -gt 0 ] && [ $((SECONDS - t0)) -ge "$D_LEAD" ]; then
      hints_pool pre-dob; run_w D "$D/dob.yaml" "$D_N" 1 "$D_THREADS" "$D_SECS" & dp=$!; pids+=($dp)
      [ "$F_THREADS" -gt 0 ] && [ "$F_WITH_D" = 1 ] && { run_w F "$BASE/local.yaml" "$F_N" 50000001 "$F_THREADS" "$D_SECS" & pids+=($!); }
      # R (optional): reads of the DOB rows, started with D, to drive ReadStage shared-pool workers
      [ "$R_THREADS" -gt 0 ] && { run_w R "$D/dob.yaml" 100000000 1 "$R_THREADS" "$D_SECS" read1=1 & pids+=($!); }; fi
    local live=0; for p in "${pids[@]}"; do kill -0 "$p" 2>/dev/null && live=1; done
    [ $live = 0 ] && { [ "$D_THREADS" -eq 0 ] || [ -n "$dp" ]; } && break
    sleep 4; i=$((i+1)); sample "w$i" || { alive=0; break; }; [ $((i % 4)) = 0 ] && hints_pool "w$i"
  done
  [ $alive = 0 ] && { pkill -f '[o]rg.apache.cassandra.stress.Stress' 2>/dev/null || true; }
  for p in "${pids[@]}"; do wait "$p" 2>/dev/null || true; done
  if [ $alive = 1 ]; then for h in 1 2 3 4 5 6; do sleep 5; sample "hold$h" || { alive=0; break; }; done; fi
  [ $alive = 1 ] && { hints_pool final; histo final; sample final || alive=0; }
  [ $alive = 1 ] && tablecounts final
  if [ $alive = 1 ] && [ "$END_DUMP" = 1 ]; then jcmd "$PID" GC.heap_dump -all "$D/end-dump.hprof" > /dev/null 2>&1 || true; note "end dump: $(ls -la "$D/end-dump.hprof" 2>/dev/null)"; fi
  note "PEAK directMiB (sampled) = $PEAK of $budget ($(( PEAK * 100 / budget ))%)"
  for w in H F D R; do [ -f "$D/stress-$w.txt" ] && note "stress-$w: $(grep -E 'Total partitions|Total errors|Op rate' "$D/stress-$w.txt" | tr -s ' ' | tr '\n' '|')"; done
  grep -c '^ERROR' "$N1LOGS/system.log" > "$D/error-count.txt" 2>/dev/null || echo 0 > "$D/error-count.txt"
  grep -E '^ERROR' "$N1LOGS/system.log" | head -20 > "$D/error-lines.txt" || true
  grep -hE 'java.lang.OutOfMemoryError' "$D/n1-stdout.txt" "$N1LOGS/system.log" 2>/dev/null | head -10 > "$D/oom-jvm.txt" || true
  sudo -n dmesg -T 2>/dev/null | grep -E "Killed process|invoked oom-killer" | tail -5 > "$D/dmesg-kills-tail.txt" || true
  cp "$N1LOGS/system.log" "$D/n1-system.log" 2>/dev/null || true; for g in "$N1LOGS"/gc.log*; do [ -f "$g" ] && cp "$g" "$D/n1-$(basename "$g")"; done
  ls -la "$D"/*.hprof 2>/dev/null > "$D/hprof.txt" || true
  note "ERROR lines: $(cat "$D/error-count.txt"); JVM OOM lines: $(wc -l < "$D/oom-jvm.txt"); N1 alive at end: $(n1_up && echo yes || echo NO)"
  pkill -f '[o]rg.apache.cassandra.stress.Stress' 2>/dev/null || true
  for p in $(n1_pid); do nt1 stopdaemon >/dev/null 2>&1 || true; for _ in $(seq 60); do n1_up || break; sleep 1; done; n1_up && kill -9 "$p" 2>/dev/null || true; done
  for _ in $(seq 60); do any_daemon || break; sleep 1; done
  check "no daemon left" bash -c '! pgrep -f "[o]rg.apache.cassandra.service.CassandraDaemon" >/dev/null'
  check "no stress left" bash -c '! pgrep -f "[o]rg.apache.cassandra.stress.Stress" >/dev/null'
  rm -rf "$N1DIR/data" "$N2DIR/data" "$N1DIR/commitlog" "$N1DIR/hints"   # data volume is not evidence; keep disk use bounded
  log "ARM $name DONE"; }
case "${1:-}" in arm) shift; cmd_arm "$@" ;; *) echo "usage: $0 arm <name> <budget_MiB>"; exit 2 ;; esac
