#!/usr/bin/env bash
# usage (in the clone root): make-node-yaml.sh <label>
# Rebuilds conf/cassandra.yaml from the tag with the hold-fixed settings of case 9b: column_index_size 4KiB (uncommented),
# key_cache_size 8MiB. column_index_cache_size stays at the shipped 2KiB: the run changes it over JMX.
set -euo pipefail
label=$1
y=conf/cassandra.yaml
git show HEAD:conf/cassandra.yaml > $y
sed -i -e 's/^# column_index_size: 4KiB$/column_index_size: 4KiB/' -e 's/^key_cache_size:.*$/key_cache_size: 8MiB/' $y
grep -q '^column_index_size: 4KiB$' $y && grep -q '^key_cache_size: 8MiB$' $y || { echo "make-node-yaml: edit failed" >&2; exit 2; }
echo "yaml for $label:"; diff <(git show HEAD:conf/cassandra.yaml) $y | grep '^[<>]' || true
