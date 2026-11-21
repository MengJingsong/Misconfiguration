#!/usr/bin/env python3
"""R17 stage-2 client (from U11's client.py). Bundled Python driver (lib/cassandra-driver-internal-only-*.zip), protocol 4,
whitelist 127.0.0.1, FallthroughRetryPolicy (no retries), CL ONE, client request timeout 30 s, token metadata off.
  schema   <port>
  settings <port>                                         resolved settings from system_views.settings (JSON)
  fill     <port> <arm T|C|I|D> <target_bytes> <poll.log> <batch>
           unlogged single-partition batches of <batch> S = DELETE FROM r17.rt WHERE pk=? AND ck>4i AND ck<4i+2 (i ascending
           per partition); T/I/D pk=0; C pk = b mod 1000 round-robin. Reads K_rt from the poll log's last line every 10
           batches; above 0.9 x target it waits 1.2 s for a fresh sample after every 10 batches. Stops at K_rt >= target.
  stream   <port> <hot|blob> <arm> <I0> <rate/s> <max_outstanding> <maxsec> <stopfile> <csv>
           open loop: issue slot k at t0 + k/rate; a slot that finds <max_outstanding> outstanding is skipped ('capped').
           hot: S with fresh ascending i >= I0 (T/I/D pk=0; C pk = k mod 1000, i = I0 + k//1000).
           blob: INSERT INTO r17.blob (k, v) VALUES (k, <4,194,304 random bytes generated once>), k = 0,1,2...
           Stops at <maxsec> or when <stopfile> exists; then drains up to 35 s. Timeouts/errors counted, never retried.
           <csv>: one cumulative row per second (written live): epoch_s,issued,capped,ok,timeouts,errors,outstanding
  closed   <port> <arm> <I0> <inflight> <maxsec> <poll.log> <csv>
           U11's write mode (S512 arms): hot S only, <inflight> outstanding closed loop, stops at maxsec or a K_rt switch."""
import glob, json, os, sys, threading, time

CASS = os.environ.get('CASSANDRA_HOME', '/mydata/s4/r17/cassandra')
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

NPART_C = 1000
BLOB = 4194304


def connect(port, timeout=30):
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


def main():
    mode, port = sys.argv[1], int(sys.argv[2])
    c, s = connect(port)
    if mode == 'schema':
        s.execute("CREATE KEYSPACE IF NOT EXISTS r17 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
        s.execute('CREATE TABLE IF NOT EXISTS r17.rt (pk int, ck int, v int, PRIMARY KEY (pk, ck))')
        s.execute('CREATE TABLE IF NOT EXISTS r17.blob (k bigint PRIMARY KEY, v blob)')
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
                 'native_transport_rate_limiting_enabled', 'max_hints_delivery_threads', 'max_hint_window']
        out = {}
        for r in s.execute('SELECT name, value FROM system_views.settings'):
            if r.name in names:
                out[r.name] = r.value
        print(json.dumps(out, sort_keys=True))
    elif mode == 'fill':
        arm, target, poll, batch = sys.argv[3], int(sys.argv[4]), sys.argv[5], int(sys.argv[6])
        ps = s.prepare('DELETE FROM r17.rt WHERE pk = ? AND ck > ? AND ck < ?')
        cnt = {}
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
            s.execute(bs)
            cnt[pk] = i0 + batch
            b += 1
            if b - last_check >= 10:
                last_check = b
                if k >= 0.9 * target:
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
        time.sleep(1.5)
        p = poll_last(poll)
        tomb = sum(cnt.values())
        print(json.dumps({'batches': b, 'batch': batch, 'tombstones': tomb, 'partitions': len(cnt), 'n_per_partition_max': max(cnt.values()),
                          'I0': max(cnt.values()), 'target': target, 'K_at_stop': k, 'K_after': p['K_rt'] if p else None,
                          'K_per_tombstone': round(p['K_rt'] / tomb, 1) if p else None,
                          'switch': p['sw_rt'] if p else None, 'seconds': round(time.time() - t0, 1)}))
    elif mode == 'stream':
        kind, arm, I0, rate, maxout, maxsec, stopf, csvp = (sys.argv[3], sys.argv[4], int(sys.argv[5]), float(sys.argv[6]),
                                                            int(sys.argv[7]), float(sys.argv[8]), sys.argv[9], sys.argv[10])
        if kind == 'hot':
            ps = s.prepare('DELETE FROM r17.rt WHERE pk = ? AND ck > ? AND ck < ?')
        else:
            ps = s.prepare('INSERT INTO r17.blob (k, v) VALUES (?, ?)')
            val = os.urandom(BLOB)
        lock = threading.Lock()
        st = {'issued': 0, 'capped': 0, 'ok': 0, 'timeout': 0, 'err': 0, 'outstanding': 0, 'first_err': []}
        lat = []

        def args(kk):
            if kind == 'blob':
                return (kk, val)
            if arm == 'C':
                return (kk % NPART_C, 4 * (I0 + kk // NPART_C), 4 * (I0 + kk // NPART_C) + 2)
            return (0, 4 * (I0 + kk), 4 * (I0 + kk) + 2)

        def on_ok(_, ts):
            now = time.time()
            with lock:
                st['ok'] += 1
                st['outstanding'] -= 1
                lat.append(now - ts)

        def on_err(e, ts):
            with lock:
                st['outstanding'] -= 1
                if is_timeout(e):
                    st['timeout'] += 1
                else:
                    st['err'] += 1
                if len(st['first_err']) < 3:
                    st['first_err'].append('%s: %s' % (type(e).__name__, str(e)[:200]))

        fcsv = open(csvp, 'w')
        fcsv.write('epoch_s,issued,capped,ok,timeouts,errors,outstanding\n')
        fcsv.flush()

        def row():
            with lock:
                fcsv.write('%d,%d,%d,%d,%d,%d,%d\n' % (int(time.time()), st['issued'], st['capped'], st['ok'], st['timeout'], st['err'], st['outstanding']))
            fcsv.flush()

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
                with lock:
                    full = st['outstanding'] >= maxout
                    if full:
                        st['capped'] += 1
                    else:
                        kk = st['issued']
                        st['issued'] += 1
                        st['outstanding'] += 1
                slot += 1
                if not full:
                    ts = time.time()
                    try:
                        f = s.execute_async(ps, args(kk))
                        f.add_callbacks(callback=on_ok, errback=on_err, callback_args=(ts,), errback_args=(ts,))
                    except Exception as e:  # synchronous failure (e.g. node gone): counted as an error
                        on_err(e, ts)
            if int(now) > last_row:
                last_row = int(now)
                row()
            time.sleep(0.005)
        t_stop = time.time()
        while time.time() - t_stop < 35:
            with lock:
                if st['outstanding'] == 0:
                    break
            if int(time.time()) > last_row:
                last_row = int(time.time())
                row()
            time.sleep(0.2)
        row()
        fcsv.close()
        el = t_stop - t0
        ls = sorted(lat)

        def q(f):
            return round(ls[min(len(ls) - 1, int(f * len(ls)))] * 1000, 1) if ls else None
        print(json.dumps({'kind': kind, 'stop': why, 'issued': st['issued'], 'capped': st['capped'], 'ok': st['ok'], 'timeouts': st['timeout'],
                          'errors': st['err'], 'outstanding_after_drain': st['outstanding'], 'seconds': round(el, 1),
                          'ok_per_s': round(st['ok'] / el, 2) if el else None, 'p50_ms': q(0.5), 'p99_ms': q(0.99), 'max_ms': q(1.0),
                          'first_errors': st['first_err']}))
    elif mode == 'closed':
        arm, I0, inflight, maxsec, poll, csvp = sys.argv[3], int(sys.argv[4]), int(sys.argv[5]), float(sys.argv[6]), sys.argv[7], sys.argv[8]
        ps = s.prepare('DELETE FROM r17.rt WHERE pk = ? AND ck > ? AND ck < ?')
        lock = threading.Lock()
        st = {'issued': 0, 'ok': 0, 'timeout': 0, 'err': 0, 'outstanding': 0, 'stop': False, 'first_err': []}
        lat = []
        sec = {}

        def stmt(kk):
            if arm == 'C':
                return (kk % NPART_C, 4 * (I0 + kk // NPART_C), 4 * (I0 + kk // NPART_C) + 2)
            return (0, 4 * (I0 + kk), 4 * (I0 + kk) + 2)

        def issue():
            with lock:
                if st['stop']:
                    return
                kk = st['issued']
                st['issued'] += 1
                st['outstanding'] += 1
            ts = time.time()
            f = s.execute_async(ps, stmt(kk))
            f.add_callbacks(callback=on_ok, errback=on_err, callback_args=(ts,), errback_args=(ts,))

        def on_ok(_, ts):
            now = time.time()
            with lock:
                st['ok'] += 1
                st['outstanding'] -= 1
                lat.append(now - ts)
                sec.setdefault(int(now), [0, 0, 0])[0] += 1
            issue()

        def on_err(e, ts):
            now = time.time()
            with lock:
                st['outstanding'] -= 1
                if is_timeout(e):
                    st['timeout'] += 1
                    sec.setdefault(int(now), [0, 0, 0])[1] += 1
                else:
                    st['err'] += 1
                    sec.setdefault(int(now), [0, 0, 0])[2] += 1
                if len(st['first_err']) < 3:
                    st['first_err'].append('%s: %s' % (type(e).__name__, str(e)[:200]))
            issue()

        p0 = poll_last(poll)
        sw0 = p0['sw_rt'] if p0 else 0
        t0 = time.time()
        for _ in range(inflight):
            issue()
        why = 'maxsec'
        while True:
            time.sleep(1)
            if time.time() - t0 > maxsec:
                break
            p = poll_last(poll)
            if p is not None and p['sw_rt'] > sw0:
                why = 'memtable switch'
                break
            try:
                stale = time.time() - os.path.getmtime(poll)
            except OSError:
                stale = 99
            if stale > 6:
                why = 'poll stale %.0fs (node down?)' % stale
                break
        with lock:
            st['stop'] = True
        t_stop = time.time()
        while time.time() - t_stop < 40:
            with lock:
                if st['outstanding'] == 0:
                    break
            time.sleep(0.5)
        el = t_stop - t0
        ls = sorted(lat)

        def q(f):
            return round(ls[min(len(ls) - 1, int(f * len(ls)))] * 1000, 1) if ls else None
        with open(csvp, 'w') as f:
            f.write('epoch_s,ok,timeouts,errors\n')
            for k2 in sorted(sec):
                f.write('%d,%d,%d,%d\n' % (k2, *sec[k2]))
        print(json.dumps({'stop': why, 'ok': st['ok'], 'timeouts': st['timeout'], 'errors': st['err'], 'issued': st['issued'],
                          'outstanding_after_drain': st['outstanding'], 'seconds': round(el, 1), 'rate_per_s': round(st['ok'] / el, 1) if el else None,
                          'p50_ms': q(0.5), 'p99_ms': q(0.99), 'max_ms': q(1.0), 'first_errors': st['first_err']}))
    c.shutdown()


main()
