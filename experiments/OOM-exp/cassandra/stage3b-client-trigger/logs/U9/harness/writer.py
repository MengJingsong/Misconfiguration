#!/usr/bin/env python3
"""U9 stage 3-b confirm writer, adapted from the stage-2 writer.py. Changes: every connection authenticates
(PlainTextAuthProvider, role from U9_USER / U9_PASS); 'admin' (superuser only: schema, roles, GRANTs) and
'privcheck' (as the attacker: what the role may not do) modes. 'write' is unchanged apart from the login.
Bundled Python driver of the build copy (CASSANDRA_HOME), protocol 4, CL ONE, DCAwareRoundRobinPolicy,
token_metadata_enabled=False, <= 16 in flight.
  writer.py admin                                 as cassandra/cassandra: ks.t1 (admin-made, as stage 2), vks.vt, roles
  writer.py privcheck                             as the attacker: statements outside its grant must fail
  writer.py write <table> <big|small> <start> <end> <seed>
        rows i in [start, end) into partition pk = 1 of ks.<table>:
          big:   ck = 8-byte BE i + 65,527 seeded random bytes (65,535 B), v = 64 random bytes
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
from cassandra.auth import PlainTextAuthProvider
from cassandra import ConsistencyLevel
from cassandra.concurrent import execute_concurrent_with_args

ATK, ATKPW = 'u9atk', 'u9atk-pw'
VIC, VICPW = 'u9vic', 'u9vic-pw'

def connect(user, pw, wait=0):
    prof = ExecutionProfile(request_timeout=120, consistency_level=ConsistencyLevel.ONE,
                            load_balancing_policy=DCAwareRoundRobinPolicy(local_dc='datacenter1'))
    t_end = time.time() + wait
    while True:
        try:
            cl = Cluster(['127.0.0.1'], protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof},
                         connect_timeout=30, token_metadata_enabled=False,
                         auth_provider=PlainTextAuthProvider(username=user, password=pw))
            return cl, cl.connect()
        except Exception as e:
            if time.time() >= t_end:
                raise
            print(json.dumps({'connect_retry': user, 'err': type(e).__name__ + ': ' + str(e)[:160]}), flush=True)
            time.sleep(3)

mode = sys.argv[1]
if mode == 'admin':
    cl, s = connect('cassandra', 'cassandra', wait=120)   # default superuser, created ~10 s after start
    stmts = [
        "CREATE KEYSPACE ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}",
        "CREATE TABLE ks.t1 (pk int, ck blob, v blob, PRIMARY KEY (pk, ck))",
        "CREATE KEYSPACE vks WITH replication = {'class':'SimpleStrategy','replication_factor':1}",
        "CREATE TABLE vks.vt (k int PRIMARY KEY, v blob)",
        f"CREATE ROLE {ATK} WITH PASSWORD = '{ATKPW}' AND LOGIN = true AND SUPERUSER = false",
        f"GRANT MODIFY ON TABLE ks.t1 TO {ATK}",
        f"CREATE ROLE {VIC} WITH PASSWORD = '{VICPW}' AND LOGIN = true AND SUPERUSER = false",
        f"GRANT SELECT ON KEYSPACE vks TO {VIC}",
        f"GRANT MODIFY ON KEYSPACE vks TO {VIC}",
    ]
    for q in stmts:
        s.execute(q, timeout=60)
        print(json.dumps({'superuser_cql': q.replace(ATKPW, '***').replace(VICPW, '***')}), flush=True)
    for r in s.execute("LIST ROLES"):
        print(json.dumps({'role': r.role, 'super': r.super, 'login': r.login}), flush=True)
    for who in (ATK, VIC):
        for r in s.execute(f"LIST ALL PERMISSIONS OF {who}"):
            print(json.dumps({'perm_of': who, 'role': r.role, 'resource': r.resource, 'permission': r.permission}), flush=True)
    cl.shutdown()
elif mode == 'privcheck':
    cl, s = connect(ATK, ATKPW, wait=30)
    checks = [
        ('select own target table', "SELECT pk FROM ks.t1 LIMIT 1"),
        ('create table in ks', "CREATE TABLE ks.x (a int PRIMARY KEY)"),
        ('create keyspace', "CREATE KEYSPACE atk WITH replication = {'class':'SimpleStrategy','replication_factor':1}"),
        ('alter target table', "ALTER TABLE ks.t1 WITH comment = 'x'"),
        ('read victim table', "SELECT k FROM vks.vt LIMIT 1"),
        ('write victim table', "INSERT INTO vks.vt (k, v) VALUES (1, 0x00)"),
        ('create role', "CREATE ROLE x WITH LOGIN = true"),
    ]
    for name, q in checks:
        try:
            s.execute(q, timeout=30); out = 'ALLOWED'
        except Exception as e:
            out = type(e).__name__ + ': ' + str(e)[:140]
        print(json.dumps({'privcheck': name, 'stmt': q, 'result': out}), flush=True)
    st = s.prepare('INSERT INTO ks.t1 (pk, ck, v) VALUES (1, ?, ?)')
    print(json.dumps({'privcheck': 'prepare attack INSERT', 'result': 'ok'}), flush=True)
    cl.shutdown()
elif mode == 'write':
    cl, s = connect(os.environ['U9_USER'], os.environ['U9_PASS'], wait=20)
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
    print(json.dumps({'table': table, 'kind': kind, 'user': os.environ['U9_USER'], 'rows': [a, b], 'ok': ok,
                      'errors': n - ok, 'messages': msgs, 'seconds': round(time.time() - t0, 1),
                      'mb': round(n * 0.06566, 1)}))
    cl.shutdown()
