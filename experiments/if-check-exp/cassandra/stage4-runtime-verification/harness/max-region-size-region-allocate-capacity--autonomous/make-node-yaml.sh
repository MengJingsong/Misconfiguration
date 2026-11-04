#!/usr/bin/env bash
# usage: make-node-yaml.sh [yaml_key=value ...]   (cluster tier B3a of max-region-size-region-allocate-capacity--autonomous, port slot 4)
# Builds $MO/conf from the tree's conf/: the tag's cassandra.yaml with this node's lines (cluster name, loopback address 127.0.4.1,
# default ports, 4 tokens, SimpleSnitch, seed 127.0.4.1:7000, directories under $MO on tmpfs, and the B3a lines as amended 2026-10-26 (memtable_heap_space 256MiB, offheap 64MiB default)),
# then the arm's key=value arguments, which replace a line of the same key. cassandra-env.sh JMX_PORT = 7140 (local JMX, binds 127.0.0.1).
# Nothing in the tree is changed. Pattern from the memtable-offheap-space harness.
set -euo pipefail
C=${CASSANDRA_HOME:-$HOME/s4-b7-mr}; MO=${MO:-/dev/shm/s4-b7-mr}; addr=127.0.4.1; jmx=7140
mkdir -p "$MO/logs" "$MO/data" "$MO/commitlog" "$MO/hints" "$MO/saved_caches" "$MO/cdc_raw"
rm -rf "$MO/conf"; cp -r "$C/conf" "$MO/conf"
git -C "$C" show HEAD:conf/cassandra-env.sh > "$MO/conf/cassandra-env.sh"
sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$jmx\"/" "$MO/conf/cassandra-env.sh"
grep -q "^JMX_PORT=\"$jmx\"" "$MO/conf/cassandra-env.sh" || { echo "JMX_PORT line not replaced" >&2; exit 1; }
git -C "$C" show HEAD:conf/jvm11-server.options > "$MO/conf/jvm11-server.options"
declare -A kv=( [memtable_allocation_type]=offheap_objects [memtable_offheap_space]=64MiB [memtable_heap_space]=256MiB
  [memtable_flush_writers]=1 [memtable_cleanup_threshold]=0.99 [commitlog_total_space]=4096MiB [file_cache_size]=64MiB
  [key_cache_size]=0MiB [row_cache_size]=0MiB [concurrent_compactors]=1 [compaction_throughput]=16MiB/s
  [write_request_timeout]=30000ms [native_transport_timeout]=60000ms )
order=(memtable_allocation_type memtable_offheap_space memtable_heap_space memtable_flush_writers memtable_cleanup_threshold commitlog_total_space file_cache_size key_cache_size row_cache_size concurrent_compactors compaction_throughput write_request_timeout native_transport_timeout)
for a in "$@"; do k=${a%%=*}; [ -n "${kv[$k]+x}" ] || order+=("$k"); kv[$k]=${a#*=}; done
{
  echo "cluster_name: stage4-mr"; echo "num_tokens: 4"; echo "endpoint_snitch: SimpleSnitch"
  echo "listen_address: $addr"; echo "rpc_address: $addr"; echo "storage_port: 7000"; echo "native_transport_port: 9042"
  echo "seed_provider:"; echo "  - class_name: org.apache.cassandra.locator.SimpleSeedProvider"; echo "    parameters:"; echo "      - seeds: \"$addr:7000\""
  echo "data_file_directories:"; echo "    - $MO/data"
  echo "commitlog_directory: $MO/commitlog"; echo "hints_directory: $MO/hints"; echo "saved_caches_directory: $MO/saved_caches"; echo "cdc_raw_directory: $MO/cdc_raw"
  for k in "${order[@]}"; do echo "$k: ${kv[$k]}"; done
} > "$MO/lines.yaml"
git -C "$C" show HEAD:conf/cassandra.yaml > "$MO/shipped.yaml"
python3 -I - "$MO" <<'PY'
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
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 mr lines ----\n' + '\n'.join(add) + '\n')
PY
echo "node: conf $MO/conf, JMX $jmx, address $addr; yaml tail:"
sed -n '/^# ---- stage4 mr lines/,$p' "$MO/conf/cassandra.yaml" | grep -v '^ *- \|^ *parameters\|class_name' | tr '\n' ';' ; echo
