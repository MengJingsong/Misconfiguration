#!/usr/bin/env python3
"""B13 stall5.py (from stage-4 stall-client.py). C raw sockets to <host>:9042, SO_RCVBUF 65,536 before connect, STARTUP/READY
at protocol v5, then paced waves: every <period> s write <w> QUERY messages to every socket (each its own self-contained CRC
frame, bundled driver codec), stream ids 1.. per socket, until <R> per socket are sent. Optional one burst: after
<burst_after> waves, write <burst> per socket at once (calibration arm). mode stall: never read after READY; mode drain:
one reader thread per socket that discards. On <stop-file>: close with SO_LINGER 0.
  stall5.py <host> <C> <R> <w> <period> <mode> <stop-file> [burst_after burst]
Prints LOAD_START <epoch_ms>, WAVE <epoch_ms> <sent_total>, SENT_ALL <epoch_ms> <sent_total>, CLOSED <epoch_ms>."""
import io, os, socket, struct, sys, time, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import drv
drv.load()
from cassandra.protocol import StartupMessage, QueryMessage, _ProtocolHandler
from cassandra.segment import SegmentCodec

host, C, R, w, period, mode, stop = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), float(sys.argv[5]), sys.argv[6], sys.argv[7]
burst_after = int(sys.argv[8]) if len(sys.argv) > 8 else -1
burst = int(sys.argv[9]) if len(sys.argv) > 9 else 0
ms = lambda: int(time.time() * 1000)


def recv_exact(s, n):
    b = b''
    while len(b) < n:
        c = s.recv(n - len(b))
        if not c:
            raise SystemExit('connection closed during the handshake')
        b += c
    return b


socks = []
for k in range(C):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
    s.connect((host, 9042))
    s.sendall(_ProtocolHandler.encode_message(StartupMessage('3.0.0', {}), 0, 5, None, False))
    ver, flags, stream, opcode, length = struct.unpack('>BBhBi', recv_exact(s, 9))
    recv_exact(s, length)
    if opcode != 0x02:
        raise SystemExit(f'expected READY (0x02), got opcode {opcode:#x}')
    socks.append(s)
print(f'READY {C} sockets; SO_RCVBUF {socks[0].getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)}; mode {mode}', flush=True)
codec = SegmentCodec()


def enc(k, i):
    msg = _ProtocolHandler.encode_message(QueryMessage(f'SELECT v FROM b13.t WHERE pk = {(k * 4 + i) % 64}', 1), (i % 32767) + 1, 5, None, False)
    b = io.BytesIO(); codec.encode(b, msg); return b.getvalue()


reqs = [[enc(k, i) for i in range(R)] for k in range(C)]
drained = [0] * C
if mode == 'drain':
    def reader(k):
        s = socks[k]
        try:
            while True:
                c = s.recv(1 << 20)
                if not c:
                    break
                drained[k] += len(c)
        except OSError:
            pass
    for k in range(C):
        threading.Thread(target=reader, args=(k,), daemon=True).start()
sent = [0] * C
t0 = time.time()
print(f'LOAD_START {ms()}', flush=True)
wave = 0
while min(sent) < R and not os.path.exists(stop):
    n = burst if wave == burst_after else w
    for k in range(C):
        m = min(n, R - sent[k])
        if m > 0:
            socks[k].sendall(b''.join(reqs[k][sent[k]:sent[k] + m]))
            sent[k] += m
    wave += 1
    print(f'WAVE {ms()} {sum(sent)}', flush=True)
    nxt = t0 + wave * period
    while time.time() < nxt and not os.path.exists(stop):
        time.sleep(min(0.05, max(0.0, nxt - time.time())))
print(f'SENT_ALL {ms()} {sum(sent)}', flush=True)
while not os.path.exists(stop):
    time.sleep(0.2)
for s in socks:
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0)); s.close()
    except OSError:
        pass
print(f'CLOSED {ms()} drained_bytes {sum(drained)}', flush=True)
