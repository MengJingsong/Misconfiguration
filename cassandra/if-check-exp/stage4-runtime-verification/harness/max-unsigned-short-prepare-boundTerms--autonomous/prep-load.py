#!/usr/bin/env python3
"""Client for the marker-limit cluster tier (B3c/B3i). Python 3.9+, the driver bundled in the tree's lib/. Native protocol 4, session without keyspace.
usage: prep-load.py setup
       prep-load.py load <M> <N> <rate> <stopfile>   up to N distinct PREPAREs of M-marker statements, 8 threads, paced at <rate>/s, stops early if <stopfile> exists
                                                     or after 5 consecutive rejections with no PREPARE ever accepted
       prep-load.py boundary <M>                     one PREPARE of an M-marker statement; prints accepted or the error text
       prep-load.py dup <K> <M>                      K PREPAREs of one text
       prep-load.py rows                             count(*) of system.prepared_statements
Env: PSC_ADDR (default 127.0.3.1), CASSANDRA_HOME. Prints lines starting RESULT."""
import os, sys, threading, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import drv
drv.load()
from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
from cassandra import ConsistencyLevel

cl = Cluster([os.environ.get('PSC_ADDR', '127.0.3.1')], protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: ExecutionProfile(request_timeout=300, consistency_level=ConsistencyLevel.ONE)})
ses = cl.connect()
cmd = sys.argv[1]


def q(m, tag):
    return 'SELECT * FROM ks.t WHERE k IN (' + ', '.join(['?'] * m) + ') /* %s */' % tag


def paced(n, rate, work, stopfile=None):
    lock = threading.Lock(); st = {'i': 0, 'ok': 0, 'err': 0, 'consec': 0, 'first_err': None, 'quit': False}
    t0 = time.time()

    def run():
        while True:
            with lock:
                i = st['i']
                if i >= n or st['quit'] or (stopfile and os.path.exists(stopfile)):
                    return
                st['i'] += 1
            wait = t0 + i / rate - time.time()
            if wait > 0:
                time.sleep(wait)
            try:
                work(i)
                with lock:
                    st['ok'] += 1; st['consec'] = 0
            except Exception as e:
                with lock:
                    st['err'] += 1; st['consec'] += 1
                    st['first_err'] = st['first_err'] or repr(e)[:260]
                    if st['consec'] >= 5 and st['ok'] == 0:
                        st['quit'] = True
    th = [threading.Thread(target=run) for _ in range(8)]
    [t.start() for t in th]; [t.join() for t in th]
    return st, time.time() - t0


if cmd == 'setup':
    ses.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
    ses.execute('CREATE TABLE IF NOT EXISTS ks.t (k int PRIMARY KEY, v int)')
    print('RESULT setup ok', ses.execute('SELECT release_version FROM system.local').one()[0])
elif cmd == 'load':
    m, n, rate, stop = int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4]), sys.argv[5]
    st, dt = paced(n, rate, lambda i: ses.prepare(q(m, 'c%d' % i)), stop)
    print('RESULT load M=%d offered=%d accepted=%d rejected=%d seconds=%.1f rate=%.0f/s quit_on_rejections=%s first_error=%s'
          % (m, st['i'], st['ok'], st['err'], dt, st['i'] / max(dt, 0.001), st['quit'], st['first_err']))
elif cmd == 'boundary':
    m = int(sys.argv[2])
    try:
        p = ses.prepare(q(m, 'boundary'))
        print('RESULT boundary M=%d accepted bind_variables=%d' % (m, len(p.bind_metadata)))
    except Exception as e:
        print('RESULT boundary M=%d rejected %s' % (m, repr(e)[:300]))
elif cmd == 'dup':
    k, m = int(sys.argv[2]), int(sys.argv[3])
    for _ in range(k):
        ses.prepare(q(m, 'dup'))
    print('RESULT dup prepared=%d' % k)
elif cmd == 'rows':
    print('RESULT rows', ses.execute('SELECT count(*) FROM system.prepared_statements').one()[0])
cl.shutdown()
