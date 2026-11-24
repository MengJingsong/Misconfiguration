"""3-b confirm B20: load the Python driver bundled with the build copy (CASSANDRA_HOME) and open an authenticated
session over the native protocol (v4, CL ONE, 127.0.0.1). Used by admin.py, attacker.py and victim.py."""
import glob, os, sys, time
CASS = os.environ['CASSANDRA_HOME']
def _zip(prefix):
    z = glob.glob(os.path.join(CASS, 'lib', prefix + '*.zip')); return max(z) if z else None
_cql = _zip('cassandra-driver-internal-only-')
_ver = os.path.splitext(os.path.basename(_cql))[0][len('cassandra-driver-internal-only-'):]
sys.path.insert(0, os.path.join(_cql, 'cassandra-driver-' + _ver))
for _lib in ('pure_sasl-', 'wcwidth-', 'pyasyncore-', 'geomet-'):
    _z = _zip(_lib)
    if _z: sys.path.insert(0, _z)
from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT  # noqa: E402
from cassandra.policies import DCAwareRoundRobinPolicy, ConstantReconnectionPolicy  # noqa: E402
from cassandra.auth import PlainTextAuthProvider  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402

PASSWORDS = {'cassandra': 'cassandra', 'attacker': 'attacker-pw', 'victim': 'victim-pw', 'datarole': 'datarole-pw'}

def session(user, timeout=120.0, retry_s=0, **kw):
    prof = ExecutionProfile(request_timeout=timeout, consistency_level=ConsistencyLevel.ONE,
                            load_balancing_policy=DCAwareRoundRobinPolicy(local_dc='datacenter1'))
    t_end = time.time() + retry_s
    while True:
        cl = Cluster(['127.0.0.1'], protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof},
                     auth_provider=PlainTextAuthProvider(username=user, password=PASSWORDS[user]),
                     connect_timeout=10, token_metadata_enabled=False, **kw)
        try:
            return cl, cl.connect()
        except Exception as e:  # default superuser is created ~10 s after startup
            try: cl.shutdown()
            except Exception: pass
            if time.time() >= t_end: raise
            print(f'connect as {user} failed ({type(e).__name__}); retry', file=sys.stderr); time.sleep(3)
