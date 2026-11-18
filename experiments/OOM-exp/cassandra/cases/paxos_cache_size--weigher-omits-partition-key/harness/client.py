#!/usr/bin/env python3
"""B12 client: raw CQL native protocol v4, standard library only (after B11's client.py).

  client.py --ddl                     create keyspace b12 and table b12.t (k blob PRIMARY KEY, v int)
  client.py --settings                print selected rows of system_views.settings
  client.py --cl SERIAL|ONE --K 61440 --nmax 50000 --m 4000 --out DIR [--conns 32] [--max-load-s 900]

C connections to 127.0.0.1:9042, one request outstanding each (closed loop, one thread per connection):
STARTUP, PREPARE `SELECT v FROM b12.t WHERE k = ?`, then EXECUTE with one bound blob. Consistency SERIAL
(0x0008) in the test arms, ONE (0x0001) in the control arm; that is the only difference.
Key i (each used once) = 8-byte big-endian i || a fixed pad of K-8 bytes from random.Random(12).
Per-request timeout 30 s; an error is counted and the next key is used (no retry); after a timeout or
I/O error the connection is reopened (if that fails, the thread ends: daemon gone).
Milestones: at every M drained keys, stop issuing, wait for outstanding = 0 (<= 60 s), create
DIR/ms-<n>.req (content: drained count), wait for DIR/ms-<n>.done (<= 180 s), resume.
Stop at N_max issued and drained, when every connection thread has ended, or after max-load-s of load
(milestone pauses excluded).
Logs: DIR/client.txt every second (t_ms issued ok errors outstanding alive_threads), DIR/errors.txt
(first 50 error messages), DIR/errcounts.txt (error tally at end).
"""
import argparse, os, random, socket, struct, sys, threading, time

HOST, PORT = '127.0.0.1', 9042
STMT = 'SELECT v FROM b12.t WHERE k = ?'
OP_ERROR, OP_STARTUP, OP_READY, OP_QUERY, OP_RESULT, OP_PREPARE, OP_EXECUTE = 0x00, 0x01, 0x02, 0x07, 0x08, 0x09, 0x0A
CL = {'SERIAL': 0x0008, 'ONE': 0x0001}


def frame(op, body, flags=0, stream=0):
    return struct.pack('>BBhBi', 0x04, flags, stream, op, len(body)) + body


def lstr(s):
    b = s.encode(); return struct.pack('>i', len(b)) + b


def sstr(s):
    b = s.encode(); return struct.pack('>H', len(b)) + b


def recvn(sock, n):
    buf = bytearray(n); mv = memoryview(buf); got = 0
    while got < n:
        r = sock.recv_into(mv[got:], n - got)
        if r == 0:
            raise ConnectionError('closed')
        got += r
    return bytes(buf)


def recv_frame(sock):
    h = recvn(sock, 9)
    ver, flags, stream, op, ln = struct.unpack('>BBhBi', h)
    body = recvn(sock, ln) if ln else b''
    if flags & 0x02:
        body = body[16:]
    if flags & 0x08:
        n = struct.unpack_from('>H', body)[0]; p = 2
        for _ in range(n):
            l = struct.unpack_from('>H', body, p)[0]; p += 2 + l
        body = body[p:]
    return op, body


def err_text(body):
    code = struct.unpack_from('>i', body)[0]; l = struct.unpack_from('>H', body, 4)[0]
    return '0x%04x:%s' % (code, body[6:6 + l].decode('utf-8', 'replace')[:160])


def open_conn(timeout=60):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    s.settimeout(timeout)
    s.connect((HOST, PORT))
    s.sendall(frame(OP_STARTUP, struct.pack('>H', 1) + sstr('CQL_VERSION') + sstr('3.0.0')))
    op, b = recv_frame(s)
    if op != OP_READY:
        raise RuntimeError('startup: op %d %s' % (op, err_text(b) if op == 0 else ''))
    return s


def query(s, q):
    s.sendall(frame(OP_QUERY, lstr(q) + struct.pack('>HB', 1, 0)))
    op, b = recv_frame(s)
    if op == OP_ERROR:
        raise RuntimeError(err_text(b))
    return b


def parse_rows(b):
    """RESULT Rows with text/blob columns only -> list of rows (bytes or None)."""
    kind, flags, ncol = struct.unpack_from('>iii', b); p = 12
    assert kind == 2
    def rs(p):
        l = struct.unpack_from('>H', b, p)[0]; return b[p + 2:p + 2 + l].decode(), p + 2 + l
    if flags & 0x02:
        l = struct.unpack_from('>i', b, p)[0]; p += 4 + max(l, 0)
    glob = flags & 0x01
    if glob:
        _, p = rs(p); _, p = rs(p)
    for _ in range(ncol):
        if not glob:
            _, p = rs(p); _, p = rs(p)
        _, p = rs(p)
        t = struct.unpack_from('>H', b, p)[0]; p += 2
        assert t in (0x0003, 0x000A, 0x000D), 'type %x' % t
    nrows = struct.unpack_from('>i', b, p)[0]; p += 4; rows = []
    for _ in range(nrows):
        r = []
        for _ in range(ncol):
            l = struct.unpack_from('>i', b, p)[0]; p += 4
            r.append(None if l < 0 else b[p:p + l]); p += max(l, 0)
        rows.append(r)
    return rows


def prepare(s):
    s.sendall(frame(OP_PREPARE, lstr(STMT)))
    op, b = recv_frame(s)
    if op != OP_RESULT or struct.unpack_from('>i', b)[0] != 4:
        raise RuntimeError('prepare: op %d %s' % (op, err_text(b) if op == 0 else ''))
    l = struct.unpack_from('>H', b, 4)[0]
    return b[6:6 + l]


SETTINGS = ('paxos_cache_size', 'paxos_variant', 'paxos_state_purging', 'paxos_repair_enabled', 'memtable_heap_space',
            'memtable_offheap_space', 'memtable_allocation_type', 'memtable_cleanup_threshold', 'memtable_flush_writers',
            'native_transport_max_request_data_in_flight', 'native_transport_max_request_data_in_flight_per_ip',
            'key_cache_size', 'counter_cache_size', 'commitlog_total_space', 'native_transport_max_frame_size',
            'cas_contention_timeout', 'read_request_timeout', 'write_request_timeout', 'native_transport_timeout')


class St:
    def __init__(self, nmax, m):
        self.cond = threading.Condition(); self.issued = 0; self.ok = 0; self.err = 0; self.out = 0
        self.nmax = nmax; self.m = m; self.boundary = min(m, nmax); self.stop = False; self.errs = {}; self.nerrlog = 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ddl', action='store_true'); ap.add_argument('--settings', action='store_true')
    ap.add_argument('--cl', choices=list(CL)); ap.add_argument('--K', type=int); ap.add_argument('--nmax', type=int)
    ap.add_argument('--m', type=int); ap.add_argument('--conns', type=int, default=32)
    ap.add_argument('--max-load-s', type=int, default=900); ap.add_argument('--out', default='.')
    a = ap.parse_args()
    if a.ddl:
        s = open_conn()
        query(s, "CREATE KEYSPACE IF NOT EXISTS b12 WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
        query(s, 'CREATE TABLE IF NOT EXISTS b12.t (k blob PRIMARY KEY, v int)')
        print('ddl ok'); return 0
    if a.settings:
        s = open_conn()
        rows = parse_rows(query(s, 'SELECT name, value FROM system_views.settings'))
        d = {r[0].decode(): (r[1].decode() if r[1] is not None else None) for r in rows}
        for n in SETTINGS:
            print('%s = %r' % (n, d.get(n, '<absent>')))
        return 0
    out = a.out; os.makedirs(out, exist_ok=True)
    pad = random.Random(12).randbytes(a.K - 8)
    cl = CL[a.cl]
    st = St(a.nmax, a.m)
    clog = open(os.path.join(out, 'client.txt'), 'a', buffering=1)
    elog = open(os.path.join(out, 'errors.txt'), 'a', buffering=1)
    t0 = time.time()
    clog.write('# start %s cl=%s K=%d nmax=%d m=%d conns=%d\n' % (time.strftime('%Y-%m-%dT%H:%M:%S%z'), a.cl, a.K, a.nmax, a.m, a.conns))

    def take():
        with st.cond:
            while not st.stop and st.issued >= st.boundary:
                if st.issued >= st.nmax:
                    return None
                st.cond.wait(0.5)
            if st.stop:
                return None
            i = st.issued; st.issued += 1; st.out += 1
            return i

    def fin(ok, msg=None):
        with st.cond:
            st.out -= 1
            if ok: st.ok += 1
            else:
                st.err += 1; k = (msg or '?')[:70]; st.errs[k] = st.errs.get(k, 0) + 1
                if st.nerrlog < 50:
                    st.nerrlog += 1; elog.write('%d %s\n' % ((time.time() - t0) * 1000, msg))
            st.cond.notify_all()

    def worker(ci):
        try:
            s = open_conn(); sid = prepare(s); s.settimeout(30)
        except Exception as e:
            elog.write('connect %d: %s\n' % (ci, e)); return
        head = struct.pack('>H', len(sid)) + sid + struct.pack('>HBH', cl, 0x01, 1) + struct.pack('>i', a.K)
        while True:
            i = take()
            if i is None:
                break
            fr = frame(OP_EXECUTE, head + struct.pack('>Q', i) + pad)
            try:
                s.sendall(fr)
                op, b = recv_frame(s)
                if op == OP_RESULT: fin(True)
                else: fin(False, 'err:' + err_text(b) if op == OP_ERROR else 'op%d' % op)
                continue
            except Exception as e:
                fin(False, 'io:%s:%s' % (type(e).__name__, str(e)[:80]))
            try: s.close()
            except Exception: pass
            try:
                s = open_conn(); sid2 = prepare(s); s.settimeout(30)
                assert sid2 == sid
            except Exception as e:
                elog.write('%d reconnect %d failed: %s\n' % ((time.time() - t0) * 1000, ci, e)); return
        try: s.close()
        except Exception: pass

    ths = [threading.Thread(target=worker, args=(ci,), daemon=True) for ci in range(a.conns)]
    for t in ths: t.start()
    alive = lambda: sum(t.is_alive() for t in ths)

    def sampler():
        while True:
            with st.cond:
                clog.write('%d %d %d %d %d %d\n' % ((time.time() - t0) * 1000, st.issued, st.ok, st.err, st.out, alive()))
            time.sleep(1)
    threading.Thread(target=sampler, daemon=True).start()

    paused = 0.0; n = 0; end = 'nmax'
    while True:
        time.sleep(0.2)
        if alive() == 0:
            with st.cond:
                end = 'nmax' if (st.issued >= st.nmax and st.out == 0) else 'all-threads-ended'
            break
        if time.time() - t0 - paused > a.max_load_s:
            end = 'max-load-time'; break
        with st.cond:
            at_b = st.issued >= st.boundary
        if not at_b:
            continue
        p0 = time.time()
        dl = time.time() + 60
        while time.time() < dl:
            with st.cond:
                if st.out == 0: break
            if alive() == 0: break
            time.sleep(0.2)
        if alive() == 0:
            end = 'all-threads-ended'; break
        with st.cond:
            drained = st.issued; outn = st.out
        if drained >= st.nmax:
            paused += time.time() - p0; end = 'nmax'; break
        n += 1
        clog.write('# milestone %d drained=%d ok=%d err=%d out=%d at %d ms\n' % (n, drained, st.ok, st.err, outn, (time.time() - t0) * 1000))
        open(os.path.join(out, 'ms-%d.req' % n), 'w').write('%d\n' % drained)
        dl = time.time() + 180
        while time.time() < dl and not os.path.exists(os.path.join(out, 'ms-%d.done' % n)):
            time.sleep(0.5)
        clog.write('# milestone %d done=%s at %d ms\n' % (n, os.path.exists(os.path.join(out, 'ms-%d.done' % n)), (time.time() - t0) * 1000))
        paused += time.time() - p0
        with st.cond:
            st.boundary = min(st.boundary + st.m, st.nmax); st.cond.notify_all()
    with st.cond:
        st.stop = True; st.cond.notify_all()
    for t in ths: t.join(35)
    with st.cond:
        clog.write('# end %s at %d ms (load %.0f s) issued=%d ok=%d err=%d out=%d\n' % (
            end, (time.time() - t0) * 1000, time.time() - t0 - paused, st.issued, st.ok, st.err, st.out))
        with open(os.path.join(out, 'errcounts.txt'), 'w') as f:
            for k, v in sorted(st.errs.items(), key=lambda x: -x[1]): f.write('%d %s\n' % (v, k))
    time.sleep(1.2)
    return 0


if __name__ == '__main__':
    sys.exit(main())
