#!/usr/bin/env python3
"""Cluster-tier client for internode_application_receive_queue_capacity-acquireCapacity-queueCapacity (case 9c, amended
2026-10-14). Bundled Python driver, protocol 5, whitelist: the one host given. Modes:
  probe <host>
  schema <host> <rf>               CREATE KEYSPACE ks (SimpleStrategy, RF <rf>) and TABLE ks.t (pk bigint PRIMARY KEY, v blob)
  truncate <host>                  TRUNCATE ks.t (every node must be up)
  inflight <host> <first_pk> <W> <max_s> <payload> <keylog> [<max_rows>]
                                   INSERT INTO ks.t at CL ALL, pk = first_pk, first_pk+1, ..., v = <payload> random bytes,
                                   keeping exactly W requests in flight (a new one is sent when one completes) until
                                   <max_s> seconds or <max_rows> rows have been sent; then the outstanding ones finish.
                                   Every pk is appended to <keylog> as "pk,ms_sent,ms_done,ok|err".
One JSON object on stdout, a human line on stderr. Exit 0 on OK, 1 on ERR.
Adapted from the max_hints_size_per_host harness's write-load.py (the paced stream replaced by a fixed in-flight count)."""
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
from cassandra.policies import WhiteListRoundRobinPolicy  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402


def connect(host, timeout=60, cl=ConsistencyLevel.ALL):
    prof = ExecutionProfile(request_timeout=timeout, consistency_level=cl,
                            load_balancing_policy=WhiteListRoundRobinPolicy([host]))
    c = Cluster([host], protocol_version=5, execution_profiles={EXEC_PROFILE_DEFAULT: prof})
    return c, c.connect()


def inflight(s, first_pk, w, max_s, payload, keylog, max_rows):
    ps = s.prepare("INSERT INTO ks.t (pk, v) VALUES (?, ?)")
    lock = threading.Condition()
    state = {'inflight': 0, 'ok': 0, 'err': 0, 'errs': [], 'max_inflight': 0}
    log = open(keylog, 'a')

    def done(pk, sent, ok, exc=None):
        now = int(time.time() * 1000)
        with lock:
            state['inflight'] -= 1
            state['ok' if ok else 'err'] += 1
            if exc is not None and len(state['errs']) < 5:
                state['errs'].append(repr(exc)[:300])
            log.write(f'{pk},{sent},{now},{"ok" if ok else "err"}\n')
            lock.notify_all()

    t0 = time.time()
    i = 0
    while True:
        if time.time() - t0 >= max_s or (max_rows and i >= max_rows):
            break
        with lock:
            while state['inflight'] >= w:
                lock.wait(0.5)
            if time.time() - t0 >= max_s:
                break
            state['inflight'] += 1
            state['max_inflight'] = max(state['max_inflight'], state['inflight'])
        pk = first_pk + i
        sent = int(time.time() * 1000)
        f = s.execute_async(ps, (pk, os.urandom(payload)))
        f.add_callbacks(lambda _r, pk=pk, sent=sent: done(pk, sent, True),
                        lambda e, pk=pk, sent=sent: done(pk, sent, False, e))
        i += 1
    t_stop = time.time()
    with lock:
        while state['inflight'] > 0:
            lock.wait(1)
    log.close()
    el = time.time() - t0
    return {'ok': state['err'] == 0 and i > 0, 'written': i, 'succeeded': state['ok'], 'failed': state['err'],
            'errors': state['errs'], 'first_pk': first_pk, 'last_pk': first_pk + i - 1, 'w': w,
            'max_inflight': state['max_inflight'], 'payload': payload, 'send_s': round(t_stop - t0, 3),
            'rows_per_s': round(i / el, 2), 't0_ms': int(t0 * 1000), 'stop_ms': int(t_stop * 1000)}


def main():
    a = sys.argv[1:]
    mode, host = a[0], a[1]
    c, s = connect(host, timeout=120 if mode in ('truncate', 'schema') else 60)
    t0 = time.time()
    try:
        if mode == 'probe':
            row = s.execute("SELECT release_version, host_id FROM system.local").one()
            out = {'ok': True, 'release_version': row.release_version, 'host_id': str(row.host_id), 'protocol': c.protocol_version}
        elif mode == 'schema':
            rf = int(a[2])
            s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': %d}" % rf)
            s.execute("CREATE TABLE IF NOT EXISTS ks.t (pk bigint PRIMARY KEY, v blob)")
            agreed = c.control_connection.wait_for_schema_agreement(wait_time=60)
            out = {'ok': bool(agreed), 'schema_agreement': agreed}
        elif mode == 'truncate':
            s.execute("TRUNCATE ks.t", timeout=120)
            out = {'ok': True}
        elif mode == 'inflight':
            out = inflight(s, int(a[2]), int(a[3]), float(a[4]), int(a[5]), a[6], int(a[7]) if len(a) > 7 else 0)
        else:
            raise SystemExit('unknown mode')
    finally:
        c.shutdown()
    out['elapsed_s'] = round(time.time() - t0, 3)
    print(json.dumps(out))
    print(('OK ' if out.get('ok') else 'ERR ') + json.dumps(out)[:300], file=sys.stderr)
    sys.exit(0 if out.get('ok') else 1)


main()
