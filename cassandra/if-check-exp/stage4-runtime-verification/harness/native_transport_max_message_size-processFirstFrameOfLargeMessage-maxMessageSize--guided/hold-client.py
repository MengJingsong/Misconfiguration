#!/usr/bin/env python3
"""usage: hold-client.py --conns N --blob B --hold-s S [--ctl-kib 64] [--idle-s 8] [--host 127.0.0.1]
(native_transport_max_message_size case 9c, amended R1: the raw v5 client hold_large_request.py of 9c, written here)

N raw sockets to <host>:9042, protocol v5 (STARTUP/READY unframed, then CRC frames from the bundled driver's SegmentCodec).
Connection 0 prepares "INSERT INTO ks.t (pk, v) VALUES (?, ?)"; if --ctl-kib > 0 it executes one single-frame request with a
blob of that size (9e control run). It then idles --idle-s seconds (the pool baseline, connection open and idle). Each
connection i then gets its own thread, which writes every frame but the last of one EXECUTE with pk 1000 + i and a blob of
B bytes (in 131,071-byte frames, as the drivers split a message). The main thread prints HELD when every thread has written
all but its last frame, or has made no progress for 3 s (a connection the server paused), then holds --hold-s seconds. Then,
connection by connection, it waits (up to 180 s) for the thread to finish, writes the last frame and reads the response.
Finally connection 0 sends one more single-frame request (the connection still works, 6b).
Event lines on stdout, one per event, flushed:
  READY conn=<i> ms=   PREPARED id=<hex> ms=   CTL resp=<...> ms=   IDLE ms=
  SEND conn=<i> frames=<n> env=<envelope bytes> body=<body bytes> ms=     SENT conn=<i> frames=<n-1> bytes=<written> ms=
  HELD ms= sent=<bytes per conn>      LAST conn=<i> ms=      RESP conn=<i> opcode= code= msg=<text, spaces as _> ms=
  FOLLOW resp=<...> ms=      DONE ms=
"""
import argparse, os, random, socket, struct, sys, threading, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import drv
drv.load()
from cassandra.protocol import StartupMessage, PrepareMessage, ExecuteMessage, _ProtocolHandler
from cassandra.segment import SegmentCodec, Segment
from cassandra import ConsistencyLevel
import io

ap = argparse.ArgumentParser()
ap.add_argument('--conns', type=int, default=1)
ap.add_argument('--blob', type=int, required=True)
ap.add_argument('--hold-s', type=float, default=30)
ap.add_argument('--ctl-kib', type=int, default=64)
ap.add_argument('--idle-s', type=float, default=8)
ap.add_argument('--host', default='127.0.0.1')
a = ap.parse_args()
MAX = Segment.MAX_PAYLOAD_LENGTH          # 131,071
codec = SegmentCodec()


def ms():
    return int(time.time() * 1000)


def ev(s):
    print(f'{s} ms={ms()}', flush=True)


def recv_exact(s, n):
    b = bytearray()
    while len(b) < n:
        c = s.recv(n - len(b))
        if not c:
            raise IOError('connection closed')
        b += c
    return bytes(b)


def connect(i):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    s.connect((a.host, 9042))
    s.sendall(_ProtocolHandler.encode_message(StartupMessage('3.0.0', {}), 0, 5, None, False))
    hdr = recv_exact(s, 9)
    ver, flags, stream, opcode, length = struct.unpack('>BBhBi', hdr)
    recv_exact(s, length)
    if opcode != 0x02:
        raise SystemExit(f'conn {i}: expected READY, got opcode {opcode:#x}')
    ev(f'READY conn={i}')
    return s


def segments(env):
    """the envelope as CRC frames: one self-contained frame if it fits, else 131,071-byte non-self-contained frames"""
    out = []
    parts = [env] if len(env) <= MAX else [env[k:k + MAX] for k in range(0, len(env), MAX)]
    for p in parts:
        b = io.BytesIO()
        codec._encode_segment(b, p, len(parts) == 1)
        out.append(b.getvalue())
    return out


def read_response(s):
    """one frame from the server; the first envelope in it -> (opcode, code or kind, message, body)"""
    h = recv_exact(s, 6)
    hdr = h[0] | (h[1] << 8) | (h[2] << 16)
    n = hdr & 0x1FFFF
    p = recv_exact(s, n)
    recv_exact(s, 4)
    ver, flags, stream, opcode, length = struct.unpack('>BBhBi', p[:9])
    body = p[9:9 + length]
    off = 0
    if flags & 0x02:                      # tracing id
        off += 16
    if flags & 0x08:                      # warnings: [string list]
        k = struct.unpack('>H', body[off:off + 2])[0]; off += 2
        for _ in range(k):
            sl = struct.unpack('>H', body[off:off + 2])[0]; off += 2 + sl
    body = body[off:]
    if opcode == 0x00:
        code = struct.unpack('>i', body[:4])[0]
        sl = struct.unpack('>H', body[4:6])[0]
        return opcode, code, body[6:6 + sl].decode('utf-8', 'replace'), body
    if opcode == 0x08:
        return opcode, struct.unpack('>i', body[:4])[0], '', body
    return opcode, -1, '', body


def fmt(r):
    return f'opcode={r[0]} code={r[1]} msg={r[2].replace(" ", "_")[:300]}'


conns = [connect(i) for i in range(a.conns)]
c0 = conns[0]
c0.sendall(segments(_ProtocolHandler.encode_message(PrepareMessage('INSERT INTO ks.t (pk, v) VALUES (?, ?)'), 1, 5, None, False))[0])
r = read_response(c0)
if r[0] != 0x08 or r[1] != 4:
    raise SystemExit('PREPARE failed: ' + fmt(r))
b = r[3][4:]
il = struct.unpack('>H', b[:2])[0]; qid = b[2:2 + il]; b = b[2 + il:]
ml = struct.unpack('>H', b[:2])[0]; rmid = b[2:2 + ml]
ev(f'PREPARED id={qid.hex()}')


def execute(stream, pk, blob):
    m = ExecuteMessage(qid, [struct.pack('>i', pk), blob], ConsistencyLevel.ONE, result_metadata_id=rmid)
    return _ProtocolHandler.encode_message(m, stream, 5, None, False)


if a.ctl_kib > 0:
    c0.sendall(segments(execute(2, 1, bytes(a.ctl_kib * 1024)))[0])
    ev('CTL resp=' + fmt(read_response(c0)).replace(' ', ','))
ev('IDLE')
time.sleep(a.idle_s)

rnd = random.Random(1000)
blob = rnd.randbytes(a.blob)
plans = []
for i in range(a.conns):
    env = execute(10 + i, 1000 + i, blob)
    plans.append(segments(env))
    ev(f'SEND conn={i} frames={len(plans[i])} env={len(env)} body={len(env) - 9}')
written = [0] * a.conns
done = [threading.Event() for _ in range(a.conns)]


def sender(i):
    for seg in plans[i][:-1]:
        conns[i].sendall(seg)
        written[i] += len(seg)
    ev(f'SENT conn={i} frames={len(plans[i]) - 1} bytes={written[i]}')
    done[i].set()


threads = [threading.Thread(target=sender, args=(i,), daemon=True) for i in range(a.conns)]
for t in threads:
    t.start()
last = list(written); still = [0.0] * a.conns
t0 = time.time()
while time.time() - t0 < 120:
    time.sleep(0.2)
    for i in range(a.conns):
        if written[i] != last[i]:
            last[i] = written[i]; still[i] = 0.0
        else:
            still[i] += 0.2
    if all(done[i].is_set() or still[i] >= 3.0 for i in range(a.conns)):
        break
ev('HELD sent=' + '/'.join(str(w) for w in written) + ' done=' + '/'.join('1' if d.is_set() else '0' for d in done))
time.sleep(a.hold_s)
for i in range(a.conns):
    if not done[i].wait(180):
        ev(f'RESP conn={i} opcode=-1 code=-1 msg=sender_did_not_finish written={written[i]}')
        continue
    conns[i].sendall(plans[i][-1])
    ev(f'LAST conn={i}')
    conns[i].settimeout(120)
    try:
        ev(f'RESP conn={i} ' + fmt(read_response(conns[i])))
    except Exception as e:
        ev(f'RESP conn={i} opcode=-1 code=-1 msg={type(e).__name__}:{str(e).replace(" ", "_")}')
try:
    c0.settimeout(60)
    c0.sendall(segments(execute(3, 2, bytes(64 * 1024)))[0])
    ev('FOLLOW resp=' + fmt(read_response(c0)).replace(' ', ','))
except Exception as e:
    ev(f'FOLLOW resp=error:{type(e).__name__}')
for s in conns:
    s.close()
ev('DONE')
