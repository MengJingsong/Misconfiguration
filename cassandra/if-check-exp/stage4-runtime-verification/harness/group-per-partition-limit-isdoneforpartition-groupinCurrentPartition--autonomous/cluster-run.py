#!/usr/bin/env python3
"""Cluster tier driver (B3 as amended 2026-10-27). Usage:
  cluster-run.py <tree> <nodedir> <outdir> load            create ks.t (10 partitions x 200000 rows x 100 B), flush, wait for compactions, known-answer check
  cluster-run.py <tree> <nodedir> <outdir> run [plan]      one node lifetime: warm-up, forward sweep N=1,100,10000,absent at P=1000 (10 reps x 10 partitions),
        unrelated point reads (noise), page-size control (P=300000, N absent), reverse sweep, exploratory P=300000 with N=1,100,10000
Own ports (tag g73, slot 3): 127.0.3.1, storage 7000, ssl 7001, native 9042, JMX 7130. Stops the node on any exit.
First-trigger check: the first arm (N=1) must return exactly 1 group per query (query.py exits 1 otherwise); a failure stops the run (exit 3).
Env STAGE4_ROWS_PER_PK (default 200000) and STAGE4_REPS (default 10) shrink the run for shakedowns only."""
import sys, os, subprocess, time, json, shutil, signal, resource, re, threading, atexit

tree, node, out, mode = sys.argv[1:5]
HARN = os.path.dirname(os.path.abspath(__file__))
DRIVER = os.path.expanduser('~/s4-b11-g73-drv')
ADDR, STORAGE, SSL, NATIVE, JMX = '127.0.3.1', 7000, 7001, 9042, 7130
ROWS = int(os.environ.get('STAGE4_ROWS_PER_PK', 200000)); REPS = int(os.environ.get('STAGE4_REPS', 10)); NPROC = 5
os.environ['STAGE4_ROWS_PER_PK'] = str(ROWS)
resource.setrlimit(resource.RLIMIT_NOFILE, (100000, 100000))
os.makedirs(out, exist_ok=True)
LOG = open(os.path.join(out, 'session.log'), 'a')
def log(*a):
    m = '[%s] %s' % (time.strftime('%FT%T%z'), ' '.join(str(x) for x in a)); print(m, flush=True); LOG.write(m + '\n'); LOG.flush()
def sh(cmd, check=True, timeout=None, quiet=False):
    log('+', cmd if isinstance(cmd, str) else ' '.join(cmd)); t0 = time.time()
    p = subprocess.run(cmd, shell=isinstance(cmd, str), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    if not quiet: log(p.stdout.strip()[-2500:])
    log('  exit', p.returncode, 'in %.1fs' % (time.time() - t0))
    if check and p.returncode: raise RuntimeError('command failed: %s' % cmd)
    return p.stdout
NT = [os.path.join(tree, 'bin/nodetool'), '-p', str(JMX)]
PIDF = os.path.join(node, 'cassandra.pid')
def daemons():
    return subprocess.run("ps -eo pid,args | grep '[j]ava.*%s.*CassandraDaemon' | awk '{print $1}'" % tree, shell=True, stdout=subprocess.PIPE, text=True).stdout.split()
def node_pid():
    try: pid = int(open(PIDF).read().strip()); os.kill(pid, 0); return pid
    except Exception: return None
def stop_node():
    pid = node_pid()
    if pid:
        try:
            log('stopping node: nodetool drain'); subprocess.run(NT + ['drain'], timeout=240, stdout=LOG, stderr=LOG, stdin=subprocess.DEVNULL)
        except Exception as e: log('drain failed', e)
        try:
            os.kill(pid, signal.SIGTERM)
            for _ in range(90):
                try: os.kill(pid, 0); time.sleep(1)
                except OSError: break
            else: os.kill(pid, signal.SIGKILL)
        except OSError: pass
    log('daemons left:', daemons())
atexit.register(stop_node)

def make_conf(label):
    conf = node + '/conf'
    shutil.rmtree(conf, ignore_errors=True); shutil.copytree(tree + '/conf', conf)
    lines = {
        'cluster_name': "'g73'", 'num_tokens': '1',
        'data_file_directories': '\n    - %s/data' % node,
        'commitlog_directory': node + '/commitlog', 'hints_directory': node + '/hints', 'saved_caches_directory': node + '/saved_caches', 'cdc_raw_directory': node + '/cdc_raw',
        'listen_address': ADDR, 'rpc_address': ADDR,
        'seed_provider': '\n  - class_name: org.apache.cassandra.locator.SimpleSeedProvider\n    parameters:\n      - seeds: "%s:%d"' % (ADDR, STORAGE),
        'storage_port': str(STORAGE), 'ssl_storage_port': str(SSL), 'native_transport_port': str(NATIVE),
        'read_request_timeout': '120s', 'range_request_timeout': '120s', 'native_transport_timeout': '120s',
        'auto_snapshot': 'false', 'cdc_enabled': 'false', 'concurrent_compactors': '2',
    }
    outl, skip = [], False
    for l in open(tree + '/conf/cassandra.yaml').read().splitlines():
        m = re.match(r'^([A-Za-z_]+):', l)
        if m:
            skip = m.group(1) in lines
            if skip: continue
        elif skip and (l.startswith((' ', '\t', '-')) or l.strip() == ''): continue
        else: skip = False
        outl.append(l)
    outl.append('# ---- stage4 g73 (B3a as amended) ----'); outl += ['%s: %s' % (k, v) for k, v in lines.items()]
    open(conf + '/cassandra.yaml', 'w').write('\n'.join(outl) + '\n')
    shutil.copy(conf + '/cassandra.yaml', os.path.join(out, 'cassandra.yaml.%s' % label))
    env = open(conf + '/cassandra-env.sh').read(); assert env.count('JMX_PORT="7199"') == 1
    open(conf + '/cassandra-env.sh', 'w').write(env.replace('JMX_PORT="7199"', 'JMX_PORT="%d"' % JMX))
    with open(conf + '/jvm11-server.options', 'a') as f: f.write('\n# stage4 g73\n-XX:+AlwaysPreTouch\n-XX:G1HeapRegionSize=4m\n-XX:G1NewSizePercent=1\n-XX:G1MaxNewSizePercent=2\n')

def start_node(label):
    if node_pid() or daemons(): raise RuntimeError('a daemon of this tree is running: %s' % daemons())
    for p in (STORAGE, SSL, NATIVE):
        if subprocess.run("ss -ltn | grep -q '%s:%d '" % (ADDR, p), shell=True).returncode == 0: raise SystemExit('port %s:%d busy' % (ADDR, p))
    if subprocess.run("ss -ltn | grep -q ':%d '" % JMX, shell=True).returncode == 0: raise SystemExit('JMX port %d busy' % JMX)
    env = dict(os.environ, MAX_HEAP_SIZE='1G', CASSANDRA_CONF=node + '/conf', CASSANDRA_LOG_DIR=node + '/logs')
    log('+ bin/cassandra -p', PIDF, '(ulimit -n %d, heap 1G)' % resource.getrlimit(resource.RLIMIT_NOFILE)[0])
    subprocess.run([os.path.join(tree, 'bin/cassandra'), '-p', PIDF], env=env, stdout=open(node + '/logs/stdout-%s.log' % label, 'w'), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=120)
    t0 = time.time()
    while time.time() - t0 < 400:
        time.sleep(4)
        if not node_pid() and time.time() - t0 > 12: raise RuntimeError('daemon died during start')
        st = subprocess.run(NT + ['status'], stdout=subprocess.PIPE, text=True, stderr=subprocess.DEVNULL).stdout
        sb = subprocess.run(NT + ['statusbinary'], stdout=subprocess.PIPE, text=True, stderr=subprocess.DEVNULL).stdout.strip()
        if re.search(r'^UN\s+' + re.escape(ADDR), st, re.M) and sb == 'running':
            log('node up (%s) after %.0f s, pid %s' % (label, time.time() - t0, node_pid())); return node_pid()
    raise RuntimeError('node did not come up')

sys.path.insert(0, DRIVER)
def cql(stmt, timeout=600):
    from cassandra.cluster import Cluster
    from cassandra.policies import DCAwareRoundRobinPolicy
    c = Cluster([ADDR], port=NATIVE, protocol_version=4, load_balancing_policy=DCAwareRoundRobinPolicy(local_dc='datacenter1'), token_metadata_enabled=False)
    s = c.connect()
    try:
        r = s.execute(stmt, timeout=timeout); return list(r) if r else []
    finally: c.shutdown()
def client(*args, timeout=7200):
    p = subprocess.run([sys.executable, os.path.join(HARN, 'query.py'), DRIVER, ADDR, str(NATIVE)] + [str(a) for a in args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL, timeout=timeout)
    log(p.stdout.strip()[-400:]); return p.returncode
def du():
    return int(subprocess.run(['du', '-sb', node + '/data'], stdout=subprocess.PIPE, text=True).stdout.split()[0])

shutil.copytree(HARN, os.path.join(out, 'tools_src'), dirs_exist_ok=True)
os.makedirs(os.path.join(out, 'tools'), exist_ok=True); sh(['javac', '-d', os.path.join(out, 'tools'), HARN + '/Jmx.java'])
log('cluster-run start mode=%s tree=%s head=%s rows/pk=%d reps=%d' % (mode, tree, subprocess.run(['git', '-C', tree, 'rev-parse', '--short', 'HEAD'], stdout=subprocess.PIPE, text=True).stdout.strip(), ROWS, REPS))
log('df:', subprocess.run(['df', '-T', node if os.path.exists(node) else os.path.dirname(node)], stdout=subprocess.PIPE, text=True).stdout.splitlines()[-1])

if mode == 'load':
    shutil.rmtree(node, ignore_errors=True)
    for d in ('data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw', 'logs'): os.makedirs(os.path.join(node, d))
    make_conf('load'); start_node('load')
    cql("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    cql("CREATE TABLE IF NOT EXISTS ks.t (k int, ck int, v blob, PRIMARY KEY (k, ck)) WITH compression = {'enabled':'false'}")
    t0 = time.time(); ps = []
    for i in range(NPROC):   # two partitions per client process
        ps.append(subprocess.Popen([sys.executable, os.path.join(HARN, 'query.py'), DRIVER, ADDR, str(NATIVE), 'load', str(2 * i), '2', str(ROWS)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL))
    for p in ps:
        o = p.communicate(timeout=7200)[0]; log(o.strip()[-200:]); assert p.returncode == 0, 'load client failed'
    log('load took %.1fs' % (time.time() - t0)); sh(NT + ['flush', 'ks', 't'])
    for _ in range(90):
        cs = sh(NT + ['compactionstats'], check=False, quiet=True)
        if re.search(r'pending tasks\s+0\b', cs): break
        time.sleep(10)
    log(sh(NT + ['tablestats', 'ks.t'], check=False, quiet=True)[-1500:])
    n = cql("SELECT count(*) FROM ks.t WHERE k = 7", timeout=600)[0][0]; log('rows in ks.t k=7:', n); assert n == ROWS
    log('data bytes after load:', du()); sys.exit(0)

if mode == 'run':
    od = os.path.join(out, 'arms'); os.makedirs(od, exist_ok=True); marker = os.path.join(od, 'markers.txt')
    syslog = node + '/logs/system.log'; off = os.path.getsize(syslog) if os.path.exists(syslog) else 0
    make_conf('run'); start_node('run'); pid = node_pid()
    jp = subprocess.Popen(['java', '-cp', os.path.join(out, 'tools'), 'Jmx', str(JMX), 'poll', '100', os.path.join(od, 'samples.csv')], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ev = open(os.path.join(od, 'arms.txt'), 'a')
    def mark(kind, label, extra=''):
        ev.write('%d %s %s %s\n' % (int(time.time() * 1000), kind, label, extra)); ev.flush()
    rc = 0
    # label, fetch size P, N, kind
    PLAN = [('warmup', 1000, 'absent', 1)]
    fwd = [('f_N1_P1000', 1000, '1'), ('f_N100_P1000', 1000, '100'), ('f_N10000_P1000', 1000, '10000'), ('f_Nabs_P1000', 1000, 'absent')]
    rev = [('r_Nabs_P1000', 1000, 'absent'), ('r_N10000_P1000', 1000, '10000'), ('r_N100_P1000', 1000, '100'), ('r_N1_P1000', 1000, '1')]
    ctl = [('c_Nabs_P300000', 300000, 'absent')]
    expl = [('x_N1_P300000', 300000, '1'), ('x_N100_P300000', 300000, '100'), ('x_N10000_P300000', 300000, '10000')]
    try:
        time.sleep(15)
        mark('DISK', 'start', du())
        for nm, cmd in (('heapinfo-start.txt', 'GC.heap_info'), ('vmflags.txt', 'VM.flags')):
            open(os.path.join(od, nm), 'w').write(sh(['jcmd', str(pid), cmd], check=False, quiet=True))
        sh(['jcmd', str(pid), 'GC.run'], check=False, quiet=True); time.sleep(3)
        # warm-up: one full pass, N absent, P=1000, discarded
        mark('START', 'warmup'); r = client('group', 1000, 'absent', 1, marker, 'warmup'); mark('END', 'warmup')
        if r: raise SystemExit(3)
        def arm(label, fs, N, reps=None):
            reps = reps or REPS
            sh(['jcmd', str(pid), 'GC.run'], check=False, quiet=True); time.sleep(4)
            mark('START', label, '%d %s' % (fs, N)); t0 = time.time()
            r = client('group', fs, N, reps, marker, label); mark('END', label, '%d %s' % (fs, N))
            log('ARM', label, 'P', fs, 'N', N, 'took %.1fs' % (time.time() - t0), 'rc', r)
            if r: raise SystemExit(3)   # first-trigger / row-count check failed
        for a in fwd: arm(*a)
        sh(['jcmd', str(pid), 'GC.run'], check=False, quiet=True); time.sleep(4)
        mark('START', 'noise'); client('point', REPS, marker, 'noise'); mark('END', 'noise')
        for a in ctl: arm(*a)
        for a in rev: arm(*a)
        for a in expl: arm(*a)
        mark('DISK', 'end', du())
        sh(NT + ['tablestats', 'ks.t'], check=False, quiet=True)
    except SystemExit as e:
        rc = e.code if isinstance(e.code, int) else 3
    finally:
        time.sleep(2); jp.terminate()
        with open(syslog, errors='replace') as f: f.seek(off); seg = f.read()
        open(os.path.join(od, 'system.log.segment'), 'w').write(seg)
        errs = [l for l in seg.splitlines() if l.startswith('ERROR')]; log('ERROR lines in segment:', len(errs), errs[:3])
        gcl = [l for l in seg.splitlines() if 'GCInspector' in l]; open(os.path.join(od, 'gcinspector.txt'), 'w').write('\n'.join(gcl) + '\n')
        stop_node()
    sys.exit(rc)
