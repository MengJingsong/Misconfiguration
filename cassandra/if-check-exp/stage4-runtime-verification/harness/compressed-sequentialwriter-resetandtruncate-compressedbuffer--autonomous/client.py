#!/usr/bin/env python3
"""Cluster-tier client (B3c) of compressed-sequentialwriter-resetandtruncate-compressedbuffer--autonomous. Bundled Python driver,
protocol 4, one host, native port from CS_NATIVE_PORT (9349). Modes (one JSON object on stdout):
  create <host> <chunk_kb|none> <table> ...   CREATE KEYSPACE ks (RF 1); each table (k bigint PRIMARY KEY, v blob) is created plain, then
                                              ALTER TABLE ... WITH compression = {LZ4Compressor, chunk_length_in_kb: N} (or {'enabled':'false'})
                                              and compaction {'class': 'SizeTieredCompactionStrategy', 'enabled': 'false'}
  load <host> <table> <first_key> <n> <bytes> <conc>   n INSERTs of <bytes> random bytes (k = first_key ..) at CL ONE
  scrubtable <host> <chunk_kb> <partitions> <rows> <bytes>   ks.scr (k int, c int, v blob, PRIMARY KEY (k, c)), LZ4 chunk_kb, compaction disabled,
                                              partitions x rows INSERTs of <bytes> random bytes
  count <host> <table>  / settings <host> <name> ...
"""
import glob, json, os, sys, threading, time

CASS = os.environ.get('CASSANDRA_HOME', os.path.expanduser('~/s4-cs'))
LIB = os.path.join(CASS, 'lib')
PORT = int(os.environ.get('CS_NATIVE_PORT', 9349))


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


def connect(host, timeout=120):
    prof = ExecutionProfile(request_timeout=timeout, consistency_level=ConsistencyLevel.ONE, retry_policy=FallthroughRetryPolicy(),
                            load_balancing_policy=WhiteListRoundRobinPolicy([host]))
    c = Cluster([host], port=PORT, protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof})
    return c, c.connect()


def compr(chunk):
    if chunk == 'none':
        return "{'enabled': 'false'}"
    return "{'class': 'LZ4Compressor', 'chunk_length_in_kb': '%s'}" % chunk


def inserts(s, ps, keys, make_val, conc):
    sem = threading.Semaphore(conc)
    errs = []
    t0 = time.time()

    def ok(_):
        sem.release()

    def bad(e):
        errs.append(str(e)[:200])
        sem.release()
    n = 0
    for key in keys:
        sem.acquire()
        f = s.execute_async(ps, key + (make_val(),))
        f.add_callbacks(ok, bad)
        n += 1
    for _ in range(conc):
        sem.acquire()
    return {'n': n, 'err': len(errs), 'first_err': errs[:1], 'seconds': round(time.time() - t0, 2)}


def main():
    mode, host = sys.argv[1], sys.argv[2]
    c, s = connect(host)
    if mode == 'create':
        chunk, tables = sys.argv[3], sys.argv[4:]
        s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
        for t in tables:
            s.execute('CREATE TABLE IF NOT EXISTS ks.%s (k bigint PRIMARY KEY, v blob)' % t)
            s.execute('ALTER TABLE ks.%s WITH compression = %s' % (t, compr(chunk)))
            s.execute("ALTER TABLE ks.%s WITH compaction = {'class': 'SizeTieredCompactionStrategy', 'enabled': 'false'}" % t)
        c.control_connection.wait_for_schema_agreement(wait_time=60)
        out = {}
        for t in tables:
            r = s.execute("SELECT compression FROM system_schema.tables WHERE keyspace_name='ks' AND table_name=%s", [t]).one()
            out[t] = dict(r.compression)
        print(json.dumps({'created': out}))
    elif mode == 'load':
        t, first, n, size, conc = sys.argv[3], int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6]), int(sys.argv[7])
        ps = s.prepare('INSERT INTO ks.%s (k, v) VALUES (?, ?)' % t)
        r = inserts(s, ps, ((first + i,) for i in range(n)), lambda: os.urandom(size), conc)
        print(json.dumps(r))
    elif mode == 'scrubtable':
        chunk, parts, rows, size = sys.argv[3], int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6])
        s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
        s.execute('CREATE TABLE IF NOT EXISTS ks.scr (k int, c int, v blob, PRIMARY KEY (k, c))')
        s.execute('ALTER TABLE ks.scr WITH compression = %s' % compr(chunk))
        s.execute("ALTER TABLE ks.scr WITH compaction = {'class': 'SizeTieredCompactionStrategy', 'enabled': 'false'}")
        c.control_connection.wait_for_schema_agreement(wait_time=60)
        ps = s.prepare('INSERT INTO ks.scr (k, c, v) VALUES (?, ?, ?)')
        r = inserts(s, ps, ((p, i) for p in range(parts) for i in range(rows)), lambda: os.urandom(size), 8)
        print(json.dumps(r))
    elif mode == 'count':
        print(json.dumps({'count': s.execute('SELECT count(*) FROM ks.%s' % sys.argv[3], timeout=600).one()[0]}))
    elif mode == 'settings':
        res = {}
        for name in sys.argv[3:]:
            r = s.execute('SELECT name, value FROM system_views.settings WHERE name = %s', [name]).one()
            res[name] = r.value if r else None
        print(json.dumps(res))
    else:
        sys.exit(__doc__)
    c.shutdown()


main()
