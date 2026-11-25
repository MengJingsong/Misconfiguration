#!/usr/bin/env python3
"""B13 3-b confirm (2026-11-24): pre-auth check on protocol v5. One connection: STARTUP (v5) -> AUTHENTICATE, never
answered; then N QUERY messages (each its own v5 segment) on the unauthenticated connection; read every reply and print
opcode, error code, message and wire size; after 2 s send one more and read it (is the connection still open?).
  preauth5.py <host> [N=3] [query]"""
import io, os, socket, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import drv
drv.load()
from cassandra.protocol import StartupMessage, QueryMessage, _ProtocolHandler
from cassandra.segment import SegmentCodec

host = sys.argv[1]; N = int(sys.argv[2]) if len(sys.argv) > 2 else 3
Q = sys.argv[3] if len(sys.argv) > 3 else 'SELECT v FROM b13.t WHERE pk = 0'
codec = SegmentCodec()
hl = codec.header_length_with_crc
hl = hl() if callable(hl) else hl


def rx(s, n):
    b = b''
    while len(b) < n:
        c = s.recv(n - len(b))
        if not c:
            raise EOFError('closed by server')
        b += c
    return b


def seg_envelopes(s):
    hdr = rx(s, hl); h = codec.decode_header(io.BytesIO(hdr))
    p = codec.decode(io.BytesIO(rx(s, h.payload_length + 4)), h).payload
    out = []; i = 0
    while i + 9 <= len(p):
        _, _, st, op, ln = struct.unpack('>BBhBi', p[i:i + 9]); body = p[i + 9:i + 9 + ln]; i += 9 + ln
        out.append((st, op, body))
    return hl + h.payload_length + 4, out


def show(tag, wire, envs):
    for st, op, body in envs:
        if op == 0:
            code = struct.unpack('>i', body[:4])[0]; ml = struct.unpack('>H', body[4:6])[0]
            print(f'{tag}: stream {st} ERROR code {code:#06x} "{body[6:6 + ml].decode(errors="replace")}" envelope {9 + len(body)} B; segment {wire} B for {len(envs)} envelope(s)')
        else:
            print(f'{tag}: stream {st} opcode {op:#04x} body {len(body)} B; segment {wire} B')


s = socket.create_connection((host, 9042), timeout=5)
s.sendall(_ProtocolHandler.encode_message(StartupMessage('3.0.0', {}), 0, 5, None, False))
v, f, st, op, ln = struct.unpack('>BBhBi', rx(s, 9)); body = rx(s, ln)
print(f'STARTUP (v5) -> opcode {op:#04x} {"AUTHENTICATE " + body[2:].decode(errors="replace") if op == 3 else ""}')
enc = lambda i: (lambda b: (codec.encode(b, _ProtocolHandler.encode_message(QueryMessage(Q, 1), i, 5, None, False)), b.getvalue())[1])(io.BytesIO())
reqs = [enc(i + 1) for i in range(N)]
print(f'sending {N} QUERY "{Q}" unauthenticated, {len(reqs[0])} B each')
s.sendall(b''.join(reqs))
got = 0
while got < N:
    wire, envs = seg_envelopes(s); show('reply', wire, envs); got += len(envs)
time.sleep(2)
try:
    s.sendall(enc(N + 1)); wire, envs = seg_envelopes(s); show('after 2 s, one more', wire, envs)
    print('connection still open: yes')
except Exception as e:
    print(f'connection still open: no ({type(e).__name__} {e})')
s.close()
