#!/usr/bin/env bash
# usage: make-node-yaml.sh <A|B> [yaml_key=value ...]          (case B3a, amended 2026-10-20: R3 hints off, R4 native default)
# Rebuilds ~/stage4-imm/<node>/conf from the clone: a copy of conf/ whose cassandra.yaml is the tag's file with this node's
# B3a lines (cluster, loopback address, 4 tokens, SimpleSnitch, seed 127.0.0.1, commitlog_segment_size 32MiB,
# hinted_handoff_enabled false, every directory under ~/stage4-imm/<node>/, on local disk) and then the extra key=value
# arguments (the run's internode_max_message_size); cassandra-env.sh has JMX_PORT set to the node's port (A 7199,
# B 7299); jvm11-server.options gets -XX:MaxDirectMemorySize=1G (the heap, 1G, is MAX_HEAP_SIZE in cluster-run.py).
# native_transport_max_message_size is not set (R4: derived 16 MiB at -Xmx1G). A key already set in the shipped yaml is
# removed first, so no key appears twice. Nothing in the clone is changed. From the
# internode_application_receive_queue_capacity harness's make-node-yaml.sh.
set -euo pipefail
node=${1:?A|B}; shift 1
C=${CASSANDRA_HOME:-$HOME/cassandra-run5}; N=${IMM:-$HOME/stage4-imm}/$node
case $node in
  A) addr=127.0.0.1; jmx=7199 ;;
  B) addr=127.0.0.2; jmx=7299 ;;
  *) echo "unknown node $node" >&2; exit 2 ;;
esac
mkdir -p "$N/logs" "$N/data" "$N/commitlog" "$N/hints" "$N/saved_caches" "$N/cdc_raw"
rm -rf "$N/conf"; cp -r "$C/conf" "$N/conf"
git -C "$C" show HEAD:conf/cassandra-env.sh > "$N/conf/cassandra-env.sh"
sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$jmx\"/" "$N/conf/cassandra-env.sh"
grep -q "^JMX_PORT=\"$jmx\"" "$N/conf/cassandra-env.sh" || { echo "JMX_PORT line not replaced" >&2; exit 1; }
git -C "$C" show HEAD:conf/jvm11-server.options > "$N/conf/jvm11-server.options"
printf '\n# stage4 imm (B3a)\n-XX:MaxDirectMemorySize=1G\n' >> "$N/conf/jvm11-server.options"
{
  echo "cluster_name: stage4-imm"
  echo "num_tokens: 4"
  echo "endpoint_snitch: SimpleSnitch"
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
  echo "commitlog_segment_size: 32MiB"
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
        continue          # continuation (list items, comments inside the removed block)
    else:
        skip = False
    out.append(l)
dups = [k for k in keys if sum(1 for l in add if l.startswith(k + ':')) > 1]
if dups:
    sys.exit('duplicate keys in the arguments: %s' % dups)
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 imm lines ----\n' + '\n'.join(add) + '\n')
PY
echo "node $node: conf $N/conf, JMX $jmx, address $addr; yaml tail:"
sed -n '/^# ---- stage4 imm lines/,$p' "$N/conf/cassandra.yaml" | grep -v '^ *- \|^ *parameters\|class_name' | tr '\n' ';' ; echo
