#!/usr/bin/env python3
"""B13 3-b confirm (2026-11-24; copy of C2 3-b victim.py, table renamed vic.kv, env VIC_USER / VIC_PASS):
victim-tenant client (raw CQL native protocol v4, SASL PLAIN login as its own role).
  victim.py <host> <ops_per_sec> <secs> [timeout_s=2]     env VIC_USER / VIC_PASS
Steady light workload on its own table vic.kv (k int PRIMARY KEY, v blob): alternating
INSERT INTO vic.kv (k, v) VALUES (<k>, <200 B>) and SELECT v FROM vic.kv WHERE k=<k>, CL ONE, one request at a time
on one connection, paced at <ops_per_sec>. A request that errors, times out (> timeout_s) or finds the connection
gone counts as an error; the client then reconnects (one attempt per scheduled op) and keeps going.
Prints one CSV line per second: t_ms,attempted,ok,err,p50ms,p99ms,maxms,connected,lastErr ; ends with SUMMARY."""
import os, socket, struct, sys, time

host, rate, secs = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
tmo = float(sys.argv[4]) if len(sys.argv) > 4 else 2.0
USER, PASS = os.environ['VIC_USER'].encode(), os.environ['VIC_PASS'].encode()
VAL = bytes(range(200))


def frame(stream, opcode, body):
    return struct.pack('>BBhBi', 4, 0, stream, opcode, len(body)) + body


def recvn(sk, n):
    b = b''
    while len(b) < n:
        c = sk.recv(n - len(b))
        if not c:
            raise EOFError('closed by server')
        b += c
    return b


def rd(sk):
    _, _, st, op, ln = struct.unpack('>BBhBi', recvn(sk, 9))
    return op, recvn(sk, ln)


def connect():
    sk = socket.create_connection((host, 9042), timeout=tmo)
    sk.settimeout(tmo)
    m = {b'CQL_VERSION': b'3.0.0'}
    b = struct.pack('>H', len(m))
    for k, v in m.items():
        b += struct.pack('>H', len(k)) + k + struct.pack('>H', len(v)) + v
    sk.sendall(frame(0, 0x01, b))
    op, body = rd(sk)
    if op == 0x03:
        tok = b'\0' + USER + b'\0' + PASS
        sk.sendall(frame(0, 0x0F, struct.pack('>i', len(tok)) + tok))
        op, body = rd(sk)
        if op != 0x10:
            raise RuntimeError('auth failed op=%d %r' % (op, body[:80]))
    elif op != 0x02:
        raise RuntimeError('startup op=%d' % op)
    return sk


def query(q, vals=None):
    q = q.encode()
    if vals is None:
        body = struct.pack('>i', len(q)) + q + struct.pack('>HB', 0x0001, 0x00)
    else:
        body = struct.pack('>i', len(q)) + q + struct.pack('>HBH', 0x0001, 0x01, len(vals))
        for v in vals:
            body += struct.pack('>i', len(v)) + v
    return frame(1, 0x07, body)


print('t_ms,attempted,ok,err,p50ms,p99ms,maxms,connected,lastErr', flush=True)
sk = None; t0 = time.time(); nxt = t0; tick = t0 + 1; i = 0
att = ok = er = 0; lat = []; lasterr = ''; T_ok = T_err = T_att = 0
while time.time() - t0 < secs:
    now = time.time()
    if now >= tick:
        lat.sort()
        p = (lambda f: '%.1f' % (lat[min(len(lat) - 1, int(len(lat) * f))] * 1000) if lat else '-1')
        print('%d,%d,%d,%d,%s,%s,%s,%d,%s' % (int(now * 1000), att, ok, er, p(0.5), p(0.99), p(1.0), sk is not None, lasterr), flush=True)
        att = ok = er = 0; lat = []; lasterr = ''; tick += 1
        continue
    if now < nxt:
        time.sleep(min(nxt, tick) - now if min(nxt, tick) > now else 0.001)
        continue
    nxt += 1.0 / rate; i += 1; att += 1; T_att += 1
    k = i % 1000
    s = time.time()
    try:
        if sk is None:
            sk = connect()
        if i % 2:
            sk.sendall(query('INSERT INTO vic.kv (k, v) VALUES (%d, ?)' % k, [VAL]))
        else:
            sk.sendall(query('SELECT v FROM vic.kv WHERE k=%d' % k))
        op, body = rd(sk)
        if op == 0x00:
            raise RuntimeError('server error ' + body[4:100].decode(errors='replace'))
        ok += 1; T_ok += 1; lat.append(time.time() - s)
    except Exception as e:
        er += 1; T_err += 1; lasterr = (type(e).__name__ + ' ' + str(e))[:90].replace(',', ';')
        try:
            sk and sk.close()
        except Exception:
            pass
        sk = None
    if nxt < time.time() - 5:  # do not burst after a long stall
        nxt = time.time()
print('SUMMARY secs=%.0f attempted=%d ok=%d err=%d' % (time.time() - t0, T_att, T_ok, T_err), flush=True)
