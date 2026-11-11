#!/usr/bin/env python3
"""Cluster-tier client (B3c-B3e, as amended 2026-10-26) of sai_vector_search_max_top_k-execute-pageSize--autonomous.

  probe.py setup               CREATE KEYSPACE v (SimpleStrategy RF 1); CREATE TABLE v.vt (k int PRIMARY KEY, e vector<float,16>, p blob)
                               WITH compression = {'enabled': false}; CREATE INDEX ON v.vt(e) USING 'sai'
  probe.py load <rows> <conc>  prepared INSERT (k, e, p): e = 16 floats from random.Random(34).uniform(0.1, 1.0), p = os.urandom(8192)
  probe.py count               SELECT count(*) FROM v.vt (fetch 5000)
  probe.py q <L>               SELECT k, p FROM v.vt ORDER BY e ANN OF [0.5 x16] LIMIT <L>, CL ONE, fetch_size 10; first page only
Each call prints one line starting RESULT. Bundled driver from CASSANDRA_HOME/lib (the filed PYTHONPATH form, a subfolder of the zip).
Driver settings: protocol 5, DCAwareRoundRobinPolicy, token and schema metadata off, heartbeat off, request timeout 120 s."""
import glob, logging, os, random, sys, time

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

QV = '[' + ', '.join(['0.5'] * 16) + ']'


def ms():
    return int(time.time() * 1000)


def connect(tries=10):
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
    cl, s = connect(30)
    s.execute("CREATE KEYSPACE IF NOT EXISTS v WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    s.execute("CREATE TABLE IF NOT EXISTS v.vt (k int PRIMARY KEY, e vector<float,16>, p blob) WITH compression = {'enabled': false}")
    s.execute("CREATE INDEX IF NOT EXISTS ON v.vt(e) USING 'sai'")
    comp = s.execute("SELECT compression FROM system_schema.tables WHERE keyspace_name='v' AND table_name='vt'").one()[0]
    idx = [tuple(r) for r in s.execute("SELECT index_name, kind, options FROM system_schema.indexes WHERE keyspace_name='v' AND table_name='vt'")]
    print('RESULT setup compression=%s indexes=%s' % (dict(comp), idx))
    cl.shutdown()
elif cmd == 'load':
    rows, conc = int(sys.argv[2]), int(sys.argv[3])
    rnd = random.Random(34)
    cl, s = connect()
    ins = s.prepare('INSERT INTO v.vt (k, e, p) VALUES (?, ?, ?)')
    t0 = time.time()
    done = fail = 0
    first = None
    step = 5000
    for base in range(0, rows, step):
        args = [(k, [rnd.uniform(0.1, 1.0) for _ in range(16)], os.urandom(8192)) for k in range(base, min(rows, base + step))]
        for ok, res in execute_concurrent_with_args(s, ins, args, concurrency=conc, raise_on_first_error=False):
            if ok:
                done += 1
            else:
                fail += 1
                first = first or repr(res)[:200]
    print('RESULT load rows=%d ok=%d failed=%d seconds=%.1f first_error=%s' % (rows, done, fail, time.time() - t0, first))
    cl.shutdown()
elif cmd == 'count':
    cl, s = connect()
    n = s.execute(SimpleStatement('SELECT count(*) FROM v.vt', fetch_size=5000)).one()[0]
    print('RESULT count=%d' % n)
    cl.shutdown()
elif cmd == 'q':
    L = int(sys.argv[2])
    q = 'SELECT k, p FROM v.vt ORDER BY e ANN OF %s LIMIT %d' % (QV, L)
    cl, s = connect()
    st = SimpleStatement(q, fetch_size=10)
    t0 = ms()
    try:
        rs = s.execute(st)
        rows = len(rs.current_rows)
        more = rs.has_more_pages
        warns = rs.response_future.warnings or []
        vbytes = sum(len(r.p) for r in rs.current_rows)
        distinct = len(set(r.k for r in rs.current_rows))
        out, err = 'ok', ''
    except Exception as e:
        rows, more, warns, vbytes, distinct = -1, 'na', [], 0, 0
        out = 'error'
        err = '%s: %s' % (type(e).__name__, str(e).replace('\n', ' ')[:300])
    t1 = ms()
    tw = [w for w in warns if w.startswith('Top-K queries do not support paging')]
    print('RESULT q L=%d fetch=10 outcome=%s rows=%d distinct_k=%d has_more=%s value_bytes=%d topk_warnings=%d warnings=%d '
          'q_start_ms=%d q_end_ms=%d err=[%s] warntext=%s' % (L, out, rows, distinct, more, vbytes, len(tw), len(warns), t0, t1, err,
                                                              [w.replace('\n', ' ') for w in warns]))
    cl.shutdown()
else:
    raise SystemExit('bad command')
