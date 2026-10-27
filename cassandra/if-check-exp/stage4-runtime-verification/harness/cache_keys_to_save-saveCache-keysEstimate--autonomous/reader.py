#!/usr/bin/env python3
"""reader.py <host> : populate the key and row caches (B3c). Scans keyspace1.standard1 for its keys, then
SELECT * FROM keyspace1.standard1 WHERE key=? for every key once (protocol 4, consistency ONE, 100 in flight).
Prints one JSON line {"keys":n,"errors":e,"seconds":s}. Uses the build copy's bundled Python driver (CASSANDRA_HOME)."""
import glob, json, os, sys, time
CASS = os.environ.get('CASSANDRA_HOME', os.path.expanduser('~/s4-b8-kt/c'))
def find_zip(prefix):
    z = glob.glob(os.path.join(CASS, 'lib', prefix + '*.zip')); return max(z) if z else None
cql = find_zip('cassandra-driver-internal-only-')
ver = os.path.splitext(os.path.basename(cql))[0][len('cassandra-driver-internal-only-'):]
sys.path.insert(0, os.path.join(cql, 'cassandra-driver-' + ver))
for lib in ('pure_sasl-', 'wcwidth-', 'pyasyncore-'):
    z = find_zip(lib)
    if z: sys.path.insert(0, z)
from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
from cassandra.policies import WhiteListRoundRobinPolicy
from cassandra import ConsistencyLevel
from cassandra.concurrent import execute_concurrent_with_args
host = sys.argv[1]
prof = ExecutionProfile(request_timeout=120, consistency_level=ConsistencyLevel.ONE,
                        load_balancing_policy=WhiteListRoundRobinPolicy([host]))
cl = Cluster([host], protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof})
s = cl.connect()
t0 = time.time()
s.default_fetch_size = 5000
keys = [r.key for r in s.execute('SELECT key FROM keyspace1.standard1')]
st = s.prepare('SELECT * FROM keyspace1.standard1 WHERE key = ?')
res = execute_concurrent_with_args(s, st, [(k,) for k in keys], concurrency=100, raise_on_first_error=False)
err = sum(1 for ok, _ in res if not ok)
print(json.dumps({'keys': len(keys), 'errors': err, 'seconds': round(time.time() - t0, 1)}))
cl.shutdown()
sys.exit(1 if err else 0)
