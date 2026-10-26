#!/usr/bin/env bash
# usage: make-node-yaml.sh <A|B> [yaml_key=value ...]   (cluster tier B3a of hints-HintsBuffer-put-slabCapacity--autonomous)
# Builds $HB/<node>/conf from the tree's conf/: the tag's cassandra.yaml with this node's lines (cluster name, loopback address
# A 127.0.20.1 / B 127.0.20.2, storage_port 7020, native_transport_port 9342, 4 tokens, SimpleSnitch, seed 127.0.20.1:7020,
# local directories under $HB/<node>/, hinted_handoff_enabled true, write_request_timeout 30000ms, native_transport_timeout
# 60000ms), then the arm's key=value arguments, which replace a line of the same key. cassandra-env.sh JMX_PORT = A 7320 / B 7321;
# jvm11-server.options gets -XX:MaxDirectMemorySize=1g. Nothing in the tree is changed. Pattern from the hints-CompressedHintsWriter harness.
set -euo pipefail
node=${1:?A|B}; shift 1
C=${CASSANDRA_HOME:-$HOME/s4-hb}; HB=${HB:-$HOME/s4-hb-data}; N=$HB/$node
case $node in A) addr=127.0.20.1; jmx=7320 ;; B) addr=127.0.20.2; jmx=7321 ;; *) echo "unknown node $node" >&2; exit 2 ;; esac
mkdir -p "$N/logs" "$N/data" "$N/commitlog" "$N/hints" "$N/saved_caches" "$N/cdc_raw"
rm -rf "$N/conf"; cp -r "$C/conf" "$N/conf"
git -C "$C" show HEAD:conf/cassandra-env.sh > "$N/conf/cassandra-env.sh"
sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$jmx\"/" "$N/conf/cassandra-env.sh"
grep -q "^JMX_PORT=\"$jmx\"" "$N/conf/cassandra-env.sh" || { echo "JMX_PORT line not replaced" >&2; exit 1; }
git -C "$C" show HEAD:conf/jvm11-server.options > "$N/conf/jvm11-server.options"
printf '\n# stage4 hb (B3a)\n-XX:MaxDirectMemorySize=1g\n' >> "$N/conf/jvm11-server.options"
declare -A kv=( [hinted_handoff_enabled]=true [write_request_timeout]=30000ms [native_transport_timeout]=60000ms )
order=(hinted_handoff_enabled write_request_timeout native_transport_timeout)
for a in "$@"; do k=${a%%=*}; [ -n "${kv[$k]+x}" ] || order+=("$k"); kv[$k]=${a#*=}; done
{
  echo "cluster_name: stage4-hb"; echo "num_tokens: 4"; echo "endpoint_snitch: SimpleSnitch"
  echo "listen_address: $addr"; echo "rpc_address: $addr"; echo "storage_port: 7020"; echo "native_transport_port: 9342"
  echo "seed_provider:"; echo "  - class_name: org.apache.cassandra.locator.SimpleSeedProvider"; echo "    parameters:"; echo "      - seeds: \"127.0.20.1:7020\""
  echo "data_file_directories:"; echo "    - $N/data"
  echo "commitlog_directory: $N/commitlog"; echo "hints_directory: $N/hints"; echo "saved_caches_directory: $N/saved_caches"; echo "cdc_raw_directory: $N/cdc_raw"
  for k in "${order[@]}"; do echo "$k: ${kv[$k]}"; done
} > "$N/lines.yaml"
git -C "$C" show HEAD:conf/cassandra.yaml > "$N/shipped.yaml"
python3 -I - "$N" <<'PY'
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
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 hb lines ----\n' + '\n'.join(add) + '\n')
PY
echo "node $node: conf $N/conf, JMX $jmx, address $addr; yaml tail:"
sed -n '/^# ---- stage4 hb lines/,$p' "$N/conf/cassandra.yaml" | grep -v '^ *- \|^ *parameters\|class_name' | tr '\n' ';' ; echo
