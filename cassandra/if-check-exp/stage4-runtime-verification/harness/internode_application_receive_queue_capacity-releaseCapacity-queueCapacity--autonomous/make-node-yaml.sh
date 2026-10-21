#!/usr/bin/env bash
# usage: make-node-yaml.sh <A|B> [yaml_key=value ...]          (case file B3a/B3b, audit amendments R3/R4)
# Rebuilds ~/stage4-rrc/<node>/conf from the clone: a copy of conf/ whose cassandra.yaml is the tag's file with this node's
# lines and then the extra key=value arguments; cassandra-env.sh has JMX_PORT set to the node's port.
#   A = 127.0.0.2 (JMX 7102, the seed, sender/coordinator), B = 127.0.0.3 (JMX 7103, the receiver under test).
#   Both: cluster stage4-rrc, num_tokens 1 (B3a), SimpleSnitch (B3a), write_request_timeout 60000ms (R3),
#   native_transport_timeout 60000ms (runbook defect 1, shakedown 2: the coordinator stamps a MUTATION_REQ's expiry
#   with the nearer of the verb timeout and native_transport_timeout, 12 s by default, so R3 alone left a 12 s expiry),
#   hinted_handoff_enabled false (harness choice: A's overloaded or timed-out sends to B would otherwise be hinted and
#   replayed into B's queue after the load, at 1 MiB/s; not a §9a knob), auto_bootstrap false, every directory under
#   $RRC_DATA/<node>/ (a tmpfs on the run node's RAM: local, never /proj).
#   A only: the raised send-side limits of B3b (internode_application_send_queue_capacity 64MiB, send reserves
#   512MiB/1GiB).
#   B only: memtable_allocation_type offheap_buffers (harness choice, fixed before any reading: keeps the memtable's
#   copies of the 512 KiB values out of the heap histogram that B3d(2) reads for the queued messages); NMT summary on
#   (B3d(4)) in jvm11-server.options.
# A key already set in the shipped yaml is removed first (with its continuation lines), so no key appears twice. Nothing
# in the clone is changed. From the closed sibling's make-node-yaml.sh (internode_application_receive_queue_capacity
# acquireCapacity--guided) and the loopback recipe of internode_max_message_size-inferMessageSize--autonomous.
set -euo pipefail
node=${1:?A|B}; shift 1
C=${CASSANDRA_HOME:-$HOME/cassandra-run1}; N=${RRC:-$HOME/stage4-rrc}/$node
DD=${RRC_DATA:-/mnt/stage4-rrc}/$node
case $node in
  A) addr=127.0.0.2; jmx=7102; tok=-9223372036854775808 ;;
  B) addr=127.0.0.3; jmx=7103; tok=0 ;;
  *) echo "unknown node $node" >&2; exit 2 ;;
esac
mountpoint -q "$(dirname "$DD")" || { echo "$(dirname "$DD") is not mounted" >&2; exit 1; }
mkdir -p "$N/logs" "$DD/data" "$DD/commitlog" "$DD/hints" "$DD/saved_caches" "$DD/cdc_raw"
rm -rf "$N/conf"; cp -r "$C/conf" "$N/conf"
git -C "$C" show HEAD:conf/cassandra-env.sh > "$N/conf/cassandra-env.sh"
sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$jmx\"/" "$N/conf/cassandra-env.sh"
grep -q "^JMX_PORT=\"$jmx\"" "$N/conf/cassandra-env.sh" || { echo "JMX_PORT line not replaced" >&2; exit 1; }
git -C "$C" show HEAD:conf/jvm11-server.options > "$N/conf/jvm11-server.options"
[ "$node" = B ] && printf '\n# stage4 rrc (B3d(4))\n-XX:NativeMemoryTracking=summary\n' >> "$N/conf/jvm11-server.options"
{
  echo "cluster_name: stage4-rrc"
  echo "num_tokens: 1"
  echo "initial_token: $tok"
  echo "endpoint_snitch: SimpleSnitch"
  echo "auto_bootstrap: false"
  echo "listen_address: $addr"
  echo "rpc_address: $addr"
  echo "seed_provider:"
  echo "  - class_name: org.apache.cassandra.locator.SimpleSeedProvider"
  echo "    parameters:"
  echo "      - seeds: \"127.0.0.2:7000\""
  echo "data_file_directories:"
  echo "    - $DD/data"
  echo "commitlog_directory: $DD/commitlog"
  echo "hints_directory: $DD/hints"
  echo "saved_caches_directory: $DD/saved_caches"
  echo "cdc_raw_directory: $DD/cdc_raw"
  echo "write_request_timeout: 60000ms"
  echo "native_transport_timeout: 60000ms"
  echo "hinted_handoff_enabled: false"
  echo "auto_snapshot: false"
  if [ "$node" = A ]; then
    echo "internode_application_send_queue_capacity: 64MiB"
    echo "internode_application_send_queue_reserve_endpoint_capacity: 512MiB"
    echo "internode_application_send_queue_reserve_global_capacity: 1GiB"
  else
    echo "memtable_allocation_type: offheap_buffers"
  fi
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
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 rrc lines ----\n' + '\n'.join(add) + '\n')
PY
echo "node $node: conf $N/conf, JMX $jmx, address $addr, token $tok; yaml tail:"
sed -n '/^# ---- stage4 rrc lines/,$p' "$N/conf/cassandra.yaml" | grep -v '^ *- \|^ *parameters\|class_name' | tr '\n' ';' ; echo
