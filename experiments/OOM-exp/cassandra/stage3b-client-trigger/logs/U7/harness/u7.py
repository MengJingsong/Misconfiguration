#!/usr/bin/env python3
"""U7 client, stage 3-b confirm copy (2026-11-23) of the stage-2 u7.py (case file §2.5): bundled python driver 3.29.0,
protocol v4, one node 127.0.0.1, PasswordAuthenticator + CassandraAuthorizer on.
Changes from stage 2: tree path /mydata/s4/3b-U7/cassandra; ddl creates the admin schema (u7.t, vks.t), the attacker role
u7atk (MODIFY on u7.t only) and the victim role victim (SELECT, MODIFY on keyspace vks) as the superuser; new 'privcheck'
(what the attacker may and may not do); count/settings always as the superuser.
  u7.py ddl                                superuser cassandra/cassandra (retry <= 60 s): schema, roles, GRANTs, LIST
  u7.py privcheck                          as u7atk: statements that must be Unauthorized, and the one that must pass
  u7.py send --kind {update|delete} --p P --q Q [--k0 K0] [--user u7atk] --out FILE
                                           one prepared EXECUTE with k IN (K0..K0+P-1), c IN (0..Q-1), CL ONE, timeout 1800 s
  u7.py count --k K                        SELECT count(*) FROM u7.t WHERE k = K (superuser)
  u7.py settings                           resolved values from system_views.settings (superuser)
"""
import argparse, sys, time
TREE = '/mydata/s4/3b-U7/cassandra'
sys.path.insert(0, TREE + '/lib/cassandra-driver-internal-only-3.29.0.zip/cassandra-driver-3.29.0')
from cassandra.cluster import Cluster  # noqa: E402
from cassandra.policies import WhiteListRoundRobinPolicy  # noqa: E402
from cassandra.auth import PlainTextAuthProvider  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402

PW = {'cassandra': 'cassandra', 'u7atk': 'atkpw', 'victim': 'vicpw'}

DDL = [
    "CREATE KEYSPACE IF NOT EXISTS u7 WITH replication = {'class':'SimpleStrategy','replication_factor':1}",
    'CREATE TABLE IF NOT EXISTS u7.t (k int, c int, v int, PRIMARY KEY (k, c))',
    "CREATE KEYSPACE IF NOT EXISTS vks WITH replication = {'class':'SimpleStrategy','replication_factor':1}",
    'CREATE TABLE IF NOT EXISTS vks.t (k int PRIMARY KEY, v blob)',
    "CREATE ROLE IF NOT EXISTS u7atk WITH PASSWORD = 'atkpw' AND LOGIN = true AND SUPERUSER = false",
    "CREATE ROLE IF NOT EXISTS victim WITH PASSWORD = 'vicpw' AND LOGIN = true AND SUPERUSER = false",
    'GRANT MODIFY ON TABLE u7.t TO u7atk',
    'GRANT SELECT ON KEYSPACE vks TO victim',
    'GRANT MODIFY ON KEYSPACE vks TO victim',
]


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
    ap.add_argument('--kind', default='update')
    ap.add_argument('--p', type=int)
    ap.add_argument('--q', type=int)
    ap.add_argument('--k0', type=int, default=0)
    ap.add_argument('--k', type=int)
    ap.add_argument('--user', default='u7atk')
    ap.add_argument('--out')
    a = ap.parse_args()
    if a.cmd == 'ddl':
        t_end = time.time() + 60
        while True:
            try:
                c, s = connect('cassandra'); break
            except Exception as e:
                if time.time() > t_end:
                    print('ddl login failed: %r' % e); sys.exit(1)
                time.sleep(3)
        for q in DDL:
            s.execute(q, timeout=60)
            print('superuser: %s' % q)
        for r in ('u7atk', 'victim'):
            for row in s.execute('LIST ALL PERMISSIONS OF %s' % r, timeout=60):
                print('perm %s' % '|'.join(str(x) for x in row))
        for row in s.execute('LIST ROLES', timeout=60):
            print('role %s' % '|'.join(str(x) for x in row))
        print('ddl ok t=%d' % now())
        c.shutdown()
    elif a.cmd == 'privcheck':
        c, s = connect('u7atk')
        checks = [('deny', 'SELECT * FROM u7.t LIMIT 1'), ('deny', 'SELECT * FROM vks.t LIMIT 1'),
                  ('deny', 'INSERT INTO vks.t (k, v) VALUES (1, 0x00)'),
                  ('deny', "CREATE KEYSPACE x WITH replication = {'class':'SimpleStrategy','replication_factor':1}"),
                  ('deny', 'CREATE TABLE u7.t2 (k int PRIMARY KEY)'), ('deny', 'ALTER TABLE u7.t ADD w int'),
                  ('deny', 'GRANT SELECT ON TABLE u7.t TO u7atk'),
                  ('allow', 'UPDATE u7.t SET v = 1 WHERE k = -1 AND c = -1')]
        for want, q in checks:
            try:
                s.execute(q, timeout=30); got = 'OK'
            except Exception as e:
                got = '%s: %s' % (type(e).__name__, str(e).replace('\n', ' ')[:160])
            ok = (want == 'allow') == (got == 'OK')
            print('privcheck want=%s %s got=%s :: %s' % (want, 'PASS' if ok else 'FAIL', got, q))
        c.shutdown()
    elif a.cmd == 'count':
        c, s = connect('cassandra')
        r = s.execute('SELECT count(*) FROM u7.t WHERE k = %d' % a.k, timeout=120).one()
        print('count k=%d rows=%d t=%d' % (a.k, r[0], now()))
        c.shutdown()
    elif a.cmd == 'settings':
        c, s = connect('cassandra')
        names = ['max_mutation_size', 'memtable_heap_space', 'native_transport_max_request_data_in_flight',
                 'native_transport_max_request_data_in_flight_per_ip', 'native_transport_max_message_size',
                 'native_transport_receive_queue_capacity', 'native_transport_max_threads', 'commitlog_segment_size',
                 'in_select_cartesian_product_warn_threshold', 'in_select_cartesian_product_fail_threshold',
                 'partition_keys_in_select_fail_threshold', 'write_request_timeout', 'native_transport_timeout',
                 'memtable_allocation_type', 'authenticator', 'authorizer', 'role_manager', 'network_authorizer',
                 'data_disk_usage_percentage_fail_threshold', 'native_transport_rate_limiting_enabled',
                 'native_transport_max_concurrent_connections', 'native_transport_max_concurrent_connections_per_ip']
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
