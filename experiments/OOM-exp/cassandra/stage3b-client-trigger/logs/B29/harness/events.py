#!/usr/bin/env python3
# 3-b confirm B29 (pc82, 2026-11-24): a client's view of node outages through the native protocol only. Hand-made v4 frames
# (no driver): STARTUP, SASL PLAIN login as the given role, REGISTER [STATUS_CHANGE, TOPOLOGY_CHANGE], then print every EVENT
# frame with a timestamp (transport/Server.java EventNotifier). With --waitup IP it exits 0 at the first STATUS_CHANGE UP for IP.
#   events.py <host> <user> <password> <maxSecs> <stopFile> [--waitup IP]
import socket, struct, sys, time, os, datetime
H, U, PW, MAXS, STOP = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4]), sys.argv[5]
WAIT = sys.argv[7] if len(sys.argv) > 7 and sys.argv[6] == '--waitup' else None
def now(): t = time.time(); return datetime.datetime.fromtimestamp(t).strftime('%H:%M:%S.%f')[:-3] + f' ({int(t * 1000)})'
def s_(x): b = x.encode(); return struct.pack('>H', len(b)) + b
def frame(stream, op, body): return struct.pack('>BBhBi', 4, 0, stream, op, len(body)) + body
def rd(sk, n):
    b = b''
    while len(b) < n:
        c = sk.recv(n - len(b))
        if not c: raise EOFError('closed')
        b += c
    return b
def recv(sk):
    _, _, st, op, n = struct.unpack('>BBhBi', rd(sk, 9)); return st, op, rd(sk, n)
def gs(b, o): n = struct.unpack('>H', b[o:o + 2])[0]; return b[o + 2:o + 2 + n].decode(), o + 2 + n
def inet(b, o): n = b[o]; ip = socket.inet_ntop(socket.AF_INET if n == 4 else socket.AF_INET6, b[o + 1:o + 1 + n]); return ip, o + 1 + n + 4
sk = socket.create_connection((H, 9042), timeout=10)
sk.sendall(frame(1, 1, struct.pack('>H', 1) + s_('CQL_VERSION') + s_('3.0.0')))
st, op, b = recv(sk); print(now(), 'STARTUP ->', {2: 'READY', 3: 'AUTHENTICATE'}.get(op, op), flush=True)
if op == 3:
    tok = b'\x00' + U.encode() + b'\x00' + PW.encode()
    sk.sendall(frame(2, 0x0F, struct.pack('>i', len(tok)) + tok))
    st, op, b = recv(sk); print(now(), f'AUTH_RESPONSE as {U} ->', {0x10: 'AUTH_SUCCESS', 0: 'ERROR'}.get(op, op), flush=True)
    if op != 0x10: sys.exit(2)
sk.sendall(frame(3, 0x0B, struct.pack('>H', 2) + s_('STATUS_CHANGE') + s_('TOPOLOGY_CHANGE')))
st, op, b = recv(sk); print(now(), 'REGISTER [STATUS_CHANGE, TOPOLOGY_CHANGE] ->', {2: 'READY', 0: 'ERROR'}.get(op, op), flush=True)
sk.settimeout(1.0); t0 = time.time()
while time.time() - t0 < MAXS and not os.path.exists(STOP):
    try: st, op, b = recv(sk)
    except socket.timeout: continue
    if op != 0x0C: continue
    typ, o = gs(b, 0); ch, o = gs(b, o); ip, o = inet(b, o)
    print(now(), 'EVENT', typ, ch, ip, flush=True)
    if WAIT and typ == 'STATUS_CHANGE' and ch == 'UP' and ip == WAIT: print(now(), 'waitup', WAIT, 'UP', flush=True); sys.exit(0)
print(now(), 'end', flush=True); sys.exit(1 if WAIT else 0)
