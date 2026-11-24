"""C9 3-b confirm: bundled python driver (lib/cassandra-driver-internal-only-3.29.0.zip) and an authenticated session
(PlainTextAuthProvider, native protocol 4, 127.0.0.1:9042)."""
import glob, os, sys

CH = '/mydata/s4/cassandra-base'


def driver():
    lib = CH + '/lib'
    z = max(glob.glob(lib + '/cassandra-driver-internal-only-*.zip'))
    ver = os.path.splitext(os.path.basename(z))[0][len('cassandra-driver-internal-only-'):]
    sys.path.insert(0, os.path.join(z, 'cassandra-driver-' + ver))
    for p in ('pure_sasl-', 'wcwidth-', 'pyasyncore-'):
        zz = glob.glob(os.path.join(lib, p + '*.zip'))
        if zz:
            sys.path.insert(0, max(zz))


def connect(user, pw, timeout=30, const_reconnect=False, schema=False):
    driver()
    from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
    from cassandra.policies import DCAwareRoundRobinPolicy, ConstantReconnectionPolicy
    from cassandra.auth import PlainTextAuthProvider
    from cassandra import ConsistencyLevel
    prof = ExecutionProfile(consistency_level=ConsistencyLevel.ONE, request_timeout=timeout,
                            load_balancing_policy=DCAwareRoundRobinPolicy(local_dc='datacenter1'))
    kw = dict(port=9042, protocol_version=4, token_metadata_enabled=False, schema_metadata_enabled=schema,
              execution_profiles={EXEC_PROFILE_DEFAULT: prof}, connect_timeout=20,
              auth_provider=PlainTextAuthProvider(username=user, password=pw))
    if const_reconnect:
        kw['reconnection_policy'] = ConstantReconnectionPolicy(1.0, max_attempts=None)
    cl = Cluster(['127.0.0.1'], **kw)
    return cl, cl.connect()
