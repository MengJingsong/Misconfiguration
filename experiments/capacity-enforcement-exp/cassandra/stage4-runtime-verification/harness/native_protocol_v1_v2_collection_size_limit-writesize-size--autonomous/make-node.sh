#!/usr/bin/env bash
# usage: T=<node dir> make-node.sh <run copy> <extra-yaml-lines-file>   (B3a, 2026-10-28)
# Builds $T/conf from the run copy's conf/: the tag's cassandra.yaml with one node on 127.0.0.1, every directory under $T (local disk),
# plus the key: value lines of the extra file (they replace same-named keys). The run copy's conf/ is not changed. G1 and its flags stay (B3a: default).
set -euo pipefail
C=${1:?run copy}; X=${2:?extra yaml}; T=${T:?node dir}
mkdir -p "$T/logs" "$T/data" "$T/commitlog" "$T/hints" "$T/saved_caches" "$T/cdc_raw"
rm -rf "$T/conf"; cp -r "$C/conf" "$T/conf"
git -C "$C" show HEAD:conf/cassandra.yaml > "$T/shipped.yaml"
cat > "$T/lines.yaml" <<EOL
cluster_name: stage4-b34
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
EOL
cat "$X" >> "$T/lines.yaml"
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
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 lines ----\n' + '\n'.join(add) + '\n')
PY
echo "node conf $T/conf made from $C ($(grep -c . "$X") extra lines)"
