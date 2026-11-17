#!/usr/bin/env python3
"""Client of the recheck stage-4 run (slab-region-size-region-allocate-capacity--autonomous, design of 2026-11-17).
Bundled Python driver (from $CASSANDRA_HOME/lib), protocol 4, CL ONE, whitelist the one host, native port 9042.
  probe <host>                        SELECT release_version FROM system.local
  settings <host> <name> ...          rows of system_views.settings for the names (the read-back)
  schema <host> <ntables>             keyspace ks (SimpleStrategy RF 1), tables ks.t0 .. ks.t<ntables> (k int PRIMARY KEY, v blob),
                                      shipped table options, created one by one; then waits for schema agreement
  one <host> <first> <last>           one row (k = 1, v = 1024 random bytes) into each of ks.t<first> .. ks.t<last>
  fill <host> <table> <k0> <n> <conc> n rows (k = k0 .. k0+n-1, v = 1024 random bytes) into ks.<table>, at most <conc> in flight
One JSON object on stdout (ok/err counts, seconds). Driver loading pattern from the earlier harness's client.py."""
import glob, json, os, sys, time

CASS = os.environ.get('CASSANDRA_HOME', '/mydata/s4/slabrc')
LIB = os.path.join(CASS, 'lib')
VALUE = 1024


def find_zip(prefix):
    z = glob.glob(os.path.join(LIB, prefix + '*.zip'))
    return max(z) if z else None


cql = find_zip('cassandra-driver-internal-only-')
ver = os.path.splitext(os.path.basename(cql))[0][len('cassandra-driver-internal-only-'):]
sys.path.insert(0, os.path.join(cql, 'cassandra-driver-' + ver))
for lib in ('pure_sasl-', 'wcwidth-', 'pyasyncore-', 'geomet-', 'futures-'):
    z = find_zip(lib)
    if z:
        sys.path.insert(0, z)

from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT  # noqa: E402
from cassandra.policies import WhiteListRoundRobinPolicy, FallthroughRetryPolicy  # noqa: E402
from cassandra.concurrent import execute_concurrent_with_args  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402


def connect(host, timeout=120):
    prof = ExecutionProfile(request_timeout=timeout, consistency_level=ConsistencyLevel.ONE, retry_policy=FallthroughRetryPolicy(),
                            load_balancing_policy=WhiteListRoundRobinPolicy([host]))
    c = Cluster([host], port=9042, protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof},
                control_connection_timeout=60, connect_timeout=30, max_schema_agreement_wait=120)
    return c, c.connect()


def main(a):
    cmd, host = a[0], a[1]
    t0 = time.time()
    c, s = connect(host)
    out = {'cmd': cmd}
    try:
        if cmd == 'probe':
            out['release_version'] = s.execute('SELECT release_version FROM system.local').one()[0]
        elif cmd == 'settings':
            got = {}
            for n in a[2:]:
                r = s.execute('SELECT name, value FROM system_views.settings WHERE name = %s', (n,)).one()
                got[n] = r[1] if r else None
            out['settings'] = got
        elif cmd == 'schema':
            n = int(a[2])
            s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
            for i in range(n + 1):
                s.execute(f'CREATE TABLE IF NOT EXISTS ks.t{i} (k int PRIMARY KEY, v blob)')
            out['tables'] = n + 1
            out['agreement'] = c.control_connection.wait_for_schema_agreement()
        elif cmd == 'one':
            first, last = int(a[2]), int(a[3])
            ok = err = 0
            for i in range(first, last + 1):
                try:
                    s.execute(f'INSERT INTO ks.t{i} (k, v) VALUES (%s, %s)', (1, os.urandom(VALUE)))
                    ok += 1
                except Exception as e:  # counted, first message kept
                    err += 1
                    out.setdefault('first_error', repr(e)[:300])
            out.update(ok=ok, err=err, tables=[first, last])
        elif cmd == 'fill':
            table, k0, n, conc = a[2], int(a[3]), int(a[4]), int(a[5])
            ps = s.prepare(f'INSERT INTO ks.{table} (k, v) VALUES (?, ?)')
            ok = err = 0
            step = 2000
            for b in range(k0, k0 + n, step):
                args = [(k, os.urandom(VALUE)) for k in range(b, min(b + step, k0 + n))]
                for success, res in execute_concurrent_with_args(s, ps, args, concurrency=conc, raise_on_first_error=False):
                    if success:
                        ok += 1
                    else:
                        err += 1
                        out.setdefault('first_error', repr(res)[:300])
            out.update(ok=ok, err=err, table=table, k0=k0, n=n)
        else:
            raise SystemExit(__doc__)
    finally:
        c.shutdown()
    out['seconds'] = round(time.time() - t0, 2)
    print(json.dumps(out))


if __name__ == '__main__':
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
