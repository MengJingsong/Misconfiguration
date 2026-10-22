#!/usr/bin/env python3
# usage: v4load.py HOST PORT CONNS TOTAL_REQS BLOB_BYTES THROW(0|1) [setup]
import socket, struct, sys, threading, time
H, P, C, N, B, THROW = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), sys.argv[6] == '1'
SETUP = len(sys.argv) > 7 and sys.argv[7] == 'setup'
def frame(st, op, body): return struct.pack('>BBhBi', 0x04, 0, st, op, len(body)) + body
def s(x): b = x.encode(); return struct.pack('>H', len(b)) + b
def ls(x): b = x.encode(); return struct.pack('>i', len(b)) + b
def rx(k, n):
    buf = bytearray()
    while len(buf) < n:
        c = k.recv(min(1 << 20, n - len(buf)))
        if not c: raise EOFError
        buf += c
    return bytes(buf)
def rframe(k):
    _, _, st, op, ln = struct.unpack('>BBhBi', rx(k, 9)); return st, op, rx(k, ln)
def connect():
    k = socket.create_connection((H, P)); k.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    opts = {'CQL_VERSION': '3.0.0'}
    if THROW: opts['THROW_ON_OVERLOAD'] = '1'
    k.sendall(frame(0, 0x01, struct.pack('>H', len(opts)) + b''.join(s(a) + s(v) for a, v in opts.items())))
    _, op, body = rframe(k); assert op == 0x02, (op, body)       # READY
    return k
def q(st, cql, vals=None):
    body = ls(cql) + struct.pack('>H', 1)                         # consistency ONE
    body += b'\x00' if vals is None else b'\x01' + struct.pack('>H', len(vals)) + b''.join(struct.pack('>i', len(v)) + v for v in vals)
    return frame(st, 0x07, body)
if SETUP:
    k = connect()
    for i, c in enumerate(["CREATE KEYSPACE IF NOT EXISTS s3 WITH replication = {'class':'SimpleStrategy','replication_factor':1}",
                           "CREATE TABLE IF NOT EXISTS s3.t (k int PRIMARY KEY, v blob)"]):
        k.sendall(q(i + 1, c)); print(rframe(k)[1]); time.sleep(1)
    sys.exit(0)
blob = b'\xab' * B
per = N // C
res = {'ok': 0, 'overloaded': 0, 'other_err': 0}; lock = threading.Lock()
def worker(cid):
    k = connect()
    def reader():
        for _ in range(per):
            _, op, body = rframe(k)
            code = struct.unpack('>i', body[:4])[0] if op == 0x00 else None
            with lock:
                if op == 0x08: res['ok'] += 1
                elif code == 0x1001: res['overloaded'] += 1
                else: res['other_err'] += 1
    t = threading.Thread(target=reader); t.start()
    for i in range(per):
        key = cid * per + i
        k.sendall(q(1 + i % 32000, "INSERT INTO s3.t (k, v) VALUES (?, ?)", [struct.pack('>i', key), blob]))
    t.join(); k.close()
t0 = time.time(); ts = [threading.Thread(target=worker, args=(c,)) for c in range(C)]
[t.start() for t in ts]; [t.join() for t in ts]
print('RESULT', 'conns=%d reqs=%d blob=%d throw=%d secs=%.1f' % (C, N, B, THROW, time.time() - t0), res)
