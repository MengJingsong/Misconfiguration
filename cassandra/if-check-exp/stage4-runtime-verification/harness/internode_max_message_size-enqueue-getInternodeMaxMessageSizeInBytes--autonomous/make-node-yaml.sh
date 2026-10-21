#!/usr/bin/env bash
# usage: make-node-yaml.sh <A|B> [yaml_key=value ...]      (case B3a/B3b, with amendments R1 and R5 of 2026-10-20)
# Rebuilds $IME/<node>/conf from the clone: a copy of conf/ whose cassandra.yaml is the tag's file with this node's B3a
# lines and then the extra key=value arguments (the run's internode_max_message_size; none for the default run, R1):
#   cluster_name, num_tokens 1, SimpleSnitch, listen/rpc address (A = 127.0.0.2, the seed and the only coordinator;
#   B = 127.0.0.3), write_request_timeout 30s, hinted_handoff_enabled false (R5), every directory under $IME/<node>/
#   (default /mydata/stage4-ime, local disk of pc12).
# cassandra-env.sh: JMX_PORT A 7102, B 7103. jvm11-server.options: -XX:MaxDirectMemorySize=1G (B3a); the heap (1G,
# new size 256M) is set by cluster-run.py through MAX_HEAP_SIZE / HEAP_NEWSIZE. GC logging: cassandra-env.sh's default
# -Xlog:gc=info,heap*=trace,... to <log dir>/gc.log is kept. A key already in the shipped yaml is removed first, so no key
# appears twice. Nothing in the clone is changed. From the internode_max_message_size-inferMessageSize-size--autonomous
# harness's make-node-yaml.sh (addresses, ports, tokens, timeout and directory root changed).
set -euo pipefail
node=${1:?A|B}; shift 1
C=${CASSANDRA_HOME:-$HOME/cassandra-run1}; N=${IME:-/mydata/stage4-ime}/$node
case $node in
  A) addr=127.0.0.2; jmx=7102 ;;
  B) addr=127.0.0.3; jmx=7103 ;;
  *) echo "unknown node $node" >&2; exit 2 ;;
esac
mkdir -p "$N/logs" "$N/data" "$N/commitlog" "$N/hints" "$N/saved_caches" "$N/cdc_raw"
rm -rf "$N/conf"; cp -r "$C/conf" "$N/conf"
git -C "$C" show HEAD:conf/cassandra-env.sh > "$N/conf/cassandra-env.sh"
sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$jmx\"/" "$N/conf/cassandra-env.sh"
grep -q "^JMX_PORT=\"$jmx\"" "$N/conf/cassandra-env.sh" || { echo "JMX_PORT line not replaced" >&2; exit 1; }
git -C "$C" show HEAD:conf/jvm11-server.options > "$N/conf/jvm11-server.options"
printf '\n# stage4 ime (B3a)\n-XX:MaxDirectMemorySize=1G\n' >> "$N/conf/jvm11-server.options"
{
  echo "cluster_name: stage4-ime"
  echo "num_tokens: 1"
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
  echo "write_request_timeout: 30s"
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
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 ime lines ----\n' + '\n'.join(add) + '\n')
PY
echo "node $node: conf $N/conf, JMX $jmx, address $addr; yaml tail:"
sed -n '/^# ---- stage4 ime lines/,$p' "$N/conf/cassandra.yaml" | grep -v '^ *- \|^ *parameters\|class_name' | tr '\n' ';' ; echo
