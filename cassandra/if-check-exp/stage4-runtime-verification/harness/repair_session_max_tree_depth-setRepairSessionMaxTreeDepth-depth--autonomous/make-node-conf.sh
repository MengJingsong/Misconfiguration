#!/usr/bin/env bash
# usage: make-node-conf.sh <n1|n2> [yaml_key=value ...]   (B3a as amended 2026-10-25, repair_session_max_tree_depth setter case)
# Rebuilds $W/node-rsmtds/<node>/conf from the node's clone: a copy of conf/ whose cassandra.yaml is the tag's file with this
# node's lines (cluster, loopback address, token, directories under $W/node-rsmtds/<node>/) and then the extra key=value
# arguments, and whose cassandra-env.sh has JMX_PORT set to the node's port. A key already set in the shipped yaml is
# removed first (with its continuation lines), so no key appears twice. Nothing in the clone is changed.
# Copied from harness/repair_session_max_tree_depth-applySimpleConfig-repair_session_max_tree_depth--autonomous/make-node-conf.sh;
# changed: two nodes (tokens -2^63 and 0, JMX 7199 and 7200, clones run24 / run24-n2), cluster_name td, data under $W/node-rsmtds.
# Changed 2026-10-27 for the cluster re-run (paths only): the clones and the node root come from RSMTD_C1, RSMTD_C2 and
# RSMTD_NODE; the defaults reproduce run 1.
set -euo pipefail
source ~/Library/Caches/stage4/env.sh
node=${1:?n1|n2}; shift
case $node in
  n1) addr=127.0.0.1; jmx=7199; tok=-9223372036854775808; C=${RSMTD_C1:-$W/cassandra-run24} ;;
  n2) addr=127.0.0.2; jmx=7200; tok=0; C=${RSMTD_C2:-$W/cassandra-run24-n2} ;;
  *) echo "unknown node $node" >&2; exit 2 ;;
esac
N=${RSMTD_NODE:-$W/node-rsmtds}/$node
mkdir -p "$N/data" "$N/commitlog" "$N/hints" "$N/saved_caches" "$N/cdc_raw"
rm -rf "$N/conf"; cp -R "$C/conf" "$N/conf"
git -C "$C" show HEAD:conf/cassandra-env.sh > "$N/conf/cassandra-env.sh"
sed -i '' "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$jmx\"/" "$N/conf/cassandra-env.sh"
grep -q "^JMX_PORT=\"$jmx\"" "$N/conf/cassandra-env.sh" || { echo "JMX_PORT line not replaced" >&2; exit 1; }
{
  echo "cluster_name: td"
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
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 rsmtds lines ----\n' + '\n'.join(add) + '\n')
PY
echo "node $node: clone $C, conf $N/conf, JMX $jmx, address $addr, token $tok; yaml tail: $(sed -n '/^# ---- stage4 rsmtds lines/,$p' "$N/conf/cassandra.yaml" | tr '\n' ';')"
