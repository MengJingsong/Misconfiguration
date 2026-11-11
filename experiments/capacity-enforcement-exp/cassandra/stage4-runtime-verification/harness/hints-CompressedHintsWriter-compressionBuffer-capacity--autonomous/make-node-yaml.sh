#!/usr/bin/env bash
# usage: make-node-yaml.sh <A|B|C> [yaml_key=value ...]   (cluster tier B3a, as amended 2026-10-25)
# Rebuilds $HW/<node>/conf from the tree: a copy of conf/ whose cassandra.yaml is the tag's file with this node's lines:
# cluster name, loopback address (A 127.0.14.1, B 127.0.14.2, C 127.0.14.3), storage_port 7014, native_transport_port 9146,
# 4 tokens, SimpleSnitch, seed 127.0.14.1:7014, every directory under $HW/<node>/ on local disk, hinted_handoff_enabled true,
# write_request_timeout 30000ms, native_transport_timeout 60000ms, then the arm's key=value arguments, which replace a line of
# the same key. The argument hints_compression=LZ4Compressor writes the multi-line block (one list item, class_name LZ4Compressor, no parameters); absent = hints uncompressed. cassandra-env.sh has JMX_PORT set to the node's port (A 7814, B 7815, C 7816);
# jvm11-server.options gets -XX:MaxDirectMemorySize=2g. Nothing in the tree is changed. From the max_mutation_size harness.
set -euo pipefail
node=${1:?A|B|C}; shift 1
C=${CASSANDRA_HOME:-$HOME/s4-hw}; HW=${HW:-$HOME/s4-hw-data}; N=$HW/$node
case $node in
  A) addr=127.0.14.1; jmx=7814 ;;
  B) addr=127.0.14.2; jmx=7815 ;;
  C) addr=127.0.14.3; jmx=7816 ;;
  *) echo "unknown node $node" >&2; exit 2 ;;
esac
mkdir -p "$N/logs" "$N/data" "$N/commitlog" "$N/hints" "$N/saved_caches" "$N/cdc_raw"
rm -rf "$N/conf"; cp -r "$C/conf" "$N/conf"
git -C "$C" show HEAD:conf/cassandra-env.sh > "$N/conf/cassandra-env.sh"
sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$jmx\"/" "$N/conf/cassandra-env.sh"
grep -q "^JMX_PORT=\"$jmx\"" "$N/conf/cassandra-env.sh" || { echo "JMX_PORT line not replaced" >&2; exit 1; }
git -C "$C" show HEAD:conf/jvm11-server.options > "$N/conf/jvm11-server.options"
printf '\n# stage4 hw (B3a)\n-XX:MaxDirectMemorySize=2g\n' >> "$N/conf/jvm11-server.options"
declare -A kv=( [hinted_handoff_enabled]=true [write_request_timeout]=30000ms [native_transport_timeout]=60000ms )
order=(hinted_handoff_enabled write_request_timeout native_transport_timeout)
comp=""
for a in "$@"; do
  k=${a%%=*}
  if [ "$k" = hints_compression ]; then comp=${a#*=}; continue; fi
  [ -n "${kv[$k]+x}" ] || order+=("$k"); kv[$k]=${a#*=}
done
{
  echo "cluster_name: stage4-hw"
  echo "num_tokens: 4"
  echo "endpoint_snitch: SimpleSnitch"
  echo "listen_address: $addr"
  echo "rpc_address: $addr"
  echo "storage_port: 7014"
  echo "native_transport_port: 9146"
  echo "seed_provider:"
  echo "  - class_name: org.apache.cassandra.locator.SimpleSeedProvider"
  echo "    parameters:"
  echo "      - seeds: \"127.0.14.1:7014\""
  echo "data_file_directories:"
  echo "    - $N/data"
  echo "commitlog_directory: $N/commitlog"
  echo "hints_directory: $N/hints"
  echo "saved_caches_directory: $N/saved_caches"
  echo "cdc_raw_directory: $N/cdc_raw"
  for k in "${order[@]}"; do echo "$k: ${kv[$k]}"; done
  if [ -n "$comp" ]; then
    echo "hints_compression:"
    echo "    - class_name: $comp"
  fi
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
dups = [k for k in keys if sum(1 for l in add if l.startswith(k + ':')) > 1]
if dups:
    sys.exit('duplicate keys: %s' % dups)
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 hw lines ----\n' + '\n'.join(add) + '\n')
PY
echo "node $node: conf $N/conf, JMX $jmx, address $addr; yaml tail:"
sed -n '/^# ---- stage4 hw lines/,$p' "$N/conf/cassandra.yaml" | grep -v '^ *- \|^ *parameters\|class_name' | tr '\n' ';' ; echo
