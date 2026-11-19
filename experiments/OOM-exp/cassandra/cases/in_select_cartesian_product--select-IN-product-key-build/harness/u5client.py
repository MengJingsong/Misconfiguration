#!/usr/bin/env python3
"""U5 client: raw CQL native protocol v4, standard library only (adapted from B11's client.py).

  u5client.py ddl [--user U --pw P]                   schema u5.ck, u5.pk + one row each (LOAD lifetimes)
  u5client.py mkrole --user cassandra --pw cassandra  CREATE ROLE u5 (non-superuser; LOAD-G only)
  u5client.py run --cond CK|PK --k1 N --k2 N --window S --out FILE [--user U --pw P]
      one connection, STARTUP (+ AUTHENTICATE/AUTH_RESPONSE with --user), PREPARE the condition's statement,
      ONE EXECUTE (consistency ONE, flags VALUES|SKIP_METADATA|PAGE_SIZE, page size 5,000) with bound lists
      0..k1-1 and 0..k2-1 (CK: pk = 0). Never sends IN literals. JSON lines to FILE: prepared, sent (t_send ms,
      frame body bytes = K), then result (rows) | error (code + message) | conn_closed | timeout.
"""
import argparse, json, socket, struct, sys, time

HOST, PORT = '127.0.0.1', 9042
OP_ERROR, OP_STARTUP, OP_READY, OP_AUTHENTICATE, OP_QUERY, OP_RESULT, OP_PREPARE, OP_EXECUTE = 0x00, 0x01, 0x02, 0x03, 0x07, 0x08, 0x09, 0x0A
OP_AUTH_RESPONSE, OP_AUTH_SUCCESS = 0x0F, 0x10
STMT = {'CK': 'SELECT * FROM u5.ck WHERE pk = ? AND c1 IN ? AND c2 IN ?',
        'PK': 'SELECT * FROM u5.pk WHERE a IN ? AND b IN ?'}
MAXFRAME = 16 * 1024 * 1024


def frame(op, body, stream=0):
    return struct.pack('>BBhBi', 0x04, 0, stream, op, len(body)) + body


def lstr(s):
    b = s.encode(); return struct.pack('>i', len(b)) + b


def sstr(s):
    b = s.encode(); return struct.pack('>H', len(b)) + b


def recvn(sock, n):
    buf = bytearray(n); mv = memoryview(buf); got = 0
    while got < n:
        r = sock.recv_into(mv[got:], n - got)
        if r == 0:
            raise ConnectionError('closed')
        got += r
    return bytes(buf)


def recv_frame(sock):
    ver, flags, stream, op, ln = struct.unpack('>BBhBi', recvn(sock, 9))
    body = recvn(sock, ln) if ln else b''
    if flags & 0x02:
        body = body[16:]
    if flags & 0x08:
        n = struct.unpack_from('>H', body)[0]; p = 2
        for _ in range(n):
            l = struct.unpack_from('>H', body, p)[0]; p += 2 + l
        body = body[p:]
    return op, body


def err_text(body):
    code = struct.unpack_from('>i', body)[0]; l = struct.unpack_from('>H', body, 4)[0]
    return '0x%04x' % code, body[6:6 + l].decode('utf-8', 'replace')[:400]


def connect(user=None, pw=None, timeout=60):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    s.settimeout(timeout)
    s.connect((HOST, PORT))
    s.sendall(frame(OP_STARTUP, struct.pack('>H', 1) + sstr('CQL_VERSION') + sstr('3.0.0')))
    op, b = recv_frame(s)
    if op == OP_AUTHENTICATE:
        if not user:
            raise RuntimeError('server asks for authentication')
        tok = b'\0' + user.encode() + b'\0' + pw.encode()
        s.sendall(frame(OP_AUTH_RESPONSE, struct.pack('>i', len(tok)) + tok))
        op, b = recv_frame(s)
        if op != OP_AUTH_SUCCESS:
            raise RuntimeError('auth: op %d %s' % (op, err_text(b) if op == 0 else ''))
    elif op != OP_READY:
        raise RuntimeError('startup: op %d %s' % (op, err_text(b) if op == 0 else ''))
    return s


def query(s, q):
    s.sendall(frame(OP_QUERY, lstr(q) + struct.pack('>HB', 1, 0)))
    op, b = recv_frame(s)
    if op == OP_ERROR:
        raise RuntimeError(err_text(b))
    return b


def prepare(s, q):
    s.sendall(frame(OP_PREPARE, lstr(q)))
    op, b = recv_frame(s)
    if op != OP_RESULT or struct.unpack_from('>i', b)[0] != 4:
        raise RuntimeError('prepare: op %d %s' % (op, err_text(b) if op == 0 else ''))
    l = struct.unpack_from('>H', b, 4)[0]
    return b[6:6 + l]


def int_value(v):
    return struct.pack('>ii', 4, v)


def list_value(n):
    # [bytes] wrapping a list<int>: [int n] then n x ([int 4][int v]); values 0..n-1, sorted and distinct
    body = struct.pack('>i', n) + b''.join(struct.pack('>ii', 4, v) for v in range(n))
    return struct.pack('>i', len(body)) + body


def rows_count(b):
    kind = struct.unpack_from('>i', b)[0]
    if kind != 2:
        return 'kind%d' % kind, False
    flags, cc = struct.unpack_from('>ii', b, 4); p = 12
    more = bool(flags & 0x02)
    if flags & 0x02:
        l = struct.unpack_from('>i', b, p)[0]; p += 4 + max(l, 0)
    if not flags & 0x04:
        return 'metadata-present', more
    return struct.unpack_from('>i', b, p)[0], more


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['ddl', 'mkrole', 'run'])
    ap.add_argument('--user'); ap.add_argument('--pw')
    ap.add_argument('--cond', choices=['CK', 'PK']); ap.add_argument('--k1', type=int); ap.add_argument('--k2', type=int)
    ap.add_argument('--window', type=int, default=240); ap.add_argument('--out')
    a = ap.parse_args()
    if a.mode == 'ddl':
        s = connect(a.user, a.pw)
        for q in ("CREATE KEYSPACE IF NOT EXISTS u5 WITH replication = {'class':'SimpleStrategy','replication_factor':1}",
                  'CREATE TABLE IF NOT EXISTS u5.ck (pk int, c1 int, c2 int, v int, PRIMARY KEY (pk, c1, c2))',
                  'CREATE TABLE IF NOT EXISTS u5.pk (a int, b int, v int, PRIMARY KEY ((a, b)))',
                  'INSERT INTO u5.ck (pk,c1,c2,v) VALUES (0,0,0,1)',
                  'INSERT INTO u5.pk (a,b,v) VALUES (0,0,1)'):
            query(s, q); print('ok:', q)
        return 0
    if a.mode == 'mkrole':
        s = connect(a.user, a.pw)
        query(s, "CREATE ROLE IF NOT EXISTS u5 WITH PASSWORD = 'u5' AND LOGIN = true AND SUPERUSER = false")
        print('role u5 created'); return 0
    out = open(a.out, 'a', buffering=1)
    def ev(**kw):
        kw['t_ms'] = int(time.time() * 1000); out.write(json.dumps(kw) + '\n')
    try:
        s = connect(a.user, a.pw)
        sid = prepare(s, STMT[a.cond])
    except Exception as e:
        ev(ev='pre_send_error', msg=str(e)[:300]); return 2
    t_b = time.time()
    vals = ([int_value(0)] if a.cond == 'CK' else []) + [list_value(a.k1), list_value(a.k2)]
    body = (struct.pack('>H', len(sid)) + sid + struct.pack('>HB', 1, 0x01 | 0x02 | 0x04)
            + struct.pack('>H', len(vals)) + b''.join(vals) + struct.pack('>i', 5000))
    ev(ev='prepared', cond=a.cond, k1=a.k1, k2=a.k2, N=a.k1 * a.k2, body_bytes=len(body), build_s=round(time.time() - t_b, 2))
    if len(body) > MAXFRAME:
        ev(ev='frame_too_big', body_bytes=len(body)); return 3
    s.settimeout(a.window)
    t_send = time.time()
    s.sendall(frame(OP_EXECUTE, body))
    ev(ev='sent', t_send_ms=int(t_send * 1000), body_bytes=len(body))
    try:
        op, b = recv_frame(s)
        dt = round(time.time() - t_send, 3)
        if op == OP_RESULT:
            n, more = rows_count(b); ev(ev='result', rows=n, more_pages=more, latency_s=dt)
        elif op == OP_ERROR:
            c, m = err_text(b); ev(ev='error', code=c, msg=m, latency_s=dt)
        else:
            ev(ev='op%d' % op, latency_s=dt)
    except socket.timeout:
        ev(ev='timeout', latency_s=round(time.time() - t_send, 3))
    except (ConnectionError, OSError) as e:
        ev(ev='conn_closed', msg=str(e)[:200], latency_s=round(time.time() - t_send, 3))
    return 0


if __name__ == '__main__':
    sys.exit(main())
