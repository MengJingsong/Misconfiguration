#!/usr/bin/env python3
"""Cluster-tier client (B3c) of initial-buffer-capacity-ensurecapacity-datalengthinbytes--autonomous. Bundled Python driver, protocol 4
(native v5 large requests leave unreturned direct buffers), one host (127.0.3.1:9042), password authentication (the case's B3b amendment:
guardrails do not apply to a superuser or without authentication). Modes (one JSON object on stdout; exit 0 unless the mode could not run):
  ready                          wait until the superuser cassandra/cassandra can log in (default role created ~10 s after start)
  setup <idx 0|1>                as superuser: ordinary role `ordinary`, keyspace ks (RF 1), table ks.t (k blob PRIMARY KEY, v text), and with
                                 idx=1 an SAI index on v; waits for schema agreement
  load <K> <first> <n> <vlen>    as `ordinary`: n INSERTs, i = first..first+n-1; key = 8-byte big-endian i + (K-8) random bytes (K >= 8),
                                 v = 'v%08d' % i padded with 'x' to vlen characters; 48 in flight; outcome counts, first error text
  big <n> <vlen>                 as `ordinary`: n INSERTs with v of vlen characters (a 4 KiB value), key = 16 bytes; outcome counts, first error text
  query <idx 0|1> <K> <first> <n> <q>   as `ordinary`: q point queries on rows chosen at random from first..first+n-1 (seed 7):
                                 idx=1 SELECT k FROM ks.t WHERE v = ?; idx=0 SELECT v FROM ks.t WHERE k = ? (k rebuilt from the same seed is
                                 not possible, so keys of the loaded rows are read first by a paged scan and kept)
"""
import glob, json, os, random, sys, threading, time

CASS = os.environ.get('CASSANDRA_HOME', os.path.expanduser('~/s4-b7-ie'))
LIB = os.path.join(CASS, 'lib')
HOST = os.environ.get('EC_HOST', '127.0.3.1')
PORT = int(os.environ.get('EC_NATIVE_PORT', 9042))


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
from cassandra.auth import PlainTextAuthProvider  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402


def connect(user, pw, timeout=120):
    prof = ExecutionProfile(request_timeout=timeout, consistency_level=ConsistencyLevel.ONE, retry_policy=FallthroughRetryPolicy(),
                            load_balancing_policy=WhiteListRoundRobinPolicy([HOST]))
    c = Cluster([HOST], port=PORT, protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof},
                auth_provider=PlainTextAuthProvider(user, pw))
    return c, c.connect()


def run_async(s, ps, argsets, conc=48):
    sem = threading.Semaphore(conc)
    lock = threading.Lock()
    res = {'ok': 0, 'err': 0, 'errors': {}, 'first_error': None}

    def ok(_):
        with lock:
            res['ok'] += 1
        sem.release()

    def bad(e):
        with lock:
            res['err'] += 1
            k = type(e).__name__
            res['errors'][k] = res['errors'].get(k, 0) + 1
            if res['first_error'] is None:
                res['first_error'] = str(e)[:400]
        sem.release()

    t0 = time.time()
    for a in argsets:
        sem.acquire()
        f = s.execute_async(ps, a)
        f.add_callbacks(ok, bad)
    for _ in range(conc):
        sem.acquire()
    res['seconds'] = round(time.time() - t0, 3)
    return res


def vtext(i, vlen):
    return ('v%08d' % i).ljust(vlen, 'x')


def main():
    mode = sys.argv[1]
    out = {}
    if mode == 'ready':
        t0 = time.time()
        while time.time() - t0 < 180:
            try:
                c, s = connect('cassandra', 'cassandra', timeout=20)
                out = {'ready': True, 'seconds': round(time.time() - t0, 1)}
                c.shutdown()
                break
            except Exception as e:
                out = {'ready': False, 'last': str(e)[:200]}
                time.sleep(3)
    elif mode == 'setup':
        idx = int(sys.argv[2])
        c, s = connect('cassandra', 'cassandra')
        s.execute("CREATE ROLE IF NOT EXISTS ordinary WITH PASSWORD = 'ordinary' AND LOGIN = true")
        s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
        s.execute('CREATE TABLE IF NOT EXISTS ks.t (k blob PRIMARY KEY, v text)')
        if idx:
            s.execute("CREATE CUSTOM INDEX IF NOT EXISTS t_v ON ks.t (v) USING 'StorageAttachedIndex'")
        ok = c.control_connection.wait_for_schema_agreement(wait_time=60)
        r = s.execute("SELECT role, is_superuser, can_login FROM system_auth.roles WHERE role = 'ordinary'").one()
        out = {'schema': 'ok', 'agreement': bool(ok), 'ordinary_is_superuser': r.is_superuser if r else None, 'ordinary_can_login': r.can_login if r else None}
        c.shutdown()
    elif mode == 'load':
        K, first, n, vlen = (int(x) for x in sys.argv[2:6])
        c, s = connect('ordinary', 'ordinary')
        ps = s.prepare('INSERT INTO ks.t (k, v) VALUES (?, ?)')
        rnd = os.urandom(K)
        out = run_async(s, ps, ((i.to_bytes(8, 'big') + rnd[8:], vtext(i, vlen)) for i in range(first, first + n)))
        out.update({'K': K, 'n': n, 'vlen': vlen})
        c.shutdown()
    elif mode == 'big':
        n, vlen = int(sys.argv[2]), int(sys.argv[3])
        c, s = connect('ordinary', 'ordinary')
        ps = s.prepare('INSERT INTO ks.t (k, v) VALUES (?, ?)')
        out = run_async(s, ps, ((b'big' + i.to_bytes(8, 'big') + b'.....', vtext(10_000_000 + i, vlen)) for i in range(n)), conc=4)
        out.update({'n': n, 'vlen': vlen})
        c.shutdown()
    elif mode == 'query':
        idx, K, first, n, q = (int(x) for x in sys.argv[2:7])
        c, s = connect('ordinary', 'ordinary')
        rng = random.Random(7)
        rows = [rng.randrange(first, first + n) for _ in range(q)]
        ok = bad = 0
        found = 0
        t0 = time.time()
        if idx:
            ps = s.prepare('SELECT k FROM ks.t WHERE v = ?')
            for i in rows:
                try:
                    r = list(s.execute(ps, (vtext(i, int(os.environ.get('EC_VLEN', 1000))),)))
                    ok += 1
                    found += len(r)
                except Exception as e:
                    bad += 1
                    out.setdefault('first_error', str(e)[:300])
        else:
            keys = {}
            ps0 = s.prepare('SELECT k, v FROM ks.t')
            for r in s.execute(ps0):
                if r.v and r.v.startswith('v'):
                    keys[int(r.v[1:9])] = r.k
            ps = s.prepare('SELECT v FROM ks.t WHERE k = ?')
            for i in rows:
                try:
                    r = list(s.execute(ps, (keys[i],)))
                    ok += 1
                    found += len(r)
                except Exception as e:
                    bad += 1
                    out.setdefault('first_error', str(e)[:300])
        out.update({'queries': q, 'ok': ok, 'err': bad, 'rows_returned': found, 'seconds': round(time.time() - t0, 2)})
        c.shutdown()
    else:
        sys.exit(__doc__)
    print(json.dumps(out))


main()
