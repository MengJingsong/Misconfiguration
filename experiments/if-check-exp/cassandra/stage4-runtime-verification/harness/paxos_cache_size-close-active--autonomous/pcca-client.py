#!/usr/bin/env python3
"""Cluster-tier client (B3c, amendment C3 of 2026-10-27) of paxos_cache_size-close-active--autonomous.
Adapted from harness/paxos_cache_size-applySimpleConfig-paxosCacheSizeInMiB--autonomous/pcs-client.py (driver set-up and the
execute_concurrent loop); keyspace, table, payload and modes are this case's.
Bundled Python driver (lib/cassandra-driver-internal-only-*.zip), protocol 5, one node, DCAwareRoundRobinPolicy,
token_metadata_enabled=False. Modes:
  settings          name, value from system_views.settings for paxos_cache_size, paxos_variant, paxos_state_purging
  schema            CREATE KEYSPACE pk (SimpleStrategy, RF 1); CREATE TABLE pk.t (k int PRIMARY KEY, v blob)
  lwt <lo> <hi>     prepared INSERT INTO pk.t (k, v) VALUES (?, ?) IF NOT EXISTS for k in [lo, hi), v = os.urandom(8192),
                    commit consistency ONE, serial consistency SERIAL, 32 in flight, request timeout 60 s; returns when every
                    request has completed
One JSON object on stdout. Exit 0 on OK, 1 on ERR."""
import glob, json, os, sys, time

CASS = os.environ.get('CASSANDRA_HOME')
LIB = os.path.join(CASS, 'lib')


def find_zip(prefix):
    z = glob.glob(os.path.join(LIB, prefix + '*.zip'))
    return max(z) if z else None


cql = find_zip('cassandra-driver-internal-only-')
ver = os.path.splitext(os.path.basename(cql))[0][len('cassandra-driver-internal-only-'):]
sys.path.insert(0, os.path.join(cql, 'cassandra-driver-' + ver))
for lib in ('pure_sasl-', 'wcwidth-', 'pyasyncore-', 'geomet-'):
    z = find_zip(lib)
    if z:
        sys.path.insert(0, z)

from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT  # noqa: E402
from cassandra.policies import DCAwareRoundRobinPolicy  # noqa: E402
from cassandra.concurrent import execute_concurrent  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402

CONC = 32
PAYLOAD = 8192


def main():
    a = sys.argv[1:]
    mode = a[0]
    prof = ExecutionProfile(load_balancing_policy=DCAwareRoundRobinPolicy(), request_timeout=60,
                            consistency_level=ConsistencyLevel.ONE, serial_consistency_level=ConsistencyLevel.SERIAL)
    c = Cluster(['127.0.0.1'], protocol_version=5, execution_profiles={EXEC_PROFILE_DEFAULT: prof},
                token_metadata_enabled=False, idle_heartbeat_interval=0)
    s = c.connect()
    t0 = time.time()
    out = {'ok': True, 'mode': mode}
    try:
        if mode == 'settings':
            rows = s.execute("SELECT name, value FROM system_views.settings WHERE name IN ('paxos_cache_size', 'paxos_variant', 'paxos_state_purging')")
            out['settings'] = {r.name: r.value for r in rows}
        elif mode == 'schema':
            s.execute("CREATE KEYSPACE IF NOT EXISTS pk WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
            s.execute("CREATE TABLE IF NOT EXISTS pk.t (k int PRIMARY KEY, v blob)")
        elif mode == 'lwt':
            lo, hi = int(a[1]), int(a[2])
            ps = s.prepare("INSERT INTO pk.t (k, v) VALUES (?, ?) IF NOT EXISTS")

            def gen():
                for k in range(lo, hi):
                    yield ps, (k, os.urandom(PAYLOAD))

            applied = not_applied = errors = 0
            first_err = None
            for ok, res in execute_concurrent(s, gen(), concurrency=CONC, raise_on_first_error=False, results_generator=True):
                if not ok:
                    errors += 1
                    if first_err is None:
                        first_err = repr(res)[:300]
                    continue
                row = res.one()
                if row is not None and row[0] is True:
                    applied += 1
                else:
                    not_applied += 1
            out.update({'lo': lo, 'hi': hi, 'requests': hi - lo, 'applied': applied, 'not_applied': not_applied,
                        'errors': errors, 'first_error': first_err})
            if errors or not_applied:
                out['ok'] = False
        else:
            raise ValueError('unknown mode ' + mode)
    except Exception as e:  # noqa
        out = {'ok': False, 'mode': mode, 'error': repr(e)[:500]}
    out['secs'] = round(time.time() - t0, 2)
    print(json.dumps(out))
    c.shutdown()
    sys.exit(0 if out['ok'] else 1)


if __name__ == '__main__':
    main()
