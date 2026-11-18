#!/usr/bin/env python3
"""B11 client: raw CQL native protocol v4, standard library only.

  client.py --ddl                                  create keyspace b11 and table b11.t
  client.py --trace-check                          print the parameters of up to 3 system_traces.sessions rows
  client.py --tracing {on,off} --fixed N --hold-s H --out DIR
  client.py --tracing {on,off} --ramp 8,13,16 --step-s 60 --out DIR

Each connection i binds to source address 127.1.(i // 250).(1 + i % 250) (one request per IP), sends
STARTUP, PREPAREs `SELECT c FROM b11.t WHERE k = 0 AND v = ? ALLOW FILTERING`, then runs a closed loop of
EXECUTE frames carrying one blob of S bytes (consistency ONE). Tracing flag 0x02 in the frame header when
--tracing on; that flag is the only difference between test and control.
Logs: DIR/completions.txt (t_ms conn latency_ms status), DIR/client.txt (per second:
t_ms open established outstanding completed errors K_client).
"""
import argparse, os, socket, struct, sys, threading, time

S = 16_000_000
HOST, PORT = '127.0.0.1', 9042
STMT = 'SELECT c FROM b11.t WHERE k = 0 AND v = ? ALLOW FILTERING'
OP_ERROR, OP_STARTUP, OP_READY, OP_QUERY, OP_RESULT, OP_PREPARE, OP_EXECUTE = 0x00, 0x01, 0x02, 0x07, 0x08, 0x09, 0x0A


def frame(op, body, flags=0, stream=0):
    return struct.pack('>BBhBi', 0x04, flags, stream, op, len(body)) + body


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
    h = recvn(sock, 9)
    ver, flags, stream, op, ln = struct.unpack('>BBhBi', h)
    body = recvn(sock, ln) if ln else b''
    if flags & 0x02:       # tracing: 16-byte session id first
        body = body[16:]
    if flags & 0x08:       # warnings: [string list]
        n = struct.unpack_from('>H', body)[0]; p = 2
        for _ in range(n):
            l = struct.unpack_from('>H', body, p)[0]; p += 2 + l
        body = body[p:]
    return op, body


def err_text(body):
    code = struct.unpack_from('>i', body)[0]; l = struct.unpack_from('>H', body, 4)[0]
    return '0x%04x:%s' % (code, body[6:6 + l].decode('utf-8', 'replace')[:120])


def open_conn(i, timeout=60):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    s.bind(('127.1.%d.%d' % (i // 250, 1 + i % 250), 0))
    s.settimeout(timeout)
    s.connect((HOST, PORT))
    body = struct.pack('>H', 1) + sstr('CQL_VERSION') + sstr('3.0.0')
    s.sendall(frame(OP_STARTUP, body))
    op, b = recv_frame(s)
    if op != OP_READY:
        raise RuntimeError('startup: op %d %s' % (op, err_text(b) if op == 0 else ''))
    return s


def query(s, q):
    s.sendall(frame(OP_QUERY, lstr(q) + struct.pack('>HB', 1, 0)))
    op, b = recv_frame(s)
    if op == OP_ERROR:
        raise RuntimeError(err_text(b))
    return b


def prepare(s):
    s.sendall(frame(OP_PREPARE, lstr(STMT)))
    op, b = recv_frame(s)
    if op != OP_RESULT or struct.unpack_from('>i', b)[0] != 4:
        raise RuntimeError('prepare: op %d %s' % (op, err_text(b) if op == 0 else ''))
    l = struct.unpack_from('>H', b, 4)[0]
    return b[6:6 + l]


class Stats:
    def __init__(self):
        self.lock = threading.Lock(); self.open = 0; self.est = 0; self.out = 0; self.done = 0; self.err = 0


def worker(i, st, payload_holder, tracing, stop, comp, t0, ready_evt):
    try:
        with st.lock: st.open += 1
        s = open_conn(i)
        sid = prepare(s)
        s.settimeout(None)
        if payload_holder.get('id') is None:
            payload_holder['id'] = sid
        if sid != payload_holder['id']:
            raise RuntimeError('statement id differs')
        with st.lock: st.est += 1
    except Exception as e:
        with st.lock: st.err += 1; st.open -= 1
        comp.write('%d %d -1 connect_error:%s\n' % ((time.time() - t0) * 1000, i, str(e)[:100]))
        return
    ready_evt.wait()
    fr = payload_holder['frame']
    while not stop.is_set():
        ts = time.time()
        try:
            with st.lock: st.out += 1
            s.sendall(fr)
            op, b = recv_frame(s)
            status = 'ok' if op == OP_RESULT else ('err:' + err_text(b) if op == OP_ERROR else 'op%d' % op)
        except Exception as e:
            status = 'io_error:%s' % str(e)[:80]
            with st.lock: st.out -= 1; st.err += 1
            comp.write('%d %d %d %s\n' % ((time.time() - t0) * 1000, i, (time.time() - ts) * 1000, status))
            break
        with st.lock:
            st.out -= 1
            if status == 'ok': st.done += 1
            else: st.err += 1
        comp.write('%d %d %d %s\n' % ((time.time() - t0) * 1000, i, (time.time() - ts) * 1000, status))
    try: s.close()
    except Exception: pass


def build_frame(sid, tracing):
    blob = bytes(range(256)) * (S // 256)
    assert len(blob) == S
    body = struct.pack('>H', len(sid)) + sid + struct.pack('>HBH', 1, 0x01, 1) + struct.pack('>i', S) + blob
    return frame(OP_EXECUTE, body, flags=0x02 if tracing else 0x00)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ddl', action='store_true'); ap.add_argument('--trace-check', action='store_true')
    ap.add_argument('--tracing', choices=['on', 'off']); ap.add_argument('--fixed', type=int)
    ap.add_argument('--ramp'); ap.add_argument('--step-s', type=int, default=60); ap.add_argument('--hold-s', type=int, default=150)
    ap.add_argument('--out', default='.')
    a = ap.parse_args()
    if a.ddl:
        s = open_conn(9999)
        query(s, "CREATE KEYSPACE IF NOT EXISTS b11 WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
        query(s, 'CREATE TABLE IF NOT EXISTS b11.t (k int, c int, v blob, PRIMARY KEY (k, c))')
        print('ddl ok'); return
    if a.trace_check:
        s = open_conn(9998)
        b = query(s, 'SELECT session_id, parameters FROM system_traces.sessions LIMIT 3')
        # crude: print map strings that start with bound_var and their lengths
        txt = b.decode('latin-1')
        k = 0
        while True:
            j = txt.find('bound_var_', k)
            if j < 0: break
            kl = struct.unpack_from('>i', b, j - 4)[0]; key = txt[j:j + kl]
            vl = struct.unpack_from('>i', b, j + kl)[0]; val = txt[j + kl + 4:j + kl + 4 + vl]
            print('%s len=%d head=%s tail=%s' % (key, vl, val[:12], val[-8:])); k = j + kl + 4 + vl
        return
    tracing = a.tracing == 'on'
    steps = [a.fixed] if a.fixed else [int(x) for x in a.ramp.split(',')]
    os.makedirs(a.out, exist_ok=True)
    comp = open(os.path.join(a.out, 'completions.txt'), 'a', buffering=1)
    clog = open(os.path.join(a.out, 'client.txt'), 'a', buffering=1)
    st = Stats(); stop = threading.Event(); holder = {'id': None, 'frame': None}
    t0 = time.time()
    clog.write('# start %s tracing=%s steps=%s S=%d\n' % (time.strftime('%Y-%m-%dT%H:%M:%S%z'), a.tracing, steps, S))
    B = None
    def sampler():
        while not stop.is_set():
            with st.lock:
                clog.write('%d %d %d %d %d %d %d\n' % ((time.time() - t0) * 1000, st.open, st.est, st.out, st.done, st.err,
                                                        st.out * (B or 0)))
            time.sleep(1)
    threading.Thread(target=sampler, daemon=True).start()
    threads = []; n = 0
    for si, target in enumerate(steps):
        evt = threading.Event()
        new = []
        while n < target:
            t = threading.Thread(target=worker, args=(n, st, holder, tracing, stop, comp, t0, evt), daemon=True)
            t.start(); new.append(t); n += 1
        # wait for the new connections to be established (or fail), up to 120 s
        dl = time.time() + 120
        while time.time() < dl:
            with st.lock:
                if st.est + st.err >= n: break
            time.sleep(0.2)
        if holder['frame'] is None:
            if holder['id'] is None:
                clog.write('# no connection established\n'); stop.set(); return 2
            holder['frame'] = build_frame(holder['id'], tracing); B = len(holder['frame']) - 9
        clog.write('# step %d N=%d established=%d at %d ms\n' % (si, target, st.est, (time.time() - t0) * 1000))
        evt.set(); threads += new
        hold = a.hold_s if a.fixed else a.step_s
        dl = time.time() + hold
        while time.time() < dl:
            if not any(t.is_alive() for t in threads):
                break
            time.sleep(0.5)
        if not any(t.is_alive() for t in threads):
            clog.write('# all connections ended at %d ms\n' % ((time.time() - t0) * 1000)); break
    stop.set()
    clog.write('# end %d ms done=%d err=%d\n' % ((time.time() - t0) * 1000, st.done, st.err))
    time.sleep(1.2)
    return 0


if __name__ == '__main__':
    sys.exit(main())
