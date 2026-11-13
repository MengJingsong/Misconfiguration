#!/usr/bin/env bash
# OOM-exp C3 run 1 (2026-11-12): DOB scratch-buffer retention multiplied by worker threads.
# Single Cassandra 5.0.9 node on apt190 (127.0.0.2), DOB_MAX_RECYCLE_BYTES at its default unless the arm
# sets L (intervention). Budget: -Xmx2048M, MAX_DIRECT_MEMORY_SIZE per arm (cassandra-env.sh sets the flag).
# Usage:
#   c3-run.sh arm <name> <direct_MiB> <L: default|bytes> <fill_threads_total> <fill_ips: 1|4> <burst> [dump|nodump]
#     burst = none | <blob_bytes>:<n_total>:<threads_per_ip>:<ips>
# Fill: FILL_N (default 4000) inserts of FILL_SIZE (default 520000) B, split evenly over fill_ips stress
# processes. With ips = 4, an iptables SNAT on lo spreads new connections to 127.0.0.2:9042 over source
# addresses 127.0.0.11-14 (emulates 4 client hosts for the per-IP in-flight limit); removed at the end.
set -Eeuo pipefail
CH=$HOME/cassandra-c1; BASE=/mydata/c3; LOGS=$BASE/logs; NODE=$BASE/node; CONF=$BASE/conf; NLOGS=$BASE/node-logs
XMX=${XMX:-2048M}; FILL_N=${FILL_N:-4000}; FILL_SIZE=${FILL_SIZE:-520000}; IDLE=${IDLE:-30}; HOLD=${HOLD:-20}
FILL_SECS=${FILL_SECS:-900}; BURST_SECS=${BURST_SECS:-600}; JMX=7199
D=""; S=""; PID=""; POLLPID=""
log()  { echo "[$(date '+%F %T')] $*" >&2; }
note() { printf '%s\n' "$*" | tee -a "$S"; }
fail() { log "FAIL: $*"; exit 1; }
check(){ local d=$1; shift; if "$@"; then log "CHECK PASS: $d"; else fail "CHECK FAILED: $d"; fi; }
wait_for() { local d=$1 t=$2 i=0; shift 2; until "$@"; do sleep 1; i=$((i+1)); [ "$i" -ge "$t" ] && fail "timeout ${t}s: $d"; done; log "ok: $d (${i}s)"; }
node_pid() { pgrep -f "[o]rg.apache.cassandra.service.CassandraDaemon" | while read -r p; do tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null | grep -q -- "-Dcassandra.logdir=$NLOGS " && echo "$p"; done | head -1; }
node_up() { [ -n "$(node_pid)" ]; }
any_daemon() { pgrep -f '[o]rg.apache.cassandra.service.CassandraDaemon' >/dev/null; }
nt() { CASSANDRA_HOME=$CH CASSANDRA_CONF=$CONF "$CH/bin/nodetool" -h 127.0.0.1 -p $JMX "$@"; }
snat_off() { local n; for n in 11 12 13 14; do
  while sudo -n iptables -t nat -D POSTROUTING -o lo -p tcp -d 127.0.0.2 --dport 9042 -m comment --comment c3-snat -m statistic --mode nth --every $(( 15 - n )) --packet 0 -j SNAT --to-source 127.0.0.$n 2>/dev/null; do :; done; done
  while sudo -n iptables -t nat -D POSTROUTING -o lo -p tcp -d 127.0.0.2 --dport 9042 -m comment --comment c3-snat -j SNAT --to-source 127.0.0.14 2>/dev/null; do :; done
  ! sudo -n iptables -t nat -S POSTROUTING | grep -q c3-snat; }
snat_on() { snat_off || fail "stale SNAT rules"
  # new connections: 1/4 -> .11, 1/3 of the rest -> .12, 1/2 of the rest -> .13, the rest -> .14
  for n in 11 12 13; do sudo -n iptables -t nat -A POSTROUTING -o lo -p tcp -d 127.0.0.2 --dport 9042 -m comment --comment c3-snat -m statistic --mode nth --every $(( 15 - n )) --packet 0 -j SNAT --to-source 127.0.0.$n; done
  sudo -n iptables -t nat -A POSTROUTING -o lo -p tcp -d 127.0.0.2 --dport 9042 -m comment --comment c3-snat -j SNAT --to-source 127.0.0.14
  sudo -n iptables -t nat -S POSTROUTING > "$D/iptables-nat.txt"; }
cleanup() { local rc=$?; trap - EXIT ERR
  pkill -f '[o]rg.apache.cassandra.stress.Stress' 2>/dev/null || true
  [ -n "$POLLPID" ] && kill "$POLLPID" 2>/dev/null || true
  for p in $(node_pid); do kill -9 "$p" 2>/dev/null || true; done
  for _ in $(seq 60); do any_daemon || break; sleep 1; done
  snat_off || log "WARN: SNAT rules left"; exit "$rc"; }
trap 'log "ERR line $LINENO: $BASH_COMMAND"' ERR; trap cleanup EXIT

make_conf() {
  rm -rf "$CONF"; mkdir -p "$CONF"; cp -r "$CH/conf/." "$CONF/"
  rm -rf "$NODE"; mkdir -p "$NODE"/{data,commitlog,hints,saved_caches,cdc_raw}
  cat > "$CONF/lines.yaml" <<EOF
cluster_name: oom-exp-c3
listen_address: 127.0.0.2
rpc_address: 127.0.0.2
seed_provider:
  - class_name: org.apache.cassandra.locator.SimpleSeedProvider
    parameters:
      - seeds: "127.0.0.2:7000"
data_file_directories:
    - $NODE/data
commitlog_directory: $NODE/commitlog
hints_directory: $NODE/hints
saved_caches_directory: $NODE/saved_caches
cdc_raw_directory: $NODE/cdc_raw
EOF
  python3 -I - "$CONF" <<'PY'
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
open(n + '/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- C3 lines (environment) ----\n' + '\n'.join(add) + '\n')
PY
  diff "$CH/conf/cassandra.yaml" "$CONF/cassandra.yaml" > "$D/cassandra.yaml.diff" || true; }

start_node() { local budget=$1 Lb=$2
  check "no daemon running" bash -c '! pgrep -f "[o]rg.apache.cassandra.service.CassandraDaemon" >/dev/null'
  check "ports free" bash -c '! ss -ltn | grep -qE "127.0.0.2:(7000|9042)|:7199\b"'
  make_conf
  local extra="-XX:NativeMemoryTracking=summary"
  [ "$Lb" != default ] && extra="$extra -Dcassandra.dob_max_recycle_bytes=$Lb"
  rm -rf "$NLOGS"; mkdir -p "$NLOGS"
  CASSANDRA_HOME=$CH CASSANDRA_CONF=$CONF CASSANDRA_LOG_DIR=$NLOGS CASSANDRA_HEAPDUMP_DIR=$D \
    MAX_HEAP_SIZE=$XMX HEAP_NEWSIZE= MAX_DIRECT_MEMORY_SIZE=${budget}M JVM_EXTRA_OPTS="$extra" \
    "$CH/bin/cassandra" -p "$NODE/cassandra.pid" > "$D/node-stdout.txt" 2>&1
  ready() { [ -n "$(node_pid)" ] || return 1; grep -q 'Starting listening for CQL clients' "$NLOGS/system.log" 2>/dev/null; }
  wait_for "CQL up" 300 ready
  PID=$(node_pid); tr '\0' '\n' < /proc/$PID/cmdline > "$D/jvm-args.txt"
  check "-Xmx$XMX" grep -qx -- "-Xmx$XMX" "$D/jvm-args.txt"
  check "one MaxDirectMemorySize=${budget}M" bash -c "[ \$(grep -c MaxDirectMemorySize '$D/jvm-args.txt') = 1 ] && grep -qx -- '-XX:MaxDirectMemorySize=${budget}M' '$D/jvm-args.txt'"
  if [ "$Lb" = default ]; then check "dob_max_recycle_bytes unset" bash -c "! grep -q dob_max_recycle '$D/jvm-args.txt'"
  else check "dob_max_recycle_bytes=$Lb" grep -qx -- "-Dcassandra.dob_max_recycle_bytes=$Lb" "$D/jvm-args.txt"; fi
  "$CH/bin/cqlsh" 127.0.0.2 --request-timeout=60 -e "
    CREATE KEYSPACE c3ks WITH replication = {'class':'SimpleStrategy','replication_factor':1};
    CREATE TABLE c3ks.t (key blob PRIMARY KEY, \"C0\" blob);" > "$D/cqlsh-schema.txt" 2>&1 || fail "schema"
  ( cd "$BASE/tools" && exec java -cp . DirectPoll $JMX 250 ) > "$D/samples.tsv" 2> "$D/poll.err" & POLLPID=$!
  note "node pid $PID: -Xmx$XMX MaxDirectMemorySize=${budget}M dob_max_recycle_bytes=$Lb; poller $POLLPID"; sleep 5; }

# ------------------------------------------------------------ instruments
last() { tail -1 "$D/samples.tsv" 2>/dev/null | awk '{printf "directMiB=%.1f count=%d threads=%d heapMiB=%.0f", $2/1048576, $3, $4, $5/1048576}'; }
nmt() { jcmd "$PID" VM.native_memory summary 2>/dev/null | grep -A1 -E '^-\s+Other' | grep -Eo 'committed=[0-9]+KB' | head -1 || true; }
point() { local tag=$1
  [ -r "/proc/$PID/status" ] || { note "p $tag: NODE GONE"; return 1; }
  sleep 1; note "p $tag $(date +%T): $(last) nmtOther=$(nmt) rssAnonKB=$(awk '/^RssAnon/{print $2}' /proc/$PID/status)"; }
sep_workers() { local tag=$1; local f="$D/jstack-$tag.txt"
  jstack "$PID" > "$f" 2>/dev/null || { note "jstack $tag failed"; return 0; }
  local ids; ids=$(grep -oE '^"(ReadStage|MutationStage|CounterMutationStage|ViewMutationStage|RequestResponseStage|Native-Transport-Requests|Native-Transport-Auth-Requests|SharedPool-Worker)-[0-9]+"' "$f" | grep -oE '[0-9]+"$' | sort -u | wc -l)
  note "sep $tag: SEP worker threads (distinct ids)=$ids; by last stage: $(grep -oE '^"(ReadStage|MutationStage|CounterMutationStage|ViewMutationStage|RequestResponseStage|Native-Transport-Requests|Native-Transport-Auth-Requests|SharedPool-Worker)-' "$f" | sort | uniq -c | tr -s ' ' | tr '\n' ' ')"; }
dump() { local tag=$1
  local t0=$SECONDS; jcmd "$PID" GC.heap_dump "$D/$tag.hprof" > "$D/dump-$tag.txt" 2>&1 || { note "dump failed"; return 0; }
  note "dump $tag: $(ls -la "$D/$tag.hprof" | awk '{print $5}') B in $((SECONDS - t0)) s"; point "after-dump-$tag" || true; }
analyse() { local h=$1; local out=$2
  HPROF_LARGE=524288 python3 -I "$BASE/tools/hprof_direct.py" "$h" 30 > "$out" 2> "$out.err" || note "analysis failed ($h)"
  note "hprof $(basename "$h"): $(grep -E 'DOB thread-local scratch' "$out" | head -1 | tr -s ' ') | $(grep -E 'memory owners charged' "$out" | grep -Eo 'capacity sum [0-9]+ B = [0-9.]+ MiB' | head -1) | $(grep -E 'threads by pool' "$out" | head -1 | tr -s ' ')"; }

# ------------------------------------------------------------ workloads
profile() { local name=$1 size=$2
  cat > "$D/$name.yaml" <<EOF
# C3 $name: one $size-byte blob per partition into the pre-created c3ks.t (no schema statements)
keyspace: c3ks
table: t
columnspec:
  - name: key
    size: fixed(10)
    population: seq(1..100000000)
  - name: C0
    size: fixed($size)
insert:
  partitions: fixed(1)
  batchtype: UNLOGGED
  select: fixed(1)/1
queries:
  read1:
    cql: select * from t where key = ?
    fields: samerow
EOF
}
stress() { CASSANDRA_HOME=$CH "$CH/tools/bin/cassandra-stress" "$@" -node 127.0.0.2 -port native=9042 jmx=$JMX -mode native cql3 protocolVersion=4; }
# run_load <tag> <profile> <n_total> <threads_per_proc> <procs> <key_offset> <cap_s>
run_load() { local tag=$1 prof=$2 n=$3 th=$4 procs=$5 off=$6 cap=$7 i pids=()
  local per=$(( n / procs ))
  log "+ $tag: $n x $prof over $procs process(es) x $th threads"
  for i in $(seq 0 $((procs - 1))); do
    local a=$(( off + i * per + 1 )) b=$(( off + (i + 1) * per ))
    timeout --signal=INT "$cap" bash -c "$(declare -f stress); CH=$CH; JMX=$JMX; stress user profile=$D/$prof.yaml 'ops(insert=1)' n=$per cl=ONE no-warmup -pop seq=$a..$b -errors retries=3 -rate threads=$th" > "$D/stress-$tag-$i.txt" 2>&1 &
    pids+=($!); done
  local rc=0; for p in "${pids[@]}"; do wait "$p" || rc=1; done
  note "$tag clients: rc=$rc $(for i in $(seq 0 $((procs - 1))); do grep -E 'Total partitions|Total errors|Op rate' "$D/stress-$tag-$i.txt" | tr -s ' ' | tr '\n' '|'; echo -n ' ;; '; done)"; }
clients() { ss -tn state established "( sport = :9042 )" 2>/dev/null | awk 'NR>1{split($4,a,":"); print a[1]}' | sort | uniq -c | tr -s ' ' | tr '\n' ' '; }
window() { local from=$1 to=$2 tag=$3   # peak/min direct between two epoch-ms marks
  awk -v a="$from" -v b="$to" -v t="$tag" '$1>=a && $1<=b {n++; if($2>mx){mx=$2; tm=$1}; if(mn==""||$2<mn)mn=$2; if($3>mc)mc=$3} END{printf "window %s: samples=%d peakDirectMiB=%.1f (at %d) minMiB=%.1f peakCount=%d\n", t, n, mx/1048576, tm, mn/1048576, mc}' "$D/samples.tsv" | tee -a "$S"; }
now_ms() { date +%s%3N; }

cmd_arm() { local name=$1 budget=$2 Lb=$3 fc=$4 fips=$5 burst=$6 dmp=${7:-nodump}
  D=$LOGS/$name; mkdir -p "$LOGS"; [ -e "$D" ] && mv "$D" "$D.attempt-$(date +%s)"; mkdir -p "$D"; S=$D/summary.txt
  exec > >(tee -a "$D/session.log") 2>&1; log "script: $0 arm $*"; log "host: $(hostname)"
  note "arm $name: direct=${budget}M L=$Lb fill=${FILL_N}x${FILL_SIZE}B threads=$fc ips=$fips burst=$burst dump=$dmp"
  start_node "$budget" "$Lb"; local alive=1
  point idle1; sleep 10; point idle2 || alive=0; sep_workers idle
  profile fill "$FILL_SIZE"
  [ "$fips" -gt 1 ] && snat_on
  local t0; t0=$(now_ms)
  ( while sleep 10; do echo "[$(date +%T)] clients by source: $(clients)"; done ) > "$D/clients.txt" 2>&1 & local cpid=$!
  run_load fill fill "$FILL_N" $(( fc / fips )) "$fips" 0 "$FILL_SECS" || true
  local t1; t1=$(now_ms); window "$t0" "$t1" fill
  node_up || alive=0
  if [ $alive = 1 ]; then sleep "$IDLE"; point retained || alive=0; fi
  [ $alive = 1 ] && sep_workers retained
  [ $alive = 1 ] && [ "$dmp" = dump ] && dump retained
  nt tablestats c3ks.t > "$D/tablestats-retained.txt" 2>&1 || true
  [ $alive = 1 ] && note "server writes after fill: $(grep -E 'Write Count' "$D/tablestats-retained.txt" | tr -s ' ')"
  if [ $alive = 1 ] && [ "$burst" != none ]; then
    # amendment 2026-11-12 (after calibration b8m): flush c3ks before the burst so the 2 GiB heap is not
    # already holding the fill's memtable (the b8m calibration died of Java heap OOM); same in every arm
    local f0=$SECONDS; nt flush c3ks > "$D/flush.txt" 2>&1 || true; note "flush c3ks before burst: $((SECONDS - f0)) s"
    point post-flush || alive=0; sep_workers post-flush
  fi
  if [ $alive = 1 ] && [ "$burst" != none ]; then
    IFS=: read -r bsize bn bth bips <<< "$burst"; profile burst "$bsize"
    if [ "$bips" -gt 1 ] && [ "$fips" -le 1 ]; then snat_on; fi
    if [ "$bips" -le 1 ] && [ "$fips" -gt 1 ]; then snat_off; fi
    point pre-burst || alive=0
    local b0; b0=$(now_ms)
    [ $alive = 1 ] && { run_load burst burst "$bn" "$bth" "$bips" 50000000 "$BURST_SECS" || true; }
    local b1; b1=$(now_ms); window "$b0" "$b1" burst
    node_up || alive=0
    if [ $alive = 1 ]; then sleep "$HOLD"; point after-burst || alive=0; fi
  fi
  kill "$cpid" 2>/dev/null || true
  window 0 99999999999999 whole-run
  nt tablestats c3ks.t > "$D/tablestats-end.txt" 2>&1 || true
  cp "$NLOGS/system.log" "$D/system.log" 2>/dev/null || true; cp "$NLOGS/gc.log"* "$D/" 2>/dev/null || true
  grep -c '^ERROR' "$D/system.log" > "$D/error-count.txt" 2>/dev/null || echo 0 > "$D/error-count.txt"
  grep -E '^ERROR' "$D/system.log" | head -20 > "$D/error-lines.txt" || true
  grep -hE 'java.lang.OutOfMemoryError' "$D/node-stdout.txt" "$D/system.log" 2>/dev/null | head -10 > "$D/oom-lines.txt" || true
  grep -n -m1 -A40 'OutOfMemoryError: Direct buffer memory' "$D/system.log" > "$D/first-oom.txt" 2>/dev/null || true
  sudo -n dmesg -T 2>/dev/null | grep -E "Killed process|invoked oom-killer" | tail -5 > "$D/dmesg-kills-tail.txt" || true
  ls -la "$D"/*.hprof 2>/dev/null > "$D/hprof-list.txt" || true
  note "ERROR lines: $(cat "$D/error-count.txt"); OOM lines: $(wc -l < "$D/oom-lines.txt"); node alive at end: $(node_up && echo yes || echo NO)"
  pkill -f '[o]rg.apache.cassandra.stress.Stress' 2>/dev/null || true
  for p in $(node_pid); do nt stopdaemon >/dev/null 2>&1 || true; for _ in $(seq 60); do node_up || break; sleep 1; done; node_up && kill -9 "$p" 2>/dev/null || true; done
  kill "$POLLPID" 2>/dev/null || true; POLLPID=""
  for _ in $(seq 60); do any_daemon || break; sleep 1; done
  check "SNAT removed" snat_off
  check "no daemon left" bash -c '! pgrep -f "[o]rg.apache.cassandra.service.CassandraDaemon" >/dev/null'
  check "no stress left" bash -c '! pgrep -f "[o]rg.apache.cassandra.stress.Stress" >/dev/null'
  for h in "$D"/*.hprof; do [ -e "$h" ] && analyse "$h" "${h%.hprof}-analysis.txt"; done
  rm -rf "$NODE/data" "$NODE/commitlog"
  log "ARM $name DONE"; }
case "${1:-}" in arm) shift; cmd_arm "$@" ;; *) echo "usage: $0 arm <name> <direct_MiB> <L|default> <fill_threads> <fill_ips> <burst|none> [dump]"; exit 2 ;; esac
