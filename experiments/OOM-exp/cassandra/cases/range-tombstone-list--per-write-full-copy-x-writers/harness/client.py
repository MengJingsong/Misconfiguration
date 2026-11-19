#!/usr/bin/env python3
"""U11 stage-2 client. Bundled Python driver (lib/cassandra-driver-internal-only-*.zip), protocol 4, whitelist 127.0.0.1,
FallthroughRetryPolicy, CL ONE, request timeout 30 s, token metadata off (one node). One JSON object on stdout per mode.
  schema   <port>
  settings <port>                                 resolved settings from system_views.settings
  fill     <port> <arm T|C|I|D> <target_bytes> <poll.log>
           unlogged batches of 100 S = DELETE ... WHERE pk=? AND ck>4i AND ck<4i+2 (i ascending per partition);
           T/I/D: pk=0; C: pk = b mod 1000 round-robin. Reads K (MemtableOnHeapDataSize) from the poll log's last line
           every 50 batches (every 5 once K > 0.75 target); stops at K >= target.
  write    <port> <arm> <I0> <count> <inflight> <maxsec> <poll.log> <persec.csv>
           single-statement S with fresh ascending i >= I0, kept at <inflight> outstanding; T/I/D pk=0, C pk = k mod 1000
           with i = I0 + k//1000. Stops at <count> acknowledged, <maxsec>, or when MemtableSwitchCount rises.
           Timeouts/errors are counted, not retried."""
import glob, json, os, sys, threading, time

CASS = os.environ.get('CASSANDRA_HOME', '/mydata/s4/u11-w4/cassandra')
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


def connect(port, timeout=30):
    prof = ExecutionProfile(request_timeout=timeout, consistency_level=ConsistencyLevel.ONE, retry_policy=FallthroughRetryPolicy(),
                            load_balancing_policy=WhiteListRoundRobinPolicy(['127.0.0.1']))
    c = Cluster(['127.0.0.1'], port=port, protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof},
                connect_timeout=30, token_metadata_enabled=False)
    return c, c.connect()


def poll_last(path):
    """last complete poll line as a dict"""
    try:
        with open(path, 'rb') as f:
            hdr = f.readline().decode().split()
            f.seek(0, 2)
            sz = f.tell()
            f.seek(max(0, sz - 4096))
            lines = f.read().decode(errors='replace').splitlines()
        for l in reversed(lines):
            p = l.split()
            if len(p) == len(hdr) and p[0].isdigit():
                return dict(zip(hdr, map(int, p)))
    except Exception:
        pass
    return None


def main():
    mode, port = sys.argv[1], int(sys.argv[2])
    c, s = connect(port)
    if mode == 'schema':
        s.execute("CREATE KEYSPACE IF NOT EXISTS u11 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
        s.execute('CREATE TABLE IF NOT EXISTS u11.rt (pk int, ck int, v int, PRIMARY KEY (pk, ck))')
        print(json.dumps({'schema': 'ok'}))
    elif mode == 'settings':
        names = ['memtable_heap_space', 'memtable_offheap_space', 'memtable_cleanup_threshold', 'memtable_flush_writers',
                 'concurrent_writes', 'range_tombstone_list_growth_factor', 'initial_range_tombstone_list_allocation_size',
                 'memtable_allocation_type', 'max_mutation_size', 'native_transport_max_request_data_in_flight',
                 'native_transport_max_request_data_in_flight_per_ip', 'write_request_timeout', 'native_transport_timeout',
                 'key_cache_size', 'commitlog_segment_size']
        out = {}
        for r in s.execute('SELECT name, value FROM system_views.settings'):
            if r.name in names:
                out[r.name] = r.value
        print(json.dumps(out))
    elif mode == 'fill':
        arm, target, poll = sys.argv[3], int(sys.argv[4]), sys.argv[5]
        ps = s.prepare('DELETE FROM u11.rt WHERE pk = ? AND ck > ? AND ck < ?')
        cnt = {}
        b = 0
        t0 = time.time()
        k = 0
        last_check = 0
        while True:
            pk = 0 if arm != 'C' else b % NPART_C
            i0 = cnt.get(pk, 0)
            bs = BatchStatement(batch_type=BatchType.UNLOGGED)
            for i in range(i0, i0 + 100):
                bs.add(ps, (pk, 4 * i, 4 * i + 2))
            s.execute(bs)
            cnt[pk] = i0 + 100
            b += 1
            step = 50 if k < 0.75 * target else 5
            if b - last_check >= step:
                last_check = b
                p = poll_last(poll)
                if p is not None:
                    k = p['K_table']
                    if p['switch'] > 0:
                        print(json.dumps({'error': 'flush during fill', 'batches': b, 'K': k}))
                        sys.exit(2)
                if k >= target:
                    break
            if time.time() - t0 > 1200:
                print(json.dumps({'error': 'fill timeout', 'batches': b, 'K': k}))
                sys.exit(3)
        time.sleep(1.5)
        p = poll_last(poll)
        print(json.dumps({'batches': b, 'tombstones': sum(cnt.values()), 'partitions': len(cnt), 'n_per_partition_max': max(cnt.values()),
                          'I0': max(cnt.values()), 'K_at_stop': k, 'K_after': p['K_table'] if p else None,
                          'switch': p['switch'] if p else None, 'seconds': round(time.time() - t0, 1)}))
    elif mode == 'write':
        arm, I0, count, inflight, maxsec, poll, csvp = sys.argv[3], int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6]), float(sys.argv[7]), sys.argv[8], sys.argv[9]
        ps = s.prepare('DELETE FROM u11.rt WHERE pk = ? AND ck > ? AND ck < ?')
        lock = threading.Lock()
        st = {'issued': 0, 'ok': 0, 'timeout': 0, 'err': 0, 'outstanding': 0, 'stop': False, 'first_err': []}
        lat = []          # (t_done, latency) per ack
        sec = {}          # second -> [ok, timeouts, errors]

        def stmt(kk):
            if arm == 'C':
                pk = kk % NPART_C
                i = I0 + kk // NPART_C
            else:
                pk, i = 0, I0 + kk
            return (pk, 4 * i, 4 * i + 2)

        def issue():
            with lock:
                if st['stop'] or st['issued'] >= count + 10 * inflight or st['ok'] >= count:
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
                lat.append((now, now - ts))
                sec.setdefault(int(now), [0, 0, 0])[0] += 1
            issue()

        def on_err(e, ts):
            now = time.time()
            with lock:
                st['outstanding'] -= 1
                if 'imeout' in type(e).__name__ or 'imeout' in str(e)[:100]:
                    st['timeout'] += 1
                    sec.setdefault(int(now), [0, 0, 0])[1] += 1
                else:
                    st['err'] += 1
                    sec.setdefault(int(now), [0, 0, 0])[2] += 1
                if len(st['first_err']) < 3:
                    st['first_err'].append('%s: %s' % (type(e).__name__, str(e)[:200]))
            issue()

        p0 = poll_last(poll)
        sw0 = p0['switch'] if p0 else 0
        t0 = time.time()
        for _ in range(inflight):
            issue()
        why = 'count'
        while True:
            time.sleep(1)
            with lock:
                okn, out = st['ok'], st['outstanding']
            if okn >= count:
                why = 'count'
                break
            if time.time() - t0 > maxsec:
                why = 'maxsec'
                break
            p = poll_last(poll)
            if p is not None and p['switch'] > sw0:
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
        ls = sorted(x[1] for x in lat)

        def q(f):
            return round(ls[min(len(ls) - 1, int(f * len(ls)))] * 1000, 1) if ls else None
        with open(csvp, 'w') as f:
            f.write('epoch_s,ok,timeouts,errors\n')
            for k2 in sorted(sec):
                f.write('%d,%d,%d,%d\n' % (k2, *sec[k2]))
        print(json.dumps({'stop': why, 'ok': st['ok'], 'timeouts': st['timeout'], 'errors': st['err'], 'issued': st['issued'],
                          'outstanding_after_drain': st['outstanding'], 'seconds': round(el, 1), 'rate_per_s': round(st['ok'] / el, 1) if el else None,
                          'p50_ms': q(0.5), 'p99_ms': q(0.99), 'max_ms': q(1.0), 'first_errors': st['first_err'],
                          'I_max': I0 + (st['issued'] if arm != 'C' else st['issued'] // NPART_C + 1)}))
    c.shutdown()


main()
