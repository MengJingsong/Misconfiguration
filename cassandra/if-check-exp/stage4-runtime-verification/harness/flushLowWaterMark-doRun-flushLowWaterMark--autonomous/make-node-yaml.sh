#!/usr/bin/env bash
# usage: CASSANDRA_HOME=<variant tree> make-node-yaml.sh <A|B>
#   Cluster tier (B3a, amendments A5/A11) of flushLowWaterMark-doRun-flushLowWaterMark--autonomous.
#   Rebuilds ~/stage4-flw/<node>/conf from the variant tree: a copy of conf/ whose cassandra.yaml is the tag's file with
#   B3a's lines (both nodes: cluster fwm, num_tokens 16, seeds 127.0.0.1:7000, hinted_handoff_enabled false,
#   internode_compression none, internode_tcp_user_timeout 0ms, phi_convict_threshold 16, concurrent_compactors 2, all
#   directories on the tmpfs ~/stage4-flw/nodes/<node>; B: auto_bootstrap false), and cassandra-env.sh with JMX_PORT
#   set (A 7199, B 7299). The 4 KiB socket-buffer lines of B3a are dropped (runbook defect 1, dated amendment in the case
#   file, 2026-10-22: with them the link drained ~17 KB/s and was saturated before the freeze). A key already in the shipped yaml is removed first (with its continuation lines).
#   Adapted from the closed internode_application_send_queue_capacity-releaseCapacity-pendingCapacityInBytes--autonomous
#   harness's make-node-yaml.sh. Nothing in the tree is changed.
set -euo pipefail
node=${1:?A|B}
C=${CASSANDRA_HOME:?variant tree}
N=$HOME/stage4-flw/$node
DD=$HOME/stage4-flw/nodes/$node
case $node in
  A) addr=127.0.0.1; jmx=7199 ;;
  B) addr=127.0.0.2; jmx=7299 ;;
  *) echo "unknown node $node" >&2; exit 2 ;;
esac
mountpoint -q "$(dirname "$DD")" || { echo "$(dirname "$DD") is not mounted" >&2; exit 1; }
mkdir -p "$N/logs" "$DD/data" "$DD/commitlog" "$DD/hints" "$DD/saved_caches" "$DD/cdc_raw"
rm -rf "$N/conf"; cp -r "$C/conf" "$N/conf"
git -C "$C" show HEAD:conf/cassandra-env.sh > "$N/conf/cassandra-env.sh"
sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$jmx\"/" "$N/conf/cassandra-env.sh"
grep -q "^JMX_PORT=\"$jmx\"" "$N/conf/cassandra-env.sh" || { echo "JMX_PORT line not replaced" >&2; exit 1; }
{
  echo "cluster_name: fwm"
  echo "num_tokens: 16"
  echo "listen_address: $addr"
  echo "rpc_address: $addr"
  echo "seed_provider:"
  echo "  - class_name: org.apache.cassandra.locator.SimpleSeedProvider"
  echo "    parameters:"
  echo "      - seeds: \"127.0.0.1:7000\""
  echo "data_file_directories:"
  echo "    - $DD/data"
  echo "commitlog_directory: $DD/commitlog"
  echo "hints_directory: $DD/hints"
  echo "saved_caches_directory: $DD/saved_caches"
  echo "cdc_raw_directory: $DD/cdc_raw"
  echo "hinted_handoff_enabled: false"
  echo "internode_compression: none"
  echo "internode_tcp_user_timeout: 0ms"
  echo "phi_convict_threshold: 16"
  echo "concurrent_compactors: 2"
  echo "auto_snapshot: false"
  if [ "$node" = B ]; then echo "auto_bootstrap: false"; fi
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
    sys.exit('duplicate keys: %s' % dups)
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 flw lines ----\n' + '\n'.join(add) + '\n')
PY
echo "node $node: tree $C conf $N/conf, JMX $jmx, address $addr; yaml tail:"
sed -n '/^# ---- stage4 flw lines/,$p' "$N/conf/cassandra.yaml" | grep -v '^ *- \|^ *parameters\|class_name' | tr '\n' ';' ; echo
