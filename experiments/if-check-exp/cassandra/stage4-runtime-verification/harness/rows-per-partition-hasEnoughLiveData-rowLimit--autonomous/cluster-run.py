#!/usr/bin/env python3
"""Cluster tier driver (B3 as amended 2026-10-27), case rows-per-partition-hasEnoughLiveData-rowLimit--autonomous. Usage:
  cluster-run.py <tree> <nodedir> <outdir> load           create ks.t (20,000 pk x 200 rows x 100 chars) and ks.t2 (2,000 pk, ck 0-99 row-deleted), flush, drain
  cluster-run.py <tree> <nodedir> <outdir> arm <label>    one node lifetime, cold cache, 256 MiB row cache:
        n5 (N=5, ks.t)  n50  nall (N=ALL)  none (NONE)  t5 (N=5, ks.t2, pass 1 only)
        passes: P1 LIMIT 1, P2 LIMIT 100, P3 LIMIT 1; n50 then runs the informational setcachecapacity 0 8 0 step
Own ports (tag p75, slot 5): 127.0.5.1, storage 7000, ssl 7001, native 9042, JMX 7150. Stops the node on any exit.
First-trigger check: after P1 of an arm the cache must hold entries (none: zero); a failure stops the arm with exit 3 (the chain script stops there).
Env STAGE4_NPK (default 20000), STAGE4_NPK2 (default 2000) shrink the data for shakedowns only."""
import sys, os, subprocess, time, json, shutil, signal, resource, re, threading, atexit

tree, node, out, mode = sys.argv[1:5]; labels = sys.argv[5:]
HARN = os.path.dirname(os.path.abspath(__file__))
DRIVER = os.path.expanduser('~/s4-b11-p75-drv/cassandra-driver-3.29.0')
ADDR, STORAGE, SSL, NATIVE, JMX = '127.0.5.1', 7000, 7001, 9042, 7150
NPK = int(os.environ.get('STAGE4_NPK', 20000)); NPK2 = int(os.environ.get('STAGE4_NPK2', 2000)); NPROC = 4
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
        'cluster_name': "'p75'", 'num_tokens': '1',
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
    outl.append('# ---- stage4 p75 (B3a as amended) ----'); outl += ['%s: %s' % (k, v) for k, v in lines.items()]
    open(conf + '/cassandra.yaml', 'w').write('\n'.join(outl) + '\n')
    shutil.copy(conf + '/cassandra.yaml', os.path.join(out, 'cassandra.yaml.%s' % label))
    env = open(conf + '/cassandra-env.sh').read(); assert env.count('JMX_PORT="7199"') == 1
    open(conf + '/cassandra-env.sh', 'w').write(env.replace('JMX_PORT="7199"', 'JMX_PORT="%d"' % JMX))
    with open(conf + '/jvm11-server.options', 'a') as f: f.write('\n# stage4 p75\n-XX:+AlwaysPreTouch\n')
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

def clients(m, table, first, count, timeout, limit=1):
    q = count // NPROC; ps = []
    for i in range(NPROC):
        f = first + i * q; c = q if i < NPROC - 1 else count - 3 * q
        ps.append(subprocess.Popen([sys.executable, os.path.join(HARN, 'loader.py'), DRIVER, ADDR, str(NATIVE), m, table, str(f), str(c), str(limit)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL))
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

PASS_LIMITS = [1, 100, 1]   # P1 populates, P2 LIMIT above N, P3 LIMIT below N
ARMS = {  # label: (row_cache_size MiB, rows_per_partition, table, number of partitions read, passes)
    'n5': (256, '5', 't', None, 3), 'n50': (256, '50', 't', None, 3), 'nall': (256, 'ALL', 't', None, 3),
    't5': (256, '5', 't2', 'NPK2', 1), 'none': (256, 'NONE', 't', None, 3),
}
def run_arm(label):
    rc_mb, caching, table, npk_key, passes = ARMS[label]
    npk = NPK2 if npk_key else NPK
    od = os.path.join(out, label); os.makedirs(od, exist_ok=True)
    log('=== arm', label, 'row_cache_size', rc_mb, 'rows_per_partition', caching, 'table', table, 'partitions', npk)
    syslog = node + '/logs/system.log'; off = os.path.getsize(syslog) if os.path.exists(syslog) else 0
    make_conf(rc_mb, label); start_node(label); pid = node_pid()
    cql("ALTER TABLE ks.%s WITH caching = {'keys':'NONE','rows_per_partition':'%s'}" % (table, caching))
    log('schema caching =', [dict(r.caching) for r in cql("SELECT caching FROM system_schema.tables WHERE keyspace_name='ks' AND table_name='%s'" % table)])
    other = 't' if table == 't2' else 't2'
    cql("ALTER TABLE ks.%s WITH caching = {'keys':'NONE','rows_per_partition':'NONE'}" % other)   # the table not under test has its row cache off
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
        # warm-up (harness step carried over from the earlier row-cache case, before run 1): whole-partition reads of the other table (row cache off) put the read path's one-off native memory
        # (chunk cache, buffers, thread arenas) into the baseline; 'cold' is kept for the record
        t0 = time.time(); clients('full', other, 0, 1000, 3600); log('warm-up took %.1fs' % (time.time() - t0)); time.sleep(10)
        checkpoint('baseline', pid, od, table)
        for p in range(1, passes + 1):
            t0 = time.time(); rows = clients('scan', table, 0, npk, 3600, PASS_LIMITS[p - 1])
            log('scan pass %d (LIMIT %d) took %.1fs, rows returned %d' % (p, PASS_LIMITS[p - 1], time.time() - t0, rows)); r = checkpoint('pass%d' % p, pid, od, table, {'secs': round(time.time() - t0, 1), 'rows_returned': rows, 'limit': PASS_LIMITS[p - 1]})
            if p == 1:   # first-trigger check
                ok = (r.get('entries', -1) == 0) if label == 'none' else (r.get('entries', 0) > 0)
                log('FIRST-TRIGGER CHECK', 'ok' if ok else 'FAILED', 'entries =', r.get('entries'))
                if not ok: rc = 3; break
        sh(NT + ['info'], check=False)
        sh(NT + ['tablestats', 'ks.' + table], check=False, quiet=True)
        if label == 'n50' and rc == 0:   # informational: runtime capacity change 256 -> 8 MiB (not a B3f prediction)
            sh(NT + ['setcachecapacity', '0', '8', '0']); time.sleep(5); checkpoint('shrunk5s', pid, od, table)
            time.sleep(55); checkpoint('shrunk60s', pid, od, table)
            rows = clients('scan', table, 0, npk, 3600, 1); checkpoint('shrunk_p4', pid, od, table, {'rows_returned': rows, 'limit': 1})
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
log('cluster-run start mode=%s tree=%s head=%s labels=%s NPK=%d NPK2=%d' % (mode, tree, subprocess.run(['git', '-C', tree, 'rev-parse', '--short', 'HEAD'], stdout=subprocess.PIPE, text=True).stdout.strip(), labels, NPK, NPK2))
log('df:', subprocess.run(['df', '-T', node if os.path.exists(node) else os.path.dirname(node)], stdout=subprocess.PIPE, text=True).stdout.splitlines()[-1])
if mode == 'load':
    shutil.rmtree(node, ignore_errors=True)
    for d in ('data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw', 'logs'): os.makedirs(os.path.join(node, d))
    make_conf(0, 'load'); start_node('load')
    cql("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    for t in ('t', 't2'):
        cql("CREATE TABLE IF NOT EXISTS ks.%s (pk int, ck int, v text, PRIMARY KEY (pk, ck)) WITH caching = {'keys':'NONE','rows_per_partition':'NONE'} AND compression = {'enabled':'false'}" % t)
    t0 = time.time()
    q = NPK // 4
    for part in range(4):   # flush every quarter so the memtable stays small
        clients('load', 't', part * q, q, 3600); sh(NT + ['flush', 'ks', 't'], quiet=True)
    clients('load', 't2', 0, NPK2, 3600); sh(NT + ['flush', 'ks', 't2'], quiet=True)
    clients('del', 't2', 0, NPK2, 3600); sh(NT + ['flush', 'ks', 't2'], quiet=True)
    log('load took %.1fs' % (time.time() - t0))
    for _ in range(90):
        cs = sh(NT + ['compactionstats'], check=False, quiet=True)
        if re.search(r'pending tasks\s+0\b', cs): break
        time.sleep(10)
    log(sh(NT + ['tablestats', 'ks.t', 'ks.t2'], check=False, quiet=True)[-1800:])
    # known-answer check of the loaded data: one partition read back
    rows = cql("SELECT count(*) FROM ks.t WHERE pk = 17")[0][0]; log('rows in ks.t pk=17:', rows); assert rows == 200
    rows = cql("SELECT count(*) FROM ks.t2 WHERE pk = 17")[0][0]; log('live rows in ks.t2 pk=17 (100 deleted):', rows); assert rows == 100
    sh(['du', '-sb', node + '/data'], quiet=False)
    sys.exit(0)
if mode == 'arm':
    code = 0
    for lab in labels:
        code = run_arm(lab)
        if code: break
    sys.exit(code)
