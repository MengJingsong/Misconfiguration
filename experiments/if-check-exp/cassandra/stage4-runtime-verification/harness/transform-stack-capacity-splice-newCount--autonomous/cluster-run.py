#!/usr/bin/env python3
"""Cluster tier driver (case file B3 as amended B3i). Usage: cluster-run.py <nodetree> <workdir> <outdir> <driver-dir> <rules.btm> [phases...]
Phases (default all): up load diverge scan control down.  Two nodes on 127.54.0.1 / 127.54.0.2 (ports 7054/9054, JMX 7154/7155), Byteman rules from rules.btm on both.
Every process is started by this script and stopped by PID on any exit; nothing is matched by name."""
import sys, os, re, time, json, signal, subprocess, shutil, threading, atexit, random, resource
tree, work, out, drv, rules = [os.path.abspath(a) for a in sys.argv[1:6]]
PHASES = sys.argv[6:] or ['up', 'load', 'diverge', 'scan', 'control', 'down']
ADDR = {1: '127.54.0.1', 2: '127.54.0.2'}; JMX = {1: 7154, 2: 7155}; STORAGE, NATIVE = 7054, 9054
ROWS = int(os.environ.get('STAGE4_ROWS', 80000)); LS = [int(x) for x in os.environ.get('STAGE4_LS', '10,2000,40000').split(',')]; DUR = int(os.environ.get('STAGE4_DUR', 40))
resource.setrlimit(resource.RLIMIT_NOFILE, (100000, 100000))
os.makedirs(out, exist_ok=True)
LOG = open(os.path.join(out, 'session.log'), 'a')
def log(*a):
    m = '[%s] %s' % (time.strftime('%FT%T%z'), ' '.join(str(x) for x in a)); print(m, flush=True); LOG.write(m + '\n'); LOG.flush()
def sh(cmd, check=True, timeout=300, quiet=False):
    t0 = time.time()
    p = subprocess.run(cmd, shell=isinstance(cmd, str), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    if not quiet: log('+', cmd if isinstance(cmd, str) else ' '.join(cmd), '->', p.returncode, '(%.1fs)' % (time.time() - t0), p.stdout.strip()[-400:])
    if check and p.returncode: raise RuntimeError('failed: %s\n%s' % (cmd, p.stdout))
    return p.stdout
def nd(i): return os.path.join(work, 'node%d' % i)
def pidf(i): return os.path.join(nd(i), 'cassandra.pid')
def pid(i):
    try: return int(open(pidf(i)).read().strip())
    except Exception: return None
def alive(p):
    try: os.kill(p, 0); return True
    except OSError: return False
def NT(i): return [os.path.join(tree, 'bin/nodetool'), '-h', '127.0.0.1', '-p', str(JMX[i])]
def stop_node(i, drain=True):
    p = pid(i)
    if p and alive(p):
        log('stopping node', i, 'pid', p)
        if drain:
            try: sh(NT(i) + ['drain'], check=False, timeout=240)
            except Exception as e: log('drain error', e)
        try:
            os.kill(p, signal.SIGTERM)
            for _ in range(90):
                if not alive(p): break
                time.sleep(1)
            else: os.kill(p, signal.SIGKILL)
        except OSError: pass
    log('node', i, 'pid alive after stop:', bool(p and alive(p)))
def stop_all():
    for i in (1, 2): stop_node(i, drain=False)
atexit.register(stop_all)
def setkey(txt, k, v):
    if re.search(r'^%s:' % k, txt, re.M): return re.sub(r'^%s:.*$' % k, '%s: %s' % (k, v), txt, flags=re.M)
    return txt + '\n%s: %s\n' % (k, v)
def setup_node(i):
    n = nd(i); shutil.rmtree(n, ignore_errors=True)
    for d in ('data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw', 'logs'): os.makedirs(os.path.join(n, d))
    shutil.copytree(os.path.join(tree, 'conf'), os.path.join(n, 'conf'))
    envsh = os.path.join(n, 'conf/cassandra-env.sh'); t = open(envsh).read()
    assert 'JMX_PORT="7199"' in t; open(envsh, 'w').write(t.replace('JMX_PORT="7199"', 'JMX_PORT="%d"' % JMX[i]))
    y = os.path.join(n, 'conf/cassandra.yaml'); txt = open(y).read()
    txt = re.sub(r'^listen_address:.*$', 'listen_address: ' + ADDR[i], txt, flags=re.M); txt = re.sub(r'^rpc_address:.*$', 'rpc_address: ' + ADDR[i], txt, flags=re.M)
    txt = re.sub(r'- seeds: ".*"', '- seeds: "%s:%d"' % (ADDR[1], STORAGE), txt)
    for k, v in (('storage_port', STORAGE), ('native_transport_port', NATIVE), ('cluster_name', "'st-stage4'"), ('auto_snapshot', 'false'), ('cdc_enabled', 'false'),
                 ('num_tokens', 1), ('hinted_handoff_enabled', 'false'), ('commitlog_directory', n + '/commitlog'), ('hints_directory', n + '/hints'),
                 ('saved_caches_directory', n + '/saved_caches'), ('cdc_raw_directory', n + '/cdc_raw'), ('key_cache_size', '0MiB'), ('row_cache_size', '0MiB'),
                 ('read_request_timeout', '60000ms'), ('range_request_timeout', '60000ms'), ('native_transport_timeout', '60s'), ('write_request_timeout', '60000ms')):
        txt = setkey(txt, k, v)
    txt = re.sub(r'^data_file_directories:\n(\s+-.*\n)?', '', txt, flags=re.M)
    txt += '\ndata_file_directories:\n    - %s/data\n' % n
    open(y, 'w').write(txt)
def start_node(i):
    n = nd(i)
    env = dict(os.environ, MAX_HEAP_SIZE='1G', HEAP_NEWSIZE='256M', CASSANDRA_CONF=n + '/conf', CASSANDRA_LOG_DIR=n + '/logs',
               JVM_EXTRA_OPTS='-Dcassandra.ring_delay_ms=5000 -Dstage4.trace=%s/logs/byteman-trace.txt -javaagent:%s/build/lib/jars/byteman-4.0.20.jar=script:%s' % (n, tree, rules))
    if os.path.exists(pidf(i)): os.remove(pidf(i))
    log('start node', i)
    subprocess.run([os.path.join(tree, 'bin/cassandra'), '-p', pidf(i)], env=env, stdout=open(n + '/logs/stdout-%d.log' % int(time.time()), 'w'), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=120)
    t0 = time.time()
    while time.time() - t0 < 400:
        time.sleep(4)
        p = pid(i)
        if not p or not alive(p): raise RuntimeError('daemon %d died during start' % i)
        st = subprocess.run(NT(i) + ['status'], stdout=subprocess.PIPE, text=True, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL).stdout
        sb = subprocess.run(NT(i) + ['statusbinary'], stdout=subprocess.PIPE, text=True, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL).stdout.strip()
        if len(re.findall(r'^UN', st, re.M)) >= (2 if (i == 2 or os.path.exists(nd(2) + '/joined')) else 1) and sb == 'running': break
    else: raise RuntimeError('node did not come up')
    log('node', i, 'up pid', pid(i), 'in %.0fs' % (time.time() - t0))
    ev = os.path.join(out, 'evidence-node%d' % i); os.makedirs(ev, exist_ok=True)
    open(ev + '/cmdline.txt', 'w').write(open('/proc/%d/cmdline' % pid(i), 'rb').read().replace(b'\0', b' ').decode())
    open(ev + '/yaml-keys.txt', 'w').write('\n'.join(l for l in open(n + '/conf/cassandra.yaml').read().splitlines() if re.match(r'(key_cache|row_cache|listen_address|rpc_address|storage_port|native_transport_port|hinted_handoff|num_tokens|cluster_name)', l)))
    if i == 2: open(nd(2) + '/joined', 'w').write('1')

sys.path.insert(0, drv)
def connect(only=None):
    from cassandra.cluster import Cluster
    from cassandra.policies import WhiteListRoundRobinPolicy
    from cassandra import ConsistencyLevel
    c = Cluster([ADDR[only or 1]], port=NATIVE, protocol_version=5, load_balancing_policy=WhiteListRoundRobinPolicy([ADDR[only or 1]]), connect_timeout=30, control_connection_timeout=30)
    return c, c.connect()
def run_async(s, ps, gen, inflight=64):
    sem = threading.Semaphore(inflight); st = dict(err=0, n=0, first=None)
    def ok(_): sem.release()
    def bad(e): st['err'] += 1; st['first'] = st['first'] or str(e)[:300]; sem.release()
    for a in gen:
        sem.acquire(); f = s.execute_async(ps, a, timeout=120); f.add_callbacks(ok, bad); st['n'] += 1
    for _ in range(inflight): sem.acquire()
    return st

CLASSES = ['[Lorg.apache.cassandra.db.transform.Transformation;', '[Lorg.apache.cassandra.db.transform.Stack$MoreContentsHolder;', 'org.apache.cassandra.db.transform.Stack$MoreContentsHolder', 'org.apache.cassandra.cache.KeyCacheKey']
def histogram(i):
    o = sh(['jcmd', str(pid(i)), 'GC.class_histogram'], quiet=True, timeout=300)
    d = {c: (0, 0) for c in CLASSES}; total = None
    for l in o.splitlines():
        f = l.split()
        if len(f) >= 4 and f[-1] in d: d[f[-1]] = (int(f[1]), int(f[2]))
        if f and f[0] == 'Total': total = (int(f[1]), int(f[2]))
    return total, d
class Sampler(threading.Thread):
    def __init__(self, label, nodes, dt): super().__init__(daemon=True); self.label, self.nodes, self.dt, self.stop_, self.rows = label, nodes, dt, threading.Event(), []
    def run(self):
        while not self.stop_.is_set():
            for i in self.nodes:
                try:
                    t = int(time.time() * 1000); tot, d = histogram(i)
                    self.rows.append([self.label, i, t, tot[0], tot[1]] + [x for c in CLASSES for x in d[c]])
                except Exception as e: log('sampler error', e)
            self.stop_.wait(self.dt)
    def dump(self, name):
        with open(os.path.join(out, name), 'w') as f:
            f.write('label,node,t_ms,total_objs,total_bytes,' + ','.join('%s_objs,%s_bytes' % (c, c) for c in CLASSES) + '\n')
            for r in self.rows: f.write(','.join(str(x) for x in r) + '\n')
def trace_counts(i):
    S = G = SRP = mx = mxk = 0
    p = nd(i) + '/logs/byteman-trace.txt'
    if os.path.exists(p):
        for l in open(p):
            if l.startswith('S '):
                S += 1; f = l.split(); mx = max(mx, int(f[1])); mxk = max(mxk, int(f[2]))
            elif l.startswith('G '): G += 1
            elif l.startswith('SRP'): SRP += 1
    return dict(S=S, G=G, SRP=SRP, max_newCount=mx, max_keepLength=mxk)
def srp_log_lines(i):
    p = nd(i) + '/logs/system.log'
    return sum(1 for l in open(p, errors='replace') if 'for short read protection' in l) if os.path.exists(p) else 0
def rss_anon_kb(i):
    for l in open('/proc/%d/status' % pid(i)):
        if l.startswith('RssAnon:'): return int(l.split()[1])

R = {}  # results for this invocation
def save(): json.dump(R, open(os.path.join(out, 'phases.json'), 'w'), indent=1)
if os.path.exists(os.path.join(out, 'phases.json')): R.update(json.load(open(os.path.join(out, 'phases.json'))))

if 'up' in PHASES:
    for i in (1, 2): setup_node(i)
    start_node(1); start_node(2)
    for i in (1, 2): sh(NT(i) + ['status'])
    c, s = connect()
    s.execute("CREATE KEYSPACE IF NOT EXISTS st WITH replication = {'class':'SimpleStrategy','replication_factor':2}")
    s.execute("CREATE TABLE IF NOT EXISTS st.t (id int PRIMARY KEY, v blob) WITH read_repair = 'NONE' AND compression = {'enabled':'false'}")
    c.shutdown()
if 'load' in PHASES:
    from cassandra import ConsistencyLevel
    c, s = connect(); ps = s.prepare('INSERT INTO st.t (id, v) VALUES (?, ?)'); ps.consistency_level = ConsistencyLevel.ALL
    t0 = time.time(); st = run_async(s, ps, ((k, random.Random(k).randbytes(1024)) for k in range(ROWS)))
    log('load', st, '%.0fs' % (time.time() - t0)); c.shutdown(); assert st['err'] == 0
    for i in (1, 2): sh(NT(i) + ['flush'], timeout=300)
    R['load'] = st; save()
if 'diverge' in PHASES:
    from cassandra import ConsistencyLevel
    stop_node(2)
    c, s = connect(1); ps = s.prepare('DELETE FROM st.t WHERE id = ?'); ps.consistency_level = ConsistencyLevel.ONE
    st = run_async(s, ps, ((k,) for k in range(0, ROWS, 2))); log('delete evens at ONE via node 1 (node 2 down)', st); c.shutdown(); assert st['err'] == 0
    sh(NT(1) + ['flush'], timeout=300)
    start_node(2)
    R['diverge'] = st; save()
if 'scan' in PHASES:
    from cassandra import ConsistencyLevel
    from cassandra.query import SimpleStatement
    R.setdefault('scan', {})
    c, s = connect(1)
    for L in LS:
        label = 'L%d' % L
        before = {i: trace_counts(i) for i in (1, 2)}; srp_before = {i: srp_log_lines(i) for i in (1, 2)}
        smp = Sampler(label, (1, 2), 1.0); smp.start(); time.sleep(4)   # idle samples first
        stmt = SimpleStatement('SELECT * FROM st.t LIMIT %d' % L, consistency_level=ConsistencyLevel.ALL, fetch_size=L + 1)
        t_start = int(time.time() * 1000); scans = []; t0 = time.time()
        while time.time() - t0 < DUR:
            a = time.time(); rows = list(s.execute(stmt, timeout=120)); scans.append((len(rows), round(time.time() - a, 3)))
        t_end = int(time.time() * 1000); time.sleep(3); smp.stop_.set(); smp.join(); smp.dump('samples-%s.csv' % label)
        after = {i: trace_counts(i) for i in (1, 2)}; srp_after = {i: srp_log_lines(i) for i in (1, 2)}
        R['scan'][label] = dict(L=L, t_start=t_start, t_end=t_end, nscans=len(scans), rows_per_scan=sorted(set(r for r, _ in scans)), mean_secs=round(sum(x for _, x in scans) / len(scans), 3),
                                trace_before=before, trace_after=after, srp_log_before=srp_before, srp_log_after=srp_after,
                                rssanon_kb={i: rss_anon_kb(i) for i in (1, 2)})
        log(label, json.dumps(R['scan'][label])); save()
    c.shutdown()
if 'control' in PHASES:
    from cassandra import ConsistencyLevel
    c, s = connect(1); ps = s.prepare('SELECT v FROM st.t WHERE id = ?'); ps.consistency_level = ConsistencyLevel.ALL
    R.setdefault('control', {})
    for label, args in (('keycache_off', ['0', '0', '0']), ('keycache_64', ['64', '0', '0'])):
        sh(NT(1) + ['setcachecapacity'] + args)
        smp = Sampler(label, (1,), 1.0); smp.start(); time.sleep(3)
        info0 = sh(NT(1) + ['info'], quiet=True)
        for k in (1, 2):
            t0 = time.time(); st = run_async(s, ps, ((j,) for j in range(ROWS)), 64); log(label, 'pass', k, st, '%.0fs' % (time.time() - t0))
        time.sleep(3); smp.stop_.set(); smp.join(); smp.dump('samples-%s.csv' % label)
        info = sh(NT(1) + ['info'], quiet=True); m = re.search(r'Key Cache\s*:.*', info)
        open(os.path.join(out, 'info-%s.txt' % label), 'w').write(info)
        R['control'][label] = dict(key_cache_line=m.group(0) if m else None, last_pass=st); log(label, R['control'][label]); save()
    c.shutdown()
if 'down' in PHASES:
    for i in (1, 2): stop_node(i)
    for i in (1, 2):
        for f in ('system.log', 'byteman-trace.txt'):
            p = nd(i) + '/logs/' + f
            if os.path.exists(p): shutil.copy(p, os.path.join(out, 'node%d-%s' % (i, f)) if f != 'system.log' else os.path.join(out, 'node%d-system.log' % i))
    log('down; pids alive:', [pid(i) and alive(pid(i)) for i in (1, 2)])
