#!/usr/bin/env bash
# Shared node helpers for the stage-4 cluster tiers of the SASI hard-coded-constant cases (identical copy in each harness folder).
# Source it:   . "$HARN/lib.sh"      Variables: C (run copy), T (node dir), OUT (arm output dir).
C=${CASSANDRA_HOME:-$HOME/s4-b34/c}
ts() { date +%s%3N; }
daemons() { ps -eo pid,comm,args | awk '$2=="java" && /CassandraDaemon/' | wc -l; }

# mk_conf <T> <extra yaml file>: the node's conf = the run copy's conf with the keys in the extra file replacing the shipped ones.
mk_conf() {
  local T=$1 extra=$2
  mkdir -p "$T/logs" "$T/data" "$T/commitlog" "$T/hints" "$T/saved_caches" "$T/cdc_raw"
  rm -rf "$T/conf"; cp -r "$C/conf" "$T/conf"
  cp "$C/conf/cassandra.yaml" "$T/shipped.yaml"
  python3 - "$T" "$extra" <<'PY'
import re, sys
t, extra = sys.argv[1], sys.argv[2]
add = open(extra).read().splitlines()
keys = {l.split(':', 1)[0] for l in add if re.match(r'^[A-Za-z_]+:', l)}
out, skip = [], False
for l in open(t + '/shipped.yaml').read().splitlines():
    m = re.match(r'^([A-Za-z_]+):', l)
    if m:
        skip = m.group(1) in keys
        if skip: continue
    elif skip and (l.startswith((' ', '\t', '-')) or l.strip() == '' or l.lstrip().startswith('#')):
        continue
    else:
        skip = False
    out.append(l)
open(t + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 lines ----\n' + '\n'.join(add) + '\n')
PY
}

# base_yaml <T>: yaml lines common to every arm (single node, local dirs, SASI enabled, unthrottled compaction)
base_yaml() {
  local T=$1
  cat <<YAML
cluster_name: stage4-b34
num_tokens: 1
endpoint_snitch: SimpleSnitch
listen_address: 127.0.0.1
rpc_address: 127.0.0.1
seed_provider:
  - class_name: org.apache.cassandra.locator.SimpleSeedProvider
    parameters:
      - seeds: "127.0.0.1:7000"
data_file_directories:
    - $T/data
commitlog_directory: $T/commitlog
hints_directory: $T/hints
saved_caches_directory: $T/saved_caches
cdc_raw_directory: $T/cdc_raw
sasi_indexes_enabled: true
compaction_throughput: 0MiB/s
YAML
}

# start_node <T> <heap> <newsize> <jvm extra opts>: starts the daemon, waits for the native port; returns 1 if it dies.
start_node() {
  local T=$1
  CASSANDRA_CONF=$T/conf CASSANDRA_LOG_DIR=$T/logs MAX_HEAP_SIZE=$2 HEAP_NEWSIZE=$3 JVM_EXTRA_OPTS="$4" "$C/bin/cassandra" -p "$T/cassandra.pid" > "$T/stdout.txt" 2>&1
  local i s
  for i in $(seq 1 120); do
    s=$("$C/bin/nodetool" statusbinary 2>/dev/null | tr -d '\n'); [ "$s" = running ] && return 0
    pgrep -F "$T/cassandra.pid" >/dev/null 2>&1 || { echo "daemon died at start"; tail -30 "$T/stdout.txt"; return 1; }
    sleep 3
  done
  echo "node did not come up"; return 1
}

# stop_node <T>: drain, stop, wait, report leftover daemons
stop_node() {
  local T=$1 i
  "$C/bin/nodetool" drain > /dev/null 2>&1
  "$C/bin/nodetool" stopdaemon > /dev/null 2>&1
  for i in $(seq 1 60); do pgrep -F "$T/cassandra.pid" >/dev/null 2>&1 || break; sleep 2; done
  pgrep -F "$T/cassandra.pid" >/dev/null 2>&1 && { kill "$(cat "$T/cassandra.pid")"; sleep 5; }
  echo "daemons left: $(daemons)"
}

# bytes <path...>: du -sb total
bytes() { du -sb "$@" 2>/dev/null | awk '{s+=$1} END {print s+0}'; }

# disk_sampler <T> <stopfile> <csv>: every 2 s "epoch,datadir bytes,commitlog bytes,free KB on /"
disk_sampler() {
  local T=$1 stop=$2 csv=$3
  echo "epoch_ms,data_bytes,commitlog_bytes,free_kb" > "$csv"
  while [ ! -e "$stop" ]; do
    echo "$(ts),$(bytes "$T/data"),$(bytes "$T/commitlog"),$(df --output=avail / | tail -1 | tr -d ' ')" >> "$csv"; sleep 2
  done
}

# wait_one_sstable <keyspace.table> <timeout s>
wait_one_sstable() {
  local i n
  for i in $(seq 1 "${2:-3600}"); do
    n=$("$C/bin/nodetool" tablestats "$1" 2>/dev/null | awk -F: '/SSTable count/ {gsub(/ /,"",$2); print $2; exit}')
    [ "$n" = 1 ] && return 0; sleep 1
  done
  return 1
}
