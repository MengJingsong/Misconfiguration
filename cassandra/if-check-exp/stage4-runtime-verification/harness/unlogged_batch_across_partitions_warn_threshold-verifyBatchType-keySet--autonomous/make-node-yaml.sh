#!/usr/bin/env bash
# usage: make-node-yaml.sh [yaml_key=value ...]   (cluster tier B3a of unlogged_batch_across_partitions_warn_threshold-verifyBatchType-keySet--autonomous, port slot 4)
# Builds $BU/conf from the tree's conf/: the tag's cassandra.yaml with this node's lines (loopback 127.0.4.1, ports 7000/9042, JMX_PORT 7140,
# directories under $BU on tmpfs, size thresholds out of the way: batch_size_warn/fail 1000KiB), then the arm's key=value arguments, which replace
# a line of the same key. Nothing in the tree is changed. Pattern from the cache-keys-to-save-writer harness (same batch).
set -euo pipefail
C=${CASSANDRA_HOME:-$HOME/s4-b9-bu-node}; BU=${BU:-/dev/shm/s4-b9-bu}; addr=127.0.4.1; jmx=7140
mkdir -p "$BU/logs" "$BU/data" "$BU/commitlog" "$BU/hints" "$BU/saved_caches" "$BU/cdc_raw"
rm -rf "$BU/conf"; cp -r "$C/conf" "$BU/conf"
git -C "$C" show HEAD:conf/cassandra-env.sh > "$BU/conf/cassandra-env.sh"
sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$jmx\"/" "$BU/conf/cassandra-env.sh"
grep -q "^JMX_PORT=\"$jmx\"" "$BU/conf/cassandra-env.sh" || { echo "JMX_PORT line not replaced" >&2; exit 1; }
declare -A kv=( [batch_size_warn_threshold]=1000KiB [batch_size_fail_threshold]=1000KiB [auto_snapshot]=false )
order=(batch_size_warn_threshold batch_size_fail_threshold auto_snapshot)
for a in "$@"; do k=${a%%=*}; [ -n "${kv[$k]+x}" ] || order+=("$k"); kv[$k]=${a#*=}; done
{
  echo "cluster_name: stage4-bu"; echo "num_tokens: 4"; echo "endpoint_snitch: SimpleSnitch"
  echo "listen_address: $addr"; echo "rpc_address: $addr"; echo "storage_port: 7000"; echo "native_transport_port: 9042"
  echo "seed_provider:"; echo "  - class_name: org.apache.cassandra.locator.SimpleSeedProvider"; echo "    parameters:"; echo "      - seeds: \"$addr:7000\""
  echo "data_file_directories:"; echo "    - $BU/data"
  echo "commitlog_directory: $BU/commitlog"; echo "hints_directory: $BU/hints"; echo "saved_caches_directory: $BU/saved_caches"; echo "cdc_raw_directory: $BU/cdc_raw"
  for k in "${order[@]}"; do echo "$k: ${kv[$k]}"; done
} > "$BU/lines.yaml"
git -C "$C" show HEAD:conf/cassandra.yaml > "$BU/shipped.yaml"
python3 -I - "$BU" <<'PY'
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
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 bu lines ----\n' + '\n'.join(add) + '\n')
PY
echo "node: conf $BU/conf, JMX $jmx, address $addr; yaml tail:"
sed -n '/^# ---- stage4 bu lines/,$p' "$BU/conf/cassandra.yaml" | grep -v '^ *- \|^ *parameters\|class_name' | tr '\n' ';' ; echo
