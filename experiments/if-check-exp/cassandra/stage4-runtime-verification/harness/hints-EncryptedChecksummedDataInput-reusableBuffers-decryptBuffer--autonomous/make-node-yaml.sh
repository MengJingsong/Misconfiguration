#!/usr/bin/env bash
# usage: make-node-yaml.sh <A|B> <max_mutation_size KiB|default> [yaml_key=value ...]                      (case B3a, audit R2/R9)
# Rebuilds $EC/<node>/conf from the clone (CASSANDRA_HOME, default ~/s4-ec): conf/ plus B3a's lines. Loopback, host pc12, tag ec:
# A = 127.0.33.2 (seed, JMX 7333, storage 7033, native 9355), B = 127.0.33.3 (JMX 7334, storage 7034, native 9356).
# A and B: TDE key_provider (enabled false, see the deviation below) with the test keystore (alias testing:1, copy at $EC/keystore), max_hints_delivery_threads 1 (A), hinted handoff
# throttle 102400KiB, hints_flush_period 1000ms. max_mutation_size KiB (A only) with commitlog_segment_size = 2 x it (default: 32MiB).
# jvm11-server.options: -XX:MaxDirectMemorySize=2g, NativeMemoryTracking=summary (B3a). Heap 2 GiB is MAX_HEAP_SIZE in cluster-run.py.
set -euo pipefail
node=${1:?A|B}; mm=${2:?KiB|default}; shift 2
C=${CASSANDRA_HOME:-$HOME/s4-ec}; E=${EC:-$HOME/s4-ec-run}; N=$E/$node
case $node in
  A) addr=127.0.33.2; jmx=7333; sp=7033; np=9355; tok=-9223372036854775808 ;;
  B) addr=127.0.33.3; jmx=7334; sp=7034; np=9356; tok=0 ;;
  *) echo "unknown node $node" >&2; exit 2 ;;
esac
mkdir -p "$N/logs" "$N/data" "$N/commitlog" "$N/hints" "$N/saved_caches" "$N/cdc_raw"
cp "$C/test/conf/cassandra.keystore" "$E/keystore"
rm -rf "$N/conf"; cp -r "$C/conf" "$N/conf"
git -C "$C" show HEAD:conf/cassandra-env.sh > "$N/conf/cassandra-env.sh"
sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$jmx\"/" "$N/conf/cassandra-env.sh"
grep -q "^JMX_PORT=\"$jmx\"" "$N/conf/cassandra-env.sh" || { echo "JMX_PORT line not replaced" >&2; exit 1; }
git -C "$C" show HEAD:conf/jvm11-server.options > "$N/conf/jvm11-server.options"
printf '\n# stage4 ec (B3a)\n-XX:MaxDirectMemorySize=2g\n-XX:NativeMemoryTracking=summary\n' >> "$N/conf/jvm11-server.options"
{
  echo "cluster_name: stage4-ec"
  echo "num_tokens: 1"
  echo "initial_token: $tok"
  echo "endpoint_snitch: SimpleSnitch"
  echo "listen_address: $addr"
  echo "rpc_address: $addr"
  echo "storage_port: $sp"
  echo "ssl_storage_port: $((sp+100))"
  echo "native_transport_port: $np"
  echo "seed_provider:"
  echo "  - class_name: org.apache.cassandra.locator.SimpleSeedProvider"
  echo "    parameters:"
  echo "      - seeds: \"127.0.33.2:7033\""
  echo "data_file_directories:"
  echo "    - $N/data"
  echo "commitlog_directory: $N/commitlog"
  echo "hints_directory: $N/hints"
  echo "saved_caches_directory: $N/saved_caches"
  echo "cdc_raw_directory: $N/cdc_raw"
  echo "hinted_handoff_enabled: true"
  echo "max_hint_window: 3h"
  echo "hints_flush_period: 1000ms"
  echo "hinted_handoff_throttle: 102400KiB"
  echo "max_hints_delivery_threads: 1"
  if [ "$node" = A ] && [ "$mm" != default ]; then
    echo "commitlog_segment_size: $((mm*2/1024))MiB"
    echo "max_mutation_size: ${mm}KiB"
  else
    echo "commitlog_segment_size: 32MiB"
  fi
  echo "transparent_data_encryption_options:"
  echo "  enabled: ${TDE_ENABLED:-false}"   # DEVIATION (audit R2): true makes the commit log encrypted and 5.0.9 then fails at start (AbstractCommitLogSegmentManager.java:125 assert / commitlog_disk_access_mode refused with every value tried); the key_provider block alone is what the hints reader needs
  echo "  chunk_length_kb: 64"
  echo "  cipher: AES/CBC/PKCS5Padding"
  echo "  key_alias: testing:1"
  echo "  key_provider:"
  echo "    - class_name: org.apache.cassandra.security.JKSKeyProvider"
  echo "      parameters:"
  echo "        - keystore: $E/keystore"
  echo "          keystore_password: cassandra"
  echo "          store_type: JCEKS"
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
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 ec lines ----\n' + '\n'.join(add) + '\n')
PY
echo "node $node: conf $N/conf, JMX $jmx, address $addr, native $np, storage $sp, max_mutation_size $mm; yaml tail:"
sed -n '/^# ---- stage4 ec lines/,$p' "$N/conf/cassandra.yaml" | grep -v '^ *- \|^ *parameters\|class_name\|^  ' | tr '\n' ';' ; echo
