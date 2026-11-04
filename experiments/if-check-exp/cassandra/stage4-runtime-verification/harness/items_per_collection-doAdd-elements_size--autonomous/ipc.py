#!/usr/bin/env python3
"""Cluster-tier client (B3c, as amended 2026-10-26) of items_per_collection-doAdd-elements_size--autonomous.

Workload as filed (B3c), split into one call per phase so the run script can sample and flush between phases:
  setup <table>                 as cassandra/cassandra: keyspace probe (RF 1), table probe.<table> (k int PRIMARY KEY, v set<int>)
                                WITH compression = {'enabled': false} (amendment B3c), role app (LOGIN, not superuser,
                                password 'app'), GRANT ALL ON KEYSPACE probe TO app; waits for the superuser to exist.
  phase i   <W> <table> [reps]  as app: reps (200) single INSERTs of W+1 items on keys 1000..1000+reps-1
  phase ii  <W> <table> [reps]  as app: reps appends v = v + {W new distinct ints} on key 1 (reps*W items in all)
  phase iii <W> <table> [reps]  as app: reps empty appends v = v + {} on key 2
  phase iv  <W> <table> [reps]  as cassandra: the same single INSERTs as phase i on keys 2000..2000+reps-1
  phase iiibseed <W> <table>    (re-run 2026-10-28, amendment B3c) as app: one append v = v + {0} on key 3 (the seed)
  phase iiib <W> <table> [reps] (re-run 2026-10-28, amendment B3c) as app: reps empty appends v = v + {} on key 3
  card <table> <k>              stored cardinality of key k (0 if the row or the set is absent)
  keys <table> <from> <n>       how many of keys from..from+n-1 exist
  bytes <dir>                   sum of file sizes under dir, skipping snapshots/ and backups/ (no connection)
Each call prints one line starting RESULT.
Amended: the bundled driver is imported from inside the zip; DCAwareRoundRobinPolicy, token_metadata_enabled=False,
idle_heartbeat_interval=0, PlainTextAuthProvider; a connection error (not a server rejection) is retried up to 5 times
on a new session (a retried set append is idempotent)."""
import glob, logging, os, sys, time

cmd = sys.argv[1]
if cmd == 'bytes':
    root, tot, n = sys.argv[2], 0, 0
    for d, subs, files in os.walk(root):
        subs[:] = [s for s in subs if s not in ('snapshots', 'backups')]
        for f in files:
            tot += os.path.getsize(os.path.join(d, f)); n += 1
    print('RESULT bytes dir=%s bytes=%d files=%d' % (root, tot, n))
    sys.exit(0)

CASS = os.environ['CASSANDRA_HOME']
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

logging.basicConfig(level=logging.ERROR)
logging.getLogger('cassandra').setLevel(logging.CRITICAL)
from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT  # noqa: E402
from cassandra import ConsistencyLevel, InvalidRequest, Unauthorized  # noqa: E402
from cassandra.auth import PlainTextAuthProvider  # noqa: E402
from cassandra.policies import DCAwareRoundRobinPolicy  # noqa: E402


class Conn:
    def __init__(self, user, pw):
        self.user, self.pw = user, pw
        self.cl = self.s = None
        self.connect()

    def connect(self):
        prof = ExecutionProfile(request_timeout=120, consistency_level=ConsistencyLevel.ONE,
                                load_balancing_policy=DCAwareRoundRobinPolicy(local_dc='datacenter1'))
        self.cl = Cluster(['127.0.0.1'], protocol_version=5, token_metadata_enabled=False, idle_heartbeat_interval=0,
                          auth_provider=PlainTextAuthProvider(self.user, self.pw),
                          execution_profiles={EXEC_PROFILE_DEFAULT: prof})
        self.s = self.cl.connect()

    def reconnect(self):
        try:
            self.cl.shutdown()
        except Exception:
            pass
        self.connect()

    def run(self, q, args=None):
        """returns (ok, rows_or_message, retries); a server rejection is (False, message)."""
        retries = 0
        while True:
            try:
                return True, self.s.execute(q, args), retries
            except (InvalidRequest, Unauthorized) as e:
                return False, str(e), retries
            except Exception as e:
                if retries == 5:
                    return False, 'CONN-ERROR ' + repr(e)[:200], retries
                retries += 1
                time.sleep(1)
                self.reconnect()

    def shutdown(self):
        self.cl.shutdown()


def card(c, table, k):
    ok, rs, _ = c.run('SELECT v FROM probe.%s WHERE k = %d' % (table, k))
    if not ok:
        return -1
    row = rs.one()
    return 0 if row is None or row.v is None else len(row.v)


t0 = time.time()
if cmd == 'setup':
    table = sys.argv[2]
    c = None
    for attempt in range(60):          # the default superuser appears after cassandra.superuser_setup_delay_ms (10 s)
        try:
            c = Conn('cassandra', 'cassandra')
            break
        except Exception:
            time.sleep(2)
    if c is None:
        print('RESULT setup FAILED no superuser login after 120 s'); sys.exit(1)
    for q in ("CREATE KEYSPACE IF NOT EXISTS probe WITH replication = {'class':'SimpleStrategy','replication_factor':1}",
              "CREATE TABLE IF NOT EXISTS probe.%s (k int PRIMARY KEY, v set<int>) WITH compression = {'enabled': false}" % table,
              "CREATE ROLE IF NOT EXISTS app WITH PASSWORD = 'app' AND LOGIN = true AND SUPERUSER = false",
              "GRANT ALL ON KEYSPACE probe TO app"):
        ok, r, _ = c.run(q)
        if not ok:
            print('RESULT setup FAILED %s -> %s' % (q, r)); sys.exit(1)
    su = c.run("SELECT is_superuser, can_login FROM system_auth.roles WHERE role = 'app'")[1].one()
    rel = c.run('SELECT release_version FROM system.local')[1].one()[0]
    c.shutdown()
    time.sleep(3)                      # > permissions_validity / roles_validity (2000 ms, conf/cassandra.yaml:300,327)
    a = Conn('app', 'app')
    me = a.run('SELECT count(*) FROM probe.%s' % table)
    a.shutdown()
    print('RESULT setup table=probe.%s app_is_superuser=%s app_can_login=%s app_select_ok=%s release=%s'
          % (table, su.is_superuser, su.can_login, me[0], rel))
elif cmd == 'phase':
    ph, W, table = sys.argv[2], int(sys.argv[3]), sys.argv[4]
    reps = int(sys.argv[5]) if len(sys.argv) > 5 else 200
    if ph == 'iiibseed':
        reps = 1
    user = ('cassandra', 'cassandra') if ph == 'iv' else ('app', 'app')
    c = Conn(*user)
    ins = c.s.prepare('INSERT INTO probe.%s (k, v) VALUES (?, ?)' % table)
    add = c.s.prepare('UPDATE probe.%s SET v = v + ? WHERE k = ?' % table)
    acc = rej = conn_err = retries = 0
    first = None
    for j in range(reps):
        if ph in ('i', 'iv'):
            base = 1000 if ph == 'i' else 2000
            ok, r, rt = c.run(ins, (base + j, set(range(0, W + 1))))
        elif ph == 'ii':
            ok, r, rt = c.run(add, (set(range(j * W, (j + 1) * W)), 1))
        elif ph == 'iii':
            ok, r, rt = c.run(add, (set(), 2))
        elif ph == 'iiibseed':
            ok, r, rt = c.run(add, ({0}, 3))
        elif ph == 'iiib':
            ok, r, rt = c.run(add, (set(), 3))
        else:
            raise SystemExit('bad phase')
        retries += rt
        if ok:
            acc += 1
        elif isinstance(r, str) and r.startswith('CONN-ERROR'):
            conn_err += 1
            first = first or r
        else:
            rej += 1
            first = first or r[:300]
    c.shutdown()
    print('RESULT phase=%s user=%s W=%d table=probe.%s reps=%d accepted=%d rejected=%d conn_errors=%d retries=%d seconds=%.1f first=%s'
          % (ph, user[0], W, table, reps, acc, rej, conn_err, retries, time.time() - t0, first))
elif cmd == 'card':
    table, k = sys.argv[2], int(sys.argv[3])
    c = Conn('cassandra', 'cassandra')
    n = card(c, table, k)
    c.shutdown()
    print('RESULT card table=probe.%s k=%d card=%d seconds=%.1f' % (table, k, n, time.time() - t0))
elif cmd == 'keys':
    table, a, n = sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    c = Conn('cassandra', 'cassandra')
    present = sum(1 for k in range(a, a + n) if c.run('SELECT k FROM probe.%s WHERE k = %d' % (table, k))[1].one() is not None)
    c.shutdown()
    print('RESULT keys table=probe.%s from=%d n=%d present=%d' % (table, a, n, present))
