#!/usr/bin/env python3
"""Cluster-tier client (B3c, as amended 2026-10-26) of
prepared_statements_cache_size-getSizeOfPreparedStatementForCache-pstmntSize--autonomous.

Workload as filed: keyspace probe, table probe.wide (k int, c int, v0..v19 text, PRIMARY KEY (k, c)),
statement i = "SELECT * FROM probe.wide WHERE k = ? AND c = <i>", no session keyspace (one cache id per statement),
system_views.cql_metrics sampled every 1,000 prepares and at the end, CSV columns i,t,count,evicted.
Amended: bundled driver imported from inside the zip; DCAwareRoundRobinPolicy, token_metadata_enabled=False,
idle_heartbeat_interval=0; a failed prepare is retried up to 5 times on a new session; range of i given on the command line.

usage: prep.py schema
       prep.py load <from> <to> <outcsv>     prepare i = from .. to (inclusive), sample every 1000 (i % 1000 == 0) and at i == to
       prep.py trigger <read|clear>          run the B3d instrument query
       prep.py metrics                       print one cql_metrics snapshot
Prints one line starting RESULT."""
import csv, glob, logging, os, sys, time

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
from cassandra import ConsistencyLevel  # noqa: E402
from cassandra.policies import DCAwareRoundRobinPolicy  # noqa: E402


def connect():
    prof = ExecutionProfile(request_timeout=60, consistency_level=ConsistencyLevel.ONE,
                            load_balancing_policy=DCAwareRoundRobinPolicy(local_dc='datacenter1'))
    cl = Cluster(['127.0.0.1'], protocol_version=5, token_metadata_enabled=False, idle_heartbeat_interval=0,
                 execution_profiles={EXEC_PROFILE_DEFAULT: prof})
    return cl, cl.connect()          # no keyspace -> one cache id per statement


cl, s = connect()


def reconnect():
    global cl, s
    try:
        cl.shutdown()
    except Exception:
        pass
    cl, s = connect()


def metrics():
    return {r.name: r.value for r in s.execute("SELECT name, value FROM system_views.cql_metrics")}


cmd = sys.argv[1]
t0 = time.time()
if cmd == 'schema':
    s.execute("CREATE KEYSPACE IF NOT EXISTS probe WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    cols = ", ".join("v%d text" % i for i in range(20))
    s.execute("CREATE TABLE IF NOT EXISTS probe.wide (k int, c int, %s, PRIMARY KEY (k, c))" % cols)
    print('RESULT schema ok release=%s protocol=%d' % (s.execute('SELECT release_version FROM system.local').one()[0],
                                                        cl.protocol_version))
elif cmd == 'load':
    a, b, outp = int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    f = open(outp, 'a', newline='')
    out = csv.writer(f)
    if f.tell() == 0:
        out.writerow(['i', 't', 'count', 'evicted'])
    done = retries = failed = 0
    first = None
    for i in range(a, b + 1):
        q = "SELECT * FROM probe.wide WHERE k = ? AND c = %d" % i
        for attempt in range(6):
            try:
                s.prepare(q)
                done += 1
                break
            except Exception as e:
                first = first or ('i=%d %r' % (i, e))[:200]
                if attempt == 5:
                    failed += 1
                    break
                retries += 1
                time.sleep(1)
                reconnect()
        if i % 1000 == 0 or i == b:
            m = metrics()
            out.writerow([i, '%.3f' % time.time(), int(m['prepared_statements_count']), int(m['prepared_statements_evicted'])])
            f.flush()
    f.close()
    print('RESULT load from=%d to=%d prepared=%d retries=%d failed=%d seconds=%.1f first_error=%s'
          % (a, b, done, retries, failed, time.time() - t0, first))
elif cmd == 'trigger':
    name = sys.argv[2]
    assert name in ('read', 'clear')
    rows = list(s.execute("SELECT key FROM system.local WHERE key = 'stage4-pscache-%s'" % name))
    print('RESULT trigger %s rows=%d t=%d' % (name, len(rows), int(time.time() * 1000)))
elif cmd == 'metrics':
    m = metrics()
    print('RESULT metrics count=%d evicted=%d' % (int(m['prepared_statements_count']), int(m['prepared_statements_evicted'])))
cl.shutdown()
