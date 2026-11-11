#!/usr/bin/env bash
# usage: make-node-conf.sh <S>     (B3a as amended 2026-10-26, repair_state_size setter case)
# Rebuilds $W/node-rss/n1/conf from the run clone: a copy of conf/ whose cassandra.yaml is the tag's file with this node's lines
# (cluster name, directories under $W/node-rss/n1/, repair_state_size: <S>) appended; a key already in the shipped yaml is removed
# first (with its continuation lines), so no key appears twice. cassandra-env.sh is the tag's (JMX 7199, local only).
# Nothing in the clone is changed. Adapted from harness/repair_session_max_tree_depth-setRepairSessionMaxTreeDepth-depth--autonomous/.
set -euo pipefail
source ~/Library/Caches/stage4/env.sh
S=${1:?repair_state_size}
C=${RSS_C:-$W/cassandra-run27}; N=${RSS_NODE:-$W/node-rss}/n1   # run 1 defaults; the 2026-10-28 re-run sets RSS_C and RSS_NODE
mkdir -p "$N/data" "$N/commitlog" "$N/hints" "$N/saved_caches" "$N/cdc_raw"
rm -rf "$N/conf"; cp -R "$C/conf" "$N/conf"
git -C "$C" show HEAD:conf/cassandra-env.sh > "$N/conf/cassandra-env.sh"
{
  echo "cluster_name: rss"
  echo "data_file_directories:"
  echo "    - $N/data"
  echo "commitlog_directory: $N/commitlog"
  echo "hints_directory: $N/hints"
  echo "saved_caches_directory: $N/saved_caches"
  echo "cdc_raw_directory: $N/cdc_raw"
  echo "repair_state_size: $S"
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
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 rss lines ----\n' + '\n'.join(add) + '\n')
PY
echo "conf $N/conf; yaml tail: $(sed -n '/^# ---- stage4 rss lines/,$p' "$N/conf/cassandra.yaml" | tr '\n' ';')"
