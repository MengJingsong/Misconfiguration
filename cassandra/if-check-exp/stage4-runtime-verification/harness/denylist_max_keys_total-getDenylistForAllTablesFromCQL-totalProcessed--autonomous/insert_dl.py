#!/usr/bin/env python3
"""B3c (amended 2026-10-26): insert M keys per table t1..t4 into system_distributed.partition_denylist with the bundled driver.
usage: python3 -I insert_dl.py <driver zip> <M> <out file>
key i = 4-byte big-endian i followed by 32,764 bytes of 0xAB (32,768 B); prepared INSERT ... VALUES ('dl', ?, ?) at CL ONE.
A failed insert is retried up to 5 times with a reconnect. Output lines: INS table=tN ok=<n> failed=<n> retries=<n>; INS total ...
"""
import os, sys, time
_ver = os.path.splitext(os.path.basename(sys.argv[1]))[0][len('cassandra-driver-internal-only-'):]
sys.path.insert(0, os.path.join(sys.argv[1], 'cassandra-driver-' + _ver))   # as bin/cqlsh.py does
M = int(sys.argv[2])
out = open(sys.argv[3], 'a')
from cassandra import ConsistencyLevel
from cassandra.cluster import Cluster
from cassandra.policies import DCAwareRoundRobinPolicy

KEYLEN = 32768


def p(s):
    out.write(s + '\n'); out.flush(); print(s, flush=True)


def connect():
    c = Cluster(['127.0.0.1'], port=9042, protocol_version=5, load_balancing_policy=DCAwareRoundRobinPolicy(),
                token_metadata_enabled=False, connect_timeout=30, idle_heartbeat_interval=0)
    s = c.connect()
    s.default_timeout = 120
    ps = s.prepare("INSERT INTO system_distributed.partition_denylist (ks_name, table_name, key) VALUES ('dl', ?, ?)")
    ps.consistency_level = ConsistencyLevel.ONE
    return c, s, ps


c, s, ps = connect()
filler = b'\xab' * (KEYLEN - 4)
t0 = time.time()
tot_ok = tot_fail = tot_retry = 0
for t in range(1, 5):
    ok = fail = retries = 0
    for i in range(M):
        key = i.to_bytes(4, 'big') + filler
        for attempt in range(6):
            try:
                s.execute(ps, ('t%d' % t, key))
                ok += 1
                break
            except Exception as e:
                if attempt == 5:
                    fail += 1
                    p('INS error table=t%d i=%d %s %s' % (t, i, type(e).__name__, str(e)[:200]))
                    break
                retries += 1
                time.sleep(1)
                try:
                    c.shutdown()
                except Exception:
                    pass
                c, s, ps = connect()
    p('INS table=t%d ok=%d failed=%d retries=%d keylen=%d' % (t, ok, fail, retries, KEYLEN))
    tot_ok += ok; tot_fail += fail; tot_retry += retries
p('INS total ok=%d failed=%d retries=%d secs=%.1f' % (tot_ok, tot_fail, tot_retry, time.time() - t0))
c.shutdown()
