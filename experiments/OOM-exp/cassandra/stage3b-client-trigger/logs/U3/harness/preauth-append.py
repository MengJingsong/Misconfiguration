#!/usr/bin/env python3
# 3-b confirm U3 (2026-11-24): pre-auth probe for the WRITE step: STARTUP, then an append QUERY (UPDATE u3.s1m SET v = v + {..})
# and a SELECT of the grown set, both before any AUTH_RESPONSE; v4 frames, no driver. Prints each reply.
import socket, struct, sys
H = sys.argv[1]; P = 9042
def s_(x): b = x.encode(); return struct.pack('>H', len(b)) + b
def ls_(x): b = x.encode(); return struct.pack('>i', len(b)) + b
def frame(st, op, body): return struct.pack('>BBhBi', 4, 0, st, op, len(body)) + body
def recv(sk):
    h = b''
    while len(h) < 9:
        r = sk.recv(9 - len(h))
        if not r: raise ConnectionError('closed')
        h += r
    _, _, st, op, n = struct.unpack('>BBhBi', h); b = b''
    while len(b) < n: b += sk.recv(n - len(b))
    if op == 0:
        c = struct.unpack('>i', b[:4])[0]; ml = struct.unpack('>H', b[4:6])[0]
        return 'ERROR code=0x%04X msg="%s"' % (c, b[6:6 + ml].decode(errors='replace'))
    return 'op=0x%02x (%d B body)' % (op, n)
sk = socket.create_connection((H, P), timeout=10)
for name, fr in [('STARTUP', frame(1, 1, struct.pack('>H', 1) + s_('CQL_VERSION') + s_('3.0.0'))),
                 ('QUERY append to u3.s1m k=7 before AUTH_RESPONSE', frame(2, 7, ls_('UPDATE u3.s1m SET v = v + {%s} WHERE k = 7' % ','.join(str(i) for i in range(-1000, 0))) + struct.pack('>HB', 1, 0))),
                 ('QUERY SELECT v FROM u3.s1m WHERE k = 7', frame(3, 7, ls_('SELECT v FROM u3.s1m WHERE k = 7') + struct.pack('>HB', 1, 0)))]:
    sk.sendall(fr)
    try: print('  %-50s -> %s' % (name, recv(sk)))
    except Exception as e: print('  %-50s -> no reply / closed (%s)' % (name, e)); break
