#!/usr/bin/env bash
# usage: make-node-conf.sh [yaml_key=value ...]   (B3a as amended 2026-10-26, denylist_max_keys_per_table setter case)
# Rebuilds $W/node-dlmk/conf from the run clone: a copy of conf/ whose cassandra.yaml is the tag's file with this node's lines
# (single node 127.0.0.1, directories under $W/node-dlmk/) and then the extra key=value arguments. A key already set in the shipped
# yaml is removed first (with its continuation lines), so no key appears twice. Nothing in the clone is changed.
# Adapted from harness/repair_session_max_tree_depth-setRepairSessionMaxTreeDepth-depth--autonomous/make-node-conf.sh (one node).
set -euo pipefail
source ~/Library/Caches/stage4/env.sh
C=${DLMK_C:-$W/cassandra-run25}; N=${DLMK_NODE:-$W/node-dlmk}   # H1 2026-10-27: env overrides for the cluster re-run
mkdir -p "$N/data" "$N/commitlog" "$N/hints" "$N/saved_caches" "$N/cdc_raw"
rm -rf "$N/conf"; cp -R "$C/conf" "$N/conf"
{
  echo "cluster_name: dlmk"
  echo "listen_address: 127.0.0.1"
  echo "rpc_address: 127.0.0.1"
  echo "data_file_directories:"
  echo "    - $N/data"
  echo "commitlog_directory: $N/commitlog"
  echo "hints_directory: $N/hints"
  echo "saved_caches_directory: $N/saved_caches"
  echo "cdc_raw_directory: $N/cdc_raw"
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
        continue
    else:
        skip = False
    out.append(l)
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 dlmk lines ----\n' + '\n'.join(add) + '\n')
PY
echo "node: clone $C, conf $N/conf; yaml tail: $(sed -n '/^# ---- stage4 dlmk lines/,$p' "$N/conf/cassandra.yaml" | tr '\n' ';')"
