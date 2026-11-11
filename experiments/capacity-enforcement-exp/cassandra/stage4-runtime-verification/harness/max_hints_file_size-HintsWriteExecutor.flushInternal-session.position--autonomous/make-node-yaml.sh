#!/usr/bin/env bash
# usage: make-node-yaml.sh <A|B> [yaml_key=value ...]      (B3a as amended 2026-10-26; adapted from the
# max_hints_size_per_host harness). Rebuilds ~/s4-mh-run/<node>/conf from the tree: a copy of conf/ whose cassandra.yaml is
# the tag's file with this node's lines (cluster, loopback address, ports, token, directories, hold-fixed settings) and then
# the extra key=value arguments, and whose cassandra-env.sh has JMX_PORT set to the node's port. A key already set in the
# shipped yaml is removed first (with its continuation lines). Nothing in the tree is changed.
# A = 127.0.23.1 storage 7023 JMX 7323 native 9345; B = 127.0.23.2 storage 7024 JMX 7324 native 9346.
set -euo pipefail
node=${1:?A|B}; shift 1
C=${CASSANDRA_HOME:-$HOME/s4-mh}; N=${MH_RUN:-$HOME/s4-mh-run}/$node
case $node in
  A) addr=127.0.23.1; jmx=7323; st=7023; nat=9345; tok=-4611686018427387904 ;;
  B) addr=127.0.23.2; jmx=7324; st=7024; nat=9346; tok=4611686018427387904 ;;
  *) echo "unknown node $node" >&2; exit 2 ;;
esac
mkdir -p "$N/logs" "$N/data" "$N/commitlog" "$N/hints" "$N/saved_caches" "$N/cdc_raw"
rm -rf "$N/conf"; cp -r "$C/conf" "$N/conf"
git -C "$C" show HEAD:conf/cassandra-env.sh > "$N/conf/cassandra-env.sh"
sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$jmx\"/" "$N/conf/cassandra-env.sh"
grep -q "^JMX_PORT=\"$jmx\"" "$N/conf/cassandra-env.sh" || { echo "JMX_PORT line not replaced" >&2; exit 1; }
{
  echo "cluster_name: stage4-mh"
  echo "num_tokens: 1"
  echo "initial_token: $tok"
  echo "auto_bootstrap: false"
  echo "storage_port: $st"
  echo "native_transport_port: $nat"
  echo "listen_address: $addr"
  echo "rpc_address: $addr"
  echo "seed_provider:"
  echo "  - class_name: org.apache.cassandra.locator.SimpleSeedProvider"
  echo "    parameters:"
  echo "      - seeds: \"127.0.23.1:7023\""
  echo "data_file_directories:"
  echo "    - $N/data"
  echo "commitlog_directory: $N/commitlog"
  echo "hints_directory: $N/hints"
  echo "saved_caches_directory: $N/saved_caches"
  echo "cdc_raw_directory: $N/cdc_raw"
  echo "hinted_handoff_enabled: true"
  echo "max_hint_window: 6h"
  echo "hints_flush_period: 1000ms"
  echo "auto_hints_cleanup_enabled: false"
  echo "endpoint_snitch: SimpleSnitch"
  for kv in "$@"; do echo "${kv%%=*}: ${kv#*=}"; done
} > "$N/lines.yaml"
git -C "$C" show HEAD:conf/cassandra.yaml > "$N/shipped.yaml"
python3 - "$N" <<'PY'
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
    sys.exit('duplicate keys in the arguments: %s' % dups)
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 mh lines ----\n' + '\n'.join(add) + '\n')
PY
echo "node $node: conf $N/conf, JMX $jmx, address $addr, storage $st, native $nat; yaml tail:"
sed -n '/^# ---- stage4 mh lines/,$p' "$N/conf/cassandra.yaml" | tr '\n' ';' ; echo
