#!/usr/bin/env python3
"""R22 stage-2 client (from R17's client.py; design §2.5). Bundled Python driver (lib/cassandra-driver-internal-only-*.zip),
protocol 4, whitelist 127.0.0.1, FallthroughRetryPolicy (no retries), CL ONE, client request timeout 60 s, token metadata off.
Optional source address (E5): the driver's socket is bound to <src> before connect.
  schema   <port>
  settings <port>                                     resolved settings from system_views.settings (JSON)
  clients  <port>                                     system_views.clients address/port counts (JSON)
  fill     <port> <arm T|C|I|D> <target_bytes> <poll.log> <batch> <inflight>
           unlogged single-partition batches of <batch> S = DELETE FROM r22.rt WHERE pk=? AND ck>4i AND ck<4i+2 (i ascending per
           partition); T/I/D pk=0; C pk = b mod 1000 round-robin; <inflight> batches outstanding. Reads K_rt from the poll log
           every 10 completed batches (above 0.9 x target waits 1.2 s for a fresh sample). Stops at K_rt >= target.
  hot      <port> <arm> <I0> <rate/s> <max_out> <burst_n> <burst_offsets_s e.g. 0,20> <maxsec> <stopfile> <csv> <resp>
           bursts of <burst_n> S at t0+offset (exempt from the caps); otherwise paced closed loop: at most <rate> issues/s
           (pacer, no catch-up beyond one slot) and only while outstanding (bursts included) < <max_out>; a slot that finds
           max_out outstanding waits. T/I/D pk=0 with fresh i >= I0; C pk = k mod 1000, i = I0 + k//1000.
  blob     <port> <src> <idx> <rate/s> <max_out> <maxsec> <stopfile> <csv> <resp>
           open loop: slot k at t0 + k/rate; a slot that finds <max_out> outstanding is skipped ('capped').
           INSERT INTO r22.blob (k, v) VALUES (idx*1e9 + seq, <12,582,912 random bytes generated once>).
  Stream modes stop at <maxsec> or when <stopfile> exists; then drain up to 35 s. Timeouts/errors counted, never retried.
  <csv>: one cumulative row per second: epoch_s,issued,capped_or_burst,ok,timeouts,errors,outstanding
  <resp>: one row per response: issue_epoch,latency_s,outcome(o=ok,t=timeout,e=error)"""
import glob, json, os, sys, threading, time

CASS = os.environ.get('CASSANDRA_HOME', '/mydata/s4/r22/cassandra')
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
from cassandra.policies import WhiteListRoundRobinPolicy, FallthroughRetryPolicy  # noqa: E402
from cassandra.query import BatchStatement, BatchType  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402
import cassandra.connection as cconn  # noqa: E402

NPART_C = 1000
BLOB = 12582912
SRC = None
_orig_init = cconn.Connection._initiate_connection


def _bound_init(self, sockaddr):
    if SRC:
        self._socket.bind((SRC, 0))
    return _orig_init(self, sockaddr)


cconn.Connection._initiate_connection = _bound_init


def connect(port, timeout=60):
    prof = ExecutionProfile(request_timeout=timeout, consistency_level=ConsistencyLevel.ONE, retry_policy=FallthroughRetryPolicy(),
                            load_balancing_policy=WhiteListRoundRobinPolicy(['127.0.0.1']))
    c = Cluster(['127.0.0.1'], port=port, protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof},
                connect_timeout=30, token_metadata_enabled=False)
    return c, c.connect()


def poll_last(path):
    try:
        with open(path, 'rb') as f:
            hdr = f.readline().decode().split()
            f.seek(0, 2)
            sz = f.tell()
            f.seek(max(0, sz - 8192))
            lines = f.read().decode(errors='replace').splitlines()
        for l in reversed(lines):
            p = l.split()
            if len(p) == len(hdr) and p[0].isdigit():
                return dict(zip(hdr, map(int, p)))
    except Exception:
        pass
    return None


def is_timeout(e):
    return 'imeout' in type(e).__name__ or 'imeout' in str(e)[:100]


class Stream:
    """shared bookkeeping of a stream process"""

    def __init__(self, csvp, respp):
        self.lock = threading.Lock()
        self.st = {'issued': 0, 'capped': 0, 'burst': 0, 'ok': 0, 'timeout': 0, 'err': 0, 'outstanding': 0, 'first_err': []}
        self.lat = {'o': [], 't': [], 'e': []}
        self.fcsv = open(csvp, 'w')
        self.fcsv.write('epoch_s,issued,capped_or_burst,ok,timeouts,errors,outstanding\n')
        self.fcsv.flush()
        self.fresp = open(respp, 'w')
        self.fresp.write('issue_epoch,latency_s,outcome\n')
        self.capcol = 'capped'

    def on_ok(self, _, ts):
        now = time.time()
        with self.lock:
            self.st['ok'] += 1
            self.st['outstanding'] -= 1
            self.lat['o'].append(now - ts)
            self.fresp.write('%.3f,%.3f,o\n' % (ts, now - ts))

    def on_err(self, e, ts):
        now = time.time()
        with self.lock:
            self.st['outstanding'] -= 1
            o = 't' if is_timeout(e) else 'e'
            self.st['timeout' if o == 't' else 'err'] += 1
            self.lat[o].append(now - ts)
            self.fresp.write('%.3f,%.3f,%s\n' % (ts, now - ts, o))
            if len(self.st['first_err']) < 3:
                self.st['first_err'].append('%s: %s' % (type(e).__name__, str(e)[:200]))

    def row(self):
        with self.lock:
            s = self.st
            self.fcsv.write('%d,%d,%d,%d,%d,%d,%d\n' % (int(time.time()), s['issued'], s[self.capcol], s['ok'], s['timeout'], s['err'], s['outstanding']))
        self.fcsv.flush()
        self.fresp.flush()

    def send(self, s, ps, a):
        ts = time.time()
        try:
            f = s.execute_async(ps, a)
            f.add_callbacks(callback=self.on_ok, errback=self.on_err, callback_args=(ts,), errback_args=(ts,))
        except Exception as e:
            self.on_err(e, ts)

    def drain(self, last_row):
        t_stop = time.time()
        while time.time() - t_stop < 35:
            with self.lock:
                if self.st['outstanding'] == 0:
                    break
            if int(time.time()) > last_row:
                last_row = int(time.time())
                self.row()
            time.sleep(0.2)
        self.row()
        self.fcsv.close()
        with self.lock:
            self.fresp.close()

    def summary(self, extra, el):
        def q(ls, f):
            return round(ls[min(len(ls) - 1, int(f * len(ls)))] * 1000, 1) if ls else None
        out = dict(extra)
        s = self.st
        out.update({'issued': s['issued'], 'capped': s['capped'], 'burst': s['burst'], 'ok': s['ok'], 'timeouts': s['timeout'],
                    'errors': s['err'], 'outstanding_after_drain': s['outstanding'], 'seconds': round(el, 1),
                    'ok_per_s': round(s['ok'] / el, 2) if el else None, 'first_errors': s['first_err']})
        for o, name in (('o', 'ok'), ('t', 'timeout'), ('e', 'error')):
            ls = sorted(self.lat[o])
            out['lat_%s_ms' % name] = {'p50': q(ls, 0.5), 'p99': q(ls, 0.99), 'max': q(ls, 1.0)}
        return out


def main():
    global SRC
    mode, port = sys.argv[1], int(sys.argv[2])
    if mode == 'blob':
        SRC = sys.argv[3]
    c, s = connect(port)
    if mode == 'schema':
        s.execute("CREATE KEYSPACE IF NOT EXISTS r22 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
        s.execute('CREATE TABLE IF NOT EXISTS r22.rt (pk int, ck int, v int, PRIMARY KEY (pk, ck))')
        s.execute('CREATE TABLE IF NOT EXISTS r22.blob (k bigint PRIMARY KEY, v blob)')
        print(json.dumps({'schema': 'ok'}))
    elif mode == 'settings':
        names = ['memtable_heap_space', 'memtable_offheap_space', 'memtable_cleanup_threshold', 'memtable_flush_writers',
                 'concurrent_writes', 'range_tombstone_list_growth_factor', 'initial_range_tombstone_list_allocation_size',
                 'memtable_allocation_type', 'max_mutation_size', 'native_transport_max_request_data_in_flight',
                 'native_transport_max_request_data_in_flight_per_ip', 'write_request_timeout', 'native_transport_timeout',
                 'native_transport_max_threads', 'native_transport_max_frame_size', 'commitlog_segment_size',
                 'commitlog_total_space', 'hinted_handoff_enabled', 'enforce_native_deadline_for_hints', 'cql_start_time',
                 'key_cache_size', 'counter_cache_size', 'row_cache_size', 'column_value_size_warn_threshold',
                 'column_value_size_fail_threshold', 'memtable', 'native_transport_max_concurrent_requests_in_bytes',
                 'native_transport_rate_limiting_enabled', 'max_hints_delivery_threads', 'max_hint_window',
                 'compaction_throughput', 'native_transport_max_request_data_in_flight_per_ip', 'max_hints_size_per_host']
        out = {}
        for r in s.execute('SELECT name, value FROM system_views.settings'):
            if r.name in names:
                out[r.name] = r.value
        print(json.dumps(out, sort_keys=True))
    elif mode == 'clients':
        out = {}
        for r in s.execute('SELECT address, port, username FROM system_views.clients'):
            out[str(r.address)] = out.get(str(r.address), 0) + 1
        print(json.dumps({'clients_by_address': out}, sort_keys=True))
    elif mode == 'fill':
        arm, target, poll, batch, inflight = sys.argv[3], int(sys.argv[4]), sys.argv[5], int(sys.argv[6]), int(sys.argv[7])
        ps = s.prepare('DELETE FROM r22.rt WHERE pk = ? AND ck > ? AND ck < ?')
        cnt = {}
        sem = threading.Semaphore(inflight)
        lock = threading.Lock()
        done = [0, 0]  # completed, errors
        errs = []

        def fin(_r=None):
            with lock:
                done[0] += 1
            sem.release()

        def ferr(e):
            with lock:
                done[0] += 1
                done[1] += 1
                if len(errs) < 3:
                    errs.append('%s: %s' % (type(e).__name__, str(e)[:200]))
            sem.release()

        b = 0
        t0 = time.time()
        k = 0
        last_check = 0
        while True:
            pk = 0 if arm != 'C' else b % NPART_C
            i0 = cnt.get(pk, 0)
            bs = BatchStatement(batch_type=BatchType.UNLOGGED)
            for i in range(i0, i0 + batch):
                bs.add(ps, (pk, 4 * i, 4 * i + 2))
            sem.acquire()
            f = s.execute_async(bs)
            f.add_callbacks(callback=fin, errback=ferr)
            cnt[pk] = i0 + batch
            b += 1
            with lock:
                d = done[0]
            if d - last_check >= 10:
                last_check = d
                if k >= 0.9 * target:
                    for _ in range(inflight):
                        sem.acquire()
                    for _ in range(inflight):
                        sem.release()
                    time.sleep(1.2)
                p = poll_last(poll)
                if p is not None:
                    k = p['K_rt']
                    if p['sw_rt'] > 0:
                        print(json.dumps({'error': 'flush during fill', 'batches': b, 'K': k}))
                        sys.exit(2)
                if k >= target:
                    break
            if time.time() - t0 > 1200:
                print(json.dumps({'error': 'fill timeout', 'batches': b, 'K': k}))
                sys.exit(3)
        for _ in range(inflight):
            sem.acquire()
        time.sleep(1.5)
        p = poll_last(poll)
        tomb = sum(cnt.values())
        print(json.dumps({'batches': b, 'batch': batch, 'inflight': inflight, 'batch_errors': done[1], 'first_errors': errs,
                          'tombstones': tomb, 'partitions': len(cnt), 'n_per_partition_max': max(cnt.values()),
                          'I0': max(cnt.values()), 'target': target, 'K_at_stop': k, 'K_after': p['K_rt'] if p else None,
                          'K_per_tombstone': round(p['K_rt'] / tomb, 1) if p else None,
                          'switch': p['sw_rt'] if p else None, 'seconds': round(time.time() - t0, 1)}))
    elif mode == 'hot':
        arm, I0, rate, maxout, burst_n = sys.argv[3], int(sys.argv[4]), float(sys.argv[5]), int(sys.argv[6]), int(sys.argv[7])
        offs = [float(x) for x in sys.argv[8].split(',') if x != '']
        maxsec, stopf, csvp, respp = float(sys.argv[9]), sys.argv[10], sys.argv[11], sys.argv[12]
        ps = s.prepare('DELETE FROM r22.rt WHERE pk = ? AND ck > ? AND ck < ?')
        S = Stream(csvp, respp)
        S.capcol = 'burst'

        def args(kk):
            if arm == 'C':
                return (kk % NPART_C, 4 * (I0 + kk // NPART_C), 4 * (I0 + kk // NPART_C) + 2)
            return (0, 4 * (I0 + kk), 4 * (I0 + kk) + 2)

        def take(is_burst):
            with S.lock:
                kk = S.st['issued']
                S.st['issued'] += 1
                S.st['outstanding'] += 1
                if is_burst:
                    S.st['burst'] += 1
            return kk

        t0 = time.time()
        nxt = t0
        bi = 0
        last_row = int(t0)
        why = 'maxsec'
        while True:
            now = time.time()
            if now - t0 > maxsec:
                break
            if os.path.exists(stopf):
                why = 'stopfile'
                break
            while bi < len(offs) and now - t0 >= offs[bi]:
                for _ in range(burst_n):
                    S.send(s, ps, args(take(True)))
                bi += 1
            if now >= nxt:
                with S.lock:
                    room = S.st['outstanding'] < maxout
                if room:
                    if nxt < now - 1.0 / rate:
                        nxt = now
                    S.send(s, ps, args(take(False)))
                    nxt += 1.0 / rate
            if int(now) > last_row:
                last_row = int(now)
                S.row()
            time.sleep(0.002)
        el = time.time() - t0
        S.drain(last_row)
        print(json.dumps(S.summary({'kind': 'hot', 'stop': why, 'rate': rate, 'max_out': maxout, 'burst_n': burst_n, 'bursts_at': offs}, el)))
    elif mode == 'blob':
        idx, rate, maxout, maxsec, stopf, csvp, respp = (int(sys.argv[4]), float(sys.argv[5]), int(sys.argv[6]), float(sys.argv[7]),
                                                         sys.argv[8], sys.argv[9], sys.argv[10])
        ps = s.prepare('INSERT INTO r22.blob (k, v) VALUES (?, ?)')
        val = os.urandom(BLOB)
        S = Stream(csvp, respp)
        t0 = time.time()
        slot = 0
        last_row = int(t0)
        why = 'maxsec'
        while True:
            now = time.time()
            if now - t0 > maxsec:
                break
            if os.path.exists(stopf):
                why = 'stopfile'
                break
            while slot <= (now - t0) * rate:
                with S.lock:
                    full = S.st['outstanding'] >= maxout
                    if full:
                        S.st['capped'] += 1
                    else:
                        kk = S.st['issued']
                        S.st['issued'] += 1
                        S.st['outstanding'] += 1
                slot += 1
                if not full:
                    S.send(s, ps, (idx * 1000000000 + kk, val))
            if int(now) > last_row:
                last_row = int(now)
                S.row()
            time.sleep(0.005)
        el = time.time() - t0
        S.drain(last_row)
        print(json.dumps(S.summary({'kind': 'blob', 'src': SRC, 'idx': idx, 'stop': why, 'rate': rate, 'max_out': maxout}, el)))
    c.shutdown()


main()
