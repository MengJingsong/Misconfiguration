#!/usr/bin/env python3
"""Cluster-tier client (B3c-B3e, as amended 2026-10-26) of MAXIMUM_MAXIMUM_NODE_CONNECTIONS-fromOptions-maximumNodeConnections--autonomous.

  probe.py setup                    CREATE KEYSPACE k (SimpleStrategy RF 1); for each table spec below: CREATE TABLE k.t_<s>
                                    (pk int PRIMARY KEY, v vector<float,8>) and CREATE CUSTOM INDEX idx_<s> ON k.t_<s>(v) USING
                                    'StorageAttachedIndex' WITH OPTIONS = {...}; prints accepted/rejected (with the server message)
                                    per index and the options read back from system_schema.indexes
  probe.py load <table> <rows> <conc>  prepared INSERT (pk, v); v = 8 floats random.Random(42).uniform(-1, 1), scaled to unit length;
                                    the same rows for every table (re-seeded per call)
  probe.py count <table>            SELECT count(*) (fetch 5000)
Table specs: 16 (M 16), 128 (M 128), 512 (M 512), 16b400 (M 16, construction_beam_width 400), 513 (M 513: the rejected attempt).
Each call prints one line starting RESULT. Bundled driver from CASSANDRA_HOME/lib (subfolder of the zip). Protocol 5,
DCAwareRoundRobinPolicy, token and schema metadata off, heartbeat off, request timeout 120 s, reconnect on connect failure."""
import glob, logging, math, os, random, sys, time

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

SPECS = [('16', {'maximum_node_connections': '16'}),
         ('128', {'maximum_node_connections': '128'}),
         ('512', {'maximum_node_connections': '512'}),
         ('16b400', {'maximum_node_connections': '16', 'construction_beam_width': '400'}),
         ('513', {'maximum_node_connections': '513'})]
DIM = 8


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


def vectors(rows):
    rnd = random.Random(42)
    out = []
    for _ in range(rows):
        v = [rnd.uniform(-1.0, 1.0) for _ in range(DIM)]
        n = math.sqrt(sum(x * x for x in v))
        out.append([x / n for x in v])
    return out


cmd = sys.argv[1]
if cmd == 'setup':
    cl, s = connect(30)
    s.execute("CREATE KEYSPACE IF NOT EXISTS k WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    parts = []
    for suf, opts in SPECS:
        s.execute("CREATE TABLE IF NOT EXISTS k.t_%s (pk int PRIMARY KEY, v vector<float,8>)" % suf)
        o = ', '.join("'%s':'%s'" % kv for kv in opts.items())
        q = "CREATE CUSTOM INDEX idx_%s ON k.t_%s(v) USING 'StorageAttachedIndex' WITH OPTIONS = {%s}" % (suf, suf, o)
        try:
            s.execute(q, timeout=120)
            parts.append('idx_%s=accepted' % suf)
        except Exception as e:
            parts.append('idx_%s=rejected[%s: %s]' % (suf, type(e).__name__, str(e).replace('\n', ' ')))
    idx = sorted((r[0], r[1], dict(r[2])) for r in
                 s.execute("SELECT table_name, index_name, options FROM system_schema.indexes WHERE keyspace_name='k'"))
    print('RESULT setup %s | schema_indexes=%s' % (' '.join(parts), idx))
    cl.shutdown()
elif cmd == 'load':
    table, rows, conc = sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    vs = vectors(rows)
    cs = sum(sum(v) for v in vs)
    cl, s = connect()
    ins = s.prepare('INSERT INTO k.%s (pk, v) VALUES (?, ?)' % table)
    t0 = time.time()
    done = fail = 0
    first = None
    args = [(i, vs[i]) for i in range(rows)]
    for ok, res in execute_concurrent_with_args(s, ins, args, concurrency=conc, raise_on_first_error=False):
        if ok:
            done += 1
        else:
            fail += 1
            first = first or repr(res)[:200]
    print('RESULT load table=%s rows=%d ok=%d failed=%d seconds=%.1f vector_sum=%.6f first_error=%s'
          % (table, rows, done, fail, time.time() - t0, cs, first))
    cl.shutdown()
elif cmd == 'count':
    table = sys.argv[2]
    cl, s = connect()
    n = s.execute(SimpleStatement('SELECT count(*) FROM k.%s' % table, fetch_size=5000), timeout=120).one()[0]
    print('RESULT count table=%s rows=%d' % (table, n))
    cl.shutdown()
else:
    raise SystemExit('RESULT unknown-command %s' % cmd)
