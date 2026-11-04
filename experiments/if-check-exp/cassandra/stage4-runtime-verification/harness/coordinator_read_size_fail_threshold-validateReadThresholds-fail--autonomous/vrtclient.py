#!/usr/bin/env python3
"""B3c (amended 2026-10-25) of coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous: client.
usage: vrtclient.py <driver zip> <mode> [args]
  settings <out>                      read-back of the read-threshold settings from system_views.settings
  schema                              keyspace ks (SimpleStrategy RF 1), table ks.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck))
  load <partitions> <rows>            os.urandom(65536) per row, prepared insert, 16 concurrent requests
  read <P> <secs> <nproc> <outdir>    nproc worker processes start together at a common epoch and loop paged
                                      SELECT * FROM ks.t WHERE pk = ? (random pk) with fetch_size P for <secs> s;
                                      each writes <outdir>/w<i>.lines (one line per query) and <outdir>/w<i>.json;
                                      <outdir>/phase.json holds the common start and end epoch ms
  worker <P> <t_start_ms> <t_end_ms> <outfile> <npk>
Bundled driver (protocol 5), DCAwareRoundRobinPolicy, token_metadata_enabled=False, schema_metadata_enabled=False, CL ONE,
request timeout 60 s, FallthroughRetryPolicy.
Per-query line: q t0=<ms> t1=<ms> pk=<> outcome=OK|ERR rows=<> pages=<> [cls=<> codes=<> msg=<first 200 chars>]
Runbook fix D1 (2026-10-25): after a client-side error (CLIENT_SIDE) the worker rebuilds its session and writes 'reconnect t=<ms> after=<cls>'.
"""
import json, os, random, subprocess, sys, time
_zip = sys.argv[1]
_ver = os.path.splitext(os.path.basename(_zip))[0][len('cassandra-driver-internal-only-'):]
sys.path.insert(0, os.path.join(_zip, 'cassandra-driver-' + _ver))
from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402
from cassandra.policies import DCAwareRoundRobinPolicy, FallthroughRetryPolicy  # noqa: E402
from cassandra.query import SimpleStatement  # noqa: E402
from cassandra.concurrent import execute_concurrent_with_args  # noqa: E402

MODE = sys.argv[2]
ARGS = sys.argv[3:]
NAMES = ['read_thresholds_enabled', 'coordinator_read_size_warn_threshold', 'coordinator_read_size_fail_threshold',
         'local_read_size_warn_threshold', 'local_read_size_fail_threshold', 'row_index_read_size_warn_threshold',
         'row_index_read_size_fail_threshold', 'concurrent_reads', 'read_request_timeout']


CLIENT_SIDE = ('ConnectionShutdown', 'NoHostAvailable', 'OperationTimedOut', 'ConnectionException', 'ConnectionBusy')


def ms():
    return int(time.time() * 1000)


def session():
    prof = ExecutionProfile(load_balancing_policy=DCAwareRoundRobinPolicy(), request_timeout=60,
                            consistency_level=ConsistencyLevel.ONE, retry_policy=FallthroughRetryPolicy())
    c = Cluster(['127.0.0.1'], protocol_version=5, token_metadata_enabled=False, schema_metadata_enabled=False,
                execution_profiles={EXEC_PROFILE_DEFAULT: prof})
    return c, c.connect()


def main():
    if MODE == 'read':
        P, secs, nproc, outdir = int(ARGS[0]), int(ARGS[1]), int(ARGS[2]), ARGS[3]
        npk = int(ARGS[4]) if len(ARGS) > 4 else 8
        os.makedirs(outdir, exist_ok=True)
        t_start = ms() + 8000
        t_end = t_start + secs * 1000
        procs = [subprocess.Popen([sys.executable, os.path.abspath(__file__), _zip, 'worker', str(P), str(t_start), str(t_end),
                                   os.path.join(outdir, 'w%02d' % i), str(npk)]) for i in range(nproc)]
        rcs = [p.wait() for p in procs]
        json.dump({'P': P, 'secs': secs, 'nproc': nproc, 't_start': t_start, 't_end': t_end, 'rcs': rcs, 'returned': ms()},
                  open(os.path.join(outdir, 'phase.json'), 'w'))
        tot = {}
        for i in range(nproc):
            try:
                w = json.load(open(os.path.join(outdir, 'w%02d.json' % i)))
            except Exception:
                w = {'error': 'no summary'}
            for k, v in w.items():
                if isinstance(v, int):
                    tot[k] = tot.get(k, 0) + v
        print('READ P=%d secs=%d nproc=%d rcs=%s totals=%s' % (P, secs, nproc, rcs, json.dumps(tot, sort_keys=True)))
        return 0 if all(r == 0 for r in rcs) else 1
    if MODE == 'worker':
        P, t_start, t_end, outfile, npk = int(ARGS[0]), int(ARGS[1]), int(ARGS[2]), ARGS[3], int(ARGS[4])
        c, s = session()
        stmt = SimpleStatement('SELECT * FROM ks.t WHERE pk = %s', fetch_size=P)
        rnd = random.Random(os.getpid())
        cnt = {'queries': 0, 'ok': 0, 'err': 0, 'rows': 0, 'pages': 0, 'reconnects': 0}
        errs = {}
        jitter = rnd.randrange(500)  # runbook fix D1: spread the first requests over 0.5 s
        with open(outfile + '.lines', 'w') as f:
            while ms() < t_start + jitter:
                time.sleep(0.005)
            while ms() < t_end:
                pk = rnd.randrange(npk)
                t0 = ms(); rows = 0; pages = 0
                try:
                    rs = s.execute(stmt, (pk,))
                    pages = 1; rows = len(rs.current_rows)
                    while rs.has_more_pages:
                        rs.fetch_next_page()
                        pages += 1; rows += len(rs.current_rows)
                    f.write('q t0=%d t1=%d pk=%d outcome=OK rows=%d pages=%d\n' % (t0, ms(), pk, rows, pages))
                    cnt['ok'] += 1
                except Exception as e:
                    cls = type(e).__name__
                    codes = getattr(e, 'error_code_map', None)
                    codes = ','.join('%s:%s' % (k, v) for k, v in sorted(codes.items())) if codes else '-'
                    msg = str(e).replace('\n', ' ')[:200]
                    f.write('q t0=%d t1=%d pk=%d outcome=ERR rows=%d pages=%d cls=%s codes=%s msg=%s\n' % (t0, ms(), pk, rows, pages, cls, codes, msg))
                    cnt['err'] += 1
                    key = cls + '|' + codes
                    errs[key] = errs.get(key, 0) + 1
                    if cls in CLIENT_SIDE:
                        # runbook fix D1: a connection closed under the client (e.g. ENOBUFS on loopback) leaves the
                        # single-host driver with no host; rebuild the session instead of failing every later query
                        try:
                            c.shutdown()
                        except Exception:
                            pass
                        time.sleep(0.2)
                        while True:
                            try:
                                c, s = session()
                                break
                            except Exception:
                                time.sleep(0.5)
                        cnt['reconnects'] += 1
                        f.write('reconnect t=%d after=%s\n' % (ms(), cls))
                cnt['queries'] += 1; cnt['rows'] += rows; cnt['pages'] += pages
        cnt['errors_by_class'] = errs
        json.dump(cnt, open(outfile + '.json', 'w'))
        c.shutdown()
        return 0
    c, s = session()
    try:
        if MODE == 'settings':
            out = {}
            for n in NAMES:
                rows = list(s.execute("SELECT name, value FROM system_views.settings WHERE name = %s", (n,)))
                out[n] = rows[0].value if rows else None
            print('SETTINGS ' + json.dumps(out, sort_keys=True))
            if ARGS:
                json.dump(out, open(ARGS[0], 'w'))
        elif MODE == 'schema':
            s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
            s.execute("CREATE TABLE IF NOT EXISTS ks.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck))")
            print('SCHEMA ok')
        elif MODE == 'load':
            npart, nrows = int(ARGS[0]), int(ARGS[1])
            ps = s.prepare("INSERT INTO ks.t (pk, ck, v) VALUES (?, ?, ?)")
            t0 = ms(); done = 0; failed = 0
            for pk in range(npart):
                for start in range(0, nrows, 64):
                    args = [(pk, ck, os.urandom(65536)) for ck in range(start, min(nrows, start + 64))]
                    res = execute_concurrent_with_args(s, ps, args, concurrency=16, raise_on_first_error=False)
                    for ok, r in res:
                        if ok:
                            done += 1
                        else:
                            failed += 1
            print('LOAD partitions=%d rows=%d acknowledged=%d failed=%d secs=%.1f' % (npart, nrows, done, failed, (ms() - t0) / 1000.0))
            return 0 if failed == 0 else 1
        else:
            print('unknown mode ' + MODE)
            return 2
    finally:
        c.shutdown()
    return 0


if __name__ == '__main__':
    sys.exit(main())
