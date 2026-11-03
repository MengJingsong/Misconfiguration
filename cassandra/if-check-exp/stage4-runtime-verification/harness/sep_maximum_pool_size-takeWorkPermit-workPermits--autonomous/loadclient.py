#!/usr/bin/env python3
"""B3c (amended 2026-10-26) of sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous: closed-loop count(*) client.
usage: loadclient.py <driver zip> count
       loadclient.py <driver zip> run <nproc> <perproc> <secs> <outdir>
       loadclient.py <driver zip> worker <perproc> <t_start_ms> <t_end_ms> <outfile>
run: nproc worker processes start together at a common epoch (launch + 8 s); each keeps <perproc> queries
     'SELECT count(*) FROM keyspace1.standard1' in flight until t_end, re-firing from the completion callback;
     after t_end it waits for its outstanding queries (at most 330 s).
Bundled driver (protocol 5), DCAwareRoundRobinPolicy, token_metadata_enabled=False, schema_metadata_enabled=False,
CL ONE, request timeout 300 s, FallthroughRetryPolicy.
Runbook fix 2026-10-26 (defect 4): idle_heartbeat_interval=0. The driver's 30 s heartbeat (an OPTIONS request) waits in
the same NTR queue as the count(*) queries; at knob 16 the queue wait exceeded the 30 s heartbeat timeout, the driver
closed the connection and failed its 100 queries, and Cluster.shutdown() then blocked for about 100 s. A rebuild now
shuts the old cluster down in a daemon thread (at most 5 s), and the 'inflight' lines come from a separate reporter thread.
Per worker: <outfile>.lines with 'q t0= t1= outcome=OK count=<n>' or 'q t0= t1= outcome=ERR cls= msg=',
'inflight t=<ms> n=<k>' once a second, 'reconnect t=<ms> after=<cls>'; <outfile>.json with totals.
On an error the query is re-fired after 0.2 s; on a connection-level error the session is rebuilt.
"""
import json, os, subprocess, sys, threading, time
_zip = sys.argv[1]
_ver = os.path.splitext(os.path.basename(_zip))[0][len('cassandra-driver-internal-only-'):]
sys.path.insert(0, os.path.join(_zip, 'cassandra-driver-' + _ver))
from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402
from cassandra.policies import DCAwareRoundRobinPolicy, FallthroughRetryPolicy  # noqa: E402
from cassandra.query import SimpleStatement  # noqa: E402

MODE = sys.argv[2]
ARGS = sys.argv[3:]
Q = 'SELECT count(*) FROM keyspace1.standard1'
CONN_ERR = ('ConnectionShutdown', 'NoHostAvailable', 'OperationTimedOut', 'ConnectionException', 'ConnectionBusy')


def ms():
    return int(time.time() * 1000)


def session():
    prof = ExecutionProfile(load_balancing_policy=DCAwareRoundRobinPolicy(), request_timeout=300,
                            consistency_level=ConsistencyLevel.ONE, retry_policy=FallthroughRetryPolicy())
    c = Cluster(['127.0.0.1'], protocol_version=5, token_metadata_enabled=False, schema_metadata_enabled=False,
                execution_profiles={EXEC_PROFILE_DEFAULT: prof}, idle_heartbeat_interval=0)
    return c, c.connect()


class Worker(object):
    def __init__(self, perproc, t_start, t_end, outfile):
        self.perproc, self.t_start, self.t_end = perproc, t_start, t_end
        self.f = open(outfile + '.lines', 'w')
        self.outfile = outfile
        self.lock = threading.Lock()
        self.inflight = 0
        self.broken = False
        self.retry_at = 0
        self.cnt = {'queries': 0, 'ok': 0, 'err': 0, 'reconnects': 0, 'fired': 0}
        self.errs = {}
        self.inflight_samples = []
        self.c, self.s = session()
        self.stmt = SimpleStatement(Q)

    def write(self, line):
        with self.lock:
            self.f.write(line + '\n')

    def fire(self):
        with self.lock:
            if self.broken or ms() >= self.t_end or self.inflight >= self.perproc or ms() < self.retry_at:
                return False
            self.inflight += 1
            self.cnt['fired'] += 1
            s = self.s
        t0 = ms()
        try:
            fut = s.execute_async(self.stmt, timeout=300)
            fut.add_callbacks(self.ok, self.err, callback_args=(t0,), errback_args=(t0,))
        except Exception as e:  # noqa: BLE001
            self.err(e, t0)
        return True

    def ok(self, rows, t0):
        n = rows[0][0] if rows else -1
        with self.lock:
            self.inflight -= 1
            self.cnt['ok'] += 1
            self.cnt['queries'] += 1
            self.f.write('q t0=%d t1=%d outcome=OK count=%d\n' % (t0, ms(), n))
        self.fire()

    def err(self, e, t0):
        cls = type(e).__name__
        msg = str(e).replace('\n', ' ')[:200]
        with self.lock:
            self.inflight -= 1
            self.cnt['err'] += 1
            self.cnt['queries'] += 1
            self.errs[cls] = self.errs.get(cls, 0) + 1
            self.f.write('q t0=%d t1=%d outcome=ERR cls=%s msg=%s\n' % (t0, ms(), cls, msg))
            self.retry_at = ms() + 200
            if cls in CONN_ERR:
                self.broken = True

    def rebuild(self, why):
        old = self.c

        def _shut():
            try:
                old.shutdown()
            except Exception:  # noqa: BLE001
                pass
        th = threading.Thread(target=_shut)
        th.daemon = True
        th.start()
        th.join(5.0)
        time.sleep(0.2)
        while True:
            try:
                self.c, self.s = session()
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.5)
        with self.lock:
            self.broken = False
            self.cnt['reconnects'] += 1
            self.f.write('reconnect t=%d after=%s\n' % (ms(), why))

    def reporter(self):
        nxt = self.t_start
        while ms() < self.t_end:
            now = ms()
            if now >= nxt:
                with self.lock:
                    n = self.inflight
                    self.f.write('inflight t=%d n=%d\n' % (now, n))
                self.inflight_samples.append(n)
                nxt += 1000
            time.sleep(0.02)

    def main(self):
        while ms() < self.t_start:
            time.sleep(0.005)
        rep = threading.Thread(target=self.reporter)
        rep.daemon = True
        rep.start()
        last = self.t_end
        while ms() < self.t_end:
            if self.broken:
                with self.lock:
                    # queries of the broken session will not complete; forget them
                    self.inflight = 0
                self.rebuild('conn-error')
            while self.fire():
                pass
            time.sleep(0.05)
        rep.join(2.0)
        wait_until = ms() + 330000
        while ms() < wait_until:
            with self.lock:
                n = self.inflight
            if n <= 0 or self.broken:
                break
            now = ms()
            if now - last >= 1000:
                self.write('inflight t=%d n=%d drain' % (now, n))
                last = now
            time.sleep(0.05)
        with self.lock:
            left = self.inflight
        out = dict(self.cnt)
        out['left_inflight'] = left
        out['errors_by_class'] = self.errs
        xs = sorted(self.inflight_samples)
        out['inflight_median'] = xs[len(xs) // 2] if xs else 0
        out['inflight_min'] = xs[0] if xs else 0
        out['inflight_lines'] = len(xs)
        out['t_start'] = self.t_start
        out['t_end'] = self.t_end
        out['returned'] = ms()
        self.f.close()
        json.dump(out, open(self.outfile + '.json', 'w'))
        try:
            self.c.shutdown()
        except Exception:  # noqa: BLE001
            pass
        return 0


def main():
    if MODE == 'count':
        c, s = session()
        try:
            r = s.execute(SimpleStatement(Q), timeout=300)
            print('COUNT %d' % r.one()[0])
        finally:
            c.shutdown()
        return 0
    if MODE == 'run':
        nproc, perproc, secs, outdir = int(ARGS[0]), int(ARGS[1]), int(ARGS[2]), ARGS[3]
        os.makedirs(outdir, exist_ok=True)
        t_start = ms() + 8000
        t_end = t_start + secs * 1000
        json.dump({'nproc': nproc, 'perproc': perproc, 'secs': secs, 't_start': t_start, 't_end': t_end},
                  open(os.path.join(outdir, 'phase.json'), 'w'))
        procs = [subprocess.Popen([sys.executable, os.path.abspath(__file__), _zip, 'worker', str(perproc), str(t_start),
                                   str(t_end), os.path.join(outdir, 'w%02d' % i)]) for i in range(nproc)]
        rcs = [p.wait() for p in procs]
        tot = {}
        for i in range(nproc):
            try:
                w = json.load(open(os.path.join(outdir, 'w%02d.json' % i)))
            except Exception:  # noqa: BLE001
                w = {'missing': 1}
            for k, v in w.items():
                if isinstance(v, int) and k not in ('t_start', 't_end', 'returned'):
                    tot[k] = tot.get(k, 0) + v
        d = json.load(open(os.path.join(outdir, 'phase.json')))
        d.update({'rcs': rcs, 'returned': ms(), 'totals': tot})
        json.dump(d, open(os.path.join(outdir, 'phase.json'), 'w'))
        print('RUN nproc=%d perproc=%d secs=%d rcs=%s totals=%s' % (nproc, perproc, secs, rcs, json.dumps(tot, sort_keys=True)))
        return 0 if all(r == 0 for r in rcs) else 1
    if MODE == 'worker':
        return Worker(int(ARGS[0]), int(ARGS[1]), int(ARGS[2]), ARGS[3]).main()
    print('unknown mode ' + MODE)
    return 2


if __name__ == '__main__':
    sys.exit(main())
