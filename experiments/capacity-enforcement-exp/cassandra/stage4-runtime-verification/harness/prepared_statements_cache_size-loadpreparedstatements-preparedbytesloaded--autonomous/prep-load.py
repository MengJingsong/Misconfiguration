#!/usr/bin/env python3
"""Client for the prepared_statements_cache_size cluster tier (B3c). Python 3.9+, the driver bundled in the clone's lib/.
usage: prep-load.py setup
       prep-load.py plain <N> <rate>        N unprepared SELECTs (simple statements), paced at <rate>/s, 8 threads   (B3h d)
       prep-load.py load <N> <rate> <stopfile>   N distinct PREPAREs of fully qualified SELECTs, session with NO keyspace, paced,
                                            8 threads; every 200th op also executes one of 10 hot statements; stops early if <stopfile> exists
       prep-load.py dup <K>                 K PREPAREs of one text                                                    (B3h a)
       prep-load.py oversize <bytes>        one PREPARE whose literal is <bytes> chars
Prints one result line starting RESULT. Statements: SELECT v FROM ks.t WHERE k = ? /* c<i> */ (unique trailing comment)."""
import os, sys, threading, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import drv
drv.load()
from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
from cassandra import ConsistencyLevel

cl = Cluster(['127.0.0.1'], protocol_version=5, execution_profiles={EXEC_PROFILE_DEFAULT: ExecutionProfile(request_timeout=120, consistency_level=ConsistencyLevel.ONE)})
ses = cl.connect()          # no keyspace: one cache entry per fully qualified PREPARE
cmd = sys.argv[1]
Q = 'SELECT v FROM ks.t WHERE k = ? /* %s */'


def paced(n, rate, work, stopfile=None):
    lock = threading.Lock(); st = {'i': 0, 'err': 0, 'first_err': None}
    t0 = time.time()

    def run():
        while True:
            with lock:
                i = st['i']
                if i >= n or (stopfile and os.path.exists(stopfile)):
                    return
                st['i'] += 1
            wait = t0 + i / rate - time.time()
            if wait > 0:
                time.sleep(wait)
            try:
                work(i)
            except Exception as e:
                with lock:
                    st['err'] += 1
                    st['first_err'] = st['first_err'] or repr(e)[:200]
    th = [threading.Thread(target=run) for _ in range(8)]
    [t.start() for t in th]; [t.join() for t in th]
    return st, time.time() - t0


if cmd == 'setup':
    ses.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
    ses.execute('CREATE TABLE IF NOT EXISTS ks.t (k text PRIMARY KEY, v int)')
    ses.execute("INSERT INTO ks.t (k, v) VALUES ('hot', 1)")
    print('RESULT setup ok', ses.execute('SELECT release_version FROM system.local').one()[0])
elif cmd == 'plain':
    n, rate = int(sys.argv[2]), float(sys.argv[3])
    st, dt = paced(n, rate, lambda i: ses.execute("SELECT v FROM ks.t WHERE k = 'p%d'" % i))
    print('RESULT plain n=%d done=%d errors=%d seconds=%.1f first_error=%s' % (n, st['i'], st['err'], dt, st['first_err']))
elif cmd == 'load':
    n, rate, stop = int(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
    hot = [ses.prepare(Q % ('hot%d' % j)) for j in range(10)]
    hot_ok = {'n': 0}

    def work(i):
        ses.prepare(Q % ('c%d' % i))
        if i % 200 == 0:
            r = ses.execute(hot[(i // 200) % 10], ('hot',)).one()
            if r is not None and r[0] == 1:
                hot_ok['n'] += 1
    st, dt = paced(n, rate, work, stop)
    print('RESULT load offered=%d prepared=%d errors=%d seconds=%.1f rate=%.0f/s hot_executes_ok=%d first_error=%s'
          % (n, st['i'], st['err'], dt, st['i'] / dt, hot_ok['n'], st['first_err']))
elif cmd == 'dup':
    k = int(sys.argv[2])
    for _ in range(k):
        ses.prepare(Q % 'dup')
    print('RESULT dup prepared=%d' % k)
elif cmd == 'oversize':
    size = int(sys.argv[2])
    q = "SELECT v FROM ks.t WHERE k = '" + 'x' * size + "'"
    try:
        ses.prepare(q)
        print('RESULT oversize chars=%d accepted' % len(q))
    except Exception as e:
        print('RESULT oversize chars=%d rejected %s' % (len(q), repr(e)[:260]))
cl.shutdown()
