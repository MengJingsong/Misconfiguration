#!/usr/bin/env python3
"""R12 client (from B11's): raw CQL native protocol v4, standard library only.

  client.py --ddl                                  create keyspace r12 and table r12.t
  client.py --load [--conns 8]                     seed: k=1 100,000 rows, k=2 300,000, k=3 1,000,000 (v = 8-byte c)
  client.py --single K --count 20                  calibration: one connection, sequential untraced requests
  client.py --trace-check                          print the parameters of up to 3 system_traces.sessions rows
  client.py --k K --tracing {on,off} [--distinct] --fixed N --hold-s H --out DIR
  client.py --k K --tracing {on,off} [--distinct] --ramp 8,13,16 --step-s 60 --out DIR

3-b confirm changes (2026-11-23): SASL PLAIN login for PasswordAuthenticator (--user/--password or env R12_USER /
R12_PASS; every connection logs in after STARTUP), --admin FILE (run the CQL statements of FILE, one per line, as the
logged-in role, printing each result or error), --victim (steady light workload of the victim role on vks.t from its own
source addresses 127.2.0.x, per-request log), --victim-load (victim seeds vks.t keys 0..999).

R12 changes: --k (statement partition), --distinct (each connection keeps its own copy of the frame and writes
struct.pack('>IQ', conn_id, seq) over the first 12 bytes of the value before every send), --load, --single.

Each connection i binds to source address 127.1.(i // 250).(1 + i % 250) (one request per IP), sends
STARTUP, PREPAREs `SELECT c FROM r12.t WHERE k = 0 AND v = ? ALLOW FILTERING`, then runs a closed loop of
EXECUTE frames carrying one blob of S bytes (consistency ONE). Tracing flag 0x02 in the frame header when
--tracing on; that flag is the only difference between test and control.
Logs: DIR/completions.txt (t_ms conn latency_ms status), DIR/client.txt (per second:
t_ms open established outstanding completed errors K_client).
"""
import argparse, os, socket, struct, sys, threading, time

S = 16_000_000
HOST, PORT = '127.0.0.1', 9042
STMT = 'SELECT c FROM r12.t WHERE k = %d AND v = ? ALLOW FILTERING'
INS = 'INSERT INTO r12.t (k, c, v) VALUES (?, ?, ?)'
VOFF = None  # offset of the value in the EXECUTE frame
OP_ERROR, OP_STARTUP, OP_READY, OP_QUERY, OP_RESULT, OP_PREPARE, OP_EXECUTE, OP_BATCH = 0x00, 0x01, 0x02, 0x07, 0x08, 0x09, 0x0A, 0x0D
OP_AUTHENTICATE, OP_AUTH_RESPONSE, OP_AUTH_SUCCESS = 0x03, 0x0F, 0x10
USER = os.environ.get('R12_USER'); PASS = os.environ.get('R12_PASS')


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
    if flags & 0x02:       # tracing: 16-byte session id first
        body = body[16:]
    if flags & 0x08:       # warnings: [string list]
        n = struct.unpack_from('>H', body)[0]; p = 2
        for _ in range(n):
            l = struct.unpack_from('>H', body, p)[0]; p += 2 + l
        body = body[p:]
    return op, body


def err_text(body):
    code = struct.unpack_from('>i', body)[0]; l = struct.unpack_from('>H', body, 4)[0]
    return '0x%04x:%s' % (code, body[6:6 + l].decode('utf-8', 'replace')[:120])


def open_conn(i, timeout=60, src=None):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    s.bind((src or '127.1.%d.%d' % (i // 250, 1 + i % 250), 0))
    s.settimeout(timeout)
    s.connect((HOST, PORT))
    body = struct.pack('>H', 1) + sstr('CQL_VERSION') + sstr('3.0.0')
    s.sendall(frame(OP_STARTUP, body))
    op, b = recv_frame(s)
    if op == OP_AUTHENTICATE:      # PasswordAuthenticator: SASL PLAIN token \0user\0password
        if USER is None:
            raise RuntimeError('server requires authentication and no user given')
        tok = b'\0' + USER.encode() + b'\0' + PASS.encode()
        s.sendall(frame(OP_AUTH_RESPONSE, struct.pack('>i', len(tok)) + tok))
        op, b = recv_frame(s)
        if op != OP_AUTH_SUCCESS:
            raise RuntimeError('auth: op %d %s' % (op, err_text(b) if op == 0 else ''))
        return s
    if op != OP_READY:
        raise RuntimeError('startup: op %d %s' % (op, err_text(b) if op == 0 else ''))
    return s


def query(s, q):
    s.sendall(frame(OP_QUERY, lstr(q) + struct.pack('>HB', 1, 0)))
    op, b = recv_frame(s)
    if op == OP_ERROR:
        raise RuntimeError(err_text(b))
    return b


def prepare(s, stmt=None):
    s.sendall(frame(OP_PREPARE, lstr(stmt or STMT)))
    op, b = recv_frame(s)
    if op != OP_RESULT or struct.unpack_from('>i', b)[0] != 4:
        raise RuntimeError('prepare: op %d %s' % (op, err_text(b) if op == 0 else ''))
    l = struct.unpack_from('>H', b, 4)[0]
    return b[6:6 + l]


class Stats:
    def __init__(self):
        self.lock = threading.Lock(); self.open = 0; self.est = 0; self.out = 0; self.done = 0; self.err = 0


def worker(i, st, payload_holder, tracing, stop, comp, t0, ready_evt):
    try:
        with st.lock: st.open += 1
        s = open_conn(i)
        sid = prepare(s)
        s.settimeout(None)
        if payload_holder.get('id') is None:
            payload_holder['id'] = sid
        if sid != payload_holder['id']:
            raise RuntimeError('statement id differs')
        with st.lock: st.est += 1
    except Exception as e:
        with st.lock: st.err += 1; st.open -= 1
        comp.write('%d %d -1 connect_error:%s\n' % ((time.time() - t0) * 1000, i, str(e)[:100]))
        return
    ready_evt.wait()
    fr = payload_holder['frame']
    if payload_holder.get('distinct'):
        fr = bytearray(fr)
    seq = 0
    while not stop.is_set():
        ts = time.time()
        try:
            with st.lock: st.out += 1
            if payload_holder.get('distinct'):
                struct.pack_into('>IQ', fr, VOFF, i, seq); seq += 1
            s.sendall(fr)
            op, b = recv_frame(s)
            status = 'ok' if op == OP_RESULT else ('err:' + err_text(b) if op == OP_ERROR else 'op%d' % op)
        except Exception as e:
            status = 'io_error:%s' % str(e)[:80]
            with st.lock: st.out -= 1; st.err += 1
            comp.write('%d %d %d %s\n' % ((time.time() - t0) * 1000, i, (time.time() - ts) * 1000, status))
            break
        with st.lock:
            st.out -= 1
            if status == 'ok': st.done += 1
            else: st.err += 1
        comp.write('%d %d %d %s\n' % ((time.time() - t0) * 1000, i, (time.time() - ts) * 1000, status))
    try: s.close()
    except Exception: pass


def build_frame(sid, tracing):
    global VOFF
    blob = bytes(range(256)) * (S // 256)
    assert len(blob) == S
    head = struct.pack('>H', len(sid)) + sid + struct.pack('>HBH', 1, 0x01, 1) + struct.pack('>i', S)
    VOFF = 9 + len(head)
    return frame(OP_EXECUTE, head + blob, flags=0x02 if tracing else 0x00)


def load(conns):
    """Seed: unlogged single-partition batches of 150 rows over `conns` connections (closed loop each)."""
    jobs = []
    for k, n in ((1, 100_000), (2, 300_000), (3, 1_000_000)):
        for c0 in range(0, n, 150):
            jobs.append((k, c0, min(150, n - c0)))
    lock = threading.Lock(); errs = []; done = [0]
    def w(ci):
        s = open_conn(500 + ci); sid = prepare(s, INS)
        while True:
            with lock:
                if not jobs: return
                k, c0, m = jobs.pop()
            body = bytearray(struct.pack('>BH', 1, m))
            for c in range(c0, c0 + m):
                body += struct.pack('>BH', 1, len(sid)) + sid + struct.pack('>H', 3)
                body += struct.pack('>ii', 4, k) + struct.pack('>ii', 4, c) + struct.pack('>iQ', 8, c)
            body += struct.pack('>HB', 1, 0)      # consistency ONE, flags 0
            s.sendall(frame(OP_BATCH, bytes(body)))
            op, b = recv_frame(s)
            if op != OP_RESULT:
                with lock: errs.append(err_text(b) if op == 0 else 'op%d' % op)
                return
            with lock: done[0] += m
    ts = [threading.Thread(target=w, args=(i,)) for i in range(conns)]
    t0 = time.time(); [t.start() for t in ts]; [t.join() for t in ts]
    print('load: rows %d in %.1f s, errors %s' % (done[0], time.time() - t0, errs[:3])); return 1 if errs else 0


def single(k, count):
    global STMT
    STMT = STMT % k
    s = open_conn(9997, timeout=120); sid = prepare(s); fr = build_frame(sid, False); lat = []
    for j in range(count):
        ts = time.time(); s.sendall(fr); op, b = recv_frame(s); l = (time.time() - ts) * 1000; lat.append(l)
        print('k=%d req %d latency %.0f ms %s' % (k, j, l, 'ok' if op == OP_RESULT else (err_text(b) if op == 0 else 'op%d' % op)), flush=True)
    sl = sorted(lat); print('k=%d median %.0f ms min %.0f max %.0f' % (k, sl[len(sl) // 2], sl[0], sl[-1]))


def _opt(b, p):
    t = struct.unpack_from('>H', b, p)[0]; p += 2
    if t == 0x0000:
        l = struct.unpack_from('>H', b, p)[0]; return (t, b[p + 2:p + 2 + l].decode()), p + 2 + l
    if t in (0x0020, 0x0022):
        e, p = _opt(b, p); return (t, e), p
    if t == 0x0021:
        k, p = _opt(b, p); v, p = _opt(b, p); return (t, k, v), p
    if t == 0x0031:
        n = struct.unpack_from('>H', b, p)[0]; p += 2; es = []
        for _ in range(n):
            e, p = _opt(b, p); es.append(e)
        return (t, es), p
    if t == 0x0030:
        raise RuntimeError('udt not supported')
    return (t,), p


def _val(t, v):
    if v is None: return 'null'
    if t[0] in (0x0001, 0x000D): return v.decode('utf-8', 'replace')
    if t[0] == 0x0004: return str(bool(v[0]))
    if t[0] == 0x0009: return str(struct.unpack('>i', v)[0])
    if t[0] in (0x0020, 0x0022):
        n = struct.unpack_from('>i', v)[0]; p = 4; out = []
        for _ in range(n):
            l = struct.unpack_from('>i', v, p)[0]; out.append(_val(t[1], v[p + 4:p + 4 + l])); p += 4 + l
        return '{' + ', '.join(out) + '}'
    if t[0] == 0x0021:
        n = struct.unpack_from('>i', v)[0]; p = 4; out = []
        for _ in range(n):
            l = struct.unpack_from('>i', v, p)[0]; kk = _val(t[1], v[p + 4:p + 4 + l]); p += 4 + l
            l = struct.unpack_from('>i', v, p)[0]; vv = _val(t[2], v[p + 4:p + 4 + l]); p += 4 + l
            out.append('%s: %s' % (kk, vv))
        return '{' + ', '.join(out) + '}'
    return '0x' + v.hex()[:40]


def result_text(b):
    kind = struct.unpack_from('>i', b)[0]
    if kind == 1: return 'void'
    if kind == 3: return 'set_keyspace'
    if kind == 5: return 'schema_change'
    if kind != 2: return 'kind %d' % kind
    flags, ncol = struct.unpack_from('>ii', b, 4); p = 12
    if flags & 0x0002:
        l = struct.unpack_from('>i', b, p)[0]; p += 4 + max(l, 0)
    gts = flags & 0x0001
    if gts:
        for _ in range(2):
            l = struct.unpack_from('>H', b, p)[0]; p += 2 + l
    cols = []
    if not flags & 0x0004:
        for _ in range(ncol):
            if not gts:
                for _ in range(2):
                    l = struct.unpack_from('>H', b, p)[0]; p += 2 + l
            l = struct.unpack_from('>H', b, p)[0]; name = b[p + 2:p + 2 + l].decode(); p += 2 + l
            t, p = _opt(b, p); cols.append((name, t))
    nrows = struct.unpack_from('>i', b, p)[0]; p += 4; lines = ['rows %d: %s' % (nrows, ' | '.join(c[0] for c in cols))]
    for _ in range(nrows):
        vals = []
        for c in cols:
            l = struct.unpack_from('>i', b, p)[0]; p += 4
            v = None if l < 0 else b[p:p + l]; p += max(l, 0); vals.append(_val(c[1], v))
        lines.append('  ' + ' | '.join(vals))
    return '\n'.join(lines)


def admin(path):
    """Run each non-empty, non-comment line of `path` as one CQL statement as the logged-in role."""
    s = open_conn(9999, src='127.3.0.1'); bad = 0
    for line in open(path):
        q = line.strip().rstrip(';')
        if not q or q.startswith('--'): continue
        shown = q if 'PASSWORD' not in q.upper() else q[:q.upper().find('PASSWORD')] + "PASSWORD = '<redacted>' ..."
        try:
            b = query(s, q); print('OK   %s\n     %s' % (shown, result_text(b).replace('\n', '\n     ')), flush=True)
        except RuntimeError as e:
            bad += 1; print('ERR  %s\n     %s' % (shown, e), flush=True)
    return 0


def victim_load():
    s = open_conn(0, src='127.2.0.200'); sid = prepare(s, 'INSERT INTO vks.t (k, v) VALUES (?, ?)')
    for k in range(1000):
        body = struct.pack('>H', len(sid)) + sid + struct.pack('>HBH', 1, 0x01, 2) + struct.pack('>ii', 4, k) + struct.pack('>i', 100) + bytes([k % 256]) * 100
        s.sendall(frame(OP_EXECUTE, body)); op, b = recv_frame(s)
        if op != OP_RESULT: print('victim load error', err_text(b) if op == 0 else op); return 1
    print('victim load: 1000 rows ok'); return 0


def victim(conns, rate, out, stopfile, timeout):
    """Steady light workload as the victim role: `conns` connections from 127.2.0.(1+i), together `rate` requests/s,
    alternating a 100-B INSERT and a SELECT of one row of vks.t at CL ONE. Each connection sends on a fixed schedule
    (one request in flight; a late request is followed by the next one at once). On an error the connection is
    re-opened (connect errors are logged on the schedule as well). Ends when `stopfile` exists.
    Log: out/victim.txt  epoch_ms conn op latency_ms status"""
    import random
    log = open(os.path.join(out, 'victim.txt'), 'a', buffering=1); lk = threading.Lock()
    iv = conns / float(rate)
    def w(i):
        rnd = random.Random(i); s = None; nxt = time.time(); j = 0; wid = rid = None
        while not os.path.exists(stopfile):
            now = time.time()
            if now < nxt: time.sleep(min(nxt - now, 0.5)); continue
            nxt += iv
            if nxt < now - 5: nxt = now   # do not build up an unbounded backlog after a stall
            op = 'w' if j % 2 == 0 else 'r'; j += 1; k = rnd.randrange(1000); ts = time.time()
            try:
                if s is None:
                    s = open_conn(i, timeout=timeout, src='127.2.0.%d' % (1 + i))
                    s.settimeout(timeout)
                    wid = prepare(s, 'INSERT INTO vks.t (k, v) VALUES (?, ?)'); rid = prepare(s, 'SELECT v FROM vks.t WHERE k = ?')
                if op == 'w':
                    body = struct.pack('>H', len(wid)) + wid + struct.pack('>HBH', 1, 0x01, 2) + struct.pack('>ii', 4, k) + struct.pack('>i', 100) + os.urandom(100)
                else:
                    body = struct.pack('>H', len(rid)) + rid + struct.pack('>HBH', 1, 0x01, 1) + struct.pack('>ii', 4, k)
                s.sendall(frame(OP_EXECUTE, body)); rop, b = recv_frame(s)
                st = 'ok' if rop == OP_RESULT else ('err:' + err_text(b)[:60].replace(' ', '_') if rop == OP_ERROR else 'op%d' % rop)
            except Exception as e:
                st = 'io:%s' % type(e).__name__
                try: s and s.close()
                except Exception: pass
                s = None
            with lk: log.write('%d %d %s %d %s\n' % (ts * 1000, i, op, (time.time() - ts) * 1000, st))
            if s is None and st.startswith('io:'): time.sleep(0.2)
    ts_ = [threading.Thread(target=w, args=(i,), daemon=True) for i in range(conns)]
    [t.start() for t in ts_]
    while not os.path.exists(stopfile): time.sleep(0.5)
    time.sleep(timeout + 1)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ddl', action='store_true'); ap.add_argument('--trace-check', action='store_true')
    ap.add_argument('--tracing', choices=['on', 'off']); ap.add_argument('--fixed', type=int)
    ap.add_argument('--ramp'); ap.add_argument('--step-s', type=int, default=60); ap.add_argument('--hold-s', type=int, default=150)
    ap.add_argument('--out', default='.'); ap.add_argument('--k', type=int); ap.add_argument('--distinct', action='store_true')
    ap.add_argument('--load', action='store_true'); ap.add_argument('--conns', type=int, default=8)
    ap.add_argument('--single', type=int); ap.add_argument('--count', type=int, default=20)
    ap.add_argument('--user'); ap.add_argument('--password'); ap.add_argument('--admin')
    ap.add_argument('--victim', action='store_true'); ap.add_argument('--victim-load', action='store_true')
    ap.add_argument('--rate', type=float, default=20); ap.add_argument('--stopfile'); ap.add_argument('--timeout', type=float, default=12)
    a = ap.parse_args()
    global STMT, USER, PASS
    if a.user: USER, PASS = a.user, a.password
    if a.admin: return admin(a.admin)
    if a.victim_load: return victim_load()
    if a.victim: return victim(a.conns, a.rate, a.out, a.stopfile, a.timeout)
    if a.load: return load(a.conns)
    if a.single is not None: single(a.single, a.count); return 0
    if a.ddl:
        s = open_conn(9999)
        query(s, "CREATE KEYSPACE IF NOT EXISTS r12 WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
        query(s, 'CREATE TABLE IF NOT EXISTS r12.t (k int, c int, v blob, PRIMARY KEY (k, c))')
        print('ddl ok'); return
    if a.trace_check:
        s = open_conn(9998)
        b = query(s, 'SELECT session_id, parameters FROM system_traces.sessions LIMIT 3')
        # crude: print map strings that start with bound_var and their lengths
        txt = b.decode('latin-1')
        k = 0
        while True:
            j = txt.find('bound_var_', k)
            if j < 0: break
            kl = struct.unpack_from('>i', b, j - 4)[0]; key = txt[j:j + kl]
            vl = struct.unpack_from('>i', b, j + kl)[0]; val = txt[j + kl + 4:j + kl + 4 + vl]
            print('%s len=%d head=%s tail=%s' % (key, vl, val[:12], val[-8:])); k = j + kl + 4 + vl
        return
    tracing = a.tracing == 'on'
    STMT = STMT % a.k
    steps = [a.fixed] if a.fixed else [int(x) for x in a.ramp.split(',')]
    os.makedirs(a.out, exist_ok=True)
    comp = open(os.path.join(a.out, 'completions.txt'), 'a', buffering=1)
    clog = open(os.path.join(a.out, 'client.txt'), 'a', buffering=1)
    st = Stats(); stop = threading.Event(); holder = {'id': None, 'frame': None, 'distinct': a.distinct}
    t0 = time.time()
    clog.write('# start %s tracing=%s distinct=%s k=%d steps=%s S=%d\n' % (time.strftime('%Y-%m-%dT%H:%M:%S%z'), a.tracing, a.distinct, a.k, steps, S))
    B = None
    def sampler():
        while not stop.is_set():
            with st.lock:
                clog.write('%d %d %d %d %d %d %d\n' % ((time.time() - t0) * 1000, st.open, st.est, st.out, st.done, st.err,
                                                        st.out * (B or 0)))
            time.sleep(1)
    threading.Thread(target=sampler, daemon=True).start()
    threads = []; n = 0
    for si, target in enumerate(steps):
        evt = threading.Event()
        new = []
        while n < target:
            t = threading.Thread(target=worker, args=(n, st, holder, tracing, stop, comp, t0, evt), daemon=True)
            t.start(); new.append(t); n += 1
        # wait for the new connections to be established (or fail), up to 120 s
        dl = time.time() + 120
        while time.time() < dl:
            with st.lock:
                if st.est + st.err >= n: break
            time.sleep(0.2)
        if holder['frame'] is None:
            if holder['id'] is None:
                clog.write('# no connection established\n'); stop.set(); return 2
            holder['frame'] = build_frame(holder['id'], tracing); B = len(holder['frame']) - 9
        clog.write('# step %d N=%d established=%d at %d ms\n' % (si, target, st.est, (time.time() - t0) * 1000))
        evt.set(); threads += new
        hold = a.hold_s if a.fixed else a.step_s
        dl = time.time() + hold
        while time.time() < dl:
            if not any(t.is_alive() for t in threads):
                break
            time.sleep(0.5)
        if not any(t.is_alive() for t in threads):
            clog.write('# all connections ended at %d ms\n' % ((time.time() - t0) * 1000)); break
    stop.set()
    clog.write('# end %d ms done=%d err=%d\n' % ((time.time() - t0) * 1000, st.done, st.err))
    time.sleep(1.2)
    return 0


if __name__ == '__main__':
    sys.exit(main())
