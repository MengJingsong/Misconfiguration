#!/usr/bin/env python3
"""usage: stall-client.py <R> <stop-file>     (networking_cache_size case 9c)
Raw socket to 127.0.0.1:9042 with SO_RCVBUF 65,536 set before connect. STARTUP (protocol v5, unframed) and READY, then R QUERY
messages 'SELECT v FROM ks1.t WHERE pk = <i mod 8>' at ONE, each in its own self-contained CRC frame encoded with the bundled
driver's cassandra.protocol and cassandra.segment.SegmentCodec, written in one burst; never reads after READY. When <stop-file>
exists it closes with SO_LINGER 0. Prints the bytes written and the socket's receive buffer."""
import io, os, socket, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import drv
drv.load()
from cassandra.protocol import StartupMessage, QueryMessage, _ProtocolHandler
from cassandra.segment import SegmentCodec

R, stop = int(sys.argv[1]), sys.argv[2]
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
s.connect(('127.0.0.1', 9042))
rcvbuf = s.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
s.sendall(_ProtocolHandler.encode_message(StartupMessage('3.0.0', {}), 0, 5, None, False))


def recv_exact(n):
    b = b''
    while len(b) < n:
        c = s.recv(n - len(b))
        if not c:
            raise SystemExit('connection closed during the handshake')
        b += c
    return b


hdr = recv_exact(9)
ver, flags, stream, opcode, length = struct.unpack('>BBhBi', hdr)
recv_exact(length)
if opcode != 0x02:
    raise SystemExit(f'expected READY (0x02), got opcode {opcode:#x}')
codec = SegmentCodec()
buf = io.BytesIO()
for i in range(R):
    msg = _ProtocolHandler.encode_message(QueryMessage(f'SELECT v FROM ks1.t WHERE pk = {i % 8}', 1), (i % 30000) + 1, 5, None, False)
    codec.encode(buf, msg)
data = buf.getvalue()
s.sendall(data)
print(f'READY; wrote {R} requests in {len(data)} bytes; SO_RCVBUF {rcvbuf}', flush=True)
while not os.path.exists(stop):
    time.sleep(0.2)
s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
s.close()
print('closed', flush=True)
