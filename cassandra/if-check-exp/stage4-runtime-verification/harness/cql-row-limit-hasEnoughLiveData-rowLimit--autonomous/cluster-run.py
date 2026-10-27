#!/usr/bin/env python3
"""Cluster tier driver (B3 as amended 2026-10-27), case cql-row-limit-hasEnoughLiveData-rowLimit. Usage:
  cluster-run.py <tree> <nodedir> <outdir> load            create ks.t (200 pk x 2000 rows x 200 B) and ks.t2 (100 pk, same shape; warm-up table), flush
  cluster-run.py <tree> <nodedir> <outdir> arm <label>...  one node lifetime per arm (labels in ARMS): l1000 l10 l100 l100k lnone a100 anone s256 off10 off1000 offnone
Own ports (tag c74, slot 4): 127.0.4.1, storage 7000, ssl 7001, native 9042, JMX 7140. Stops the node on any exit.
First-trigger checks: after the populate pass an on-arm must hold entries (off arms: none); in the first arm (l1000) the window must raise RowCacheHitOutOfRange; failure stops with exit 3.
Env STAGE4_NPK (default 200), STAGE4_READS (default 10000), STAGE4_IDLE (default 60) shrink the run for shakedowns only."""
import sys, os, subprocess, time, json, shutil, signal, resource, re, threading, atexit

tree, node, out, mode = sys.argv[1:5]; labels = sys.argv[5:]
HARN = os.path.dirname(os.path.abspath(__file__))
DRIVER = os.path.expanduser('~/s4-b11-c74-drv/cassandra-driver-3.29.0')
ADDR, STORAGE, SSL, NATIVE, JMX = '127.0.4.1', 7000, 7001, 9042, 7140
NPK = int(os.environ.get('STAGE4_NPK', 200)); NPK2 = 100; READS = int(os.environ.get('STAGE4_READS', 10000)); IDLE = int(os.environ.get('STAGE4_IDLE', 60)); NPROC = 4
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
        'cluster_name': "'c74'", 'num_tokens': '1',
        'data_file_directories': '\n    - %s/data' % node,
        'commitlog_directory': node + '/commitlog', 'hints_directory': node + '/hints', 'saved_caches_directory': node + '/saved_caches', 'cdc_raw_directory': node + '/cdc_raw',
        'listen_address': ADDR, 'rpc_address': ADDR,
        'seed_provider': '\n  - class_name: org.apache.cassandra.locator.SimpleSeedProvider\n    parameters:\n      - seeds: "%s:%d"' % (ADDR, STORAGE),
        'storage_port': str(STORAGE), 'ssl_storage_port': str(SSL), 'native_transport_port': str(NATIVE),
        'row_cache_class_name': 'org.apache.cassandra.cache.OHCProvider', 'row_cache_size': '%dMiB' % rc_mb, 'row_cache_save_period': '0s',
        'key_cache_size': '0MiB', 'counter_cache_size': '0MiB', 'file_cache_size': '64MiB', 'memtable_allocation_type': 'heap_buffers',
        'commitlog_total_space': '2GiB', 'auto_snapshot': 'false', 'cdc_enabled': 'false', 'concurrent_compactors': '2',
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
    outl.append('# ---- stage4 c74 (B3a as amended) ----'); outl += ['%s: %s' % (k, v) for k, v in lines.items()]
    open(conf + '/cassandra.yaml', 'w').write('\n'.join(outl) + '\n')
    shutil.copy(conf + '/cassandra.yaml', os.path.join(out, 'cassandra.yaml.%s' % label))
    env = open(conf + '/cassandra-env.sh').read(); assert env.count('JMX_PORT="7199"') == 1
    open(conf + '/cassandra-env.sh', 'w').write(env.replace('JMX_PORT="7199"', 'JMX_PORT="%d"' % JMX))
    with open(conf + '/jvm11-server.options', 'a') as f: f.write('\n# stage4 c74\n-XX:+AlwaysPreTouch\n')
    log('conf %s: row_cache_size=%dMiB' % (label, rc_mb))

def start_node(label):
    if node_pid() or daemons(): raise RuntimeError('a daemon of this tree is running: %s' % daemons())
    for p in (STORAGE, SSL, NATIVE):   # other cases listen on the same port numbers at their own loopback addresses: check only ours
        if subprocess.run("ss -ltn | grep -q '%s:%d '" % (ADDR, p), shell=True).returncode == 0: raise SystemExit('port %s:%d busy' % (ADDR, p))
    if subprocess.run("ss -ltn | grep -q ':%d '" % JMX, shell=True).returncode == 0: raise SystemExit('JMX port %d busy' % JMX)
    env = dict(os.environ, MAX_HEAP_SIZE='2G', HEAP_NEWSIZE='512M', CASSANDRA_CONF=node + '/conf', CASSANDRA_LOG_DIR=node + '/logs')
    log('+ bin/cassandra -p', PIDF, '(ulimit -n %d)' % resource.getrlimit(resource.RLIMIT_NOFILE)[0])
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

def clients(m, table, first, count, timeout, extra=()):
    """m: load (extra: nck, blob) | full | q (extra: L) | rnd (first = seed, extra: L, npk). Returns (rows returned, ok requests)."""
    q = count // NPROC; ps = []
    for i in range(NPROC):
        f = first + i * q if m != 'rnd' else first * 100 + i
        c = q if i < NPROC - 1 else count - (NPROC - 1) * q
        ps.append(subprocess.Popen([sys.executable, os.path.join(HARN, 'loader.py'), DRIVER, ADDR, str(NATIVE), m, table, str(f), str(c)] + [str(x) for x in extra], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL))
    res = []
    for p in ps:
        o = p.communicate(timeout=timeout)[0]; log(o.strip()[-300:]); res.append((p.returncode, o))
    assert all(r[0] == 0 for r in res), 'client failed'
    rows = sum(int(re.search(r' rows (\d+)', o).group(1)) for _, o in res)
    return rows

def status_kb(pid, key):
    for l in open('/proc/%d/status' % pid):
        if l.startswith(key + ':'): return int(l.split()[1])
def jmx_once(table):
    j = subprocess.run(['java', '-cp', os.path.join(out, 'tools'), 'Jmx', str(JMX), 'once', table], stdout=subprocess.PIPE, text=True, stderr=subprocess.STDOUT).stdout.strip().split(',')
    return j
def checkpoint(name, pid, od, table, extra=None):
    sh(['jcmd', str(pid), 'GC.run'], check=False, quiet=True); time.sleep(3)
    rec = {'name': name, 'table': table, 'epoch_ms': int(time.time() * 1000), 'RssAnon_kb': status_kb(pid, 'RssAnon'), 'VmRSS_kb': status_kb(pid, 'VmRSS')}
    hi = sh(['jcmd', str(pid), 'GC.heap_info'], check=False, quiet=True); open(os.path.join(od, 'heapinfo-%s.txt' % name), 'w').write(hi)
    j = jmx_once(table)
    try: rec.update(size=int(j[1]), capacity=int(j[2]), entries=int(j[3]), hit=int(j[4]), miss=int(j[5]), outOfRange=int(j[6]))
    except Exception: rec['jmx_raw'] = j
    if extra: rec.update(extra)
    open(os.path.join(od, 'ckpt.jsonl'), 'a').write(json.dumps(rec) + '\n'); log('CKPT', json.dumps(rec)); return rec

ARMS = {  # label: (row_cache_size MiB, rows_per_partition, L (None = no LIMIT))
    'l1000': (64, '100', 1000), 'l10': (64, '100', 10), 'l100': (64, '100', 100), 'l100k': (64, '100', 100000), 'lnone': (64, '100', None),
    'a100': (64, 'ALL', 100), 'anone': (64, 'ALL', None), 's256': (256, 'ALL', 100),
    'off10': (0, '100', 10), 'off1000': (0, '100', 1000), 'offnone': (0, '100', None),
}
def run_arm(label):
    rc_mb, caching, L = ARMS[label]; table = 't'; other = 't2'
    Ls = 'none' if L is None else str(L)
    od = os.path.join(out, label); os.makedirs(od, exist_ok=True)
    log('=== arm', label, 'row_cache_size', rc_mb, 'rows_per_partition', caching, 'L', Ls, 'reads', READS)
    syslog = node + '/logs/system.log'; off = os.path.getsize(syslog) if os.path.exists(syslog) else 0
    make_conf(rc_mb, label); start_node(label); pid = node_pid()
    cql("ALTER TABLE ks.t WITH caching = {'keys':'NONE','rows_per_partition':'%s'}" % caching)
    log('schema caching =', [dict(r.caching) for r in cql("SELECT caching FROM system_schema.tables WHERE keyspace_name='ks' AND table_name='t'")])
    cql("ALTER TABLE ks.t2 WITH caching = {'keys':'NONE','rows_per_partition':'NONE'}")   # the warm-up table has its row cache off
    sh(NT + ['invalidaterowcache'])
    stop = threading.Event()
    jp = subprocess.Popen(['java', '-cp', os.path.join(out, 'tools'), 'Jmx', str(JMX), 'poll', '5000', os.path.join(od, 'jmx.csv'), table], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    def samp():
        with open(os.path.join(od, 'rss.csv'), 'w') as f:
            f.write('epoch_ms,RssAnon_kb,VmRSS_kb\n')
            while not stop.is_set():
                try: f.write('%d,%d,%d\n' % (int(time.time() * 1000), status_kb(pid, 'RssAnon'), status_kb(pid, 'VmRSS'))); f.flush()
                except Exception: pass
                stop.wait(5)
    th = threading.Thread(target=samp); th.start()
    rc = 0
    try:
        time.sleep(20); checkpoint('cold', pid, od, table)
        t0 = time.time(); clients('full', other, 0, NPK2, 3600); log('warm-up took %.1fs' % (time.time() - t0)); time.sleep(10)
        checkpoint('baseline', pid, od, table)
        t0 = time.time(); rows = clients('q', table, 0, NPK, 3600, ['none']); log('populate pass took %.1fs, rows returned %d' % (time.time() - t0, rows))
        r = checkpoint('populated', pid, od, table, {'rows_returned': rows})
        ok = (r.get('entries', -1) == 0) if rc_mb == 0 else (r.get('entries', 0) > 0)
        log('FIRST-TRIGGER CHECK (populate)', 'ok' if ok else 'FAILED', 'entries =', r.get('entries'))
        if not ok: return 3
        t0 = time.time(); rows = clients('rnd', table, 74, READS, 3600, [Ls, NPK])
        secs = round(time.time() - t0, 1); log('window took %.1fs, rows returned %d' % (secs, rows))
        r = checkpoint('window', pid, od, table, {'secs': secs, 'rows_returned': rows, 'L': Ls, 'reads': READS})
        if label == 'l1000':
            ok = r.get('outOfRange', 0) > 0
            log('FIRST-TRIGGER CHECK (disallow branch)', 'ok' if ok else 'FAILED', 'outOfRange =', r.get('outOfRange'))
            if not ok: return 3
        log('idle %d s' % IDLE); time.sleep(IDLE); checkpoint('idle', pid, od, table)
        sh(NT + ['info'], check=False)
    finally:
        stop.set(); th.join(); jp.terminate()
        with open(syslog, errors='replace') as f: f.seek(off); seg = f.read()
        open(os.path.join(od, 'system.log.segment'), 'w').write(seg)
        errs = [l for l in seg.splitlines() if l.startswith('ERROR')]; log('ERROR lines in segment:', len(errs), errs[:3])
        log('Initializing row cache lines:', [l for l in seg.splitlines() if 'Initializing row cache' in l])
        stop_node()
    return rc

shutil.copytree(HARN, os.path.join(out, 'tools_src'), dirs_exist_ok=True)
os.makedirs(os.path.join(out, 'tools'), exist_ok=True); sh(['javac', '-d', os.path.join(out, 'tools'), HARN + '/Jmx.java'])
log('cluster-run start mode=%s tree=%s head=%s labels=%s NPK=%d reads=%d' % (mode, tree, subprocess.run(['git', '-C', tree, 'rev-parse', '--short', 'HEAD'], stdout=subprocess.PIPE, text=True).stdout.strip(), labels, NPK, READS))
log('df:', subprocess.run(['df', '-T', node if os.path.exists(node) else os.path.dirname(node)], stdout=subprocess.PIPE, text=True).stdout.splitlines()[-1])
if mode == 'load':
    shutil.rmtree(node, ignore_errors=True)
    for d in ('data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw', 'logs'): os.makedirs(os.path.join(node, d))
    make_conf(0, 'load'); start_node('load')
    cql("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    for t in ('t', 't2'):
        cql("CREATE TABLE IF NOT EXISTS ks.%s (pk int, ck int, v blob, PRIMARY KEY (pk, ck)) WITH caching = {'keys':'NONE','rows_per_partition':'NONE'} AND compression = {'enabled':'false'}" % t)
    t0 = time.time()
    clients('load', 't', 0, NPK, 3600, [2000, 200]); sh(NT + ['flush', 'ks', 't'], quiet=True)
    clients('load', 't2', 0, NPK2, 3600, [2000, 200]); sh(NT + ['flush', 'ks', 't2'], quiet=True)
    log('load took %.1fs' % (time.time() - t0))
    for _ in range(90):
        cs = sh(NT + ['compactionstats'], check=False, quiet=True)
        if re.search(r'pending tasks\s+0\b', cs): break
        time.sleep(10)
    log(sh(NT + ['tablestats', 'ks.t', 'ks.t2'], check=False, quiet=True)[-1800:])
    rows = cql("SELECT count(*) FROM ks.t WHERE pk = 17")[0][0]; log('rows in ks.t pk=17:', rows); assert rows == 2000
    rows = cql("SELECT count(*) FROM ks.t2 WHERE pk = 17")[0][0]; log('rows in ks.t2 pk=17:', rows); assert rows == 2000
    sh(['du', '-sb', node + '/data'], quiet=False)
    sys.exit(0)
if mode == 'arm':
    code = 0
    for lab in labels:
        code = run_arm(lab)
        if code: break
    sys.exit(code)
