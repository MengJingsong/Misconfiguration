#!/usr/bin/env python3
"""Cluster-tier client (B3c, as amended 2026-10-26) of batch_size_fail_threshold-verifyBatchSize-mutations--autonomous.

  batch.py schema                      CREATE KEYSPACE b (SimpleStrategy RF 1) and b.t (k int, c int, v blob, PRIMARY KEY (k, c))
                                       WITH compression = {'enabled': false}, both IF NOT EXISTS
  batch.py run <multi|single> <B> <N>  N logged batches, one at a time; each a driver BatchStatement(LOGGED) of a prepared INSERT:
                                       multi: (k=2i, c=0), (k=2i+1, c=0); single: (k=i, c=0), (k=i, c=1); values os.urandom(B*1024)
  batch.py count                       SELECT count(*) FROM b.t
  batch.py truncate                    TRUNCATE b.t
  batch.py bytes <dir>                 sum of file sizes under dir, skipping snapshots/ and backups/; number of *-Data.db (no connection)
Each call prints one line starting RESULT. Imports the bundled driver from CASSANDRA_HOME/lib (the filed PYTHONPATH form)."""
import glob, logging, os, sys, time

cmd = sys.argv[1]
if cmd == 'bytes':
    root, tot, n, data = sys.argv[2], 0, 0, 0
    for d, subs, files in os.walk(root):
        subs[:] = [s for s in subs if s not in ('snapshots', 'backups')]
        for f in files:
            tot += os.path.getsize(os.path.join(d, f)); n += 1
            data += f.endswith('-Data.db')
    print('RESULT bytes dir=%s bytes=%d files=%d data_db=%d' % (root, tot, n, data))
    sys.exit(0)

LIB = os.path.join(os.environ['CASSANDRA_HOME'], 'lib')
z = glob.glob(os.path.join(LIB, 'cassandra-driver-internal-only-*.zip'))[0]
ver = os.path.splitext(os.path.basename(z))[0][len('cassandra-driver-internal-only-'):]
sys.path.insert(0, os.path.join(z, 'cassandra-driver-' + ver))
logging.basicConfig(level=logging.ERROR)
logging.getLogger('cassandra').setLevel(logging.CRITICAL)
from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT  # noqa: E402
from cassandra import ConsistencyLevel, InvalidRequest  # noqa: E402
from cassandra.query import BatchStatement, BatchType  # noqa: E402
from cassandra.policies import DCAwareRoundRobinPolicy  # noqa: E402

prof = ExecutionProfile(request_timeout=60, consistency_level=ConsistencyLevel.ONE,
                        load_balancing_policy=DCAwareRoundRobinPolicy(local_dc='datacenter1'))
cl = Cluster(['127.0.0.1'], protocol_version=5, token_metadata_enabled=False, idle_heartbeat_interval=0,
             execution_profiles={EXEC_PROFILE_DEFAULT: prof})
s = cl.connect()
t0 = time.time()
if cmd == 'schema':
    s.execute("CREATE KEYSPACE IF NOT EXISTS b WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    s.execute("CREATE TABLE IF NOT EXISTS b.t (k int, c int, v blob, PRIMARY KEY (k, c)) WITH compression = {'enabled': false}")
    comp = s.execute("SELECT compression FROM system_schema.tables WHERE keyspace_name='b' AND table_name='t'").one()[0]
    print('RESULT schema ok compression=%s' % dict(comp))
elif cmd == 'run':
    shape, B, N = sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    ins = s.prepare('INSERT INTO b.t (k, c, v) VALUES (?, ?, ?)')
    ok = rej = other = 0
    first = None
    for i in range(N):
        bt = BatchStatement(batch_type=BatchType.LOGGED)
        if shape == 'multi':
            bt.add(ins, (2 * i, 0, os.urandom(B * 1024)))
            bt.add(ins, (2 * i + 1, 0, os.urandom(B * 1024)))
        elif shape == 'single':
            bt.add(ins, (i, 0, os.urandom(B * 1024)))
            bt.add(ins, (i, 1, os.urandom(B * 1024)))
        else:
            raise SystemExit('bad shape')
        try:
            s.execute(bt)
            ok += 1
        except InvalidRequest as e:
            if 'Batch too large' in str(e):
                rej += 1
            else:
                other += 1
            first = first or str(e)[:200]
        except Exception as e:
            other += 1
            first = first or ('OTHER ' + repr(e)[:200])
    print('RESULT shape=%s B=%d n=%d ok=%d rejected=%d other_errors=%d seconds=%.1f first=%s'
          % (shape, B, N, ok, rej, other, time.time() - t0, first))
elif cmd == 'count':
    n = s.execute('SELECT count(*) FROM b.t').one()[0]
    print('RESULT count=%d seconds=%.1f' % (n, time.time() - t0))
elif cmd == 'truncate':
    s.execute('TRUNCATE b.t')
    print('RESULT truncate ok')
cl.shutdown()
