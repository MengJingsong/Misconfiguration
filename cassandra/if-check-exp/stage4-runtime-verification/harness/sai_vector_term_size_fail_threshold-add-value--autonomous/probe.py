#!/usr/bin/env python3
"""Cluster-tier client (B3c-B3e, as amended 2026-10-26) of sai_vector_term_size_fail_threshold-add-value--autonomous.

  probe.py setup [auth]           CREATE KEYSPACE vt (SimpleStrategy RF 1), TABLE vt.t (k int PRIMARY KEY, v vector<float, 2048>)
                                  WITH compaction enabled false, INDEX t_v_idx USING 'sai' (euclidean). With 'auth': connects as
                                  cassandra/cassandra (retrying while the default superuser is created), then CREATE ROLE vt_writer
                                  (LOGIN, not superuser) and GRANT MODIFY, SELECT ON KEYSPACE vt.
  probe.py load <passes> <conc> [auth]  prepared INSERT, k = 0..9999 per pass (VTS_ROWS overrides 10000, shakedown only); v = 2048 x random.Random(42).uniform(0.1, 1.0), one
                                  generator across passes; with 'auth' as vt_writer
  probe.py ann [auth]             SELECT k FROM vt.t ORDER BY v ANN OF <random.Random(7) vector> LIMIT 10
  probe.py count [auth]           SELECT count(*) FROM vt.t
Each call prints one line starting RESULT. Bundled driver from CASSANDRA_HOME/lib (subfolder of the zip). Protocol 5,
DCAwareRoundRobinPolicy, token and schema metadata off, heartbeat off, request timeout 120 s, reconnect on connect failure."""
import glob, logging, os, random, sys, time

LIB = os.path.join(os.environ['CASSANDRA_HOME'], 'lib')
z = glob.glob(os.path.join(LIB, 'cassandra-driver-internal-only-*.zip'))[0]
ver = os.path.splitext(os.path.basename(z))[0][len('cassandra-driver-internal-only-'):]
sys.path.insert(0, os.path.join(z, 'cassandra-driver-' + ver))
logging.basicConfig(level=logging.ERROR)
logging.getLogger('cassandra').setLevel(logging.CRITICAL)
from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402
from cassandra.auth import PlainTextAuthProvider  # noqa: E402
from cassandra.query import SimpleStatement  # noqa: E402
from cassandra.policies import DCAwareRoundRobinPolicy  # noqa: E402
from cassandra.concurrent import execute_concurrent_with_args  # noqa: E402

ROWS, DIM = int(os.environ.get('VTS_ROWS', '10000')), 2048   # VTS_ROWS: shakedown only


def connect(user=None, tries=10):
    last = None
    for i in range(tries):
        prof = ExecutionProfile(request_timeout=120, consistency_level=ConsistencyLevel.ONE,
                                load_balancing_policy=DCAwareRoundRobinPolicy(local_dc='datacenter1'))
        auth = PlainTextAuthProvider(username=user, password=user) if user else None
        cl = Cluster(['127.0.0.1'], protocol_version=5, token_metadata_enabled=False, schema_metadata_enabled=False,
                     idle_heartbeat_interval=0, connect_timeout=30, auth_provider=auth,
                     execution_profiles={EXEC_PROFILE_DEFAULT: prof})
        try:
            return cl, cl.connect()
        except Exception as e:  # ENOBUFS on this host; superuser not created yet
            last = e
            try:
                cl.shutdown()
            except Exception:
                pass
            time.sleep(3)
    raise SystemExit('RESULT connect-failed user=%s err=%r' % (user, last))


args = sys.argv[1:]
auth = 'auth' in args
args = [a for a in args if a != 'auth']
cmd = args[0]
if cmd == 'setup':
    cl, s = connect('cassandra' if auth else None, 40)
    s.execute("CREATE KEYSPACE IF NOT EXISTS vt WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    s.execute("CREATE TABLE IF NOT EXISTS vt.t (k int PRIMARY KEY, v vector<float, 2048>) "
              "WITH compaction = {'class':'SizeTieredCompactionStrategy','enabled':'false'}")
    s.execute("CREATE INDEX IF NOT EXISTS t_v_idx ON vt.t(v) USING 'sai' WITH OPTIONS = {'similarity_function':'euclidean'}",
              timeout=120)
    extra = ''
    if auth:
        s.execute("CREATE ROLE IF NOT EXISTS vt_writer WITH PASSWORD = 'vt_writer' AND LOGIN = true AND SUPERUSER = false")
        s.execute("GRANT MODIFY ON KEYSPACE vt TO vt_writer")
        s.execute("GRANT SELECT ON KEYSPACE vt TO vt_writer")
        r = s.execute("SELECT role, is_superuser, can_login FROM system_auth.roles WHERE role = 'vt_writer'").one()
        perms = sorted(tuple(x) for x in s.execute("LIST ALL PERMISSIONS OF vt_writer"))
        extra = ' role=%s is_superuser=%s can_login=%s perms=%s' % (r[0], r[1], r[2], perms)
    idx = [tuple(x) for x in s.execute("SELECT index_name, kind, options FROM system_schema.indexes WHERE keyspace_name='vt'")]
    print('RESULT setup ok user=%s indexes=%s%s' % ('cassandra' if auth else 'anonymous', idx, extra))
    time.sleep(2)
    cl.shutdown()
elif cmd == 'load':
    passes, conc = int(args[1]), int(args[2])
    rnd = random.Random(42)
    cl, s = connect('vt_writer' if auth else None)
    ins = s.prepare('INSERT INTO vt.t (k, v) VALUES (?, ?)')
    for p in range(passes):
        vs = [[rnd.uniform(0.1, 1.0) for _ in range(DIM)] for _ in range(ROWS)]
        t0 = time.time()
        done = fail = 0
        first = None
        for ok, res in execute_concurrent_with_args(s, ins, [(k, vs[k]) for k in range(ROWS)], concurrency=conc,
                                                    raise_on_first_error=False):
            if ok:
                done += 1
            else:
                fail += 1
                first = first or str(res).replace('\n', ' ')[:300]
        print('RESULT load pass=%d rows=%d ok=%d failed=%d seconds=%.1f sum_first_vector=%.6f first_error=%s'
              % (p + 1, ROWS, done, fail, time.time() - t0, sum(vs[0]), first))
        sys.stdout.flush()
    cl.shutdown()
elif cmd == 'ann':
    rq = random.Random(7)
    q = [rq.uniform(0.1, 1.0) for _ in range(DIM)]
    cl, s = connect('vt_writer' if auth else None)
    try:
        st = s.prepare('SELECT k FROM vt.t ORDER BY v ANN OF ? LIMIT 10')
        rows = list(s.execute(st, (q,), timeout=120))
        print('RESULT ann rows=%d keys=%s' % (len(rows), sorted(r[0] for r in rows)))
    except Exception as e:
        print('RESULT ann error=%s' % str(e).replace('\n', ' ')[:300])
    cl.shutdown()
elif cmd == 'count':
    cl, s = connect('vt_writer' if auth else None)
    n = s.execute(SimpleStatement('SELECT count(*) FROM vt.t', fetch_size=5000), timeout=120).one()[0]
    print('RESULT count rows=%d' % n)
    cl.shutdown()
else:
    raise SystemExit('RESULT unknown-command %s' % cmd)
