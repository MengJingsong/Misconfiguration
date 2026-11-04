#!/usr/bin/env python3
"""Cluster-tier client for the two NAME_LENGTH cases (B3c). The build's bundled Python driver (lib/ zip), protocol 4, consistency ONE,
whitelist 127.0.0.1. Modes (one JSON object on stdout, a human line on stderr, exit 0 on OK):
  probe
  ddl    <kind> <L> <N>                 CREATE the targets: kind ks -> N keyspaces named base-36(i) left-padded with 'k' to L chars, each with
                                         table t(id int PRIMARY KEY, v text); kind tbl -> keyspace 'ks' and N tables named (L-3) 'a' + 3-digit i
  write  <kind> <L> <N> <rows> <conc> [part nparts]   <rows> INSERTs of one 100-character value per target, round robin by target (all rows of a target in turn)
  one    <ks> <rows> <conc> [offset]    keyspace <ks> (created if needed), table t, <rows> INSERTs (ids offset..offset+rows-1) of the same 100-character value (control B)
  try-ks <name> | try-tbl <ks> <name>   one CREATE KEYSPACE / TABLE that is expected to be rejected: prints error class and message
"""
import glob, json, os, sys, threading, time

CASS = os.environ.get('CASSANDRA_HOME', os.path.expanduser('~/s4-b2/base'))
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

HOST = '127.0.0.1'
VALUE = ('stage4-' + 'x' * 100)[:100]


def b36(i):
    d = '0123456789abcdefghijklmnopqrstuvwxyz'
    s = ''
    while True:
        s = d[i % 36] + s
        i //= 36
        if i == 0:
            return s


def targets(kind, L, N):
    if kind == 'ks':
        out = []
        for i in range(N):
            b = b36(i)
            assert len(b) <= L
            out.append(('k' * (L - len(b)) + b, 't'))
        return out
    return [('ks', 'a' * (L - 3) + '%03d' % i) for i in range(N)]


def connect(timeout=120):
    prof = ExecutionProfile(request_timeout=timeout, consistency_level=ConsistencyLevel.ONE,
                            load_balancing_policy=WhiteListRoundRobinPolicy([HOST]))
    c = Cluster([HOST], protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof}, token_metadata_enabled=False,
                connect_timeout=30, max_schema_agreement_wait=30)
    return c, c.connect()


def ddl(s, kind, L, N):
    t0 = time.time()
    if kind == 'tbl':
        s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
    for ks, t in targets(kind, L, N):
        if kind == 'ks':
            s.execute("CREATE KEYSPACE %s WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}" % ks)
        s.execute("CREATE TABLE %s.%s (id int PRIMARY KEY, v text)" % (ks, t))
    return {'ok': True, 'created': N, 'kind': kind, 'L': L, 'name_len_first': len(targets(kind, L, N)[0][0 if kind == 'ks' else 1]),
            'sample': targets(kind, L, N)[-1][0 if kind == 'ks' else 1][:60], 'elapsed_s': round(time.time() - t0, 1)}


def write(s, tg, rows, conc, offset=0):
    prep = {}
    for ks, t in tg:
        prep[(ks, t)] = s.prepare("INSERT INTO %s.%s (id, v) VALUES (?, ?)" % (ks, t))
    lock = threading.Condition()
    st = {'inflight': 0, 'ok': 0, 'err': 0, 'errs': []}

    def done(ok, exc=None):
        with lock:
            st['inflight'] -= 1
            st['ok' if ok else 'err'] += 1
            if exc is not None and len(st['errs']) < 3:
                st['errs'].append(repr(exc)[:200])
            lock.notify_all()

    t0 = time.time()
    for key in tg:
        p = prep[key]
        for i in range(rows):
            with lock:
                while st['inflight'] >= conc:
                    lock.wait(1)
                st['inflight'] += 1
            f = s.execute_async(p, (offset + i, VALUE))
            f.add_callbacks(lambda _r: done(True), lambda e: done(False, e))
    with lock:
        while st['inflight'] > 0:
            lock.wait(1)
    el = time.time() - t0
    return {'ok': st['err'] == 0, 'targets': len(tg), 'rows_each': rows, 'succeeded': st['ok'], 'failed': st['err'], 'errors': st['errs'],
            'value_bytes': len(VALUE), 'elapsed_s': round(el, 1), 'rows_per_s': round(st['ok'] / el)}


def main():
    a = sys.argv[1:]
    mode = a[0]
    c, s = connect()
    try:
        if mode == 'probe':
            r = s.execute("SELECT release_version FROM system.local").one()
            out = {'ok': True, 'release_version': r.release_version}
        elif mode == 'ddl':
            out = ddl(s, a[1], int(a[2]), int(a[3]))
        elif mode == 'write':
            tg = targets(a[1], int(a[2]), int(a[3]))
            if len(a) > 7:                       # write ... <part> <nparts>: every nparts-th target starting at part
                tg = tg[int(a[6])::int(a[7])]
            out = write(s, tg, int(a[4]), int(a[5]))
        elif mode == 'one':
            s.execute("CREATE KEYSPACE IF NOT EXISTS %s WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}" % a[1])
            s.execute("CREATE TABLE IF NOT EXISTS %s.t (id int PRIMARY KEY, v text)" % a[1])
            out = write(s, [(a[1], 't')], int(a[2]), int(a[3]), int(a[4]) if len(a) > 4 else 0)
        elif mode in ('try-ks', 'try-tbl'):
            q = ("CREATE KEYSPACE %s WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}" % a[1]) if mode == 'try-ks' \
                else ("CREATE TABLE %s.%s (id int PRIMARY KEY, v text)" % (a[1], a[2]))
            name = a[1] if mode == 'try-ks' else a[2]
            try:
                s.execute(q)
                out = {'ok': True, 'rejected': False, 'name_len': len(name)}
            except Exception as e:
                out = {'ok': True, 'rejected': True, 'name_len': len(name), 'error_class': type(e).__name__, 'message': str(e)[:600]}
        else:
            raise SystemExit('unknown mode')
    finally:
        c.shutdown()
    print(json.dumps(out))
    print(('OK ' if out.get('ok') else 'ERR ') + json.dumps(out)[:300], file=sys.stderr)
    sys.exit(0 if out.get('ok') else 1)


main()
