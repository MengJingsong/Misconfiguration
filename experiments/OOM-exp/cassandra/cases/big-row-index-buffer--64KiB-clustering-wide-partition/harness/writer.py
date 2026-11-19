#!/usr/bin/env python3
"""U9 writer (stage 2), adapted from the stage-4 writer of OC-277. Bundled Python driver of the build copy
(CASSANDRA_HOME), protocol 4, CL ONE, DCAwareRoundRobinPolicy, token_metadata_enabled=False, <= 16 in flight.
  writer.py schema <table>                       ks (RF 1), ks.<table> (pk int, ck blob, v blob, PRIMARY KEY (pk, ck))
  writer.py write <table> <big|small> <start> <end> <seed>
        rows i in [start, end) into partition pk = 1:
          big:   ck = 8-byte BE i + 65,527 seeded random bytes (65,535 B), v = 64 random bytes
          small: ck = 8-byte BE i + 8 random bytes (16 B),           v = 65,583 random bytes
        the generator is seeded with seed*1_000_003 + start so a chunked load is reproducible.
        prints one JSON line {ok, errors, messages, seconds, mb}
"""
import glob, json, os, random, struct, sys, time, collections
CASS = os.environ['CASSANDRA_HOME']
def find_zip(prefix):
    z = glob.glob(os.path.join(CASS, 'lib', prefix + '*.zip')); return max(z) if z else None
cql = find_zip('cassandra-driver-internal-only-')
ver = os.path.splitext(os.path.basename(cql))[0][len('cassandra-driver-internal-only-'):]
sys.path.insert(0, os.path.join(cql, 'cassandra-driver-' + ver))
for lib in ('pure_sasl-', 'wcwidth-', 'pyasyncore-', 'geomet-'):
    z = find_zip(lib)
    if z: sys.path.insert(0, z)
from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
from cassandra.policies import DCAwareRoundRobinPolicy
from cassandra import ConsistencyLevel
from cassandra.concurrent import execute_concurrent_with_args
mode = sys.argv[1]
prof = ExecutionProfile(request_timeout=120, consistency_level=ConsistencyLevel.ONE,
                        load_balancing_policy=DCAwareRoundRobinPolicy(local_dc='datacenter1'))
cl = Cluster(['127.0.0.1'], protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof},
             connect_timeout=30, token_metadata_enabled=False)
s = cl.connect()
if mode == 'schema':
    s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    s.execute(f"CREATE TABLE ks.{sys.argv[2]} (pk int, ck blob, v blob, PRIMARY KEY (pk, ck))")
    print(json.dumps({'created': sys.argv[2]}))
elif mode == 'write':
    table, kind, a, b, seed = sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6])
    st = s.prepare(f'INSERT INTO ks.{table} (pk, ck, v) VALUES (1, ?, ?)')
    rnd = random.Random(seed * 1_000_003 + a)
    def params():
        for i in range(a, b):
            if kind == 'big':
                yield (struct.pack('>Q', i) + rnd.randbytes(65527), rnd.randbytes(64))
            else:
                yield (struct.pack('>Q', i) + rnd.randbytes(8), rnd.randbytes(65583))
    t0 = time.time()
    res = execute_concurrent_with_args(s, st, params(), concurrency=16, raise_on_first_error=False)
    msgs = collections.Counter(); ok = 0
    for good, r in res:
        if good: ok += 1
        else: msgs[type(r).__name__ + ': ' + str(r)[:200]] += 1
    n = b - a
    print(json.dumps({'table': table, 'kind': kind, 'rows': [a, b], 'ok': ok, 'errors': n - ok, 'messages': msgs,
                      'seconds': round(time.time() - t0, 1), 'mb': round(n * 0.06566, 1)}))
cl.shutdown()
