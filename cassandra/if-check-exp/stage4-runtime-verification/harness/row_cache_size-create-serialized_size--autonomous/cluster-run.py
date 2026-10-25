#!/usr/bin/env python3
"""Cluster tier driver (B3 as amended B3i). Usage:
  cluster-run.py <tree> <nodedir> <outdir> load            create ks.t and load 32768 partitions (row cache 0MiB), flush, drain
  cluster-run.py <tree> <nodedir> <outdir> arm <label>...  labels: c0 c128 c512 c1024 n128 c128b   (one node lifetime each, cold cache)
Own ports/addresses (tag rc): 127.0.9.1, storage 7390, ssl 7391, native 9390, JMX 7399. Stops the node on any exit."""
import sys, os, subprocess, time, json, shutil, signal, resource, re, threading, atexit

tree, node, out, mode = sys.argv[1:5]; labels = sys.argv[5:]
HARN = os.path.dirname(os.path.abspath(__file__))
DRIVER = os.path.expanduser('~/s4-rc/driver/cassandra-driver-3.29.0')
ADDR, STORAGE, SSL, NATIVE, JMX = '127.0.9.1', 7390, 7391, 9390, 7399
NPK = int(os.environ.get('STAGE4_NPK', 32768)); RAND_S = int(os.environ.get('STAGE4_RAND_S', 180)); NPROC = 4
resource.setrlimit(resource.RLIMIT_NOFILE, (100000, 100000))
os.makedirs(out, exist_ok=True)
LOG = open(os.path.join(out, 'session.log'), 'a')
def log(*a):
    m = '[%s] %s' % (time.strftime('%FT%T%z'), ' '.join(str(x) for x in a)); print(m, flush=True); LOG.write(m + '\n'); LOG.flush()
def sh(cmd, check=True, timeout=None, quiet=False):
    log('+', cmd if isinstance(cmd, str) else ' '.join(cmd))
    t0 = time.time()
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

def make_conf(rc_mb, label):
    conf = node + '/conf'
    shutil.rmtree(conf, ignore_errors=True); shutil.copytree(tree + '/conf', conf)
    lines = {
        'cluster_name': "'rc'", 'num_tokens': '1',
        'data_file_directories': '\n    - %s/data' % node,
        'commitlog_directory': node + '/commitlog', 'hints_directory': node + '/hints', 'saved_caches_directory': node + '/saved_caches', 'cdc_raw_directory': node + '/cdc_raw',
        'listen_address': ADDR, 'rpc_address': ADDR,
        'seed_provider': '\n  - class_name: org.apache.cassandra.locator.SimpleSeedProvider\n    parameters:\n      - seeds: "%s:%d"' % (ADDR, STORAGE),
        'storage_port': str(STORAGE), 'ssl_storage_port': str(SSL), 'native_transport_port': str(NATIVE),
        'row_cache_class_name': 'org.apache.cassandra.cache.SerializingCacheProvider', 'row_cache_size': '%dMiB' % rc_mb, 'row_cache_save_period': '0s',
        'key_cache_size': '0MiB', 'counter_cache_size': '0MiB', 'file_cache_size': '64MiB', 'memtable_allocation_type': 'heap_buffers',
        'commitlog_total_space': '1GiB', 'auto_snapshot': 'false', 'cdc_enabled': 'false',
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
    outl.append('# ---- stage4 rc (B3a, B3i) ----'); outl += ['%s: %s' % (k, v) for k, v in lines.items()]
    open(conf + '/cassandra.yaml', 'w').write('\n'.join(outl) + '\n')
    shutil.copy(conf + '/cassandra.yaml', os.path.join(out, 'cassandra.yaml.%s' % label))
    env = open(conf + '/cassandra-env.sh').read(); assert env.count('JMX_PORT="7199"') == 1
    open(conf + '/cassandra-env.sh', 'w').write(env.replace('JMX_PORT="7199"', 'JMX_PORT="%d"' % JMX))
    with open(conf + '/jvm11-server.options', 'a') as f: f.write('\n# stage4 rc\n-XX:NativeMemoryTracking=summary\n')
    log('conf %s: row_cache_size=%dMiB' % (label, rc_mb))

def start_node(label):
    if node_pid() or daemons(): raise RuntimeError('a daemon of this tree is running: %s' % daemons())
    for p in (STORAGE, SSL, NATIVE, JMX):
        if subprocess.run("ss -ltn | grep -q ':%d '" % p, shell=True).returncode == 0: raise SystemExit('port %d busy' % p)
    env = dict(os.environ, MAX_HEAP_SIZE='2G', HEAP_NEWSIZE='512M', CASSANDRA_CONF=node + '/conf', CASSANDRA_LOG_DIR=node + '/logs')
    log('+ bin/cassandra -p', PIDF, '(ulimit -n %d)' % resource.getrlimit(resource.RLIMIT_NOFILE)[0])
    subprocess.run([os.path.join(tree, 'bin/cassandra'), '-p', PIDF], env=env, stdout=open(node + '/logs/stdout-%s.log' % label, 'w'), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=60)
    t0 = time.time()
    while time.time() - t0 < 300:
        time.sleep(4)
        if not node_pid() and time.time() - t0 > 12: raise RuntimeError('daemon died during start')
        st = subprocess.run(NT + ['status'], stdout=subprocess.PIPE, text=True, stderr=subprocess.DEVNULL).stdout
        sb = subprocess.run(NT + ['statusbinary'], stdout=subprocess.PIPE, text=True, stderr=subprocess.DEVNULL).stdout.strip()
        if re.search(r'^UN\s+' + re.escape(ADDR), st, re.M) and sb == 'running':
            log('node up (%s) after %.0f s, pid %s' % (label, time.time() - t0, node_pid())); return node_pid()
    raise RuntimeError('node did not come up')

sys.path.insert(0, DRIVER)
def cql(stmt, timeout=300):
    from cassandra.cluster import Cluster
    from cassandra.policies import DCAwareRoundRobinPolicy
    c = Cluster([ADDR], port=NATIVE, protocol_version=4, load_balancing_policy=DCAwareRoundRobinPolicy(local_dc='datacenter1'), token_metadata_enabled=False)
    s = c.connect()
    try:
        r = s.execute(stmt, timeout=timeout); return list(r) if r else []
    finally: c.shutdown()

def clients(m, ranges_or_args, timeout):
    ps = []
    for a in ranges_or_args:
        ps.append(subprocess.Popen([sys.executable, os.path.join(HARN, 'loader.py'), DRIVER, ADDR, str(NATIVE), m] + [str(x) for x in a], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL))
    res = []
    for p in ps:
        o = p.communicate(timeout=timeout)[0]; log(o.strip()[-300:]); res.append((p.returncode, o))
    assert all(r[0] == 0 for r in res), 'client failed'
    return res
def split(n): q = n // NPROC; return [(i * q, q if i < NPROC - 1 else n - 3 * q) for i in range(NPROC)]

# ---- measurement ----
def status_kb(pid, key):
    for l in open('/proc/%d/status' % pid):
        if l.startswith(key + ':'): return int(l.split()[1])
def checkpoint(name, pid, od, extra=None):
    sh(['jcmd', str(pid), 'GC.run'], check=False, quiet=True); time.sleep(3)
    rec = {'name': name, 'epoch_ms': int(time.time() * 1000), 'RssAnon_kb': status_kb(pid, 'RssAnon'), 'VmRSS_kb': status_kb(pid, 'VmRSS')}
    nmt = sh(['jcmd', str(pid), 'VM.native_memory', 'summary'], check=False, quiet=True); open(os.path.join(od, 'nmt-%s.txt' % name), 'w').write(nmt)
    m = re.search(r'^Total: reserved=(\d+)KB, committed=(\d+)KB', nmt, re.M); rec['nmt_total_committed_kb'] = int(m.group(2)) if m else None
    m = re.search(r'Java Heap \(reserved=(\d+)KB, committed=(\d+)KB\)', nmt); rec['nmt_heap_committed_kb'] = int(m.group(2)) if m else None
    hi = sh(['jcmd', str(pid), 'GC.heap_info'], check=False, quiet=True); open(os.path.join(od, 'heapinfo-%s.txt' % name), 'w').write(hi)
    j = subprocess.run(['java', '-cp', os.path.join(out, 'tools'), 'Jmx', str(JMX), 'once'], stdout=subprocess.PIPE, text=True, stderr=subprocess.STDOUT).stdout.strip().split(',')
    try: rec.update(size=int(j[1]), capacity=int(j[2]), entries=int(j[3]))
    except Exception: rec['jmx_raw'] = j
    if rec.get('nmt_total_committed_kb'): rec['est_kb'] = rec['RssAnon_kb'] - rec['nmt_total_committed_kb']
    if extra: rec.update(extra)
    open(os.path.join(od, 'ckpt.jsonl'), 'a').write(json.dumps(rec) + '\n'); log('CKPT', json.dumps(rec)); return rec

def run_arm(label):
    rc_mb, caching = {'c0': (0, 'ALL'), 'c128': (128, 'ALL'), 'c512': (512, 'ALL'), 'c1024': (1024, 'ALL'), 'n128': (128, 'NONE'), 'c128b': (128, 'ALL'), 't1024': (1024, 'ALL')}[label]
    od = os.path.join(out, label); os.makedirs(od, exist_ok=True)
    log('=== arm', label, 'row_cache_size', rc_mb, 'rows_per_partition', caching)
    syslog = node + '/logs/system.log'; off = os.path.getsize(syslog) if os.path.exists(syslog) else 0
    make_conf(rc_mb, label); start_node(label); pid = node_pid()
    cql("ALTER TABLE ks.t WITH caching = {'keys':'NONE','rows_per_partition':'%s'}" % caching)
    log('schema caching =', [dict(r.caching) for r in cql("SELECT caching FROM system_schema.tables WHERE keyspace_name='ks' AND table_name='t'")])
    stop = threading.Event()
    jp = subprocess.Popen(['java', '-cp', os.path.join(out, 'tools'), 'Jmx', str(JMX), 'poll', '5000', os.path.join(od, 'jmx.csv')], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    def samp():
        with open(os.path.join(od, 'rss.csv'), 'w') as f:
            f.write('epoch_ms,RssAnon_kb,VmRSS_kb\n')
            while not stop.is_set():
                try: f.write('%d,%d,%d\n' % (int(time.time() * 1000), status_kb(pid, 'RssAnon'), status_kb(pid, 'VmRSS'))); f.flush()
                except Exception: pass
                stop.wait(5)
    th = threading.Thread(target=samp); th.start()
    try:
        time.sleep(20); checkpoint('idle', pid, od)
        for p in (1, 2):
            t0 = time.time(); clients('scan', split(NPK), 3600); log('scan pass %d took %.1fs' % (p, time.time() - t0)); checkpoint('pass%d' % p, pid, od, {'secs': round(time.time() - t0, 1)})
        t0 = time.time(); clients('rand', [(100 + i, RAND_S, NPK) for i in range(NPROC)], RAND_S + 600); checkpoint('rand', pid, od, {'secs': round(time.time() - t0, 1)})
        hist = sh(['jcmd', str(pid), 'GC.class_histogram'], check=False, quiet=True)
        open(os.path.join(od, 'class_histogram.top.txt'), 'w').write('\n'.join(l for l in hist.splitlines()[:4] + [l for l in hist.splitlines() if 'RefCountedMemory' in l or 'OHCacheImpl' in l or 'RowCacheKey' in l]))
        if label == 't1024':   # POST-HOC diagnostic (added after run 1): does glibc hold freed blocks? malloc_trim(0) through gdb (sudo: ptrace_scope=1)
            for step, cmd in (('trimfull', None), ('set64', ['setcachecapacity', '0', '64', '0']), ('trimmed', None)):
                if cmd: sh(NT + cmd); time.sleep(30)
                else:
                    sh(['sudo', 'gdb', '-p', str(pid), '-batch', '-ex', 'call (int)malloc_trim(0)'], check=False); time.sleep(5)
                checkpoint(step, pid, od)
        if label == 'c1024':
            for cap in (256, 64, 1024):
                sh(NT + ['setcachecapacity', '0', str(cap), '0']); time.sleep(30); checkpoint('set%d' % cap, pid, od)
            t0 = time.time(); clients('rand', [(200 + i, 60, NPK) for i in range(NPROC)], 600); checkpoint('rand_after_set1024', pid, od, {'secs': round(time.time() - t0, 1)})
        sh(NT + ['info'], quiet=False)
        sh(NT + ['tablestats', 'ks.t'], check=False, quiet=True)
    finally:
        stop.set(); th.join(); jp.terminate()
        with open(syslog, errors='replace') as f: f.seek(off); seg = f.read()
        open(os.path.join(od, 'system.log.segment'), 'w').write(seg)
        errs = [l for l in seg.splitlines() if l.startswith('ERROR')]; log('ERROR lines in segment:', len(errs), errs[:3])
        log('Initializing row cache lines:', [l for l in seg.splitlines() if 'Initializing row cache' in l])
        stop_node()

shutil.copytree(HARN, os.path.join(out, 'tools_src'), dirs_exist_ok=True)
os.makedirs(os.path.join(out, 'tools'), exist_ok=True); sh(['javac', '-d', os.path.join(out, 'tools'), HARN + '/Jmx.java'])
log('cluster-run start mode=%s tree=%s head=%s labels=%s' % (mode, tree, subprocess.run(['git', '-C', tree, 'rev-parse', '--short', 'HEAD'], stdout=subprocess.PIPE, text=True).stdout.strip(), labels))
log('df:', subprocess.run(['df', '-T', os.path.expanduser('~')], stdout=subprocess.PIPE, text=True).stdout.splitlines()[-1])
if mode == 'load':
    shutil.rmtree(node, ignore_errors=True)
    for d in ('data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw', 'logs'): os.makedirs(os.path.join(node, d))
    make_conf(0, 'load'); start_node('load')
    cql("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    cql("CREATE TABLE IF NOT EXISTS ks.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck)) WITH caching = {'keys':'NONE','rows_per_partition':'ALL'} AND compression = {'enabled':'false'}")
    t0 = time.time()
    # flush every quarter so the memtable never grows large
    for part in range(4):
        q = NPK // 4
        clients('load', [(part * q + i * (q // NPROC), q // NPROC) for i in range(NPROC)], 3600)
        sh(NT + ['flush', 'ks', 't'], quiet=True)
    log('load took %.1fs' % (time.time() - t0))
    sh(NT + ['compactionstats'], check=False)
    for _ in range(60):
        cs = sh(NT + ['compactionstats'], check=False, quiet=True)
        if re.search(r'pending tasks:?\s+0', cs): break
        time.sleep(10)
    sh(NT + ['tablestats', 'ks.t'])
    sh('du -sb %s/data/ks' % node)
    stop_node()
else:
    assert mode == 'arm'
    for l in labels: run_arm(l)
log('cluster-run done')
