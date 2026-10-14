#!/usr/bin/env bash
# usage (in the clone root): make-unit-yaml.sh <label> <value|none>   e.g. make-unit-yaml.sh 256k 256KiB
# Copies test/conf/cassandra.yaml to build/test/mms-<label>.yaml and appends max_mutation_size (case 9c); nothing for none.
set -euo pipefail
label=$1; val=$2; y=build/test/mms-$label.yaml
mkdir -p build/test; cp test/conf/cassandra.yaml "$y"
[ "$val" != none ] && printf '\nmax_mutation_size: %s\n' "$val" >> "$y"
echo "$PWD/$y"
