#!/usr/bin/env bash
# usage: make-node-yaml.sh <MiB|default>    (networking_cache_size case 9b/9c)
# Rebuilds ~/stage4-ncs/conf from the clone: the tag's cassandra.yaml with every directory under ~/stage4-ncs/ and, unless
# "default", networking_cache_size: <MiB>MiB. Nothing else changes (memtable_allocation_type stays heap_buffers, the default).
set -euo pipefail
v=${1:?MiB or default}
C=${CASSANDRA_HOME:-$HOME/cassandra-run3}; N=${NCS:-$HOME/stage4-ncs}
mkdir -p "$N/logs" "$N/data" "$N/commitlog" "$N/hints" "$N/saved_caches" "$N/cdc_raw"
rm -rf "$N/conf"; cp -r "$C/conf" "$N/conf"
git -C "$C" show HEAD:conf/cassandra.yaml > "$N/conf/cassandra.yaml"
{
  echo "# ---- stage4 ncs lines ----"
  echo "data_file_directories:"
  echo "    - $N/data"
  echo "commitlog_directory: $N/commitlog"
  echo "hints_directory: $N/hints"
  echo "saved_caches_directory: $N/saved_caches"
  echo "cdc_raw_directory: $N/cdc_raw"
  [ "$v" = default ] || echo "networking_cache_size: ${v}MiB"
} >> "$N/conf/cassandra.yaml"
for k in data_file_directories commitlog_directory hints_directory saved_caches_directory cdc_raw_directory networking_cache_size; do
  c=$(grep -c "^$k:" "$N/conf/cassandra.yaml" || true); [ "$c" -le 1 ] || { echo "duplicate key $k" >&2; exit 1; }
done
echo "yaml for networking_cache_size=$v: $(sed -n '/^# ---- stage4 ncs lines/,$p' "$N/conf/cassandra.yaml" | tr '\n' ';')"
