# U2 stage 2 (2026-11-17) authenticated-service probe (case §2.5 item 3). Default AllowAllAuthenticator: STARTUP needs no credentials.
# usage: python3 service_probe.py <host> <port>
# Persistent connection: one QUERY every 0.5 s (2 s timeout): "P t_ms ok lat_ms" / "P t_ms err <e>"; reconnect every 5 s when broken.
# Every 5 s one NEW connection (STARTUP + one QUERY + close, 2 s timeouts): "N t_ms ok lat_ms" / "N t_ms err <e>". Runs until killed.
import socket, struct, sys, time
host, port = sys.argv[1], int(sys.argv[2])
ms = lambda: int(time.time() * 1000)
Q = b'SELECT release_version FROM system.local'

def recvn(s, n):
    b = b''
    while len(b) < n:
        c = s.recv(n - len(b))
        if not c:
            raise EOFError('closed after %d of %d bytes' % (len(b), n))
        b += c
    return b

def frame(stream, op, body):
    return struct.pack('>BBhBI', 4, 0, stream, op, len(body)) + body

def read_frame(s):
    v, f, st, op, n = struct.unpack('>BBhBI', recvn(s, 9))
    return op, recvn(s, n)

def err_of(body):
    code, ml = struct.unpack('>iH', body[:6])
    return 'ERROR code=0x%04x msg=%s' % (code, body[6:6 + ml].decode('utf-8', 'replace'))

def connect():
    s = socket.create_connection((host, port), timeout=2)
    s.settimeout(2)
    k, v = b'CQL_VERSION', b'3.0.0'
    s.sendall(frame(0, 1, struct.pack('>H', 1) + struct.pack('>H', len(k)) + k + struct.pack('>H', len(v)) + v))
    op, body = read_frame(s)
    if op != 2:
        s.close()
        raise RuntimeError(err_of(body) if op == 0 else 'startup opcode %d' % op)
    return s

def query(s, stream):
    s.sendall(frame(stream, 7, struct.pack('>i', len(Q)) + Q + struct.pack('>HB', 1, 0)))
    op, body = read_frame(s)
    if op != 8:
        raise RuntimeError(err_of(body) if op == 0 else 'query opcode %d' % op)

p = None
last_reconnect = 0
next_p = time.time()
next_n = time.time() + 1
stream = 1
while True:
    now = time.time()
    if now >= next_p:
        next_p += 0.5
        t = ms()
        try:
            if p is None:
                if now - last_reconnect < 5 and last_reconnect:
                    raise RuntimeError('disconnected (reconnect pending)')
                last_reconnect = now
                p = connect()
            stream = stream % 30000 + 1
            query(p, stream)
            print('P %d ok %d' % (t, ms() - t), flush=True)
        except Exception as e:
            print('P %d err %r' % (t, e), flush=True)
            try:
                if p is not None:
                    p.close()
            except Exception:
                pass
            p = None
    if now >= next_n:
        next_n += 5
        t = ms()
        try:
            s = connect()
            query(s, 1)
            s.close()
            print('N %d ok %d' % (t, ms() - t), flush=True)
        except Exception as e:
            print('N %d err %r' % (t, e), flush=True)
    time.sleep(max(0.0, min(next_p, next_n) - time.time()))
