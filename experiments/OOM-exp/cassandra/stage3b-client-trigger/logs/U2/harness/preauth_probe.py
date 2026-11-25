#!/usr/bin/env python3
"""U2 3-b confirm (2026-11-24): what an unauthenticated client gets from the native port with PasswordAuthenticator on.
usage: preauth_probe.py <host> <port> <victim_password>
Each probe uses a fresh v4 connection (raw frames, standard library only) and prints one line:
  P1 OPTIONS before STARTUP           (expect SUPPORTED 0x06: served by InitialConnectionHandler, no auth)
  P2 QUERY before STARTUP             (expect ERROR: only OPTIONS/STARTUP are accepted pre-STARTUP)
  P3 STARTUP                          (expect AUTHENTICATE 0x03 naming PasswordAuthenticator)
  P4 STARTUP, QUERY without AUTH_RESPONSE (expect ERROR, connection not authenticated)
  P5 STARTUP, wrong password          (expect ERROR 0x0100 bad credentials)
  P6 STARTUP, victim's password       (expect AUTH_SUCCESS 0x10; sanity check that login works)
  P7 9-byte header declaring 16,777,207 B, then 1 MiB of body, then wait 3 s (expect no response: the frame waits for its rest)
"""
import socket, struct, sys
host, port, vpw = sys.argv[1], int(sys.argv[2]), sys.argv[3]
OPS = {0: 'ERROR', 2: 'READY', 3: 'AUTHENTICATE', 6: 'SUPPORTED', 8: 'RESULT', 0x0E: 'AUTH_CHALLENGE', 0x10: 'AUTH_SUCCESS'}

def recvn(s, n):
    b = b''
    while len(b) < n:
        c = s.recv(n - len(b))
        if not c:
            raise EOFError('closed after %d of %d bytes' % (len(b), n))
        b += c
    return b

def frame(op, body, stream=1):
    return struct.pack('>BBhBI', 4, 0, stream, op, len(body)) + body

def rd(s):
    v, f, st, op, n = struct.unpack('>BBhBI', recvn(s, 9))
    b = recvn(s, n) if n else b''
    return op, b

def desc(op, b):
    name = OPS.get(op, 'op%d' % op)
    if op == 0:
        c, l = struct.unpack_from('>iH', b)
        return 'ERROR code=0x%04x msg=%s' % (c, b[6:6 + l].decode('utf-8', 'replace')[:160])
    if op == 3:
        l = struct.unpack_from('>H', b)[0]
        return 'AUTHENTICATE %s' % b[2:2 + l].decode()
    return name

STARTUP = frame(1, struct.pack('>H', 1) + struct.pack('>H', 11) + b'CQL_VERSION' + struct.pack('>H', 5) + b'3.0.0')
Q = b'SELECT release_version FROM system.local'
QUERY = frame(7, struct.pack('>i', len(Q)) + Q + struct.pack('>HB', 1, 0), 2)

def conn():
    s = socket.create_connection((host, port), timeout=5); s.settimeout(5); return s

def auth(user, pw):
    tok = b'\0' + user.encode() + b'\0' + pw.encode()
    return frame(0x0F, struct.pack('>i', len(tok)) + tok, 3)

def probe(name, fn):
    try:
        print('%s %s' % (name, fn()), flush=True)
    except Exception as e:
        print('%s exception %r' % (name, e), flush=True)

def p1():
    s = conn(); s.sendall(frame(5, b'')); r = desc(*rd(s)); s.close(); return r
def p2():
    s = conn(); s.sendall(QUERY); r = desc(*rd(s)); s.close(); return r
def p3():
    s = conn(); s.sendall(STARTUP); r = desc(*rd(s)); s.close(); return r
def p4():
    s = conn(); s.sendall(STARTUP); a = desc(*rd(s)); s.sendall(QUERY); r = desc(*rd(s)); s.close(); return a + ' -> ' + r
def p5():
    s = conn(); s.sendall(STARTUP); a = desc(*rd(s)); s.sendall(auth('victim', 'wrong-' + vpw)); r = desc(*rd(s)); s.close(); return a + ' -> ' + r
def p6():
    s = conn(); s.sendall(STARTUP); a = desc(*rd(s)); s.sendall(auth('victim', vpw)); r = desc(*rd(s)); s.close(); return a + ' -> ' + r
def p7():
    s = conn(); s.sendall(struct.pack('>BBhBI', 4, 0, 1, 5, 16777207)); s.sendall(b'\0' * (1 << 20)); s.settimeout(3)
    try:
        d = s.recv(1)
        r = 'got %r (unexpected)' % d if d else 'closed by server'
    except socket.timeout:
        r = 'no response in 3 s; connection open (frame waits for its rest)'
    s.close(); return r

for n, f in (('P1 OPTIONS-before-STARTUP', p1), ('P2 QUERY-before-STARTUP', p2), ('P3 STARTUP', p3), ('P4 STARTUP+QUERY-no-auth', p4),
             ('P5 STARTUP+wrong-password', p5), ('P6 STARTUP+victim-login', p6), ('P7 partial-16MiB-frame', p7)):
    probe(n, f)
