#!/usr/bin/env python3
"""U14 stage-2 client (design §2.5). Bundled Python driver from $CASSANDRA_HOME/lib, protocol 4,
WhiteListRoundRobinPolicy([host]), schema_metadata_enabled=False, token_metadata_enabled=False, max_schema_agreement_wait=0,
one session, one statement at a time, request timeout 120 s, PlainTextAuthProvider(user, password).
  client.py <host> <user> <pw> probe
  client.py <host> <user> <pw> settings <name> ...
  client.py <host> <user> <pw> setup <ks>                 as the superuser: wait for login (<= 180 s), CREATE ROLE u14 (LOGIN,
                                                          not SUPERUSER), LIST ROLES; then as u14: CREATE KEYSPACE <ks> (RF 1)
  client.py <host> <user> <pw> tablecount <ks>
  client.py <host> <user> <pw> namecheck <ks>             length of one table name of <ks> (and the keyspace name)
  client.py <host> <user> <pw> checkpoint <ks> <outdir> <pid> <tag>
  client.py <host> <user> <pw> create <ks> <names> <first> <last> <outdir> <pid> <ddl_cap_s> [<W>]
       names: long (t + 5-digit i + 216 x, 222 chars) | short (t + 5-digit i). With <W> (churn): after CREATE i, DROP i - W
       when i - W >= first. Per statement one line to <outdir>/client.csv (epoch ms, i, op, latency ms, result, detail).
       A timed-out statement is retried (<= 3 tries). 'Guardrail tables violated' -> rejected (not retried).
       After every 500 successful CREATEs: checkpoint (two jcmd GC.class_histogram, L = total of the 2nd; K = count of the
       keyspace's tables; MBean count) to <outdir>/checkpoints.jsonl. Stops at <last>, at node death (pid gone, or no
       reconnect within 60 s), or when DDL time (checkpoints excluded) exceeds <ddl_cap_s>.
One JSON object on stdout.
3-b confirm (2026-11-23, ms0640; copy of the U14 harness in /mydata/s4/3b-U14/harness):
  client.py <host> cassandra <pw> setup3b <ks> <victimks> as the superuser (roles, grants and admin schema only): CREATE ROLE u14
                                                          (attacker, LOGIN, not SUPERUSER) and victim (LOGIN); CREATE KEYSPACE
                                                          <ks> (admin-made, RF 1); GRANT CREATE ON KEYSPACE <ks> TO u14 (the only
                                                          grant of the attacker); CREATE KEYSPACE <victimks> + TABLE kv; GRANT
                                                          SELECT, MODIFY ON TABLE <victimks>.kv TO victim; LIST ROLES / LIST ALL
                                                          PERMISSIONS OF u14 / victim
  client.py <host> cassandra <pw> authprobe <ks> <victimks>  claim tests (pre-auth, data role, keyspace scope, creator grant)
  client.py <host> cassandra <pw> perms <role>            LIST ALL PERMISSIONS OF <role> (count + first rows)
  In 'create', when U14_SU="user:pw" is set, each checkpoint also counts the attacker's rows in LIST ALL PERMISSIONS OF u14
  through a separate superuser instrument session (the creator grants; not part of the attack)."""
import glob, json, os, re, subprocess, sys, time

CASS = os.environ.get('CASSANDRA_HOME', '/mydata/s4/3b-U14/cassandra')
LIB = os.path.join(CASS, 'lib')
JMXCLS = os.environ.get('U14_JMXCLS', '/mydata/s4/3b-U14/jmxcls')
JMXPORT = os.environ.get('U14_JMXPORT', '7214')


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

from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT, NoHostAvailable  # noqa: E402
from cassandra.policies import WhiteListRoundRobinPolicy, FallthroughRetryPolicy  # noqa: E402
from cassandra.auth import PlainTextAuthProvider  # noqa: E402
from cassandra import ConsistencyLevel, OperationTimedOut, InvalidRequest  # noqa: E402


def tname(names, i):
    return f't{i:05d}' + ('x' * 216 if names == 'long' else '')


def connect(host, user, pw, timeout=120):
    prof = ExecutionProfile(request_timeout=timeout, consistency_level=ConsistencyLevel.ONE, retry_policy=FallthroughRetryPolicy(),
                            load_balancing_policy=WhiteListRoundRobinPolicy([host]))
    c = Cluster([host], port=9042, protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof},
                auth_provider=PlainTextAuthProvider(username=user, password=pw),
                schema_metadata_enabled=False, token_metadata_enabled=False,
                control_connection_timeout=60, connect_timeout=30, max_schema_agreement_wait=0)
    return c, c.connect()


def pid_alive(pid):
    return os.path.exists(f'/proc/{pid}')


def hist(pid, path):
    try:
        r = subprocess.run(['jcmd', str(pid), 'GC.class_histogram'], capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return None, []
    out = r.stdout
    open(path, 'w').write(out)
    tot, top = None, []
    for l in out.splitlines():
        m = re.match(r'\s*(\d+):\s+(\d+)\s+(\d+)\s+(\S+)', l)
        if m and int(m.group(1)) <= 40:
            top.append([m.group(4), int(m.group(2)), int(m.group(3))])
        m = re.match(r'Total\s+(\d+)\s+(\d+)', l.strip())
        if m:
            tot = int(m.group(2))
    return tot, top


def mbeans():
    try:
        r = subprocess.run(['java', '-cp', JMXCLS, 'Jmx', JMXPORT, 'get', 'MBEANCOUNT', 'n'], capture_output=True, text=True, timeout=120)
        v = r.stdout.strip().rsplit('|', 1)[-1]
        return int(v) if v.isdigit() else v
    except Exception as e:
        return repr(e)[:80]


def tablecount(s, ks):
    rows = s.execute('SELECT table_name FROM system_schema.tables WHERE keyspace_name = %s', (ks,))
    return sum(1 for _ in rows)


SU_SESSION = {'c': None, 's': None}


def perm_count(role='u14'):
    """3-b: rows of LIST ALL PERMISSIONS OF <role> via a superuser instrument session (U14_SU), or None"""
    su = os.environ.get('U14_SU')
    if not su:
        return None
    try:
        if SU_SESSION['s'] is None:
            u, p = su.split(':', 1)
            SU_SESSION['c'], SU_SESSION['s'] = connect(os.environ.get('U14_HOST', '127.0.14.1'), u, p)
        rows = list(SU_SESSION['s'].execute(f'LIST ALL PERMISSIONS OF {role}'))
        return {'rows': len(rows), 'table_ALL_rows': sum(1 for r in rows if r.resource.startswith('<table ')),
                'other': sorted({f'{r.resource} {r.permission}' for r in rows if not r.resource.startswith('<table ')})[:8]}
    except Exception as e:
        return repr(e)[:160]


def checkpoint(s, ks, outdir, pid, tag, n):
    t0 = time.time()
    h1, _ = hist(pid, f'{outdir}/hist-{tag}-1.txt')
    h2, top = hist(pid, f'{outdir}/hist-{tag}-2.txt')
    try:
        k = tablecount(s, ks)
    except Exception as e:
        k = repr(e)[:120]
    r = {'tag': tag, 'n_ok': n, 'ms': int(time.time() * 1000), 'L1': h1, 'L': h2, 'K': k, 'mbeans': mbeans(), 'top40': top,
         'perms_u14': perm_count(), 'secs': round(time.time() - t0, 1)}
    with open(f'{outdir}/checkpoints.jsonl', 'a') as f:
        f.write(json.dumps(r) + '\n')
    return r


def run_create(host, user, pw, ks, names, first, last, outdir, pid, cap, W, out):
    os.makedirs(outdir, exist_ok=True)
    csvf = open(os.path.join(outdir, 'client.csv'), 'a')
    csvf.write('ms,i,op,lat_ms,result,detail\n')
    c, s = connect(host, user, pw)
    st = {'ok': 0, 'rejected': 0, 'error': 0, 'timeout_tries': 0, 'drops_ok': 0, 'last_ok_i': None, 'last_ok_ms': None}
    ddl_time = 0.0
    stopped = 'end'

    def execute(stmt, i, op):
        nonlocal c, s, ddl_time
        tries = 0
        while True:
            tries += 1
            t0 = time.time()
            try:
                s.execute(stmt)
                dt = time.time() - t0
                ddl_time += dt
                csvf.write(f'{int(time.time()*1000)},{i},{op},{dt*1000:.1f},ok,{tries}\n'); csvf.flush()
                return 'ok'
            except InvalidRequest as e:
                dt = time.time() - t0
                ddl_time += dt
                msg = str(e)
                res = 'rejected' if 'Guardrail tables violated' in msg else 'error'
                csvf.write(f'{int(time.time()*1000)},{i},{op},{dt*1000:.1f},{res},"{msg[:200]}"\n'); csvf.flush()
                if res == 'error':
                    out.setdefault('errors', []).append(msg[:300])
                return res
            except OperationTimedOut as e:
                dt = time.time() - t0
                ddl_time += dt
                st['timeout_tries'] += 1
                csvf.write(f'{int(time.time()*1000)},{i},{op},{dt*1000:.1f},timeout,{tries}\n'); csvf.flush()
                if not pid_alive(pid):
                    return 'dead'
                if tries >= 3:
                    return 'timeout'
            except NoHostAvailable as e:
                dt = time.time() - t0
                ddl_time += dt
                csvf.write(f'{int(time.time()*1000)},{i},{op},{dt*1000:.1f},nohost,"{str(e)[:150]}"\n'); csvf.flush()
                if not pid_alive(pid):
                    return 'dead'
                t1 = time.time()
                while time.time() - t1 < 60:
                    time.sleep(5)
                    if not pid_alive(pid):
                        return 'dead'
                    try:
                        c.shutdown()
                    except Exception:
                        pass
                    try:
                        c, s = connect(host, user, pw)
                        break
                    except Exception:
                        continue
                else:
                    return 'dead'
                if tries >= 3:
                    return 'timeout'
            except Exception as e:
                dt = time.time() - t0
                ddl_time += dt
                msg = repr(e)
                csvf.write(f'{int(time.time()*1000)},{i},{op},{dt*1000:.1f},error,"{msg[:200]}"\n'); csvf.flush()
                out.setdefault('errors', []).append(msg[:300])
                if not pid_alive(pid):
                    return 'dead'
                if tries >= 3:
                    return 'error'

    for i in range(first, last + 1):
        if ddl_time > cap:
            stopped = 'ddl_cap'
            break
        r = execute(f'CREATE TABLE IF NOT EXISTS "{ks}"."{tname(names, i)}" (k int PRIMARY KEY, v blob)', i, 'create')
        if r == 'dead':
            stopped = 'node_dead'
            break
        if r == 'ok':
            st['ok'] += 1
            st['last_ok_i'] = i
            st['last_ok_ms'] = int(time.time() * 1000)
        elif r == 'rejected':
            st['rejected'] += 1
        else:
            st['error'] += 1
        if W is not None and i - W >= first:
            r2 = execute(f'DROP TABLE IF EXISTS "{ks}"."{tname(names, i - W)}"', i - W, 'drop')
            if r2 == 'dead':
                stopped = 'node_dead'
                break
            if r2 == 'ok':
                st['drops_ok'] += 1
        if r == 'ok' and st['ok'] % 500 == 0:
            if not pid_alive(pid):
                stopped = 'node_dead'
                break
            try:
                cp = checkpoint(s, ks, outdir, pid, f'n{st["ok"]}', st['ok'])
                print(json.dumps({'checkpoint': cp['tag'], 'L': cp['L'], 'K': cp['K'], 'mbeans': cp['mbeans']}), file=sys.stderr, flush=True)
            except Exception as e:
                out.setdefault('checkpoint_errors', []).append(repr(e)[:200])
    csvf.close()
    try:
        c.shutdown()
    except Exception:
        pass
    out.update(st, stopped=stopped, ddl_seconds=round(ddl_time, 1))


def main(a):
    host, user, pw, cmd = a[0], a[1], a[2], a[3]
    t0 = time.time()
    out = {'cmd': cmd, 'args': a[4:], 'start_ms': int(t0 * 1000)}
    if cmd == 'create':
        ks, names, first, last, outdir, pid, cap = a[4], a[5], int(a[6]), int(a[7]), a[8], int(a[9]), float(a[10])
        W = int(a[11]) if len(a) > 11 else None
        run_create(host, user, pw, ks, names, first, last, outdir, pid, cap, W, out)
    elif cmd == 'setup3b':
        ks, vks = a[4], a[5]
        t1 = time.time()
        while True:
            try:
                c, s = connect(host, user, pw)
                break
            except Exception as e:
                if time.time() - t1 > 180:
                    raise
                time.sleep(3)
        out['login_wait_s'] = round(time.time() - t1, 1)
        stmts = ["CREATE ROLE IF NOT EXISTS u14 WITH PASSWORD = 'u14pw' AND LOGIN = true AND SUPERUSER = false",
                 "CREATE ROLE IF NOT EXISTS victim WITH PASSWORD = 'victimpw' AND LOGIN = true AND SUPERUSER = false",
                 f"CREATE KEYSPACE IF NOT EXISTS \"{ks}\" WITH replication = {{'class': 'SimpleStrategy', 'replication_factor': 1}}",
                 f"GRANT CREATE ON KEYSPACE \"{ks}\" TO u14",
                 f"CREATE KEYSPACE IF NOT EXISTS \"{vks}\" WITH replication = {{'class': 'SimpleStrategy', 'replication_factor': 1}}",
                 f"CREATE TABLE IF NOT EXISTS \"{vks}\".kv (k int PRIMARY KEY, v blob)",
                 f"GRANT SELECT ON TABLE \"{vks}\".kv TO victim",
                 f"GRANT MODIFY ON TABLE \"{vks}\".kv TO victim"]
        for q in stmts:
            s.execute(q)
        out['statements'] = stmts
        out['roles'] = [[r.role, r.super, r.login] for r in s.execute('LIST ROLES')]
        out['perms'] = {ro: [[r.role, r.resource, r.permission] for r in s.execute(f'LIST ALL PERMISSIONS OF {ro}')] for ro in ('u14', 'victim')}
        out['ks'] = ks
        c.shutdown()
    elif cmd == 'perms':
        c, s = connect(host, user, pw)
        rows = [[r.role, r.resource, r.permission] for r in s.execute(f'LIST ALL PERMISSIONS OF {a[4]}')]
        out['n'] = len(rows)
        out['first'] = rows[:12]
        c.shutdown()
    elif cmd == 'authprobe':
        from cassandra import Unauthorized, AuthenticationFailed  # noqa: F401
        ks, vks = a[4], a[5]
        res = []

        def attempt(who, session, q, expect):
            try:
                session.execute(q)
                got = 'ok'
            except Exception as e:
                got = f'{type(e).__name__}: {str(e)[:160]}'
            res.append({'role': who, 'stmt': q[:120], 'expect': expect, 'got': got,
                        'pass': (got == 'ok') if expect == 'ok' else got.startswith(expect)})

        def try_connect(who, u, p):
            try:
                if u is None:
                    prof = ExecutionProfile(request_timeout=30, load_balancing_policy=WhiteListRoundRobinPolicy([host]))
                    cc = Cluster([host], port=9042, protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof},
                                 schema_metadata_enabled=False, token_metadata_enabled=False, connect_timeout=15)
                    ss = cc.connect()
                else:
                    cc, ss = connect(host, u, p)
                got = 'connected'
                try:
                    ss.execute(f'CREATE TABLE "{ks}".probe_preauth (k int PRIMARY KEY)')
                    got += '; CREATE ok'
                except Exception as e:
                    got += f'; CREATE {type(e).__name__}'
                cc.shutdown()
            except Exception as e:
                got = f'{type(e).__name__}: {str(e)[:200]}'
            res.append({'role': who, 'stmt': 'connect + CREATE TABLE', 'expect': 'no connection', 'got': got,
                        'pass': not got.startswith('connected')})

        c, s = connect(host, user, pw)
        for q in ["CREATE ROLE IF NOT EXISTS nobody WITH PASSWORD = 'nobodypw' AND LOGIN = true",
                  "CREATE ROLE IF NOT EXISTS datarole WITH PASSWORD = 'datapw' AND LOGIN = true",
                  f'GRANT SELECT ON TABLE "{vks}".kv TO datarole', f'GRANT MODIFY ON TABLE "{vks}".kv TO datarole']:
            s.execute(q)
        out['setup'] = 'probe roles nobody (no grant), datarole (SELECT, MODIFY on victim table) created by the superuser'
        # 1. pre-auth: no credentials, wrong password
        try_connect('anonymous (no credentials)', None, None)
        try_connect('u14 wrong password', 'u14', 'wrong')
        # 2. no grant at all
        cn, sn = connect(host, 'nobody', 'nobodypw')
        attempt('nobody', sn, f'CREATE TABLE "{ks}".probe_nobody (k int PRIMARY KEY)', 'Unauthorized')
        cn.shutdown()
        # 3. data role
        cd, sd = connect(host, 'datarole', 'datapw')
        attempt('datarole', sd, f'INSERT INTO "{vks}".kv (k, v) VALUES (999999, 0x00)', 'ok')
        attempt('datarole', sd, f'CREATE TABLE "{ks}".probe_data (k int PRIMARY KEY)', 'Unauthorized')
        attempt('datarole', sd, f'CREATE TABLE "{vks}".probe_data (k int PRIMARY KEY)', 'Unauthorized')
        attempt('datarole', sd, "CREATE KEYSPACE probe_data_ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}", 'Unauthorized')
        cd.shutdown()
        s.execute(f'DELETE FROM "{vks}".kv WHERE k = 999999')
        # 4. attacker (CREATE ON KEYSPACE ks only)
        p0 = [[r.resource, r.permission] for r in s.execute('LIST ALL PERMISSIONS OF u14')]
        ca, sa = connect(host, 'u14', 'u14pw')
        attempt('u14', sa, "CREATE KEYSPACE probe_u14_ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}", 'Unauthorized')
        attempt('u14', sa, f'CREATE TABLE "{vks}".probe_u14 (k int PRIMARY KEY)', 'Unauthorized')
        attempt('u14', sa, f'SELECT * FROM "{vks}".kv LIMIT 1', 'Unauthorized')
        attempt('u14', sa, f'INSERT INTO "{vks}".kv (k, v) VALUES (1, 0x00)', 'Unauthorized')
        attempt('u14', sa, f'CREATE TABLE "{ks}".probe_u14 (k int PRIMARY KEY, v blob)', 'ok')
        p1 = [[r.resource, r.permission] for r in s.execute('LIST ALL PERMISSIONS OF u14')]
        attempt('u14', sa, f'INSERT INTO "{ks}".probe_u14 (k, v) VALUES (1, 0x00)', 'ok')
        attempt('u14', sa, f'DROP TABLE "{ks}".probe_u14', 'ok')
        time.sleep(2)
        p2 = [[r.resource, r.permission] for r in s.execute('LIST ALL PERMISSIONS OF u14')]
        ca.shutdown()
        out['perms_u14'] = {'before': p0, 'after_create': p1, 'after_drop': p2}
        out['roles'] = [[r.role, r.super, r.login] for r in s.execute('LIST ROLES')]
        c.shutdown()
        out['probe'] = res
        out['all_pass'] = all(x['pass'] for x in res)
    elif cmd == 'setup':
        ks = a[4]
        t1 = time.time()
        while True:
            try:
                c, s = connect(host, user, pw)
                break
            except Exception as e:
                if time.time() - t1 > 180:
                    raise
                time.sleep(3)
        out['login_wait_s'] = round(time.time() - t1, 1)
        s.execute("CREATE ROLE IF NOT EXISTS u14 WITH PASSWORD = 'u14pw' AND LOGIN = true AND SUPERUSER = false")
        out['roles'] = [[r.role, r.super, r.login] for r in s.execute('LIST ROLES')]
        c.shutdown()
        c, s = connect(host, 'u14', 'u14pw')
        s.execute(f"CREATE KEYSPACE IF NOT EXISTS \"{ks}\" WITH replication = {{'class': 'SimpleStrategy', 'replication_factor': 1}}")
        out['ks'] = ks
        c.shutdown()
    else:
        c, s = connect(host, user, pw)
        try:
            if cmd == 'probe':
                out['release_version'] = s.execute('SELECT release_version FROM system.local').one()[0]
            elif cmd == 'settings':
                got = {}
                for n in a[4:]:
                    r = s.execute('SELECT name, value FROM system_views.settings WHERE name = %s', (n,)).one()
                    got[n] = r[1] if r else None
                out['settings'] = got
            elif cmd == 'tablecount':
                out['tables'] = tablecount(s, a[4])
            elif cmd == 'namecheck':
                r = s.execute('SELECT keyspace_name, table_name FROM system_schema.tables WHERE keyspace_name = %s LIMIT 1', (a[4],)).one()
                out['ks_len'] = len(r[0]) if r else None
                out['table_len'] = len(r[1]) if r else None
                out['table'] = r[1] if r else None
            elif cmd == 'checkpoint':
                ks, outdir, pid, tag = a[4], a[5], int(a[6]), a[7]
                os.makedirs(outdir, exist_ok=True)
                out['cp'] = checkpoint(s, ks, outdir, pid, tag, None)
                out['cp'].pop('top40', None)
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
    if len(sys.argv) < 5:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
