#!/usr/bin/env bash
# usage: make-node-yaml.sh [yaml_key=value ...]   (cluster tier B3a of cache-keys-to-save-writer-keysToSave--autonomous, port slot 5)
# Builds $CK/conf from the tree's conf/: the tag's cassandra.yaml with this node's lines (loopback address 127.0.5.1, default ports,
# JMX_PORT 7150, directories under $CK on tmpfs, caches as B3a/B3h: row_cache_size 0, counter_cache_size 0, key_cache_save_period 1h),
# then the arm's key=value arguments, which replace a line of the same key. Nothing in the tree is changed.
# Pattern from the max-cloned-size-allocate-size harness (same batch).
set -euo pipefail
C=${CASSANDRA_HOME:-$HOME/s4-b7-ck-n}; CK=${CK:-/dev/shm/s4-b7-ck}; addr=127.0.5.1; jmx=7150
mkdir -p "$CK/logs" "$CK/data" "$CK/commitlog" "$CK/hints" "$CK/saved_caches" "$CK/cdc_raw"
rm -rf "$CK/conf"; cp -r "$C/conf" "$CK/conf"
git -C "$C" show HEAD:conf/cassandra-env.sh > "$CK/conf/cassandra-env.sh"
sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$jmx\"/" "$CK/conf/cassandra-env.sh"
grep -q "^JMX_PORT=\"$jmx\"" "$CK/conf/cassandra-env.sh" || { echo "JMX_PORT line not replaced" >&2; exit 1; }
git -C "$C" show HEAD:conf/jvm11-server.options > "$CK/conf/jvm11-server.options"
declare -A kv=( [key_cache_size]=200MiB [key_cache_save_period]=1h [row_cache_size]=0MiB [counter_cache_size]=0MiB
  [commitlog_total_space]=4096MiB [auto_snapshot]=false [concurrent_compactors]=2 )
order=(key_cache_size key_cache_save_period row_cache_size counter_cache_size commitlog_total_space auto_snapshot concurrent_compactors)
for a in "$@"; do k=${a%%=*}; [ -n "${kv[$k]+x}" ] || order+=("$k"); kv[$k]=${a#*=}; done
{
  echo "cluster_name: stage4-ck"; echo "num_tokens: 4"; echo "endpoint_snitch: SimpleSnitch"
  echo "listen_address: $addr"; echo "rpc_address: $addr"; echo "storage_port: 7000"; echo "native_transport_port: 9042"
  echo "seed_provider:"; echo "  - class_name: org.apache.cassandra.locator.SimpleSeedProvider"; echo "    parameters:"; echo "      - seeds: \"$addr:7000\""
  echo "data_file_directories:"; echo "    - $CK/data"
  echo "commitlog_directory: $CK/commitlog"; echo "hints_directory: $CK/hints"; echo "saved_caches_directory: $CK/saved_caches"; echo "cdc_raw_directory: $CK/cdc_raw"
  for k in "${order[@]}"; do echo "$k: ${kv[$k]}"; done
} > "$CK/lines.yaml"
git -C "$C" show HEAD:conf/cassandra.yaml > "$CK/shipped.yaml"
python3 -I - "$CK" <<'PY'
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
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 ck lines ----\n' + '\n'.join(add) + '\n')
PY
echo "node: conf $CK/conf, JMX $jmx, address $addr; yaml tail:"
sed -n '/^# ---- stage4 ck lines/,$p' "$CK/conf/cassandra.yaml" | grep -v '^ *- \|^ *parameters\|class_name' | tr '\n' ';' ; echo
