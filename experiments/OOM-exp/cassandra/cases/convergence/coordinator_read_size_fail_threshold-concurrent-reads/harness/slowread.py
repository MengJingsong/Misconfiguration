#!/usr/bin/env python3
"""C2 slow-consumer client (apt138): raw CQL native protocol v4, no driver.
  slowread.py <host> <conns> <steps "perconn:secs,..."> <total_seconds_cap> <drainKBps_per_conn> [rcvbuf=65536] [pks=64]
Opens <conns> connections (STARTUP only), then per step tops every connection up to <perconn> outstanding
QUERY requests (outstanding total = conns x perconn) and holds it for <secs>; keeps them outstanding
(SELECT v FROM c2.t WHERE pk=<random>, CL ONE, page size 5000), and reads each socket at most
<drainKBps_per_conn> KiB/s (token bucket; 0 = unlimited). Every complete response is replaced by a new
request on the same stream (closed loop). SO_RCVBUF is set to <rcvbuf> before connect (client choice).
Prints one CSV line per second: t,outstanding,responses,errors,MBps,lastErr ; ends with SUMMARY.
Each read is the same 3.5 MiB single-page read as C2Load; only the client's drain rate differs."""
import random, selectors, socket, struct, sys, time

host, conns, steps, secs, kbps = sys.argv[1], int(sys.argv[2]), [tuple(int(x) for x in st.split(':')) for st in sys.argv[3].split(',')], float(sys.argv[4]), float(sys.argv[5])
rcvbuf = int(sys.argv[6]) if len(sys.argv) > 6 else 65536
pks = int(sys.argv[7]) if len(sys.argv) > 7 else 64
rnd = random.Random(7)


def frame(stream, opcode, body):
    return struct.pack('>BBhBi', 4, 0, stream, opcode, len(body)) + body


def startup():
    m = {b'CQL_VERSION': b'3.0.0'}
    b = struct.pack('>H', len(m))
    for k, v in m.items():
        b += struct.pack('>H', len(k)) + k + struct.pack('>H', len(v)) + v
    return frame(0, 0x01, b)


def query(stream):
    q = ('SELECT v FROM c2.t WHERE pk=%d' % rnd.randrange(pks)).encode()
    body = struct.pack('>i', len(q)) + q + struct.pack('>HBi', 0x0001, 0x04, 5000)
    return frame(stream, 0x07, body)


class Conn:
    def __init__(s, i):
        s.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, rcvbuf)
        s.sock.connect((host, 9042))
        s.sock.sendall(startup())
        hdr = s.recvn(9)
        _, _, _, op, ln = struct.unpack('>BBhBi', hdr)
        s.recvn(ln)
        assert op == 0x02, 'expected READY, got opcode %d' % op
        s.sock.setblocking(False)
        s.buf = bytearray(); s.need = None; s.tokens = 0.0; s.last = time.time()
        s.out = 0; s.nstreams = 0

    def topup(s, n):
        s.sock.setblocking(True)
        while s.nstreams < n:
            s.nstreams += 1; s.sock.sendall(query(s.nstreams)); s.out += 1
        s.sock.setblocking(False)

    def recvn(s, n):
        b = b''
        while len(b) < n:
            c = s.sock.recv(n - len(b))
            if not c:
                raise EOFError('closed')
            b += c
        return b


print('t,outstanding,responses,errors,MBps,lastErr,step_perconn', flush=True)
cs = []
for i in range(conns):
    cs.append(Conn(i))
print('# %d connections ready' % conns, flush=True)
sel = selectors.DefaultSelector()
for c in cs:
    sel.register(c.sock, selectors.EVENT_READ, c)
resp = err = 0; nbytes = 0; lasterr = ''
t0 = time.time(); tick = t0 + 1; last_resp = 0; last_bytes = 0
rate = kbps * 1024
si = -1; step_end = t0
while time.time() - t0 < secs:
    now = time.time()
    if now >= step_end:
        si += 1
        if si >= len(steps):
            break
        pc, ss = steps[si]; step_end = now + ss
        for c in cs:
            if c.sock.fileno() >= 0 and c.out >= 0:
                try:
                    c.topup(pc)
                except Exception as e:
                    lasterr = 'send ' + type(e).__name__
    if now >= tick:
        print('%d,%d,%d,%d,%.1f,%s,%d' % (int(now * 1000), sum(c.out for c in cs), resp, err, (nbytes - last_bytes) / 1048576.0, lasterr, steps[si][0]), flush=True)
        last_bytes = nbytes; lasterr = ''; tick += 1
    ev = sel.select(timeout=0.02)
    for key, _ in ev:
        c = key.data
        if rate > 0:
            c.tokens = min(c.tokens + (now - c.last) * rate, max(rate * 0.1, 65536)); c.last = now
            want = int(c.tokens)
            if want <= 0:
                continue
        else:
            want = 1 << 20
        try:
            d = c.sock.recv(min(want, 1 << 20))
        except BlockingIOError:
            continue
        except Exception as e:
            lasterr = 'recv ' + type(e).__name__; sel.unregister(c.sock); c.out = 0; continue
        if not d:
            lasterr = 'closed by server'; sel.unregister(c.sock); c.out = 0; continue
        if rate > 0:
            c.tokens -= len(d)
        nbytes += len(d); c.buf += d
        while True:
            if len(c.buf) < 9:
                break
            _, _, st, op, ln = struct.unpack('>BBhBi', bytes(c.buf[:9]))
            if len(c.buf) < 9 + ln:
                break
            body = bytes(c.buf[9:9 + ln]); del c.buf[:9 + ln]
            if op == 0x00:
                err += 1; lasterr = body[6:120].decode(errors='replace').replace(',', ';')
            else:
                resp += 1
            c.sock.setblocking(True); c.sock.sendall(query(st)); c.sock.setblocking(False)
    if rate > 0:
        # idle wait so token buckets refill without busy-looping over readable sockets
        time.sleep(0.005)
print('SUMMARY secs=%.0f responses=%d errors=%d MB=%.0f' % (time.time() - t0, resp, err, nbytes / 1048576.0), flush=True)
