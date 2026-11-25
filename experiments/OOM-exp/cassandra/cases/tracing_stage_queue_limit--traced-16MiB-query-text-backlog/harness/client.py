#!/usr/bin/env python3
"""B28 client (stage 2, 2026-11-24): raw CQL native protocol v4 (unsegmented frames), standard library only.
Frame I/O adapted from R15's client.py; per-connection source IPs as B11's.

  client.py --ddl                                 CREATE KEYSPACE b28 (untraced)
  client.py --sizes [--len S]                     print query/body/frame size of the payload
  client.py --n N --hold-s H --out DIR [--flags 2|0] [--len S] [--tag p0]      fixed: N connections together, hold H s
  client.py --ramp 1,2,4,8 --step-s 60 --out DIR [--flags 2|0] [--len S]       ramp: connections added per step
  client.py --n 1 --count K --out DIR [--flags 2] [--len S]                     K requests on one connection (S0)
  client.py --traces --out DIR                    S0 check: per system_traces.sessions row the length of parameters['query'],
                                                  per session the events (activity length, thread)

Payload (case file section 2.4): unprepared QUERY of `USE b28 /*` + 'a' x (S - 12) + `*/` (S bytes, one comment token),
consistency ONE, flags 0x00; S = 16,000,000 by default. Frame header flags = --flags (0x02 tracing in test / intervention
arms, 0x00 in the control: the only difference). Connection i binds 127.1.(i // 250).(1 + i % 250) before connecting to
127.0.0.1:9042. Each connection: STARTUP -> READY, then a closed loop, one request outstanding.
Logs: DIR/completions-<tag>.txt (t_ms conn latency_ms result) and DIR/client-<tag>.txt (per second: t_ms open established
outstanding completed errors).
"""
import argparse, os, socket, struct, sys, threading, time

HOST, PORT = '127.0.0.1', 9042
OP_ERROR, OP_STARTUP, OP_READY, OP_QUERY, OP_RESULT = 0x00, 0x01, 0x02, 0x07, 0x08
S_DEFAULT = 16_000_000


def frame(op, body, flags=0, stream=0):
    return struct.pack('>BBhBi', 0x04, flags, stream, op, len(body)) + body


def lstr_b(b):
    return struct.pack('>i', len(b)) + b


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


def err_text(body):
    code = struct.unpack_from('>i', body)[0]; l = struct.unpack_from('>H', body, 4)[0]
    return code, body[6:6 + l].decode('utf-8', 'replace')


def src_ip(i):
    return '127.1.%d.%d' % (i // 250, 1 + i % 250)


class Conn:
    def __init__(self, i=0, timeout=60):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        s.bind((src_ip(i), 0))
        s.settimeout(timeout)
        s.connect((HOST, PORT))
        self.s = s
        s.sendall(frame(OP_STARTUP, struct.pack('>H', 1) + sstr('CQL_VERSION') + sstr('3.0.0')))
        op, fl, b = self.recv()
        if op != OP_READY:
            raise RuntimeError('startup: op %d %s' % (op, err_text(b) if op == 0 else ''))

    def recv(self):
        h = recvn(self.s, 9)
        ver, fl, st, op, ln = struct.unpack('>BBhBi', h)
        b = recvn(self.s, ln) if ln else b''
        if fl & 0x02: b = b[16:]   # tracing session id
        if fl & 0x08:              # warnings
            n = struct.unpack_from('>H', b)[0]; p = 2
            for _ in range(n):
                l = struct.unpack_from('>H', b, p)[0]; p += 2 + l
            b = b[p:]
        return op, fl, b

    def query(self, q, page_size=None, paging_state=None):
        fl = 0; extra = b''
        if page_size is not None: fl |= 0x04; extra += struct.pack('>i', page_size)
        if paging_state is not None: fl |= 0x08; extra += lstr_b(paging_state)
        self.s.sendall(frame(OP_QUERY, lstr_b(q.encode()) + struct.pack('>HB', 1, fl) + extra))
        op, _, b = self.recv()
        if op == OP_ERROR:
            raise RuntimeError('%x %s' % err_text(b))
        return b


def payload(S):
    return b'USE b28 /*' + b'a' * (S - 12) + b'*/'


def build(S, flags):
    q = payload(S)
    body = lstr_b(q) + struct.pack('>HB', 1, 0)
    return q, frame(OP_QUERY, body, flags), len(body)


# ---- minimal Rows parser (S0 trace check only) ----
def _opt(b, p):
    t = struct.unpack_from('>H', b, p)[0]; p += 2
    if t == 0x0000:
        l = struct.unpack_from('>H', b, p)[0]; p += 2 + l
    elif t in (0x0020, 0x0022):
        _, p = _opt(b, p)
    elif t == 0x0021:
        _, p = _opt(b, p); _, p = _opt(b, p)
    elif t in (0x0030, 0x0031):
        raise ValueError('udt/tuple not supported')
    return t, p


def rows(body):
    kind = struct.unpack_from('>i', body)[0]
    if kind != 2: return [], None
    p = 4; flags, ncol = struct.unpack_from('>ii', body, p); p += 8
    ps = None
    if flags & 0x02:
        l = struct.unpack_from('>i', body, p)[0]; p += 4
        if l >= 0: ps = body[p:p + l]; p += l
    if flags & 0x04: ncol = ncol
    else:
        if flags & 0x01:
            for _ in range(2):
                l = struct.unpack_from('>H', body, p)[0]; p += 2 + l
        types = []
        for _ in range(ncol):
            if not flags & 0x01:
                for _ in range(2):
                    l = struct.unpack_from('>H', body, p)[0]; p += 2 + l
            l = struct.unpack_from('>H', body, p)[0]; p += 2 + l
            t, p = _opt(body, p); types.append(t)
    n = struct.unpack_from('>i', body, p)[0]; p += 4
    out = []
    for _ in range(n):
        r = []
        for _ in range(ncol):
            l = struct.unpack_from('>i', body, p)[0]; p += 4
            r.append(None if l < 0 else body[p:p + l]); p += max(l, 0)
        out.append(r)
    return out, ps


def mapdec(v):
    n = struct.unpack_from('>i', v)[0]; p = 4; d = {}
    for _ in range(n):
        kl = struct.unpack_from('>i', v, p)[0]; p += 4; k = v[p:p + kl].decode(); p += kl
        vl = struct.unpack_from('>i', v, p)[0]; p += 4; d[k] = v[p:p + vl]; p += vl
    return d


def uuid_s(b):
    h = b.hex(); return '%s-%s-%s-%s-%s' % (h[:8], h[8:12], h[12:16], h[16:20], h[20:])


def traces(out):
    c = Conn(0, timeout=120)
    ids, _ = rows(c.query('SELECT session_id, started_at FROM system_traces.sessions'))
    print('sessions rows %d' % len(ids))
    for sid, _ in ids:
        r, _ = rows(c.query('SELECT parameters, request, duration FROM system_traces.sessions WHERE session_id = %s' % uuid_s(sid)))
        par = mapdec(r[0][0]) if r and r[0][0] else {}
        q = par.get('query', b'')
        ev, ps = rows(c.query('SELECT activity, thread FROM system_traces.events WHERE session_id = %s' % uuid_s(sid), page_size=1))
        evs = list(ev)
        while ps is not None:
            e2, ps = rows(c.query('SELECT activity, thread FROM system_traces.events WHERE session_id = %s' % uuid_s(sid),
                                  page_size=1, paging_state=ps))
            evs += e2
        print('session %s request=%s duration_us=%s params=%s query_len=%d query_head=%r query_tail=%r events=%d: %s' % (
            uuid_s(sid), (r[0][1] or b'').decode() if r else '-',
            struct.unpack('>i', r[0][2])[0] if r and r[0][2] else '-', sorted(par), len(q), q[:12], q[-4:], len(evs),
            '; '.join('len %d %r.. [%s]' % (len(a or b''), (a or b'')[:24], (t or b'').decode()) for a, t in evs)))


class Stats:
    def __init__(self):
        self.lock = threading.Lock(); self.open = 0; self.est = 0; self.out = 0; self.done = 0; self.err = 0


def worker(i, fr, st, stop, comp, start_at, count, sock_timeout):
    while time.time() < start_at and not stop.is_set():
        time.sleep(0.05)
    if stop.is_set(): return
    try:
        with st.lock: st.open += 1
        c = Conn(i, timeout=60)
        c.s.settimeout(sock_timeout)
        with st.lock: st.est += 1
    except Exception as e:
        with st.lock: st.err += 1; st.open -= 1
        comp.write('%d %d -1 connect_error %s\n' % (time.time() * 1000, i, str(e)[:100].replace(' ', '_')))
        return
    k = 0
    while not stop.is_set() and (count is None or k < count):
        ts = time.time()
        try:
            with st.lock: st.out += 1
            c.s.sendall(fr)
            op, fl, b = c.recv()
        except Exception as e:
            with st.lock: st.out -= 1; st.err += 1
            comp.write('%d %d %d io_error %s\n' % (time.time() * 1000, i, (time.time() - ts) * 1000,
                                                  str(e)[:100].replace(' ', '_')))
            break
        k += 1
        if op == OP_ERROR:
            code, msg = err_text(b); res = 'ERROR_0x%04x %s' % (code, msg[:120].replace(' ', '_'))
        else:
            res = 'op%d fl%d %s' % (op, fl, b[:4].hex())
        with st.lock:
            st.out -= 1
            if op == OP_ERROR: st.err += 1
            else: st.done += 1
        comp.write('%d %d %d %s\n' % (time.time() * 1000, i, (time.time() - ts) * 1000, res))
    try: c.s.close()
    except Exception: pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ddl', action='store_true'); ap.add_argument('--sizes', action='store_true')
    ap.add_argument('--traces', action='store_true')
    ap.add_argument('--n', type=int, default=1); ap.add_argument('--ramp')
    ap.add_argument('--step-s', type=int, default=60); ap.add_argument('--hold-s', type=int, default=180)
    ap.add_argument('--count', type=int); ap.add_argument('--flags', type=int, default=2)
    ap.add_argument('--len', type=int, default=S_DEFAULT); ap.add_argument('--out', default='.')
    ap.add_argument('--tag', default='p0')
    a = ap.parse_args()
    if a.ddl:
        c = Conn(0)
        c.query("CREATE KEYSPACE IF NOT EXISTS b28 WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
        print('ddl ok'); return 0
    if a.sizes:
        q, fr, B = build(a.len, a.flags)
        print('query %d body %d frame %d head %r tail %r' % (len(q), B, len(fr), q[:12], q[-4:])); return 0
    if a.traces:
        traces(a.out); return 0
    os.makedirs(a.out, exist_ok=True)
    comp = open(os.path.join(a.out, 'completions-%s.txt' % a.tag), 'a', buffering=1)
    clog = open(os.path.join(a.out, 'client-%s.txt' % a.tag), 'a', buffering=1)
    q, fr, B = build(a.len, a.flags)
    t0 = time.time() + 0.5
    if a.ramp:
        steps = [int(x) for x in a.ramp.split(',')]
        starts = []
        for i in range(steps[-1]):
            k = next(j for j, v in enumerate(steps) if v > i)
            starts.append(t0 + k * a.step_s)
        end = t0 + len(steps) * a.step_s
        for j, v in enumerate(steps):
            clog.write('# step %d N=%d at %d\n' % (j, v, (t0 + j * a.step_s) * 1000))
    else:
        starts = [t0] * a.n
        end = t0 + a.hold_s if a.count is None else t0 + 3600
    n = len(starts)
    clog.write('# start %s mode=%s n=%d len=%d body=%d frame=%d flags=0x%02x pid=%d t0=%d end=%d\n' % (
        time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'ramp ' + a.ramp if a.ramp else ('count %s' % a.count if a.count else 'fixed'),
        n, len(q), B, len(fr), a.flags, os.getpid(), t0 * 1000, end * 1000))
    st = Stats(); stop = threading.Event()
    th = [threading.Thread(target=worker, args=(i, fr, st, stop, comp, starts[i], a.count, 900), daemon=True)
          for i in range(n)]
    for t in th: t.start()

    def sampler():
        while not stop.is_set():
            with st.lock:
                clog.write('%d %d %d %d %d %d\n' % (time.time() * 1000, st.open, st.est, st.out, st.done, st.err))
            time.sleep(1)
    threading.Thread(target=sampler, daemon=True).start()
    while time.time() < end:
        if all(not t.is_alive() for t in th) and time.time() > max(starts):
            clog.write('# all connections ended at %d\n' % (time.time() * 1000)); break
        time.sleep(0.2)
    stop.set()
    with st.lock:
        clog.write('# end %d done=%d err=%d\n' % (time.time() * 1000, st.done, st.err))
    time.sleep(1.2)
    return 0


if __name__ == '__main__':
    sys.exit(main())
