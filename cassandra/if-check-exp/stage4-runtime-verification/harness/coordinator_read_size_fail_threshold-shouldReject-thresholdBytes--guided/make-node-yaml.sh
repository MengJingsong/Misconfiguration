#!/usr/bin/env bash
# usage: make-node-yaml.sh   (run in the clone root)
# Rebuilds conf/cassandra.yaml from the tag plus the case's one line (9b): the master switch. The limit is set live over JMX.
set -euo pipefail
git show HEAD:conf/cassandra.yaml > conf/cassandra.yaml
printf 'read_thresholds_enabled: true\n' >> conf/cassandra.yaml
echo "yaml: $(tail -1 conf/cassandra.yaml); diff vs tag: $(git diff --stat conf/cassandra.yaml | tail -1)"
