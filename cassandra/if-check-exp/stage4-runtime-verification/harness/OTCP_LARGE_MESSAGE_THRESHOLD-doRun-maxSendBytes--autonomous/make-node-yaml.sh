#!/usr/bin/env bash
# usage: make-node-yaml.sh <n1|n2> [yaml_key=value ...]        (case file B3a, B3b; amendments S4-A5, S4-A6)
# Rebuilds ~/stage4-otc/<node>/conf from the clone: a copy of conf/ whose cassandra.yaml is the tag's file with B3a's lines
# and then the extra key=value arguments (the B3b send-queue knobs and S4-A6's receive endpoint key); cassandra-env.sh has
# JMX_PORT set (n1 7199, n2 7299). Data, commit log, hints, caches and cdc_raw under ~/stage4-otc/<node>/data (local disk).
# A key already set in the shipped yaml is removed first (with its continuation lines). Nothing in the clone is changed.
# Adapted from internode_application_send_queue_capacity-releaseCapacity-pendingCapacityInBytes--autonomous/make-node-yaml.sh.
set -euo pipefail
node=${1:?n1|n2}; shift 1
C=${CASSANDRA_HOME:-$HOME/cassandra-otc}; N=$HOME/stage4-otc/$node; DD=$N/data
case $node in
  n1) addr=127.0.0.1; jmx=7199 ;;
  n2) addr=127.0.0.2; jmx=7299 ;;
  *) echo "unknown node $node" >&2; exit 2 ;;
esac
mkdir -p "$N/logs" "$DD/data" "$DD/commitlog" "$DD/hints" "$DD/saved_caches" "$DD/cdc_raw"
rm -rf "$N/conf"; cp -r "$C/conf" "$N/conf"
git -C "$C" show HEAD:conf/cassandra-env.sh > "$N/conf/cassandra-env.sh"
sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$jmx\"/" "$N/conf/cassandra-env.sh"
grep -q "^JMX_PORT=\"$jmx\"" "$N/conf/cassandra-env.sh" || { echo "JMX_PORT line not replaced" >&2; exit 1; }
{
  echo "cluster_name: lmt"
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
  echo "write_request_timeout: 10000ms"
  echo "phi_convict_threshold: 16"
  echo "internode_compression: none"
  echo "hinted_handoff_enabled: false"
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
    sys.exit('duplicate keys: %s' % dups)
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 otc lines ----\n' + '\n'.join(add) + '\n')
PY
echo "node $node: conf $N/conf, JMX $jmx, address $addr; yaml tail:"
sed -n '/^# ---- stage4 otc lines/,$p' "$N/conf/cassandra.yaml" | grep -v '^ *- \|^ *parameters\|class_name' | tr '\n' ';' ; echo
