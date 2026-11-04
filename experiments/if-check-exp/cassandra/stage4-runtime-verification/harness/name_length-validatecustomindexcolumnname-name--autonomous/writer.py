#!/usr/bin/env python3
"""writer.py <host> <mode> ...   (bundled Python driver of the build copy, CASSANDRA_HOME; protocol 4, CL ONE)
  schema <table> <L> <custom|plain|none>   create ks (RF 1) and ks.<table> (k int PRIMARY KEY, <col> text) with col = 'c' + 'x' * (L-1);
                                           custom: CREATE CUSTOM INDEX i_<table> ... USING SASIIndex; plain: CREATE INDEX i_<table>;
                                           prints {"create_index": "ok"|"rejected"|"none", "message": ...}
  indexcount <table>                       number of rows of system_schema.indexes for ks.<table>
  write <table> <L> <N> <seed>             N single-row inserts, value = seeded random 100-char hex (the same data for every table with the same seed);
                                           128 in flight; prints {ok, errors, messages, seconds}
  drop <table>
"""
import glob, json, os, random, sys, time, collections
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
col = lambda L: 'c' + 'x' * (int(L) - 1)
if mode == 'schema':
    t, L, kind = sys.argv[3], sys.argv[4], sys.argv[5]
    s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    s.execute(f"CREATE TABLE ks.{t} (k int PRIMARY KEY, {col(L)} text)")
    out = {'created': t, 'create_index': 'none'}
    try:
        if kind == 'custom':
            s.execute(f"CREATE CUSTOM INDEX i_{t} ON ks.{t} ({col(L)}) USING 'org.apache.cassandra.index.sasi.SASIIndex'")
            out['create_index'] = 'ok'
        elif kind == 'plain':
            s.execute(f"CREATE INDEX i_{t} ON ks.{t} ({col(L)})")
            out['create_index'] = 'ok'
    except Exception as e:
        out['create_index'] = 'rejected'; out['message'] = type(e).__name__ + ': ' + str(e)[:600]
    print(json.dumps(out))
elif mode == 'indexcount':
    r = s.execute("SELECT index_name FROM system_schema.indexes WHERE keyspace_name='ks' AND table_name=%s", (sys.argv[3],))
    print(json.dumps({'count': len(list(r))}))
elif mode == 'drop':
    s.execute(f"DROP TABLE ks.{sys.argv[3]}")
    print(json.dumps({'dropped': sys.argv[3]}))
elif mode == 'write':
    table, L, N, seed = sys.argv[3], sys.argv[4], int(sys.argv[5]), int(sys.argv[6])
    st = s.prepare(f'INSERT INTO ks.{table} (k, {col(L)}) VALUES (?, ?)')
    rnd = random.Random(seed)
    def params():
        for i in range(N):
            yield (i, rnd.randbytes(50).hex())
    t0 = time.time()
    res = execute_concurrent_with_args(s, st, params(), concurrency=128, raise_on_first_error=False)
    msgs = collections.Counter(); ok = 0
    for good, r in res:
        if good: ok += 1
        else: msgs[type(r).__name__ + ': ' + str(r)[:300]] += 1
    print(json.dumps({'ok': ok, 'errors': N - ok, 'messages': msgs, 'seconds': round(time.time() - t0, 1)}))
cl.shutdown()
