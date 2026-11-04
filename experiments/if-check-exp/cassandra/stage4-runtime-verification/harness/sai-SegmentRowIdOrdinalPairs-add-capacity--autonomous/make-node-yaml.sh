#!/usr/bin/env bash
# usage (in the tree root): make-node-yaml.sh <root>     Builds the node's own conf dir <root>/conf (copy of the tree's conf/, tree untouched) with
# cassandra.yaml rebuilt from the tag plus: loopback 127.0.28.1, storage 7028, native 9350, JMX 7328 (cassandra-env.sh), num_tokens 1, own data dirs
# under <root>, and the node's timeouts raised (loads and traces).
set -euo pipefail
root=$1
rm -rf "$root/conf"; mkdir -p "$root"; cp -r conf "$root/conf"
y=$root/conf/cassandra.yaml
git show HEAD:conf/cassandra.yaml > "$y"
sed -i -e 's/^num_tokens: .*/num_tokens: 1/' -e 's/^listen_address: .*/listen_address: 127.0.28.1/' -e 's/^rpc_address: .*/rpc_address: 127.0.28.1/' \
  -e 's/^storage_port: .*/storage_port: 7028/' -e 's/^native_transport_port: .*/native_transport_port: 9350/' \
  -e 's/- seeds: "127.0.0.1:7000"/- seeds: "127.0.28.1:7028"/' -e 's/^read_request_timeout: .*/read_request_timeout: 120000ms/' \
  -e 's/^range_request_timeout: .*/range_request_timeout: 120000ms/' "$y"
cat >> "$y" <<YAML

# stage4 sr
data_file_directories:
    - $root/data
commitlog_directory: $root/commitlog
hints_directory: $root/hints
saved_caches_directory: $root/saved_caches
cdc_raw_directory: $root/cdc_raw
YAML
sed -i 's/^JMX_PORT="7199"/JMX_PORT="7328"/' "$root/conf/cassandra-env.sh"
grep -q '^JMX_PORT="7328"' "$root/conf/cassandra-env.sh" && grep -q '^listen_address: 127.0.28.1$' "$y" && grep -q '^storage_port: 7028$' "$y" && grep -q '^native_transport_port: 9350$' "$y" && grep -q 'seeds: "127.0.28.1:7028"' "$y" || { echo "make-node-yaml: edit failed" >&2; exit 2; }
echo "yaml ok:"; diff <(git show HEAD:conf/cassandra.yaml) "$y" | grep '^[<>]' | tr '\n' ' ' || true
