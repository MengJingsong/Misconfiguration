#!/usr/bin/env python3
"""U17 client: raw CQL native protocol v4 (unsegmented frames), standard library only. Frame I/O adapted from U6's
client.py (../ErrorCollector_errorMsgs--one-message-per-bad-character/harness/client.py).

  u17client.py --ddl D                 keyspace u17; tables t (vector<tinyint, D>), h (blob), w (vector<tinyint, 8192>)
  u17client.py --sizes --d D           print text/body/frame lengths of VEC, HEX, WB at dimension D
  u17client.py --payload {VEC,HEX,WB} --d D --n N --rounds R --out DIR
  u17client.py --readback              SELECT v FROM u17.t / SELECT b FROM u17.h / count of u17.w, print cell lengths
  u17client.py --payload PREP ...      C3 (added 2026-11-24 stage 2): each connection PREPAREs INSERT INTO u17.t (pk, v)
                                       VALUES (0, ?) once, then EXECUTEs it per round with the serialized vector
                                       (D x (vint 1, byte 0) = 2D bytes), CL ONE

Payloads (case file section 2, "Workload"), all unprepared QUERY at CL ONE, pk 0:
  VEC  INSERT INTO u17.t (pk, v) VALUES (0, [0,0,...,0])             (D elements, 2D + 39 characters)
  HEX  INSERT INTO u17.h (pk, b) VALUES (0, 0x00...00)               (D bytes, 2D + 40 characters)
  WB   BEGIN UNLOGGED BATCH + M x INSERT INTO u17.w (pk, ck, v) VALUES (0, <ck>, [8192 x 0]); + APPLY BATCH, M = D // 8192
N connections (one thread each), one request outstanding per connection; per round every live connection sends at
once (a coordinator releases them together) and the next round starts when every live connection has its answer.
Socket timeout 120 s (client side): a timeout is recorded and the client keeps waiting for that response; it does not
end the run. The run ends when R rounds finish or every connection is refused/reset.
Output: DIR/client.csv: send_ms,resp_ms,conn,round,body_bytes,opcode,err_code,msg  then  SUMMARY ...
"""
import argparse, os, socket, struct, sys, threading, time

HOST, PORT = '127.0.0.1', 9042
OP_ERROR, OP_STARTUP, OP_READY, OP_QUERY, OP_RESULT, OP_PREPARE, OP_EXECUTE = 0x00, 0x01, 0x02, 0x07, 0x08, 0x09, 0x0A
PREP_Q = 'INSERT INTO u17.t (pk, v) VALUES (0, ?)'
MAX_BODY = 16_777_207
CL_ONE = 0x0001


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
    def __init__(self, timeout=120, on_timeout=None):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        s.settimeout(30)
        s.connect((HOST, PORT))
        self.s = s; self.on_timeout = on_timeout
        s.sendall(frame(OP_STARTUP, struct.pack('>H', 1) + sstr('CQL_VERSION') + sstr('3.0.0')))
        op, b = self.recv()
        if op != OP_READY:
            raise RuntimeError('startup: op %d %s' % (op, err_text(b) if op == 0 else ''))
        s.settimeout(timeout)

    def recvn(self, n):
        buf = bytearray(n); mv = memoryview(buf); got = 0
        while got < n:
            try:
                r = self.s.recv_into(mv[got:], n - got)
            except socket.timeout:
                if self.on_timeout: self.on_timeout()
                continue
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

    def query(self, q):
        self.s.sendall(frame(OP_QUERY, lstr_b(q.encode()) + struct.pack('>HB', CL_ONE, 0)))
        op, b = self.recv()
        if op == OP_ERROR:
            raise RuntimeError('%x %s' % err_text(b))
        return b


def payload(p, d):
    if p == 'VEC':
        return b'INSERT INTO u17.t (pk, v) VALUES (0, [' + b'0,' * (d - 1) + b'0])'
    if p == 'HEX':
        return b'INSERT INTO u17.h (pk, b) VALUES (0, 0x' + b'00' * d + b')'
    if p == 'WB':
        m = d // 8192
        one = b'0,' * 8191 + b'0'
        parts = [b'BEGIN UNLOGGED BATCH ']
        for ck in range(m):
            parts.append(b'INSERT INTO u17.w (pk, ck, v) VALUES (0, ' + str(ck).encode() + b', [' + one + b']); ')
        parts.append(b'APPLY BATCH')
        return b''.join(parts)
    raise ValueError(p)


def build(p, d):
    q = payload(p, d)
    body = lstr_b(q) + struct.pack('>HB', CL_ONE, 0)
    return q, frame(OP_QUERY, body), len(body)


# ---- ROWS parsing for --readback (v4 result metadata) ----
def _opt(b, p):
    t = struct.unpack_from('>H', b, p)[0]; p += 2
    if t == 0x0000:
        l = struct.unpack_from('>H', b, p)[0]; p += 2 + l
    elif t in (0x0020, 0x0022):
        p = _opt(b, p)
    elif t == 0x0021:
        p = _opt(b, p); p = _opt(b, p)
    elif t in (0x0030, 0x0031):
        raise ValueError('udt/tuple not expected')
    return p


def rows_cells(b):
    kind = struct.unpack_from('>i', b, 0)[0]
    if kind != 2:
        return kind, []
    p = 4
    flags, ncol = struct.unpack_from('>ii', b, p); p += 8
    if flags & 0x0002:
        l = struct.unpack_from('>i', b, p)[0]; p += 4 + max(l, 0)
    if not flags & 0x0004:
        gts = flags & 0x0001
        if gts:
            for _ in range(2):
                l = struct.unpack_from('>H', b, p)[0]; p += 2 + l
        for _ in range(ncol):
            if not gts:
                for _ in range(2):
                    l = struct.unpack_from('>H', b, p)[0]; p += 2 + l
            l = struct.unpack_from('>H', b, p)[0]; p += 2 + l
            p = _opt(b, p)
    nrows = struct.unpack_from('>i', b, p)[0]; p += 4
    cells = []
    for _ in range(nrows):
        row = []
        for _ in range(ncol):
            l = struct.unpack_from('>i', b, p)[0]; p += 4
            row.append(l); p += max(l, 0)
        cells.append(row)
    return kind, cells


class Worker(threading.Thread):
    def __init__(self, i, fr, B, out, lock, rounds, d=0):
        super().__init__(daemon=True); self.d = d
        self.i, self.fr, self.B, self.out, self.lock, self.rounds = i, fr, B, out, lock, rounds
        self.go = threading.Event(); self.fin = threading.Event(); self.dead = False; self.r = 0
        self.timeouts = 0; self.done = 0; self.errs = 0

    def line(self, ts, te, op, code, msg):
        with self.lock:
            self.out.write('%d,%d,%d,%d,%d,%s,%s,%s\n' % (ts, te, self.i, self.r, self.B, op, code,
                                                       msg.replace(',', ';').replace('\n', ' ')[:120]))
            self.out.flush()

    def tmo(self):
        self.timeouts += 1
        self.line(self.ts, time.time() * 1000, 'timeout', '', 'client socket timeout 120 s; still waiting')

    def run(self):
        try:
            self.c = Conn(on_timeout=self.tmo)
        except Exception as e:
            self.dead = True; self.r = -1
            self.line(time.time() * 1000, time.time() * 1000, 'connect_error', '', str(e)[:100])
            self.fin.set(); return
        if self.fr is None:  # PREP: prepare once, then the EXECUTE frame with the 2D-byte bound value
            try:
                self.c.s.sendall(frame(OP_PREPARE, lstr_b(PREP_Q.encode())))
                op, b = self.c.recv()
                assert op == OP_RESULT and struct.unpack_from('>i', b)[0] == 4, (op, b[:60])
                l = struct.unpack_from('>H', b, 4)[0]; pid = b[6:6 + l]
                val = b'\x01\x00' * self.d
                body = struct.pack('>H', l) + pid + struct.pack('>HBH', CL_ONE, 0x01, 1) + lstr_b(val)
                self.fr = frame(OP_EXECUTE, body); self.B = len(body)
            except Exception as e:
                self.dead = True; self.r = -1
                self.line(time.time() * 1000, time.time() * 1000, 'prepare_error', '', str(e)[:100])
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
                kind = struct.unpack_from('>i', b)[0] if len(b) >= 4 else -1
                self.done += 1
                self.line(self.ts, te, '0x%02x' % op, '', 'kind=%d' % kind)
            self.fin.set()
        try: self.c.s.close()
        except Exception: pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ddl', type=int); ap.add_argument('--sizes', action='store_true')
    ap.add_argument('--readback', action='store_true')
    ap.add_argument('--payload', choices=['VEC', 'HEX', 'WB', 'PREP']); ap.add_argument('--d', type=int, default=6_000_000)
    ap.add_argument('--n', type=int, default=1); ap.add_argument('--rounds', type=int, default=5)
    ap.add_argument('--out', default='.')
    a = ap.parse_args()
    if a.ddl:
        c = Conn()
        c.query("CREATE KEYSPACE IF NOT EXISTS u17 WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
        c.query('CREATE TABLE IF NOT EXISTS u17.t (pk int PRIMARY KEY, v vector<tinyint, %d>)' % a.ddl)
        c.query('CREATE TABLE IF NOT EXISTS u17.h (pk int PRIMARY KEY, b blob)')
        c.query('CREATE TABLE IF NOT EXISTS u17.w (pk int, ck int, v vector<tinyint, 8192>, PRIMARY KEY (pk, ck))')
        print('ddl ok D=%d' % a.ddl); return 0
    if a.sizes:
        for p in ('VEC', 'HEX', 'WB'):
            q, fr, B = build(p, a.d)
            print('%s d=%d text=%d body=%d frame=%d%s' % (p, a.d, len(q), B, len(fr),
                  ' M=%d elements=%d' % (a.d // 8192, a.d // 8192 * 8192) if p == 'WB' else ''))
        return 0
    if a.readback:
        c = Conn()
        for q in ('SELECT v FROM u17.t WHERE pk = 0', 'SELECT b FROM u17.h WHERE pk = 0',
                  'SELECT ck FROM u17.w WHERE pk = 0'):
            try:
                kind, cells = rows_cells(c.query(q))
                if 'u17.w' in q:
                    print('readback %s rows=%d' % (q, len(cells)))
                else:
                    print('readback %s rows=%d cell_len=%s' % (q, len(cells), [r[0] for r in cells]))
            except Exception as e:
                print('readback %s ERROR %s' % (q, str(e)[:200]))
        return 0
    if a.payload == 'PREP':
        q, fr, B = PREP_Q.encode(), None, 2 + 16 + 5 + 4 + 2 * a.d
    else:
        q, fr, B = build(a.payload, a.d)
    if B > MAX_BODY:
        print('REFUSE body %d > %d' % (B, MAX_BODY)); return 1
    os.makedirs(a.out, exist_ok=True)
    out = open(os.path.join(a.out, 'client.csv'), 'a')
    out.write('# start %s payload=%s d=%d n=%d rounds=%d text=%d body=%d frame=%d pid=%d\n' % (
        time.strftime('%Y-%m-%dT%H:%M:%S%z'), a.payload, a.d, a.n, a.rounds, len(q), B, len(fr) if fr else B + 9, os.getpid()))
    out.write('send_ms,resp_ms,conn,round,body_bytes,opcode,err_code,msg\n'); out.flush()
    lock = threading.Lock()
    ws = [Worker(i, fr, B, out, lock, a.rounds, a.d) for i in range(a.n)]
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
