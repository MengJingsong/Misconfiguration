#!/usr/bin/env python3
"""U9 stage 3-b confirm: the victim tenant (copied from U7's 3-b victim.py; role, table and driver path changed).
Role 'u9vic' (SELECT, MODIFY on keyspace vks only), its own table vks.vt, the same node 127.0.0.1 (bundled driver 3.29.0,
protocol v4). Steady light load: RATE ops/s alternating a 100-byte INSERT and a single-key SELECT (keys 0..999, CL ONE),
each async with a 5-s client timeout; at most 200 in flight (above that an op is recorded as 'skip'). One line per op to
<out>: t_send_ms,op,outcome,latency_ms. Ends when <stopfile> exists. Connection trouble at start is retried; later
failures are recorded per op (the driver reconnects every 1 s, so a restarted node is picked up again).
usage: victim.py <out.csv> <stopfile> [rate]"""
import os, sys, threading, time
sys.path.insert(0, '/mydata/s4/3b-U9/tree/lib/cassandra-driver-internal-only-3.29.0.zip/cassandra-driver-3.29.0')
from cassandra.cluster import Cluster  # noqa: E402
from cassandra.policies import WhiteListRoundRobinPolicy, ConstantReconnectionPolicy  # noqa: E402
from cassandra.auth import PlainTextAuthProvider  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402

OUT, STOP = sys.argv[1], sys.argv[2]
RATE = float(sys.argv[3]) if len(sys.argv) > 3 else 20.0
lock = threading.Lock()
lines = []
inflight = [0]


def now_ms():
    return int(time.time() * 1000)


def rec(t0, op, outcome):
    with lock:
        lines.append('%d,%s,%s,%d' % (t0, op, outcome, now_ms() - t0))
        inflight[0] -= 1


def main():
    f = open(OUT, 'a')
    f.write('# victim start %d rate %.1f\n' % (now_ms(), RATE)); f.flush()
    t_end = time.time() + 90
    while True:
        try:
            c = Cluster(contact_points=['127.0.0.1'], port=9042, protocol_version=4,
                        load_balancing_policy=WhiteListRoundRobinPolicy(['127.0.0.1']), token_metadata_enabled=False,
                        auth_provider=PlainTextAuthProvider(username='u9vic', password='u9vic-pw'),
                        reconnection_policy=ConstantReconnectionPolicy(1.0), connect_timeout=10,
                        control_connection_timeout=10)
            s = c.connect()
            ins = s.prepare('INSERT INTO vks.vt (k, v) VALUES (?, ?)')
            sel = s.prepare('SELECT v FROM vks.vt WHERE k = ?')
            break
        except Exception as e:
            f.write('# connect failed %d %r\n' % (now_ms(), e)); f.flush()
            if time.time() > t_end or os.path.exists(STOP):
                return
            time.sleep(2)
    ins.consistency_level = ConsistencyLevel.ONE
    sel.consistency_level = ConsistencyLevel.ONE
    payload = os.urandom(100)
    f.write('# victim connected %d\n' % now_ms()); f.flush()
    i = 0
    nxt = time.time()
    last_flush = time.time()
    while not os.path.exists(STOP):
        op = 'w' if i % 2 == 0 else 'r'
        k = (i // 2) % 1000
        t0 = now_ms()
        if inflight[0] >= 200:
            with lock:
                lines.append('%d,%s,skip,0' % (t0, op))
        else:
            with lock:
                inflight[0] += 1
            try:
                fut = s.execute_async(ins.bind([k, payload]) if op == 'w' else sel.bind([k]), timeout=5)
                fut.add_callbacks(lambda _r, t0=t0, op=op: rec(t0, op, 'ok'),
                                  lambda e, t0=t0, op=op: rec(t0, op, 'err:' + type(e).__name__))
            except Exception as e:
                rec(t0, op, 'err:' + type(e).__name__)
        i += 1
        nxt += 1.0 / RATE
        d = nxt - time.time()
        if d > 0:
            time.sleep(d)
        else:
            nxt = time.time()
        if time.time() - last_flush >= 1:
            with lock:
                out, lines[:] = list(lines), []
            if out:
                f.write('\n'.join(out) + '\n'); f.flush()
            last_flush = time.time()
    time.sleep(6)
    with lock:
        out, lines[:] = list(lines), []
    if out:
        f.write('\n'.join(out) + '\n')
    f.write('# victim stop %d inflight %d\n' % (now_ms(), inflight[0])); f.flush()
    try:
        c.shutdown()
    except Exception:
        pass


if __name__ == '__main__':
    main()
