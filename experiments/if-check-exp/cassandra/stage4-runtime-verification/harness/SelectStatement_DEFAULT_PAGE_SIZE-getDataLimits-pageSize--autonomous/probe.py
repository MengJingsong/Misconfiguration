#!/usr/bin/env python3
"""Cluster-tier client (B3c-B3e, as amended 2026-10-26) of SelectStatement_DEFAULT_PAGE_SIZE-getDataLimits-pageSize--autonomous.

  probe.py setup                   keyspace g (SimpleStrategy RF 1), table g.t (k int, g int, c int, v blob, PRIMARY KEY (k,g,c))
                                   WITH compression = {'enabled': false}; prints the compression read-back
  probe.py load <groups> <per> <conc>
                                   prepared INSERT (k=0, g, c, v=os.urandom(4096)) for g < groups, c < per; concurrency <conc>
  probe.py count                   SELECT count(*) FROM g.t WHERE k=0 (fetch 5000)
  probe.py q <qg|qa> <off|fetch>   Qg: SELECT k, g, max(v) FROM g.t WHERE k=0 GROUP BY k, g
                                   Qa: SELECT max(v) FROM g.t WHERE k=0
                                   paging off: session.default_fetch_size = None and SimpleStatement(fetch_size=None);
                                   otherwise fetch_size=<fetch>; all pages are read
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
from cassandra import ConsistencyLevel  # noqa: E402
from cassandra.query import SimpleStatement  # noqa: E402
from cassandra.policies import DCAwareRoundRobinPolicy  # noqa: E402
from cassandra.concurrent import execute_concurrent_with_args  # noqa: E402

QG = 'SELECT k, g, max(v) FROM g.t WHERE k=0 GROUP BY k, g'
QA = 'SELECT max(v) FROM g.t WHERE k=0'


def ms():
    return int(time.time() * 1000)


def connect(tries=1):
    last = None
    for i in range(tries):
        prof = ExecutionProfile(request_timeout=120, consistency_level=ConsistencyLevel.ONE,
                                load_balancing_policy=DCAwareRoundRobinPolicy(local_dc='datacenter1'))
        cl = Cluster(['127.0.0.1'], protocol_version=5, token_metadata_enabled=False, schema_metadata_enabled=False,
                     idle_heartbeat_interval=0, connect_timeout=30, execution_profiles={EXEC_PROFILE_DEFAULT: prof})
        try:
            return cl, cl.connect()
        except Exception as e:  # e.g. ENOBUFS on this host
            last = e
            try:
                cl.shutdown()
            except Exception:
                pass
            time.sleep(2)
    raise SystemExit('RESULT connect-failed err=%r' % (last,))


cmd = sys.argv[1]
if cmd == 'setup':
    cl, s = connect(tries=10)
    s.execute("CREATE KEYSPACE IF NOT EXISTS g WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    s.execute("CREATE TABLE IF NOT EXISTS g.t (k int, g int, c int, v blob, PRIMARY KEY (k, g, c)) WITH compression = {'enabled': false}")
    comp = s.execute("SELECT compression FROM system_schema.tables WHERE keyspace_name='g' AND table_name='t'").one()[0]
    rep = s.execute("SELECT replication FROM system_schema.keyspaces WHERE keyspace_name='g'").one()[0]
    print('RESULT setup compression=%s replication=%s' % (dict(comp), dict(rep)))
    cl.shutdown()
elif cmd == 'load':
    groups, per, conc = int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
    cl, s = connect(tries=10)
    ins = s.prepare('INSERT INTO g.t (k, g, c, v) VALUES (0, ?, ?, ?)')
    t0 = time.time()
    done = fail = 0
    first = None
    for g in range(groups):
        args = [(g, c, os.urandom(4096)) for c in range(per)]
        for ok, res in execute_concurrent_with_args(s, ins, args, concurrency=conc, raise_on_first_error=False):
            if ok:
                done += 1
            else:
                fail += 1
                first = first or repr(res)[:200]
    print('RESULT load rows=%d ok=%d failed=%d seconds=%.1f first_error=%s' % (groups * per, done, fail, time.time() - t0, first))
    cl.shutdown()
elif cmd == 'count':
    cl, s = connect(tries=10)
    n = s.execute(SimpleStatement('SELECT count(*) FROM g.t WHERE k=0', fetch_size=5000)).one()[0]
    print('RESULT count=%d' % n)
    cl.shutdown()
elif cmd == 'q':
    which, fetch = sys.argv[2], sys.argv[3]
    q = QG if which == 'qg' else QA
    cl, s = connect(tries=10)
    if fetch == 'off':
        s.default_fetch_size = None
        st = SimpleStatement(q, fetch_size=None)
    else:
        st = SimpleStatement(q, fetch_size=int(fetch))
    t0 = ms()
    pages = rows = vbytes = 0
    try:
        rs = s.execute(st)
        while True:
            pages += 1
            rows += len(rs.current_rows)
            vbytes += sum(len(r[-1]) for r in rs.current_rows if r[-1] is not None)
            if not rs.has_more_pages:
                break
            rs.fetch_next_page()
        warns = rs.response_future.warnings or []
        out, err = 'ok', ''
    except Exception as e:
        warns = []
        out = 'error'
        err = '%s: %s' % (type(e).__name__, str(e).replace('\n', ' ')[:300])
    t1 = ms()
    print('RESULT q query=%s fetch=%s outcome=%s rows=%d pages=%d value_bytes=%d warnings=%d q_start_ms=%d q_end_ms=%d err=[%s]'
          % (which, fetch, out, rows, pages, vbytes, len(warns), t0, t1, err))
    cl.shutdown()
else:
    raise SystemExit('bad command')
