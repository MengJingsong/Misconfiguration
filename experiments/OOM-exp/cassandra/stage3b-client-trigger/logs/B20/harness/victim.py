#!/usr/bin/env python3
"""3-b confirm B20 victim tenant: role 'victim' (SELECT, MODIFY on vks.kv only), its own keyspace vks, same node.
Steady light workload: <rate> ops/s alternating INSERT and SELECT of random k in [0, 10000) with 100-byte values,
CL ONE, client timeout 2 s, at most 200 in flight (beyond that a request is counted as 'shed'). Reconnects every 1 s.
Per issue-second CSV: epoch,sent,ok,err,shed,p50_ms,p99_ms,max_ms,errtypes. Runs until <out>.stop exists or SIGTERM.
  victim.py <out.csv> <rate>
"""
import os, random, signal, sys, threading, time, drv
out, rate = sys.argv[1], float(sys.argv[2])
stop = threading.Event()
signal.signal(signal.SIGTERM, lambda *a: stop.set())
cl, s = drv.session('victim', timeout=2.0, retry_s=120, reconnection_policy=drv.ConstantReconnectionPolicy(1.0, None),
                    idle_heartbeat_interval=5, control_connection_timeout=5)
ins = s.prepare('INSERT INTO vks.kv (k, v) VALUES (?, ?)')
sel = s.prepare('SELECT v FROM vks.kv WHERE k = ?')
lock = threading.Lock(); buckets = {}; inflight = [0]
def bucket(sec):
    b = buckets.get(sec)
    if b is None: b = buckets[sec] = {'sent': 0, 'ok': 0, 'err': 0, 'shed': 0, 'lat': [], 'et': {}}
    return b
def done(sec, t, ok, et=None):
    lat = (time.time() - t) * 1000
    with lock:
        inflight[0] -= 1; b = bucket(sec)
        if ok: b['ok'] += 1; b['lat'].append(lat)
        else: b['err'] += 1; b['et'][et] = b['et'].get(et, 0) + 1
def writer():
    f = open(out, 'a'); f.write('epoch,sent,ok,err,shed,p50_ms,p99_ms,max_ms,errtypes\n'); f.flush()
    while not (stop.is_set() and not buckets):
        time.sleep(1); now = int(time.time())
        with lock:
            ready = sorted(k for k in buckets if k < now - 4 or stop.is_set())
            rows = [(k, buckets.pop(k)) for k in ready]
        for k, b in rows:
            L = sorted(b['lat']); q = lambda p: round(L[min(len(L) - 1, int(p * len(L)))], 2) if L else ''
            f.write(f"{k},{b['sent']},{b['ok']},{b['err']},{b['shed']},{q(0.5)},{q(0.99)},{round(L[-1], 2) if L else ''},"
                    f"{';'.join(f'{e}:{c}' for e, c in b['et'].items())}\n")
        f.flush()
        if stop.is_set() and not buckets: break
    f.close()
wt = threading.Thread(target=writer, daemon=True); wt.start()
val = os.urandom(100); i = 0; nxt = time.time()
while not stop.is_set() and not os.path.exists(out + '.stop'):
    nxt += 1.0 / rate; d = nxt - time.time()
    if d > 0: time.sleep(d)
    t = time.time(); sec = int(t); i += 1
    with lock:
        b = bucket(sec); b['sent'] += 1
        if inflight[0] >= 200: b['shed'] += 1; continue
        inflight[0] += 1
    k = random.randrange(10000)
    try:
        fut = s.execute_async(ins, (k, val)) if i % 2 else s.execute_async(sel, (k,))
        fut.add_callbacks(lambda r, sec=sec, t=t: done(sec, t, True),
                          lambda e, sec=sec, t=t: done(sec, t, False, type(e).__name__))
    except Exception as e:
        done(sec, t, False, type(e).__name__)
time.sleep(2.5); stop.set(); wt.join(timeout=10)
os._exit(0)
