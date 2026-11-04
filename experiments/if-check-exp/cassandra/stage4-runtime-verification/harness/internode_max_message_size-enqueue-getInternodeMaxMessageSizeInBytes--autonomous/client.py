#!/usr/bin/env python3
"""Cluster-tier client (B3c) of internode_max_message_size-enqueue-getInternodeMaxMessageSizeInBytes--autonomous.
Bundled Python driver, native protocol 4 (large v5 requests leave unreturned direct buffers on the coordinator, the
networking_cache_size arm L of HANDOFF's lessons, which would blur the coordinator's direct-memory reading), whitelist
one host (node A, 127.0.0.2, the only coordinator, B3h), no driver retries. Modes:
  probe <host>                         SELECT release_version FROM system.local
  schema <host>                        CREATE KEYSPACE ks (SimpleStrategy, RF 2) and TABLE ks.t (k int PRIMARY KEY, v blob)
  setting <host> <name>                the row of system_views.settings for <name> on that node (read-back)
  load <host> <first_k> <threads> <per_thread> <bytes> <keylog>
                                       <threads> client threads, each <per_thread> INSERTs into ks.t at CL ALL one after
                                       another (thread t writes k = first_k + t*per_thread + i), v = <bytes> random bytes;
                                       every write appended to <keylog> as
                                       "k,bytes,thread,ms_sent,ms_done,ok|err,<error class>: <message>"
  count <host>                         SELECT count(*) FROM ks.t at CL ONE through that node, one row per page
One JSON object on stdout. Exit 0 unless the mode itself could not run (a write that fails is a reading, not an error).
Adapted from the internode_max_message_size-inferMessageSize-size--autonomous harness's client.py (threads added)."""
import glob, json, os, sys, threading, time

CASS = os.environ.get('CASSANDRA_HOME', os.path.expanduser('~/cassandra-run1'))
LIB = os.path.join(CASS, 'lib')


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
from cassandra import ConsistencyLevel  # noqa: E402

PROTOCOL = int(os.environ.get('IME_PROTOCOL', 4))


def connect(host, cl, timeout=60):
    # FallthroughRetryPolicy: a failed write is reported once, never retried by the driver; the request timeout (60 s)
    # is above the node's write_request_timeout (30 s, B3a)
    prof = ExecutionProfile(request_timeout=timeout, consistency_level=cl, retry_policy=FallthroughRetryPolicy(),
                            load_balancing_policy=WhiteListRoundRobinPolicy([host]))
    c = Cluster([host], protocol_version=PROTOCOL, execution_profiles={EXEC_PROFILE_DEFAULT: prof},
                token_metadata_enabled=False)
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
        print(json.dumps({'schema': 'ok'}))
    elif mode == 'setting':
        c, s = connect(host, ConsistencyLevel.ONE)
        r = s.execute('SELECT name, value FROM system_views.settings WHERE name = %s', [sys.argv[3]]).one()
        print(json.dumps({'host': host, 'name': sys.argv[3], 'value': r.value if r else None}))
    elif mode == 'load':
        first, nt, per, size, keylog = int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6]), sys.argv[7]
        c, s = connect(host, ConsistencyLevel.ALL)
        ps = s.prepare('INSERT INTO ks.t (k, v) VALUES (?, ?)')
        lock = threading.Lock()
        res = {'ok': 0, 'err': 0, 'errors': {}}
        log = open(keylog, 'a')

        def worker(t):
            for i in range(per):
                k = first + t * per + i
                v = os.urandom(size)
                t0 = int(time.time() * 1000)
                try:
                    s.execute(ps, (k, v))
                    r, why = 'ok', ''
                except Exception as e:  # the reading: timeout, failure or server error
                    r, why = 'err', f'{type(e).__name__}: {str(e)[:200]}'.replace(',', ';').replace('\n', ' ')
                t1 = int(time.time() * 1000)
                with lock:
                    res[r] += 1
                    if r == 'err':
                        n = why.split(':')[0]
                        res['errors'][n] = res['errors'].get(n, 0) + 1
                    log.write(f'{k},{size},{t},{t0},{t1},{r},{why}\n')
                    log.flush()

        t_start = time.time()
        th = [threading.Thread(target=worker, args=(t,)) for t in range(nt)]
        for x in th:
            x.start()
        for x in th:
            x.join()
        log.close()
        print(json.dumps({'first': first, 'threads': nt, 'per_thread': per, 'bytes': size, 'ok': res['ok'],
                          'err': res['err'], 'errors': res['errors'], 'seconds': round(time.time() - t_start, 1),
                          'protocol': PROTOCOL}))
    elif mode == 'count':
        c, s = connect(host, ConsistencyLevel.ONE, timeout=120)
        from cassandra.query import SimpleStatement
        print(json.dumps({'host': host, 'count': s.execute(SimpleStatement('SELECT count(*) FROM ks.t', fetch_size=1)).one()[0]}))
    else:
        sys.exit(__doc__)
    c.shutdown()


main()
