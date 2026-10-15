#!/usr/bin/env python3
"""Cluster-tier client for max_hints_size_per_host-shouldHint-maxHintsSize (case 9c, amended 2026-10-14).
Bundled Python driver, protocol 5, whitelist: the one host given, consistency ONE. Modes:
  probe <host>
  schema <host>                     CREATE KEYSPACE ks (SimpleStrategy, RF 3) and TABLE ks.t (pk bigint PRIMARY KEY, v blob)
  stream <host> <first_pk> <stopflag> <max_s> <keylog>
                                    one INSERT per row, pk = first_pk, first_pk+1, ..., v = 5,120 random bytes, paced at
                                    RATE rows/s (200) with at most 32 in flight; stops when <stopflag> exists or after
                                    <max_s> seconds (no new request after that; the outstanding ones finish). Every pk is
                                    appended to <keylog> as "pk,ms_sent,ok|err".
  count <host> <outfile>            every pk of ks.t, read at ONE through <host> (paged, 5,000 a page), one per line
One JSON object on stdout, a human line on stderr. Exit 0 on OK, 1 on ERR."""
import glob, json, os, sys, threading, time

CASS = os.environ.get('CASSANDRA_HOME', os.path.expanduser('~/cassandra-run1'))
LIB = os.path.join(CASS, 'lib')
RATE = float(os.environ.get('MHS_RATE', 200))
PAYLOAD = int(os.environ.get('MHS_PAYLOAD', 5120))
INFLIGHT = 32


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
from cassandra.policies import WhiteListRoundRobinPolicy  # noqa: E402
from cassandra.query import SimpleStatement  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402


def connect(host, timeout=60):
    prof = ExecutionProfile(request_timeout=timeout, consistency_level=ConsistencyLevel.ONE,
                            load_balancing_policy=WhiteListRoundRobinPolicy([host]))
    c = Cluster([host], protocol_version=5, execution_profiles={EXEC_PROFILE_DEFAULT: prof})
    return c, c.connect()


def stream(s, first_pk, stopflag, max_s, keylog):
    ps = s.prepare("INSERT INTO ks.t (pk, v) VALUES (?, ?)")
    lock = threading.Condition()
    state = {'inflight': 0, 'ok': 0, 'err': 0, 'errs': []}
    log = open(keylog, 'a')

    def done(pk, sent, ok, exc=None):
        with lock:
            state['inflight'] -= 1
            state['ok' if ok else 'err'] += 1
            if exc is not None and len(state['errs']) < 3:
                state['errs'].append(repr(exc)[:200])
            log.write(f'{pk},{sent},{"ok" if ok else "err"}\n')
            lock.notify_all()

    t0 = time.time()
    i = 0
    while True:
        now = time.time()
        if now - t0 >= max_s or os.path.exists(stopflag):
            break
        due = t0 + i / RATE
        if due > now:
            time.sleep(min(due - now, 0.05))
            continue
        with lock:
            while state['inflight'] >= INFLIGHT:
                lock.wait(1)
            state['inflight'] += 1
        pk = first_pk + i
        sent = int(time.time() * 1000)
        f = s.execute_async(ps, (pk, os.urandom(PAYLOAD)))
        f.add_callbacks(lambda _r, pk=pk, sent=sent: done(pk, sent, True),
                        lambda e, pk=pk, sent=sent: done(pk, sent, False, e))
        i += 1
    with lock:
        while state['inflight'] > 0:
            lock.wait(1)
    log.close()
    el = time.time() - t0
    return {'ok': state['err'] == 0 and i > 0, 'written': i, 'succeeded': state['ok'], 'failed': state['err'],
            'errors': state['errs'], 'first_pk': first_pk, 'last_pk': first_pk + i - 1, 'rows_per_s': round(i / el, 2),
            'stopped_by': 'flag' if os.path.exists(stopflag) else 'time'}


def main():
    a = sys.argv[1:]
    mode, host = a[0], a[1]
    c, s = connect(host, timeout=120 if mode == 'count' else 60)
    t0 = time.time()
    try:
        if mode == 'probe':
            row = s.execute("SELECT release_version, host_id FROM system.local").one()
            out = {'ok': True, 'release_version': row.release_version, 'host_id': str(row.host_id), 'protocol': c.protocol_version}
        elif mode == 'schema':
            s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 3}")
            s.execute("CREATE TABLE IF NOT EXISTS ks.t (pk bigint PRIMARY KEY, v blob)")
            agreed = c.control_connection.wait_for_schema_agreement(wait_time=60)
            out = {'ok': bool(agreed), 'schema_agreement': agreed}
        elif mode == 'stream':
            out = stream(s, int(a[2]), a[3], float(a[4]), a[5])
        elif mode == 'count':
            st = SimpleStatement("SELECT pk FROM ks.t", fetch_size=5000, consistency_level=ConsistencyLevel.ONE)
            n = 0
            with open(a[2], 'w') as f:
                for row in s.execute(st):
                    f.write(f'{row.pk}\n')
                    n += 1
            out = {'ok': True, 'rows': n}
        else:
            raise SystemExit('unknown mode')
    finally:
        c.shutdown()
    out['elapsed_s'] = round(time.time() - t0, 3)
    print(json.dumps(out))
    print(('OK ' if out.get('ok') else 'ERR ') + json.dumps(out)[:300], file=sys.stderr)
    sys.exit(0 if out.get('ok') else 1)


main()
