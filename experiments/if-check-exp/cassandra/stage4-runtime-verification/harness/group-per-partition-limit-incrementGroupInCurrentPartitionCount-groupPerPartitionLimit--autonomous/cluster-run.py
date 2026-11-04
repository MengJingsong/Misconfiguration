#!/usr/bin/env python3
"""Cluster tier driver (B3 as amended 2026-10-27). Usage:
  cluster-run.py <tree> <nodedir> <outdir> load            create ks.t (20 partitions x 200000 rows x 100 B, 2000 ck1 values x 100 ck2), flush, wait for compactions, known-answer check
  cluster-run.py <tree> <nodedir> <outdir> run             one node lifetime: warm-up, forward sweep of 16 arms (shape A/B x fetch size x PER PARTITION LIMIT), noise arm, reverse sweep of the F=5000 arms
Own ports (tag g80, slot 10): 127.0.10.1, storage 7000, ssl 7001, native 9042, JMX 7200. Stops the node on any exit.
First-trigger check: the first arm (shape A, L=1, F=5000) must return exactly 20 groups per query (query.py exits 1 otherwise); a failure stops the run (exit 3).
Env STAGE4_ROWS_PER_PK (default 200000; multiple of 100) and STAGE4_REPS (default 3) shrink the run for shakedowns only."""
import sys, os, subprocess, time, json, shutil, signal, resource, re, threading, atexit

tree, node, out, mode = sys.argv[1:5]
HARN = os.path.dirname(os.path.abspath(__file__))
DRIVER = os.path.expanduser('~/s4-b11-g80-drv/cassandra-driver-3.29.0')
ADDR, STORAGE, SSL, NATIVE, JMX = '127.0.10.1', 7000, 7001, 9042, 7200
ROWS = int(os.environ.get('STAGE4_ROWS_PER_PK', 200000)); REPS = int(os.environ.get('STAGE4_REPS', 3)); NPROC = 10; PARTS = 20
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
        'cluster_name': "'g80'", 'num_tokens': '1',
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
    outl.append('# ---- stage4 g80 (B3a as amended) ----'); outl += ['%s: %s' % (k, v) for k, v in lines.items()]
    open(conf + '/cassandra.yaml', 'w').write('\n'.join(outl) + '\n')
    shutil.copy(conf + '/cassandra.yaml', os.path.join(out, 'cassandra.yaml.%s' % label))
    env = open(conf + '/cassandra-env.sh').read(); assert env.count('JMX_PORT="7199"') == 1
    open(conf + '/cassandra-env.sh', 'w').write(env.replace('JMX_PORT="7199"', 'JMX_PORT="%d"' % JMX))
    with open(conf + '/jvm11-server.options', 'a') as f: f.write('\n# stage4 g80\n-XX:+AlwaysPreTouch\n-XX:G1HeapRegionSize=4m\n-XX:G1NewSizePercent=1\n-XX:G1MaxNewSizePercent=2\n')

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


def rchar():
    for l in open('/proc/%d/io' % node_pid()):
        if l.startswith('rchar:'): return int(l.split()[1])

if mode == 'load':
    shutil.rmtree(node, ignore_errors=True)
    for d in ('data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw', 'logs'): os.makedirs(os.path.join(node, d))
    make_conf('load'); start_node('load')
    cql("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    cql("CREATE TABLE IF NOT EXISTS ks.t (pk int, ck1 int, ck2 int, v blob, PRIMARY KEY (pk, ck1, ck2)) WITH compression = {'enabled':'false'}")
    t0 = time.time(); ps = []
    per = PARTS // NPROC
    for i in range(NPROC):
        ps.append(subprocess.Popen([sys.executable, os.path.join(HARN, 'query.py'), DRIVER, ADDR, str(NATIVE), 'load', str(per * i), str(per), str(ROWS)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL))
    for p in ps:
        o = p.communicate(timeout=7200)[0]; log(o.strip()[-200:]); assert p.returncode == 0, 'load client failed'
    log('load took %.1fs' % (time.time() - t0)); sh(NT + ['flush', 'ks', 't'])
    for _ in range(90):
        cs = sh(NT + ['compactionstats'], check=False, quiet=True)
        if re.search(r'pending tasks\s+0\b', cs): break
        time.sleep(10)
    log(sh(NT + ['tablestats', 'ks.t'], check=False, quiet=True)[-1800:])
    n = cql("SELECT count(*) FROM ks.t WHERE pk = 7", timeout=600)[0][0]; log('rows in ks.t pk=7:', n); assert n == ROWS
    log('data bytes after load:', du()); sys.exit(0)

if mode == 'run':
    od = os.path.join(out, 'arms'); os.makedirs(od, exist_ok=True); marker = os.path.join(od, 'markers.txt')
    syslog = node + '/logs/system.log'; off = os.path.getsize(syslog) if os.path.exists(syslog) else 0
    make_conf('run'); start_node('run'); pid = node_pid()
    sh(NT + ['disableautocompaction', 'ks', 't'], check=False, quiet=True)
    jp = subprocess.Popen(['java', '-cp', os.path.join(out, 'tools'), 'Jmx', str(JMX), 'poll', '100', os.path.join(od, 'samples.csv')], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ev = open(os.path.join(od, 'arms.txt'), 'a')
    def mark(kind, label, extra=''):
        ev.write('%d %s %s %s\n' % (int(time.time() * 1000), kind, label, extra)); ev.flush()
    rc = 0
    # (label, shape, fetch size F, per-partition limit L); the first arm is the first-trigger arm
    fwd = []
    for shape in ('A', 'B'):
        for F in (5000, 100):
            for L in ('1', '100', 'abs'):
                fwd.append(('f_%s_L%s_F%d' % (shape, L, F), shape, F, L))
    fwd += [('f_B_Labs_F100000', 'B', 100000, 'abs'), ('f_B_L1_F100000', 'B', 100000, '1'), ('f_A_Labs_F100000', 'A', 100000, 'abs'), ('f_A_L1_F100000', 'A', 100000, '1')]
    rev = [('r_%s_L%s_F5000' % (s, L), s, 5000, L) for s in ('B', 'A') for L in ('abs', '100', '1')]
    try:
        time.sleep(15)
        mark('DISK', 'start', du())
        for nm, cmd in (('heapinfo-start.txt', 'GC.heap_info'), ('vmflags.txt', 'VM.flags')):
            open(os.path.join(od, nm), 'w').write(sh(['jcmd', str(pid), cmd], check=False, quiet=True))
        sh(['jcmd', str(pid), 'GC.run'], check=False, quiet=True); time.sleep(3)
        def arm(label, shape, fs, L, reps=None):
            reps = reps or REPS
            sh(['jcmd', str(pid), 'GC.run'], check=False, quiet=True); time.sleep(4)
            r0 = rchar(); mark('START', label, '%s %d %s %d' % (shape, fs, L, r0)); t0 = time.time()
            r = client('scan', shape, fs, L, reps, marker, label)
            r1 = rchar(); mark('END', label, '%s %d %s %d' % (shape, fs, L, r1))
            log('ARM', label, 'took %.1fs' % (time.time() - t0), 'rc', r, 'rchar delta', r1 - r0)
            if r: raise SystemExit(3)   # first-trigger / row-count check failed
        # warm-up: one pass of each shape, discarded, so JIT, sstable readers and indexes are warm
        mark('START', 'warmup', 'A 5000 abs %d' % rchar()); r = client('scan', 'A', 5000, 'abs', 1, marker, 'warmup'); r += client('scan', 'B', 5000, 'abs', 1, marker, 'warmup'); mark('END', 'warmup', 'B 5000 abs %d' % rchar())
        if r: raise SystemExit(3)
        for a in fwd: arm(*a)
        sh(['jcmd', str(pid), 'GC.run'], check=False, quiet=True); time.sleep(4)
        mark('START', 'noise', 'P 0 0 %d' % rchar()); client('point', REPS * 10, marker, 'noise'); mark('END', 'noise', 'P 0 0 %d' % rchar())
        for a in rev: arm(*a)
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
