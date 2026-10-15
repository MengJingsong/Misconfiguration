"""Loads the Python driver bundled with cqlsh (lib/cassandra-driver-internal-only-*.zip), as bin/cqlsh.py does, and opens a session
on 127.0.0.1 with consistency ONE, a 200 s request timeout and FallthroughRetryPolicy (case 9b, 9c)."""
import glob, os, sys

CASS = os.environ.get('CASSANDRA_HOME', os.path.expanduser('~/cassandra-run1'))
LIB = os.path.join(CASS, 'lib')


def _zip(prefix):
    z = glob.glob(os.path.join(LIB, prefix + '*.zip'))
    return max(z) if z else None


_cql = _zip('cassandra-driver-internal-only-')
_ver = os.path.splitext(os.path.basename(_cql))[0][len('cassandra-driver-internal-only-'):]
sys.path.insert(0, os.path.join(_cql, 'cassandra-driver-' + _ver))
for _lib in ('pure_sasl-', 'wcwidth-', 'pyasyncore-'):
    _z = _zip(_lib)
    if _z:
        sys.path.insert(0, _z)

from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402
from cassandra.policies import FallthroughRetryPolicy  # noqa: E402

TIMEOUT = 200


def session():
    prof = ExecutionProfile(request_timeout=TIMEOUT, consistency_level=ConsistencyLevel.ONE, retry_policy=FallthroughRetryPolicy())
    c = Cluster(['127.0.0.1'], execution_profiles={EXEC_PROFILE_DEFAULT: prof}, connect_timeout=30)
    return c, c.connect()
