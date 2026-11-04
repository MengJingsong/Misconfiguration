#!/usr/bin/env python3
"""Cluster tier driver (case file B3 as amended B3i).
Usage: cluster-run.py <node-tree> <nodedir> <outdir> <driver-dir> <helper-jar> <btm-file> <label>...
Labels: hb64 hb256 hb512 oo64 (ByteOrderedPartitioner, trie memtable, comb) ; m3 (Murmur3, filed workload) ; sl (BOP, skiplist, comb).
One single-node Cassandra on 127.0.0.88 (storage 7088, native 9088, JMX 7288); a fresh data directory per label. Stops the node on any exit; kills by PID only.
env STAGE4_SMALL=<n> shrinks the filler (instrument shakedown only)."""
import sys, os, re, time, json, signal, subprocess, shutil, threading, atexit, random, resource
tree, node, out, drv, helper, btm = [os.path.abspath(a) for a in sys.argv[1:7]]
LABELS = sys.argv[7:]
ADDR, STORAGE, NATIVE, JMX = '127.0.0.88', 7088, 9088, 7288
NT = [os.path.join(tree, 'bin/nodetool'), '-p', str(JMX)]
PIDF = os.path.join(node, 'cassandra.pid')
BM = os.path.join(tree, 'build/lib/jars/byteman-4.0.20.jar')
FILLER = int(os.environ.get('STAGE4_SMALL', '400000'))
SCAN_SECONDS = int(os.environ.get('STAGE4_SCAN_SECONDS', '90'))
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
CFG = {  # label -> (partitioner, memtable table option, allocation type, heap space, offheap space)
 'hb64':  ('ByteOrderedPartitioner', 'trie', 'heap_buffers', '64MiB', None),
 'hb256': ('ByteOrderedPartitioner', 'trie', 'heap_buffers', '256MiB', None),
 'hb512': ('ByteOrderedPartitioner', 'trie', 'heap_buffers', '512MiB', None),
 'oo64':  ('ByteOrderedPartitioner', 'trie', 'offheap_objects', '64MiB', '64MiB'),
 'm3':    ('Murmur3Partitioner', 'trie', 'heap_buffers', '256MiB', None),
 'sl':    ('ByteOrderedPartitioner', None, 'heap_buffers', '256MiB', None),
}
def setup_node(label):
    part, mt, alloc, hs, ohs = CFG[label]
    shutil.rmtree(node, ignore_errors=True)
    for d in ('data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw', 'logs'): os.makedirs(os.path.join(node, d))
    shutil.copytree(os.path.join(tree, 'conf'), os.path.join(node, 'conf'))
    envsh = os.path.join(node, 'conf/cassandra-env.sh'); t = open(envsh).read()
    assert 'JMX_PORT="7199"' in t; open(envsh, 'w').write(t.replace('JMX_PORT="7199"', 'JMX_PORT="%d"' % JMX))
    y = os.path.join(node, 'conf/cassandra.yaml'); txt = open(y).read()
    txt = re.sub(r'^listen_address:.*$', 'listen_address: ' + ADDR, txt, flags=re.M); txt = re.sub(r'^rpc_address:.*$', 'rpc_address: ' + ADDR, txt, flags=re.M)
    txt = re.sub(r'- seeds: ".*"', '- seeds: "%s:%d"' % (ADDR, STORAGE), txt)
    for k, v in (('storage_port', STORAGE), ('native_transport_port', NATIVE), ('cluster_name', "'bt-stage4'"), ('auto_snapshot', 'false'), ('cdc_enabled', 'false'),
                 ('commitlog_directory', node + '/commitlog'), ('hints_directory', node + '/hints'), ('saved_caches_directory', node + '/saved_caches'), ('cdc_raw_directory', node + '/cdc_raw'),
                 ('partitioner', 'org.apache.cassandra.dht.' + part), ('memtable_allocation_type', alloc), ('memtable_heap_space', hs),
                 ('read_request_timeout', '60000ms'), ('write_request_timeout', '60000ms'), ('native_transport_timeout', '60s')):
        txt = setkey(txt, k, v)
    if ohs: txt = setkey(txt, 'memtable_offheap_space', ohs)
    if part.startswith('Byte'):   # BytesToken does not support token allocation (found by the first node start)
        txt = setkey(txt, 'num_tokens', 1); txt = re.sub(r'^allocate_tokens_for_local_replication_factor:.*$', '# allocate_tokens_for_local_replication_factor (off for BOP)', txt, flags=re.M)
    txt = re.sub(r'^data_file_directories:\n(\s+-.*\n)?', '', txt, flags=re.M)
    txt += '\ndata_file_directories:\n    - %s/data\n' % node
    open(y, 'w').write(txt)
def start_node(label):
    env = dict(os.environ, MAX_HEAP_SIZE='1G', HEAP_NEWSIZE='256M', CASSANDRA_CONF=node + '/conf', CASSANDRA_LOG_DIR=node + '/logs',
               JVM_EXTRA_OPTS='-javaagent:%s=listener:false,boot:%s,boot:%s,script:%s -Dstage4.bt.stats=%s/%s/bt-stats.txt' % (BM, BM, helper, btm, out, label))
    if os.path.exists(PIDF): os.remove(PIDF)
    os.makedirs(os.path.join(out, label), exist_ok=True)
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
    ev = os.path.join(out, label, 'evidence'); os.makedirs(ev, exist_ok=True)
    open(ev + '/cmdline.txt', 'w').write(open('/proc/%d/cmdline' % p, 'rb').read().replace(b'\0', b' ').decode())
    open(ev + '/yaml-keys.txt', 'w').write('\n'.join(l for l in open(node + '/conf/cassandra.yaml').read().splitlines() if re.match(r'(partitioner|memtable_|listen_address|rpc_address|storage_port|native_transport_port)', l)))
    return p

def mx(bean, attr):
    o = subprocess.run(NT + ['sjk', 'mx', '-mg', '-b', bean, '-f', attr], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL, timeout=120).stdout.strip()
    return o
def acct(tag, label, rec):
    d = dict(tag=tag, t=int(time.time() * 1000))
    for a in ('MemtableOnHeapDataSize', 'MemtableOffHeapDataSize', 'MemtableLiveDataSize'):
        d[a] = mx('org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=t,name=' + a, 'Value').splitlines()[-1]
    rec.append(d); log('acct', json.dumps(d)); return d
def bt_stats(label):
    try: return open(os.path.join(out, label, 'bt-stats.txt')).read().strip()
    except Exception: return None
def int_hist(p):
    o = subprocess.run(['jcmd', str(p), 'GC.class_histogram'], stdout=subprocess.PIPE, text=True, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=120).stdout
    m = [l for l in o.splitlines() if len(l.split()) > 3 and l.split()[3] == '[I']
    return m[0].strip() if m else 'NOMATCH: ' + o[:200].replace(chr(10), ' | ')
def flush_lines(): 
    try: return [l for l in open(node + '/logs/system.log', errors='replace') if 'Enqueuing flush of' in l or 'Completed flushing' in l]
    except Exception: return []

sys.path.insert(0, os.path.join(drv, 'cassandra-driver-3.29.0'))
def connect():
    from cassandra.cluster import Cluster
    from cassandra.policies import DCAwareRoundRobinPolicy
    c = Cluster([ADDR], port=NATIVE, protocol_version=5, load_balancing_policy=DCAwareRoundRobinPolicy(local_dc='datacenter1'), token_metadata_enabled=False, connect_timeout=30)
    return c, c.connect()
def run_async(s, ps, argl, inflight=256, timeout=120):
    sem = threading.Semaphore(inflight); st = dict(ok=0, err=0, firsterr=None); lock = threading.Lock()
    def done(_):
        with lock: st['ok'] += 1
        sem.release()
    def bad(e):
        with lock: st['err'] += 1; st['firsterr'] = st['firsterr'] or str(e)[:300]
        sem.release()
    for a in argl:
        sem.acquire(); f = s.execute_async(ps, a, timeout=timeout); f.add_callbacks(done, bad)
    for _ in range(inflight): sem.acquire()
    return st

def run_label(label):
    part, mt, alloc, hs, ohs = CFG[label]
    bop = part.startswith('Byte')
    L = os.path.join(out, label); os.makedirs(L, exist_ok=True)
    res = dict(label=label, cfg=CFG[label], accounting=[], scan_series=[], hist_series=[], errors={})
    setup_node(label); p = start_node(label)
    res['stats_after_start'] = bt_stats(label)
    c, s = connect()
    s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    s.execute("CREATE TABLE ks.t (pk blob, ck blob, v blob, PRIMARY KEY (pk, ck))" + (" WITH memtable = '%s'" % mt if mt else ''))
    open(L + '/schema.txt', 'w').write(sh(['bash', '-c', 'echo "DESCRIBE TABLE ks.t" | %s/bin/cqlsh %s %d 2>&1 | head -40' % (tree, ADDR, NATIVE)], check=False, quiet=True))
    ins = s.prepare('INSERT INTO ks.t (pk, ck, v) VALUES (?, ?, ?)')
    rnd = random.Random(11)
    t_fill = time.time()
    if bop:   # filler: 16-byte random pk (first byte 0x20..0xEF), ck 8 bytes, v 1000 bytes
        def gen():
            for i in range(FILLER):
                pk = bytes([rnd.randint(0x20, 0xEF)]) + bytes(rnd.getrandbits(8) for _ in range(15))
                yield (pk, i.to_bytes(8, 'big'), b'x' * 1000)
        st = run_async(s, ins, gen())
    else:     # m3: filed workload, pk 1000 random bytes, ck 100, v 16
        n = int(os.environ.get('STAGE4_SMALL_M3', '20000'))
        def gen():
            for i in range(n):
                yield (rnd.randbytes(1000), rnd.randbytes(100), rnd.randbytes(16))
        st = run_async(s, ins, gen())
    res['filler'] = dict(st, seconds=round(time.time() - t_fill, 1)); log('filler', res['filler'])
    # wait for flushes to finish
    t0 = time.time(); last = None
    while time.time() - t0 < 180:
        fl = [l for l in flush_lines() if 'flush of ks.t,' in l or '/data/ks/t-' in l]; enq = sum('Enqueuing' in l for l in fl); comp = sum('Completed flushing' in l for l in fl)
        if (enq, comp) == last and enq >= 0: 
            if enq == comp: break
        last = (enq, comp); time.sleep(5)
    log('flush lines after filler: enqueued', enq, 'completed', comp)
    if bop:   # comb D=1000 -- first empty the residual filler memtable so that the comb enters an empty memtable (B3i.9)
        sh(NT + ['flush', 'ks', 't'], check=False, timeout=300)
        rows = [(bytes([0x10]) * d + bytes([0x11]), (0).to_bytes(8, 'big'), b'y' * 16) for d in range(1000)] + [(bytes([0x10]) * 1000, (0).to_bytes(8, 'big'), b'y' * 16)]
        st = run_async(s, ins, rows); res['comb'] = st; log('comb', st)
    acct('before_scan', label, res['accounting'])
    res['stats_before_scan'] = bt_stats(label)
    # scan phase
    stop = threading.Event(); cnt = dict(scans=0, rows=0, err=0, firsterr=None, badrows=0); lock = threading.Lock()
    from cassandra.query import SimpleStatement
    if bop: q = SimpleStatement("SELECT pk FROM ks.t WHERE token(pk) >= token(0x10) AND token(pk) < token(0x12)", fetch_size=5000); expect = 1001
    else: q = SimpleStatement("SELECT * FROM ks.t", fetch_size=1000); expect = None
    def worker():
        while not stop.is_set():
            try:
                n = sum(1 for _ in s.execute(q, timeout=60))
                with lock:
                    cnt['scans'] += 1; cnt['rows'] += n
                    if expect is not None and n != expect: cnt['badrows'] += 1
            except Exception as e:
                with lock: cnt['err'] += 1; cnt['firsterr'] = cnt['firsterr'] or str(e)[:300]
                time.sleep(0.5)
    ths = [threading.Thread(target=worker, daemon=True) for _ in range(16)]
    t_scan = time.time()
    for t in ths: t.start()
    n = 0
    while time.time() - t_scan < SCAN_SECONDS:
        time.sleep(10); n += 1
        res['scan_series'].append(dict(t=int(time.time() * 1000), stats=bt_stats(label), scans=cnt['scans']))
        res['hist_series'].append(dict(t=int(time.time() * 1000), int_arrays=int_hist(p)))
        if n % 3 == 0: acct('during_scan', label, res['accounting'])
    stop.set()
    for t in ths: t.join(timeout=90)
    res['scan'] = dict(cnt, seconds=round(time.time() - t_scan, 1)); log('scan', res['scan'])
    res['stats_after_scan'] = bt_stats(label)
    acct('after_scan', label, res['accounting'])
    sh(NT + ['flush', 'ks', 't'], check=False, timeout=300)
    time.sleep(4)
    res['stats_after_flush'] = bt_stats(label)
    acct('after_flush', label, res['accounting'])
    res['flush_log'] = [l.strip() for l in flush_lines()]
    open(L + '/flush-lines.txt', 'w').write('\n'.join(res['flush_log']) + '\n')
    sl = open(node + '/logs/system.log', errors='replace').read()
    res['errors']['log_ERROR_lines'] = len(re.findall(r'^ERROR', sl, re.M)); res['errors']['log_WARN_lines'] = len(re.findall(r'^WARN', sl, re.M))
    open(L + '/system.log.errors.txt', 'w').write('\n'.join(l for l in sl.splitlines() if l.startswith('ERROR'))[:20000])
    shutil.copy(node + '/logs/system.log', L + '/system.log')
    c.shutdown()
    time.sleep(3); res['stats_final'] = bt_stats(label)
    json.dump(res, open(L + '/result.json', 'w'), indent=1)
    stop_node()
    shutil.rmtree(node + '/data', ignore_errors=True); shutil.rmtree(node + '/commitlog', ignore_errors=True)
    log('label done', label)

for lab in LABELS:
    run_label(lab)
log('all labels done')
