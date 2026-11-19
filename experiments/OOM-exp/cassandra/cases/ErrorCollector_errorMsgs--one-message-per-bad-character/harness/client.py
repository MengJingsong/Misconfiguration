#!/usr/bin/env python3
"""U6 client: raw CQL native protocol v4 (unsegmented frames), standard library only. Frame I/O adapted from B11/B14.

  client.py --ddl                       create keyspace u6 and table u6.t (k int PRIMARY KEY, v int)
  client.py --sizes                     print query/body/frame sizes of every payload at the default length
  client.py --payload {H,C,M,CM} --n N --hold-s S --out DIR [--len L] [--count K] [--tag p0]

Payloads (case file section 2.4/2.5):
  H   QUERY of '#' x L (L = 16,777,200 by default; v4 body 16,777,207 B, frame 16,777,216 B)
  C   QUERY of '-- ' + '#' x (L - 4) + '\\n' (same L bytes, one COMMENT token)
  M   PREPARE of 'SELECT v FROM u6.t WHERE k IN (' + '?,' x (M - 1) + '?)', M = (L_M - len(prefix)) // 2,
      L_M = 16,777,203 by default (body = 4 + query <= 16,777,207)
  CM  PREPARE of '-- ' + '#' x (L_M - 4) + '\\n'
All connections from 127.0.0.1 (one client IP) to 127.0.0.1:9042. Each connection: STARTUP -> READY -> closed loop with
one request outstanding until the hold ends (or K responses with --count). The frame is built once per process.
Logs: DIR/completions-<tag>.txt (t_ms conn latency_ms opcode code first-120-chars-of-message, spaces as '_') and
DIR/client-<tag>.txt (per second: t_ms open established outstanding completed errors K_client).
"""
import argparse, os, socket, struct, sys, threading, time

HOST, PORT = '127.0.0.1', 9042
OP_ERROR, OP_STARTUP, OP_READY, OP_QUERY, OP_RESULT, OP_PREPARE = 0x00, 0x01, 0x02, 0x07, 0x08, 0x09
L_DEFAULT = 16_777_200
LM_DEFAULT = 16_777_203
PREFIX_M = 'SELECT v FROM u6.t WHERE k IN ('


def frame(op, body, stream=0):
    return struct.pack('>BBhBi', 0x04, 0, stream, op, len(body)) + body


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


class Conn:
    def __init__(self, timeout=60):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        s.bind(('127.0.0.1', 0))
        s.settimeout(timeout)
        s.connect((HOST, PORT))
        self.s = s
        s.sendall(frame(OP_STARTUP, struct.pack('>H', 1) + sstr('CQL_VERSION') + sstr('3.0.0')))
        op, b = self.recv()
        if op != OP_READY:
            raise RuntimeError('startup: op %d %s' % (op, err_text(b) if op == 0 else ''))

    def recv(self):
        h = recvn(self.s, 9)
        ver, fl, st, op, ln = struct.unpack('>BBhBi', h)
        b = recvn(self.s, ln) if ln else b''
        if fl & 0x02: b = b[16:]
        if fl & 0x08:
            n = struct.unpack_from('>H', b)[0]; p = 2
            for _ in range(n):
                l = struct.unpack_from('>H', b, p)[0]; p += 2 + l
            b = b[p:]
        return op, b

    def query(self, q):
        self.s.sendall(frame(OP_QUERY, lstr_b(q.encode()) + struct.pack('>HB', 1, 0)))
        op, b = self.recv()
        if op == OP_ERROR:
            raise RuntimeError('%x %s' % err_text(b))
        return b


def payload(p, L=None):
    """-> (opcode, query bytes)"""
    if p == 'H':
        L = L or L_DEFAULT; return OP_QUERY, b'#' * L
    if p == 'C':
        L = L or L_DEFAULT; return OP_QUERY, b'-- ' + b'#' * (L - 4) + b'\n'
    if p == 'M':
        LM = L or LM_DEFAULT; m = (LM - len(PREFIX_M)) // 2
        return OP_PREPARE, PREFIX_M.encode() + b'?,' * (m - 1) + b'?)'
    if p == 'CM':
        LM = L or LM_DEFAULT; return OP_PREPARE, b'-- ' + b'#' * (LM - 4) + b'\n'
    raise ValueError(p)


def build(p, L=None):
    op, q = payload(p, L)
    body = lstr_b(q) + (struct.pack('>HB', 1, 0) if op == OP_QUERY else b'')
    return op, q, frame(op, body), len(body)


class Stats:
    def __init__(self):
        self.lock = threading.Lock(); self.open = 0; self.est = 0; self.out = 0; self.done = 0; self.err = 0


def worker(i, fr, st, stop, comp, go, hold, count):
    try:
        with st.lock: st.open += 1
        c = Conn()
        c.s.settimeout(hold + 120)
        with st.lock: st.est += 1
    except Exception as e:
        with st.lock: st.err += 1; st.open -= 1
        comp.write('%d %d -1 connect_error - %s\n' % (time.time() * 1000, i, str(e)[:100].replace(' ', '_')))
        return
    go.wait()
    k = 0
    while not stop.is_set() and (count is None or k < count):
        ts = time.time()
        try:
            with st.lock: st.out += 1
            c.s.sendall(fr)
            op, b = c.recv()
        except Exception as e:
            with st.lock: st.out -= 1; st.err += 1
            comp.write('%d %d %d io_error - %s\n' % (time.time() * 1000, i, (time.time() - ts) * 1000,
                                                    str(e)[:100].replace(' ', '_')))
            break
        k += 1
        if op == OP_ERROR:
            code, msg = err_text(b); res = 'ERROR 0x%04x %s' % (code, msg[:120].replace(' ', '_'))
        else:
            res = 'op%d - %s' % (op, b[:4].hex())
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
    ap.add_argument('--payload', choices=['H', 'C', 'M', 'CM']); ap.add_argument('--n', type=int, default=1)
    ap.add_argument('--hold-s', type=int, default=300); ap.add_argument('--out', default='.')
    ap.add_argument('--len', type=int); ap.add_argument('--count', type=int); ap.add_argument('--tag', default='p0')
    a = ap.parse_args()
    if a.ddl:
        c = Conn()
        c.query("CREATE KEYSPACE IF NOT EXISTS u6 WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
        c.query('CREATE TABLE IF NOT EXISTS u6.t (k int PRIMARY KEY, v int)')
        print('ddl ok'); return 0
    if a.sizes:
        for p in ('H', 'C', 'M', 'CM'):
            op, q, fr, bl = build(p, a.len)
            extra = ' markers %d' % q.count(b'?') if p == 'M' else ''
            print('%s op 0x%02x query %d body %d frame %d%s' % (p, op, len(q), bl, len(fr), extra))
        return 0
    os.makedirs(a.out, exist_ok=True)
    comp = open(os.path.join(a.out, 'completions-%s.txt' % a.tag), 'a', buffering=1)
    clog = open(os.path.join(a.out, 'client-%s.txt' % a.tag), 'a', buffering=1)
    op, q, fr, B = build(a.payload, a.len)
    st = Stats(); stop = threading.Event(); go = threading.Event()
    clog.write('# start %s payload=%s n=%d len=%d body=%d frame=%d pid=%d\n' % (
        time.strftime('%Y-%m-%dT%H:%M:%S%z'), a.payload, a.n, len(q), B, len(fr), os.getpid()))
    threads = [threading.Thread(target=worker, args=(i, fr, st, stop, comp, go, a.hold_s, a.count), daemon=True)
               for i in range(a.n)]
    for t in threads: t.start()
    dl = time.time() + 60
    while time.time() < dl:
        with st.lock:
            if st.est + st.err >= a.n: break
        time.sleep(0.1)
    clog.write('# established=%d body=%d at %d\n' % (st.est, B, time.time() * 1000))

    def sampler():
        while not stop.is_set():
            with st.lock:
                clog.write('%d %d %d %d %d %d %d\n' % (time.time() * 1000, st.open, st.est, st.out, st.done, st.err, st.out * B))
            time.sleep(1)
    threading.Thread(target=sampler, daemon=True).start()
    go.set()
    dl = time.time() + a.hold_s
    while time.time() < dl:
        if not any(t.is_alive() for t in threads):
            clog.write('# all connections ended at %d\n' % (time.time() * 1000)); break
        time.sleep(0.5)
    stop.set()
    clog.write('# end %d done=%d err=%d\n' % (time.time() * 1000, st.done, st.err))
    time.sleep(1.2)
    return 0


if __name__ == '__main__':
    sys.exit(main())
