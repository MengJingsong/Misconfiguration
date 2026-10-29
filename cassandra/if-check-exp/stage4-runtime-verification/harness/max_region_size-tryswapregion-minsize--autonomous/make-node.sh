#!/usr/bin/env bash
# usage: make-node.sh <memtable_allocation_type offheap_objects|heap_buffers> <memtable_offheap_space e.g. 512MiB> [cleanup_threshold|none]   (case B3a, 2026-10-28)
# Builds $T/conf (T=~/stage4-tmp/mrs/node) from the run copy's conf/: the tag's cassandra.yaml with, appended, a single node on 127.0.0.1,
# every directory under $T on local disk, the given memtable_allocation_type and memtable_offheap_space, memtable_heap_space 512MiB,
# commitlog_total_space 8GiB, and memtable_cleanup_threshold only when given. Adapted from the row_overhead_size harness' make-node.sh.
# Nothing in the run copy changes.
set -euo pipefail
alloc=${1:?offheap_objects|heap_buffers}; off=${2:?512MiB|32MiB}; thr=${3:-none}
C=${CASSANDRA_HOME:-$HOME/s4-mrs}; T=${T:-$HOME/stage4-tmp/mrs/node}
mkdir -p "$T/logs" "$T/data" "$T/commitlog" "$T/hints" "$T/saved_caches" "$T/cdc_raw"
rm -rf "$T/conf"; cp -r "$C/conf" "$T/conf"
git -C "$C" show HEAD:conf/cassandra.yaml > "$T/shipped.yaml"
cat > "$T/lines.yaml" <<EOL
cluster_name: stage4-mrs
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
memtable_allocation_type: $alloc
memtable_offheap_space: $off
memtable_heap_space: 512MiB
commitlog_total_space: 8GiB
EOL
[ "$thr" != none ] && echo "memtable_cleanup_threshold: $thr" >> "$T/lines.yaml"
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
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 mrs lines ----\n' + '\n'.join(add) + '\n')
PY
echo "node conf $T/conf: alloc $alloc offheap $off cleanup $thr"
