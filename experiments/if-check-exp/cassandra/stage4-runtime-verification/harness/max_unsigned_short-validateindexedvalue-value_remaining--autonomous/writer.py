#!/usr/bin/env python3
"""writer.py <host> <mode> ...   (bundled Python driver of the build copy, CASSANDRA_HOME; protocol 4, CL ONE)
  schema <table> <index|noindex>      create ks (RF 1) and ks.<table> (k int PRIMARY KEY, v text); with 'index' also CREATE INDEX idx_<table> ON ks.<table> (v)
  write <table> <S> <N> <seed>        N single-row inserts, v = 8-digit counter + seeded random base64 ASCII, exactly S chars; 32 in flight;
                                      prints one JSON line {ok, errors, messages:{msg:count}, seconds}
  drop <table>
"""
import glob, json, os, random, sys, time, collections, base64
CASS = os.environ.get('CASSANDRA_HOME', os.path.expanduser('~/s4-b2/c'))
def find_zip(prefix):
    z = glob.glob(os.path.join(CASS, 'lib', prefix + '*.zip')); return max(z) if z else None
cql = find_zip('cassandra-driver-internal-only-')
ver = os.path.splitext(os.path.basename(cql))[0][len('cassandra-driver-internal-only-'):]
sys.path.insert(0, os.path.join(cql, 'cassandra-driver-' + ver))
for lib in ('pure_sasl-', 'wcwidth-', 'pyasyncore-', 'geomet-'):
    z = find_zip(lib)
    if z: sys.path.insert(0, z)
from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
from cassandra.policies import WhiteListRoundRobinPolicy
from cassandra import ConsistencyLevel
from cassandra.concurrent import execute_concurrent_with_args
host, mode = sys.argv[1], sys.argv[2]
prof = ExecutionProfile(request_timeout=120, consistency_level=ConsistencyLevel.ONE,
                        load_balancing_policy=WhiteListRoundRobinPolicy([host]))
cl = Cluster([host], protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof}, connect_timeout=30)
s = cl.connect()
if mode == 'schema':
    t = sys.argv[3]
    s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    s.execute(f"CREATE TABLE ks.{t} (k int PRIMARY KEY, v text)")
    if sys.argv[4] == 'index':
        s.execute(f"CREATE INDEX idx_{t} ON ks.{t} (v)")
    print(json.dumps({'created': t, 'index': sys.argv[4]}))
elif mode == 'drop':
    s.execute(f"DROP TABLE ks.{sys.argv[3]}")
    print(json.dumps({'dropped': sys.argv[3]}))
elif mode == 'write':
    table, S, N, seed = sys.argv[3], int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6])
    st = s.prepare(f'INSERT INTO ks.{table} (k, v) VALUES (?, ?)')
    rnd = random.Random(seed)
    nb = (S * 3) // 4 + 8
    def params():
        for i in range(N):
            yield (i, ('%08d' % i + base64.b64encode(rnd.randbytes(nb)).decode('ascii'))[:S])
    t0 = time.time()
    res = execute_concurrent_with_args(s, st, params(), concurrency=32, raise_on_first_error=False)
    msgs = collections.Counter(); ok = 0
    for good, r in res:
        if good: ok += 1
        else: msgs[type(r).__name__ + ': ' + str(r)[:300]] += 1
    print(json.dumps({'ok': ok, 'errors': N - ok, 'messages': msgs, 'seconds': round(time.time() - t0, 1)}))
cl.shutdown()
