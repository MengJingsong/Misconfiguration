#!/usr/bin/env python3
"""Cluster-tier client for DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE (case 9c, amended 2026-10-15: protocol 4).
Bundled Python driver, native protocol 4, request timeout 60 s.
  dob-writes.py --ks <ks> --n <n> --value <V> --first <k>     n writes INSERT INTO <ks>.t (k, v) of V zero bytes, sent at once
  dob-writes.py --probe                                       one read of ks1.t
Prints one line: acked=<n> failed=<f> ms=<elapsed> (or probe=ok)."""
import argparse, glob, os, sys, time

CASS = os.environ.get('CASSANDRA_HOME', os.path.expanduser('~/cassandra-run1'))
LIB = os.path.join(CASS, 'lib')
z = max(glob.glob(os.path.join(LIB, 'cassandra-driver-internal-only-*.zip')))
ver = os.path.splitext(os.path.basename(z))[0][len('cassandra-driver-internal-only-'):]
sys.path.insert(0, os.path.join(z, 'cassandra-driver-' + ver))
for p in ('pure_sasl-', 'wcwidth-', 'pyasyncore-'):
    zz = glob.glob(os.path.join(LIB, p + '*.zip'))
    if zz:
        sys.path.insert(0, max(zz))
from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('--ks'); ap.add_argument('--n', type=int); ap.add_argument('--value', type=int); ap.add_argument('--first', type=int)
ap.add_argument('--probe', action='store_true')
a = ap.parse_args()
prof = ExecutionProfile(request_timeout=60, consistency_level=ConsistencyLevel.ONE)
c = Cluster(['127.0.0.1'], protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof})
s = c.connect()
try:
    if a.probe:
        s.execute('SELECT * FROM ks1.t LIMIT 1')
        print('probe=ok protocol=%d' % c.protocol_version)
    else:
        ps = s.prepare('INSERT INTO %s.t (k, v) VALUES (?, ?)' % a.ks)
        val = bytes(a.value)
        t0 = time.time()
        futs = [s.execute_async(ps, (a.first + i, val)) for i in range(a.n)]
        ok = bad = 0
        for f in futs:
            try:
                f.result(); ok += 1
            except Exception as e:
                bad += 1; print('error %s' % e, file=sys.stderr)
        print('acked=%d failed=%d ms=%d' % (ok, bad, (time.time() - t0) * 1000))
finally:
    c.shutdown()
