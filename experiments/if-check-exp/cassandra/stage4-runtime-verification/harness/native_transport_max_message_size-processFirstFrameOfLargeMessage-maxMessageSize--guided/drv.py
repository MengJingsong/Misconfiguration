"""The bundled Python driver on sys.path (copied from the networking_cache_size harness for native_transport_max_message_size, 2026-10-20). Python 3.9+."""
import glob, os, sys

C = os.environ.get('CASSANDRA_HOME', os.path.expanduser('~/cassandra-run1'))


def load():
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
