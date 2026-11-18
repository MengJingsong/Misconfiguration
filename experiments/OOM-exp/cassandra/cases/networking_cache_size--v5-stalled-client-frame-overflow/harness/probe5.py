#!/usr/bin/env python3
"""B13 probe5.py: one protocol-v5 connection that reads normally; once per second sends
SELECT release_version FROM system.local (CL ONE) and waits <= 2 s. Logs: epoch_ms,ok|timeout|error,latency_ms.
Reconnects after an error. Stops on <stop-file>.   probe5.py <host> <stop-file>"""
import io, os, socket, struct, sys, time, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import drv
drv.load()
from cassandra.protocol import StartupMessage, QueryMessage, _ProtocolHandler
from cassandra.segment import SegmentCodec

host, stop = sys.argv[1], sys.argv[2]
ms = lambda: int(time.time() * 1000)
codec = SegmentCodec()
got = {}; cv = threading.Condition()


def recv_exact(s, n):
    b = bytearray()
    while len(b) < n:
        c = s.recv(n - len(b))
        if not c:
            raise OSError('closed')
        b += c
    return bytes(b)


def reader(s):
    buf = b''
    try:
        while True:
            h = recv_exact(s, 6)
            v = int.from_bytes(h[:3], 'little'); plen = v & 0x1FFFF
            buf += recv_exact(s, plen + 4)[:plen]
            while len(buf) >= 9:
                ver, flags, stream, opcode, length = struct.unpack('>BBhBi', buf[:9])
                if len(buf) < 9 + length:
                    break
                buf = buf[9 + length:]
                with cv:
                    got[stream] = (opcode, time.time()); cv.notify_all()
    except OSError:
        with cv:
            got[-1] = ('closed', time.time()); cv.notify_all()


def connect():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.settimeout(5)
    s.connect((host, 9042)); s.settimeout(None)
    s.sendall(_ProtocolHandler.encode_message(StartupMessage('3.0.0', {}), 0, 5, None, False))
    ver, flags, stream, opcode, length = struct.unpack('>BBhBi', recv_exact(s, 9)); recv_exact(s, length)
    got.clear(); threading.Thread(target=reader, args=(s,), daemon=True).start(); return s


print('epoch_ms,status,latency_ms', flush=True)
s = None; sid = 0
while not os.path.exists(stop):
    t = time.time()
    try:
        if s is None:
            s = connect()
        sid = sid % 30000 + 1
        b = io.BytesIO(); codec.encode(b, _ProtocolHandler.encode_message(QueryMessage('SELECT release_version FROM system.local', 1), sid, 5, None, False))
        s.sendall(b.getvalue())
        with cv:
            cv.wait_for(lambda: sid in got or -1 in got, timeout=2.0)
            r = got.pop(sid, None); closed = -1 in got
        if r is not None:
            st = 'ok' if r[0] == 0x08 else f'error_op{r[0]:#x}'
            print(f'{int(t*1000)},{st},{int((r[1]-t)*1000)}', flush=True)
        elif closed:
            raise OSError('connection closed')
        else:
            print(f'{int(t*1000)},timeout,2000', flush=True)
    except Exception as e:
        print(f'{int(t*1000)},error,{type(e).__name__}', flush=True)
        try:
            s and s.close()
        except Exception:
            pass
        s = None
    d = t + 1.0 - time.time()
    if d > 0:
        time.sleep(d)
