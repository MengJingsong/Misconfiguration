#!/usr/bin/env bash
# usage: make-node-yaml.sh <N1|N2> <partitioner-class> <initial_token> [yaml_key=value ...]     (case 9b, amended 2026-10-14)
# Rebuilds ~/s4b-rss/<node>/conf from the clone: a copy of conf/ whose cassandra.yaml is the tag's file with this node's
# lines (cluster, loopback address, token, partitioner, every directory under ~/s4b-rss/<node>/, the 9b hold-fixed
# settings) and then the extra key=value arguments, and whose cassandra-env.sh has JMX_PORT set to the node's port
# (7102 N1, 7103 N2). A key already set in the shipped yaml is removed first (with its continuation lines), so no key
# appears twice. Nothing in the clone is changed. Adapted from the internode_application_send_queue_capacity harness.
set -euo pipefail
node=${1:?N1|N2}; part=${2:?partitioner}; tok=${3:?initial_token}; shift 3
C=${CASSANDRA_HOME:-$HOME/cassandra-run1}; N=${RSS:-$HOME/s4b-rss}/$node
case $node in
  N1) addr=127.0.0.2; jmx=7102 ;;
  N2) addr=127.0.0.3; jmx=7103 ;;
  *) echo "unknown node $node" >&2; exit 2 ;;
esac
mkdir -p "$N/logs" "$N/data" "$N/commitlog" "$N/hints" "$N/saved_caches" "$N/cdc_raw"
rm -rf "$N/conf"; cp -r "$C/conf" "$N/conf"
git -C "$C" show HEAD:conf/cassandra-env.sh > "$N/conf/cassandra-env.sh"
sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$jmx\"/" "$N/conf/cassandra-env.sh"
grep -q "^JMX_PORT=\"$jmx\"" "$N/conf/cassandra-env.sh" || { echo "JMX_PORT line not replaced" >&2; exit 1; }
{
  echo "cluster_name: stage4-rss"
  echo "partitioner: $part"
  echo "num_tokens: 1"
  echo "initial_token: $tok"
  echo "auto_bootstrap: false"
  echo "storage_port: 7010"
  echo "listen_address: $addr"
  echo "rpc_address: $addr"
  echo "seed_provider:"
  echo "  - class_name: org.apache.cassandra.locator.SimpleSeedProvider"
  echo "    parameters:"
  echo "      - seeds: \"127.0.0.2:7010\""
  echo "data_file_directories:"
  echo "    - $N/data"
  echo "commitlog_directory: $N/commitlog"
  echo "hints_directory: $N/hints"
  echo "saved_caches_directory: $N/saved_caches"
  echo "cdc_raw_directory: $N/cdc_raw"
  echo "concurrent_merkle_tree_requests: 1"
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
        continue          # continuation (list items, comments inside the removed block)
    else:
        skip = False
    out.append(l)
dups = [k for k in keys if sum(1 for l in add if l.startswith(k + ':')) > 1]
if dups:
    sys.exit('duplicate keys in the arguments: %s' % dups)
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 rss lines ----\n' + '\n'.join(add) + '\n')
PY
echo "node $node: conf $N/conf, JMX $jmx, address $addr, token $tok, partitioner $part; yaml tail:"
sed -n '/^# ---- stage4 rss lines/,$p' "$N/conf/cassandra.yaml" | tr '\n' ';' ; echo
