#!/usr/bin/env python3
"""C9 3-b confirm: victim client. Role `victim` (SELECT + MODIFY on keyspace vks only), its own table vks.kv.
Fixed rate: every 50 ms one INSERT and one SELECT by key (20 writes/s + 20 reads/s), async, client timeout 2 s,
ConstantReconnectionPolicy(1 s) so it reconnects as soon as the node is back.
usage: c9b_victim.py --out DIR --stopfile FILE      runs until FILE exists
DIR/ops.csv: ms_start,ms_end,op,ok,lat_ms,err"""
import argparse, os, sys, threading, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from c9b_drv import driver, connect


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--stopfile', required=True)
    ap.add_argument('--period', type=float, default=0.05)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    driver()
    f = open(a.out + '/ops.csv', 'w', buffering=1)
    f.write('ms_start,ms_end,op,ok,lat_ms,err\n')
    lk = threading.Lock()

    def rec(t0, op, ok, err=''):
        t1 = time.time()
        with lk:
            f.write(f'{int(t0*1000)},{int(t1*1000)},{op},{1 if ok else 0},{(t1-t0)*1000:.1f},{err}\n')

    cl = s = pw = pr = None
    k = 0
    nxt = time.time()
    while not os.path.exists(a.stopfile):
        now = time.time()
        if now < nxt:
            time.sleep(nxt - now)
        nxt += a.period
        if time.time() - nxt > 1.0:      # fell behind (e.g. blocked connect): skip ticks, keep the fixed rate
            nxt = time.time() + a.period
        if s is None:
            t0 = time.time()
            try:
                cl, s = connect('victim', 'victim-pw', timeout=2, const_reconnect=True)
                pw = s.prepare('INSERT INTO vks.kv (k, v) VALUES (?, ?)')
                pr = s.prepare('SELECT v FROM vks.kv WHERE k = ?')
            except Exception as e:
                rec(t0, 'connect', False, type(e).__name__)
                s = None
                try:
                    cl.shutdown()
                except Exception:
                    pass
                time.sleep(0.5)
                continue
        k += 1
        for op, stmt, args in (('w', pw, (k % 100000, 'v%06d' % k)), ('r', pr, ((k * 7919) % 100000,))):
            t0 = time.time()
            try:
                fut = s.execute_async(stmt, args, timeout=2.0)
                fut.add_callbacks(lambda _r, t0=t0, op=op: rec(t0, op, True),
                                  lambda e, t0=t0, op=op: rec(t0, op, False, type(e).__name__))
            except Exception as e:
                rec(t0, op, False, type(e).__name__)
    time.sleep(2.5)
    f.close()
    try:
        cl.shutdown()
    except Exception:
        pass
    os._exit(0)


if __name__ == '__main__':
    main()
