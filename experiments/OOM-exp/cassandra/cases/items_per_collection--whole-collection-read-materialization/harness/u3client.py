#!/usr/bin/env python3
"""U3 client (phase 2 stage 2). Bundled Python driver from $CASSANDRA_HOME/lib, as the stage-4 s4.py.

  setup                               keyspace u3 (RF 1); tables s1m s2m s4m s8m sz (set<int>), b1m (blob), r1m (k, i clustering)
  loadset <table> <M> <chunk> <P>     appends v = v + {chunk distinct ints} for k = 0..P-1 until M items each
  loadblob <table> <bytes> <P>        one INSERT of a blob of <bytes> bytes for k = 0..P-1
  loadrows <table> <M> <P>            M clustering rows per k, UNLOGGED BATCHes of 1000, 32 in flight
  readers <table> <mode> <c> <seconds> <outfile>
        forks c processes, each with its own Cluster; process i loops until the deadline:
        SELECT ... WHERE k = (i + n) mod 8; one line per read: proc k t_start t_end outcome count bytes errtype
        modes: set (SELECT v; SetType.deserialize_safe patched to count/len), blob (SELECT b), rows (SELECT i, fetch_size 5000, all pages)
        On an error the process retries at once (no backoff); on connection loss it exits.
"""
import glob, logging, os, sys, time

CASS = os.environ['CASSANDRA_HOME']
LIB = os.path.join(CASS, 'lib')
P_READ = 8


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
from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT, NoHostAvailable  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402
from cassandra import cqltypes  # noqa: E402
from cassandra.query import tuple_factory, BatchStatement, BatchType  # noqa: E402
from cassandra.policies import DCAwareRoundRobinPolicy  # noqa: E402
from cassandra.connection import ConnectionShutdown, ConnectionException  # noqa: E402


def _setlen(cls, byts, protocol_version):
    return ('SETLEN', int.from_bytes(byts[:4], 'big', signed=True), len(byts))


def connect(timeout):
    prof = ExecutionProfile(request_timeout=timeout, consistency_level=ConsistencyLevel.ONE,
                            load_balancing_policy=DCAwareRoundRobinPolicy(local_dc='datacenter1'),
                            row_factory=tuple_factory)
    cl = Cluster(['127.0.0.1'], protocol_version=5, token_metadata_enabled=False, idle_heartbeat_interval=0,
                 execution_profiles={EXEC_PROFILE_DEFAULT: prof})
    return cl, cl.connect()


def err(e):
    return (type(e).__name__ + ': ' + str(e)).replace('\n', ' ')[:300]


def reader(i, table, mode, deadline, outfile):
    out = open(outfile + '.%03d' % i, 'w', buffering=1)
    try:
        cl, s = connect(60)
    except Exception as e:
        out.write('%d -1 %.3f %.3f connect_fail -1 -1 %s\n' % (i, time.time(), time.time(), type(e).__name__))
        return
    cqltypes.SetType.deserialize_safe = classmethod(_setlen)
    if mode == 'set':
        q = s.prepare('SELECT v FROM u3.%s WHERE k = ?' % table)
    elif mode == 'blob':
        q = s.prepare('SELECT b FROM u3.%s WHERE k = ?' % table)
    else:
        q = s.prepare('SELECT i FROM u3.%s WHERE k = ?' % table)
        q.fetch_size = 5000
    n = 0
    while time.time() < deadline:
        k = (i + n) % P_READ
        n += 1
        t1 = time.time()
        try:
            rs = s.execute(q, (k,))
            if mode == 'set':
                row = rs.one(); v = None if row is None else row[0]
                cnt, nb = (v[1], v[2]) if v else (0, 0)
            elif mode == 'blob':
                row = rs.one(); v = None if row is None else row[0]
                cnt, nb = (1, len(v)) if v is not None else (0, 0)
            else:
                cnt = 0
                for _ in rs:
                    cnt += 1
                nb = cnt * 4
            out.write('%d %d %.3f %.3f ok %d %d -\n' % (i, k, t1, time.time(), cnt, nb))
        except (ConnectionShutdown, ConnectionException, NoHostAvailable) as e:
            out.write('%d %d %.3f %.3f connlost -1 -1 %s\n' % (i, k, t1, time.time(), type(e).__name__))
            break
        except Exception as e:
            out.write('%d %d %.3f %.3f error -1 -1 %s\n' % (i, k, t1, time.time(), type(e).__name__))
            if 'NoHostAvailable' in err(e) or 'shutdown' in err(e).lower():
                break
    out.close()
    try:
        cl.shutdown()
    except Exception:
        pass


cmd = sys.argv[1]
t0 = time.time()
if cmd == 'setup':
    cl, s = connect(600)
    s.execute("CREATE KEYSPACE IF NOT EXISTS u3 WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    for t in ('s1m', 's2m', 's4m', 's8m', 'sz'):
        s.execute('CREATE TABLE IF NOT EXISTS u3.%s (k int PRIMARY KEY, v set<int>)' % t)
    s.execute('CREATE TABLE IF NOT EXISTS u3.b1m (k int PRIMARY KEY, b blob)')
    s.execute('CREATE TABLE IF NOT EXISTS u3.bz (k int PRIMARY KEY, b blob)')
    s.execute('CREATE TABLE IF NOT EXISTS u3.r1m (k int, i int, PRIMARY KEY (k, i))')
    s.execute('CREATE TABLE IF NOT EXISTS u3.rz (k int, i int, PRIMARY KEY (k, i))')
    rel = s.execute('SELECT release_version FROM system.local').one()[0]
    cl.shutdown()
    print('RESULT setup release=%s seconds=%.1f' % (rel, time.time() - t0))
elif cmd == 'loadset':
    table, M, chunk, P = sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
    cl, s = connect(600)
    add = s.prepare('UPDATE u3.%s SET v = v + ? WHERE k = ?' % table)
    acc = rej = 0; first = None
    for k in range(P):
        for j in range(M // chunk):
            try:
                s.execute(add, (set(range(j * chunk, (j + 1) * chunk)), k)); acc += 1
            except Exception as e:
                rej += 1; first = first or err(e)
    cl.shutdown()
    print('RESULT loadset table=%s M=%d chunk=%d P=%d accepted=%d rejected=%d seconds=%.1f first=%s'
          % (table, M, chunk, P, acc, rej, time.time() - t0, first))
elif cmd == 'loadblob':
    table, nbytes, P = sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    cl, s = connect(600)
    ins = s.prepare('INSERT INTO u3.%s (k, b) VALUES (?, ?)' % table)
    acc = rej = 0; first = None
    for k in range(P):
        try:
            s.execute(ins, (k, bytes(nbytes))); acc += 1
        except Exception as e:
            rej += 1; first = first or err(e)
    cl.shutdown()
    print('RESULT loadblob table=%s bytes=%d P=%d accepted=%d rejected=%d seconds=%.1f first=%s'
          % (table, nbytes, P, acc, rej, time.time() - t0, first))
elif cmd == 'loadrows':
    from cassandra.concurrent import execute_concurrent
    table, M, P = sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    cl, s = connect(600)
    ins = s.prepare('INSERT INTO u3.%s (k, i) VALUES (?, ?)' % table)

    def batches():
        for k in range(P):
            for b in range(0, M, 1000):
                bs = BatchStatement(batch_type=BatchType.UNLOGGED)
                for i in range(b, min(M, b + 1000)):
                    bs.add(ins, (k, i))
                yield (bs, ())
    res = execute_concurrent(s, batches(), concurrency=32, raise_on_first_error=False)
    acc = sum(1 for ok, _ in res if ok); rej = sum(1 for ok, _ in res if not ok)
    first = next((err(r) for ok, r in res if not ok), None)
    cl.shutdown()
    print('RESULT loadrows table=%s M=%d P=%d batches_ok=%d batches_failed=%d seconds=%.1f first=%s'
          % (table, M, P, acc, rej, time.time() - t0, first))
elif cmd == 'readers':
    table, mode, c, secs, outfile = sys.argv[2], sys.argv[3], int(sys.argv[4]), float(sys.argv[5]), sys.argv[6]
    deadline = time.time() + secs
    pids = []
    for i in range(c):
        pid = os.fork()
        if pid == 0:
            try:
                reader(i, table, mode, deadline, outfile)
            finally:
                os._exit(0)
        pids.append(pid)
    for p in pids:
        os.waitpid(p, 0)
    print('RESULT readers table=%s mode=%s c=%d seconds=%.0f wall=%.1f' % (table, mode, c, secs, time.time() - t0))
else:
    raise SystemExit('bad command')
