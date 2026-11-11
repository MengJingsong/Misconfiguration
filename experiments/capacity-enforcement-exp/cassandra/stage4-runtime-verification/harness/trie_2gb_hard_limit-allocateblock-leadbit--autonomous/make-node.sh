#!/usr/bin/env bash
# usage: make-node.sh <offheap_space_MiB> [cleanup_threshold=0.99]      (case B3a, as amended 2026-10-27)
# Builds $T/conf (T=~/stage4-trie2gb/node) from the clone's conf/: the tag's cassandra.yaml with, appended, a single node on
# 127.0.0.1, every directory under $T on local disk, memtable_allocation_type offheap_buffers, memtable_offheap_space as given,
# memtable_heap_space 8192MiB, memtable_cleanup_threshold 0.99 (amendment A3). Nothing in the clone is changed.
set -euo pipefail
off=${1:?offheap MiB}; thr=${2:-0.99}
C=${CASSANDRA_HOME:-$HOME/cassandra-run1}; T=${T:-$HOME/stage4-trie2gb/node}
mkdir -p "$T/logs" "$T/data" "$T/commitlog" "$T/hints" "$T/saved_caches" "$T/cdc_raw"
rm -rf "$T/conf"; cp -r "$C/conf" "$T/conf"
git -C "$C" show HEAD:conf/cassandra.yaml > "$T/shipped.yaml"
cat > "$T/lines.yaml" <<EOL
cluster_name: stage4-trie2gb
num_tokens: 1
endpoint_snitch: SimpleSnitch
listen_address: 127.0.0.1
rpc_address: 127.0.0.1
seed_provider:
  - class_name: org.apache.cassandra.locator.SimpleSeedProvider
    parameters:
      - seeds: "127.0.0.1:7000"
data_file_directories:
    - $T/data
commitlog_directory: $T/commitlog
hints_directory: $T/hints
saved_caches_directory: $T/saved_caches
cdc_raw_directory: $T/cdc_raw
memtable_allocation_type: offheap_buffers
memtable_offheap_space: ${off}MiB
memtable_heap_space: 8192MiB
memtable_cleanup_threshold: $thr
EOL
python3 - "$T" <<'PY'
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
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 trie2gb lines ----\n' + '\n'.join(add) + '\n')
PY
echo "node conf $T/conf: offheap ${off}MiB cleanup $thr"
