#!/usr/bin/env bash
# usage (in the clone root): make-node-yaml.sh <label>
# Rebuilds conf/cassandra.yaml from the tag with the hold-fixed settings of case 9b (amended 2026-10-14): commitlog_sync batch
# (commitlog_sync_period removed), write_request_timeout 120000ms, native_transport_timeout 180000ms. The knob is a JVM property,
# not a yaml key, so the yaml is the same at every value.
set -euo pipefail
label=$1
y=conf/cassandra.yaml
git show HEAD:conf/cassandra.yaml > $y
sed -i -e 's/^commitlog_sync: periodic$/commitlog_sync: batch/' -e '/^commitlog_sync_period:/d' \
       -e 's/^write_request_timeout: .*/write_request_timeout: 120000ms/' $y
printf '\n# stage4 cms %s\nnative_transport_timeout: 180000ms\n' "$label" >> $y
echo "yaml for $label:"; diff <(git show HEAD:conf/cassandra.yaml) $y | grep '^[<>]' || true
