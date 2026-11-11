#!/usr/bin/env bash
# usage: make-node-conf.sh     (B3a as amended 2026-10-26, batchlog page-size case)
# Rebuilds $W/node-bl/n1/conf from the run clone: a copy of conf/ whose cassandra.yaml is the tag's file with B3a's lines
# (cluster name, directories under $W/node-bl/n1/, addresses, batch thresholds, offheap memtables, default replay throttle)
# appended; a key already in the shipped yaml is removed first (with its continuation lines), so no key appears twice.
# B3a's top-level `seeds:` line is not a cassandra.yaml key; the shipped seed_provider (127.0.0.1:7000) is kept instead.
# cassandra-env.sh is the tag's (JMX 7199, local only). Nothing in the clone is changed.
set -euo pipefail
source ~/Library/Caches/stage4/env.sh
C=$W/cassandra-run28; N=$W/node-bl/n1
mkdir -p "$N/data" "$N/commitlog" "$N/hints" "$N/saved_caches" "$N/cdc_raw"
rm -rf "$N/conf"; cp -R "$C/conf" "$N/conf"
git -C "$C" show HEAD:conf/cassandra-env.sh > "$N/conf/cassandra-env.sh"
{
  echo "cluster_name: blpage"
  echo "num_tokens: 16"
  echo "listen_address: 127.0.0.1"
  echo "rpc_address: 127.0.0.1"
  echo "data_file_directories:"
  echo "    - $N/data"
  echo "commitlog_directory: $N/commitlog"
  echo "hints_directory: $N/hints"
  echo "saved_caches_directory: $N/saved_caches"
  echo "cdc_raw_directory: $N/cdc_raw"
  echo "batch_size_warn_threshold: 2048KiB"
  echo "batch_size_fail_threshold: 4096KiB"
  echo "memtable_allocation_type: offheap_objects"
  echo "memtable_heap_space: 512MiB"
  echo "memtable_offheap_space: 2048MiB"
  echo "memtable_cleanup_threshold: 0.9"
  echo "batchlog_replay_throttle: 1024KiB"
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
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 bl lines ----\n' + '\n'.join(add) + '\n')
PY
echo "conf $N/conf; yaml tail: $(sed -n '/^# ---- stage4 bl lines/,$p' "$N/conf/cassandra.yaml" | tr '\n' ';')"
