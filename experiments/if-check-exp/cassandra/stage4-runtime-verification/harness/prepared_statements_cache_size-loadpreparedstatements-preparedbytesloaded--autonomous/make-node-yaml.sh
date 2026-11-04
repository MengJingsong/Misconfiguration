#!/usr/bin/env bash
# usage: make-node-yaml.sh <tree> <MiB> <node-dir>      (preload-threshold case, B3a)
# Rebuilds <node-dir>/conf from <tree>'s conf (baseline cassandra.yaml and cassandra-env.sh from git HEAD) with every directory under <node-dir>
# and prepared_statements_cache_size: <MiB>MiB. One node on 127.0.0.1, JMX 7199 (shipped default). Data directory is NOT touched.
set -euo pipefail
C=${1:?tree}; v=${2:?MiB}; N=${3:?node dir}
mkdir -p "$N/logs" "$N/data" "$N/commitlog" "$N/hints" "$N/saved_caches" "$N/cdc_raw"
rm -rf "$N/conf"; cp -r "$C/conf" "$N/conf"
git -C "$C" show HEAD:conf/cassandra.yaml > "$N/conf/cassandra.yaml"
git -C "$C" show HEAD:conf/cassandra-env.sh > "$N/conf/cassandra-env.sh"
python3 - "$N" "$v" <<'PY'
import re, sys
n, v = sys.argv[1], sys.argv[2]
y = open(n + '/conf/cassandra.yaml').read()
y = re.sub(r'^prepared_statements_cache_size:.*\n', '', y, flags=re.M)
y += f"""
# ---- stage4 pthr lines ----
data_file_directories:
    - {n}/data
commitlog_directory: {n}/commitlog
hints_directory: {n}/hints
saved_caches_directory: {n}/saved_caches
cdc_raw_directory: {n}/cdc_raw
prepared_statements_cache_size: {v}MiB
"""
open(n + '/conf/cassandra.yaml', 'w').write(y)
PY
for k in data_file_directories commitlog_directory hints_directory saved_caches_directory cdc_raw_directory prepared_statements_cache_size; do
  c=$(grep -c "^$k:" "$N/conf/cassandra.yaml" || true); [ "$c" -eq 1 ] || { echo "key $k appears $c times" >&2; exit 1; }
done
echo "yaml for prepared_statements_cache_size=$v: $(sed -n '/^# ---- stage4 pthr lines/,$p' "$N/conf/cassandra.yaml" | tr '\n' ';')"
