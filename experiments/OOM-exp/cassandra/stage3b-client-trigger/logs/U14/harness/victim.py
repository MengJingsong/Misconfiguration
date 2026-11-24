#!/usr/bin/env python3
"""U14 3-b confirm (2026-11-23): victim tenant. Role 'victim' (SELECT, MODIFY on <vks>.kv only) through the same node, steady
light load at a fixed rate: alternating prepared INSERT (k in 0..999, 100-byte blob) and SELECT by key, issued asynchronously
every 1/<rate> s (no back-pressure from slow replies; at most 2,000 in flight, else the slot is logged 'skipped').
Driver request timeout 10 s, CL ONE, protocol 4, WhiteListRoundRobinPolicy([host]).
  victim.py <host> <user> <pw> <vks> <outdir> <stopfile> <rate_per_s>
<outdir>/victim.csv: issue_ms,op,lat_ms,result   (result: ok | OperationTimedOut | ReadTimeout | WriteTimeout | NoHostAvailable |
Unavailable | ... (exception class) | skipped). Runs until <stopfile> exists. Connection attempts retry every 2 s."""
import os, sys, threading, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import client as C  # noqa: E402  (driver path setup, connect())
from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT  # noqa: E402
from cassandra.policies import WhiteListRoundRobinPolicy, FallthroughRetryPolicy  # noqa: E402
from cassandra.auth import PlainTextAuthProvider  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402

host, user, pw, vks, outdir, stopf, rate = sys.argv[1:8]
rate = float(rate)
os.makedirs(outdir, exist_ok=True)
f = open(os.path.join(outdir, 'victim.csv'), 'a')
f.write('issue_ms,op,lat_ms,result\n'); f.flush()
lock = threading.Lock()
inflight = [0]


def rec(t0, op, res):
    with lock:
        f.write(f'{int(t0*1000)},{op},{(time.time()-t0)*1000:.1f},{res}\n')
        inflight[0] -= 1 if res != 'skipped' else 0


def connect():
    prof = ExecutionProfile(request_timeout=10, consistency_level=ConsistencyLevel.ONE, retry_policy=FallthroughRetryPolicy(),
                            load_balancing_policy=WhiteListRoundRobinPolicy([host]))
    c = Cluster([host], port=9042, protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof},
                auth_provider=PlainTextAuthProvider(username=user, password=pw), schema_metadata_enabled=False,
                token_metadata_enabled=False, control_connection_timeout=10, connect_timeout=10, max_schema_agreement_wait=0)
    s = c.connect()
    w = s.prepare(f'INSERT INTO "{vks}".kv (k, v) VALUES (?, ?)')
    r = s.prepare(f'SELECT v FROM "{vks}".kv WHERE k = ?')
    return c, s, w, r


sess = None
period = 1.0 / rate
i = 0
nxt = time.time()
blob = os.urandom(100)
while not os.path.exists(stopf):
    if sess is None:
        t0 = time.time()
        try:
            sess = connect()
            with lock:
                f.write(f'{int(time.time()*1000)},connect,{(time.time()-t0)*1000:.1f},ok\n'); f.flush()
        except Exception as e:
            with lock:
                f.write(f'{int(time.time()*1000)},connect,{(time.time()-t0)*1000:.1f},{type(e).__name__}\n'); f.flush()
            time.sleep(2)
            nxt = time.time()
            continue
    now = time.time()
    if now < nxt:
        time.sleep(nxt - now)
    t0 = time.time()
    nxt += period
    if nxt < t0 - 1:          # fell behind by > 1 s (e.g. this process paused): re-anchor, never burst
        nxt = t0 + period
    op = 'write' if i % 2 == 0 else 'read'
    k = (i // 2) % 1000
    i += 1
    if inflight[0] >= 2000:
        rec(t0, op, 'skipped')
        continue
    try:
        c, s, w, r = sess
        fut = s.execute_async(w, (k, blob)) if op == 'write' else s.execute_async(r, (k,))
        with lock:
            inflight[0] += 1
        fut.add_callbacks(lambda _res, t0=t0, op=op: rec(t0, op, 'ok'),
                          lambda exc, t0=t0, op=op: rec(t0, op, type(exc).__name__))
    except Exception as e:
        with lock:
            f.write(f'{int(t0*1000)},{op},0,{type(e).__name__}\n')
    if i % 50 == 0:
        with lock:
            f.flush()
with lock:
    f.flush()
try:
    sess and sess[0].shutdown()
except Exception:
    pass
f.close()
