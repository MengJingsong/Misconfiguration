#!/usr/bin/env bash
# usage: make-node-yaml.sh <B|A> <min_free_space_per_drive, e.g. 50MiB>     (case 9b, amended 2026-10-15)
# Rebuilds ~/stage4-dds/conf from the clone: a copy of conf/ whose cassandra.yaml is the tag's file with this run's lines
# (cluster name, partitioner, one token, every directory under ~/stage4-dds/ except data on /mnt/stage4-dds/data,
# concurrent_compactors 1, min_free_space_per_drive). A key already set in the shipped yaml is removed first (with its
# continuation lines), so no key appears twice. Nothing in the clone is changed. Adapted from the repair_session_space harness.
set -euo pipefail
arm=${1:?B|A}; m=${2:?min_free_space_per_drive}
C=${CASSANDRA_HOME:-$HOME/cassandra-run3}; N=${DDS:-$HOME/stage4-dds}
case $arm in
  B) part=org.apache.cassandra.dht.ByteOrderedPartitioner; tok=00; name=stage4-dds-bop ;;
  A) part=org.apache.cassandra.dht.Murmur3Partitioner; tok=0; name=stage4-dds-m3 ;;
  *) echo "unknown arm $arm" >&2; exit 2 ;;
esac
mkdir -p "$N/logs" "$N/commitlog" "$N/hints" "$N/saved_caches" "$N/cdc_raw"
rm -rf "$N/conf"; cp -r "$C/conf" "$N/conf"
git -C "$C" show HEAD:conf/cassandra-env.sh > "$N/conf/cassandra-env.sh"
{
  echo "cluster_name: $name"
  echo "partitioner: $part"
  echo "num_tokens: 1"
  echo "initial_token: $tok"
  echo "data_file_directories:"
  echo "    - /mnt/stage4-dds/data"
  echo "commitlog_directory: $N/commitlog"
  echo "hints_directory: $N/hints"
  echo "saved_caches_directory: $N/saved_caches"
  echo "cdc_raw_directory: $N/cdc_raw"
  echo "concurrent_compactors: 1"
  echo "min_free_space_per_drive: $m"
} > "$N/lines.yaml"
git -C "$C" show HEAD:conf/cassandra.yaml > "$N/shipped.yaml"
python3 - "$N" <<'PY'
import re, sys
n = sys.argv[1]
add = open(n + '/lines.yaml').read().splitlines()
keys = {l.split(':', 1)[0] for l in add if re.match(r'^[A-Za-z_]+:', l)}
keys.add('allocate_tokens_for_local_replication_factor')     # one node with an initial_token: the allocator is not used
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
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 dds lines ----\n' + '\n'.join(add) + '\n')
PY
echo "arm $arm: conf $N/conf, partitioner $part, token $tok, m $m; yaml tail: $(sed -n '/^# ---- stage4 dds lines/,$p' "$N/conf/cassandra.yaml" | tr '\n' ';')"
