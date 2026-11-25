#!/usr/bin/env python3
"""C8 stage 3-b confirm (2026-11-24): the attacker's data load, over CQL only, as role `attacker`.
  load3b.py --user attacker --pw PW --rows 2000000 --procs 4 --conc 64 --log FILE
Inserts pk = i, v = md5_hex('big-' + i) (32 distinct characters per row, as the stage-2 seed) into c8.big with the
bundled Python driver (lib/cassandra-driver-internal-only-*.zip, as stage 2's c8.py), PlainTextAuthProvider, CL ONE,
prepared INSERT, execute_concurrent_with_args. The row range is split over --procs processes. No nodetool step.
"""
import argparse, glob, hashlib, multiprocessing as mp, os, sys, time

LIB = '/mydata/s4/3b-C8/cassandra/lib'


def driver():
    z = max(glob.glob(LIB + '/cassandra-driver-internal-only-*.zip'))
    ver = os.path.splitext(os.path.basename(z))[0][len('cassandra-driver-internal-only-'):]
    sys.path.insert(0, os.path.join(z, 'cassandra-driver-' + ver))
    for p in ('pure_sasl-', 'wcwidth-', 'pyasyncore-', 'geomet-', 'futures-'):
        zz = glob.glob(os.path.join(LIB, p + '*.zip'))
        if zz:
            sys.path.insert(0, max(zz))


def work(args):
    lo, hi, user, pw, conc, logf = args
    driver()
    from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
    from cassandra.concurrent import execute_concurrent_with_args
    from cassandra.auth import PlainTextAuthProvider
    from cassandra import ConsistencyLevel
    prof = ExecutionProfile(consistency_level=ConsistencyLevel.ONE, request_timeout=120)
    cl = Cluster(['127.0.0.1'], port=9042, auth_provider=PlainTextAuthProvider(user, pw),
                 execution_profiles={EXEC_PROFILE_DEFAULT: prof})
    s = cl.connect()
    ps = s.prepare('INSERT INTO c8.big (pk, v) VALUES (?, ?)')
    t0 = time.time(); done = lo; step = 20000; errs = 0
    while done < hi:
        rows = [(i, hashlib.md5(f'big-{i}'.encode()).hexdigest()) for i in range(done, min(hi, done + step))]
        res = execute_concurrent_with_args(s, ps, rows, concurrency=conc, raise_on_first_error=False)
        errs += sum(1 for ok, _ in res if not ok)
        done += len(rows)
        if (done - lo) % 100000 == 0:
            with open(logf, 'a') as f:
                f.write(f'{time.strftime("%FT%T")} pid {os.getpid()} [{lo},{hi}) {done - lo} rows {time.time() - t0:.0f} s errors {errs}\n')
    cl.shutdown()
    return hi - lo, errs, time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='attacker'); ap.add_argument('--pw', required=True)
    ap.add_argument('--rows', type=int, default=2000000); ap.add_argument('--procs', type=int, default=4)
    ap.add_argument('--conc', type=int, default=64); ap.add_argument('--log', required=True)
    a = ap.parse_args()
    n = a.rows; k = a.procs
    parts = [(i * n // k, (i + 1) * n // k, a.user, a.pw, a.conc, a.log) for i in range(k)]
    t0 = time.time()
    with mp.Pool(k) as p:
        res = p.map(work, parts)
    rows = sum(r[0] for r in res); errs = sum(r[1] for r in res)
    with open(a.log, 'a') as f:
        f.write(f'{time.strftime("%FT%T")} LOAD DONE rows {rows} errors {errs} in {time.time() - t0:.0f} s\n')
    print(f'rows {rows} errors {errs} in {time.time() - t0:.0f} s')


if __name__ == '__main__':
    main()
