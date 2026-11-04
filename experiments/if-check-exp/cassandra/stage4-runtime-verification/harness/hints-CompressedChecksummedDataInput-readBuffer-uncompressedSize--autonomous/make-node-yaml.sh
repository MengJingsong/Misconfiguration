#!/usr/bin/env bash
# usage: make-node-yaml.sh <A|B> <file_cache_size MiB> [yaml_key=value ...]                           (case B3a)
# Rebuilds $HU/<node>/conf from the clone (CASSANDRA_HOME, default ~/s4-hu): a copy of conf/ whose cassandra.yaml is the tag's file
# with B3a's lines and then the extra key=value arguments (a key already set in the shipped yaml is removed first). Two nodes on
# loopback (environment deviation: one host, tag hu): A = 127.0.13.1 (seed, JMX 7213), B = 127.0.13.2 (JMX 7214); storage_port 7013,
# native_transport_port 9145 on both addresses. B3a lines: hints_compression LZ4Compressor, max_hints_file_size 128MiB,
# max_mutation_size left default (16MiB), commitlog_segment_size 32MiB, hinted_handoff_enabled, max_hint_window 3h,
# file_cache_size <n>MiB; also (audit R8) hinted_handoff_throttle 102400KiB and hints_flush_period 1000ms, num_tokens 1.
# jvm11-server.options gets -XX:MaxDirectMemorySize=2g and -XX:NativeMemoryTracking=summary (B3a); the heap, 2 GiB, is
# MAX_HEAP_SIZE in cluster-run.py. Every directory is under $HU/<node>/ on local disk. Nothing in the clone is changed.
set -euo pipefail
node=${1:?A|B}; fcs=${2:?file_cache_size MiB}; shift 2
C=${CASSANDRA_HOME:-$HOME/s4-hu}; N=${HU:-$HOME/s4-hu-run}/$node
case $node in
  A) addr=127.0.13.1; jmx=7213; tok=-9223372036854775808 ;;
  B) addr=127.0.13.2; jmx=7214; tok=0 ;;
  *) echo "unknown node $node" >&2; exit 2 ;;
esac
mkdir -p "$N/logs" "$N/data" "$N/commitlog" "$N/hints" "$N/saved_caches" "$N/cdc_raw"
rm -rf "$N/conf"; cp -r "$C/conf" "$N/conf"
git -C "$C" show HEAD:conf/cassandra-env.sh > "$N/conf/cassandra-env.sh"
sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$jmx\"/" "$N/conf/cassandra-env.sh"
grep -q "^JMX_PORT=\"$jmx\"" "$N/conf/cassandra-env.sh" || { echo "JMX_PORT line not replaced" >&2; exit 1; }
git -C "$C" show HEAD:conf/jvm11-server.options > "$N/conf/jvm11-server.options"
printf '\n# stage4 hu (B3a)\n-XX:MaxDirectMemorySize=2g\n-XX:NativeMemoryTracking=summary\n' >> "$N/conf/jvm11-server.options"
{
  echo "cluster_name: stage4-hu"
  echo "num_tokens: 1"
  echo "initial_token: $tok"
  echo "endpoint_snitch: SimpleSnitch"
  echo "listen_address: $addr"
  echo "rpc_address: $addr"
  echo "storage_port: 7013"
  echo "ssl_storage_port: 7014"
  echo "native_transport_port: 9145"
  echo "seed_provider:"
  echo "  - class_name: org.apache.cassandra.locator.SimpleSeedProvider"
  echo "    parameters:"
  echo "      - seeds: \"127.0.13.1:7013\""
  echo "data_file_directories:"
  echo "    - $N/data"
  echo "commitlog_directory: $N/commitlog"
  echo "hints_directory: $N/hints"
  echo "saved_caches_directory: $N/saved_caches"
  echo "cdc_raw_directory: $N/cdc_raw"
  echo "hinted_handoff_enabled: true"
  echo "max_hint_window: 3h"
  echo "max_hints_file_size: 128MiB"
  echo "hints_flush_period: 1000ms"
  echo "hinted_handoff_throttle: 102400KiB"
  echo "commitlog_segment_size: 32MiB"
  echo "hints_compression:"
  echo "    - class_name: LZ4Compressor"
  echo "      parameters:"
  echo "          -"
  echo "file_cache_size: ${fcs}MiB"
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
        continue
    else:
        skip = False
    out.append(l)
tops = [l.split(':', 1)[0] for l in add if re.match(r'^[A-Za-z_]+:', l)]
dups = sorted({k for k in tops if tops.count(k) > 1})
if dups:
    sys.exit('duplicate keys in the arguments: %s' % dups)
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 hu lines ----\n' + '\n'.join(add) + '\n')
PY
echo "node $node: conf $N/conf, JMX $jmx, address $addr, token $tok, file_cache_size ${fcs}MiB; yaml tail:"
sed -n '/^# ---- stage4 hu lines/,$p' "$N/conf/cassandra.yaml" | grep -v '^ *- \|^ *parameters\|class_name' | tr '\n' ';' ; echo
