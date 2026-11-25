#!/usr/bin/env python3
"""B9 3-b confirm victim (from R13's victim.py): role `victim` (SELECT+MODIFY on vks.kv only), raw v4, SASL PLAIN,
one connection from --src to 127.0.0.81, open loop at --rate ops/s alternating INSERT INTO vks.kv / SELECT FROM vks.kv,
CL ONE, client timeout 5 s, reconnect 1 s apart; ticks that fall while a request is pending are logged 'missed'.
Log lines: t_ms op latency_ms status   (OK | ERR:<code>:<text> | timeout | io:<e> | connect:<e> | missed | down)"""
import argparse, os, socket, struct, time
from cql4 import *


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='victim'); ap.add_argument('--pw', required=True)
    ap.add_argument('--rate', type=float, default=20); ap.add_argument('--out', required=True)
    ap.add_argument('--stop', required=True); ap.add_argument('--src', default='127.0.2.1')
    a = ap.parse_args()
    log = open(a.out, 'a', buffering=1)
    log.write('# victim start %s user=%s rate=%s src=%s pid=%d\n' % (time.strftime('%Y-%m-%dT%H:%M:%S%z'), a.user, a.rate, a.src, os.getpid()))
    s = None; n = 0; period = 1.0 / a.rate; nxt = time.time(); last_conn_try = 0; pay = 'x' * 64
    while not os.path.exists(a.stop):
        now = time.time()
        if now < nxt:
            time.sleep(min(nxt - now, 0.2)); continue
        while nxt + period <= now:
            log.write('%d - 0 missed\n' % (nxt * 1000)); nxt += period
        nxt += period
        if s is None:
            if now - last_conn_try < 1.0:
                log.write('%d - 0 down\n' % (now * 1000)); continue
            last_conn_try = now
            try:
                s = sock(src=a.src, timeout=5); login(s, a.user, a.pw)
            except Exception as e:
                log.write('%d connect %d connect:%s\n' % (now * 1000, (time.time() - now) * 1000, str(e)[:80].replace(' ', '_')))
                try: s.close()
                except Exception: pass
                s = None; continue
        n += 1
        if n % 2:
            op, q = 'W', "INSERT INTO vks.kv (k, v) VALUES (%d, '%s')" % (n, pay)
        else:
            op, q = 'R', 'SELECT v FROM vks.kv WHERE k = %d' % (n - 1)
        t0 = time.time()
        try:
            s.sendall(frame(OP['QUERY'], query_body(q), n % 32000)); _, rop, b = rd(s)
            status = 'OK' if rop == OP['RESULT'] else describe(rop, b).replace(' ', '_')
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
