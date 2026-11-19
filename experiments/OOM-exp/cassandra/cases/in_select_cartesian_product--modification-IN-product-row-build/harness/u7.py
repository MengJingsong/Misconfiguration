#!/usr/bin/env python3
"""U7 client (case file §2.5), the tree's bundled python driver 3.29.0, protocol v4, one node 127.0.0.1.
  u7.py ddl [--auth]                       keyspace u7, table u7.t (k int, c int, v int, PRIMARY KEY (k, c));
                                           --auth: log in as cassandra/cassandra (retry <= 60 s) and create role u7
  u7.py send --kind {update|delete} --p P --q Q [--k0 K0] [--user u7] --out FILE
                                           one prepared EXECUTE with k IN (K0..K0+P-1), c IN (0..Q-1), CL ONE, timeout 1800 s
  u7.py count --k K [--user u7]            SELECT count(*) FROM u7.t WHERE k = K
  u7.py settings [--user cassandra]        resolved values from system_views.settings for the §2.2 constraints
Output lines are appended to --out (send) or stdout: key=value fields, t_* in epoch ms.
"""
import argparse, sys, time
TREE = '/mydata/s4/u7-w4/cassandra'
sys.path.insert(0, TREE + '/lib/cassandra-driver-internal-only-3.29.0.zip/cassandra-driver-3.29.0')
from cassandra.cluster import Cluster  # noqa: E402
from cassandra.policies import WhiteListRoundRobinPolicy  # noqa: E402
from cassandra.auth import PlainTextAuthProvider  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402

PW = {'cassandra': 'cassandra', 'u7': 'u7pw'}


def connect(user=None):
    kw = dict(contact_points=['127.0.0.1'], port=9042, protocol_version=4,
              load_balancing_policy=WhiteListRoundRobinPolicy(['127.0.0.1']), token_metadata_enabled=False,
              connect_timeout=30, control_connection_timeout=30)
    if user:
        kw['auth_provider'] = PlainTextAuthProvider(username=user, password=PW[user])
    c = Cluster(**kw)
    return c, c.connect()


def now():
    return int(time.time() * 1000)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd')
    ap.add_argument('--auth', action='store_true')
    ap.add_argument('--kind', default='update')
    ap.add_argument('--p', type=int)
    ap.add_argument('--q', type=int)
    ap.add_argument('--k0', type=int, default=0)
    ap.add_argument('--k', type=int)
    ap.add_argument('--user')
    ap.add_argument('--out')
    a = ap.parse_args()
    if a.cmd == 'ddl':
        user = None
        if a.auth:
            t_end = time.time() + 60
            while True:
                try:
                    c, s = connect('cassandra'); break
                except Exception as e:
                    if time.time() > t_end:
                        print('ddl login failed: %r' % e); sys.exit(1)
                    time.sleep(3)
        else:
            c, s = connect()
        s.execute("CREATE KEYSPACE IF NOT EXISTS u7 WITH replication = {'class':'SimpleStrategy','replication_factor':1}", timeout=60)
        s.execute('CREATE TABLE IF NOT EXISTS u7.t (k int, c int, v int, PRIMARY KEY (k, c))', timeout=60)
        if a.auth:
            s.execute("CREATE ROLE IF NOT EXISTS u7 WITH PASSWORD = 'u7pw' AND LOGIN = true AND SUPERUSER = false", timeout=60)
        print('ddl ok t=%d auth=%s' % (now(), a.auth))
        c.shutdown()
    elif a.cmd == 'count':
        c, s = connect(a.user)
        r = s.execute('SELECT count(*) FROM u7.t WHERE k = %d' % a.k, timeout=120).one()
        print('count k=%d rows=%d t=%d' % (a.k, r[0], now()))
        c.shutdown()
    elif a.cmd == 'settings':
        c, s = connect(a.user)
        names = ['max_mutation_size', 'memtable_heap_space', 'native_transport_max_request_data_in_flight',
                 'native_transport_max_request_data_in_flight_per_ip', 'native_transport_max_message_size',
                 'native_transport_receive_queue_capacity', 'native_transport_max_threads', 'commitlog_segment_size',
                 'in_select_cartesian_product_warn_threshold', 'in_select_cartesian_product_fail_threshold',
                 'partition_keys_in_select_fail_threshold', 'write_request_timeout', 'native_transport_timeout',
                 'memtable_allocation_type', 'authenticator', 'data_disk_usage_percentage_fail_threshold']
        for n in names:
            try:
                r = s.execute("SELECT name, value FROM system_views.settings WHERE name = %s", [n], timeout=30).one()
                print('setting %s=%s' % (n, r[1] if r else 'ABSENT'))
            except Exception as e:
                print('setting %s ERR %s' % (n, type(e).__name__))
        c.shutdown()
    elif a.cmd == 'send':
        out = open(a.out, 'a')
        c, s = connect(a.user)
        if a.kind == 'update':
            st = s.prepare('UPDATE u7.t SET v = ? WHERE k IN ? AND c IN ?')
            vals = [1, list(range(a.k0, a.k0 + a.p)), list(range(a.q))]
            body = 2 + 16 + 2 + 2 + 4 + (4 + 4) + (4 + 4 + 8 * a.p) + (4 + 4 + 8 * a.q) + 4
        else:
            st = s.prepare('DELETE FROM u7.t WHERE k IN ? AND c IN ?')
            vals = [list(range(a.k0, a.k0 + a.p)), list(range(a.q))]
            body = 2 + 16 + 2 + 2 + 4 + (4 + 4 + 8 * a.p) + (4 + 4 + 8 * a.q) + 4
        st.consistency_level = ConsistencyLevel.ONE
        b = st.bind(vals)
        t0 = now()
        out.write('send kind=%s p=%d q=%d k0=%d user=%s rows=%d wire_body_est=%d t_send=%d\n'
                  % (a.kind, a.p, a.q, a.k0, a.user, a.p * a.q, body, t0)); out.flush()
        try:
            s.execute(b, timeout=1800)
            res = 'OK'
        except Exception as e:
            res = 'ERR %s: %s' % (type(e).__name__, str(e).replace('\n', ' ')[:400])
        t1 = now()
        out.write('end kind=%s p=%d q=%d k0=%d t_end=%d latency_ms=%d outcome=%s\n' % (a.kind, a.p, a.q, a.k0, t1, t1 - t0, res))
        out.flush()
        try:
            c.shutdown()
        except Exception:
            pass


if __name__ == '__main__':
    main()
