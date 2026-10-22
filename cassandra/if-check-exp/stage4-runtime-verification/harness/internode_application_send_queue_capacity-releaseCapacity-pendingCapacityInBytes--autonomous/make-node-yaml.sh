#!/usr/bin/env bash
# usage: make-node-yaml.sh <A|B> [yaml_key=value ...]          (case file B3a/B3b, amendments A4, A9)
# Rebuilds ~/stage4-sq2/<node>/conf from the clone: a copy of conf/ whose cassandra.yaml is the tag's file with this node's
# B3a lines and then the extra key=value arguments (node A: the four knobs of B3a/B3b); cassandra-env.sh has JMX_PORT set.
#   A = 127.0.0.1 (JMX 7199, the seed, the coordinator whose outbound link to B is measured), B = 127.0.0.2 (JMX 7299).
#   Both (B3a): cluster s3probe, num_tokens 16, seeds 127.0.0.1:7000, hinted_handoff_enabled false,
#   write_request_timeout 60000ms, phi_convict_threshold 16, internode_tcp_user_timeout 0ms,
#   memtable_allocation_type offheap_objects, memtable_heap_space 64MiB, memtable_offheap_space 512MiB;
#   native_transport_timeout 60000ms (amendment A4); every directory under $SQ2_DATA/<node>/ (a tmpfs, amendment A9).
#   B only: auto_bootstrap false (harness choice: B joins an empty ring with no keyspace, nothing to stream; skips the
#   30 s ring delay).
# A key already set in the shipped yaml is removed first (with its continuation lines). Nothing in the clone is changed.
# Adapted from the receive-side twin's make-node-yaml.sh (internode_application_receive_queue_capacity-releaseCapacity--autonomous).
set -euo pipefail
node=${1:?A|B}; shift 1
C=${CASSANDRA_HOME:-$HOME/cassandra-sq2}; N=${SQ2:-$HOME/stage4-sq2}/$node
DD=${SQ2_DATA:-$HOME/stage4-sq2/nodes}/$node
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
  echo "cluster_name: s3probe"
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
  echo "write_request_timeout: 60000ms"
  echo "native_transport_timeout: 60000ms"
  echo "phi_convict_threshold: 16"
  echo "internode_tcp_user_timeout: 0ms"
  echo "memtable_allocation_type: offheap_objects"
  echo "memtable_heap_space: 64MiB"
  echo "memtable_offheap_space: 512MiB"
  echo "auto_snapshot: false"
  [ "$node" = B ] && echo "auto_bootstrap: false"
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
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 sq2 lines ----\n' + '\n'.join(add) + '\n')
PY
echo "node $node: conf $N/conf, JMX $jmx, address $addr; yaml tail:"
sed -n '/^# ---- stage4 sq2 lines/,$p' "$N/conf/cassandra.yaml" | grep -v '^ *- \|^ *parameters\|class_name' | tr '\n' ';' ; echo
