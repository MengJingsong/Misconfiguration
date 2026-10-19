#!/usr/bin/env bash
# usage (in the clone root): make-node-yaml.sh <MiB|default>
# Rebuilds conf/cassandra.yaml from the tag with the hold-fixed settings of case 9b (amended 2026-10-14): concurrent_reads 256,
# native_transport_max_threads 256, and file_cache_size: <MiB>MiB (no line for "default": the node auto-sizes it).
set -euo pipefail
v=$1
y=conf/cassandra.yaml
git show HEAD:conf/cassandra.yaml > $y
sed -i -e 's/^concurrent_reads: 32$/concurrent_reads: 256/' -e 's/^# native_transport_max_threads: 128$/native_transport_max_threads: 256/' $y
grep -q '^concurrent_reads: 256$' $y && grep -q '^native_transport_max_threads: 256$' $y || { echo "make-node-yaml: edit failed" >&2; exit 2; }
grep -q '^file_cache_size:' $y && { echo "make-node-yaml: the tag's yaml already sets file_cache_size" >&2; exit 2; }
if [ "$v" != default ]; then
  echo "file_cache_size: ${v}MiB" >> $y
fi
echo "yaml for file_cache_size=$v:"; diff <(git show HEAD:conf/cassandra.yaml) $y | grep '^[<>]' || true
