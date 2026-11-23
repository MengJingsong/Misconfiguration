#!/usr/bin/env python3
"""U14 stage-2 lifetime driver (design §2.5, frozen sha256 968539d5...), adapted from C6's run.py. One node lifetime per call,
on pc99, everything under /mydata/s4/u14 (data dirs under /dev/shm/u14/run when U14_SHM=1, the §2.5 disk rule).
usage:
  run.py shake <label>                              shakedown S0: create 1..1000 (checkpoints 500, 1000), stop, restart on the
                                                    same data with tables_fail_threshold 1050, create 1001..1100 as u14
  run.py life <label> <T|C|I> <2G|4G> <long|short> <N> [<X>]
                                                    T: create 1..N; C: churn 1..N, W = 500; I: create 1..N with
                                                    tables_fail_threshold X
  run.py down                                       stop this harness's node, if any
Output: /mydata/s4/u14/logs/<label>/ (session.log, summary.json, client.csv, checkpoints.jsonl, hist-*.txt, sampler.csv,
rss.csv, system.log, debug.log, gc.log*, stdout.txt, scan-*.json, yaml.diff, env.diff, jvm-cmdline.txt, limits.txt,
memory.events). Dumps: /mydata/s4/u14/dumps/<label>/."""
import json, os, re, shutil, signal, subprocess, sys, threading, time

W = '/mydata/s4/u14'
C = W + '/cassandra'
RD = W + '/run'
SHM = os.environ.get('U14_SHM') == '1'
DD = '/dev/shm/u14/run' if SHM else RD
HARNESS = os.path.dirname(os.path.abspath(__file__))
ADDR, JMXPORT = '127.0.14.1', 7214
KS = {'long': 'u14' + 'k' * 45, 'short': 'ks'}
G_ON = 'org.apache.cassandra.metrics:type=Table,name=AllMemtablesOnHeapDataSize'
SAMPLER_BEANS = [
    ('java.lang:type=Memory', 'HeapMemoryUsage'),
    ('java.lang:type=MemoryPool,name=G1 Old Gen', 'Usage'),
    ('java.lang:type=MemoryPool,name=G1 Old Gen', 'CollectionUsage'),
    ('java.lang:type=GarbageCollector,name=G1 Young Generation', 'CollectionCount'),
    ('java.lang:type=GarbageCollector,name=G1 Young Generation', 'CollectionTime'),
    ('java.lang:type=GarbageCollector,name=G1 Old Generation', 'CollectionCount'),
    ('java.lang:type=GarbageCollector,name=G1 Old Generation', 'CollectionTime'),
    ('MBEANCOUNT', 'n'),
    (G_ON, 'Value'),
]
SAMPLER_COLS = 'ms,heap_used,old_used,old_coll_used,young_n,young_ms,old_n,old_ms,mbeans,memtables_onheap'
SCOPE = {'2G': '8G', '4G': '10G', '8G': '14G'}
SU = ('cassandra', 'cassandra')
UU = ('u14', 'u14pw')
# stopping budget (design §2.7): DDL seconds cap and wall cap of the workload phase
CAPS = {('T', '2G'): (2400, 3300), ('C', '2G'): (1800, 2400), ('I', '2G'): (1200, 1800), ('T', '4G'): (3000, 3900)}
NO_START_AFTER = (13, 15)   # New York wall clock
# ---- 2026-11-23 owner-approved follow-up (H4-T-2..4; see the case file §3.5) ----
# (1) The service-loss stop ("criterion held 10 min") applies only to T at 2 GiB, as §2.7 lists it; on 2026-11-21 it was
#     applied to every arm and stopped H4-T-1 (deviation). (2) T at 4 GiB: DDL cap 120 min (owner, 2026-11-23), wall cap
#     DDL cap + 15 min as before; M_max 12,000 unchanged. (3) The 13:15 no-start rule was the time plan of 2026-11-21 only.
SL_STOP = {('T', '2G')}
if time.strftime('%F') >= '2026-11-23':
    CAPS[('T', '4G')] = (7200, 8100)
    NO_START_AFTER = None
# a real OutOfMemoryError thrown at runtime: HotSpot's OOM report lines or an uncaught-exception trace. Never the startup
# line "CompileCommand: exclude ...forceHeapSpaceOomMaybe(Ljava/lang/OutOfMemoryError;)V" that every lifetime prints.
OOM_RE = re.compile(r'^(?:Exception in thread .*?)?(?:# )?java\.lang\.OutOfMemoryError(?::|$)')

args = sys.argv[1:]
if not args or args[0] not in ('shake', 'life', 'down'):
    sys.exit(__doc__)
mode = args[0]
label = args[1] if mode in ('shake', 'life') else 'down'
LOGS = f'{W}/logs/{label}'
DUMPS = f'{W}/dumps/{label}'
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
SUM = {'label': label, 'mode': mode, 'args': args, 'shm': SHM}


def log(s):
    line = f'[{time.strftime("%F %T")} {int(time.time()*1000)}] {s}'
    SESSION.write(line + '\n'); SESSION.flush()


def note(k, v):
    SUM[k] = v
    log(f'{k}: {json.dumps(v)}')
    json.dump(SUM, open(LOGS + '/summary.json', 'w'), indent=1)


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


def ny_now():
    out = subprocess.run('TZ=America/New_York date +%H:%M', shell=True, capture_output=True, text=True).stdout.strip()
    h, m = out.split(':')
    return int(h), int(m)


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


def fail(msg):
    note('FAIL', msg)
    stop_samplers()
    stop_node()
    collect()
    finish()
    sys.exit(1)


def cenv():
    return dict(os.environ, CASSANDRA_HOME=C, U14_JMXCLS=W + '/jmxcls', U14_JMXPORT=str(JMXPORT))


def client(user, *a, timeout=3600, quiet=False):
    rc, out = sh(f'python3 -I {HARNESS}/client.py {ADDR} {user[0]} {user[1]} ' + ' '.join(f"'{x}'" for x in a), timeout=timeout,
                 check=False, env=cenv(), quiet=quiet)
    js = [l for l in out.splitlines() if l.startswith('{')]
    return json.loads(js[-1]) if js else None


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


# ---------------- samplers ----------------
SAMP = {'proc': None, 'stop': threading.Event(), 'thread': None, 'last_events': None}


def start_samplers(pid, cg):
    SAMP['stop'] = threading.Event()
    stopf = f'{RD}/sampler.stop'
    try:
        os.remove(stopf)
    except OSError:
        pass
    cmd = (f"java -cp {W}/jmxcls Jmx {JMXPORT} poll 1000 1000000 {stopf} " + ' '.join(f"'{b}' {a}" for b, a in SAMPLER_BEANS))
    newf = not os.path.exists(LOGS + '/sampler.csv')
    f = open(LOGS + '/sampler.csv', 'a')
    if newf:
        f.write(SAMPLER_COLS + '\n'); f.flush()
    SAMP['proc'] = subprocess.Popen(cmd, shell=True, stdout=f, stderr=open(LOGS + '/sampler.err', 'a'), cwd='/')

    def rssloop():
        newr = not os.path.exists(LOGS + '/rss.csv')
        rf = open(LOGS + '/rss.csv', 'a')
        if newr:
            rf.write('ms,rss_anon_kb,shmem_kb,cg_current,cg_oom_kill,cg_oom\n')
        while not SAMP['stop'].is_set():
            st = readf(f'/proc/{pid}/status')
            if st is None:
                rf.write(f'{int(time.time()*1000)},gone,,,,\n'); rf.flush()
                break
            m = re.search(r'RssAnon:\s+(\d+)', st)
            sm = re.search(r'Shmem:\s+(\d+)', readf('/proc/meminfo') or '')
            ev = readf(cg + '/memory.events') or ''
            SAMP['last_events'] = ev
            ok = re.search(r'oom_kill (\d+)', ev); oo = re.search(r'^oom (\d+)', ev, re.M)
            rf.write(f"{int(time.time()*1000)},{m.group(1) if m else ''},{sm.group(1) if sm else ''},{readf(cg + '/memory.current')},"
                     f"{ok.group(1) if ok else ''},{oo.group(1) if oo else ''}\n")
            rf.flush()
            SAMP['stop'].wait(1)
        rf.close()

    SAMP['thread'] = threading.Thread(target=rssloop, daemon=True)
    SAMP['thread'].start()


def stop_samplers():
    try:
        open(f'{RD}/sampler.stop', 'w').close()
    except OSError:
        pass
    SAMP['stop'].set()
    p = SAMP['proc']
    if p is not None:
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()
        SAMP['proc'] = None
    if SAMP['thread'] is not None:
        SAMP['thread'].join(timeout=5)
        SAMP['thread'] = None


# ---------------- node ----------------
def write_conf(extra, fresh=True):
    if fresh:
        for p in (RD, '/dev/shm/u14'):
            if os.path.exists(p):
                shutil.rmtree(p)
        os.makedirs(RD + '/logs')
        for d in ('data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw'):
            os.makedirs(f'{DD}/{d}')
    shutil.rmtree(RD + '/conf', ignore_errors=True)
    shutil.copytree(C + '/conf', RD + '/conf')
    os.makedirs(DUMPS, exist_ok=True)
    env_sh = open(RD + '/conf/cassandra-env.sh').read()
    if 'JMX_PORT="7199"' not in env_sh:
        fail('JMX_PORT line not found in cassandra-env.sh')
    open(RD + '/conf/cassandra-env.sh', 'w').write(env_sh.replace('JMX_PORT="7199"', f'JMX_PORT="{JMXPORT}"', 1))
    lines = ['cluster_name: u14', f'listen_address: {ADDR}', f'rpc_address: {ADDR}',
             'seed_provider:', '  - class_name: org.apache.cassandra.locator.SimpleSeedProvider', '    parameters:', f'      - seeds: "{ADDR}:7000"',
             'data_file_directories:', f'    - {DD}/data', f'commitlog_directory: {DD}/commitlog', f'hints_directory: {DD}/hints',
             f'saved_caches_directory: {DD}/saved_caches', f'cdc_raw_directory: {DD}/cdc_raw',
             'authenticator: PasswordAuthenticator'] + extra
    keys = {l.split(':', 1)[0] for l in lines if re.match(r'^[A-Za-z_]+:', l)}
    out, skip = [], False
    for l in open(RD + '/conf/cassandra.yaml').read().splitlines():
        m = re.match(r'^([A-Za-z_]+):', l)
        if m:
            skip = m.group(1) in keys
            if skip:
                continue
        elif skip and (l.startswith((' ', '\t', '-')) or l.strip() == '' or l.lstrip().startswith('#')):
            continue
        else:
            skip = False
        out.append(l)
    open(RD + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- u14 lines ----\n' + '\n'.join(lines) + '\n')
    sh(f'diff {C}/conf/cassandra.yaml {RD}/conf/cassandra.yaml > {LOGS}/yaml.diff; true', check=False, quiet=True)
    sh(f'diff {C}/conf/cassandra-env.sh {RD}/conf/cassandra-env.sh > {LOGS}/env.diff; true', check=False, quiet=True)


NODE = {'popen': None}


def start(heap, extra, fresh=True):
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
    write_conf(extra, fresh)
    env = dict(os.environ, CASSANDRA_CONF=RD + '/conf', CASSANDRA_LOG_DIR=RD + '/logs', CASSANDRA_HEAPDUMP_DIR=DUMPS,
               MAX_HEAP_SIZE=heap, XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}')
    for k in ('HEAP_NEWSIZE', 'JVM_EXTRA_OPTS', 'JVM_OPTS'):
        env.pop(k, None)
    scope = SCOPE[heap]
    unit = f'u14-{label.lower()}-{int(time.time())}'
    cmd = (f"systemd-run --user --scope --unit={unit} -p MemoryMax={scope} -p MemorySwapMax=0 "
           f"bash -c 'ulimit -n 100000 && exec bin/cassandra -f -p {RD}/cassandra.pid' >> {RD}/stdout.txt 2>&1")
    log('+ ' + cmd)
    NODE['popen'] = subprocess.Popen(cmd, shell=True, cwd=C, env=env)
    t0 = time.time()
    while time.time() - t0 < 600:
        time.sleep(3)
        if NODE['popen'].poll() is not None:
            fail(f'node died during start (exit {NODE["popen"].returncode})')
        if pid_of() and client(SU, 'probe', quiet=True, timeout=120):
            break
    else:
        fail('node not serving (or no superuser login) after 600 s')
    pid = pid_of()
    cg = cgroup_path(pid)
    want_max = str(int(scope[:-1]) << 30)
    mmax, sw = readf(cg + '/memory.max'), readf(cg + '/memory.swap.max')
    jvm = open(f'/proc/{pid}/cmdline').read().replace('\0', ' ')
    open(LOGS + '/jvm-cmdline.txt', 'a').write(jvm + '\n')
    sh(f'cat /proc/{pid}/limits >> {LOGS}/limits.txt', check=False, quiet=True)
    flags = {f: (f in jvm) for f in ('-XX:+UseG1GC', '-XX:G1HeapRegionSize=16m', '-XX:+AlwaysPreTouch', '-XX:+HeapDumpOnOutOfMemoryError',
                                     '-XX:OnOutOfMemoryError=kill -9 %p', f'-Xmx{heap}')}
    mdm = re.findall(r'-XX:MaxDirectMemorySize=\S+', jvm)
    note('start', {'pid': pid, 'up_s': round(time.time() - t0), 'unit': unit, 'cgroup': cg, 'memory.max': mmax, 'swap.max': sw,
                   'scope_ok': mmax == want_max and sw == '0', 'flags': flags, 'flags_ok': all(flags.values()),
                   'MaxDirectMemorySize': mdm, 'xmx': re.findall(r'-Xmx\S+', jvm), 'xms': re.findall(r'-Xms\S+', jvm),
                   'heapdump': re.findall(r'-XX:HeapDumpPath=\S+', jvm)})
    if mmax != want_max or sw != '0':
        fail('scope not applied')
    if not all(flags.values()):
        fail('JVM flags differ')
    return pid, cg


SETTINGS = ['authenticator', 'authorizer', 'role_manager', 'tables_warn_threshold', 'tables_fail_threshold', 'keyspaces_fail_threshold',
            'memtable_allocation_type', 'memtable_heap_space', 'key_cache_size', 'counter_cache_size', 'prepared_statements_cache_size',
            'auto_snapshot', 'num_tokens', 'columns_per_table_fail_threshold']


def readback(heap, X):
    got = client(SU, 'settings', *SETTINGS, quiet=True)
    s = got and got.get('settings') or {}
    quarter = {'2G': '512MiB', '4G': '1024MiB', '8G': '2048MiB'}[heap]
    tft = s.get('tables_fail_threshold')
    tft_ok = (str(tft) == str(X)) if X is not None else (tft in (None, '-1', 'null'))
    ok = (s.get('memtable_allocation_type') == 'heap_buffers' and s.get('memtable_heap_space') == quarter and tft_ok
          and 'PasswordAuthenticator' in str(s.get('authenticator')) and 'AllowAllAuthorizer' in str(s.get('authorizer')))
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
    rc, out = sh(f'java -Xmx2g -cp {W}/jmxcls HprofScan {path}', check=False, timeout=3600, cwd='/')
    js = [l for l in out.splitlines() if l.startswith('{')]
    r = json.loads(js[-1]) if js else {'error': out[-500:]}
    json.dump(r, open(f'{LOGS}/scan-{tag}.json', 'w'))
    note('scan ' + tag, {k: v for k, v in r.items() if k not in ('top40', 'traces')})
    return r


def finish():
    left = daemons()
    note('end', {'daemons_left': left or 'none'})
    if pid_of() is None:
        shutil.rmtree(RD, ignore_errors=True)
        shutil.rmtree('/dev/shm/u14', ignore_errors=True)


def wait_death(limit):
    t0 = time.time()
    while time.time() - t0 < limit:
        if pid_of() is None:
            return True
        time.sleep(1)
    return pid_of() is None


def checkpoint(ks, pid, tag):
    r = client(SU, 'checkpoint', ks, LOGS, pid, tag, quiet=True, timeout=1500)
    note('checkpoint ' + tag, r and r.get('cp'))
    return r and r.get('cp')


def gc_fraction(window_s):
    """fraction of wall time in young+old collections over the last window_s seconds of sampler.csv (None if too few rows)"""
    try:
        rows = [l.strip().split(',') for l in open(LOGS + '/sampler.csv') if l[0].isdigit()]
    except OSError:
        return None
    rows = [r for r in rows if len(r) >= 8 and r[5].isdigit() and r[7].isdigit()]
    if len(rows) < 2:
        return None
    last = rows[-1]
    t_end = int(last[0])
    first = None
    for r in rows:
        if int(r[0]) >= t_end - window_s * 1000:
            first = r
            break
    if first is None or t_end - int(first[0]) < window_s * 1000 * 0.9:
        return None
    gc = (int(last[5]) + int(last[7])) - (int(first[5]) + int(first[7]))
    return gc / (t_end - int(first[0]))


def workload(ks, names, first, last, pid, ddl_cap, wall_cap, W_=None, sl_stop=True):
    """runs the client as u14 under a monitor: node death, wall cap, service-loss criterion held 10 min (only if sl_stop).
    2026-11-23: the client is started without a shell, in its own session, and a monitor stop kills its whole process group
    (on 2026-11-21 p.kill() hit only the 'sh -c' wrapper and the client kept a CREATE in flight)."""
    argv = ['python3', '-I', f'{HARNESS}/client.py', ADDR, UU[0], UU[1], 'create', ks, names, str(first), str(last), LOGS,
            str(pid), str(ddl_cap)] + ([str(W_)] if W_ is not None else [])
    log('+ ' + ' '.join(argv) + f'  (service-loss stop: {sl_stop})')
    outf = open(f'{LOGS}/client.out', 'a')
    p = subprocess.Popen(argv, stdout=outf, stderr=outf, env=cenv(), cwd='/', start_new_session=True)
    t0 = time.time()
    why = None
    while p.poll() is None:
        time.sleep(5)
        if time.time() - t0 > wall_cap:
            why = 'wall_cap'
            break
        f = gc_fraction(600) if sl_stop else None
        if f is not None and f >= 0.9:
            why = f'service_loss_10min ({f:.3f})'
            break
    if why:
        log(f'monitor stop: {why}; killing client process group {p.pid}')
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        p.wait()
        note('client_killed', {'pid': p.pid, 'alive_after': os.path.exists(f'/proc/{p.pid}')})
    outf.close()
    lines = [l for l in open(f'{LOGS}/client.out') if l.startswith('{"cmd"')]
    r = json.loads(lines[-1]) if lines else {'stopped': why or 'client_no_output'}
    if why:
        r['monitor_stop'] = why
    note(f'client {first}-{last}', r)
    return r


def oom_path(t_client_end):
    """the node died: wait for the dump, collect, scan (keep the dump file for the caller's decision)"""
    wait_death(240)
    stop_samplers()
    out = readf(RD + '/stdout.txt') or ''
    oom_lines = [l for l in out.splitlines() if (OOM_RE.search(l) or 'Dumping heap' in l or 'Heap dump file' in l
                 or 'Executing /bin/sh -c "kill -9' in l or 'Killed' in l) and 'CompileCommand' not in l]
    dumps = [f for f in os.listdir(DUMPS) if f.endswith('.hprof')] if os.path.isdir(DUMPS) else []
    dinfo = []
    for d in dumps:
        p = f'{DUMPS}/{d}'
        st = sh(f'stat -c "%W %Y %s" {p}', check=False, quiet=True)[1].split()
        dinfo.append({'file': d, 'birth_s': st[0], 'mtime_s': st[1], 'bytes': st[2]})
    real = [l for l in out.splitlines() if OOM_RE.search(l) and 'CompileCommand' not in l]
    note('oom', {'stdout_lines': oom_lines[:20], 'real_oom': bool(real), 'first_real_oom': real[0] if real else None,
                 'dumps': dinfo, 'exit': NODE['popen'].poll() if NODE['popen'] else None})
    collect()
    for d in dumps:
        scan_dump(f'{DUMPS}/{d}', 'oom')
    return dumps


# ---------------- modes ----------------
def setup_user(ks, pid):
    r = client(SU, 'setup', ks, quiet=True, timeout=300)
    note('setup', r)
    if not r or 'roles' not in r:
        fail('role/keyspace setup failed')
    u = [x for x in r['roles'] if x[0] == 'u14']
    if not u or u[0][1]:
        fail('u14 missing or a superuser')


def lifetime_begin(heap, X, names):
    h, m = ny_now()
    if NO_START_AFTER is not None and (h, m) > NO_START_AFTER:
        note('not_started', f'{h:02d}:{m:02d} New York is after 13:15')
        sys.exit(2)
    extra = [f'tables_fail_threshold: {X}'] if X is not None else []
    pid, cg = start(heap, extra)
    readback(heap, X)
    ks = KS[names]
    setup_user(ks, pid)
    return pid, cg, ks


def mode_life(arm, heap, names, N, X):
    pid, cg, ks = lifetime_begin(heap, X if arm == 'I' else None, names)
    start_samplers(pid, cg)
    time.sleep(10)
    checkpoint(ks, pid, 's0')
    time.sleep(10)
    ddl_cap, wall_cap = CAPS.get((arm, heap), (1800, 2400))
    r = workload(ks, names, 1, N, pid, ddl_cap, wall_cap, 500 if arm == 'C' else None, sl_stop=(arm, heap) in SL_STOP)
    alive = pid_of() is not None
    if alive and arm == 'T' and r.get('stopped') != 'end' and r.get('stopped') != 'ddl_cap' and not r.get('monitor_stop'):
        log('client stopped with the node alive: wait <= 300 s for an OOM')
        alive = not wait_death(300)
    if not alive:
        oom_path(time.time())
        finish()
        return
    # surviving lifetime
    so = readf(RD + '/stdout.txt') or ''
    note('real_oom_in_stdout', [l for l in so.splitlines() if OOM_RE.search(l) and 'CompileCommand' not in l][:5])
    nc = client(SU, 'namecheck', ks, quiet=True)
    note('namecheck', nc)
    time.sleep(10)
    note('U_end', checkpoint(ks, pid, 'end'))
    if label.endswith('-1'):
        rc, _ = sh(f'jcmd {pid} GC.heap_dump {DUMPS}/end.hprof', check=False, timeout=900)
        stop_samplers()
        stop_node()
        collect()
        scan_dump(f'{DUMPS}/end.hprof', 'end')
        try:
            os.remove(f'{DUMPS}/end.hprof')
        except OSError:
            pass
    else:
        stop_samplers()
        stop_node()
        collect()
    finish()


def mode_shake():
    pid, cg, ks = lifetime_begin('2G', None, 'long')
    start_samplers(pid, cg)
    time.sleep(10)
    checkpoint(ks, pid, 's0')
    r = workload(ks, 'long', 1, 1000, pid, 1800, 2400)
    nc = client(SU, 'namecheck', ks, quiet=True)
    note('namecheck', nc)
    stop_samplers()
    stop_node()
    collect()
    shutil.copy(LOGS + '/system.log', LOGS + '/system-part1.log')
    # part 2: same data, tables_fail_threshold 1050
    pid, cg = start('2G', ['tables_fail_threshold: 1050'], fresh=False)
    readback('2G', 1050)
    start_samplers(pid, cg)
    r2 = workload(ks, 'long', 1001, 1100, pid, 600, 900)
    note('intervention_path_check', {'ok': r2.get('ok'), 'rejected': r2.get('rejected'), 'pass': r2.get('ok') == 50 and r2.get('rejected') == 50})
    tc = client(SU, 'tablecount', ks, quiet=True)
    note('tablecount_end', tc)
    stop_samplers()
    stop_node()
    collect()
    finish()


try:
    if mode == 'down':
        stop_node()
        note('down', daemons() or 'none')
    elif mode == 'shake':
        mode_shake()
    else:
        mode_life(args[2], args[3], args[4], int(args[5]), int(args[6]) if len(args) > 6 else None)
    note('DONE', True)
except SystemExit:
    raise
except Exception as e:
    fail(f'exception {e!r}')
