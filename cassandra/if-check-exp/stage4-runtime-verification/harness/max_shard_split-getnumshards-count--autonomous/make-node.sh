#!/usr/bin/env bash
# usage: make-node.sh [copy dir]   (case B3a, 2026-10-28; partitioner Murmur3 instead of ByteOrderedPartitioner, see the case file's audit amendment)
# One node on 127.0.0.1, all directories under $T (local disk), num_tokens 1, concurrent_compactors 1, compaction_throughput 0MiB/s, commitlog_sync periodic.
set -euo pipefail
C=${1:-$HOME/s4-ms}; T=${T:-$HOME/stage4-tmp/ms/node}
mkdir -p "$T/logs" "$T/data" "$T/commitlog" "$T/hints" "$T/saved_caches" "$T/cdc_raw"
rm -rf "$T/conf"; cp -r "$C/conf" "$T/conf"
git -C "$C" show HEAD:conf/cassandra.yaml > "$T/shipped.yaml"
cat > "$T/lines.yaml" <<EOL
cluster_name: stage4-ms
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
concurrent_compactors: 1
compaction_throughput: 0MiB/s
auto_snapshot: false
commitlog_sync: periodic
commitlog_sync_period: 10000ms
commitlog_total_space: 4GiB
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
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 ms lines ----\n' + '\n'.join(add) + '\n')
PY
echo "node conf $T/conf"
