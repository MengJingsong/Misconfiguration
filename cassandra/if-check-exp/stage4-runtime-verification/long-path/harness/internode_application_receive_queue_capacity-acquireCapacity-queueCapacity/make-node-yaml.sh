#!/usr/bin/env bash
# usage: make-node-yaml.sh <R|S1|S2|S3|S4> [yaml_key=value ...]     (case 9b, amended 2026-10-14)
# Rebuilds ~/stage4-rqc/<node>/conf from the clone: a copy of conf/ whose cassandra.yaml is the tag's file with this
# node's lines (cluster, loopback address, token, every directory under ~/stage4-rqc/<node>/, the 9b hold-fixed settings)
# and then the extra key=value arguments, and whose cassandra-env.sh has JMX_PORT set to the node's port (7102-7106).
# A key already set in the shipped yaml is removed first (with its continuation lines), so no key appears twice. Nothing
# in the clone is changed. Adapted from the max_hints_size_per_host harness (five nodes, evenly spaced Murmur3 tokens).
set -euo pipefail
node=${1:?R|S1|S2|S3|S4}; shift 1
C=${CASSANDRA_HOME:-$HOME/cassandra-run1}; N=${RQC:-$HOME/stage4-rqc}/$node
# data, commit log, hints, caches on RQC_DATA (run 1: a tmpfs at /mnt/stage4-rqc, 9b corrected 2026-10-15): with five
# nodes applying every write on this host's spinning disk, flushes stalled every node's writes past the 10 s timeout
DD=${RQC_DATA:-/mnt/stage4-rqc}/$node
case $node in
  R)  addr=127.0.0.2; jmx=7102; tok=-9223372036854775808 ;;
  S1) addr=127.0.0.3; jmx=7103; tok=-5534023222112865485 ;;
  S2) addr=127.0.0.4; jmx=7104; tok=-1844674407370955162 ;;
  S3) addr=127.0.0.5; jmx=7105; tok=1844674407370955161 ;;
  S4) addr=127.0.0.6; jmx=7106; tok=5534023222112865484 ;;
  *) echo "unknown node $node" >&2; exit 2 ;;
esac
mountpoint -q "$(dirname "$DD")" || [ -n "${RQC_DATA:-}" ] || { echo "$(dirname "$DD") is not mounted" >&2; exit 1; }
mkdir -p "$N/logs" "$DD/data" "$DD/commitlog" "$DD/hints" "$DD/saved_caches" "$DD/cdc_raw"
rm -rf "$N/conf"; cp -r "$C/conf" "$N/conf"
git -C "$C" show HEAD:conf/cassandra-env.sh > "$N/conf/cassandra-env.sh"
sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$jmx\"/" "$N/conf/cassandra-env.sh"
grep -q "^JMX_PORT=\"$jmx\"" "$N/conf/cassandra-env.sh" || { echo "JMX_PORT line not replaced" >&2; exit 1; }
{
  echo "cluster_name: stage4-rqc"
  echo "num_tokens: 1"
  echo "initial_token: $tok"
  echo "auto_bootstrap: false"
  echo "storage_port: 7010"
  echo "listen_address: $addr"
  echo "rpc_address: $addr"
  echo "seed_provider:"
  echo "  - class_name: org.apache.cassandra.locator.SimpleSeedProvider"
  echo "    parameters:"
  echo "      - seeds: \"127.0.0.2:7010\""
  echo "data_file_directories:"
  echo "    - $DD/data"
  echo "commitlog_directory: $DD/commitlog"
  echo "hints_directory: $DD/hints"
  echo "saved_caches_directory: $DD/saved_caches"
  echo "cdc_raw_directory: $DD/cdc_raw"
  echo "write_request_timeout: 10000ms"
  echo "auto_snapshot: false"
  [ "$node" != R ] && echo "native_transport_max_threads: 512"
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
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 rqc lines ----\n' + '\n'.join(add) + '\n')
PY
echo "node $node: conf $N/conf, JMX $jmx, address $addr, token $tok; yaml tail:"
sed -n '/^# ---- stage4 rqc lines/,$p' "$N/conf/cassandra.yaml" | grep -v '^ *- \|^ *parameters\|class_name' | tr '\n' ';' ; echo
