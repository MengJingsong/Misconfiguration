#!/usr/bin/env python3
"""B3c (amended 2026-10-25) of max_mutation_size-applySimpleConfig-max_mutation_size--autonomous: the driver requests of one arm.
usage: mmwrite.py <driver zip> <arm> <out file> <jmx 'once' cmd...>
  Bundled driver, protocol 5, DCAwareRoundRobinPolicy, token_metadata_enabled=False, FallthroughRetryPolicy (no request is retried).
  Creates ks (RF 1) and ks.big (k int PRIMARY KEY, v blob), waits 15 s, then per request: JMX before; execute (prepared INSERT,
  blob of zeros bound); wait 12 s (periodic sync 10 s: ActiveContentSize = synced content); JMX after; rows read back.
Lines: REQ arm= what= kind= keys= blob= outcome= exc= msg= over_before= over_after= delta_count= content_before= content_after=
       delta_content= rows_present=
"""
import os, subprocess, sys, time
_ver = os.path.splitext(os.path.basename(sys.argv[1]))[0][len('cassandra-driver-internal-only-'):]
sys.path.insert(0, os.path.join(sys.argv[1], 'cassandra-driver-' + _ver))   # as bin/cqlsh.py does
ARM = sys.argv[2]
out = open(sys.argv[3], 'a')
jmx = sys.argv[4:]
from cassandra.cluster import Cluster
from cassandra.policies import DCAwareRoundRobinPolicy, FallthroughRetryPolicy
from cassandra.query import BatchStatement, BatchType

KiB, MiB = 1024, 1048576
# (what, kind, keys, blob bytes)
PLAN = {
    'm1024': [('over', 'single', [1], MiB + 4 * KiB), ('under', 'single', [2], MiB - 4 * KiB),
              ('logged', 'logged', [11, 12], 614400), ('unlogged', 'unlogged', [21, 22], 614400)],
    'm2048': [('control_1M+4K', 'single', [1], MiB + 4 * KiB), ('over', 'single', [3], 2 * MiB + 4 * KiB),
              ('under', 'single', [4], 2 * MiB - 4 * KiB), ('control_logged', 'logged', [11, 12], 614400)],
    'mdef': [('over', 'single', [5], 4 * MiB + 4 * KiB), ('under', 'single', [6], 4 * MiB - 64 * KiB),
             ('info_1M+4K', 'single', [1], MiB + 4 * KiB)],
    'tdef': [('info_over', 'single', [1], MiB + 4 * KiB), ('info_under', 'single', [2], MiB - 4 * KiB)],
}
PLAN['sd'] = PLAN['m1024']


def p(s):
    out.write(s + '\n'); out.flush(); print(s, flush=True)


def jread():
    r = subprocess.run(jmx, capture_output=True, text=True, timeout=60)
    for l in r.stdout.splitlines():
        if l.startswith('MM ') and not l.startswith('MM ts_ms'):
            f = l[3:].split(',')
            return int(f[1]), int(f[2])
    return None, None


c = Cluster(['127.0.0.1'], port=9042, protocol_version=5, load_balancing_policy=DCAwareRoundRobinPolicy(),
            token_metadata_enabled=False, connect_timeout=30, default_retry_policy=FallthroughRetryPolicy())
s = c.connect()
s.default_timeout = 120
s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
s.execute("CREATE TABLE IF NOT EXISTS ks.big (k int PRIMARY KEY, v blob)")
ins = s.prepare("INSERT INTO ks.big (k, v) VALUES (?, ?)")
sel = s.prepare("SELECT k FROM ks.big WHERE k = ?")
time.sleep(15)
for what, kind, keys, blob in PLAN[ARM]:
    o0, c0 = jread()
    t0 = time.time()
    try:
        if kind == 'single':
            s.execute(ins, (keys[0], b'\x00' * blob), timeout=120)
        else:
            b = BatchStatement(batch_type=BatchType.LOGGED if kind == 'logged' else BatchType.UNLOGGED)
            for k in keys:
                b.add(ins, (k, b'\x00' * blob))
            s.execute(b, timeout=120)
        outcome, exc, msg = 'ACCEPTED', '-', '-'
    except Exception as e:
        outcome, exc, msg = 'REFUSED', type(e).__name__, str(e).replace('\n', ' ')[:300]
    dt = time.time() - t0
    time.sleep(12)
    o1, c1 = jread()
    present = [len(list(s.execute(sel, (k,)))) == 1 for k in keys]
    d = lambda a, b: (b - a) if (a is not None and b is not None) else 'n/a'
    p('REQ arm=%s what=%s kind=%s keys=%s blob=%d outcome=%s exc=%s secs=%.2f over_before=%s over_after=%s delta_count=%s '
      'content_before=%s content_after=%s delta_content=%s rows_present=%s msg=%s'
      % (ARM, what, kind, '/'.join(map(str, keys)), blob, outcome, exc, dt, o0, o1, d(o0, o1), c0, c1, d(c0, c1),
         '/'.join(str(x) for x in present), msg))
c.shutdown()
