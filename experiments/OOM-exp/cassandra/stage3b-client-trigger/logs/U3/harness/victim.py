#!/usr/bin/env python3
"""R13 stage 3-b confirm victim (2026-11-23): a second LOGIN role doing a steady light workload on its own table through
the same node. Raw CQL native protocol v4 (unframed), SASL PLAIN, standard library only.
  victim.py --user victim --pw PW --rate 10 --out FILE --stop STOPFILE [--src 127.0.0.1]
Every 1/rate s one request, alternating INSERT INTO victim.kv (k, v) VALUES (n, '<64 B>') and SELECT v FROM victim.kv
WHERE k = n-1, consistency ONE, client timeout 5 s. On a timeout or connection error: log it, close, reconnect (1 s apart).
A tick that falls while a request is still running is skipped and logged as 'missed'.
Log lines: t_ms op latency_ms status   (status OK | ERR:<code>:<text> | timeout | io:<error> | connect:<error> | missed)
"""
import argparse, os, socket, struct, time

OP_ERROR, OP_STARTUP, OP_READY, OP_AUTHENTICATE, OP_QUERY, OP_RESULT, OP_AUTH_RESPONSE, OP_AUTH_SUCCESS = 0, 1, 2, 3, 7, 8, 0x0F, 0x10


def recvn(s, n):
    b = bytearray()
    while len(b) < n:
        r = s.recv(n - len(b))
        if not r: raise ConnectionError('closed')
        b += r
    return bytes(b)


def frame(op, body, stream=0):
    return struct.pack('>BBhBi', 0x04, 0, stream, op, len(body)) + body


def rd(s):
    h = recvn(s, 9); ver, fl, st, op, ln = struct.unpack('>BBhBi', h)
    b = recvn(s, ln) if ln else b''
    if fl & 0x08:                                       # warnings
        n = struct.unpack_from('>H', b)[0]; p = 2
        for _ in range(n):
            l = struct.unpack_from('>H', b, p)[0]; p += 2 + l
        b = b[p:]
    return st, op, b


def err(b):
    try:
        c = struct.unpack_from('>i', b)[0]; l = struct.unpack_from('>H', b, 4)[0]
        return 'ERR:0x%04x:%s' % (c, b[6:6 + l].decode('utf-8', 'replace')[:100].replace(' ', '_'))
    except Exception:
        return 'ERR:unparsable'


def connect(a):
    s = socket.socket(); s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    s.bind((a.src, 0)); s.settimeout(5); s.connect(('127.0.0.1', 9042))
    s.sendall(frame(OP_STARTUP, struct.pack('>H', 1) + struct.pack('>H', 11) + b'CQL_VERSION' + struct.pack('>H', 5) + b'3.0.0'))
    _, op, b = rd(s)
    if op == OP_AUTHENTICATE:
        tok = b'\0' + a.user.encode() + b'\0' + a.pw.encode()
        s.sendall(frame(OP_AUTH_RESPONSE, struct.pack('>i', len(tok)) + tok))
        _, op, b = rd(s)
        if op != OP_AUTH_SUCCESS: raise RuntimeError('auth ' + (err(b) if op == OP_ERROR else 'op%d' % op))
    elif op != OP_READY:
        raise RuntimeError('startup ' + (err(b) if op == OP_ERROR else 'op%d' % op))
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='victim'); ap.add_argument('--pw', required=True)
    ap.add_argument('--rate', type=float, default=10); ap.add_argument('--out', required=True)
    ap.add_argument('--stop', required=True); ap.add_argument('--src', default='127.0.0.1')
    a = ap.parse_args()
    log = open(a.out, 'a', buffering=1)
    log.write('# victim start %s user=%s rate=%s src=%s pid=%d\n' % (time.strftime('%Y-%m-%dT%H:%M:%S%z'), a.user, a.rate, a.src, os.getpid()))
    s = None; n = 0; period = 1.0 / a.rate; nxt = time.time(); last_conn_try = 0
    pay = 'x' * 64
    while not os.path.exists(a.stop):
        now = time.time()
        if now < nxt:
            time.sleep(min(nxt - now, 0.2)); continue
        while nxt + period <= now:                        # ticks that passed while busy
            log.write('%d - 0 missed\n' % (nxt * 1000)); nxt += period
        nxt += period
        if s is None:
            if now - last_conn_try < 1.0:
                log.write('%d - 0 down\n' % (now * 1000)); continue
            last_conn_try = now
            try:
                s = connect(a)
            except Exception as e:
                log.write('%d connect %d connect:%s\n' % (now * 1000, (time.time() - now) * 1000, str(e)[:80].replace(' ', '_')))
                s = None; continue
        n += 1
        if n % 2:
            op, q = 'W', "INSERT INTO victim.kv (k, v) VALUES (%d, '%s')" % (n, pay)
        else:
            op, q = 'R', 'SELECT v FROM victim.kv WHERE k = %d' % (n - 1)
        body = struct.pack('>i', len(q)) + q.encode() + struct.pack('>HB', 0x0001, 0)
        t0 = time.time()
        try:
            s.sendall(frame(OP_QUERY, body, n % 32000))
            _, rop, b = rd(s)
            status = 'OK' if rop == OP_RESULT else (err(b) if rop == OP_ERROR else 'op%d' % rop)
        except socket.timeout:
            status = 'timeout'
        except Exception as e:
            status = 'io:%s' % str(e)[:60].replace(' ', '_')
        log.write('%d %s %d %s\n' % (t0 * 1000, op, (time.time() - t0) * 1000, status))
        if status != 'OK' and not status.startswith('ERR:'):
            try: s.close()
            except Exception: pass
            s = None
    log.write('# victim end %d\n' % (time.time() * 1000))


if __name__ == '__main__':
    main()
