#!/usr/bin/env bash
# usage: make-node-yaml.sh [yaml_key=value ...]                                                        (case B3a)
# Rebuilds ~/stage4-sep/node1/conf from the clone: a copy of conf/ whose cassandra.yaml is the tag's file with B3a's
# lines and then the extra key=value arguments (concurrent_writes, the per-IP in-flight limit of PC). B3a lines: every
# directory under ~/stage4-sep/node1/ on local disk, commitlog_total_space 2GiB, both native in-flight limits 256MiB.
# Environment deviation E1: the node listens on 127.0.0.11 (listen_address, rpc_address, the seed), not 127.0.0.1, and
# JMX is on 7211, because another stage-4 session shares this host. cassandra-env.sh gets JMX_PORT; jvm-server.options
# gets -XX:HeapDumpPath under the node's logs (B3a). The heap (MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M) is set in
# cluster-run.py. A key already set in the shipped yaml is removed first, so no key appears twice. Nothing in the clone
# is changed. From the WRITE_BUFFER_SIZE-append-remaining--autonomous harness's make-node-yaml.sh.
set -euo pipefail
C=${CASSANDRA_HOME:-$HOME/cassandra-sep}; N=${SEPN:-$HOME/stage4-sep}/node1
addr=127.0.0.11; jmx=7211
mkdir -p "$N/logs" "$N/data" "$N/commitlog" "$N/hints" "$N/saved_caches" "$N/cdc"
rm -rf "$N/conf"; cp -r "$C/conf" "$N/conf"
git -C "$C" show HEAD:conf/cassandra-env.sh > "$N/conf/cassandra-env.sh"
sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$jmx\"/" "$N/conf/cassandra-env.sh"
grep -q "^JMX_PORT=\"$jmx\"" "$N/conf/cassandra-env.sh" || { echo "JMX_PORT line not replaced" >&2; exit 1; }
git -C "$C" show HEAD:conf/jvm-server.options > "$N/conf/jvm-server.options"
printf '\n# stage4 sep (B3a)\n-XX:HeapDumpPath=%s/logs\n' "$N" >> "$N/conf/jvm-server.options"
{
  echo "cluster_name: stage4-sep"
  echo "listen_address: $addr"
  echo "rpc_address: $addr"
  echo "seed_provider:"
  echo "  - class_name: org.apache.cassandra.locator.SimpleSeedProvider"
  echo "    parameters:"
  echo "      - seeds: \"$addr:7000\""
  echo "data_file_directories:"
  echo "    - $N/data"
  echo "commitlog_directory: $N/commitlog"
  echo "saved_caches_directory: $N/saved_caches"
  echo "hints_directory: $N/hints"
  echo "cdc_raw_directory: $N/cdc"
  echo "commitlog_total_space: 2GiB"
  for kv in "$@"; do echo "${kv%%=*}: ${kv#*=}"; done
} > "$N/lines.yaml"
# defaults of B3a that an argument may override (one key once)
for kv in native_transport_max_request_data_in_flight=256MiB native_transport_max_request_data_in_flight_per_ip=256MiB; do
  grep -q "^${kv%%=*}:" "$N/lines.yaml" || echo "${kv%%=*}: ${kv#*=}" >> "$N/lines.yaml"
done
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
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 sep lines ----\n' + '\n'.join(add) + '\n')
PY
echo "node1: conf $N/conf, JMX $jmx, address $addr; yaml tail:"
sed -n '/^# ---- stage4 sep lines/,$p' "$N/conf/cassandra.yaml" | grep -v '^ *- \|^ *parameters\|class_name' | tr '\n' ';' ; echo
