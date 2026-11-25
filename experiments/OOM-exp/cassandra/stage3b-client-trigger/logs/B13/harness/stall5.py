#!/usr/bin/env python3
"""B13 stall5.py (from stage-4 stall-client.py). C raw sockets to <host>:9042, SO_RCVBUF 65,536 before connect, STARTUP/READY
at protocol v5, then paced waves: every <period> s write <w> QUERY messages to every socket (each its own self-contained CRC
frame, bundled driver codec), stream ids 1.. per socket, until <R> per socket are sent. Optional one burst: after
<burst_after> waves, write <burst> per socket at once (calibration arm). mode stall: never read after READY; mode drain:
one reader thread per socket that discards. On <stop-file>: close with SO_LINGER 0.
  stall5.py <host> <C> <R> <w> <period> <mode> <stop-file> [burst_after burst]
Prints LOAD_START <epoch_ms>, WAVE <epoch_ms> <sent_total>, SENT_ALL <epoch_ms> <sent_total>, CLOSED <epoch_ms>.

3-b confirm (2026-11-24), additions only:
  env B13_USER / B13_PASS set   -> STARTUP gets AUTHENTICATE (PasswordAuthenticator); the client answers with a SASL PLAIN
                                   AUTH_RESPONSE inside a v5 segment and requires AUTH_SUCCESS (0x10) before the load.
  env B13_PREAUTH=1             -> STARTUP gets AUTHENTICATE, which is never answered: the QUERY messages are sent on the
                                   unauthenticated connection (pre-auth arm).
  env B13_SAME=1               -> one encoded request per socket, repeated R times (large-R arms).
  env B13_QUERY                 -> the query text; '{pk}' is replaced by the partition number (default: the stage-2
                                   'SELECT v FROM b13.t WHERE pk = {pk}'). No paging options (as stage 2).
  mode 'drain' also prints the bytes drained per socket at close (used once to measure a response size)."""
import io, os, socket, struct, sys, time, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import drv
drv.load()
from cassandra.protocol import StartupMessage, QueryMessage, AuthResponseMessage, _ProtocolHandler
from cassandra.segment import SegmentCodec

host, C, R, w, period, mode, stop = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), float(sys.argv[5]), sys.argv[6], sys.argv[7]
burst_after = int(sys.argv[8]) if len(sys.argv) > 8 else -1
burst = int(sys.argv[9]) if len(sys.argv) > 9 else 0
USER, PASS = os.environ.get('B13_USER'), os.environ.get('B13_PASS')
PREAUTH = os.environ.get('B13_PREAUTH') == '1'
QTXT = os.environ.get('B13_QUERY', 'SELECT v FROM b13.t WHERE pk = {pk}')
ms = lambda: int(time.time() * 1000)
codec = SegmentCodec()
HL = codec.header_length_with_crc
HL = HL() if callable(HL) else HL


def recv_exact(s, n):
    b = b''
    while len(b) < n:
        c = s.recv(n - len(b))
        if not c:
            raise SystemExit('connection closed during the handshake')
        b += c
    return b


def read_segment_envelope(s):
    """Read one self-contained uncompressed v5 segment; return (opcode, body) of its first envelope."""
    hdr = recv_exact(s, HL)
    h = codec.decode_header(io.BytesIO(hdr))
    seg = codec.decode(io.BytesIO(recv_exact(s, h.payload_length + 4)), h)
    p = seg.payload
    _, _, _, op, ln = struct.unpack('>BBhBi', p[:9])
    return op, p[9:9 + ln]


def seg(msg_bytes):
    b = io.BytesIO(); codec.encode(b, msg_bytes); return b.getvalue()


socks = []
t_login0 = time.time()
for k in range(C):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
    s.connect((host, 9042))
    s.sendall(_ProtocolHandler.encode_message(StartupMessage('3.0.0', {}), 0, 5, None, False))
    ver, flags, stream, opcode, length = struct.unpack('>BBhBi', recv_exact(s, 9))
    body = recv_exact(s, length)
    if opcode == 0x03:  # AUTHENTICATE
        if PREAUTH:
            pass  # never answered
        elif USER is not None:
            tok = b'\0' + USER.encode() + b'\0' + PASS.encode()
            s.sendall(seg(_ProtocolHandler.encode_message(AuthResponseMessage(tok), 0, 5, None, False)))
            op, b2 = read_segment_envelope(s)
            if op != 0x10:
                raise SystemExit(f'expected AUTH_SUCCESS (0x10), got opcode {op:#x} {b2[:160]!r}')
        else:
            raise SystemExit('server asked for authentication; set B13_USER/B13_PASS or B13_PREAUTH=1')
    elif opcode != 0x02:
        raise SystemExit(f'expected READY (0x02), got opcode {opcode:#x}')
    elif PREAUTH or USER is not None:
        raise SystemExit('server sent READY: authentication is not on')
    socks.append(s)
print(f'READY {C} sockets; SO_RCVBUF {socks[0].getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)}; mode {mode}; '
      f'auth {"PREAUTH (AUTHENTICATE unanswered)" if PREAUTH else (USER or "none")}; handshakes {time.time() - t_login0:.1f} s; '
      f'query {QTXT!r}', flush=True)


def enc(k, i):
    msg = _ProtocolHandler.encode_message(QueryMessage(QTXT.format(pk=(k * 4 + i) % 64), 1), (i % 32767) + 1, 5, None, False)
    return seg(msg)


if os.environ.get('B13_SAME') == '1':   # one encoded request repeated (stream id 1, pk k*4 % 64): cheap for very large R
    reqs = [[enc(k, 0)] * R for k in range(C)]
else:
    reqs = [[enc(k, i) for i in range(R)] for k in range(C)]
print(f'REQ_BYTES {len(reqs[0][0])} (one request incl. segment framing)', flush=True)
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
print(f'CLOSED {ms()} drained_bytes {sum(drained)} per_socket {drained}', flush=True)
