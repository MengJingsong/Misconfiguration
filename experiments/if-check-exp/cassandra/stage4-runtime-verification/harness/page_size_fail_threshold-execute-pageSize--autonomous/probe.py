#!/usr/bin/env python3
"""Cluster-tier client (B3c-B3e, as amended 2026-10-26) of page_size_fail_threshold-execute-pageSize--autonomous.

  probe.py setup                  as cassandra/cassandra (retries until the default superuser exists): CREATE ROLE app (LOGIN, not
                                  superuser), keyspace p (SimpleStrategy RF 1), table p.wide (k int, c int, v blob, PRIMARY KEY (k, c))
                                  WITH compression = {'enabled': false}, GRANT SELECT ON KEYSPACE p TO app; prints app's is_superuser
  probe.py load <rows> <conc>     as cassandra: prepared INSERT (k=0, c=i, v=os.urandom(2048)) for i in 0..rows-1, concurrency <conc>
  probe.py count                  as cassandra: SELECT count(*) FROM p.wide WHERE k = 0
  probe.py q <fetch|off> <limit|none>
                                  as app: SELECT k, c, v FROM p.wide WHERE k = 0 [LIMIT n]; fetch_size=<fetch>, or paging off
                                  (session.default_fetch_size = None and SimpleStatement(fetch_size=None)); reads only the first page
Each call prints one line starting RESULT. Bundled driver from CASSANDRA_HOME/lib (the filed PYTHONPATH form, a subfolder of the zip).
Driver settings: protocol 5, DCAwareRoundRobinPolicy, token and schema metadata off, heartbeat off, request timeout 120 s."""
import glob, logging, os, sys, time

LIB = os.path.join(os.environ['CASSANDRA_HOME'], 'lib')
z = glob.glob(os.path.join(LIB, 'cassandra-driver-internal-only-*.zip'))[0]
ver = os.path.splitext(os.path.basename(z))[0][len('cassandra-driver-internal-only-'):]
sys.path.insert(0, os.path.join(z, 'cassandra-driver-' + ver))
logging.basicConfig(level=logging.ERROR)
logging.getLogger('cassandra').setLevel(logging.CRITICAL)
from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT  # noqa: E402
from cassandra.auth import PlainTextAuthProvider  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402
from cassandra.query import SimpleStatement  # noqa: E402
from cassandra.policies import DCAwareRoundRobinPolicy  # noqa: E402
from cassandra.concurrent import execute_concurrent_with_args  # noqa: E402


def ms():
    return int(time.time() * 1000)


def connect(user, pw, tries=1):
    last = None
    for i in range(tries):
        prof = ExecutionProfile(request_timeout=120, consistency_level=ConsistencyLevel.ONE,
                                load_balancing_policy=DCAwareRoundRobinPolicy(local_dc='datacenter1'))
        cl = Cluster(['127.0.0.1'], protocol_version=5, token_metadata_enabled=False, schema_metadata_enabled=False,
                     idle_heartbeat_interval=0, connect_timeout=30,
                     auth_provider=PlainTextAuthProvider(username=user, password=pw),
                     execution_profiles={EXEC_PROFILE_DEFAULT: prof})
        try:
            return cl, cl.connect()
        except Exception as e:  # e.g. the default superuser not yet created, or ENOBUFS on this host
            last = e
            try:
                cl.shutdown()
            except Exception:
                pass
            time.sleep(2)
    raise SystemExit('RESULT connect-failed user=%s err=%r' % (user, last))


cmd = sys.argv[1]
if cmd == 'setup':
    cl, s = connect('cassandra', 'cassandra', tries=60)
    s.execute("CREATE ROLE IF NOT EXISTS app WITH PASSWORD = 'app' AND LOGIN = true")
    s.execute("CREATE KEYSPACE IF NOT EXISTS p WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    s.execute("CREATE TABLE IF NOT EXISTS p.wide (k int, c int, v blob, PRIMARY KEY (k, c)) WITH compression = {'enabled': false}")
    s.execute("GRANT SELECT ON KEYSPACE p TO app")
    su = s.execute("SELECT is_superuser, can_login FROM system_auth.roles WHERE role = 'app'").one()
    comp = s.execute("SELECT compression FROM system_schema.tables WHERE keyspace_name='p' AND table_name='wide'").one()[0]
    perms = [tuple(r) for r in s.execute("LIST ALL PERMISSIONS OF app")]
    print('RESULT setup app_is_superuser=%s app_can_login=%s compression=%s perms=%s' % (su[0], su[1], dict(comp), perms))
    cl.shutdown()
elif cmd == 'load':
    rows, conc = int(sys.argv[2]), int(sys.argv[3])
    cl, s = connect('cassandra', 'cassandra', tries=10)
    ins = s.prepare('INSERT INTO p.wide (k, c, v) VALUES (0, ?, ?)')
    t0 = time.time()
    done = fail = 0
    first = None
    step = 10000
    for base in range(0, rows, step):
        args = [(c, os.urandom(2048)) for c in range(base, min(rows, base + step))]
        for ok, res in execute_concurrent_with_args(s, ins, args, concurrency=conc, raise_on_first_error=False):
            if ok:
                done += 1
            else:
                fail += 1
                first = first or repr(res)[:200]
    print('RESULT load rows=%d ok=%d failed=%d seconds=%.1f first_error=%s' % (rows, done, fail, time.time() - t0, first))
    cl.shutdown()
elif cmd == 'count':
    cl, s = connect('cassandra', 'cassandra', tries=10)
    n = s.execute(SimpleStatement('SELECT count(*) FROM p.wide WHERE k = 0', fetch_size=5000)).one()[0]
    print('RESULT count=%d' % n)
    cl.shutdown()
elif cmd == 'q':
    fetch, limit = sys.argv[2], sys.argv[3]
    q = 'SELECT k, c, v FROM p.wide WHERE k = 0' + ('' if limit == 'none' else ' LIMIT %d' % int(limit))
    cl, s = connect('app', 'app', tries=10)
    if fetch == 'off':
        s.default_fetch_size = None
        st = SimpleStatement(q, fetch_size=None)
    else:
        st = SimpleStatement(q, fetch_size=int(fetch))
    t0 = ms()
    try:
        rs = s.execute(st)
        rows = len(rs.current_rows)
        more = rs.has_more_pages
        warns = rs.response_future.warnings or []
        vbytes = sum(len(r.v) for r in rs.current_rows)
        out = 'ok'
        err = ''
    except Exception as e:
        rows, more, warns, vbytes = -1, 'na', [], 0
        out = 'error'
        err = '%s: %s' % (type(e).__name__, str(e).replace('\n', ' ')[:300])
    t1 = ms()
    pw = sum(1 for w in warns if 'page size' in w and 'exceeds warning threshold' in w)
    print('RESULT q fetch=%s limit=%s outcome=%s rows=%d has_more=%s value_bytes=%d page_size_warnings=%d warnings=%d '
          'q_start_ms=%d q_end_ms=%d err=[%s]' % (fetch, limit, out, rows, more, vbytes, pw, len(warns), t0, t1, err))
    cl.shutdown()
else:
    raise SystemExit('bad command')
