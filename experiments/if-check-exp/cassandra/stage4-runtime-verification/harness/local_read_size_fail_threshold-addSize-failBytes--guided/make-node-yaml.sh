#!/usr/bin/env bash
# usage: make-node-yaml.sh <label> <bytes|none>   (run in the clone root)
# Rebuilds conf/cassandra.yaml from the tag plus this arm's lines (case 9b): the master switch, the warn limit at 1 B (except for
# the default control) and the fail limit. Nothing else is changed.
set -euo pipefail
label=$1; val=$2
git show HEAD:conf/cassandra.yaml > conf/cassandra.yaml
if [ "$val" != none ]; then
  printf 'read_thresholds_enabled: true\nlocal_read_size_warn_threshold: 1B\nlocal_read_size_fail_threshold: %sB\n' "$val" >> conf/cassandra.yaml
else
  printf 'read_thresholds_enabled: true\n' >> conf/cassandra.yaml
fi
echo "yaml for $label: $(tail -3 conf/cassandra.yaml | tr '\n' ';')"
