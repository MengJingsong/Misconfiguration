#!/usr/bin/env bash
# usage: make-node-yaml.sh   (run in the clone root) — the tag's yaml plus the case's 9b rows: the two timeouts.
set -euo pipefail
git show HEAD:conf/cassandra.yaml | grep -v -E '^(write_request_timeout|native_transport_timeout):' > conf/cassandra.yaml
printf 'write_request_timeout: 30000ms\nnative_transport_timeout: 30s\n' >> conf/cassandra.yaml
echo "yaml tail: $(tail -2 conf/cassandra.yaml | tr '\n' ';') diff: $(git diff --stat conf/cassandra.yaml | tail -1)"
