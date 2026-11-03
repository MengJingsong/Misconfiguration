#!/usr/bin/env bash
# usage: make-node-conf.sh <n1|n2|n3>           (B3a as amended C1, 2026-10-27)
# Builds $W/node-rssih/<node>/conf from the clone $W/cassandra-run60: a copy of conf/ whose cassandra.yaml is the tag's file with
# this node's lines (cluster, loopback address, token, directories under $W/node-rssih/<node>/), and whose cassandra-env.sh has
# JMX_PORT set to the node's port. A key already set in the shipped yaml is removed first (with its continuation lines), so no key
# appears twice. Nothing in the clone is changed.
# Adapted from harness/repair_session_space-applySimpleConfig-repair_session_space--autonomous/make-node-conf.sh (one clone for all nodes).
set -euo pipefail
source ~/Library/Caches/stage4/env.sh
C=$W/cassandra-run60
node=${1:?n1|n2|n3}
case $node in
  n1) addr=127.0.0.1; jmx=7199; tok=-9223372036854775808 ;;
  n2) addr=127.0.0.2; jmx=7299; tok=-3074457345618258603 ;;
  n3) addr=127.0.0.3; jmx=7399; tok=3074457345618258602 ;;
  *) echo "unknown node $node" >&2; exit 2 ;;
esac
N=$W/node-rssih/$node
mkdir -p "$N/data" "$N/commitlog" "$N/hints" "$N/saved_caches" "$N/cdc_raw"
rm -rf "$N/conf"; cp -R "$C/conf" "$N/conf"
git -C "$C" show HEAD:conf/cassandra-env.sh > "$N/conf/cassandra-env.sh"
sed -i '' "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$jmx\"/" "$N/conf/cassandra-env.sh"
grep -q "^JMX_PORT=\"$jmx\"" "$N/conf/cassandra-env.sh" || { echo "JMX_PORT line not replaced" >&2; exit 1; }
{
  echo "cluster_name: rssih"
  echo "num_tokens: 1"
  echo "initial_token: $tok"
  echo "auto_bootstrap: false"
  echo "listen_address: $addr"
  echo "rpc_address: $addr"
  echo "seed_provider:"
  echo "  - class_name: org.apache.cassandra.locator.SimpleSeedProvider"
  echo "    parameters:"
  echo "      - seeds: \"127.0.0.1:7000\""
  echo "data_file_directories:"
  echo "    - $N/data"
  echo "commitlog_directory: $N/commitlog"
  echo "hints_directory: $N/hints"
  echo "saved_caches_directory: $N/saved_caches"
  echo "cdc_raw_directory: $N/cdc_raw"
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
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 rssih lines ----\n' + '\n'.join(add) + '\n')
PY
echo "node $node: clone $C, conf $N/conf, JMX $jmx, address $addr, token $tok"
