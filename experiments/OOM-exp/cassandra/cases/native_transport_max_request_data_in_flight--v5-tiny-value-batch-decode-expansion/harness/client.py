#!/usr/bin/env python3
"""R13 client (from B14's client.py; keyspace r13, arm Cp, --last-delay, sent_first): raw CQL native protocol v5
(segments, uncompressed), standard library only.

  client.py --ddl                      create keyspace r13, tables r13.t (50 tinyint columns) and r13.big (blob)
  client.py --bodylen                  offline check: body bytes, key offsets per partition, segments per arm
  client.py --arm {T,C,P,Cp} --conn-start S --conn-n M --hold-s H --out DIR [--tag p0] [--last-delay S]

Arms (case file section 2.4):
  T   LOGGED BATCH of 55,000 prepared INSERTs into r13.t, one partition, c = 0..54,999, 50 one-byte tinyint values each
  C   LOGGED BATCH of 64 prepared INSERTs into r13.big, one partition, c = 0..63, one 246,599-byte blob each
  P   payload T with statements 27,500..54,999 on key k+500,000 (two partitions)          [R13 test arm]
  Cp  payload C with statements 32..63 on key k+500,000 (two partitions)                   [R13 matched control C']
Connection i binds to source address 127.1.(i // 250).(1 + i % 250). Each connection: STARTUP (unframed v5) -> READY ->
PREPARE (framed) -> closed loop, one BATCH outstanding: patch the partition keys into the connection's copy of the body,
segment-encode, send, wait for the response. --last-delay S: send all but the last segment, sleep S, send the last one.
Segment codec: the bundled python driver's cassandra/segment.py algorithm (CRC24 init 0x875060 poly 0x1974F0B over the
3-byte LE header, CRC32 with initial value crc32(fa 2d 55 ca) over the payload, payload <= 131,071 bytes, self-contained
flag bit 17 only when the envelope fits one segment), re-implemented here to avoid importing the driver package.
Logs: DIR/completions-<tag>.txt (t_ms conn latency_ms status k=..) and DIR/client-<tag>.txt (per second:
t_ms open established outstanding completed errors K_client sent_first), t_ms = epoch ms. Statuses keep the server
error code (0x2200 Invalid = "Batch too large", 0x1100 WriteTimeout, 0x1001 Overloaded).
"""
import argparse, io, os, socket, struct, sys, threading, time, zlib

HOST, PORT = '127.0.0.1', 9042
OP_ERROR, OP_STARTUP, OP_READY, OP_QUERY, OP_RESULT, OP_PREPARE, OP_BATCH = 0x00, 0x01, 0x02, 0x07, 0x08, 0x09, 0x0D
NCOLS = 50
T_N = 55_000
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


class Conn:
    def __init__(self, i, timeout=60):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        s.bind(('127.1.%d.%d' % (i // 250, 1 + i % 250), 0))
        s.settimeout(timeout)
        s.connect((HOST, PORT))
        self.s = s; self.buf = b''
        body = struct.pack('>H', 1) + sstr('CQL_VERSION') + sstr('3.0.0')
        s.sendall(envelope(OP_STARTUP, body))           # unframed
        h = recvn(s, 9)
        ver, fl, st, op, ln = struct.unpack('>BBhBi', h)
        b = recvn(s, ln) if ln else b''
        if op != OP_READY:
            raise RuntimeError('startup: op %d %s' % (op, err_text(b) if op == 0 else ''))

    def send(self, env):
        self.s.sendall(b''.join(seg_encode(env)))

    def recv(self):
        """read segments until one complete envelope is buffered; return (op, body)"""
        while True:
            if len(self.buf) >= 9:
                ln = struct.unpack_from('>i', self.buf, 5)[0]
                if len(self.buf) >= 9 + ln:
                    flags = self.buf[1]; op = self.buf[4]; body = self.buf[9:9 + ln]; self.buf = self.buf[9 + ln:]
                    if flags & 0x02: body = body[16:]
                    if flags & 0x08:
                        n = struct.unpack_from('>H', body)[0]; p = 2
                        for _ in range(n):
                            l = struct.unpack_from('>H', body, p)[0]; p += 2 + l
                        body = body[p:]
                    return op, body
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


def err_text(body):
    code = struct.unpack_from('>i', body)[0]; l = struct.unpack_from('>H', body, 4)[0]
    return '0x%04x:%s' % (code, body[6:6 + l].decode('utf-8', 'replace')[:120].replace(' ', '_'))


def build_template(arm, sid):
    """-> (bytearray body, key offsets of the first partition, key offsets of the second partition)"""
    out = io.BytesIO(); offs1 = []; offs2 = []
    idb = struct.pack('>H', len(sid)) + sid
    if arm in ('T', 'P'):
        n = T_N
        vals = b''.join(struct.pack('>i', 1) + b'\x01' for _ in range(NCOLS))
        out.write(struct.pack('>BH', 0x00, n))
        for j in range(n):
            out.write(b'\x01' + idb + struct.pack('>H', NCOLS + 2) + struct.pack('>i', 4))
            (offs2 if (arm == 'P' and j >= n // 2) else offs1).append(out.tell())
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


def worker(i, arm, st, tmpl, stop, comp, go, last_delay):
    try:
        with st.lock: st.open += 1
        c = Conn(i)
        sid = c.prepare(stmt_for(arm))
        c.s.settimeout(None)
        with st.lock: st.est += 1
    except Exception as e:
        with st.lock: st.err += 1; st.open -= 1
        comp.write('%d %d -1 connect_error:%s\n' % (time.time() * 1000, i, str(e)[:100].replace(' ', '_')))
        return
    go.wait()
    body0, offs1, offs2, sid0 = tmpl['body'], tmpl['o1'], tmpl['o2'], tmpl['sid']
    if sid != sid0:
        comp.write('%d %d -1 statement_id_differs\n' % (time.time() * 1000, i)); return
    body = bytearray(body0)
    hdr = struct.pack('>BBhBi', 0x05, 0, 0, OP_BATCH, len(body))
    seq = 0
    while not stop.is_set():
        k = 1_000_000 * (i + 1) + seq; seq += 1
        for o in offs1: struct.pack_into('>i', body, o, k)
        for o in offs2: struct.pack_into('>i', body, o, k + 500_000)
        segs = seg_encode(hdr + body)
        ts = time.time(); first = False
        try:
            with st.lock: st.out += 1
            c.s.sendall(b''.join(segs[:3]))
            with st.lock: st.sf += 1
            first = True
            if last_delay > 0:
                c.s.sendall(b''.join(segs[3:-3])); time.sleep(last_delay); c.s.sendall(b''.join(segs[-3:]))
            else:
                c.s.sendall(b''.join(segs[3:]))
            op, b = c.recv()
            status = 'VOID' if op == OP_RESULT else ('ERR:' + err_text(b) if op == OP_ERROR else 'op%d' % op)
        except Exception as e:
            status = 'io_error:%s' % str(e)[:80].replace(' ', '_')
            with st.lock:
                st.out -= 1; st.err += 1
                if first: st.sf -= 1
            comp.write('%d %d %d %s\n' % (time.time() * 1000, i, (time.time() - ts) * 1000, status))
            break
        with st.lock:
            st.out -= 1; st.sf -= 1
            if status == 'VOID': st.done += 1
            else: st.err += 1
        comp.write('%d %d %d %s k=%d\n' % (time.time() * 1000, i, (time.time() - ts) * 1000, status, k))
    try: c.s.close()
    except Exception: pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ddl', action='store_true')
    ap.add_argument('--arm', choices=['T', 'C', 'P', 'Cp']); ap.add_argument('--conn-start', type=int, default=0)
    ap.add_argument('--conn-n', type=int, default=1); ap.add_argument('--hold-s', type=int, default=150)
    ap.add_argument('--out', default='.'); ap.add_argument('--tag', default='p0')
    ap.add_argument('--last-delay', type=float, default=0.0)
    ap.add_argument('--bodylen', action='store_true')
    a = ap.parse_args()
    if a.ddl:
        c = Conn(9999)
        c.query("CREATE KEYSPACE IF NOT EXISTS %s WITH replication = {'class':'SimpleStrategy','replication_factor':1}" % KS)
        c.query('CREATE TABLE IF NOT EXISTS %s.t (k int, c int, %s, PRIMARY KEY (k, c))' %
                (KS, ', '.join('v%02d tinyint' % i for i in range(NCOLS))))
        c.query('CREATE TABLE IF NOT EXISTS %s.big (k int, c int, v blob, PRIMARY KEY (k, c))' % KS)
        print('ddl ok'); return 0
    if a.bodylen:
        print('arm body_bytes offs1 offs2 segments')
        for arm in ('T', 'C', 'P', 'Cp'):
            body, o1, o2 = build_template(arm, b'\0' * 16)
            print(arm, len(body), len(o1), len(o2), len(seg_encode(envelope(OP_BATCH, bytes(body)))) // 3)
        return 0
    os.makedirs(a.out, exist_ok=True)
    comp = open(os.path.join(a.out, 'completions-%s.txt' % a.tag), 'a', buffering=1)
    clog = open(os.path.join(a.out, 'client-%s.txt' % a.tag), 'a', buffering=1)
    st = Stats(); stop = threading.Event(); go = threading.Event(); tmpl = {}
    clog.write('# start %s arm=%s conns=%d..%d last_delay=%s pid=%d\n' % (time.strftime('%Y-%m-%dT%H:%M:%S%z'), a.arm,
               a.conn_start, a.conn_start + a.conn_n - 1, a.last_delay, os.getpid()))
    threads = [threading.Thread(target=worker, args=(i, a.arm, st, tmpl, stop, comp, go, a.last_delay), daemon=True)
               for i in range(a.conn_start, a.conn_start + a.conn_n)]
    for t in threads: t.start()
    dl = time.time() + 120
    while time.time() < dl:
        with st.lock:
            if st.est + st.err >= a.conn_n: break
        time.sleep(0.2)
    c = Conn(a.conn_start + 5000)
    sid = c.prepare(stmt_for(a.arm)); c.s.close()
    body, o1, o2 = build_template(a.arm, sid)
    tmpl.update(body=body, o1=o1, o2=o2, sid=sid)
    B = len(body)
    clog.write('# established=%d body=%d offs=%d/%d at %d\n' % (st.est, B, len(o1), len(o2), time.time() * 1000))

    def sampler():
        while not stop.is_set():
            with st.lock:
                clog.write('%d %d %d %d %d %d %d %d\n' % (time.time() * 1000, st.open, st.est, st.out, st.done, st.err,
                                                          st.out * B, st.sf))
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
