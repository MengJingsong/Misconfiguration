#!/usr/bin/env python3
"""Cluster-tier client for WRITE_BUFFER_SIZE-append-remaining--autonomous (B3c). Bundled Python driver loaded from the
clone's lib/ zip (as the max_hints_size_per_host harness's write-load.py does), **protocol 4** (large native-v5 requests
leave unreturned direct buffers on the node, HANDOFF lesson 2026-10-15 `networking_cache_size` arm L, and this tier reads
direct memory), whitelist: the one host given, consistency ONE. Modes:
  probe  <host>
  schema <host> <ks>        CREATE KEYSPACE <ks> (SimpleStrategy, RF 2) and TABLE <ks>.t (pk bigint PRIMARY KEY, v blob)
  drop   <host> <ks>        DROP KEYSPACE IF EXISTS <ks>
  write  <host> <ks> <size> <bytes> <conc> <first_pk> <max_s> <keylog>
                            INSERTs of one random <size>-byte value (generated once per call) with pk = first_pk, ...,
                            until <bytes> of values are sent, at most <conc> in flight; stops early after <max_s> s
                            or after 20 consecutive failures (no new request then; the outstanding ones finish).
                            Every pk is appended to <keylog> as "pk,ms_sent,ms_done,ok|err".
One JSON object on stdout, a human line on stderr. Exit 0 on OK, 1 on ERR."""
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


def connect(host, timeout=60):
    prof = ExecutionProfile(request_timeout=timeout, consistency_level=ConsistencyLevel.ONE,
                            load_balancing_policy=WhiteListRoundRobinPolicy([host]))
    c = Cluster([host], protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof},
                token_metadata_enabled=False)
    return c, c.connect()


def write(s, ks, size, total, conc, first_pk, max_s, keylog):
    ps = s.prepare(f"INSERT INTO {ks}.t (pk, v) VALUES (?, ?)")
    value = os.urandom(size)
    n_target = max(1, total // size)
    lock = threading.Condition()
    st = {'inflight': 0, 'ok': 0, 'err': 0, 'consec': 0, 'errs': []}
    log = open(keylog, 'a')

    def done(pk, sent, ok, exc=None):
        with lock:
            st['inflight'] -= 1
            st['ok' if ok else 'err'] += 1
            st['consec'] = 0 if ok else st['consec'] + 1
            if exc is not None and len(st['errs']) < 5:
                st['errs'].append(repr(exc)[:200])
            log.write(f'{pk},{sent},{int(time.time() * 1000)},{"ok" if ok else "err"}\n')
            lock.notify_all()

    t0 = time.time()
    i = 0
    stopped = 'count'
    while i < n_target:
        if time.time() - t0 >= max_s:
            stopped = 'time'
            break
        with lock:
            while st['inflight'] >= conc:
                lock.wait(1)
            if st['consec'] >= 20:
                stopped = 'failures'
                break
            st['inflight'] += 1
        pk = first_pk + i
        sent = int(time.time() * 1000)
        f = s.execute_async(ps, (pk, value))
        f.add_callbacks(lambda _r, pk=pk, sent=sent: done(pk, sent, True),
                        lambda e, pk=pk, sent=sent: done(pk, sent, False, e))
        i += 1
    with lock:
        while st['inflight'] > 0:
            lock.wait(1)
    log.close()
    el = time.time() - t0
    return {'ok': i > 0, 'target': n_target, 'written': i, 'succeeded': st['ok'], 'failed': st['err'],
            'errors': st['errs'], 'first_pk': first_pk, 'last_pk': first_pk + i - 1, 'size': size, 'conc': conc,
            'elapsed_s': round(el, 2), 'mb_per_s': round(st['ok'] * size / el / 1e6, 2), 'stopped_by': stopped}


def main():
    a = sys.argv[1:]
    mode, host = a[0], a[1]
    c, s = connect(host)
    t0 = time.time()
    try:
        if mode == 'probe':
            row = s.execute("SELECT release_version, host_id FROM system.local").one()
            out = {'ok': True, 'release_version': row.release_version, 'host_id': str(row.host_id), 'protocol': c.protocol_version}
        elif mode == 'schema':
            s.execute(f"CREATE KEYSPACE IF NOT EXISTS {a[2]} WITH replication = {{'class': 'SimpleStrategy', 'replication_factor': 2}}")
            s.execute(f"CREATE TABLE IF NOT EXISTS {a[2]}.t (pk bigint PRIMARY KEY, v blob)")
            agreed = c.control_connection.wait_for_schema_agreement(wait_time=30)
            out = {'ok': True, 'schema_agreement': agreed}
        elif mode == 'drop':
            s.execute(f"DROP KEYSPACE IF EXISTS {a[2]}")
            out = {'ok': True}
        elif mode == 'write':
            out = write(s, a[2], int(a[3]), int(a[4]), int(a[5]), int(a[6]), float(a[7]), a[8])
        else:
            raise SystemExit('unknown mode')
    finally:
        c.shutdown()
    out.setdefault('elapsed_s', round(time.time() - t0, 3))
    print(json.dumps(out))
    print(('OK ' if out.get('ok') else 'ERR ') + json.dumps(out)[:300], file=sys.stderr)
    sys.exit(0 if out.get('ok') else 1)


main()
