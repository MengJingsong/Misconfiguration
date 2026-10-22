#!/usr/bin/env bash
# usage: make-node-yaml.sh A|B [yaml_key=value | yaml_key=__DELETE__ ...]                              (case B3a)
# Rebuilds ~/stage4-mps/<node>/conf from the clone (~/cassandra-mps): the tag's conf/, with cassandra.yaml = the tag's file
# with B3a's lines: listen/rpc address, seed = A, every directory under ~/stage4-mps/<node>, hinted_handoff_enabled false,
# auto_snapshot false, memtable_heap_space 256MiB; then the extra arguments (control reserves, R5's group commit and
# timeouts). A key given here is removed from the shipped yaml first (no key twice); __DELETE__ only removes it.
# Environment deviation E1: A = 127.0.0.21 (JMX 7221), B = 127.0.0.22 (JMX 7222), not 127.0.0.1/.2 and 7199/7299.
# Adapted from the concurrent_writes-takeWorkPermit-workPermits--autonomous harness's make-node-yaml.sh.
set -euo pipefail
C=${CASSANDRA_HOME:-$HOME/cassandra-mps}; NODE=$1; shift
case $NODE in A) addr=127.0.0.21; jmx=7221;; B) addr=127.0.0.22; jmx=7222;; *) echo "node A or B" >&2; exit 1;; esac
N=${MPSN:-$HOME/stage4-mps}/$NODE
mkdir -p "$N/logs" "$N/data" "$N/commitlog" "$N/hints" "$N/saved_caches" "$N/cdc_raw"
rm -rf "$N/conf"; cp -r "$C/conf" "$N/conf"
git -C "$C" show HEAD:conf/cassandra-env.sh > "$N/conf/cassandra-env.sh"
sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$jmx\"/" "$N/conf/cassandra-env.sh"
grep -q "^JMX_PORT=\"$jmx\"" "$N/conf/cassandra-env.sh" || { echo "JMX_PORT line not replaced" >&2; exit 1; }
git -C "$C" show HEAD:conf/jvm-server.options > "$N/conf/jvm-server.options"
printf '\n# stage4 mps\n-XX:HeapDumpPath=%s/logs\n' "$N" >> "$N/conf/jvm-server.options"
{
  echo "cluster_name: stage4-mps"
  echo "listen_address: $addr"
  echo "rpc_address: $addr"
  echo "seed_provider:"
  echo "  - class_name: org.apache.cassandra.locator.SimpleSeedProvider"
  echo "    parameters:"
  echo "      - seeds: \"127.0.0.21:7000\""
  echo "data_file_directories:"
  echo "    - $N/data"
  echo "commitlog_directory: $N/commitlog"
  echo "saved_caches_directory: $N/saved_caches"
  echo "hints_directory: $N/hints"
  echo "cdc_raw_directory: $N/cdc_raw"
  echo "hinted_handoff_enabled: false"
  echo "auto_snapshot: false"
  echo "memtable_heap_space: 256MiB"
  for kv in "$@"; do [ "${kv#*=}" = "__DELETE__" ] || echo "${kv%%=*}: ${kv#*=}"; done
} > "$N/lines.yaml"
printf '%s\n' "$@" | grep '=__DELETE__$' | sed 's/=__DELETE__$//' > "$N/delete.keys" || true
git -C "$C" show HEAD:conf/cassandra.yaml > "$N/shipped.yaml"
python3 - "$N" <<'PY'
import re, sys
n = sys.argv[1]
add = open(n + '/lines.yaml').read().splitlines()
keys = {l.split(':', 1)[0] for l in add if re.match(r'^[A-Za-z_]+:', l)} | {k.strip() for k in open(n + '/delete.keys') if k.strip()}
out, skip = [], False
for l in open(n + '/shipped.yaml').read().splitlines():
    m = re.match(r'^([A-Za-z_]+):', l)
    if m:
        skip = m.group(1) in keys
        if skip:
            continue
    elif skip and (l.startswith((' ', '\t', '-')) or l.strip() == '' or l.lstrip().startswith('#')):
        continue
    else:
        skip = False
    out.append(l)
dups = [k for k in keys if sum(1 for l in add if l.startswith(k + ':')) > 1]
if dups:
    sys.exit('duplicate keys: %s' % dups)
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 mps lines ----\n' + '\n'.join(add) + '\n')
PY
echo "$NODE: conf $N/conf, JMX $jmx, address $addr; extra: $*"
