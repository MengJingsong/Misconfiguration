#!/usr/bin/env python3
"""B3c (amended 2026-10-25): the two large inserts with the bundled driver (protocol 5).
usage: bigwrite.py <driver zip> <S MiB> <out file> <jmx sampler cmd...>
  creates ks.big (k int PRIMARY KEY, v blob), RF 1; key 1 blob S/2 + 1 MiB (expected refused), key 2 blob S/2 - 1 MiB (expected accepted);
  around each insert runs the given JMX 'once' command to read OverSizedMutations; reads both keys back.
Lines: BIG what=<refused|accepted> key= blob= outcome= exc= oversized_before= oversized_after= delta= row_present= msg=
"""
import subprocess, sys, time
import os
_ver = os.path.splitext(os.path.basename(sys.argv[1]))[0][len('cassandra-driver-internal-only-'):]
sys.path.insert(0, os.path.join(sys.argv[1], 'cassandra-driver-' + _ver))   # as bin/cqlsh.py does
S = int(sys.argv[2]) * 1048576
out = open(sys.argv[3], 'a')
jmx = sys.argv[4:]
from cassandra.cluster import Cluster
from cassandra.policies import DCAwareRoundRobinPolicy
from cassandra.query import SimpleStatement


def p(s):
    out.write(s + '\n'); out.flush(); print(s, flush=True)


def oversized():
    r = subprocess.run(jmx, capture_output=True, text=True, timeout=60)
    for l in r.stdout.splitlines():
        if l.startswith('CL ') and not l.startswith('CL ts_ms'):
            return int(l[3:].split(',')[2])
    return None


c = Cluster(['127.0.0.1'], port=9042, protocol_version=5, load_balancing_policy=DCAwareRoundRobinPolicy(),
            token_metadata_enabled=False, connect_timeout=30)
s = c.connect()
s.default_timeout = 120
s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
s.execute("CREATE TABLE IF NOT EXISTS ks.big (k int PRIMARY KEY, v blob)")
time.sleep(2)
ins = s.prepare("INSERT INTO ks.big (k, v) VALUES (?, ?)")   # bound value: the blob travels as bytes, not as a hex literal
for what, key, blob in (('refused', 1, S // 2 + 1048576), ('accepted', 2, S // 2 - 1048576)):
    b0 = oversized()
    t0 = time.time()
    try:
        s.execute(ins, (key, b'\x00' * blob), timeout=120)
        outcome, exc, msg = 'ACCEPTED', '-', '-'
    except Exception as e:
        outcome, exc, msg = 'REFUSED', type(e).__name__, str(e).replace('\n', ' ')[:300]
    dt = time.time() - t0
    time.sleep(1)
    b1 = oversized()
    rows = list(s.execute("SELECT k FROM ks.big WHERE k = %s", (key,)))
    p('BIG what=%s key=%d blob=%d outcome=%s exc=%s secs=%.2f oversized_before=%s oversized_after=%s delta=%s row_present=%s msg=%s'
      % (what, key, blob, outcome, exc, dt, b0, b1, (b1 - b0) if (b0 is not None and b1 is not None) else 'n/a', len(rows) == 1, msg))
c.shutdown()
