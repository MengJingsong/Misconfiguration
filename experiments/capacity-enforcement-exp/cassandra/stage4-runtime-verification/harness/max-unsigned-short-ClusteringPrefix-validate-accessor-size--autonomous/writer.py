#!/usr/bin/env python3
"""writer.py <host> <mode> ...   (bundled Python driver of the build copy, CASSANDRA_HOME; protocol 4, CL ONE)
  schema <table>                  ks (RF 1) and ks.<table> (pk int, ck blob, v int, PRIMARY KEY (pk, ck))
  schema2 <table>                 ks.<table> (pk int, c1 blob, c2 blob, v int, PRIMARY KEY (pk, c1, c2))
  write <table> <K> <N> <seed>    N inserts, pk = i mod 100, ck = 8-byte big-endian counter + seeded random bytes up to K bytes,
                                  32 in flight; prints one JSON line {ok, errors, messages:{msg:count}, seconds}
  write2 <table> <S1> <S2> <N> <seed>   the same into the two-column table, c1 of S1 and c2 of S2 random bytes
  probe <table>                   B3i.8 probe on a schema table: (a) plain insert with a 65536-byte ck, (b) INSERT IF NOT EXISTS with the
                                  same, (c) DELETE ... ck > <70000-byte value>; prints one JSON line with the outcome of each
  drop <table>
"""
import glob, json, os, random, struct, sys, time, collections
CASS = os.environ.get('CASSANDRA_HOME', os.path.expanduser('~/s4-b9-cp'))
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
prof = ExecutionProfile(request_timeout=(40 if mode == 'probe' else 120), consistency_level=ConsistencyLevel.ONE,
                        load_balancing_policy=WhiteListRoundRobinPolicy([host]))
cl = Cluster([host], protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof}, connect_timeout=30)
s = cl.connect()
def summarize(res, n, t0):
    msgs = collections.Counter(); ok = 0
    for good, r in res:
        if good: ok += 1
        else: msgs[type(r).__name__ + ': ' + str(r)[:200]] += 1
    print(json.dumps({'ok': ok, 'errors': n - ok, 'messages': msgs, 'seconds': round(time.time() - t0, 1)}))
if mode == 'schema':
    s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    s.execute(f"CREATE TABLE ks.{sys.argv[3]} (pk int, ck blob, v int, PRIMARY KEY (pk, ck))")
    print(json.dumps({'created': sys.argv[3]}))
elif mode == 'schema2':
    s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    s.execute(f"CREATE TABLE ks.{sys.argv[3]} (pk int, c1 blob, c2 blob, v int, PRIMARY KEY (pk, c1, c2))")
    print(json.dumps({'created': sys.argv[3]}))
elif mode == 'drop':
    s.execute(f"DROP TABLE ks.{sys.argv[3]}")
    print(json.dumps({'dropped': sys.argv[3]}))
elif mode == 'write':
    table, K, N, seed = sys.argv[3], int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6])
    st = s.prepare(f'INSERT INTO ks.{table} (pk, ck, v) VALUES (?, ?, ?)')
    rnd = random.Random(seed)
    def params():
        for i in range(N):
            yield (i % 100, struct.pack('>Q', i) + rnd.randbytes(K - 8), i)
    t0 = time.time()
    summarize(execute_concurrent_with_args(s, st, params(), concurrency=32, raise_on_first_error=False), N, t0)
elif mode == 'write2':
    table, S1, S2, N, seed = sys.argv[3], int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6]), int(sys.argv[7])
    st = s.prepare(f'INSERT INTO ks.{table} (pk, c1, c2, v) VALUES (?, ?, ?, ?)')
    rnd = random.Random(seed)
    def params2():
        for i in range(N):
            yield (i % 100, struct.pack('>Q', i) + rnd.randbytes(S1 - 8), rnd.randbytes(S2), i)
    t0 = time.time()
    summarize(execute_concurrent_with_args(s, st, params2(), concurrency=8, raise_on_first_error=False), N, t0)
elif mode == 'probe':
    t = sys.argv[3]; rnd = random.Random(99); out = {}
    def go(name, fn):
        t0 = time.time()
        try:
            fn(); out[name] = {'outcome': 'accepted', 'seconds': round(time.time() - t0, 1)}
        except Exception as e:
            out[name] = {'outcome': type(e).__name__ + ': ' + str(e)[:300], 'seconds': round(time.time() - t0, 1)}
    big = struct.pack('>Q', 1) + rnd.randbytes(65536 - 8)
    sl = struct.pack('>Q', 2) + rnd.randbytes(70000 - 8)
    ins = s.prepare(f'INSERT INTO ks.{t} (pk, ck, v) VALUES (?, ?, ?)')
    cas = s.prepare(f'INSERT INTO ks.{t} (pk, ck, v) VALUES (?, ?, ?) IF NOT EXISTS')
    dele = s.prepare(f'DELETE FROM ks.{t} WHERE pk = ? AND ck > ?')
    go('a_plain_insert_65536', lambda: s.execute(ins, (1, big, 1)))
    go('b_cas_insert_65536', lambda: s.execute(cas, (2, big, 1)))
    go('c_slice_delete_70000', lambda: s.execute(dele, (3, sl)))
    print(json.dumps(out))
cl.shutdown()
