#!/usr/bin/env python3
"""writer.py <host> <mode> ...   (bundled Python driver of the build copy, CASSANDRA_HOME; protocol 4, CL ONE)
  schema <table>                      create ks (RF 1) and ks.<table> (k blob PRIMARY KEY, v int)
  write <table> <K> <N> <seed>        N single-partition inserts, key = 8-byte big-endian counter + seeded random bytes up to K bytes,
                                      32 in flight; prints one JSON line {ok, errors, messages:{msg:count}, seconds}
  drop <table>
"""
import glob, json, os, random, struct, sys, time, collections
CASS = os.environ.get('CASSANDRA_HOME', os.path.expanduser('~/s4-b8-uk/c'))
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
    s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    s.execute(f"CREATE TABLE ks.{sys.argv[3]} (k blob PRIMARY KEY, v int)")
    print(json.dumps({'created': sys.argv[3]}))
elif mode == 'drop':
    s.execute(f"DROP TABLE ks.{sys.argv[3]}")
    print(json.dumps({'dropped': sys.argv[3]}))
elif mode == 'write':
    table, K, N, seed = sys.argv[3], int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6])
    st = s.prepare(f'INSERT INTO ks.{table} (k, v) VALUES (?, ?)')
    rnd = random.Random(seed)
    def params():
        for i in range(N):
            yield (struct.pack('>Q', i) + rnd.randbytes(K - 8), i)
    t0 = time.time()
    res = execute_concurrent_with_args(s, st, params(), concurrency=32, raise_on_first_error=False)
    msgs = collections.Counter(); ok = 0
    for good, r in res:
        if good: ok += 1
        else: msgs[type(r).__name__ + ': ' + str(r)[:200]] += 1
    print(json.dumps({'ok': ok, 'errors': N - ok, 'messages': msgs, 'seconds': round(time.time() - t0, 1)}))
cl.shutdown()
