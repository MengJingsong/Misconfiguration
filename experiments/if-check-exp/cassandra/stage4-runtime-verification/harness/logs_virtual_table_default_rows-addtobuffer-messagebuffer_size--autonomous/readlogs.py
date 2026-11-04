#!/usr/bin/env python3
"""(Paging is off: with paging on, a virtual table returns only the first page, 5000 rows at fetch_size 5000 — found in the 2026-10-28 shakedown.) Count the rows of system_views.system_logs (client-side), split at a millisecond timestamp (pre = timestamp <= split). usage: readlogs.py <lib dir> <split_ms> -> prints LOGROWS total=.. pre=.. post=.. minTs maxTs"""
import glob, os, sys, datetime
for z in glob.glob(os.path.join(sys.argv[1], '*.zip')):
    base = os.path.basename(z)[:-4]
    sys.path.insert(0, os.path.join(z, base.replace('-internal-only-', '-')) if base.startswith('cassandra-driver') else z)
from cassandra.cluster import Cluster
from cassandra.query import SimpleStatement
split = int(sys.argv[2])
c = Cluster(['127.0.0.1'], protocol_version=4, connect_timeout=30); s = c.connect(); s.default_timeout = 600
tot = pre = 0; lo = hi = None
for r in s.execute(SimpleStatement("SELECT timestamp FROM system_views.system_logs", fetch_size=None)):
    ms = int(r.timestamp.replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)
    tot += 1; pre += ms <= split
    lo = ms if lo is None or ms < lo else lo; hi = ms if hi is None or ms > hi else hi
print("LOGROWS total=%d pre=%d post=%d minTs=%s maxTs=%s" % (tot, pre, tot - pre, lo, hi), flush=True)
c.shutdown()
