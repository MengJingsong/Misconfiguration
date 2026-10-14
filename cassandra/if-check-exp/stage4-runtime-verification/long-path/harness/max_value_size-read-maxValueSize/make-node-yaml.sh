#!/usr/bin/env bash
# usage (in the clone root): make-node-yaml.sh <label> <value|none>
# Rebuilds conf/cassandra.yaml from the tag (amended 2026-10-13, rec. 5) with the hold-fixed settings of case 9b and the knob:
# commitlog_sync batch (commitlog_sync_period removed), read and write request timeouts 10000ms, max_value_size (nothing for none).
set -euo pipefail
label=$1; val=$2
y=conf/cassandra.yaml
git show HEAD:conf/cassandra.yaml > $y
sed -i -e 's/^commitlog_sync: periodic$/commitlog_sync: batch/' -e '/^commitlog_sync_period:/d' \
       -e 's/^write_request_timeout: .*/write_request_timeout: 10000ms/' \
       -e 's/^read_request_timeout: .*/read_request_timeout: 10000ms/' $y
{ echo; echo "# stage4 mvs $label"; [ "$val" != none ] && echo "max_value_size: $val"; true; } >> $y
echo "yaml for $label:"; diff <(git show HEAD:conf/cassandra.yaml) $y | grep '^[<>]' || true
