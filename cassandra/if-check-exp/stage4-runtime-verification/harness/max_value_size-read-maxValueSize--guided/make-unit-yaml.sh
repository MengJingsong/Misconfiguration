#!/usr/bin/env bash
# usage (in the clone root): make-unit-yaml.sh <label> <value>   e.g. make-unit-yaml.sh range-hi 2048MiB
# Copies test/conf/cassandra.yaml to build/test/mvs-<label>.yaml and appends max_value_size (case 9b, range controls only).
set -euo pipefail
label=$1; val=$2; y=build/test/mvs-$label.yaml
mkdir -p build/test; cp test/conf/cassandra.yaml "$y"
printf '\nmax_value_size: %s\n' "$val" >> "$y"
echo "$PWD/$y"
