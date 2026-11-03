#!/usr/bin/env bash
# OOM-exp convergence case: commitlog_total_space + max_hints_size_per_host,
# shared budget = disk (a dedicated small loop-mounted ext4 filesystem standing
# in for "the disk", the same role -Xmx played for the heap cases).
#
# Topology: two Cassandra nodes on one physical host, loopback addresses
# 127.0.0.2 (N1, the node under test — commitlog + hints directories live on
# the small mount) and 127.0.0.3 (N2, a plain replica on normal local disk
# that we stop to make N1 hint for it). RF=2 SimpleStrategy keyspace so every
# write replicates to both.
#
# Usage:
#   oom-run.sh ring-up                         start both nodes fresh, create keyspace
#   oom-run.sh ring-down                       stop both nodes, verify none left
#   oom-run.sh baseline                        idle disk usage on N1's mount (both nodes up)
#   oom-run.sh arm commitlog_alone             N2 stays up; fast write; commitlog_total_space=800MiB target
#   oom-run.sh arm hints_alone                 N2 stopped first; slow/throttled write; max_hints_size_per_host=900MiB target
#   oom-run.sh arm converge                    N2 stopped first; fast write; both targets set
#
# Logs every command to ~/oom-exp-disk-run3/logs/<name>/session.log; readings to <name>/summary.txt.
set -Eeuo pipefail

CH=$HOME/cassandra-run1              # CASSANDRA_HOME, shared build, both nodes
BASE=$HOME/oom-disk-run3
MNT=$BASE/mnt
N1DIR=$MNT/N1                        # on the small loop-mounted disk budget
N2DIR=$BASE/N2                       # on normal local disk — not part of the tested budget
N1CONF=$BASE/N1-conf
N2CONF=$BASE/N2-conf
N1LOGS=$BASE/N1-logs                 # outside the mount: logs must not count against the disk budget
N2LOGS=$BASE/N2-logs
L=$BASE/logs
XMX=1024M  # 512M genuinely OOM'd on heap under 256-thread write load (unrelated to the disk budget under test); the closed heap cases ran the same write shape safely at 1024M
D=""; S=""

log()  { echo "[$(date '+%F %T')] $*" >&2; }
note() { printf '%s\n' "$*" | tee -a "$S"; }
fail() { log "FAIL: $*"; exit 1; }
now()  { date +%s%3N; }
run()  { log "+ $*"; "$@"; local rc=$?; log "  rc=$rc"; return $rc; }
runto(){ local f=$1; shift; log "+ $* > $f"; local rc=0; "$@" > "$f" 2>&1 || rc=$?
  log "  rc=$rc ($(wc -l < "$f") lines in $f)"; return $rc; }
check(){ local d=$1; shift; if "$@"; then log "CHECK PASS: $d"; else fail "CHECK FAILED: $d"; fi; }
wait_for() { local d=$1 t=$2 i=0; shift 2
  until "$@"; do sleep 1; i=$((i+1)); [ "$i" -ge "$t" ] && fail "timeout ${t}s waiting for: $d"; done
  log "ok: $d (after ${i}s)"; }

start_log() { mkdir -p "$L"; if [ -e "$D" ] && [ -n "$(ls -A "$D" 2>/dev/null)" ]; then mv "$D" "$D.attempt-$(date +%s)"; fi
  mkdir -p "$D"; S=$D/summary.txt; exec > >(tee -a "$D/session.log") 2>&1
  log "script: $0 $*"; log "host: $(hostname)"; }

n1_up() { [ -f "$N1DIR/cassandra.pid" ] && kill -0 "$(cat "$N1DIR/cassandra.pid")" 2>/dev/null; }
n2_up() { [ -f "$N2DIR/cassandra.pid" ] && kill -0 "$(cat "$N2DIR/cassandra.pid")" 2>/dev/null; }
n1_down() { ! n1_up; }
n2_down() { ! n2_up; }
no_daemon_left() { ! pgrep -f '[o]rg.apache.cassandra.service.CassandraDaemon' >/dev/null; }

# Nodes are meant to PERSIST across separate invocations of this script
# (ring-up starts them; baseline/arm commands run while they're up; ring-down
# stops them). The EXIT trap is a safety net for a crashed/interrupted
# invocation ONLY — it must not tear down a healthy ring on normal exit, or
# every command would kill the ring it just needed.
cleanup() {
  local rc=$?; trap - EXIT
  if [ "$rc" -ne 0 ]; then
    log "EXIT rc=$rc: stopping stress (safety net; nodes left as-is otherwise)"
    pkill -f '[o]rg.apache.cassandra.stress.Stress' 2>/dev/null || true
  fi
  exit "$rc"
}
trap 'log "ERR line $LINENO: $BASH_COMMAND"' ERR
trap cleanup EXIT

# -------------------------------------------------------- yaml generation
# make_yaml <conf_dir> <listen_addr> <data_dir> <commitlog_dir> <hints_dir> <saved_caches_dir> <cdc_raw_dir> <seed_addr> <token> key=val...
make_yaml() {
  local conf=$1 addr=$2 data=$3 cl=$4 hints=$5 caches=$6 cdc=$7 seed=$8 token=$9; shift 9
  mkdir -p "$data" "$cl" "$hints" "$caches" "$cdc"
  {
    echo "cluster_name: oom-exp-disk-run3"
    echo "num_tokens: 1"
    echo "initial_token: $token"
    echo "auto_bootstrap: false"
    echo "listen_address: $addr"
    echo "rpc_address: $addr"
    echo "broadcast_rpc_address: $addr"
    echo "seed_provider:"
    echo "  - class_name: org.apache.cassandra.locator.SimpleSeedProvider"
    echo "    parameters:"
    echo "      - seeds: \"$seed:7000\""
    echo "data_file_directories:"
    echo "    - $data"
    echo "commitlog_directory: $cl"
    echo "hints_directory: $hints"
    echo "saved_caches_directory: $caches"
    echo "cdc_raw_directory: $cdc"
    echo "max_hint_window: 24h"
    echo "hints_flush_period: 1000ms"
    for kv in "$@"; do echo "${kv%%=*}: ${kv#*=}"; done
  } > "$conf/lines.yaml"
  git -C "$CH" show HEAD:conf/cassandra.yaml > "$conf/shipped.yaml"
  python3 - "$conf" <<'PY'
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
open(n + '/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- disk-run3 lines ----\n' + '\n'.join(add) + '\n')
PY
}

configure_n1() { # commitlog_total_space=<X|-> max_hints_size_per_host=<Y|->
  local cls=${1:--} mhs=${2:--}
  # Carried over from the heap cases' own commitlog finding (if-check-exp's
  # commitlog_total_space case file: "Requires memtable_cleanup_threshold:
  # 0.99 to actually reach the limit, otherwise the default threshold
  # reclaims early") — without this, commit log never approaches its quota
  # and disk instead fills from frequent small-memtable flush output.
  local extra=("memtable_allocation_type=unslabbed_heap_buffers" "memtable_cleanup_threshold=0.99")
  [ "$cls" != "-" ] && extra+=("commitlog_total_space=${cls}MiB")
  [ "$mhs" != "-" ] && extra+=("max_hints_size_per_host=${mhs}MiB")
  make_yaml "$N1CONF" 127.0.0.2 "$N1DIR/data" "$N1DIR/commitlog" "$N1DIR/hints" "$N1DIR/saved_caches" "$N1DIR/cdc_raw" 127.0.0.2 -9223372036854775808 "${extra[@]}"
  note "N1 yaml extra: ${extra[*]:-none}"
}
configure_n2() {
  make_yaml "$N2CONF" 127.0.0.3 "$N2DIR/data" "$N2DIR/commitlog" "$N2DIR/hints" "$N2DIR/saved_caches" "$N2DIR/cdc_raw" 127.0.0.2 0
}

# -------------------------------------------------------- start/stop
start_n1() {
  check "ports free (N1)" bash -c '! ss -ltn | grep -q "127.0.0.2:7000\|127.0.0.2:9042"'
  rm -rf "$N1DIR"/data/* "$N1DIR"/commitlog/* "$N1DIR"/hints/* "$N1DIR"/saved_caches/* "$N1DIR"/cdc_raw/* "$N1DIR/cassandra.pid"
  mkdir -p "$N1LOGS"; if [ -n "$(ls -A "$N1LOGS" 2>/dev/null)" ]; then mkdir -p "$D/prev-n1-logs"; mv "$N1LOGS"/* "$D/prev-n1-logs/" 2>/dev/null || true; fi
  export CASSANDRA_HOME=$CH CASSANDRA_CONF=$N1CONF CASSANDRA_LOG_DIR=$N1LOGS MAX_HEAP_SIZE=$XMX
  unset HEAP_NEWSIZE || true
  log "+ bin/cassandra -p $N1DIR/cassandra.pid (N1, 127.0.0.2) > $D/n1-stdout.txt 2>&1"
  "$CH/bin/cassandra" -p "$N1DIR/cassandra.pid" > "$D/n1-stdout.txt" 2>&1
  n1_ready() { [ -s "$N1DIR/cassandra.pid" ] || return 1
    kill -0 "$(cat "$N1DIR/cassandra.pid")" 2>/dev/null || fail "N1 died during startup (see $D/n1-stdout.txt)"
    grep -q 'Starting listening for CQL clients' "$N1LOGS/system.log" 2>/dev/null; }
  wait_for "N1 listening for CQL clients" 300 n1_ready
  unset CASSANDRA_HOME CASSANDRA_CONF CASSANDRA_LOG_DIR MAX_HEAP_SIZE
  note "N1 pid $(cat "$N1DIR/cassandra.pid")"
  grep -E 'commitlog_total_space|Total commit log size|max_hints_size_per_host|hints size' "$N1LOGS/system.log" > "$D/n1-startup-lines.txt" 2>/dev/null || true
}
start_n2() {
  check "ports free (N2)" bash -c '! ss -ltn | grep -q "127.0.0.3:7000\|127.0.0.3:9042"'
  rm -rf "$N2DIR"/data/* "$N2DIR"/commitlog/* "$N2DIR"/hints/* "$N2DIR"/saved_caches/* "$N2DIR"/cdc_raw/* "$N2DIR/cassandra.pid"
  mkdir -p "$N2LOGS"; if [ -n "$(ls -A "$N2LOGS" 2>/dev/null)" ]; then mkdir -p "$D/prev-n2-logs"; mv "$N2LOGS"/* "$D/prev-n2-logs/" 2>/dev/null || true; fi
  export CASSANDRA_HOME=$CH CASSANDRA_CONF=$N2CONF CASSANDRA_LOG_DIR=$N2LOGS MAX_HEAP_SIZE=$XMX
  unset HEAP_NEWSIZE || true
  log "+ bin/cassandra -p $N2DIR/cassandra.pid (N2, 127.0.0.3) > $D/n2-stdout.txt 2>&1"
  "$CH/bin/cassandra" -p "$N2DIR/cassandra.pid" > "$D/n2-stdout.txt" 2>&1
  n2_ready() { [ -s "$N2DIR/cassandra.pid" ] || return 1
    kill -0 "$(cat "$N2DIR/cassandra.pid")" 2>/dev/null || fail "N2 died during startup (see $D/n2-stdout.txt)"
    grep -q 'Starting listening for CQL clients' "$N2LOGS/system.log" 2>/dev/null; }
  wait_for "N2 listening for CQL clients" 300 n2_ready
  unset CASSANDRA_HOME CASSANDRA_CONF CASSANDRA_LOG_DIR MAX_HEAP_SIZE
  note "N2 pid $(cat "$N2DIR/cassandra.pid")"
}
stop_n1() {
  if n1_up; then
    CASSANDRA_HOME=$CH CASSANDRA_CONF=$N1CONF "$CH/bin/nodetool" -h 127.0.0.1 -p 7199 drain >/dev/null 2>&1 || true
    sleep 1
    kill "$(cat "$N1DIR/cassandra.pid" 2>/dev/null)" 2>/dev/null || true
    for _ in $(seq 60); do n1_up || break; sleep 1; done
  fi
  if n1_up; then kill -9 "$(cat "$N1DIR/cassandra.pid")" 2>/dev/null || true; sleep 1; fi
  check "N1 stopped" n1_down || true
}
stop_n2() {
  if n2_up; then
    CASSANDRA_HOME=$CH CASSANDRA_CONF=$N2CONF "$CH/bin/nodetool" -h 127.0.0.1 -p 7200 drain >/dev/null 2>&1 || true
    sleep 1
    kill "$(cat "$N2DIR/cassandra.pid" 2>/dev/null)" 2>/dev/null || true
    for _ in $(seq 60); do n2_up || break; sleep 1; done
  fi
  if n2_up; then kill -9 "$(cat "$N2DIR/cassandra.pid")" 2>/dev/null || true; sleep 1; fi
}
kill_n2_hard() { # simulate "replica goes down" without a graceful drain (so it stays a plausible replica, not decommissioned)
  if n2_up; then kill -9 "$(cat "$N2DIR/cassandra.pid")" 2>/dev/null || true; sleep 1; fi
}

disk_usage() { # tag -> prints and records N1 mount usage
  local tag=$1
  local used total bytes
  bytes=$(du -sb "$N1DIR" 2>/dev/null | awk '{print $1}')
  echo "$bytes" > "$D/n1-disk-bytes-$tag.txt"
  df -B1 "$MNT" > "$D/mount-df-$tag.txt" 2>&1 || true
  local cl_bytes hints_bytes
  cl_bytes=$(du -sb "$N1DIR/commitlog" 2>/dev/null | awk '{print $1}')
  hints_bytes=$(du -sb "$N1DIR/hints" 2>/dev/null | awk '{print $1}')
  note "disk $tag: N1-total=${bytes}B ($(awk "BEGIN{printf \"%.1f\", $bytes/1048576}")MiB) commitlog=${cl_bytes}B hints=${hints_bytes}B mount=$(df -h "$MNT" | tail -1 | awk '{print $3"/"$2" ("$5" used)"}')"
}

# -------------------------------------------------------- fresh ring per command
# Every command below (baseline, each arm) brings up a COMPLETELY FRESH ring —
# both N1 and N2 wiped and restarted — rather than reusing nodes across
# invocations. Wiping only N1 between arms while N2 kept running would corrupt
# gossip state (N1 would restart with a fresh host ID/system keyspace while
# N2 still remembers the old incarnation at the same address); wiping both
# together, every time, avoids that and matches the heap cases' own
# "fresh node per arm" convention.
fresh_ring_up() { # commitlog_total_space=<X|-> max_hints_size_per_host=<Y|->
  configure_n1 "$1" "$2"
  configure_n2
  stop_n1; stop_n2
  start_n1
  start_n2
  CASSANDRA_HOME=$CH CASSANDRA_CONF=$N1CONF "$CH/bin/nodetool" -h 127.0.0.1 -p 7199 status > "$D/status-before-ks.txt" 2>&1 || true
  cat "$D/status-before-ks.txt"
  wait_for "both nodes UN" 60 bash -c "CASSANDRA_HOME=$CH CASSANDRA_CONF=$N1CONF $CH/bin/nodetool -h 127.0.0.1 -p 7199 status 2>/dev/null | grep -c '^UN' | grep -q 2"
}
ring_down() {
  stop_n1; stop_n2
  # pidfiles can disappear well before the JVM actually finishes exiting —
  # graceful JVM shutdown (netty, GC/JFR threads, etc.) can take tens of
  # seconds — so give pgrep's stricter check the same ~60s budget the heap
  # cases' own stop_node loop uses, not a short one.
  wait_for "no CassandraDaemon left" 60 no_daemon_left
}

cmd_baseline() {
  D=$L/baseline; start_log
  fresh_ring_up - -
  sleep 5
  disk_usage idle
  ring_down
  log "BASELINE DONE"
}

# -------------------------------------------------------- arms
# -schema replication(factor=2) makes cassandra-stress create its own
# "standard1" table with RF=2 (matching the fresh ring's 2 nodes) instead of
# the keyspace1 default RF=1 — every write then replicates to both N1 and N2.
SCHEMA_RF2="keyspace=ks replication(strategy=SimpleStrategy,factor=2)"

cmd_arm() {
  local name=$1
  D=$L/$name; start_log "$@"
  case "$name" in
    commitlog_alone)
      fresh_ring_up 800 -
      note "== arm $name: N2 stays UP throughout (zero hints expected); commitlog_total_space=800MiB target, max_hints_size_per_host left at default (0=disabled)"
      disk_usage idle
      log "+ cassandra-stress write (fast, no throttle) against N1 while N2 is up"
      CASSANDRA_HOME=$CH CASSANDRA_CONF=$N1CONF "$CH/tools/bin/cassandra-stress" write n=1000000 no-warmup cl=ONE -col 'size=FIXED(1024)' -rate threads=256 -node 127.0.0.2 -schema "$SCHEMA_RF2" > "$D/stress.txt" 2>&1 &
      local SP=$!
      ;;
    hints_alone)
      fresh_ring_up - 900
      note "== arm $name: N2 killed right after the ring forms, before any write (hints accumulate); commitlog_total_space left at its shipped default (not the 800MiB target — not what's under test here); max_hints_size_per_host=900MiB target"
      disk_usage idle
      kill_n2_hard
      note "N2 killed (hard, simulating a replica outage): $(date)"
      log "+ cassandra-stress write (slow, throttled 200/s, 5KiB rows) against N1 while N2 is down"
      CASSANDRA_HOME=$CH CASSANDRA_CONF=$N1CONF "$CH/tools/bin/cassandra-stress" write n=210000 no-warmup cl=ONE -col 'size=FIXED(5120)' -rate 'threads=4 throttle=200/s' -node 127.0.0.2 -schema "$SCHEMA_RF2" > "$D/stress.txt" 2>&1 &
      local SP=$!
      ;;
    converge)
      fresh_ring_up 800 900
      note "== arm $name: N2 killed right after the ring forms, before any write; commitlog_total_space=800MiB AND max_hints_size_per_host=900MiB, both at their control-arm target values"
      disk_usage idle
      kill_n2_hard
      note "N2 killed (hard): $(date)"
      log "+ cassandra-stress write (fast, no throttle) against N1 while N2 is down"
      CASSANDRA_HOME=$CH CASSANDRA_CONF=$N1CONF "$CH/tools/bin/cassandra-stress" write n=1000000 no-warmup cl=ONE -col 'size=FIXED(1024)' -rate threads=256 -node 127.0.0.2 -schema "$SCHEMA_RF2" > "$D/stress.txt" 2>&1 &
      local SP=$!
      ;;
    *) fail "unknown arm $name" ;;
  esac

  local i=0 crashed=0
  for i in $(seq 1 90); do
    sleep 5
    if n1_up; then
      disk_usage "s$i"
    else
      note "sample $i: N1 process is GONE"
      crashed=1
      break
    fi
    kill -0 "$SP" 2>/dev/null || { note "stress finished after sample $i"; break; }
  done
  [ -n "${SP:-}" ] && wait "$SP" 2>/dev/null || true

  if n1_up; then disk_usage final; else note "N1 process is GONE at end — skip final disk_usage (filesystem may still be reachable, see mount-df)"; df -h "$MNT" > "$D/mount-df-final.txt" 2>&1 || true; fi
  grep -c '^ERROR' "$N1LOGS/system.log" > "$D/error-count.txt" 2>&1 || echo 0 > "$D/error-count.txt"
  grep '^ERROR' "$N1LOGS/system.log" > "$D/error-lines.txt" 2>&1 || true
  grep -iE 'No space left on device|FSWriteError|disk_failure_policy|CassandraDaemon.stop|JVMStabilityInspector' "$N1LOGS/system.log" > "$D/disk-fail-grep.txt" 2>/dev/null || true
  note "ERROR lines in N1 system.log: $(cat "$D/error-count.txt")"
  note "disk-fail-grep hits: $(wc -l < "$D/disk-fail-grep.txt")"
  sudo dmesg -T 2>/dev/null | grep -iE 'out of memory|oom-kill|killed process|No space left|ENOSPC' > "$D/dmesg-disk.txt" 2>&1 || true
  note "dmesg disk/oom lines: $(wc -l < "$D/dmesg-disk.txt")"

  ring_down
  log "ARM $name DONE (crashed=$crashed)"
}

case "${1:-}" in
  baseline) cmd_baseline ;;
  arm) shift; cmd_arm "$@" ;;
  *) echo "usage: $0 baseline|arm <commitlog_alone|hints_alone|converge>" >&2; exit 2 ;;
esac
