#!/usr/bin/env bash
# usage (in the clone root): make-node-yaml.sh <label> <value|none> [default-transport]
# Rebuilds conf/cassandra.yaml from the tag with the hold-fixed settings of case 9b and the knob.
# default-transport leaves native_transport_max_frame_size and native_transport_max_message_size at their defaults.
set -euo pipefail
label=$1; val=$2; mode=${3:-}
y=conf/cassandra.yaml
git show HEAD:conf/cassandra.yaml > $y
sed -i -e 's/^commitlog_sync: periodic$/commitlog_sync: batch/' -e '/^commitlog_sync_period:/d' \
       -e 's/^write_request_timeout: .*/write_request_timeout: 10000ms/' \
       -e 's/^batch_size_fail_threshold: .*/batch_size_fail_threshold: 64MiB/' $y
{ echo; echo "# stage4 mms $label"
  [ "$val" != none ] && echo "max_mutation_size: $val"
  [ "$mode" != default-transport ] && printf 'native_transport_max_frame_size: 64MiB\nnative_transport_max_message_size: 64MiB\n'
  true; } >> $y
echo "yaml for $label:"; diff <(git show HEAD:conf/cassandra.yaml) $y | grep '^[<>]' || true
