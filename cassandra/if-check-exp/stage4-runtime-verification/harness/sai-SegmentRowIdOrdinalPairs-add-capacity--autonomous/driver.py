"""Bundled cqlsh driver (lib/cassandra-driver-internal-only-*.zip) on 127.0.28.1:9350, consistency ONE, 200 s timeout."""
import glob, os, sys
CASS = os.environ.get('CASSANDRA_HOME', os.path.expanduser('~/s4-sr'))
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
from cassandra.policies import FallthroughRetryPolicy, WhiteListRoundRobinPolicy  # noqa: E402
HOST, PORT = '127.0.28.1', 9350
def session():
    prof = ExecutionProfile(load_balancing_policy=WhiteListRoundRobinPolicy([HOST]), request_timeout=200,
                            consistency_level=ConsistencyLevel.ONE, retry_policy=FallthroughRetryPolicy())
    c = Cluster([HOST], port=PORT, execution_profiles={EXEC_PROFILE_DEFAULT: prof}, connect_timeout=30, protocol_version=5,
                 )
    return c, c.connect()
