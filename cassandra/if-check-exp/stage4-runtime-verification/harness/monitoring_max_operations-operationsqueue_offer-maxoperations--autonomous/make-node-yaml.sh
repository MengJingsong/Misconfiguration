#!/usr/bin/env bash
# usage: make-node-yaml.sh <tree> <node-dir> <fast|slow>     (monitoring_max_operations case, B3a)
# Rebuilds <node-dir>/conf from <tree>'s baseline conf (git HEAD) with every directory under <node-dir>.
#   slow = the shipped timeouts (used to load the data);  fast = read_request_timeout 1ms and slow_query_log_timeout 1ms (the measured arms).
# One node on 127.0.0.1, JMX 7199 (shipped default). The data directory is NOT touched.
set -euo pipefail
C=${1:?tree}; N=${2:?node dir}; mode=${3:?fast|slow}
mkdir -p "$N/logs" "$N/data" "$N/commitlog" "$N/hints" "$N/saved_caches" "$N/cdc_raw"
rm -rf "$N/conf"; cp -r "$C/conf" "$N/conf"
git -C "$C" show HEAD:conf/cassandra.yaml > "$N/conf/cassandra.yaml"
git -C "$C" show HEAD:conf/cassandra-env.sh > "$N/conf/cassandra-env.sh"
python3 - "$N" "$mode" <<'PY'
import re, sys
n, mode = sys.argv[1], sys.argv[2]
y = open(n + '/conf/cassandra.yaml').read()
for k in ('read_request_timeout', 'slow_query_log_timeout'):
    y = re.sub(r'^%s:.*\n' % k, '', y, flags=re.M)
y += f"""
# ---- stage4 mon lines ----
data_file_directories:
    - {n}/data
commitlog_directory: {n}/commitlog
hints_directory: {n}/hints
saved_caches_directory: {n}/saved_caches
cdc_raw_directory: {n}/cdc_raw
"""
if mode == 'fast':
    y += "read_request_timeout: 1ms\nslow_query_log_timeout: 1ms\n"
open(n + '/conf/cassandra.yaml', 'w').write(y)
PY
for k in data_file_directories commitlog_directory hints_directory saved_caches_directory cdc_raw_directory; do
  c=$(grep -c "^$k:" "$N/conf/cassandra.yaml" || true); [ "$c" -eq 1 ] || { echo "key $k appears $c times" >&2; exit 1; }
done
echo "yaml ($mode): $(sed -n '/^# ---- stage4 mon lines/,$p' "$N/conf/cassandra.yaml" | tr '\n' ';')"
