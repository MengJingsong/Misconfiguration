#!/usr/bin/env bash
# usage (in the clone root): make-node-yaml.sh <label> <root>
# Builds the node's own configuration directory <root>/conf (a copy of the clone's conf/, which this script does not modify, as
# CASSANDRA_CONF) with cassandra.yaml rebuilt from the tag and the hold-fixed settings of case 9b: read_request_timeout and
# range_request_timeout 120000ms, native_transport_timeout 180000ms; one data directory, commit log, hints, saved caches and
# cdc_raw under <root> (pc57 is shared with another session's node, which keeps its own directories). concurrent_reads stays
# 32. The knob is a JVM property, not a yaml key, so the yaml is the same at every value.
set -euo pipefail
label=$1; root=$2
mkdir -p "$root"
rm -rf "$root/conf"; cp -r conf "$root/conf"
y=$root/conf/cassandra.yaml
git show HEAD:conf/cassandra.yaml > "$y"
sed -i -e 's/^read_request_timeout: .*/read_request_timeout: 120000ms/' -e 's/^range_request_timeout: .*/range_request_timeout: 120000ms/' "$y"
cat >> "$y" <<YAML

# stage4 mmk $label
native_transport_timeout: 180000ms
data_file_directories:
    - $root/data
commitlog_directory: $root/commitlog
hints_directory: $root/hints
saved_caches_directory: $root/saved_caches
cdc_raw_directory: $root/cdc_raw
YAML
grep -q '^read_request_timeout: 120000ms$' "$y" && grep -q '^range_request_timeout: 120000ms$' "$y" || { echo "make-node-yaml: edit failed" >&2; exit 2; }
echo "yaml for $label:"; diff <(git show HEAD:conf/cassandra.yaml) "$y" | grep '^[<>]' | tr '\n' ' ' || true
