#!/usr/bin/env python3
"""Cluster-tier client (B3c, amended 2026-10-25) of prepared_statements_cache_size-applySimpleConfig-preparedStatementsCacheSizeInMiB--autonomous.
Driver bundled in $CASSANDRA_HOME/lib (cassandra-driver-internal-only-*.zip), protocol 5, one node 127.0.0.1,
DCAwareRoundRobinPolicy(local_dc='datacenter1'), token_metadata_enabled=False, NO session keyspace (one cache entry per PREPARE).
usage: prep.py schema                      create ks (SimpleStrategy RF 1) and ks.tbl (k int PRIMARY KEY, c0 text ... c49 text)
       prep.py load <from> <to>            PREPARE statements i = from .. to-1 (distinct texts), sequentially
       prep.py reprep <from> <to> <times>  PREPARE statements i = from .. to-1 again, <times> rounds
Prints one line starting RESULT."""
import glob, logging, os, sys, time

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
logging.getLogger('cassandra').setLevel(logging.ERROR)
from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402
from cassandra.policies import DCAwareRoundRobinPolicy  # noqa: E402

COLS = ', '.join('c%d' % c for c in range(50))


def q(i):
    return "SELECT %s FROM ks.tbl WHERE k = ? AND c0 = '%d' ALLOW FILTERING" % (COLS, i)


prof = ExecutionProfile(request_timeout=60, consistency_level=ConsistencyLevel.ONE,
                        load_balancing_policy=DCAwareRoundRobinPolicy(local_dc='datacenter1'))
cl = Cluster(['127.0.0.1'], protocol_version=5, token_metadata_enabled=False, execution_profiles={EXEC_PROFILE_DEFAULT: prof})
ses = cl.connect()   # no keyspace
cmd = sys.argv[1]
t0 = time.time()
if cmd == 'schema':
    ses.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
    ses.execute('CREATE TABLE IF NOT EXISTS ks.tbl (k int PRIMARY KEY, ' + ', '.join('c%d text' % c for c in range(50)) + ')')
    print('RESULT schema ok release=%s protocol=%d query0_chars=%d' % (ses.execute('SELECT release_version FROM system.local').one()[0],
                                                                       cl.protocol_version, len(q(0))))
elif cmd in ('load', 'reprep'):
    a, b = int(sys.argv[2]), int(sys.argv[3])
    rounds = int(sys.argv[4]) if cmd == 'reprep' else 1
    done = err = 0; first = None
    for _ in range(rounds):
        for i in range(a, b):
            try:
                ses.prepare(q(i)); done += 1
            except Exception as e:
                err += 1; first = first or repr(e)[:200]
    print('RESULT %s from=%d to=%d rounds=%d prepared=%d errors=%d seconds=%.1f first_error=%s'
          % (cmd, a, b, rounds, done, err, time.time() - t0, first))
cl.shutdown()
