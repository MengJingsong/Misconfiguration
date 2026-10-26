#!/usr/bin/env python3
"""Cluster tier driver (case file B3 as amended B3i).
Usage: cluster-run.py <node-tree> <nodedir> <outdir> <helper-jar> <btm-file> <label>...
Labels: A128 A512 B128 B512, each optionally with a repeat suffix r1 / r2 (for example A128r1).
  A = Run A (1,000,000 rows, pk 16 B), B = Run B (2,000 rows, pk 60,000 B); the number is memtable_heap_space in MiB.
One single-node Cassandra on 127.0.41.1 (storage 7011, native 9143, JMX 7211); a fresh data directory per label.
Stops the node on any exit; kills by PID only. env STAGE4_SMALL=<n> shrinks the row counts (instrument shakedown only)."""
import sys, os, re, time, json, signal, subprocess, shutil, threading, atexit, random, resource, glob
tree, node, out, helper, btm = [os.path.abspath(a) for a in sys.argv[1:6]]
LABELS = sys.argv[6:]
ADDR, STORAGE, NATIVE, JMX = '127.0.41.1', 7011, 9143, 7211
NT = [os.path.join(tree, 'bin/nodetool'), '-p', str(JMX)]
PIDF = os.path.join(node, 'cassandra.pid')
BM = os.path.join(tree, 'build/lib/jars/byteman-4.0.20.jar')
SMALL = os.environ.get('STAGE4_SMALL')
resource.setrlimit(resource.RLIMIT_NOFILE, (100000, 100000))
os.makedirs(out, exist_ok=True)
LOG = open(os.path.join(out, 'session.log'), 'a')
def log(*a):
    m = '[%s] %s' % (time.strftime('%FT%T%z'), ' '.join(str(x) for x in a)); print(m, flush=True); LOG.write(m + '\n'); LOG.flush()
def sh(cmd, check=True, timeout=300, quiet=False):
    t0 = time.time()
    p = subprocess.run(cmd, shell=isinstance(cmd, str), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    if not quiet: log('+', cmd if isinstance(cmd, str) else ' '.join(cmd), '->', p.returncode, '(%.1fs)' % (time.time() - t0), p.stdout.strip()[-300:])
    if check and p.returncode: raise RuntimeError('failed: %s\n%s' % (cmd, p.stdout))
    return p.stdout
def pid():
    try: return int(open(PIDF).read().strip())
    except Exception: return None
def alive(p):
    try: os.kill(p, 0); return True
    except OSError: return False
def stop_node():
    p = pid()
    if p and alive(p):
        log('stopping node pid', p)
        try: sh(NT + ['drain'], check=False, timeout=240)
        except Exception as e: log('drain error', e)
        try:
            os.kill(p, signal.SIGTERM)
            for _ in range(90):
                if not alive(p): break
                time.sleep(1)
            else: os.kill(p, signal.SIGKILL)
        except OSError: pass
    log('node pid alive after stop:', bool(p and alive(p)))
atexit.register(stop_node)

def setkey(txt, k, v):
    if re.search(r'^%s:' % k, txt, re.M): return re.sub(r'^%s:.*$' % k, '%s: %s' % (k, v), txt, flags=re.M)
    return txt + '\n%s: %s\n' % (k, v)

def parse(label):
    m = re.match(r'^([AB])(\d+)(r\d+)?$', label); assert m, label
    return m.group(1), '%dMiB' % int(m.group(2))

def setup_node(label, hs):
    shutil.rmtree(node, ignore_errors=True)
    for d in ('data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw', 'logs'): os.makedirs(os.path.join(node, d))
    shutil.copytree(os.path.join(tree, 'conf'), os.path.join(node, 'conf'))
    envsh = os.path.join(node, 'conf/cassandra-env.sh'); t = open(envsh).read()
    assert 'JMX_PORT="7199"' in t; open(envsh, 'w').write(t.replace('JMX_PORT="7199"', 'JMX_PORT="%d"' % JMX))
    y = os.path.join(node, 'conf/cassandra.yaml'); txt = open(y).read()
    txt = re.sub(r'^listen_address:.*$', 'listen_address: ' + ADDR, txt, flags=re.M); txt = re.sub(r'^rpc_address:.*$', 'rpc_address: ' + ADDR, txt, flags=re.M)
    txt = re.sub(r'- seeds: ".*"', '- seeds: "%s:%d"' % (ADDR, STORAGE), txt)
    for k, v in (('storage_port', STORAGE), ('native_transport_port', NATIVE), ('cluster_name', "'tp41-stage4'"), ('auto_snapshot', 'false'), ('cdc_enabled', 'false'),
                 ('commitlog_directory', node + '/commitlog'), ('hints_directory', node + '/hints'), ('saved_caches_directory', node + '/saved_caches'), ('cdc_raw_directory', node + '/cdc_raw'),
                 ('memtable_allocation_type', 'heap_buffers'), ('memtable_heap_space', hs),
                 ('read_request_timeout', '60000ms'), ('write_request_timeout', '60000ms'), ('range_request_timeout', '60000ms'), ('native_transport_timeout', '60s')):
        txt = setkey(txt, k, v)
    txt = re.sub(r'^data_file_directories:\n(\s+-.*\n)?', '', txt, flags=re.M)
    txt += '\ndata_file_directories:\n    - %s/data\n' % node
    open(y, 'w').write(txt)

def start_node(label, L):
    env = dict(os.environ, MAX_HEAP_SIZE='2G', HEAP_NEWSIZE='512M', CASSANDRA_CONF=node + '/conf', CASSANDRA_LOG_DIR=node + '/logs',
               JVM_EXTRA_OPTS='-javaagent:%s=listener:false,boot:%s,boot:%s,script:%s -Dstage4.tp.events=%s/tp-events.txt -Dstage4.tp.stats=%s/tp-stats.txt -Dstage4.tp.phase=%s/phase.txt' % (BM, BM, helper, btm, L, L, L))
    if os.path.exists(PIDF): os.remove(PIDF)
    open(L + '/phase.txt', 'w').write('idle')
    log('start node label', label)
    subprocess.run([os.path.join(tree, 'bin/cassandra'), '-p', PIDF], env=env, stdout=open(node + '/logs/stdout.log', 'w'), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=120)
    t0 = time.time()
    while time.time() - t0 < 400:
        time.sleep(4)
        p = pid()
        if not p or not alive(p): raise RuntimeError('daemon died during start')
        st = subprocess.run(NT + ['status'], stdout=subprocess.PIPE, text=True, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL).stdout
        sb = subprocess.run(NT + ['statusbinary'], stdout=subprocess.PIPE, text=True, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL).stdout.strip()
        if re.search(r'^UN', st, re.M) and sb == 'running': break
    else: raise RuntimeError('node did not come up')
    p = pid(); log('node up pid', p, 'in %.0fs' % (time.time() - t0))
    ev = os.path.join(L, 'evidence'); os.makedirs(ev, exist_ok=True)
    cmd = open('/proc/%d/cmdline' % p, 'rb').read().replace(b'\0', b' ').decode()
    open(ev + '/cmdline.txt', 'w').write(cmd)
    open(ev + '/yaml-keys.txt', 'w').write('\n'.join(l for l in open(node + '/conf/cassandra.yaml').read().splitlines() if re.match(r'(partitioner|memtable_|listen_address|rpc_address|storage_port|native_transport_port|data_file_directories|commitlog_directory)', l)))
    return p

def mx(bean, attr):
    return subprocess.run(NT + ['sjk', 'mx', '-mg', '-b', bean, '-f', attr], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL, timeout=120).stdout.strip()
def tbl(attr):
    o = mx('org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=t,name=' + attr, 'Value')
    return o.splitlines()[-1] if o else ''
def acct(tag, rec):
    d = dict(tag=tag, t=int(time.time() * 1000))
    for a in ('MemtableOnHeapDataSize', 'MemtableOffHeapDataSize', 'MemtableLiveDataSize', 'MemtableColumnsCount'):
        d[a] = tbl(a)
    rec.append(d); log('acct', json.dumps(d)); return d
def tp_stats(L):
    try: return open(os.path.join(L, 'tp-stats.txt')).read().strip()
    except Exception: return None
def flush_lines():
    try: return [l.strip() for l in open(node + '/logs/system.log', errors='replace') if ('Enqueuing flush of' in l or 'Completed flushing' in l)]
    except Exception: return []
def is_t(l): return bool(re.search(r'(flush of t[,:\s]|ks\.t[,:\s]|/ks/t-|Memtable-t@)', l))

DRV = glob.glob(os.path.join(tree, 'lib/cassandra-driver-internal-only-*.zip'))[0]
sys.path.insert(0, DRV + '/cassandra-driver-3.29.0')
def connect():
    from cassandra.cluster import Cluster
    from cassandra.policies import DCAwareRoundRobinPolicy
    c = Cluster([ADDR], port=NATIVE, protocol_version=4, load_balancing_policy=DCAwareRoundRobinPolicy(local_dc='datacenter1'), token_metadata_enabled=False, connect_timeout=30)
    return c, c.connect()
def run_async(s, ps, gen, inflight=256, timeout=120):
    sem = threading.Semaphore(inflight); st = dict(ok=0, err=0, firsterr=None); lock = threading.Lock()
    def done(_):
        with lock: st['ok'] += 1
        sem.release()
    def bad(e):
        with lock: st['err'] += 1; st['firsterr'] = st['firsterr'] or str(e)[:300]
        sem.release()
    for a in gen:
        sem.acquire(); f = s.execute_async(ps, a, timeout=timeout); f.add_callbacks(done, bad)
    for _ in range(inflight): sem.acquire()
    return st

def wait_flushes(res, key, maxs=240):
    t0 = time.time(); last = None; stable = 0
    while time.time() - t0 < maxs:
        fl = [l for l in flush_lines() if is_t(l)]
        enq = sum('Enqueuing' in l for l in fl); comp = sum('Completed flushing' in l for l in fl)
        if enq == comp and (enq, comp) == last: stable += 1
        else: stable = 0
        last = (enq, comp)
        if stable >= 2: break
        time.sleep(4)
    res[key] = dict(enqueued=last[0], completed=last[1]); log('flush lines', key, res[key])

def run_label(label):
    kind, hs = parse(label)
    L = os.path.join(out, label); shutil.rmtree(L, ignore_errors=True); os.makedirs(L)
    res = dict(label=label, kind=kind, heap_space=hs, accounting=[], samples=[])
    setup_node(label, hs); p = start_node(label, L)
    time.sleep(5); res['stats_baseline'] = tp_stats(L); log('baseline', res['stats_baseline'])
    c, s = connect()
    s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    s.execute("CREATE TABLE ks.t (pk blob, ck blob, v blob, PRIMARY KEY (pk, ck)) WITH memtable = 'trie'")
    open(L + '/schema.txt', 'w').write(sh(['bash', '-c', 'echo "DESCRIBE TABLE ks.t" | %s/bin/cqlsh %s %d 2>&1 | head -40' % (tree, ADDR, NATIVE)], check=False, quiet=True))
    ins = s.prepare('INSERT INTO ks.t (pk, ck, v) VALUES (?, ?, ?)')
    rnd = random.Random(41)
    n = int(SMALL) if SMALL else (1000000 if kind == 'A' else 2000)
    pklen = 16 if kind == 'A' else 60000
    jfr = os.path.join(L, 'tp.jfr')
    sh(['jcmd', str(p), 'JFR.start', 'name=tp', 'settings=profile', 'filename=' + jfr], check=False)
    # sampler: MemtableOnHeapDataSize every ~5 s during the write phase
    stop = threading.Event()
    def sampler():
        while not stop.is_set():
            try: res['samples'].append(dict(t=int(time.time() * 1000), onheap=tbl('MemtableOnHeapDataSize')))
            except Exception as e: res['samples'].append(dict(t=int(time.time() * 1000), err=str(e)[:100]))
            stop.wait(3)
    th = threading.Thread(target=sampler, daemon=True); th.start()
    open(L + '/phase.txt', 'w').write('write'); t_w = time.time()
    def gen():
        for i in range(n):
            yield (rnd.randbytes(pklen), i.to_bytes(16, 'big'), b'v' * 64)
    st = run_async(s, ins, gen())
    res['write'] = dict(st, rows=n, pklen=pklen, seconds=round(time.time() - t_w, 1)); log('write', res['write'])
    stop.set(); th.join(timeout=60)
    wait_flushes(res, 'flushes_after_write')
    res['stats_after_write'] = tp_stats(L)
    acct('before_scan', res['accounting'])
    # scan while the memtable still holds data (B3i.2)
    open(L + '/phase.txt', 'w').write('scan'); t_s = time.time()
    from cassandra.query import SimpleStatement
    q = SimpleStatement('SELECT pk, ck FROM ks.t', fetch_size=(5000 if kind == 'A' else 100))
    rows = 0; err = None
    try:
        for _ in s.execute(q, timeout=240): rows += 1
    except Exception as e: err = str(e)[:300]
    res['scan'] = dict(rows=rows, err=err, seconds=round(time.time() - t_s, 1)); log('scan', res['scan'])
    time.sleep(3); res['stats_after_scan'] = tp_stats(L)
    acct('after_scan', res['accounting'])
    open(L + '/phase.txt', 'w').write('flush')
    sh(NT + ['flush', 'ks', 't'], check=False, timeout=600)
    wait_flushes(res, 'flushes_after_explicit')
    open(L + '/phase.txt', 'w').write('post'); time.sleep(4)
    res['stats_after_flush'] = tp_stats(L)
    acct('after_flush', res['accounting'])
    sh(['jcmd', str(p), 'JFR.dump', 'name=tp', 'filename=' + jfr], check=False)
    res['flush_log'] = [l for l in flush_lines()]
    open(L + '/flush-lines.txt', 'w').write('\n'.join(res['flush_log']) + '\n')
    sl = open(node + '/logs/system.log', errors='replace').read()
    res['errors'] = dict(log_ERROR_lines=len(re.findall(r'^ERROR', sl, re.M)), log_WARN_lines=len(re.findall(r'^WARN', sl, re.M)))
    open(L + '/system.log.errors.txt', 'w').write('\n'.join(l for l in sl.splitlines() if l.startswith('ERROR'))[:20000])
    shutil.copy(node + '/logs/system.log', L + '/system.log')
    c.shutdown()
    time.sleep(3); res['stats_final'] = tp_stats(L)
    json.dump(res, open(L + '/result.json', 'w'), indent=1)
    stop_node()
    # JFR cross-check (secondary): count allocation events whose stack names TriePathReconstructor
    try:
        o = subprocess.run(['jfr', 'print', '--events', 'jdk.ObjectAllocationSample,jdk.ObjectAllocationOutsideTLAB', '--stack-depth', '8', jfr], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=600).stdout
        ev = o.split('\n\n'); hit = [e for e in ev if 'TriePathReconstructor' in e]
        open(L + '/jfr-tp-events.txt', 'w').write('\n\n'.join(hit[:200]))
        res['jfr'] = dict(events=len(ev), tp_events=len(hit))
    except Exception as e: res['jfr'] = dict(err=str(e)[:200])
    log('jfr', res['jfr']); json.dump(res, open(L + '/result.json', 'w'), indent=1)
    os.remove(jfr) if os.path.exists(jfr) else None
    shutil.rmtree(node + '/data', ignore_errors=True); shutil.rmtree(node + '/commitlog', ignore_errors=True)
    log('label done', label)

for lab in LABELS:
    run_label(lab)
log('all labels done')
