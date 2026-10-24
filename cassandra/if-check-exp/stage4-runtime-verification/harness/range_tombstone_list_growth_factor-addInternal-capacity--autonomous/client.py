#!/usr/bin/env python3
"""Cluster-tier client of the range_tombstone_list_growth_factor autonomous cases. Bundled Python driver, protocol 4,
whitelist: the one host:port given, no driver retries. Modes (one JSON object on stdout; exit 0 unless the mode could not run):
  schema <host> <port>                       keyspace ks (SimpleStrategy RF 1); tables ks.t and ks.t2 (pk int, ck int, v int, PRIMARY KEY (pk, ck))
  load <host> <port> <kind> <table> <p0> <p1> <i0> <i1> <conc>
        for every partition pk in [p0, p1), the statements i in [i0, i1) in ascending order, one request in flight per partition
        (execute_async chained from the callback), at most <conc> partitions active at once. kind:
          del1  DELETE FROM ks.<table> WHERE pk = ? AND ck > 2i AND ck < 2i+1     (case addInternal-capacity, as filed)
          del4  DELETE FROM ks.<table> WHERE pk = ? AND ck > 4i AND ck < 4i+2     (cases growToFree-newLength, grow-newLength, as filed)
          ins   INSERT INTO ks.<table> (pk, ck, v) VALUES (?, i, 1)               (plain-write controls)
        reports ok, errors (first 3 messages), seconds.
  select <host> <port> <table> <pk>          count of rows and the first rows of one partition (a live check that the writes are readable)
Driver loading from the max_mutation_size harness's client.py."""
import glob, json, os, sys, threading, time

CASS = os.environ.get('CASSANDRA_HOME', os.path.expanduser('~/cassandra-run1'))
LIB = os.path.join(CASS, 'lib')


def find_zip(prefix):
    z = glob.glob(os.path.join(LIB, prefix + '*.zip'))
    return max(z) if z else None


cql = find_zip('cassandra-driver-internal-only-')
ver = os.path.splitext(os.path.basename(cql))[0][len('cassandra-driver-internal-only-'):]
sys.path.insert(0, os.path.join(cql, 'cassandra-driver-' + ver))
for lib in ('pure_sasl-', 'wcwidth-', 'pyasyncore-'):
    z = find_zip(lib)
    if z:
        sys.path.insert(0, z)

from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT  # noqa: E402
from cassandra.policies import WhiteListRoundRobinPolicy, FallthroughRetryPolicy  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402


def connect(host, port, timeout=60):
    prof = ExecutionProfile(request_timeout=timeout, consistency_level=ConsistencyLevel.ONE, retry_policy=FallthroughRetryPolicy(),
                            load_balancing_policy=WhiteListRoundRobinPolicy([host]))
    c = Cluster([host], port=port, protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof}, connect_timeout=30)
    return c, c.connect()


def main():
    mode, host, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
    c, s = connect(host, port)
    if mode == 'schema':
        s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
        for t in ('t', 't2'):
            s.execute('CREATE TABLE IF NOT EXISTS ks.%s (pk int, ck int, v int, PRIMARY KEY (pk, ck))' % t)
        ok = c.control_connection.wait_for_schema_agreement(wait_time=60)
        print(json.dumps({'schema': 'ok', 'agreement': bool(ok)}))
    elif mode == 'select':
        table, pk = sys.argv[4], int(sys.argv[5])
        rows = list(s.execute('SELECT ck, v FROM ks.%s WHERE pk = %d' % (table, pk)))
        print(json.dumps({'table': table, 'pk': pk, 'rows': len(rows), 'first': [[r.ck, r.v] for r in rows[:3]]}))
    elif mode == 'load':
        kind, table = sys.argv[4], sys.argv[5]
        p0, p1, i0, i1, conc = map(int, sys.argv[6:11])
        if kind in ('del1', 'del4'):
            ps = s.prepare('DELETE FROM ks.%s WHERE pk = ? AND ck > ? AND ck < ?' % table)
            mul = 2 if kind == 'del1' else 4
            span = 1 if kind == 'del1' else 2

            def stmt(pk, i):
                return ps, (pk, mul * i, mul * i + span)
        elif kind == 'ins':
            ps = s.prepare('INSERT INTO ks.%s (pk, ck, v) VALUES (?, ?, 1)' % table)

            def stmt(pk, i):
                return ps, (pk, i)
        else:
            sys.exit('unknown kind ' + kind)
        errs, lock = [], threading.Lock()
        okc = [0]
        done = threading.Semaphore(0)
        pending = list(range(p0, p1))
        plock = threading.Lock()

        def start_partition():
            with plock:
                if not pending:
                    return False
                pk = pending.pop(0)
            state = {'i': i0}

            def issue():
                if state['i'] >= i1:
                    done.release()
                    start_partition()
                    return
                p, args = stmt(pk, state['i'])
                f = s.execute_async(p, args)
                f.add_callbacks(callback=on_ok, errback=on_err)

            def on_ok(_):
                with lock:
                    okc[0] += 1
                state['i'] += 1
                issue()

            def on_err(e):
                with lock:
                    errs.append('pk=%d i=%d %s: %s' % (pk, state['i'], type(e).__name__, str(e)[:200]))
                done.release()          # a failed partition stops: a failed write is a reading, not a retry
                start_partition()
            issue()
            return True

        t0 = time.time()
        for _ in range(min(conc, p1 - p0)):
            start_partition()
        for _ in range(p1 - p0):
            done.acquire()
        print(json.dumps({'ok': okc[0], 'expected': (p1 - p0) * (i1 - i0), 'errors': len(errs), 'first_errors': errs[:3], 'seconds': round(time.time() - t0, 2)}))
    c.shutdown()


main()
