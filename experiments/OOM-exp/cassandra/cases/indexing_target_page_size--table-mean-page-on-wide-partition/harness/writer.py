#!/usr/bin/env python3
"""B20 writer / CQL helper (stage 2), adapted from U9's writer.py. Bundled Python driver of the build copy
(CASSANDRA_HOME), protocol 4, CL ONE, DCAwareRoundRobinPolicy, token_metadata_enabled=False.
  writer.py schema                      ks (RF 1), ks.t (pk bigint, ck int, v blob, PRIMARY KEY (pk, ck))
  writer.py wide <a> <b>                rows ck in [a, b) of pk = 0, v = 1,048,576 seeded random bytes, <= 16 in flight
  writer.py small <a> <b> <inflight>    partitions pk in [a, b), one row ck = pk mod 4000, v = 64 random bytes
  writer.py cql "<statement>" [timeout] execute one statement, print the rows (count queries)
Prints one JSON line per command.
"""
import glob, json, os, random, sys, time, collections
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
tmo = float(sys.argv[3]) if mode == 'cql' and len(sys.argv) > 3 else 120
prof = ExecutionProfile(request_timeout=tmo, consistency_level=ConsistencyLevel.ONE,
                        load_balancing_policy=DCAwareRoundRobinPolicy(local_dc='datacenter1'))
cl = Cluster(['127.0.0.1'], protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof},
             connect_timeout=30, token_metadata_enabled=False)
s = cl.connect()
t0 = time.time()
def run(st, params, conc):
    res = execute_concurrent_with_args(s, st, params, concurrency=conc, raise_on_first_error=False)
    msgs = collections.Counter(); ok = 0; n = 0
    for good, r in res:
        n += 1
        if good: ok += 1
        else: msgs[type(r).__name__ + ': ' + str(r)[:200]] += 1
    return n, ok, msgs
if mode == 'schema':
    s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    s.execute("CREATE TABLE IF NOT EXISTS ks.t (pk bigint, ck int, v blob, PRIMARY KEY (pk, ck))")
    print(json.dumps({'created': 'ks.t'}))
elif mode == 'wide':
    a, b = int(sys.argv[2]), int(sys.argv[3])
    st = s.prepare('INSERT INTO ks.t (pk, ck, v) VALUES (0, ?, ?)')
    def params():
        for i in range(a, b):
            yield (i, random.Random(1_000_003 * 7 + i).randbytes(1048576))
    n, ok, msgs = run(st, params(), 16)
    print(json.dumps({'kind': 'wide', 'rows': [a, b], 'ok': ok, 'errors': n - ok, 'messages': msgs,
                      'seconds': round(time.time() - t0, 1)}))
elif mode == 'small':
    a, b, conc = int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
    st = s.prepare('INSERT INTO ks.t (pk, ck, v) VALUES (?, ?, ?)')
    rnd = random.Random(2_000_003 + a)
    def params():
        for pk in range(a, b):
            yield (pk, pk % 4000, rnd.randbytes(64))
    n, ok, msgs = run(st, params(), conc)
    print(json.dumps({'kind': 'small', 'rows': [a, b], 'ok': ok, 'errors': n - ok, 'messages': msgs,
                      'seconds': round(time.time() - t0, 1)}))
elif mode == 'cql':
    rows = list(s.execute(sys.argv[2]))
    print(json.dumps({'cql': sys.argv[2], 'rows': [list(map(str, r)) for r in rows][:20],
                      'seconds': round(time.time() - t0, 1)}))
cl.shutdown()
