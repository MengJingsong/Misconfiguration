#!/usr/bin/env bash
# usage: make-node-yaml.sh <label> <bytes|none> [stock-cache]   (run in the clone root)
# Rebuilds conf/cassandra.yaml from the tag plus this arm's lines (case 9b): the master switch, the warn limit at 1 B (except for
# the default control), the fail limit, column_index_size 1KiB (applied when an SSTable is written) and, unless "stock-cache",
# column_index_cache_size 4MiB. Nothing else is changed.
set -euo pipefail
label=$1; val=$2; stock=${3:-}
git show HEAD:conf/cassandra.yaml > conf/cassandra.yaml
{
  echo "read_thresholds_enabled: true"
  if [ "$val" != none ]; then
    echo "row_index_read_size_warn_threshold: 1B"
    echo "row_index_read_size_fail_threshold: ${val}B"
  fi
  echo "column_index_size: 1KiB"
  [ "$stock" = stock-cache ] || echo "column_index_cache_size: 4MiB"
} >> conf/cassandra.yaml
echo "yaml for $label: $(tail -5 conf/cassandra.yaml | tr '\n' ';')"
