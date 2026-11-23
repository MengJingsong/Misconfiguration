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
One JSON object on stdout."""
import glob, json, os, re, subprocess, sys, time

CASS = os.environ.get('CASSANDRA_HOME', '/mydata/s4/u14/cassandra')
LIB = os.path.join(CASS, 'lib')
JMXCLS = os.environ.get('U14_JMXCLS', '/mydata/s4/u14/jmxcls')
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


def checkpoint(s, ks, outdir, pid, tag, n):
    t0 = time.time()
    h1, _ = hist(pid, f'{outdir}/hist-{tag}-1.txt')
    h2, top = hist(pid, f'{outdir}/hist-{tag}-2.txt')
    try:
        k = tablecount(s, ks)
    except Exception as e:
        k = repr(e)[:120]
    r = {'tag': tag, 'n_ok': n, 'ms': int(time.time() * 1000), 'L1': h1, 'L': h2, 'K': k, 'mbeans': mbeans(), 'top40': top,
         'secs': round(time.time() - t0, 1)}
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
