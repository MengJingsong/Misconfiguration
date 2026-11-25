#!/usr/bin/env bash
# B27 stage 3-b confirm (2026-11-24, pc99): B10's 3-b script (logs/B10/harness/make-node-yaml-3b.sh) with cluster_name oom-b27 only; B10's note: copy of the stage-2 script; the ONLY change is two security lines
# (authenticator: PasswordAuthenticator, authorizer: CassandraAuthorizer) added to the environment lines; no capacity key.
# B10 stage 2 (2026-11-17). Adapted from the stage-4 recheck harness's make-node-yaml.sh: ONLY the environment lines of
# case §2.3 (cluster name, loopback, seeds, directories, auto_snapshot). The stage-4 lines native_transport_timeout,
# read_request_timeout, native_transport_throw_on_overload and native_transport_rate_limiting_enabled are dropped, so
# every transport/timeout/capacity setting is the shipped default. Fails if the yaml would set any §2.3 key.
# usage: CASSANDRA_HOME=<clone> NODE=<node dir> make-node-yaml.sh
set -euo pipefail
C=${CASSANDRA_HOME:?}; N=${NODE:?}; DD=$N/data
mkdir -p "$DD/data" "$DD/commitlog" "$DD/hints" "$DD/saved_caches" "$DD/cdc_raw"
rm -rf "$N/conf"; cp -r "$C/conf" "$N/conf"
if git -C "$C" rev-parse HEAD >/dev/null 2>&1; then
  git -C "$C" show HEAD:conf/cassandra.yaml > "$N/shipped.yaml"
  git -C "$C" show HEAD:conf/cassandra-env.sh > "$N/conf/cassandra-env.sh"
else
  cp "$C/conf/cassandra.yaml" "$N/shipped.yaml"
fi
{
  echo "cluster_name: oom-b27"
  echo "num_tokens: 1"
  echo "auto_bootstrap: false"
  echo "listen_address: 127.0.0.1"
  echo "rpc_address: 127.0.0.1"
  echo "seed_provider:"
  echo "  - class_name: org.apache.cassandra.locator.SimpleSeedProvider"
  echo "    parameters:"
  echo "      - seeds: \"127.0.0.1:7000\""
  echo "data_file_directories:"
  echo "    - $DD/data"
  echo "commitlog_directory: $DD/commitlog"
  echo "hints_directory: $DD/hints"
  echo "saved_caches_directory: $DD/saved_caches"
  echo "cdc_raw_directory: $DD/cdc_raw"
  echo "auto_snapshot: false"
  echo "authenticator: PasswordAuthenticator"
  echo "authorizer: CassandraAuthorizer"
} > "$N/lines.yaml"
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
y = '\n'.join(out) + '\n# ---- oom-b27 environment lines (3-b: + auth) ----\n' + '\n'.join(add) + '\n'
forbidden = ['native_transport_receive_queue_capacity', 'native_transport_max_request_data_in_flight_per_ip',
             'native_transport_max_request_data_in_flight', 'native_transport_throw_on_overload',
             'native_transport_max_concurrent_connections', 'native_transport_max_concurrent_connections_per_ip',
             'native_transport_max_threads', 'native_transport_timeout', 'native_transport_queue_max_item_age_threshold',
             'native_transport_rate_limiting_enabled', 'native_transport_max_message_size', 'read_request_timeout',
             'concurrent_reads', 'allow_filtering_enabled', 'slow_query_log_timeout',
             'native_transport_receive_queue_capacity_in_bytes', 'native_transport_max_concurrent_requests_in_bytes',
             'native_transport_max_concurrent_requests_in_bytes_per_ip', 'read_request_timeout_in_ms']
# Amendment 2026-11-17 (stage 2): the shipped cassandra.yaml itself carries concurrent_reads: 32,
# read_request_timeout: 5000ms and slow_query_log_timeout: 500ms (their §2.3 defaults). The check therefore fails if
# the harness ADDS any §2.3 key, or if a shipped §2.3 key differs from its §2.3 default value.
shipped_ok = {'concurrent_reads': '32', 'read_request_timeout': '5000ms', 'slow_query_log_timeout': '500ms'}
added = '\n'.join(add)
setk = [k for k in forbidden if re.search(rf'^{k}\s*:', added, re.M)]
for k in forbidden:
    for v in re.findall(rf'^{k}\s*:\s*(\S+)', y, re.M):
        if shipped_ok.get(k) != v:
            setk.append(f'{k}={v}')
if setk:
    sys.exit('yaml sets a §2.3 key away from its default: %s' % setk)
open(n + '/conf/cassandra.yaml', 'w').write(y)
print('yaml ok: harness adds no §2.3 key; shipped ' +
      ', '.join(f'{k}={v}' for k in forbidden for v in re.findall(rf'^{k}\s*:\s*(\S+)', y, re.M)) + ' (defaults)')
PY
