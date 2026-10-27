#!/usr/bin/env bash
# usage: make-node-yaml.sh [yaml_key=value ...]     (batch_size_warn_threshold, B3a as amended A6, A8, 2026-10-26)
# Rebuilds $N/conf (default ~/s4-b9-bs-node/conf) from the node tree's conf/: the tag's cassandra.yaml with the one node's
# lines (slot 1: 127.0.1.1, every directory under $DD on tmpfs) and then the extra key=value arguments. cassandra-env.sh is the
# tag's with JMX_PORT 7110 (slot 1; local JMX binds 127.0.0.1). A key already set in the shipped yaml is removed first (with its
# continuation lines), so no key appears twice. Nothing in the tree is changed. Adapted from the batch_size_fail_threshold harness.
set -euo pipefail
C=${CASSANDRA_HOME:-$HOME/s4-b9-bs-n}; N=${BSN:-$HOME/s4-b9-bs-node}; DD=${BSD:-/dev/shm/s4-b9-bs}/data; ADDR=127.0.1.1
mkdir -p "$N/logs" "$DD/data" "$DD/commitlog" "$DD/hints" "$DD/saved_caches" "$DD/cdc_raw"
rm -rf "$N/conf"; cp -r "$C/conf" "$N/conf"
git -C "$C" show HEAD:conf/cassandra-env.sh | sed 's/^JMX_PORT="7199"/JMX_PORT="7110"/' > "$N/conf/cassandra-env.sh"
grep -q '^JMX_PORT="7110"' "$N/conf/cassandra-env.sh" || { echo "JMX_PORT edit failed" >&2; exit 1; }
{
  echo "cluster_name: s4-b9-bs"
  echo "num_tokens: 1"
  echo "auto_bootstrap: false"
  echo "listen_address: $ADDR"
  echo "rpc_address: $ADDR"
  echo "native_transport_port: 9042"
  echo "seed_provider:"
  echo "  - class_name: org.apache.cassandra.locator.SimpleSeedProvider"
  echo "    parameters:"
  echo "      - seeds: \"$ADDR:7000\""
  echo "data_file_directories:"
  echo "    - $DD/data"
  echo "commitlog_directory: $DD/commitlog"
  echo "hints_directory: $DD/hints"
  echo "saved_caches_directory: $DD/saved_caches"
  echo "cdc_raw_directory: $DD/cdc_raw"
  echo "auto_snapshot: false"
  echo "native_transport_max_frame_size: 64MiB"
  echo "native_transport_max_message_size: 64MiB"
  echo "native_transport_max_request_data_in_flight: 128MiB"
  echo "native_transport_max_request_data_in_flight_per_ip: 128MiB"
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
    sys.exit('duplicate keys in the arguments: %s' % dups)
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 b9-bs lines ----\n' + '\n'.join(add) + '\n')
PY
echo "node: conf $N/conf; yaml tail:"
sed -n '/^# ---- stage4 b9-bs lines/,$p' "$N/conf/cassandra.yaml" | grep -v '^ *- \|^ *parameters\|class_name' | tr '\n' ';' ; echo
