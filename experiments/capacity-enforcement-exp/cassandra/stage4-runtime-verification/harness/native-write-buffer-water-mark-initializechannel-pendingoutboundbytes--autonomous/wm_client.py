import socket, struct, sys, time, argparse, threading
p = argparse.ArgumentParser()
p.add_argument('--port', type=int, default=19142); p.add_argument('--mode', choices=['insert','flood','read'])
p.add_argument('--k', type=int, default=256); p.add_argument('--page', type=int, default=0)
p.add_argument('--hold', type=int, default=60); a = p.parse_args()
def s(x): b = x.encode(); return struct.pack('>H', len(b)) + b
def frame(st, op, body): return struct.pack('>BBhBi', 4, 0, st, op, len(body)) + body
def q(text, page=0):
    b = text.encode(); body = struct.pack('>i', len(b)) + b + struct.pack('>H', 1)
    return body + (b'\x04' + struct.pack('>i', page) if page else b'\x00')
def rd(sock, n):
    out = b''
    while len(out) < n:
        c = sock.recv(n - len(out))
        if not c: raise EOFError
        out += c
    return out
def read_frame(sock):
    h = rd(sock, 9); op = h[4]; n = struct.unpack('>i', h[5:9])[0]; body = rd(sock, n)
    if op == 0: raise RuntimeError('ERROR frame: %r' % body[:200])
    return 9 + n
sock = socket.socket(); sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
sock.connect(('127.0.0.1', a.port)); sock.sendall(frame(0, 1, struct.pack('>H', 1) + s('CQL_VERSION') + s('3.0.0'))); read_frame(sock)
print('local port', sock.getsockname()[1], flush=True)
SEL = 'SELECT v FROM wm.t WHERE k=0'
if a.mode == 'insert':
    for st in ["CREATE KEYSPACE IF NOT EXISTS wm WITH replication={'class':'SimpleStrategy','replication_factor':1}",
               "CREATE TABLE IF NOT EXISTS wm.t (k int, c int, v blob, PRIMARY KEY (k, c))"]:
        sock.sendall(frame(1, 7, q(st))); read_frame(sock)
    for c in range(1024):
        sock.sendall(frame(1, 7, q('INSERT INTO wm.t (k,c,v) VALUES (0,%d,0x%s)' % (c, 'ab' * 1024)))); read_frame(sock)
    print('inserted'); sys.exit(0)
got = [0]
if a.mode == 'read':
    t = threading.Thread(target=lambda: [got.__setitem__(0, got[0] + read_frame(sock)) for _ in range(a.k)]); t.start()
for i in range(a.k):
    sock.sendall(frame(i % 32768, 7, q(SEL, a.page))); time.sleep(0.01)
print('sent', a.k, 'at', time.time(), flush=True)
if a.mode == 'read':
    t.join(); print('read bytes', got[0]); sys.exit(0)
time.sleep(a.hold)                                 # operator samples during this window
print('draining at', time.time(), flush=True)
for _ in range(a.k): got[0] += read_frame(sock)
print('drained bytes', got[0], 'R', got[0] // a.k)
