#!/usr/bin/env bash
# usage: make-node-yaml.sh <A|B> [yaml_key=value ...]                                  (B3a)
# Rebuilds $HWB_NODES/<node>/conf from the build copy $CASSANDRA_HOME (a copy made by copy-source.sh, or a variant of it):
# a copy of conf/ whose cassandra.yaml is the tag's file with this node's lines and then the extra key=value arguments
# (a later value overrides an earlier one, a key set in the shipped yaml is removed first, so no key appears twice).
# Lines for both nodes: num_tokens 1 (A at the minimum token, B at 0), hinted_handoff_enabled true, max_hint_window 3h,
# max_hints_file_size 128MiB, max_hints_size_per_host 0MiB (B3a), the loopback addresses (one host: A = 127.0.0.2 JMX 7102,
# the seed; B = 127.0.0.3 JMX 7103), SimpleSnitch, every directory under $HWB_NODES/<node>/ on local disk. cassandra-env.sh
# gets JMX_PORT; jvm11-server.options gets -XX:MaxDirectMemorySize=1g and -XX:NativeMemoryTracking=summary (B3a; the heap,
# 2 GiB, is MAX_HEAP_SIZE in cluster-run.py). Nothing in the build copy is changed. From the WRITE_BUFFER_SIZE-append-remaining
# harness's make-node-yaml.sh.
set -euo pipefail
node=${1:?A|B}; shift 1
C=${CASSANDRA_HOME:?}; N=${HWB_NODES:?}/$node
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
printf '\n# stage4 hwb (B3a)\n-XX:MaxDirectMemorySize=1g\n-XX:NativeMemoryTracking=summary\n' >> "$N/conf/jvm11-server.options"
{
  echo "cluster_name: stage4-hwb"
  echo "num_tokens: 1"
  echo "initial_token: $tok"
  echo "endpoint_snitch: SimpleSnitch"
  echo "listen_address: $addr"
  echo "rpc_address: $addr"
  echo "data_file_directories:"
  echo "    - $N/data"
  echo "commitlog_directory: $N/commitlog"
  echo "hints_directory: $N/hints"
  echo "saved_caches_directory: $N/saved_caches"
  echo "cdc_raw_directory: $N/cdc_raw"
  echo "hinted_handoff_enabled: true"
  echo "max_hint_window: 3h"
  echo "max_hints_file_size: 128MiB"
  echo "max_hints_size_per_host: 0MiB"
  for kv in "$@"; do echo "${kv%%=*}: ${kv#*=}"; done
} > "$N/lines.yaml"
git -C "$C" show HEAD:conf/cassandra.yaml > "$N/shipped.yaml"
python3 - "$N" <<'PY'
import re, sys
n = sys.argv[1]
add = open(n + '/lines.yaml').read().splitlines()
d = {}
for l in add:                       # later lines override earlier ones; the first position is kept
    if re.match(r'^[A-Za-z_]+:', l):
        d[l.split(':', 1)[0]] = l
    else:
        d.setdefault('__cont__%d' % len(d), l)
# the list-valued keys keep their continuation line right after the key
out_add, i = [], 0
lines = add
res = []
seen = set()
for idx, l in enumerate(lines):
    m = re.match(r'^([A-Za-z_]+):', l)
    if m:
        k = m.group(1)
        if k in seen:
            continue
        seen.add(k)
        res.append(d[k])
        if k == 'data_file_directories':
            res.append(lines[idx + 1])
keys = {l.split(':', 1)[0] for l in res if re.match(r'^[A-Za-z_]+:', l)}
keys.add('seed_provider')
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
seeds = ['seed_provider:', '  - class_name: org.apache.cassandra.locator.SimpleSeedProvider',
         '    parameters:', '      - seeds: "127.0.0.2:7000"']
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 hwb lines ----\n' + '\n'.join(res + seeds) + '\n')
PY
echo "node $node: conf $N/conf, JMX $jmx, address $addr, token $tok; yaml tail:"
sed -n '/^# ---- stage4 hwb lines/,$p' "$N/conf/cassandra.yaml" | grep -v '^ *- \|^ *parameters\|class_name' | tr '\n' ';' ; echo
