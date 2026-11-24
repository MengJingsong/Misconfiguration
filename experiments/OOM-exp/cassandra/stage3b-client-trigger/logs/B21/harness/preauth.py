#!/usr/bin/env python3
# B21 3-b confirm (pc72, 2026-11-23): pre-auth check with hand-made native protocol v4 frames (no driver, no login).
# Claim (3-b, code reading): nothing that builds the holder is reachable before authentication; the ANN SELECT is
# refused on an unauthenticated connection. Sequence on one connection: OPTIONS; QUERY before STARTUP; STARTUP;
# QUERY (the T statement, LIMIT 1000) after AUTHENTICATE without AUTH_RESPONSE; AUTH_RESPONSE with a wrong password;
# then on a second connection the same T QUERY sent directly after STARTUP and a REGISTER.
#   preauth.py <host> [port=9042]
import socket, struct, sys
host = sys.argv[1]; port = int(sys.argv[2]) if len(sys.argv) > 2 else 9042
OPS = {0: 'ERROR', 1: 'STARTUP', 2: 'READY', 3: 'AUTHENTICATE', 5: 'OPTIONS', 6: 'SUPPORTED', 7: 'QUERY', 8: 'RESULT',
       11: 'REGISTER', 15: 'AUTH_RESPONSE', 16: 'AUTH_SUCCESS', 14: 'AUTH_CHALLENGE'}
def sstr(s): b = s.encode(); return struct.pack('>H', len(b)) + b
def lstr(s): b = s.encode(); return struct.pack('>i', len(b)) + b
def frame(stream, op, body): return struct.pack('>BBhBi', 0x04, 0, stream, op, len(body)) + body
def recv(sock):
    h = b''
    while len(h) < 9:
        c = sock.recv(9 - len(h))
        if not c: return None
        h += c
    v, fl, st, op, n = struct.unpack('>BBhBi', h)
    b = b''
    while len(b) < n:
        c = sock.recv(n - len(b))
        if not c: break
        b += c
    return op, b
def show(tag, r):
    if r is None: print(tag, '-> connection closed'); return
    op, b = r; name = OPS.get(op, op)
    if op == 0:
        code = struct.unpack('>i', b[:4])[0]; ml = struct.unpack('>H', b[4:6])[0]
        print(tag, '-> ERROR code=0x%04x' % code, repr(b[6:6 + ml].decode(errors='replace')))
    elif op == 3: print(tag, '-> AUTHENTICATE', repr(b[2:].decode(errors='replace')))
    elif op == 8: print(tag, '-> RESULT kind=%d (%d bytes)' % (struct.unpack('>i', b[:4])[0], len(b)))
    else: print(tag, '->', name, '(%d bytes)' % len(b))
vec = ', '.join('0.5' for _ in range(16))
T = 'SELECT id, body FROM b21.docs ORDER BY emb ANN OF [%s] LIMIT 1000' % vec
def query(stream, q): return frame(stream, 7, lstr(q) + struct.pack('>HB', 0x0001, 0))  # CL ONE, no flags
startup = frame(1, 1, struct.pack('>H', 1) + sstr('CQL_VERSION') + sstr('3.0.0'))
def conn(): return socket.create_connection((host, port), timeout=15)
def step(s, tag, data):
    try: s.sendall(data); show(tag, recv(s))
    except (ConnectionResetError, BrokenPipeError) as e: print(tag, '-> connection reset by server (%s)' % e.__class__.__name__)
tok = b'\0attacker\0wrong'
s = conn()
step(s, 'P1 OPTIONS', frame(0, 5, b''))
step(s, 'P2 QUERY(T) before STARTUP', query(2, T))
step(s, 'P2b STARTUP on the same connection after P2', startup)
s.close(); s = conn()
step(s, 'P3 STARTUP (conn 2)', startup)
step(s, 'P4 QUERY(T) after AUTHENTICATE, no AUTH_RESPONSE', query(3, T))
step(s, 'P4b AUTH_RESPONSE wrong password after P4', frame(4, 15, struct.pack('>i', len(tok)) + tok))
s.close(); s = conn()
step(s, 'P5 STARTUP (conn 3)', startup)
step(s, 'P6 AUTH_RESPONSE wrong password', frame(4, 15, struct.pack('>i', len(tok)) + tok))
step(s, 'P7 QUERY(T) after failed auth', query(5, T))
s.close(); s = conn()
step(s, 'P8 STARTUP (conn 4)', startup)
step(s, 'P9 REGISTER before auth', frame(2, 11, struct.pack('>H', 1) + sstr('SCHEMA_CHANGE')))
step(s, 'P10 QUERY(count) before auth', query(3, 'SELECT count(*) FROM b21.docs'))
s.close(); s = conn()
tok2 = b'\0attacker\0atk-3b-B21'
step(s, 'P11 STARTUP (conn 5, control)', startup)
step(s, 'P12 AUTH_RESPONSE correct attacker password (control)', frame(4, 15, struct.pack('>i', len(tok2)) + tok2))
step(s, 'P13 QUERY(T LIMIT 1000) after auth (control)', query(5, T))
s.close()
print('preauth done')
