#!/usr/bin/env bash
# usage: make-node-yaml.sh <tree> <root> <1|2>
# Builds the node's own conf dir <root>/conf (copy of the tree's conf/, tree untouched) for the two-node cluster tier on one host (port slot 2):
#   node 1: 127.0.2.1, JMX 7120, native 9042 on; node 2: 127.0.2.2, JMX 7121, native off. Storage port 7000 (distinct loopback addresses).
#   num_tokens 1 with initial_token -2^62 (node 1) / +2^62 (node 2), auto_bootstrap false, both nodes seeds, SimpleSnitch (the tag's default).
#   Data, commit log, hints, saved caches and cdc_raw under <root> (tmpfs).
set -euo pipefail
tree=$1; root=$2; n=$3
case $n in 1) ip=127.0.2.1; jmx=7120; tok=-4611686018427387904;; 2) ip=127.0.2.2; jmx=7121; tok=4611686018427387904;; *) echo "node 1|2" >&2; exit 2;; esac
rm -rf "$root/conf"; mkdir -p "$root"; cp -r "$tree/conf" "$root/conf"
y=$root/conf/cassandra.yaml
git -C "$tree" show HEAD:conf/cassandra.yaml > "$y"
sed -i -e 's/^num_tokens: .*/num_tokens: 1/' -e "s/^# initial_token:.*/initial_token: $tok/" \
  -e "s/^listen_address: .*/listen_address: $ip/" -e "s/^rpc_address: .*/rpc_address: $ip/" \
  -e 's/- seeds: "127.0.0.1:7000"/- seeds: "127.0.2.1:7000,127.0.2.2:7000"/' "$y"
[ "$n" = 2 ] && sed -i 's/^start_native_transport: true/start_native_transport: false/' "$y"
cat >> "$y" <<YAML

# stage4 hv
auto_bootstrap: false
data_file_directories:
    - $root/data
commitlog_directory: $root/commitlog
hints_directory: $root/hints
saved_caches_directory: $root/saved_caches
cdc_raw_directory: $root/cdc_raw
YAML
sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$jmx\"/" "$root/conf/cassandra-env.sh"
grep -q "^JMX_PORT=\"$jmx\"" "$root/conf/cassandra-env.sh" && grep -q "^listen_address: $ip\$" "$y" && grep -q "^initial_token: $tok\$" "$y" && grep -q 'seeds: "127.0.2.1:7000,127.0.2.2:7000"' "$y" || { echo "make-node-yaml: edit failed" >&2; exit 2; }
echo "yaml ok node $n:"; diff <(git -C "$tree" show HEAD:conf/cassandra.yaml) "$y" | grep '^[<>]' | grep -v '^[<>] *#' | tr '\n' ' ' || true
