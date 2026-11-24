#!/usr/bin/env python3
"""R21 3-b confirm (ms0611, 2026-11-23): the stage-2 admin client (bundled Python driver from $CASSANDRA_HOME/lib, protocol 4,
CL ONE, WhiteListRoundRobinPolicy([host]), request timeout 120 s) with login: every connection authenticates with
PlainTextAuthProvider as the role in env R21_USER / R21_PASS (default: the shipped superuser cassandra/cassandra).
  client.py <host> probe                  release_version (as R21_USER)
  client.py <host> settings <name> ...    system_views.settings (superuser; instrumentation)
  client.py <host> admin <atk_pw> <ten_pw>
        superuser only: CREATE ROLE attacker / tenant (LOGIN, not superuser); the admin schema
        ks.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck)) as in stage 2 and the tenant's own vic.kv (k int PRIMARY KEY, v text);
        GRANT SELECT, MODIFY ON TABLE ks.t TO attacker; GRANT SELECT, MODIFY ON TABLE vic.kv TO tenant;
        then LIST ALL PERMISSIONS OF each role and system_auth.roles
  client.py <host> authcheck              as the attacker (R21_USER=attacker): what the role can and cannot do
  client.py <host> clients                system_views.clients (superuser; who is connected from where)
One JSON object on stdout."""

import glob, json, os, sys, time

CASS = os.environ.get('CASSANDRA_HOME', '/mydata/s4/3b-R21/tree')
LIB = os.path.join(CASS, 'lib')


def find_zip(prefix):
    z = glob.glob(os.path.join(LIB, prefix + '*.zip'))
    return max(z) if z else None


cql = find_zip('cassandra-driver-internal-only-')
ver = os.path.splitext(os.path.basename(cql))[0][len('cassandra-driver-internal-only-'):]
sys.path.insert(0, os.path.join(cql, 'cassandra-driver-' + ver))
for lib in ('pure_sasl-', 'wcwidth-', 'pyasyncore-', 'geomet-', 'futures-'):
    z = find_zip(lib)
    if z:
        sys.path.insert(0, z)

from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT  # noqa: E402
from cassandra.policies import WhiteListRoundRobinPolicy, FallthroughRetryPolicy  # noqa: E402
from cassandra.auth import PlainTextAuthProvider  # noqa: E402
from cassandra.query import BatchStatement, BatchType  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402

USER = os.environ.get('R21_USER', 'cassandra')
PASS = os.environ.get('R21_PASS', 'cassandra')


def connect(host, timeout=120):
    prof = ExecutionProfile(request_timeout=timeout, consistency_level=ConsistencyLevel.ONE, retry_policy=FallthroughRetryPolicy(),
                            load_balancing_policy=WhiteListRoundRobinPolicy([host]))
    c = Cluster([host], port=9042, protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof},
                auth_provider=PlainTextAuthProvider(username=USER, password=PASS),
                schema_metadata_enabled=False, token_metadata_enabled=False,
                control_connection_timeout=60, connect_timeout=30, max_schema_agreement_wait=120)
    return c, c.connect()


def attempt(s, name, stmt, params=None):
    try:
        r = s.execute(stmt, params) if params is not None else s.execute(stmt)
        rows = list(r) if r is not None else []
        return {'check': name, 'stmt': stmt if isinstance(stmt, str) else str(stmt)[:120], 'result': 'ok', 'rows': len(rows)}
    except Exception as e:
        return {'check': name, 'stmt': stmt if isinstance(stmt, str) else str(stmt)[:120], 'result': type(e).__name__,
                'msg': str(e)[:300]}


def main(a):
    host, cmd = a[0], a[1]
    t0 = time.time()
    out = {'cmd': cmd, 'user': USER, 'start_ms': int(t0 * 1000)}
    c, s = connect(host)
    try:
        if cmd == 'probe':
            out['release_version'] = s.execute('SELECT release_version FROM system.local').one()[0]
        elif cmd == 'settings':
            got = {}
            for n in a[2:]:
                r = s.execute('SELECT name, value FROM system_views.settings WHERE name = %s', (n,)).one()
                got[n] = r[1] if r else None
            out['settings'] = got
        elif cmd == 'admin':
            atk, ten = a[2], a[3]
            stmts = [
                "CREATE ROLE attacker WITH PASSWORD = '%s' AND LOGIN = true AND SUPERUSER = false" % atk,
                "CREATE ROLE tenant WITH PASSWORD = '%s' AND LOGIN = true AND SUPERUSER = false" % ten,
                "CREATE KEYSPACE ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}",
                'CREATE TABLE ks.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck))',
                "CREATE KEYSPACE vic WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}",
                'CREATE TABLE vic.kv (k int PRIMARY KEY, v text)',
                'GRANT SELECT ON TABLE ks.t TO attacker',
                'GRANT MODIFY ON TABLE ks.t TO attacker',
                'GRANT SELECT ON TABLE vic.kv TO tenant',
                'GRANT MODIFY ON TABLE vic.kv TO tenant',
            ]
            done = []
            for st in stmts:
                s.execute(st)
                done.append(st.replace(atk, '<pw>').replace(ten, '<pw>'))
            out['statements'] = done
            out['agreement'] = c.control_connection.wait_for_schema_agreement()
            perms = {}
            for role in ('attacker', 'tenant'):
                perms[role] = [[r.role, r.resource, r.permission] for r in s.execute('LIST ALL PERMISSIONS OF %s' % role)]
            out['permissions'] = perms
            out['roles'] = [[r.role, r.is_superuser, r.can_login, sorted(r.member_of or [])]
                            for r in s.execute('SELECT role, is_superuser, can_login, member_of FROM system_auth.roles')]
            out['tables'] = [[r[0], r[1]] for r in s.execute("SELECT keyspace_name, table_name FROM system_schema.tables "
                                                              "WHERE keyspace_name IN ('ks', 'vic')")]
        elif cmd == 'authcheck':
            res = []
            res.append(attempt(s, 'own permissions', 'LIST ALL PERMISSIONS OF attacker'))
            res.append(attempt(s, 'write ks.t (MODIFY)', "INSERT INTO ks.t (pk, ck, v) VALUES (7, 0, 0x00)"))
            res.append(attempt(s, 'read ks.t (SELECT)', 'SELECT ck FROM ks.t WHERE pk = 7 AND ck = 0'))
            # the T request shape: an unlogged single-partition batch of 160 rows x 8 KiB (1.25 MiB) to one pk
            ps = s.prepare('INSERT INTO ks.t (pk, ck, v) VALUES (?, ?, ?)')
            b = BatchStatement(batch_type=BatchType.UNLOGGED, consistency_level=ConsistencyLevel.ONE)
            val = os.urandom(8192)
            for i in range(160):
                b.add(ps, (7, 1000 + i, val))
            try:
                s.execute(b)
                res.append({'check': 'T request: unlogged single-partition batch 160 x 8 KiB', 'result': 'ok'})
            except Exception as e:
                res.append({'check': 'T request: unlogged single-partition batch 160 x 8 KiB', 'result': type(e).__name__,
                            'msg': str(e)[:300]})
            b2 = BatchStatement(batch_type=BatchType.UNLOGGED, consistency_level=ConsistencyLevel.ONE)
            for i in range(160):
                b2.add(ps, (100 + i, 0, val))
            try:
                s.execute(b2)
                res.append({'check': 'contrast: unlogged MULTI-partition batch 160 x 8 KiB (160 pks)', 'result': 'ok'})
            except Exception as e:
                res.append({'check': 'contrast: unlogged MULTI-partition batch 160 x 8 KiB (160 pks)', 'result': type(e).__name__,
                            'msg': str(e)[:300]})
            res.append(attempt(s, 'write the tenant table (no grant)', "INSERT INTO vic.kv (k, v) VALUES (1, 'x')"))
            res.append(attempt(s, 'read the tenant table (no grant)', 'SELECT v FROM vic.kv WHERE k = 1'))
            res.append(attempt(s, 'create a keyspace (no CREATE)', "CREATE KEYSPACE atk WITH replication = "
                                                                   "{'class': 'SimpleStrategy', 'replication_factor': 1}"))
            res.append(attempt(s, 'create a table in ks (no CREATE)', 'CREATE TABLE ks.t2 (k int PRIMARY KEY)'))
            res.append(attempt(s, 'alter ks.t (no ALTER)', "ALTER TABLE ks.t WITH comment = 'x'"))
            res.append(attempt(s, 'truncate ks.t (MODIFY covers TRUNCATE)', 'TRUNCATE ks.t'))
            res.append(attempt(s, 'create a role (no CREATE on roles)', "CREATE ROLE x WITH PASSWORD = 'x' AND LOGIN = true"))
            res.append(attempt(s, 'read system_views.settings (no grant)', "SELECT value FROM system_views.settings "
                                                                           "WHERE name = 'authenticator'"))
            out['checks'] = res
        elif cmd == 'clients':
            out['clients'] = [[str(r.address), r.username, r.port] for r in
                              s.execute('SELECT address, port, username FROM system_views.clients')]
        else:
            raise SystemExit(__doc__)
    finally:
        try:
            c.shutdown()
        except Exception:
            pass
    out['seconds'] = round(time.time() - t0, 2)
    print(json.dumps(out), flush=True)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    try:
        main(sys.argv[1:])
    except SystemExit:
        raise
    except Exception as e:
        print(json.dumps({'cmd': sys.argv[2], 'user': USER, 'error': f'{type(e).__name__}: {str(e)[:400]}'}), flush=True)
