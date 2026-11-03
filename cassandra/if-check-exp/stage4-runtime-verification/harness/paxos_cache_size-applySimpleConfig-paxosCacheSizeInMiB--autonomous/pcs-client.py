#!/usr/bin/env python3
"""Cluster-tier client (B3c, amended 2026-10-25) of paxos_cache_size-applySimpleConfig-paxosCacheSizeInMiB--autonomous.
Bundled Python driver (lib/cassandra-driver-internal-only-*.zip), protocol 5, one node. Modes:
  settings                         read-back: name, value from system_views.settings for paxos_cache_size, paxos_variant,
                                   paxos_state_purging
  schema                           CREATE KEYSPACE ks (SimpleStrategy, RF 1); CREATE TABLE ks.t (k int PRIMARY KEY, v blob)
  lwt <lo> <hi_excl> [histo_pid histo_dir]
                                   prepared INSERT INTO ks.t (k, v) VALUES (?, ?) IF NOT EXISTS for k in [lo, hi), v = os.urandom(4096),
                                   commit consistency LOCAL_ONE, serial consistency SERIAL, 32 in flight; if histo_pid is given,
                                   `jmap -histo:live <pid>` (and `jcmd <pid> GC.heap_info`) is started without pausing the load when
                                   25 / 50 / 75 % of the requests have been submitted (files histo-load-<pct>.txt in histo_dir)
One JSON object on stdout. Exit 0 on OK, 1 on ERR."""
import glob, json, os, subprocess, sys, time

CASS = os.environ.get('CASSANDRA_HOME')
LIB = os.path.join(CASS, 'lib')


def find_zip(prefix):
    z = glob.glob(os.path.join(LIB, prefix + '*.zip'))
    return max(z) if z else None


cql = find_zip('cassandra-driver-internal-only-')
ver = os.path.splitext(os.path.basename(cql))[0][len('cassandra-driver-internal-only-'):]
sys.path.insert(0, os.path.join(cql, 'cassandra-driver-' + ver))
for lib in ('pure_sasl-', 'wcwidth-', 'pyasyncore-', 'geomet-'):
    z = find_zip(lib)
    if z:
        sys.path.insert(0, z)

from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT  # noqa: E402
from cassandra.policies import DCAwareRoundRobinPolicy  # noqa: E402
from cassandra.concurrent import execute_concurrent  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402

CONC = 32
PAYLOAD = 4096


def main():
    a = sys.argv[1:]
    mode = a[0]
    prof = ExecutionProfile(load_balancing_policy=DCAwareRoundRobinPolicy(), request_timeout=60,
                            consistency_level=ConsistencyLevel.LOCAL_ONE, serial_consistency_level=ConsistencyLevel.SERIAL)
    c = Cluster(['127.0.0.1'], protocol_version=5, execution_profiles={EXEC_PROFILE_DEFAULT: prof}, token_metadata_enabled=False)
    s = c.connect()
    t0 = time.time()
    out = {'ok': True, 'mode': mode}
    try:
        if mode == 'settings':
            rows = s.execute("SELECT name, value FROM system_views.settings WHERE name IN ('paxos_cache_size', 'paxos_variant', 'paxos_state_purging')")
            out['settings'] = {r.name: r.value for r in rows}
        elif mode == 'schema':
            s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
            s.execute("CREATE TABLE IF NOT EXISTS ks.t (k int PRIMARY KEY, v blob)")
        elif mode == 'lwt':
            lo, hi = int(a[1]), int(a[2])
            hpid = a[3] if len(a) > 3 else None
            hdir = a[4] if len(a) > 4 else None
            n = hi - lo
            marks = {lo + n // 4: 25, lo + n // 2: 50, lo + 3 * n // 4: 75} if hpid else {}
            procs = []
            ps = s.prepare("INSERT INTO ks.t (k, v) VALUES (?, ?) IF NOT EXISTS")

            def gen():
                for k in range(lo, hi):
                    if k in marks:
                        pct = marks[k]
                        f = open(os.path.join(hdir, 'histo-load-%d.txt' % pct), 'w')
                        procs.append((pct, time.time(), subprocess.Popen(['jmap', '-histo:live', hpid], stdout=f, stderr=subprocess.STDOUT)))
                        g = open(os.path.join(hdir, 'heapinfo-load-%d.txt' % pct), 'w')
                        procs.append((pct, time.time(), subprocess.Popen(['jcmd', hpid, 'GC.heap_info'], stdout=g, stderr=subprocess.STDOUT)))
                    yield ps, (k, os.urandom(PAYLOAD))

            applied = not_applied = errors = 0
            first_err = None
            for ok, res in execute_concurrent(s, gen(), concurrency=CONC, raise_on_first_error=False, results_generator=True):
                if not ok:
                    errors += 1
                    if first_err is None:
                        first_err = repr(res)[:300]
                    continue
                row = res.one()
                if row is not None and row[0] is True:
                    applied += 1
                else:
                    not_applied += 1
            for pct, ts, p in procs:
                p.wait()
            out.update({'lo': lo, 'hi': hi, 'requests': n, 'applied': applied, 'not_applied': not_applied, 'errors': errors,
                        'first_error': first_err, 'histo_started': [[pct, round(ts, 3)] for pct, ts, p in procs]})
        else:
            raise ValueError('unknown mode ' + mode)
    except Exception as e:  # noqa
        out = {'ok': False, 'mode': mode, 'error': repr(e)[:500]}
    out['secs'] = round(time.time() - t0, 2)
    print(json.dumps(out))
    c.shutdown()
    sys.exit(0 if out['ok'] else 1)


if __name__ == '__main__':
    main()
