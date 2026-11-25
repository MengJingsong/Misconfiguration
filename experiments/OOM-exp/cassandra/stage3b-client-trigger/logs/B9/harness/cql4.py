#!/usr/bin/env python3
"""B9 3-b confirm (2026-11-24): minimal raw CQL native protocol v4 helpers (unframed envelopes), standard library only.
Used by admin.py, victim.py, atk.py. Request envelope: version 0x04, flags 0, stream int16, opcode, body length int32."""
import socket, struct

OP = dict(ERROR=0x00, STARTUP=0x01, READY=0x02, AUTHENTICATE=0x03, OPTIONS=0x05, SUPPORTED=0x06, QUERY=0x07,
          RESULT=0x08, PREPARE=0x09, EXECUTE=0x0A, AUTH_RESPONSE=0x0F, AUTH_SUCCESS=0x10)
OPNAME = {v: k for k, v in OP.items()}
HOST = '127.0.0.81'; PORT = 9042


def recvn(s, n):
    b = bytearray()
    while len(b) < n:
        r = s.recv(min(n - len(b), 1 << 20))
        if not r:
            raise ConnectionError('closed')
        b += r
    return bytes(b)


def frame(op, body, stream=0, ver=0x04):
    return struct.pack('>BBhBi', ver, 0, stream, op, len(body)) + body


def rd(s):
    h = recvn(s, 9)
    ver, fl, st, op, ln = struct.unpack('>BBhBi', h)
    b = recvn(s, ln) if ln else b''
    if fl & 0x08:  # warnings
        n = struct.unpack_from('>H', b)[0]; p = 2
        for _ in range(n):
            l = struct.unpack_from('>H', b, p)[0]; p += 2 + l
        b = b[p:]
    return st, op, b


def err(b):
    try:
        c = struct.unpack_from('>i', b)[0]; l = struct.unpack_from('>H', b, 4)[0]
        return 'ERR:0x%04x:%s' % (c, b[6:6 + l].decode('utf-8', 'replace')[:160])
    except Exception:
        return 'ERR:unparsable'


def describe(op, b):
    if op == OP['ERROR']:
        return err(b)
    return OPNAME.get(op, 'op%d' % op)


def startup_body():
    return struct.pack('>H', 1) + struct.pack('>H', 11) + b'CQL_VERSION' + struct.pack('>H', 5) + b'3.0.0'


def sock(src=None, host=HOST, timeout=10):
    s = socket.socket(); s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    if src:
        s.bind((src, 0))
    s.settimeout(timeout); s.connect((host, PORT))
    return s


def login(s, user, pw):
    """STARTUP then SASL PLAIN. Returns 'READY' (no auth), 'AUTH_SUCCESS', or raises."""
    s.sendall(frame(OP['STARTUP'], startup_body()))
    _, op, b = rd(s)
    if op == OP['READY']:
        return 'READY'
    if op != OP['AUTHENTICATE']:
        raise RuntimeError('startup ' + describe(op, b))
    tok = b'\0' + user.encode() + b'\0' + pw.encode()
    s.sendall(frame(OP['AUTH_RESPONSE'], struct.pack('>i', len(tok)) + tok))
    _, op, b = rd(s)
    if op != OP['AUTH_SUCCESS']:
        raise RuntimeError('auth ' + describe(op, b))
    return 'AUTH_SUCCESS'


def query_body(q, cl=0x0001):
    qb = q.encode()
    return struct.pack('>i', len(qb)) + qb + struct.pack('>HB', cl, 0)


def execute_body(stmt_id, values, cl=0x0001):
    b = struct.pack('>H', len(stmt_id)) + stmt_id + struct.pack('>HB', cl, 0x01) + struct.pack('>H', len(values))
    parts = [b]
    for v in values:
        parts.append(struct.pack('>i', len(v))); parts.append(v)
    return b''.join(parts)


# ---- minimal RESULT Rows parser (for admin output) ----
def _string(b, p):
    l = struct.unpack_from('>H', b, p)[0]; return b[p + 2:p + 2 + l].decode('utf-8', 'replace'), p + 2 + l


def _option(b, p):
    t = struct.unpack_from('>H', b, p)[0]; p += 2
    if t == 0x0000:
        _, p = _string(b, p)
    elif t in (0x0020, 0x0022):
        _, p = _option(b, p)
    elif t == 0x0021:
        _, p = _option(b, p); _, p = _option(b, p)
    elif t == 0x0030:
        _, p = _string(b, p); _, p = _string(b, p); n = struct.unpack_from('>H', b, p)[0]; p += 2
        for _ in range(n):
            _, p = _string(b, p); _, p = _option(b, p)
    elif t == 0x0031:
        n = struct.unpack_from('>H', b, p)[0]; p += 2
        for _ in range(n):
            _, p = _option(b, p)
    return t, p


def _val(t, v):
    if v is None:
        return 'null'
    if t == 0x0004:
        return str(bool(v[0])) if v else ''
    if t == 0x0009 and len(v) == 4:
        return str(struct.unpack('>i', v)[0])
    if t in (0x000D, 0x0001, 0x000A):
        return v.decode('utf-8', 'replace')
    if t in (0x0020, 0x0022):
        try:
            n = struct.unpack_from('>i', v)[0]; p = 4; out = []
            for _ in range(n):
                l = struct.unpack_from('>i', v, p)[0]; out.append(v[p + 4:p + 4 + l].decode('utf-8', 'replace')); p += 4 + l
            return '{' + ','.join(out) + '}'
        except Exception:
            return v.hex()
    return v.hex() if len(v) <= 32 else '<%dB>' % len(v)


def rows(b):
    kind = struct.unpack_from('>i', b)[0]
    if kind != 2:
        return {1: 'Void', 3: 'SetKeyspace', 4: 'Prepared', 5: 'SchemaChange'}.get(kind, 'kind%d' % kind), []
    p = 4; flags, ncol = struct.unpack_from('>ii', b, p); p += 8
    if flags & 0x0002:
        l = struct.unpack_from('>i', b, p)[0]; p += 4 + max(l, 0)
    glob = flags & 0x0001
    if glob:
        _, p = _string(b, p); _, p = _string(b, p)
    names, types = [], []
    if not flags & 0x0004:
        for _ in range(ncol):
            if not glob:
                _, p = _string(b, p); _, p = _string(b, p)
            n, p = _string(b, p); t, p = _option(b, p); names.append(n); types.append(t)
    nrows = struct.unpack_from('>i', b, p)[0]; p += 4
    out = []
    for _ in range(nrows):
        r = []
        for c in range(ncol):
            l = struct.unpack_from('>i', b, p)[0]; p += 4
            v = None if l < 0 else b[p:p + l]; p += max(l, 0)
            r.append(_val(types[c] if c < len(types) else 0, v))
        out.append(r)
    return names, out
