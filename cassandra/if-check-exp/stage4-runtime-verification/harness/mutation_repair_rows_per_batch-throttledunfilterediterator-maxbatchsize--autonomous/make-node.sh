#!/usr/bin/env bash
# usage: make-node.sh <A|B>      (case B3a as amended 2026-10-27)
# Builds $R/<node>/conf (R=~/stage4-mrb) from the run copy's conf/: the tag's cassandra.yaml with this node's lines (cluster, loopback
# address, one token, auto_bootstrap false, storage_port 7010, every directory under $R/<node>/, cdc_enabled true, memtable
# off-heap buffers with a 3 GiB off-heap space so the received data does not sit on the heap) and cassandra-env.sh with JMX_PORT
# set (A 7102, B 7103). Nothing in the run copy is changed. Adapted from the repair_session_space harness' make-node-yaml.sh.
set -euo pipefail
node=${1:?A|B}
C=${CASSANDRA_HOME:-$HOME/c4-mrb}; R=${R:-$HOME/stage4-mrb}; N=$R/$node
case $node in
  A) addr=127.0.0.2; jmx=7102; tok=-3074457345618258603 ;;
  B) addr=127.0.0.3; jmx=7103; tok=3074457345618258602 ;;
  *) echo "unknown node $node" >&2; exit 2 ;;
esac
mkdir -p "$N/logs" "$N/data" "$N/commitlog" "$N/hints" "$N/saved_caches" "$N/cdc_raw"
rm -rf "$N/conf"; cp -r "$C/conf" "$N/conf"
git -C "$C" show HEAD:conf/cassandra-env.sh > "$N/conf/cassandra-env.sh"
sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$jmx\"/" "$N/conf/cassandra-env.sh"
grep -q "^JMX_PORT=\"$jmx\"" "$N/conf/cassandra-env.sh" || { echo "JMX_PORT line not replaced" >&2; exit 1; }
cat > "$N/lines.yaml" <<EOL
cluster_name: stage4-mrb
num_tokens: 1
initial_token: $tok
auto_bootstrap: false
storage_port: 7010
listen_address: $addr
rpc_address: $addr
seed_provider:
  - class_name: org.apache.cassandra.locator.SimpleSeedProvider
    parameters:
      - seeds: "127.0.0.2:7010"
data_file_directories:
    - $N/data
commitlog_directory: $N/commitlog
hints_directory: $N/hints
saved_caches_directory: $N/saved_caches
cdc_raw_directory: $N/cdc_raw
cdc_enabled: true
memtable_allocation_type: offheap_buffers
memtable_offheap_space: 3072MiB
EOL
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
        if skip: continue
    elif skip and (l.startswith((' ', '\t', '-')) or l.strip() == '' or l.lstrip().startswith('#')):
        continue
    else:
        skip = False
    out.append(l)
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 mrb lines ----\n' + '\n'.join(add) + '\n')
PY
echo "node $node: conf $N/conf, JMX $jmx, address $addr, token $tok"
