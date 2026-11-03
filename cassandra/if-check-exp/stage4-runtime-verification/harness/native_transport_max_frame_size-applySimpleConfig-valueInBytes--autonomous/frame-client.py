#!/usr/bin/env python3
"""Cluster-tier client (B3c, amended 2026-10-24) of native_transport_max_frame_size-applySimpleConfig-valueInBytes--autonomous.
Bundled driver lib/cassandra-driver-internal-only-*.zip of $CASSANDRA_HOME (loaded as bin/cqlsh.py loads it), one node 127.0.0.1,
DCAwareRoundRobinPolicy(local_dc='datacenter1'), token_metadata_enabled=False, request timeout 60 s, FallthroughRetryPolicy, CL ONE.
Modes (each prints JSON lines; the protocol version is pinned per call):
  schema                          create ks (RF 1) and ks.t (k int PRIMARY KEY, v blob) over v4
  readback                        SELECT value FROM system_views.settings WHERE name='native_transport_max_frame_size' (v4)
  single <K> <f> <n> <k0> <proto> n sequential inserts of floor(f*K) zero bytes, keys k0..k0+n-1; one line per insert
  flood <K> <f> <secs> <workers>  <workers> processes (mode worker), each its own Cluster (v4), inserting for <secs> s; killed at secs+30
  worker <K> <f> <secs> <wid>     one flood worker: synchronous inserts of key 1000+wid; prints one summary line
"""
import glob, json, os, subprocess, sys, time

CASS = os.environ['CASSANDRA_HOME']
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
from cassandra import ConsistencyLevel  # noqa: E402
from cassandra.policies import FallthroughRetryPolicy, DCAwareRoundRobinPolicy  # noqa: E402

TIMEOUT = 60
INSERT = "INSERT INTO ks.t (k, v) VALUES (?, ?)"


def connect(proto):
    prof = ExecutionProfile(request_timeout=TIMEOUT, consistency_level=ConsistencyLevel.ONE, retry_policy=FallthroughRetryPolicy(),
                            load_balancing_policy=DCAwareRoundRobinPolicy(local_dc='datacenter1'))
    c = Cluster(['127.0.0.1'], protocol_version=proto, token_metadata_enabled=False, execution_profiles={EXEC_PROFILE_DEFAULT: prof})
    return c, c.connect()


def err(e):
    return {'cls': type(e).__name__, 'msg': str(e)[:400]}


def emit(d):
    print(json.dumps(d), flush=True)


def main():
    a = sys.argv[1:]
    mode = a[0]
    if mode == 'schema':
        c, s = connect(4)
        s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
        s.execute("CREATE TABLE IF NOT EXISTS ks.t (k int PRIMARY KEY, v blob)")
        emit({'mode': 'schema', 'ok': True, 'protocol': c.protocol_version})
        c.shutdown()
    elif mode == 'readback':
        c, s = connect(4)
        row = s.execute("SELECT value FROM system_views.settings WHERE name = 'native_transport_max_frame_size'").one()
        emit({'mode': 'readback', 'value': row.value if row else None, 'protocol': c.protocol_version})
        c.shutdown()
    elif mode == 'single':
        K, f, n, k0, proto = int(a[1]), float(a[2]), int(a[3]), int(a[4]), int(a[5])
        size = int(f * K)
        c, s = connect(proto)
        ps = s.prepare(INSERT)
        blob = bytes(size)
        for i in range(n):
            t0 = time.time()
            d = {'mode': 'single', 'K': K, 'f': f, 'size': size, 'k': k0 + i, 'protocol': c.protocol_version}
            try:
                s.execute(ps, (k0 + i, blob))
                d.update(ok=True)
            except Exception as e:  # noqa: BLE001 - the class is the reading
                d.update(ok=False, **err(e))
            d['secs'] = round(time.time() - t0, 3)
            emit(d)
        c.shutdown()
    elif mode == 'worker':
        K, f, secs, wid = int(a[1]), float(a[2]), float(a[3]), int(a[4])
        size = int(f * K)
        c, s = connect(4)
        ps = s.prepare(INSERT)
        blob = bytes(size)
        ok, errs, first_err = 0, {}, None
        t_start = time.time()
        end = t_start + secs
        while time.time() < end:
            try:
                s.execute(ps, (1000 + wid, blob))
                ok += 1
            except Exception as e:  # noqa: BLE001
                e2 = err(e)
                key = e2['cls'] + ': ' + ('Request is too big' if 'Request is too big' in e2['msg'] else e2['msg'][:120])
                errs[key] = errs.get(key, 0) + 1
                first_err = first_err or e2
        emit({'mode': 'worker', 'wid': wid, 'K': K, 'f': f, 'size': size, 'protocol': c.protocol_version, 'ok': ok, 'errors': errs,
              'first_error': first_err, 't_start': round(t_start, 3), 't_end': round(time.time(), 3)})
        c.shutdown()
    elif mode == 'flood':
        K, f, secs, workers = a[1], a[2], float(a[3]), int(a[4])
        procs = [subprocess.Popen([sys.executable, '-I', os.path.abspath(__file__), 'worker', K, f, str(secs), str(w)],
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=os.environ) for w in range(workers)]
        deadline = time.time() + secs + 30
        for p in procs:
            try:
                out, _ = p.communicate(timeout=max(1, deadline - time.time()))
                sys.stdout.write(out.decode())
            except subprocess.TimeoutExpired:
                p.kill()
                emit({'mode': 'flood', 'killed_worker_pid': p.pid})
        sys.stdout.flush()
    else:
        sys.exit('unknown mode ' + mode)


if __name__ == '__main__':
    main()
