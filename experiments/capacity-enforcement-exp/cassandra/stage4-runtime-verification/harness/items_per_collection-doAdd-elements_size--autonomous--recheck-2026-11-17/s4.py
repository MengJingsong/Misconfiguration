#!/usr/bin/env python3
"""Client of the recheck run (design R4-R5) of items_per_collection-doAdd-elements_size--autonomous.

  setup                       keyspace probe (RF 1); set tables z s5 s6 s7 (k int PRIMARY KEY, v set<int>); blob table b6 (k int PRIMARY KEY, b blob)
  load <table> <M> <chunk>    appends v = v + {chunk distinct ints} on k = 424242 until M items (M/chunk statements)
  loadblob <table> <bytes>    one INSERT of a blob of <bytes> bytes on k = 424242
  read <table> <col>          SELECT <col> FROM probe.<table> WHERE k = 424242; prints accepted/error, count, value bytes, seconds
  setupauth <table>           as cassandra: role app (LOGIN, not superuser), GRANT ALL ON KEYSPACE probe, set table <table>
  guardcheck <table> <n>      as app: one INSERT of n items on k = 1 (expected rejected when n > T)
Auth: S4_USER / S4_PW in the environment select PlainTextAuthProvider; unset = no auth (AllowAllAuthenticator, the default).
The set read does not build a Python set: SetType.deserialize_safe is replaced to return the count (the value's first 4 bytes,
protocol >= 3) and the value's byte length; the server's work is unchanged. Each call prints one line starting RESULT."""
import glob, logging, os, sys, time

CASS = os.environ['CASSANDRA_HOME']
LIB = os.path.join(CASS, 'lib')
KEY = 424242


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

logging.basicConfig(level=logging.ERROR)
logging.getLogger('cassandra').setLevel(logging.CRITICAL)
from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402
from cassandra import cqltypes  # noqa: E402
from cassandra.auth import PlainTextAuthProvider  # noqa: E402
from cassandra.policies import DCAwareRoundRobinPolicy  # noqa: E402


def _setlen(cls, byts, protocol_version):
    return ('SETLEN', int.from_bytes(byts[:4], 'big', signed=True), len(byts))



def connect(user=None, pw=None):
    user = user or os.environ.get('S4_USER'); pw = pw or os.environ.get('S4_PW')
    prof = ExecutionProfile(request_timeout=600, consistency_level=ConsistencyLevel.ONE,
                            load_balancing_policy=DCAwareRoundRobinPolicy(local_dc='datacenter1'))
    kw = dict(protocol_version=5, token_metadata_enabled=False, idle_heartbeat_interval=0,
              execution_profiles={EXEC_PROFILE_DEFAULT: prof})
    if user:
        kw['auth_provider'] = PlainTextAuthProvider(user, pw)
    last = None
    for _ in range(60):
        try:
            cl = Cluster(['127.0.0.1'], **kw)
            return cl, cl.connect()
        except Exception as e:  # superuser setup delay after start under PasswordAuthenticator
            last = e
            time.sleep(2)
    raise SystemExit('RESULT connect FAILED %r' % (last,))


def err(e):
    return (type(e).__name__ + ': ' + str(e)).replace('\n', ' ')[:400]


cmd = sys.argv[1]
t0 = time.time()
if cmd == 'setup':
    cl, s = connect()
    s.execute("CREATE KEYSPACE IF NOT EXISTS probe WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    for t in ('z', 's5', 's6', 's7'):
        s.execute('CREATE TABLE IF NOT EXISTS probe.%s (k int PRIMARY KEY, v set<int>)' % t)
    s.execute('CREATE TABLE IF NOT EXISTS probe.b6 (k int PRIMARY KEY, b blob)')
    rel = s.execute('SELECT release_version FROM system.local').one()[0]
    cl.shutdown()
    print('RESULT setup release=%s seconds=%.1f' % (rel, time.time() - t0))
elif cmd == 'load':
    table, M, chunk = sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    cl, s = connect()
    add = s.prepare('UPDATE probe.%s SET v = v + ? WHERE k = ?' % table)
    acc = rej = 0; first = None
    for j in range(M // chunk):
        try:
            s.execute(add, (set(range(j * chunk, (j + 1) * chunk)), KEY)); acc += 1
        except Exception as e:
            rej += 1; first = first or err(e)
    cl.shutdown()
    print('RESULT load table=%s M=%d chunk=%d statements=%d accepted=%d rejected=%d seconds=%.1f first=%s'
          % (table, M, chunk, M // chunk, acc, rej, time.time() - t0, first))
elif cmd == 'loadblob':
    table, n = sys.argv[2], int(sys.argv[3])
    cl, s = connect()
    ins = s.prepare('INSERT INTO probe.%s (k, b) VALUES (?, ?)' % table)
    try:
        s.execute(ins, (KEY, bytes(n))); r = 'accepted'
    except Exception as e:
        r = 'rejected ' + err(e)
    cl.shutdown()
    print('RESULT loadblob table=%s bytes=%d outcome=%s seconds=%.1f' % (table, n, r, time.time() - t0))
elif cmd == 'read':
    table, col = sys.argv[2], sys.argv[3]
    cl, s = connect()
    cqltypes.SetType.deserialize_safe = classmethod(_setlen)  # after connect: the driver's own system-table reads keep real sets
    t1 = time.time()
    try:
        row = s.execute('SELECT %s FROM probe.%s WHERE k = %d' % (col, table, KEY)).one()
        dt = time.time() - t1
        v = None if row is None else getattr(row, col)
        if v is None:
            cnt, nb = 0, 0
        elif isinstance(v, tuple) and v and v[0] == 'SETLEN':
            cnt, nb = v[1], v[2]
        else:
            cnt, nb = 1, len(v)
        out = 'accepted count=%d value_bytes=%d' % (cnt, nb)
    except Exception as e:
        dt = time.time() - t1
        out = 'error count=-1 value_bytes=-1 msg=%s' % err(e)
    cl.shutdown()
    print('RESULT read table=%s col=%s user=%s %s query_seconds=%.3f t_start=%.3f t_end=%.3f'
          % (table, col, os.environ.get('S4_USER', '-'), out, dt, t1, t1 + dt))
elif cmd == 'setupauth':
    table = sys.argv[2]
    cl, s = connect('cassandra', 'cassandra')
    s.execute("CREATE KEYSPACE IF NOT EXISTS probe WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    s.execute('CREATE TABLE IF NOT EXISTS probe.%s (k int PRIMARY KEY, v set<int>)' % table)
    s.execute("CREATE ROLE IF NOT EXISTS app WITH PASSWORD = 'app' AND LOGIN = true AND SUPERUSER = false")
    s.execute('GRANT ALL ON KEYSPACE probe TO app')
    su = s.execute("SELECT is_superuser FROM system_auth.roles WHERE role = 'app'").one()[0]
    cl.shutdown()
    time.sleep(3)  # > roles_validity / permissions_validity (2000 ms)
    print('RESULT setupauth table=%s app_is_superuser=%s seconds=%.1f' % (table, su, time.time() - t0))
elif cmd == 'guardcheck':
    table, n = sys.argv[2], int(sys.argv[3])
    cl, s = connect()
    ins = s.prepare('INSERT INTO probe.%s (k, v) VALUES (?, ?)' % table)
    try:
        s.execute(ins, (1, set(range(n)))); r = 'accepted'
    except Exception as e:
        r = 'rejected ' + err(e)
    cl.shutdown()
    print('RESULT guardcheck table=%s user=%s items=%d outcome=%s' % (table, os.environ.get('S4_USER', '-'), n, r))
else:
    raise SystemExit('bad command')
