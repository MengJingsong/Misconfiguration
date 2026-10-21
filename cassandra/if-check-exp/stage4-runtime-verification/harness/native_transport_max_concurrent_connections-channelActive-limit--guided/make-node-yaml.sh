#!/usr/bin/env bash
# usage: make-node-yaml.sh [yaml_key=value ...]     (native_transport_max_concurrent_connections case 9b)
# Rebuilds ~/stage4-ncc/conf from the clone: a copy of conf/ whose cassandra.yaml is the tag's file with the one node's
# lines (loopback 127.0.0.1, every directory under ~/stage4-ncc/data, the 9b hold-fixed settings) and then the extra
# key=value arguments (the label's capacity and reserves). cassandra-env.sh is the tag's (JMX 7199). A key already set in
# the shipped yaml is removed first (with its continuation lines), so no key appears twice. Nothing in the clone is
# changed. Copied from the native_transport_receive_queue_capacity harness (2026-10-15) via the batch_size_fail_threshold harness
# (2026-10-20); only the directory and cluster names changed (2026-10-20).
set -euo pipefail
C=${CASSANDRA_HOME:-$HOME/cassandra-run1}; N=${NCC:-$HOME/stage4-ncc}; DD=$N/data
mkdir -p "$N/logs" "$DD/data" "$DD/commitlog" "$DD/hints" "$DD/saved_caches" "$DD/cdc_raw"
rm -rf "$N/conf"; cp -r "$C/conf" "$N/conf"
git -C "$C" show HEAD:conf/cassandra-env.sh > "$N/conf/cassandra-env.sh"
{
  echo "cluster_name: stage4-ncc"
  echo "num_tokens: 1"
  echo "auto_bootstrap: false"
  echo "listen_address: 127.0.0.1"
  echo "rpc_address: 127.0.0.1"
  echo "native_transport_port: 9042"
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
  echo "auto_snapshot: false"
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
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 ncc lines ----\n' + '\n'.join(add) + '\n')
PY
echo "node: conf $N/conf; yaml tail:"
sed -n '/^# ---- stage4 ncc lines/,$p' "$N/conf/cassandra.yaml" | grep -v '^ *- \|^ *parameters\|class_name' | tr '\n' ';' ; echo
