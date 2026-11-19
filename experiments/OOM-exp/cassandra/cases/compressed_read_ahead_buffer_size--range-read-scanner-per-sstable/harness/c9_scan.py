#!/usr/bin/env python3
"""C9 scan client (design §2.5 step 5). C worker processes, each its own Cluster/Session (protocol 4),
each looping full scans `SELECT pk FROM c9.t` with fetch size 1000 (one page = one range command), logging per page.
usage: c9_scan.py --streams C --fetch 1000 --duration D --out DIR [--ramp 1,2,3,4,6,8 --step 45]
All workers connect first, then start together. With --ramp (R0), worker i starts at the first step k whose
cumulative count exceeds i; the run ends at go + duration for every worker.
Per-worker CSV DIR/w<i>.csv: ms_start,ms_end,worker,scan,page,rows,lat_ms,err"""
import argparse, glob, multiprocessing as mp, os, sys, time

CH = '/mydata/s4/cassandra-base'


def driver():
    lib = CH + '/lib'
    z = max(glob.glob(lib + '/cassandra-driver-internal-only-*.zip'))
    ver = os.path.splitext(os.path.basename(z))[0][len('cassandra-driver-internal-only-'):]
    sys.path.insert(0, os.path.join(z, 'cassandra-driver-' + ver))
    for p in ('pure_sasl-', 'wcwidth-', 'pyasyncore-'):
        zz = glob.glob(os.path.join(lib, p + '*.zip'))
        if zz:
            sys.path.insert(0, max(zz))


def worker(i, fetch, starts, end, out, ready):
    driver()
    from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
    from cassandra.policies import DCAwareRoundRobinPolicy
    from cassandra.query import SimpleStatement
    from cassandra import ConsistencyLevel
    f = open(f'{out}/w{i}.csv', 'w', buffering=1)
    f.write('ms_start,ms_end,worker,scan,page,rows,lat_ms,err\n')
    prof = ExecutionProfile(consistency_level=ConsistencyLevel.ONE, request_timeout=30,
                            load_balancing_policy=DCAwareRoundRobinPolicy(local_dc='datacenter1'))
    cl = Cluster(['127.0.0.1'], port=9042, protocol_version=4, token_metadata_enabled=False, schema_metadata_enabled=False,
                 execution_profiles={EXEC_PROFILE_DEFAULT: prof}, connect_timeout=20)
    s = None
    try:
        s = cl.connect()
    except Exception as e:
        f.write(f'{int(time.time()*1000)},{int(time.time()*1000)},{i},-1,-1,0,0,connect:{type(e).__name__}\n')
    ready.release()
    while starts[i] == 0 or time.time() < starts[i]:
        time.sleep(0.02)
    t_end = end.value
    scan = 0
    while time.time() < t_end:
        if s is None:
            time.sleep(1)
            try:
                s = cl.connect()
            except Exception as e:
                f.write(f'{int(time.time()*1000)},{int(time.time()*1000)},{i},-1,-1,0,0,connect:{type(e).__name__}\n')
            continue
        scan += 1
        page = 0
        ps = None
        while time.time() < t_end:
            st = SimpleStatement('SELECT pk FROM c9.t', fetch_size=fetch)
            t0 = time.time()
            try:
                rs = s.execute(st, paging_state=ps)
                n = len(rs.current_rows)
                t1 = time.time()
                f.write(f'{int(t0*1000)},{int(t1*1000)},{i},{scan},{page},{n},{(t1-t0)*1000:.0f},\n')
                page += 1
                ps = rs.paging_state
                if ps is None:
                    break
            except Exception as e:
                t1 = time.time()
                msg = type(e).__name__ + ':' + str(e)[:120].replace(',', ';').replace('\n', ' ')
                f.write(f'{int(t0*1000)},{int(t1*1000)},{i},{scan},{page},0,{(t1-t0)*1000:.0f},{msg}\n')
                time.sleep(0.5)
                break
    f.close()
    try:
        cl.shutdown()
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--streams', type=int, required=True)
    ap.add_argument('--fetch', type=int, default=1000)
    ap.add_argument('--duration', type=float, required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--ramp', default='')
    ap.add_argument('--step', type=float, default=45)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    ramp = [int(x) for x in a.ramp.split(',')] if a.ramp else []
    n = max(ramp) if ramp else a.streams
    ready = mp.Semaphore(0)
    starts = mp.Array('d', [0.0] * n)
    end = mp.Value('d', 0.0)
    t0 = time.time()
    procs = [mp.Process(target=worker, args=(i, a.fetch, starts, end, a.out, ready)) for i in range(n)]
    for p in procs:
        p.start()
    for _ in range(n):
        ready.acquire(timeout=120)
    go = time.time() + 1.0
    end.value = go + a.duration
    for i in range(n):
        k = next(j for j, c in enumerate(ramp) if c > i) if ramp else 0
        starts[i] = go + k * a.step
    open(f'{a.out}/client.txt', 'w').write(f'connect_s={go - t0:.1f}\ngo_ms={int(go*1000)}\nend_ms={int(end.value*1000)}\n'
                                         f'streams={n}\nramp={a.ramp}\nstep={a.step}\n')
    for p in procs:
        p.join(timeout=max(1, end.value - time.time() + 45))
    for p in procs:
        if p.is_alive():
            p.kill()


if __name__ == '__main__':
    main()
