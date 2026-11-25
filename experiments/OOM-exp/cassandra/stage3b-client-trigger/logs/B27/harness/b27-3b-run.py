#!/usr/bin/env python3
"""B27 stage 3-b confirm (2026-11-24, pc99): B10's 3-b driver (logs/B10/harness/b10-3b-run.py) adapted to B27's verified
arm T2 (3,500 v5 connections x 7 in flight, 125,000-B value, heap 2 GiB / direct 2 GiB). Changes from B10's 3-b driver:
BASE; W = 7; client JVM sizing of the case (each spec group split into JVMs of <= 500 connections, -Xmx1g, direct 2g,
-Xss512k, eventLoopThreads=1, ulimit -n 100000, --connect-threads 64); a connect/login phase before the load (every
attacker JVM connects and logs in, prints 'ready', then all start together on a go-file; driver.txt 'connect start' and
'attack start' markers); TIME-WAIT check; pollers add server-side established connections (ss) and the auth pool
(Native-Transport-Auth-Requests pending/active); per-histogram QM / server connection; containment MemoryMax = H + D + 6 GiB
as stage 2; B27 readings and EXPECTED lines.
  b27-3b-run.py dataset <R>
  b27-3b-run.py run <run-id> <arm> <heap GiB> <spec> <R> [--seconds 240] [--window 7]
      spec: <auth>:<role>:<connections>[:<window>],...   e.g. login:attacker:3500 (T2 under auth, 7 JVMs x 500)

B10 stage 3-b confirm (2026-11-24, ms0640): b10-run.py (stage 2) with authentication on. Changes: auth yaml
(make-node-yaml-3b.sh: PasswordAuthenticator + CassandraAuthorizer), the data set also creates the roles (attacker: SELECT
on ks.t only; nogrant: LOGIN only; victim: SELECT+MODIFY on its own victim.kv), per-run privilege checks
(auth-setup.txt), the flood groups given as a spec (one client JVM per group: <auth>:<role>:<connections>, auth = login |
none), a victim role (victim.py, 10 ops/s) running from 30 s before the attack to 30 s after its end, driver.txt markers,
three client-auth JMX columns. Budget, data, payload, window, instruments: as stage 2.
  b10-3b-run.py dataset <R>
  b10-3b-run.py run <run-id> <arm> <heap GiB> <spec> <R> [--seconds S] [--window W]
      spec e.g. login:attacker:10,login:attacker:10   (T2 under auth)
Original docstring (stage 2): one clean-start node lifetime on pc72, case §2.5 steps 1-10. No Byteman, no yaml key of §2.3.

usage:
  b10-run.py dataset <R>                                  build data.pristine-<R> (schema + R rows in pk=0, flushed, drained)
  b10-run.py run <run-id> <arm> <heap GiB> <N> <R> [--throw] [--seconds S] [--per-jvm 10] [--calib]
      arm: T2 C2 I2 T4 T8 (label only; parameters come from the arguments). --calib = calibration (idle cqlsh timing
      before the warm-up, 60-s load, no histograms after t=20 except at 40/60).
Layout: BASE=/mydata/s4/b10-w1: cassandra/ (cp -a cassandra-base), classes/, harness/, node/, data.pristine-<R>/,
logs/<run-id>/ (session.log, stdout.txt, system.log, gc.log*, jmx-poll.csv, cg-poll.csv, histo-*.txt, flood-*.out,
summary.txt, run.json, hprof if any).
"""
import json, os, re, signal, subprocess, sys, threading, time

BASE = os.environ.get('B27_BASE', '/mydata/s4/3b-B27')
C = BASE + '/cassandra'
NODE = BASE + '/node'
HARNESS = os.path.dirname(os.path.abspath(__file__))
CLASSES = BASE + '/classes'
JMX = 7199
FLOOD_CP = f'{CLASSES}:{C}/build/classes/main:{C}/build/lib/jars/*'
QM = 'org.apache.cassandra.transport.messages.QueryMessage'
VALUE = 125000
M = VALUE + 74
W = 7
CAP = 1 << 20
CONNECT_THREADS = 64
PER_JVM = 500
DIRECT = 2

B_HEAP = 'java.lang:type=Memory'
B_DIRECT = 'java.nio:type=BufferPool,name=direct'
B_POOLU = 'org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=UsedSize'
B_POOLO = 'org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=OverflowSize'
B_RSIZE = 'org.apache.cassandra.metrics:type=Client,name=RequestsSize'
B_PAUSED = 'org.apache.cassandra.metrics:type=Client,name=PausedConnections'
B_DISC = 'org.apache.cassandra.metrics:type=Client,name=RequestDiscarded'
B_TOBP = 'org.apache.cassandra.metrics:type=Client,name=TimedOutBeforeProcessing'
B_NTRP = 'org.apache.cassandra.metrics:type=ThreadPools,path=transport,scope=Native-Transport-Requests,name=PendingTasks'
B_NTRA = 'org.apache.cassandra.metrics:type=ThreadPools,path=transport,scope=Native-Transport-Requests,name=ActiveTasks'
B_RSP = 'org.apache.cassandra.metrics:type=ThreadPools,path=request,scope=ReadStage,name=PendingTasks'
B_AUTHS = 'org.apache.cassandra.metrics:type=Client,name=AuthSuccess'
B_AUTHF = 'org.apache.cassandra.metrics:type=Client,name=AuthFailure'
B_CONN = 'org.apache.cassandra.metrics:type=Client,name=ConnectedNativeClients'
B_AUTHP = 'org.apache.cassandra.metrics:type=ThreadPools,path=transport,scope=Native-Transport-Auth-Requests,name=PendingTasks'
B_AUTHA = 'org.apache.cassandra.metrics:type=ThreadPools,path=transport,scope=Native-Transport-Auth-Requests,name=ActiveTasks'
PW = {'attacker': 'atkpw', 'nogrant': 'ngpw', 'victim': 'vicpw', 'cassandra': 'cassandra'}
SU = 'bin/cqlsh -u cassandra -p cassandra 127.0.0.1 9042'
POLL = [(B_HEAP, 'HeapMemoryUsage'), (B_DIRECT, 'MemoryUsed'), (B_DIRECT, 'Count'), (B_POOLU, 'Value'),
        (B_POOLO, 'Value'), (B_RSIZE, 'Value'), (B_PAUSED, 'Value'), (B_DISC, 'Count'), (B_TOBP, 'Count'),
        (B_NTRP, 'Value'), (B_NTRA, 'Value'), (B_RSP, 'Value'), (B_AUTHS, 'Count'), (B_AUTHF, 'Count'), (B_CONN, 'Value'),
        (B_AUTHP, 'Value'), (B_AUTHA, 'Value')]
POLL_COLS = ['ms', 'heap_used', 'direct_used', 'direct_count', 'pool_used', 'pool_overflow', 'global_in_use', 'paused',
             'discarded', 'timedout_before', 'ntr_pending', 'ntr_active', 'read_pending', 'auth_success', 'auth_failure',
             'connected_clients', 'auth_pending', 'auth_active']

LOGS = None
SESSION = SUMMARY = None
CHILDREN = []
NODE_PROC = None


def log(s):
    line = f'[{time.strftime("%F %T")} {int(time.time() * 1000)}] {s}'
    print(line, file=sys.stderr, flush=True)
    if SESSION:
        SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    if SUMMARY:
        SUMMARY.write(s + '\n'); SUMMARY.flush()
    log(s)


def sh(cmd, timeout=600, check=True, env=None, cwd=C, quiet=False):
    log('+ ' + cmd)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
    out = (r.stdout or '') + (r.stderr or '')
    if not quiet and SESSION:
        SESSION.write(out[-4000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed rc={r.returncode}: {cmd}\n{out[-1500:]}')
    return r.returncode, out


def daemons():
    return subprocess.run("ps -eo pid,cmd | grep '[C]assandraDaemon' || true", shell=True, capture_output=True,
                          text=True).stdout.strip()


def node_pid():
    for p in os.listdir('/proc'):
        if not p.isdigit():
            continue
        try:
            cl = open(f'/proc/{p}/cmdline').read()
        except OSError:
            continue
        if 'CassandraDaemon' in cl and BASE in cl:
            return int(p)
    return None


def stop_node():
    pid = node_pid()
    if pid is not None:
        sh(f'bin/nodetool -p {JMX} stopdaemon', check=False, timeout=120)
        for _ in range(60):
            if node_pid() is None:
                break
            time.sleep(1)
        pid = node_pid()
        if pid is not None:
            log(f'node did not stop; kill -9 {pid}')
            os.kill(pid, signal.SIGKILL)
            time.sleep(2)
    if NODE_PROC is not None:
        try:
            NODE_PROC.wait(timeout=30)
        except subprocess.TimeoutExpired:
            NODE_PROC.kill()
    left = daemons()
    note(f'after stop, CassandraDaemon processes on {os.uname().nodename.split(".")[0]}: ' + (left[:300] if left else 'none'))


def kill_children():
    for p in CHILDREN:
        if p.poll() is None:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except Exception:
                p.kill()


def fail(msg):
    note('FAIL: ' + msg)
    kill_children()
    stop_node()
    sys.exit(1)


def jmx(*args):
    _, out = sh(f'java -cp {CLASSES} Jmx {JMX} ' + ' '.join(f"'{a}'" for a in args), check=False, timeout=60,
                quiet=True)
    return out


def cgroup_dir(pid):
    for l in open(f'/proc/{pid}/cgroup'):
        if l.startswith('0::'):
            return '/sys/fs/cgroup' + l.strip()[3:]
    return None


def client_jvm_opts():
    return ' '.join(l.strip() for l in open(C + '/conf/jvm11-clients.options') if l.strip().startswith('-'))


def start_node(heap, unit, memmax_gib, data_src=None):
    """steps 1-2"""
    global NODE_PROC
    if daemons():
        fail('a CassandraDaemon already runs on this host: ' + daemons()[:200])
    sh(f'rm -rf {NODE}/data', check=False)
    if data_src:
        sh(f'cp -a {data_src} {NODE}/data')
    env = dict(os.environ, CASSANDRA_HOME=C, NODE=NODE)
    _, y = sh(f'bash {HARNESS}/make-node-yaml-3b.sh', env=env)
    note('yaml check: ' + y.strip().splitlines()[-1])
    env = dict(os.environ, CASSANDRA_CONF=NODE + '/conf', CASSANDRA_LOG_DIR=LOGS, CASSANDRA_HEAPDUMP_DIR=LOGS,
               MAX_HEAP_SIZE=f'{heap}G', MAX_DIRECT_MEMORY_SIZE=f'{DIRECT}G')
    env.pop('HEAP_NEWSIZE', None)
    env.pop('JVM_EXTRA_OPTS', None)
    memmax = memmax_gib * 1024 ** 3
    cmd = ['systemd-run', '--user', '--scope', '--unit', unit, '-p', f'MemoryMax={memmax}', '-p', 'MemorySwapMax=0',
           'bash', '-c', 'ulimit -n 100000 && exec bin/cassandra -f']
    log('+ ' + ' '.join(cmd))
    NODE_PROC = subprocess.Popen(cmd, cwd=C, env=env, stdout=open(LOGS + '/stdout.txt', 'w'),
                                 stderr=subprocess.STDOUT)
    t0 = time.time()
    pid = None
    while time.time() - t0 < 300:
        if NODE_PROC.poll() is not None:
            fail(f'node exited during start-up rc={NODE_PROC.returncode}; see stdout.txt')
        pid = pid or node_pid()
        if pid:
            _, st = sh(f'bin/nodetool -p {JMX} status', check=False, quiet=True)
            _, sb = sh(f'bin/nodetool -p {JMX} statusbinary', check=False, quiet=True)
            if re.search(r'^UN\s+127\.0\.0\.1\s', st, re.M) and re.search(r'^running\s*$', sb, re.M):
                log(f'node UN and native transport running after {time.time() - t0:.0f} s')
                break
        time.sleep(2)
    else:
        fail('node not UN / native transport not running in 300 s')
    # 3-b: wait for the default superuser (CassandraRoleManager setup runs ~10 s after start on a fresh data dir)
    t1 = time.time()
    while time.time() - t1 < 180:
        rc, o = sh(f'{SU} -e "SELECT now() FROM system.local"', check=False, timeout=60, quiet=True)
        if rc == 0:
            log(f'superuser login ok after {time.time() - t1:.0f} s'); break
        time.sleep(3)
    else:
        fail('superuser login not possible in 180 s')
    cg = cgroup_dir(pid)
    mm = open(cg + '/memory.max').read().strip()
    ms = open(cg + '/memory.swap.max').read().strip()
    note(f'node pid {pid} scope {cg} memory.max {mm} (want {memmax}) memory.swap.max {ms}')
    jvm = open(f'/proc/{pid}/cmdline').read().split('\0')
    note('jvm readback: ' + ' '.join(t for t in jvm if t.startswith(
        ('-Xmx', '-Xms', '-XX:MaxDirect', '-XX:+UseG1GC', '-XX:+UseParallel', '-XX:+UseConcMark', '-XX:+HeapDump',
         '-XX:OnOutOfMemoryError', '-XX:+CrashOnOutOfMemory', '-XX:+ExitOnOutOfMemory', '-javaagent', '-XX:HeapDumpPath'))))
    try:
        sl = open(LOGS + '/system.log', errors='replace').read()
        for k in ['native_transport_max_message_size', 'native_transport_max_request_data_in_flight=',
                  'native_transport_max_request_data_in_flight_per_ip', 'native_transport_receive_queue_capacity',
                  'native_transport_timeout', 'read_request_timeout', 'native_transport_throw_on_overload',
                  'native_transport_max_threads', 'native_transport_queue_max_item_age_threshold',
                  'native_transport_max_concurrent_connections=', 'native_transport_max_concurrent_connections_per_ip',
                  'native_transport_idle_timeout', 'native_transport_rate_limiting_enabled', 'native_transport_max_auth_threads',
                  'authenticator', 'authorizer', 'role_manager', 'roles_validity', 'permissions_validity',
                  'credentials_validity', 'concurrent_reads', 'allow_filtering_enabled']:
            m = re.search(re.escape(k) + r'=?([^;,\]]*)', sl)
            note(f'resolved {k.rstrip("=")}: {m.group(1).strip() if m else "not in system.log"}')
    except OSError:
        pass
    return pid, cg


def histogram(pid, path):
    h0 = int(time.time() * 1000)
    try:
        sh(f'jcmd {pid} GC.class_histogram > {path}', check=False, timeout=150, quiet=True)
    except subprocess.TimeoutExpired:
        # fix 2026-11-17 (after T8-r1): a histogram that hangs in GC thrash no longer aborts the run
        log(f'histogram {path} timed out after 150 s; jcmd killed, run continues')
        subprocess.run(f"pkill -f 'jcmd {pid} GC.class_histogram'", shell=True)
    h1 = int(time.time() * 1000)
    sc = server_conns()
    qm = bb = 0
    top = []
    try:
        for l in open(path, errors='replace'):
            p = l.split()
            if len(p) >= 4 and p[0].endswith(':'):
                if len(top) < 6:
                    top.append((p[3], int(p[2])))
                if p[3] == QM:
                    qm = int(p[1])
                if p[3] == '[B':
                    bb = int(p[2])
    except OSError:
        pass
    log(f'histogram {path}: {h0}-{h1} QueryMessage={qm} [B={bb} server_conns={sc} top={top[:4]}')
    return dict(h0=h0, h1=h1, qm=qm, bb=bb, top=top, sc=sc)


def server_conns():
    r = subprocess.run("ss -Htn state established '( sport = :9042 )' | wc -l", shell=True, capture_output=True,
                       text=True)
    try:
        return int(r.stdout.strip())
    except ValueError:
        return -1


def time_wait():
    r = subprocess.run("ss -Htan state time-wait | wc -l", shell=True, capture_output=True, text=True)
    return int(r.stdout.strip() or 0)


class CgPoller(threading.Thread):
    def __init__(self, cg, path):
        super().__init__(daemon=True)
        self.cg, self.f, self.stop_flag, self.max, self.events = cg, open(path, 'w'), False, 0, {}
        self.sc_max = 0
        self.f.write('ms,memory_current,oom_kill,max_events,server_conns\n')

    def run(self):
        while not self.stop_flag:
            try:
                cur = int(open(self.cg + '/memory.current').read())
                ev = dict(l.split() for l in open(self.cg + '/memory.events'))
                self.max = max(self.max, cur)
                self.events = ev
                sc = server_conns()
                self.sc_max = max(self.sc_max, sc)
                self.f.write(f'{int(time.time() * 1000)},{cur},{ev.get("oom_kill")},{ev.get("max")},{sc}\n'); self.f.flush()
            except (OSError, ValueError):
                pass
            time.sleep(2)


def flood(tag, conns, window, seconds, throw, out, auth='none', user='', go=None):
    args = (f'--host 127.0.0.1 --port 9042 --connections {conns} --window {window} --value-bytes {VALUE} '
            f'--seconds {seconds} --throw {"true" if throw else "false"} --retry-ms 100 --auth {auth} '
            f'--connect-threads {CONNECT_THREADS}')
    if auth == 'login':
        args += f' --user {user} --pw {PW[user]}'
    if go:
        args += f' --go-file {go}'
    cmd = (f'ulimit -n 100000 && exec java -Xmx1g -XX:MaxDirectMemorySize=2g -Xss512k -Dio.netty.eventLoopThreads=1 '
           f'{client_jvm_opts()} '
           f'-Dlogback.configurationFile={HARNESS}/flood-logback.xml '
           f'-cp "{FLOOD_CP}" org.apache.cassandra.transport.NativeFlood3b {args}')
    log(f'+ ({tag}) {cmd}')
    p = subprocess.Popen(cmd, shell=True, cwd=C, stdout=open(out, 'w'), stderr=subprocess.STDOUT,
                         start_new_session=True)
    CHILDREN.append(p)
    return p


def flood_total(path):
    total, start_ms, last = {}, None, {}
    for l in open(path, errors='replace'):
        m = re.match(r'^start ms=(\d+)', l)
        if m:
            start_ms = int(m.group(1))
        if l.startswith(('sec ', 'drain ', 'TOTAL')):
            d = {k: int(v) for k, v in re.findall(r'(\w+)=(-?\d+)', l)}
            last = d
            if l.startswith('TOTAL'):
                total = d
    return total or last, start_ms


def gc_pauses(path_glob_dir):
    """(epoch_ms, pause_ms, line) for every stop-the-world pause line of gc.log*"""
    import glob, datetime
    out = []
    for f in sorted(glob.glob(path_glob_dir + '/gc.log*')):
        for l in open(f, errors='replace'):
            if 'Pause' not in l or not re.search(r'\d+\.\d+ms\s*$', l):
                continue
            m = re.match(r'^\[(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3})([+-]\d{4})\]', l)
            if not m:
                continue
            ts = datetime.datetime.strptime(m.group(1) + m.group(2), '%Y-%m-%dT%H:%M:%S.%f%z').timestamp() * 1000
            out.append((int(ts), float(re.search(r'(\d+\.\d+)ms\s*$', l).group(1)), l.strip()))
    return sorted(out)


def dataset(R):
    global LOGS, SESSION, SUMMARY
    LOGS = f'{BASE}/logs/dataset-{R}'
    os.makedirs(LOGS, exist_ok=True)
    SESSION = open(LOGS + '/session.log', 'a'); SUMMARY = open(LOGS + '/summary.txt', 'w')
    pid, cg = start_node(2, f'oom-b27-3b-dataset-{R}', 10)
    sh(f'{SU} -e "CREATE KEYSPACE ks WITH replication = '
       "{'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE ks.t (pk int, ck int, v blob, "
       'PRIMARY KEY (pk, ck));"', timeout=120)
    roles = ("CREATE KEYSPACE victim WITH replication = {'class':'SimpleStrategy','replication_factor':1}; "
             "CREATE TABLE victim.kv (k int PRIMARY KEY, v text); "
             "CREATE ROLE attacker WITH PASSWORD = 'atkpw' AND LOGIN = true; GRANT SELECT ON TABLE ks.t TO attacker; "
             "CREATE ROLE nogrant WITH PASSWORD = 'ngpw' AND LOGIN = true; "
             "CREATE ROLE victim WITH PASSWORD = 'vicpw' AND LOGIN = true; GRANT SELECT ON TABLE victim.kv TO victim; "
             "GRANT MODIFY ON TABLE victim.kv TO victim;")
    open(LOGS + '/admin-setup.cql', 'w').write(roles.replace('; ', ';\n') + '\n')
    sh(f'{SU} -f {LOGS}/admin-setup.cql', timeout=120)
    csv = f'{BASE}/rows-{R}.csv'
    with open(csv, 'w') as f:
        for i in range(R):
            f.write(f'0,{i},0x{os.urandom(16).hex()}\n')
    t0 = time.time()
    rc, out = sh(f"{SU} --request-timeout=120 -e \"COPY ks.t (pk, ck, v) FROM '{csv}' "
                 f"WITH MAXBATCHSIZE=50 AND NUMPROCESSES=8\"", timeout=1200, check=False)
    note(f'COPY rc={rc} in {time.time() - t0:.0f} s: ' + ' | '.join(out.strip().splitlines()[-3:]))
    sh(f'bin/nodetool -p {JMX} flush', timeout=300)
    _, cnt = sh(f'{SU} --request-timeout=120 -e "SELECT count(*) FROM ks.t WHERE pk = 0"',
                timeout=300, check=False)
    note('count: ' + ' '.join(cnt.split()))
    sh(f'bin/nodetool -p {JMX} drain', timeout=300, check=False)
    stop_node()
    sh(f'rm -rf {BASE}/data.pristine-{R} && cp -a {NODE}/data {BASE}/data.pristine-{R}')
    note(f'data.pristine-{R} written; du: ' + sh(f'du -sh {BASE}/data.pristine-{R}', quiet=True)[1].strip())


def drv(msg):
    """driver.txt markers (victim_summary.py reads 'attack start ... at_ms' and the end marker)"""
    with open(LOGS + '/driver.txt', 'a') as f:
        f.write(f'{time.strftime("%F %T")} {msg} at_ms {int(time.time() * 1000)}\n')
    log('DRIVER ' + msg)


def privilege_checks():
    out = []
    def q(user, cql, tag):
        t0 = time.time()
        rc, o = sh(f'bin/cqlsh -u {user} -p {PW[user]} 127.0.0.1 9042 --request-timeout=60 -e "{cql}"', check=False,
                   timeout=120, quiet=True)
        o = ' | '.join(l.strip() for l in o.strip().splitlines() if l.strip())[-600:]
        out.append(f'[{tag}] as {user}: {cql}\n  rc={rc} {time.time() - t0:.2f}s: {o}')
    q('cassandra', 'LIST ROLES', 'roles')
    q('cassandra', 'LIST ALL PERMISSIONS OF attacker', 'perm-attacker')
    q('cassandra', 'LIST ALL PERMISSIONS OF nogrant', 'perm-nogrant')
    q('cassandra', 'LIST ALL PERMISSIONS OF victim', 'perm-victim')
    q('cassandra', 'SELECT now() FROM system.local', 'cqlsh-startup')
    q('attacker', 'SELECT pk FROM ks.t WHERE pk = 0 AND v = 0x00 ALLOW FILTERING', 'attacker-filter-read')
    q('attacker', 'SELECT pk FROM ks.t WHERE pk = 0 AND v = 0x00 ALLOW FILTERING', 'attacker-filter-read-2')
    q('attacker', 'INSERT INTO ks.t (pk, ck, v) VALUES (1, 1, 0x00)', 'attacker-no-modify')
    q('attacker', 'SELECT * FROM victim.kv LIMIT 1', 'attacker-no-victim')
    q('attacker', "CREATE KEYSPACE atk WITH replication = {'class':'SimpleStrategy','replication_factor':1}", 'attacker-no-ddl')
    q('nogrant', 'SELECT pk FROM ks.t WHERE pk = 0 AND v = 0x00 ALLOW FILTERING', 'nogrant-no-select')
    open(LOGS + '/auth-setup.txt', 'w').write('\n'.join(out) + '\n')
    note('privilege checks written to auth-setup.txt')


def parse_spec(spec):
    g = []
    for part in spec.split(','):
        f = part.split(':')            # <auth>:<role>:<connections>[:<window>] (window default: --window)
        g.append((f[0], f[1], int(f[2])) + ((int(f[3]),) if len(f) > 3 else ()))
    return g


def run(run_id, arm, heap, spec, R, throw, seconds, window, calib):
    global LOGS, SESSION, SUMMARY, W
    W = window
    groups0 = parse_spec(spec)
    n = sum(g[2] for g in groups0)
    groups = []                      # one client JVM per <= PER_JVM connections of a group
    for g in groups0:
        k = g[2]
        while k > 0:
            groups.append((g[0], g[1], min(k, PER_JVM)) + tuple(g[3:]))
            k -= min(k, PER_JVM)
    LOGS = f'{BASE}/logs/{run_id}'
    os.makedirs(LOGS, exist_ok=True)
    SESSION = open(LOGS + '/session.log', 'a'); SUMMARY = open(LOGS + '/summary.txt', 'w')
    note(f'run {run_id} arm={arm} heap={heap}G direct={DIRECT}G N={n} jvms={len(groups)} connect_threads={CONNECT_THREADS} W={W} value={VALUE} M={M} R={R} throw={throw} '
         f'seconds={seconds} spec={spec} calib={calib}')
    note('harness md5: ' + sh(f'md5sum {HARNESS}/*', quiet=True)[1].replace('\n', '; '))
    src = f'{BASE}/data.pristine-{R}'
    if not os.path.isdir(src):
        fail('no ' + src)
    if daemons() or subprocess.run("ps -eo pid,cmd | grep '[N]ativeFlood'", shell=True, capture_output=True,
                                   text=True).stdout.strip():
        fail('CassandraDaemon or NativeFlood already running')
    tw = time_wait()
    t_w = time.time()
    while tw + n > 26000 and time.time() - t_w < 120:
        time.sleep(5); tw = time_wait()
    note(f'TIME-WAIT check: {tw} + N {n} = {tw + n} (limit 26000) ' + ('ok' if tw + n <= 26000 else 'FAILED (recorded)'))
    # case §2.3 containment (not a budget): MemoryMax = H + D + 6 GiB; B27_MEMMAX_ADD overrides the 6.
    memmax = heap + DIRECT + int(os.environ.get('B27_MEMMAX_ADD', '6'))
    pid, cg = start_node(heap, f'oom-b27-3b-{run_id}', memmax, src)
    privilege_checks()
    # step 3 / calibration (c)
    if calib:
        t0 = time.time(); sh('bin/cqlsh 127.0.0.1 9042 -e "SELECT now() FROM system.local"', check=False, timeout=120)
        t_base = time.time() - t0
        t0 = time.time(); sh('bin/cqlsh 127.0.0.1 9042 --request-timeout=60 -e "SELECT pk FROM ks.t WHERE pk = 0 AND '
                             'v = 0x00 ALLOW FILTERING"', check=False, timeout=120)
        t_q = time.time() - t0
        t0 = time.time(); sh('bin/cqlsh 127.0.0.1 9042 --request-timeout=60 -e "SELECT pk FROM ks.t WHERE pk = 0 AND '
                             'v = 0x00 ALLOW FILTERING"', check=False, timeout=120)
        t_q2 = time.time() - t0
        note(f'CALIB (c): cqlsh startup {t_base*1000:.0f} ms; filtering read {t_q*1000:.0f} / {t_q2*1000:.0f} ms; '
             f'net {(min(t_q, t_q2) - t_base)*1000:.0f} ms (accept <= 400)')
    wa, wu = groups[0][0], groups[0][1]
    wp = flood('warmup', 1, 7, 10, False, LOGS + '/flood-warmup.out', 'login', 'attacker')   # B27 3-b: always the data role
    try:
        wp.wait(timeout=200)
    except subprocess.TimeoutExpired:
        os.killpg(wp.pid, signal.SIGKILL)
    time.sleep(20)
    # step 4
    hidle = histogram(pid, LOGS + '/histo-idle.txt')
    open(LOGS + '/meters-idle.txt', 'w').write(jmx('get', *[x for p in POLL for x in p]))
    # step 5
    stopf = LOGS + '/stop-poll'
    pj = subprocess.Popen(['java', '-cp', CLASSES, 'Jmx', str(JMX), 'poll', '2000', '100000', stopf] +
                          [x for p in POLL for x in p], stdout=open(LOGS + '/jmx-poll.csv', 'w'),
                          stderr=subprocess.STDOUT, start_new_session=True)
    CHILDREN.append(pj)
    cgp = CgPoller(cg, LOGS + '/cg-poll.csv'); cgp.start()
    # 3-b: victim role from 30 s before the attack
    vstop = LOGS + '/stop-victim'
    pv = subprocess.Popen(['python3', HARNESS + '/victim.py', '--user', 'victim', '--pw', PW['victim'], '--rate', '10',
                           '--out', LOGS + '/victim.txt', '--stop', vstop], stdout=open(LOGS + '/victim.out', 'w'),
                          stderr=subprocess.STDOUT, start_new_session=True)
    CHILDREN.append(pv)
    time.sleep(30)
    # step 6 (3-b B27): connect + log in every attacker connection first, then start the load together
    go = LOGS + '/go'
    drv(f'connect start spec={spec} jvms={len(groups)}')
    jvms = []
    for j, g in enumerate(groups):
        auth, user, k = g[:3]
        jvms.append(flood(f'flood-{j}', k, g[3] if len(g) > 3 else W, seconds, throw, f'{LOGS}/flood-{j}.out', auth,
                          user, go))
    ready = {}
    t_r = time.time()
    while time.time() - t_r < 900 and len(ready) < len(jvms):
        for jj in range(len(jvms)):
            if jj in ready:
                continue
            try:
                for l in open(f'{LOGS}/flood-{jj}.out', errors='replace'):
                    if l.startswith('ready ms='):
                        ready[jj] = l.strip()
            except OSError:
                pass
            if jj not in ready and jvms[jj].poll() is not None:
                ready[jj] = f'EXITED rc={jvms[jj].returncode}'
        if node_pid() is None:
            note('NODE GONE during the connect/login phase')
            break
        time.sleep(0.5)
    rsum = {}
    for jj, l in sorted(ready.items()):
        for k, v in re.findall(r'(connected|refused|authfail)=(\d+)', l):
            rsum[k] = rsum.get(k, 0) + int(v)
    rlast = max([int(re.search(r'ready ms=(\d+)', l).group(1)) for l in ready.values() if l.startswith('ready')] or [0])
    note(f'connect/login phase: {len(ready)}/{len(jvms)} JVMs ready in {time.time() - t_r:.1f} s; {rsum}; last ready ms {rlast}; '
         f'server conns {server_conns()}')
    drv(f'attack start spec={spec}')
    open(go, 'w').close()
    t0 = None
    for _ in range(6000):
        for jj in range(len(jvms)):
            try:
                for l in open(f'{LOGS}/flood-{jj}.out', errors='replace'):
                    m = re.match(r'^start ms=(\d+)', l)
                    if m:
                        t0 = int(m.group(1)) if t0 is None else min(t0, int(m.group(1)))
            except OSError:
                pass
        if t0 is not None or any(p.poll() is not None for p in jvms):
            break
        time.sleep(0.1)
    if t0 is None:
        t0 = int(time.time() * 1000)
        note('WARNING: no client start line; t0 = now')
    note(f't0 = {t0}')
    # steps 7-8
    step = 20 if heap <= 2 else 30
    marks = [20, 40, 60] if calib else list(range(20, seconds + 1, step))
    histos = []
    end_ms, death_ms = t0 + seconds * 1000, None
    while True:
        now = int(time.time() * 1000)
        if node_pid() is None:
            death_ms = now
            drv('daemon gone while attack running')
            note(f'NODE GONE at t={(now - t0)/1000:.1f} s')
            break
        if now >= end_ms:
            break
        if marks and now >= t0 + marks[0] * 1000:
            marks.pop(0)
            h = histogram(pid, f'{LOGS}/histo-{len(histos) + 1}.txt')
            h['t'] = (h['h0'] - t0) / 1000
            histos.append(h)
            continue
        time.sleep(1)
    # step 9
    if death_ms is not None:
        time.sleep(30)          # stage 2: clients killed 30 s after the node died (the victim's 'after' window)
        for p in jvms:
            if p.poll() is None:
                os.killpg(p.pid, signal.SIGKILL)
    else:
        dl = time.time() + 150
        while time.time() < dl and any(p.poll() is None for p in jvms):
            if node_pid() is None:
                death_ms = death_ms or int(time.time() * 1000)
                note('NODE GONE during client drain')
                time.sleep(20); break
            time.sleep(1)
        for p in jvms:
            if p.poll() is None:
                os.killpg(p.pid, signal.SIGKILL)
        if death_ms is None:
            drv('attack clients ended; daemon alive (hold end)')
    # 3-b: victim 30 s after the end (node dead: connection refused); already elapsed if the node died
    if death_ms is None:
        time.sleep(30)
    open(vstop, 'w').close()
    try:
        pv.wait(timeout=20)
    except subprocess.TimeoutExpired:
        os.killpg(pv.pid, signal.SIGKILL)
    open(stopf, 'w').close()
    time.sleep(3)
    meters_end = jmx('get', *[x for p in POLL for x in p]) if node_pid() else 'node gone'
    open(LOGS + '/meters-end.txt', 'w').write(meters_end)
    cgp.stop_flag = True
    kill_children()
    stop_node()
    left = subprocess.run("ps -eo pid,cmd | grep '[N]ativeFlood' || true", shell=True, capture_output=True,
                          text=True).stdout.strip()
    note('NativeFlood left: ' + (left[:200] or 'none'))
    vleft = subprocess.run("ps -eo pid,cmd | grep '[v]ictim.py' || true", shell=True, capture_output=True,
                           text=True).stdout.strip()
    note('victim.py left: ' + (vleft[:200] or 'none'))
    try:
        _, vs = sh(f'python3 {HARNESS}/victim_summary.py {LOGS}', check=False, quiet=True, cwd=LOGS)
        open(LOGS + '/victim-summary.txt', 'w').write(vs)
        note('VICTIM ' + vs.replace('\n', ' || ')[:1500])
    except Exception as e:
        note(f'victim summary failed: {e}')
    # step 10
    try:
        sh(f'cp {NODE}/../logs/{run_id}/system.log {LOGS}/ 2>/dev/null || true', check=False, quiet=True)
    except Exception:
        pass
    stdout = open(LOGS + '/stdout.txt', errors='replace').read()
    oom = re.search(r'java\.lang\.OutOfMemoryError[^\n]*', stdout)
    dump = re.search(r'Dumping heap to ([^\s]+)', stdout)
    sl = ''
    try:
        sl = open(LOGS + '/system.log', errors='replace').read()
    except OSError:
        pass
    sl_oom = re.search(r'^.*java\.lang\.OutOfMemoryError.*$', sl, re.M)
    first_err = re.search(r'^ERROR \[[^\]]+\].*$', sl, re.M)
    polls = []
    for l in open(LOGS + '/jmx-poll.csv', errors='replace'):
        p = l.strip().split(',')
        if len(p) == len(POLL_COLS) and p[0].isdigit():
            row = {}
            for k, v in zip(POLL_COLS, p):
                try:
                    row[k] = float(v)
                except ValueError:
                    row[k] = None
            polls.append(row)

    def mx(k):
        v = [r[k] for r in polls if r.get(k) is not None]
        return max(v) if v else None

    totals = {}
    for jj in range(len(jvms)):
        t, _ = flood_total(f'{LOGS}/flood-{jj}.out')
        for k, v in t.items():
            if k in ('sent', 'ok', 'warned', 'ovl_bytes', 'ovl_other', 'err', 'outstanding', 'refused', 'connected', 'authfail'):
                totals[k] = totals.get(k, 0) + v
                totals[f'g{jj}_{k}'] = v
    endpoint_ms = death_ms
    m_oom = re.search(r'^\S+\s+\[[^\]]+\] (\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d,\d{3}) .*\n(?:.*\n)?java\.lang\.OutOfMemoryError', sl, re.M)
    if m_oom and death_ms:
        import datetime
        ts = datetime.datetime.strptime(m_oom.group(1), '%Y-%m-%dT%H:%M:%S,%f').replace(tzinfo=datetime.timezone.utc).timestamp() * 1000
        note(f'first OOM line in system.log at t={(ts - t0) / 1000:.1f} s (node gone at t={(death_ms - t0) / 1000:.1f} s)')
    load_s = ((endpoint_ms or end_ms) - t0) / 1000
    pauses = gc_pauses(LOGS)
    ref = endpoint_ms or end_ms
    win = [p for p in pauses if ref - 60000 <= p[0] <= ref]
    frac = sum(p[1] for p in win) / 60000
    heap_b = heap * 1024 ** 3
    E = heap_b // 40
    KN = n * CAP + E
    qmax = max([h['qm'] for h in histos] or [0])
    per_conn = [round(h['qm'] / h['sc'], 3) for h in histos if h.get('sc', 0) > 0]
    breached = len(re.findall(r'breached limit', sl))
    import glob
    used_hist = []
    for g in [LOGS + '/gc.log'] + sorted(glob.glob(LOGS + '/gc.log.*')):
        try:
            for l in open(g, errors='replace'):
                mm = re.search(r'Pause (?:Young|Full|Remark)[^\n]*?(\d+)M->(\d+)M\((\d+)M\)', l)
                if mm:
                    used_hist.append(int(mm.group(2)))
        except OSError:
            pass
    bb_idle = hidle['bb']
    res = dict(run_id=run_id, arm=arm, heap_gib=heap, N=n, W=W, M=M, R=R, throw=throw, t0=t0,
               endpoint='OOM' if oom else ('node died, no OOM line' if death_ms else 'none'),
               oom_line=oom.group(0) if oom else None, endpoint_t_s=(endpoint_ms - t0) / 1000 if endpoint_ms else None,
               dump=dump.group(1) if dump else None, syslog_oom=sl_oom.group(0)[:300] if sl_oom else None,
               first_error=first_err.group(0)[:300] if first_err else None,
               histos=[dict(t=h['t'], qm=h['qm'], bb=h['bb'], top=h['top'][:4], dur_ms=h['h1'] - h['h0']) for h in histos],
               qm_idle=hidle['qm'], bb_idle=bb_idle, U_D1=qmax * M, K_N=KN, U_over_KN=qmax * M / KN,
               K_max_global_in_use=mx('global_in_use'), ntr_pending_max=mx('ntr_pending'),
               read_pending_max=mx('read_pending'), heap_used_max=mx('heap_used'), direct_used_max=mx('direct_used'),
               discarded_max=mx('discarded'), timedout_before_max=mx('timedout_before'), paused_max=mx('paused'),
               client=totals, ok_per_s=totals.get('ok', 0) / max(load_s, 1), load_s=load_s,
               gc_pause_frac_last60=frac, gc_pauses_n=len(pauses), gc_last5=[p[2][-110:] for p in pauses[-5:]],
               scope_mem_max=cgp.max, scope_events=cgp.events, spec=spec,
               auth_success_max=mx('auth_success'), auth_failure_max=mx('auth_failure'),
               connected_clients_max=mx('connected_clients'), auth_pending_max=mx('auth_pending'),
               connect_phase=rsum, connect_phase_s=(rlast - int(t_r * 1000)) / 1000 if rlast else None,
               qm_max=qmax, qm_per_server_conn=per_conn, qm_per_conn_max=max(per_conn) if per_conn else None,
               breached_lines=breached, server_conns_max=cgp.sc_max, G=heap_b // 10, E=E,
               post_gc_last5_MB=used_hist[-5:], jvms=len(groups))
    if dump and os.path.exists(dump.group(1)):
        res['dump_bytes'] = os.path.getsize(dump.group(1))
    json.dump(res, open(LOGS + '/run.json', 'w'), indent=1)
    for k, v in res.items():
        note(f'{k}: {v}')
    nw = n * W
    if not calib:
        note(f'EXPECTED K: max RequestsSize {res["K_max_global_in_use"]} (stage 2: <= 264 B); breached lines {breached} '
             f'(stage 2: 0); warned {totals.get("warned")}; ovl_bytes {totals.get("ovl_bytes")}; discarded {res["discarded_max"]}')
        note(f'QM max {qmax} (histograms); QM / server conn {per_conn}; NTR pending max {res["ntr_pending_max"]}; '
             f'endpoint {res["endpoint"]} at {res["endpoint_t_s"]}; scope events {cgp.events}')
    note('DONE')


if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'dataset':
        dataset(int(a[1]))
    else:
        throw = '--throw' in a
        calib = '--calib' in a
        seconds = int(a[a.index('--seconds') + 1]) if '--seconds' in a else 240
        window = int(a[a.index('--window') + 1]) if '--window' in a else 7
        try:
            run(a[1], a[2], int(a[3]), a[4], int(a[5]), throw, seconds, window, calib)
        except SystemExit:
            raise
        except BaseException as e:
            import traceback
            note('EXCEPTION ' + traceback.format_exc()[-1500:])
            kill_children()
            stop_node()
            sys.exit(2)
