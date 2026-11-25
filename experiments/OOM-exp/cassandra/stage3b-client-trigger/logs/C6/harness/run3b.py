#!/usr/bin/env python3
"""C6 stage 3-b confirm driver (2026-11-24, ms0617). From the stage-2 run.py (same node layout, sampler, histograms, OOM
handling and dump scan), with: PasswordAuthenticator + CassandraAuthorizer (the only two yaml changes besides the node
lines), superuser setup of a victim role and an attacker role holding only CREATE ON ALL KEYSPACES, the attacker creating
`ks` and t0..t<M-1> on the RUNNING node (no template, no restart), then writing one 1 KiB row into t1..t<M-1>
(stage 2's arm T), and a victim role measuring its own table throughout.
usage:
  run3b.py attack <label> <M>              fresh node lifetime (heap 2 GiB, scope 8G); keeps run/ (data, commitlog) for replay
  run3b.py replay <label> [rewrite]         admin restart on the run/ left by the last attack (commit-log replay); if it
                                            comes up: 60 s of victim, then (rewrite) the attacker writes t1..t<M-1> again
  run3b.py down                             stop this harness's node and victim, if any
Output: /mydata/s4/3b-C6/runs/<label>/."""
import json, os, re, shutil, signal, subprocess, sys, threading, time

W = '/mydata/s4/3b-C6'
C = W + '/cassandra'
RD = W + '/run'
HARNESS = os.path.dirname(os.path.abspath(__file__))
ADDR, JMXPORT = '127.0.0.1', 7199
HEAP, SCOPE = '2G', '8G'
SU = ('cassandra', 'cassandra')
ATK = ('attacker', 'atk-pw-3b')
VIC = ('victim', 'vic-pw-3b')
G_ON = 'org.apache.cassandra.metrics:type=Table,name=AllMemtablesOnHeapDataSize'
SAMPLER_BEANS = [
    ('java.lang:type=Memory', 'HeapMemoryUsage'),
    ('java.lang:type=MemoryPool,name=G1 Old Gen', 'Usage'),
    ('java.lang:type=MemoryPool,name=G1 Old Gen', 'CollectionUsage'),
    ('java.lang:type=GarbageCollector,name=G1 Young Generation', 'CollectionCount'),
    ('java.lang:type=GarbageCollector,name=G1 Young Generation', 'CollectionTime'),
    ('java.lang:type=GarbageCollector,name=G1 Old Generation', 'CollectionCount'),
    ('java.lang:type=GarbageCollector,name=G1 Old Generation', 'CollectionTime'),
    (G_ON, 'Value'),
    ('org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation', 'Count'),
    ('org.apache.cassandra.metrics:type=ThreadPools,path=request,scope=MutationStage,name=CompletedTasks', 'Value'),
    ('org.apache.cassandra.metrics:type=ThreadPools,path=request,scope=MutationStage,name=PendingTasks', 'Value'),
    ('org.apache.cassandra.metrics:type=DroppedMessage,scope=MUTATION_REQ,name=Dropped', 'Count'),
]
SAMPLER_COLS = 'ms,heap_used,old_used,old_coll_used,young_n,young_ms,old_n,old_ms,K,blocked,mut_completed,mut_pending,mut_dropped'

args = sys.argv[1:]
if not args or args[0] not in ('attack', 'replay', 'down'):
    sys.exit(__doc__)
mode = args[0]
label = args[1] if mode in ('attack', 'replay') else 'down'
LOGS = f'{W}/runs/{label}'
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
SUM = {'label': label, 'mode': mode, 'args': args}
DEADLINE = float(open(W + '/deadline').read()) if os.path.exists(W + '/deadline') else time.time() + 3 * 3600


def log(s):
    line = f'[{time.strftime("%F %T")} {int(time.time()*1000)}] {s}'
    SESSION.write(line + '\n'); SESSION.flush()


def note(k, v):
    SUM[k] = v
    log(f'{k}: {json.dumps(v)[:3000]}')
    json.dump(SUM, open(LOGS + '/summary.json', 'w'), indent=1)


def mark(name):
    note('t_' + name, int(time.time() * 1000))


def sh(cmd, timeout=600, check=True, env=None, cwd=C, quiet=False):
    if not quiet:
        log('+ ' + cmd)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
    out = r.stdout + r.stderr
    if not quiet:
        SESSION.write(out[-4000:] + '\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed ({r.returncode}): {cmd}\n{out[-1500:]}')
    return r.returncode, out


def pid_of():
    for d in os.listdir('/proc'):
        if not d.isdigit():
            continue
        try:
            cl = open(f'/proc/{d}/cmdline').read()
        except OSError:
            continue
        if 'CassandraDaemon' in cl and f'-Dcassandra-pidfile={RD}/cassandra.pid' in cl:
            return int(d)
    return None


def daemons():
    return sh("ps -eo pid,cmd | grep '[C]assandraDaemon' | cut -c1-160 || true", check=False, quiet=True)[1].strip()


def stop_node(sig='TERM'):
    pid = pid_of()
    if pid is None:
        return
    log(f'stopping node pid {pid} (SIG{sig})')
    subprocess.run(['kill', '-' + sig, str(pid)])
    for _ in range(120):
        if pid_of() is None:
            return
        time.sleep(1)
    log(f'node did not stop; kill -9 {pid}')
    subprocess.run(['kill', '-9', str(pid)])
    time.sleep(2)


VICTIM = {'p': None}


def start_victim():
    stopf = LOGS + '/victim.stop'
    if os.path.exists(stopf):
        os.remove(stopf)
    VICTIM['p'] = subprocess.Popen(['python3', '-I', HARNESS + '/victim.py', '--user', VIC[0], '--pw', VIC[1], '--rate', '10',
                                    '--out', LOGS + '/victim.txt', '--stop', stopf, '--host', ADDR],
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=open(LOGS + '/victim.err', 'w'))
    mark('victim_start')


def stop_victim():
    p = VICTIM['p']
    if p is None:
        return
    open(LOGS + '/victim.stop', 'w').close()
    try:
        p.wait(timeout=15)
    except subprocess.TimeoutExpired:
        p.kill(); p.wait()
    VICTIM['p'] = None
    mark('victim_stop')


def fail(msg):
    note('FAIL', msg)
    stop_samplers()
    stop_victim()
    stop_node()
    collect()
    finish(keep_run=False)
    sys.exit(1)


def client(*a, user=None, timeout=3600, quiet=False):
    env = dict(os.environ, CASSANDRA_HOME=C)
    if user:
        env['CQL_USER'], env['CQL_PW'] = user
    cmd = ['python3', '-I', HARNESS + '/client.py', ADDR] + [str(x) for x in a]
    if not quiet:
        log('+ client ' + (user[0] if user else '-') + ' ' + json.dumps(cmd[4:])[:600])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, cwd='/')
    except subprocess.TimeoutExpired:
        return None
    out = r.stdout + r.stderr
    js = [l for l in out.splitlines() if l.startswith('{')]
    if not js and not quiet:
        SESSION.write(out[-2000:] + '\n'); SESSION.flush()
    return json.loads(js[-1]) if js else None


def jmx(*pairs):
    _, out = sh(f'java -cp {W}/jmxcls Jmx {JMXPORT} get ' + ' '.join(f"'{b}' {a}" for b, a in pairs), check=False, quiet=True, timeout=120)
    res = {}
    for l in out.splitlines():
        p = l.rsplit('|', 2)
        if len(p) == 3:
            res[p[0] + '|' + p[1]] = p[2]
    return [res.get(b + '|' + a) for b, a in pairs]


def hist(pid, tag, timeout=300):
    try:
        rc, out = sh(f'jcmd {pid} GC.class_histogram', check=False, quiet=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {'bb': None, 'bn': None, 'total': None, 'timeout': True}
    open(f'{LOGS}/hist-{tag}.txt', 'w').write(out)
    bb = bn = tot = r1 = None
    for l in out.splitlines():
        m = re.match(r'\s*\d+:\s+(\d+)\s+(\d+)\s+(\S+)', l)
        if m and m.group(3) == '[B':
            bn, bb = int(m.group(1)), int(m.group(2))
        m = re.match(r'Total\s+(\d+)\s+(\d+)', l.strip())
        if m:
            tot = int(m.group(2))
    return {'bb': bb, 'bn': bn, 'total': tot, 'ms': int(time.time() * 1000)}


def hist2(pid, tag):
    h1 = hist(pid, tag + '-1')
    h2 = hist(pid, tag + '-2')
    k = jmx((G_ON, 'Value'))[0]
    r = {'h1_total': h1['total'], 'total': h2['total'], 'bb': h2['bb'], 'bn': h2['bn'], 'K': int(k) if k and k.isdigit() else k,
         'ms': h2.get('ms')}
    note('hist ' + tag, r)
    return r


def readf(p):
    try:
        return open(p).read().strip()
    except OSError:
        return None


def cgroup_path(pid):
    for l in open(f'/proc/{pid}/cgroup'):
        if l.startswith('0::'):
            return '/sys/fs/cgroup' + l.strip()[3:]
    return None


SAMP = {'proc': None, 'stop': threading.Event(), 'thread': None, 'last_events': None}


def start_rss(pid, cg):
    def rssloop():
        rf = open(LOGS + '/rss.csv', 'a')
        rf.write('ms,rss_anon_kb,cg_current,cg_oom_kill,cg_oom\n')
        while not SAMP['stop'].is_set():
            st = readf(f'/proc/{pid}/status')
            if st is None:
                rf.write(f'{int(time.time()*1000)},gone,,,\n'); rf.flush()
                break
            m = re.search(r'RssAnon:\s+(\d+)', st)
            ev = readf(cg + '/memory.events') or ''
            SAMP['last_events'] = ev
            ok = re.search(r'oom_kill (\d+)', ev); oo = re.search(r'^oom (\d+)', ev, re.M)
            rf.write(f"{int(time.time()*1000)},{m.group(1) if m else ''},{readf(cg + '/memory.current')},"
                     f"{ok.group(1) if ok else ''},{oo.group(1) if oo else ''}\n")
            rf.flush()
            SAMP['stop'].wait(1)
        rf.close()
    SAMP['thread'] = threading.Thread(target=rssloop, daemon=True)
    SAMP['thread'].start()


def start_jmx_poll():
    stopf = f'{LOGS}/sampler.stop'
    if os.path.exists(stopf):
        os.remove(stopf)
    cmd = (f"java -cp {W}/jmxcls Jmx {JMXPORT} poll 1000 100000 {stopf} " + ' '.join(f"'{b}' {a}" for b, a in SAMPLER_BEANS))
    f = open(LOGS + '/sampler.csv', 'a')
    f.write(SAMPLER_COLS + '\n'); f.flush()
    SAMP['proc'] = subprocess.Popen(cmd, shell=True, stdout=f, stderr=open(LOGS + '/sampler.err', 'a'), cwd='/')


def stop_samplers():
    try:
        open(f'{LOGS}/sampler.stop', 'w').close()
    except OSError:
        pass
    SAMP['stop'].set()
    p = SAMP['proc']
    if p is not None:
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()
    if SAMP['thread'] is not None:
        SAMP['thread'].join(timeout=5)


def write_conf():
    if os.path.exists(RD):
        shutil.rmtree(RD)
    for d in ('logs', 'data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw', 'dump'):
        os.makedirs(f'{RD}/{d}')
    shutil.copytree(C + '/conf', RD + '/conf')
    lines = ['cluster_name: c6-3b', f'listen_address: {ADDR}', f'rpc_address: {ADDR}',
             'seed_provider:', '  - class_name: org.apache.cassandra.locator.SimpleSeedProvider', '    parameters:', f'      - seeds: "{ADDR}:7000"',
             'data_file_directories:', f'    - {RD}/data', f'commitlog_directory: {RD}/commitlog', f'hints_directory: {RD}/hints',
             f'saved_caches_directory: {RD}/saved_caches', f'cdc_raw_directory: {RD}/cdc_raw']
    keys = {l.split(':', 1)[0] for l in lines if re.match(r'^[A-Za-z_]+:', l)}
    out, skip = [], False
    for l in open(RD + '/conf/cassandra.yaml').read().splitlines():
        if l == 'authenticator:':
            raise RuntimeError('unexpected nested authenticator in yaml')
        m = re.match(r'^([A-Za-z_]+):', l)
        if m:
            skip = m.group(1) in keys
            if skip:
                continue
        elif skip and (l.startswith((' ', '\t', '-')) or l.strip() == '' or l.lstrip().startswith('#')):
            continue
        else:
            skip = False
        if re.match(r'^authenticator:', l):
            l = 'authenticator: PasswordAuthenticator'
        elif re.match(r'^authorizer:', l):
            l = 'authorizer: CassandraAuthorizer'
        out.append(l)
    open(RD + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- c6 3-b lines ----\n' + '\n'.join(lines) + '\n')
    sh(f'diff {C}/conf/cassandra.yaml {RD}/conf/cassandra.yaml > {LOGS}/yaml.diff; true', check=False)


NODE = {'popen': None}


def launch():
    if pid_of() is not None:
        fail('a node of this harness is already running')
    busy = sh('ss -ltn', quiet=True)[1]
    for w in (f'{ADDR}:7000', f'{ADDR}:9042', f':{JMXPORT}'):
        if re.search(re.escape(w) + r'\s', busy):
            fail(f'port {w} is busy')
    mem = int(re.search(r'MemAvailable:\s+(\d+)', open('/proc/meminfo').read()).group(1)) // 1024
    note('cotenancy', {'daemons': daemons() or 'none', 'MemAvailable_MiB': mem})
    if mem < 30 * 1024:
        fail('MemAvailable < 30 GiB')
    env = dict(os.environ, CASSANDRA_CONF=RD + '/conf', CASSANDRA_LOG_DIR=RD + '/logs', CASSANDRA_HEAPDUMP_DIR=RD + '/dump',
               MAX_HEAP_SIZE=HEAP, XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}')
    for k in ('HEAP_NEWSIZE', 'JVM_EXTRA_OPTS', 'JVM_OPTS'):
        env.pop(k, None)
    unit = f'c6-3b-{label.lower()}-{int(time.time())}'
    cmd = (f"systemd-run --user --scope --unit={unit} -p MemoryMax={SCOPE} -p MemorySwapMax=0 "
           f"bash -c 'ulimit -n 100000 && exec bin/cassandra -f -p {RD}/cassandra.pid' >> {RD}/stdout.txt 2>&1")
    log('+ ' + cmd)
    mark('launch')
    NODE['popen'] = subprocess.Popen(cmd, shell=True, cwd=C, env=env)
    return unit


def check_jvm(pid, unit):
    cg = cgroup_path(pid)
    mmax, sw = readf(cg + '/memory.max'), readf(cg + '/memory.swap.max')
    jvm = open(f'/proc/{pid}/cmdline').read().replace('\0', ' ')
    open(LOGS + '/jvm-cmdline.txt', 'w').write(jvm + '\n')
    flags = {f: (f in jvm) for f in ('-XX:+UseG1GC', '-XX:G1HeapRegionSize=16m', '-XX:+AlwaysPreTouch', '-XX:+HeapDumpOnOutOfMemoryError',
                                     '-XX:OnOutOfMemoryError=kill -9 %p', f'-Xmx{HEAP}', f'-Xms{HEAP}')}
    note('jvm', {'pid': pid, 'unit': unit, 'cgroup': cg, 'memory.max': mmax, 'swap.max': sw, 'flags': flags,
                 'MaxDirectMemorySize': re.findall(r'-XX:MaxDirectMemorySize=\S+', jvm), 'xmx': re.findall(r'-Xmx\S+', jvm)})
    if mmax != str(int(SCOPE[:-1]) << 30) or sw != '0':
        fail('scope not applied')
    if not flags[f'-Xmx{HEAP}'] or not flags['-XX:+HeapDumpOnOutOfMemoryError']:
        fail('JVM flags differ')
    return cg


def wait_serving(limit=600, user=SU):
    t0 = time.time()
    while time.time() - t0 < limit:
        time.sleep(3)
        if NODE['popen'].poll() is not None and pid_of() is None:
            return False
        if pid_of() and client('probe', user=user, quiet=True, timeout=120):
            return True
    return None


def readback():
    names = ['authenticator', 'authorizer', 'role_manager', 'network_authorizer', 'memtable_allocation_type', 'memtable_heap_space',
             'memtable_offheap_space', 'memtable_cleanup_threshold', 'memtable_flush_writers', 'commitlog_total_space',
             'memtable_flush_period_in_ms', 'num_tokens', 'tables_warn_threshold', 'tables_fail_threshold', 'keyspaces_warn_threshold',
             'keyspaces_fail_threshold', 'native_transport_max_concurrent_connections', 'native_transport_rate_limiting_enabled',
             'maximum_replication_factor_fail_threshold', 'audit_logging_options_enabled']
    got = client('settings', *names, user=SU, quiet=True)
    s = got and got.get('settings') or {}
    ok = s.get('memtable_allocation_type') == 'heap_buffers' and s.get('memtable_heap_space') == '512MiB'
    note('settings', {'values': s, 'ok': ok})
    if not ok:
        fail('settings read-back differs')


def collect():
    for f in ('logs/system.log', 'logs/debug.log', 'stdout.txt'):
        sh(f'cp {RD}/{f} {LOGS}/ 2>/dev/null; true', check=False, quiet=True)
    sh(f'cp {RD}/logs/gc.log* {LOGS}/ 2>/dev/null; true', check=False, quiet=True)
    if SAMP['last_events'] is not None:
        open(LOGS + '/memory.events', 'w').write(SAMP['last_events'] + '\n')


def scan_dump(path, tag):
    rc, out = sh(f'python3 -I {HARNESS}/hprof_scan.py {path}', check=False, timeout=2400, cwd='/')
    js = [l for l in out.splitlines() if l.startswith('{')]
    r = json.loads(js[-1]) if js else {'error': out[-500:]}
    json.dump(r, open(f'{LOGS}/scan-{tag}.json', 'w'))
    note('scan ' + tag, {k: v for k, v in r.items() if k != 'oom_traces'} if isinstance(r, dict) else r)
    return r


def finish(keep_run=True):
    left = daemons()
    note('end', {'daemons_left': left or 'none', 'run_dir_kept': keep_run and os.path.isdir(RD)})
    if not keep_run and pid_of() is None:
        shutil.rmtree(RD, ignore_errors=True)


def wait_death(limit):
    t0 = time.time()
    while time.time() - t0 < limit:
        if pid_of() is None:
            return True
        time.sleep(1)
    return pid_of() is None


def handle_oom(tag):
    wait_death(240)
    mark('daemon_gone')
    time.sleep(30)          # victim keeps measuring after the death
    stop_samplers()
    stop_victim()
    out = readf(RD + '/stdout.txt') or ''
    oom_lines = [l for l in out.splitlines() if 'OutOfMemoryError' in l or 'Dumping heap' in l or 'Heap dump file' in l
                 or 'kill -9' in l or 'Killed' in l]
    dumps = [f for f in os.listdir(RD + '/dump') if f.endswith('.hprof')]
    dinfo = []
    for d in dumps:
        p = f'{RD}/dump/{d}'
        st = sh(f'stat -c "%W %Y %s" {p}', check=False, quiet=True)[1].split()
        sha = sh(f'sha256sum {p} | cut -c1-8', check=False, quiet=True, timeout=600)[1].strip()
        dinfo.append({'file': d, 'birth_s': st[0], 'mtime_s': st[1], 'bytes': st[2], 'sha256_8': sha})
    note('oom ' + tag, {'stdout_lines': oom_lines[-20:], 'dumps': dinfo, 'exit': NODE['popen'].poll()})
    collect()
    for d in dumps:
        scan_dump(f'{RD}/dump/{d}', tag)
        os.remove(f'{RD}/dump/{d}')


def attacker_probes(tag, extra=()):
    qs = ['LIST ALL PERMISSIONS OF attacker', 'SELECT * FROM victim.kv LIMIT 1', "INSERT INTO victim.kv (k, v) VALUES (0, 'a')",
          "CREATE ROLE evil WITH PASSWORD = 'x' AND LOGIN = true", "ALTER TABLE victim.kv WITH comment = 'x'", 'GRANT SELECT ON TABLE victim.kv TO attacker',
          "SELECT name, value FROM system_views.settings WHERE name = 'memtable_heap_space'"] + list(extra)
    r = client('cql', *qs, user=ATK, timeout=600)
    note('attacker probes ' + tag, r)
    open(f'{LOGS}/auth-{tag}.json', 'w').write(json.dumps(r, indent=1))
    return r


def mode_attack(M):
    write_conf()
    unit = launch()
    ok = wait_serving()
    if not ok:
        fail(f'node not serving ({ok})')
    pid = pid_of()
    cg = check_jvm(pid, unit)
    mark('serving')
    readback()
    setup = client('cql',
                   f"CREATE ROLE {VIC[0]} WITH PASSWORD = '{VIC[1]}' AND LOGIN = true",
                   f"CREATE ROLE {ATK[0]} WITH PASSWORD = '{ATK[1]}' AND LOGIN = true",
                   "CREATE KEYSPACE victim WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}",
                   'CREATE TABLE victim.kv (k int PRIMARY KEY, v text)',
                   'GRANT SELECT ON TABLE victim.kv TO victim', 'GRANT MODIFY ON TABLE victim.kv TO victim',
                   'GRANT CREATE ON ALL KEYSPACES TO attacker',
                   'LIST ALL PERMISSIONS OF attacker', 'LIST ALL PERMISSIONS OF victim', 'LIST ROLES', 'DESCRIBE KEYSPACES',
                   user=SU, timeout=600)
    open(f'{LOGS}/auth-setup.json', 'w').write(json.dumps(setup, indent=1))
    note('superuser setup', setup)
    if not setup or not all(x['ok'] for x in setup['results']):
        fail('superuser setup failed')
    attacker_probes('before')
    start_victim()
    start_rss(pid, cg)
    start_jmx_poll()
    time.sleep(30)
    note('victim tail before', sh(f'tail -3 {LOGS}/victim.txt', check=False, quiet=True)[1])
    # ---- attack part 1: DDL on the running node, as the attacker ----
    mark('attack_start')
    mark('ddl_start')
    for a in range(0, M, 500):
        b = min(a + 499, M - 1)
        r = client('schema', a, b, LOGS, user=ATK, timeout=3600)
        note(f'schema {a}-{b}', r)
        if not r or not r.get('created') or pid_of() is None:
            if pid_of() is None:
                note('died during DDL', True)
                handle_oom('ddl')
                finish(keep_run=True)
                return
            fail('schema creation failed')
        if time.time() > DEADLINE - 1800:
            fail('deadline')
    mark('ddl_end')
    note('tablecount', client('tablecount', user=ATK, quiet=True))
    attacker_probes('after-ddl', ['LIST ALL PERMISSIONS OF attacker ON KEYSPACE ks', 'LIST ALL PERMISSIONS OF attacker ON TABLE ks.t2499'])
    time.sleep(10)
    note('L0', hist2(pid, 'after-ddl'))
    time.sleep(10)
    # ---- attack part 2: one 1 KiB row into t1..t(M-1), stage 2's arm T ----
    mark('write_start')
    r = client('spread', 1, M - 1, 100, 8, LOGS, user=ATK, timeout=1200)
    note('client spread', r)
    mark('write_end')
    alive = pid_of() is not None
    if alive and r and r.get('stopped') != 'end':
        log('client stalled with the node alive: wait <= 300 s for an OOM')
        alive = not wait_death(300)
    if not alive:
        handle_oom('oom')
        finish(keep_run=True)
        return
    note('survived', True)
    time.sleep(30)
    note('U_end', hist2(pid, 'end'))
    stop_samplers()
    stop_victim()
    stop_node()
    collect()
    finish(keep_run=True)


def mode_replay(rewrite, M=2500):
    if not os.path.isdir(RD + '/commitlog'):
        fail('no run/ to replay')
    cl = sh(f'ls -la {RD}/commitlog; du -sh {RD}/commitlog; find {RD}/data/ks -name "*-Data.db" | wc -l', check=False, quiet=True)[1]
    note('before replay: commitlog and ks sstables', cl)
    for d in os.listdir(RD + '/logs'):
        shutil.move(f'{RD}/logs/{d}', f'{RD}/logs/{d}.attack') if not d.endswith('.attack') else None
    os.rename(RD + '/stdout.txt', RD + '/stdout.attack.txt') if os.path.exists(RD + '/stdout.txt') else None
    start_victim()          # the victim tries every second; connect errors until the node serves
    unit = launch()
    t0 = time.time()
    pid = None
    while time.time() - t0 < 120 and pid is None:
        pid = pid_of(); time.sleep(0.5)
    if pid is None:
        fail('no daemon after launch')
    cg = check_jvm(pid, unit)
    start_rss(pid, cg)
    # JMX poll once the JMX port listens
    for _ in range(240):
        if re.search(rf':{JMXPORT}\s', sh('ss -ltn', quiet=True)[1]):
            start_jmx_poll(); mark('jmx_up'); break
        if pid_of() is None:
            break
        time.sleep(0.5)
    ok = wait_serving(limit=900)
    rl = sh(f"grep -hE 'Replaying|replayed|Log replay complete|Finished reading|OutOfMemory' {RD}/logs/system.log | head -20", check=False, quiet=True)[1]
    note('replay lines', rl)
    if not ok:
        note('replay outcome', 'node did not come up' + (' (daemon gone)' if pid_of() is None else ''))
        if pid_of() is not None:
            fail('node neither serving nor dead after 900 s')
        handle_oom('replay')
        finish(keep_run=False)
        return
    mark('serving')
    note('replay outcome', 'node came up and serves')
    sst = sh(f'find {RD}/data/ks -name "*-Data.db" | wc -l', check=False, quiet=True)[1].strip()
    note('ks sstables after replay', sst)
    time.sleep(30)
    note('after replay', hist2(pid, 'after-replay'))
    time.sleep(30)
    if rewrite:
        mark('attack_start')
        mark('write_start')
        r = client('spread', 1, M - 1, 100, 8, LOGS, user=ATK, timeout=1200)
        note('client spread (rewrite)', r)
        mark('write_end')
        alive = pid_of() is not None
        if alive and r and r.get('stopped') != 'end':
            alive = not wait_death(300)
        if not alive:
            handle_oom('rewrite')
            finish(keep_run=False)
            return
        note('survived rewrite', True)
        time.sleep(30)
    stop_samplers()
    stop_victim()
    stop_node()
    collect()
    finish(keep_run=False)


try:
    sh(f'mkdir -p {W}/jmxcls && javac -d {W}/jmxcls {HARNESS}/Jmx.java', cwd='/', quiet=True)
    if mode == 'down':
        stop_node()
        note('down', daemons() or 'none')
    elif mode == 'attack':
        mode_attack(int(args[2]))
    else:
        mode_replay(len(args) > 2 and args[2] == 'rewrite')
    note('DONE', True)
except SystemExit:
    raise
except Exception as e:
    fail(f'exception {e!r}')
