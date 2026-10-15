"""Shared helpers for load-keys.py and read-keys.py (Integer_MAX_VALUE case 9c): the bundled Python driver and the keys.
Key i of a table is random.Random(seed * 10000019 + i).randbytes(K), so any key is regenerated from (seed, i, K) and no key
file is written (amended 2026-10-15). Python 3.9+."""
import glob, os, random, sys

C = os.environ.get('CASSANDRA_HOME', os.path.expanduser('~/cassandra-run3'))


def key(seed, i, K):
    return random.Random(seed * 10000019 + i).randbytes(K)


def driver():
    lib = os.path.join(C, 'lib')

    def find_zip(prefix):
        z = glob.glob(os.path.join(lib, prefix + '*.zip'))
        return max(z) if z else None
    cql = find_zip('cassandra-driver-internal-only-')
    ver = os.path.splitext(os.path.basename(cql))[0][len('cassandra-driver-internal-only-'):]
    sys.path.insert(0, os.path.join(cql, 'cassandra-driver-' + ver))
    for pre in ('pure_sasl-', 'wcwidth-', 'pyasyncore-'):
        z = find_zip(pre)
        if z:
            sys.path.insert(0, z)
    from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
    from cassandra.policies import DCAwareRoundRobinPolicy
    from cassandra import ConsistencyLevel
    # No token-aware routing (run-1 defect 1, 2026-10-15): the bundled driver hashes every routing key with its pure-Python
    # Murmur3, about 5 rows/s for 60,000-byte keys; one node needs no routing.
    cl = Cluster(['127.0.0.1'], protocol_version=5, token_metadata_enabled=False,
                 execution_profiles={EXEC_PROFILE_DEFAULT: ExecutionProfile(request_timeout=200, consistency_level=ConsistencyLevel.ONE,
                                                                            load_balancing_policy=DCAwareRoundRobinPolicy())})
    return cl, cl.connect()
