#!/usr/bin/env python3
"""Cluster-tier client (B3c) of internode_max_message_size-inferMessageSize-size--autonomous. Bundled Python driver,
protocol 5, whitelist: the one host given (node A, 127.0.0.1, in every write). Modes:
  probe <host>                         SELECT release_version FROM system.local
  schema <host>                        CREATE KEYSPACE ks (SimpleStrategy, RF 2) and TABLE ks.t (k int PRIMARY KEY, v blob)
  setting <host> <name>                the row of system_views.settings for <name> on that node (the limit's read-back)
  write <host> <first_k> <n> <bytes> <keylog>
                                       n INSERTs into ks.t at CL ALL, one after another, k = first_k .. first_k+n-1,
                                       v = <bytes> random bytes; every k appended to <keylog> as
                                       "k,bytes,ms_sent,ms_done,ok|err,<error class>: <message>"
  count <host>                         SELECT count(*) FROM ks.t at CL ONE through that node, one row per page
One JSON object on stdout. Exit 0 unless the mode itself could not run (a write that fails is a reading, not an error).
Adapted from the internode_application_receive_queue_capacity harness's write-load.py."""
import glob, json, os, sys, time

CASS = os.environ.get('CASSANDRA_HOME', os.path.expanduser('~/cassandra-run5'))
LIB = os.path.join(CASS, 'lib')


def find_zip(prefix):
    z = glob.glob(os.path.join(LIB, prefix + '*.zip'))
    return max(z) if z else None


cql = find_zip('cassandra-driver-internal-only-')
ver = os.path.splitext(os.path.basename(cql))[0][len('cassandra-driver-internal-only-'):]
sys.path.insert(0, os.path.join(cql, 'cassandra-driver-' + ver))
for lib in ('pure_sasl-', 'wcwidth-', 'pyasyncore-'):
    z = find_zip(lib)
    if z:
        sys.path.insert(0, z)

from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT  # noqa: E402
from cassandra.policies import WhiteListRoundRobinPolicy, FallthroughRetryPolicy  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402


def connect(host, cl, timeout=30):
    # FallthroughRetryPolicy: a failed write is reported once, never retried by the driver
    prof = ExecutionProfile(request_timeout=timeout, consistency_level=cl, retry_policy=FallthroughRetryPolicy(),
                            load_balancing_policy=WhiteListRoundRobinPolicy([host]))
    c = Cluster([host], protocol_version=5, execution_profiles={EXEC_PROFILE_DEFAULT: prof})
    return c, c.connect()


def main():
    mode, host = sys.argv[1], sys.argv[2]
    if mode == 'probe':
        c, s = connect(host, ConsistencyLevel.ONE)
        print(json.dumps({'release_version': s.execute('SELECT release_version FROM system.local').one()[0]}))
    elif mode == 'schema':
        c, s = connect(host, ConsistencyLevel.ONE, timeout=60)
        s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 2}")
        s.execute('CREATE TABLE IF NOT EXISTS ks.t (k int PRIMARY KEY, v blob)')
        c.control_connection.wait_for_schema_agreement(wait_time=60)
        print(json.dumps({'schema': 'ok', 'agreement': c.metadata.keyspaces['ks'].replication_strategy.export_for_schema()}))
    elif mode == 'setting':
        c, s = connect(host, ConsistencyLevel.ONE)
        r = s.execute('SELECT name, value FROM system_views.settings WHERE name = %s', [sys.argv[3]]).one()
        print(json.dumps({'host': host, 'name': sys.argv[3], 'value': r.value if r else None}))
    elif mode == 'write':
        first, n, size, keylog = int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), sys.argv[6]
        c, s = connect(host, ConsistencyLevel.ALL)
        ps = s.prepare('INSERT INTO ks.t (k, v) VALUES (?, ?)')
        ok = err = 0
        errs = {}
        with open(keylog, 'a') as log:
            for k in range(first, first + n):
                v = os.urandom(size)
                t0 = int(time.time() * 1000)
                try:
                    s.execute(ps, (k, v))
                    res, why = 'ok', ''
                    ok += 1
                except Exception as e:  # the reading: timeout, failure or server error
                    res, why = 'err', f'{type(e).__name__}: {str(e)[:200]}'.replace(',', ';').replace('\n', ' ')
                    err += 1
                    errs[type(e).__name__] = errs.get(type(e).__name__, 0) + 1
                log.write(f'{k},{size},{t0},{int(time.time() * 1000)},{res},{why}\n')
                log.flush()
        print(json.dumps({'first': first, 'n': n, 'bytes': size, 'ok': ok, 'err': err, 'errors': errs}))
    elif mode == 'count':
        c, s = connect(host, ConsistencyLevel.ONE, timeout=60)
        # one row per page: a page is one replica reply, so no reply holds more than one row (a whole-table reply
        # exceeded B's own internode_max_message_size in the shakedown)
        from cassandra.query import SimpleStatement
        print(json.dumps({'host': host, 'count': s.execute(SimpleStatement('SELECT count(*) FROM ks.t', fetch_size=1)).one()[0]}))
    else:
        sys.exit(__doc__)
    c.shutdown()


main()
