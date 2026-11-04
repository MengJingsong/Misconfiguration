#!/usr/bin/env bash
# usage: make-node-yaml.sh <A|B> [yaml_key=value ...]                                  (case B3a)
# Rebuilds ~/stage4-wbs/<node>/conf from the clone: a copy of conf/ whose cassandra.yaml is the tag's file with this
# node's lines and then the extra key=value arguments. B3a lines for both nodes: num_tokens 1 (one token each, A at the
# minimum, B at 0), hinted_handoff_enabled true, max_hint_window 3h, hints_directory under the node's folder,
# max_hints_file_size 128MiB, hints_flush_period 1000ms, max_hints_size_per_host 0MiB; plus the loopback addresses
# (environment deviation: one host, A = 127.0.0.2 JMX 7102, the seed; B = 127.0.0.3 JMX 7103), SimpleSnitch, every
# directory under ~/stage4-wbs/<node>/ on local disk. cassandra-env.sh gets JMX_PORT; jvm11-server.options gets
# -XX:MaxDirectMemorySize=1g and -XX:NativeMemoryTracking=summary (B3a; the heap, 2 GiB, is MAX_HEAP_SIZE in
# cluster-run.py; the GC log is cassandra-env.sh's default ${CASSANDRA_LOG_DIR}/gc.log). A key already set in the shipped
# yaml is removed first, so no key appears twice. Nothing in the clone is changed. From the
# internode_max_message_size-inferMessageSize harness's make-node-yaml.sh.
set -euo pipefail
node=${1:?A|B}; shift 1
C=${CASSANDRA_HOME:-$HOME/cassandra-run1}; N=${WBS:-$HOME/stage4-wbs}/$node
case $node in
  A) addr=127.0.0.2; jmx=7102; tok=-9223372036854775808 ;;
  B) addr=127.0.0.3; jmx=7103; tok=0 ;;
  *) echo "unknown node $node" >&2; exit 2 ;;
esac
mkdir -p "$N/logs" "$N/data" "$N/commitlog" "$N/hints" "$N/saved_caches" "$N/cdc_raw"
rm -rf "$N/conf"; cp -r "$C/conf" "$N/conf"
git -C "$C" show HEAD:conf/cassandra-env.sh > "$N/conf/cassandra-env.sh"
sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$jmx\"/" "$N/conf/cassandra-env.sh"
grep -q "^JMX_PORT=\"$jmx\"" "$N/conf/cassandra-env.sh" || { echo "JMX_PORT line not replaced" >&2; exit 1; }
git -C "$C" show HEAD:conf/jvm11-server.options > "$N/conf/jvm11-server.options"
printf '\n# stage4 wbs (B3a)\n-XX:MaxDirectMemorySize=1g\n-XX:NativeMemoryTracking=summary\n' >> "$N/conf/jvm11-server.options"
{
  echo "cluster_name: stage4-wbs"
  echo "num_tokens: 1"
  echo "initial_token: $tok"
  echo "endpoint_snitch: SimpleSnitch"
  echo "listen_address: $addr"
  echo "rpc_address: $addr"
  echo "seed_provider:"
  echo "  - class_name: org.apache.cassandra.locator.SimpleSeedProvider"
  echo "    parameters:"
  echo "      - seeds: \"127.0.0.2:7000\""
  echo "data_file_directories:"
  echo "    - $N/data"
  echo "commitlog_directory: $N/commitlog"
  echo "hints_directory: $N/hints"
  echo "saved_caches_directory: $N/saved_caches"
  echo "cdc_raw_directory: $N/cdc_raw"
  echo "hinted_handoff_enabled: true"
  echo "max_hint_window: 3h"
  echo "max_hints_file_size: 128MiB"
  echo "hints_flush_period: 1000ms"
  echo "max_hints_size_per_host: 0MiB"
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
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 wbs lines ----\n' + '\n'.join(add) + '\n')
PY
echo "node $node: conf $N/conf, JMX $jmx, address $addr, token $tok; yaml tail:"
sed -n '/^# ---- stage4 wbs lines/,$p' "$N/conf/cassandra.yaml" | grep -v '^ *- \|^ *parameters\|class_name' | tr '\n' ';' ; echo
