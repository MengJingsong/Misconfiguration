#!/usr/bin/env bash
# usage: make-node-yaml.sh <S|R1|R2|R3> [yaml_key=value ...]     (case 9b "Per-node recipe")
# Rebuilds ~/stage4-ssq/<node>/conf from the clone: a copy of conf/ whose cassandra.yaml is the tag's file with this node's lines (cluster, addresses, token,
# every directory under ~/stage4-ssq/<node>/, and S's held settings) and then the extra key=value arguments (the swept settings), and whose cassandra-env.sh has
# its JMX_PORT line replaced by the node's port (7102 S, 7103 R1, 7104 R2, 7105 R3). Any key already set in the shipped yaml is removed first (with its
# continuation lines), so no key appears twice. Nothing in the clone is changed. Prints the effective tail of the yaml.
set -euo pipefail
node=${1:?S|R1|R2|R3}; shift
C=${CASSANDRA_HOME:-$HOME/cassandra-run1}; N=${SSQ:-$HOME/stage4-ssq}/$node
case $node in
  S)  addr=127.0.0.2; jmx=7102; tok=3 ;;
  R1) addr=127.0.0.3; jmx=7103; tok=0 ;;
  R2) addr=127.0.0.4; jmx=7104; tok=1 ;;
  R3) addr=127.0.0.5; jmx=7105; tok=2 ;;
  *) echo "unknown node $node" >&2; exit 2 ;;
esac
mkdir -p "$N/logs" "$N/data" "$N/commitlog" "$N/hints" "$N/saved_caches" "$N/cdc_raw"
rm -rf "$N/conf"; cp -r "$C/conf" "$N/conf"
sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$jmx\"/" "$N/conf/cassandra-env.sh"
grep -q "^JMX_PORT=\"$jmx\"" "$N/conf/cassandra-env.sh" || { echo "JMX_PORT line not replaced" >&2; exit 1; }
{
  echo "cluster_name: stage4-ssq"
  echo "num_tokens: 1"
  echo "initial_token: $tok"
  echo "auto_bootstrap: false"
  echo "storage_port: 7010"
  echo "listen_address: $addr"
  echo "rpc_address: $addr"
  echo "seed_provider:"
  echo "  - class_name: org.apache.cassandra.locator.SimpleSeedProvider"
  echo "    parameters:"
  echo "      - seeds: \"127.0.0.3:7010\""
  echo "data_file_directories:"
  echo "    - $N/data"
  echo "commitlog_directory: $N/commitlog"
  echo "hints_directory: $N/hints"
  echo "saved_caches_directory: $N/saved_caches"
  echo "cdc_raw_directory: $N/cdc_raw"
  if [ "$node" = S ]; then       # held settings of S (9b "Hold fixed")
    echo "native_transport_max_threads: 512"
    echo "hinted_handoff_enabled: false"
    echo "write_request_timeout: 10000ms"
  fi
  for kv in "$@"; do echo "${kv%%=*}: ${kv#*=}"; done
} > "$N/lines.yaml"
git -C "$C" show HEAD:conf/cassandra.yaml > "$N/shipped.yaml"
python3 - "$N" <<'PY'
import re, sys
n = sys.argv[1]
add = open(n + '/lines.yaml').read().splitlines()
keys = {l.split(':', 1)[0] for l in add if re.match(r'^[A-Za-z_]+:', l)}
out, skip = [], False
for l in open(n + '/shipped.yaml').read().splitlines():
    m = re.match(r'^([A-Za-z_]+):', l)
    if m:
        skip = m.group(1) in keys
        if skip:
            continue
    elif skip and (l.startswith((' ', '\t', '-')) or l.strip() == '' or l.lstrip().startswith('#')):
        continue          # continuation (list items, comments inside the removed block)
    else:
        skip = False
    out.append(l)
dups = [k for k in keys if sum(1 for l in add if l.startswith(k + ':')) > 1]
if dups:
    sys.exit('duplicate keys in the arguments: %s' % dups)
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 ssq lines ----\n' + '\n'.join(add) + '\n')
PY
echo "node $node: conf $N/conf, JMX $jmx, address $addr, token $tok; yaml tail:"
sed -n '/^# ---- stage4 ssq lines/,$p' "$N/conf/cassandra.yaml" | tr '\n' ';' ; echo
