#!/usr/bin/env bash
# usage: make-node-yaml.sh <pct|default>   (run in the clone root)
# Rebuilds conf/cassandra.yaml from the tag plus this run's lines (case 9b): the data directory on the loop-mounted filesystem and,
# unless "default", the knob. Neither entry is in the shipped file (case section 4), so both are appended. Nothing else is changed.
set -euo pipefail
pct=${1:?pct or default}
git show HEAD:conf/cassandra.yaml > conf/cassandra.yaml
{
  echo "data_file_directories:"
  echo "    - /mnt/stage4-data/data"
  [ "$pct" = default ] || echo "max_space_usable_for_compactions_in_percentage: $pct"
} >> conf/cassandra.yaml
echo "yaml for pct=$pct: $(tail -4 conf/cassandra.yaml | tr '\n' ';')"
