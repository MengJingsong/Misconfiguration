#!/usr/bin/env bash
# usage: make-node-yaml.sh <A|B> [yaml_key=value ...]          (case file B3a/B3b, audit amendments R5, R6, R10)
# Rebuilds ~/stage4-rsv/<node>/conf from the clone: a copy of conf/ whose cassandra.yaml is the tag's file with this node's lines
# and then the extra key=value arguments; cassandra-env.sh has JMX_PORT set to the node's port.
#   A = 127.0.0.2 (JMX 7102, the seed) = the TARGET of the case file (the receiver whose reserve is varied).
#   B = 127.0.0.3 (JMX 7103) = the sender / load node of the case file (the stress client connects to it; RF 2 forwards to A).
#   Both: cluster stage4-rsv, num_tokens 1, SimpleSnitch, auto_bootstrap false, write_request_timeout 60000ms and
#   native_transport_timeout 60000ms (R5: a coordinator stamps the nearer of the two on a forwarded mutation; an expired
#   inbound message is skipped before capacity), hinted_handoff_enabled false, auto_snapshot false, every directory under
#   $RSV_DATA/<node>/ (a tmpfs on the run node's RAM: local, never /proj).
#   B only: native_transport_max_threads 256 (R4a).
#   A only: concurrent_writes 2 (B3b), memtable_allocation_type offheap_buffers (harness choice: the histogram reads the queued
#   messages' Mutation + [B, and a heap memtable would keep every applied 256 KiB value as a [B), NMT summary in
#   jvm11-server.options; then the label's keys (reserves, queue capacity).
# A key already set in the shipped yaml is removed first (with its continuation lines), so no key appears twice. Nothing in
# the clone is changed. Adapted from the closed sibling's make-node-yaml.sh (releaseCapacity--autonomous).
set -euo pipefail
node=${1:?A|B}; shift 1
C=${CASSANDRA_HOME:-$HOME/cassandra-rsv}; N=${RSV:-$HOME/stage4-rsv}/$node
DD=${RSV_DATA:-/mnt/stage4-rsv}/$node
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
[ "$node" = A ] && printf '\n# stage4 rsv (B3d)\n-XX:NativeMemoryTracking=summary\n' >> "$N/conf/jvm11-server.options"
{
  echo "cluster_name: stage4-rsv"
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
  if [ "$node" = B ]; then
    echo "native_transport_max_threads: 256"   # R4a: a cl=ALL write holds an NTR thread; the default 128 capped the load at 128 messages
  fi
  if [ "$node" = A ]; then
    echo "concurrent_writes: 2"
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
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 rsv lines ----\n' + '\n'.join(add) + '\n')
PY
echo "node $node: conf $N/conf, JMX $jmx, address $addr, token $tok; yaml tail:"
sed -n '/^# ---- stage4 rsv lines/,$p' "$N/conf/cassandra.yaml" | grep -v '^ *- \|^ *parameters\|class_name' | tr '\n' ';' ; echo
