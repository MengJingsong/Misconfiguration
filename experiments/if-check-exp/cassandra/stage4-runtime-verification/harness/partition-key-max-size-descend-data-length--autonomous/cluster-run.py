#!/usr/bin/env python3
"""Cluster-tier driver for partition-key-max-size-descend-data-length--autonomous (B3, with B3i amendments).

One invocation = one node start (a "label"): builds a private conf/data tree under <out>, starts a one-node ring on
127.0.31.1 (ports 7131/9131, JMX 7331) so as not to touch other runs on the host, runs the arms, stops the node.

  cluster-run.py --src SRC --out OUT --label h64 --heap-space 64 --mode arms [--quick]
  cluster-run.py --src SRC --out OUT --label pc  --heap-space 16 --mode poscontrol

Arms (mode arms): control K=32, then K in 100,127,128,200,1000,16000,60000 (N=5), 60000 (N=1), 65535 (N=5), 65535 (N=1),
control K=32 again. Per arm: a fresh table WITH memtable='trie' (shards=1 in cassandra.yaml), int[] bytes from
GC.class_histogram (full GC) and the memtable charge from JMX before the writes, after the writes (no flush yet), and after
nodetool flush. Everything is logged to <out>/command.log; results to <out>/arms.csv (or poscontrol.csv).
"""
import argparse, atexit, csv, glob, os, random, re, shutil, signal, subprocess, sys, time

ap = argparse.ArgumentParser()
ap.add_argument('--src', required=True); ap.add_argument('--out', required=True); ap.add_argument('--label', required=True)
ap.add_argument('--heap-space', type=int, required=True); ap.add_argument('--mode', choices=['arms', 'poscontrol'], required=True)
ap.add_argument('--quick', action='store_true')
A = ap.parse_args()

SRC, OUT = os.path.abspath(A.src), os.path.abspath(A.out)
IP, STORAGE, NATIVE, JMX = '127.0.31.1', 7131, 9131, 7331
CONF = os.path.join(OUT, 'conf')
LOG = os.path.join(OUT, 'logs')
os.makedirs(OUT, exist_ok=True)
CMDLOG = open(os.path.join(OUT, 'command.log'), 'a')
node = {'p': None}

def log(msg):
    line = '%s %s' % (time.strftime('%FT%TZ', time.gmtime()), msg)
    CMDLOG.write(line + '\n'); CMDLOG.flush(); print(line, flush=True)

def sh(cmd, timeout=300, env=None, check=True, show=400):
    t0 = time.time()
    r = subprocess.run(cmd, shell=isinstance(cmd, str), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout,
                       env=env, universal_newlines=True, stdin=subprocess.DEVNULL)
    out = r.stdout
    log('$ %s  [rc=%d, %.1fs]\n%s' % (cmd if isinstance(cmd, str) else ' '.join(cmd), r.returncode, time.time() - t0, out[:show].rstrip()))
    if check and r.returncode != 0:
        raise RuntimeError('command failed: %s' % cmd)
    return out

def setup_conf():
    if os.path.exists(CONF): shutil.rmtree(CONF)
    shutil.copytree(os.path.join(SRC, 'conf'), CONF)
    for d in ('data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw', 'logs'):
        os.makedirs(os.path.join(OUT, d), exist_ok=True)
    y = open(os.path.join(CONF, 'cassandra.yaml')).read()
    def rep(pat, new, count=1):
        nonlocal y
        y2, n = re.subn(pat, new, y, count=count, flags=re.M)
        if n == 0: raise RuntimeError('yaml pattern not found: %s' % pat)
        y = y2
    rep(r'^cluster_name:.*$', "cluster_name: 'pk-%s'" % A.label)
    rep(r'^listen_address:.*$', 'listen_address: %s' % IP)
    rep(r'^rpc_address:.*$', 'rpc_address: %s' % IP)
    rep(r'^storage_port:.*$', 'storage_port: %d' % STORAGE)
    rep(r'^native_transport_port:.*$', 'native_transport_port: %d' % NATIVE)
    rep(r'- seeds:.*$', '- seeds: "%s:%d"' % (IP, STORAGE))
    rep(r'^#?\s*memtable_heap_space:.*$', 'memtable_heap_space: %dMiB' % A.heap_space)
    if A.mode == 'poscontrol':
        rep(r'^#?\s*memtable_offheap_space:.*$', 'memtable_offheap_space: %dMiB' % A.heap_space)
    rep(r'^memtable_allocation_type:.*$', 'memtable_allocation_type: heap_buffers')
    rep(r'(    trie:\n      class_name: TrieMemtable\n)', r'\1      parameters:\n        shards: 1\n')
    y += '\ndata_file_directories:\n    - %s\ncommitlog_directory: %s\nhints_directory: %s\nsaved_caches_directory: %s\ncdc_raw_directory: %s\n' % (
        *(os.path.join(OUT, d) for d in ('data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw')),)
    open(os.path.join(CONF, 'cassandra.yaml'), 'w').write(y)
    e = open(os.path.join(CONF, 'cassandra-env.sh')).read()
    assert 'JMX_PORT="7199"' in e
    open(os.path.join(CONF, 'cassandra-env.sh'), 'w').write(e.replace('JMX_PORT="7199"', 'JMX_PORT="%d"' % JMX))
    log('conf written: ' + CONF)
    sh("grep -n 'memtable_heap_space\\|memtable_offheap_space\\|memtable_allocation_type\\|listen_address\\|rpc_address\\|storage_port\\|native_transport_port\\|shards\\|seeds:' %s/cassandra.yaml | grep -v '^[0-9]*:#'" % CONF, check=False, show=2000)

def alive():
    p = node['p']
    return p is not None and p.poll() is None

def node_pid():
    return node['p'].pid

def nodetool(*args, timeout=120, check=True):
    return sh([os.path.join(SRC, 'bin/nodetool'), '-h', '127.0.0.1', '-p', str(JMX)] + list(args), timeout=timeout, check=check)

def start_node():
    env = dict(os.environ, CASSANDRA_CONF=CONF, CASSANDRA_LOG_DIR=LOG, MAX_HEAP_SIZE='2G')
    cmd = 'ulimit -n 100000; cd %s; exec bin/cassandra -f -p %s/pid' % (SRC, OUT)
    stdout = open(os.path.join(OUT, 'node.stdout'), 'w')
    node['p'] = subprocess.Popen(['bash', '-c', cmd], env=env, stdout=stdout, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    log('node started, pid %d (MAX_HEAP_SIZE=2G, ulimit -n 100000, memtable_heap_space=%d MiB)' % (node['p'].pid, A.heap_space))
    t0 = time.time()
    while time.time() - t0 < 240:
        if not alive():
            raise RuntimeError('node died during start; see node.stdout / logs/system.log')
        time.sleep(5)
        out = sh([os.path.join(SRC, 'bin/nodetool'), '-h', '127.0.0.1', '-p', str(JMX), 'statusbinary'], check=False, timeout=60, show=100)
        if out.strip() == 'running':
            st = sh([os.path.join(SRC, 'bin/nodetool'), '-h', '127.0.0.1', '-p', str(JMX), 'status'], check=False, timeout=60, show=600)
            if re.search(r'^UN\s', st, re.M):
                log('node up in %.0fs' % (time.time() - t0))
                cmdline = open('/proc/%d/cmdline' % node['p'].pid, 'rb').read().replace(b'\0', b' ').decode()
                assert 'CassandraDaemon' in cmdline, cmdline[:200]
                open(os.path.join(OUT, 'java.cmdline'), 'w').write(cmdline)
                return
    raise RuntimeError('node did not come up in 240 s')

def stop_node():
    p = node['p']
    if p is None or p.poll() is not None:
        return
    log('stopping node pid %d (SIGTERM)' % p.pid)
    try: os.kill(p.pid, signal.SIGTERM)
    except ProcessLookupError: pass
    t0 = time.time()
    while p.poll() is None and time.time() - t0 < 90: time.sleep(1)
    if p.poll() is None:
        log('SIGKILL pid %d' % p.pid); os.kill(p.pid, signal.SIGKILL); p.wait()
    log('node stopped, rc=%s' % p.returncode)
atexit.register(stop_node)

def hist(tag):
    """GC.class_histogram (runs a full GC): bytes of int[] and counts of the trie objects."""
    out = sh(['jcmd', str(node_pid()), 'GC.class_histogram'], timeout=180, show=0)
    open(os.path.join(OUT, 'hist-%s.txt' % tag), 'w').write(''.join(l + '\n' for l in out.splitlines()[:40]) +
        ''.join(l + '\n' for l in out.splitlines() if re.search(r'InMemoryTrie|ApplyState|\[I\b', l)))
    m = re.search(r'^\s*\d+:\s+(\d+)\s+(\d+)\s+\[I\b', out, re.M)
    if not m: raise RuntimeError('no int[] row in histogram')
    cnt_as = re.search(r'^\s*\d+:\s+(\d+)\s+(\d+)\s+org\.apache\.cassandra\.db\.tries\.InMemoryTrie\$ApplyState\b', out, re.M)
    log('hist %s: int[] instances=%s bytes=%s ApplyState=%s' % (tag, m.group(1), m.group(2), cnt_as.group(1) if cnt_as else 'n/a'))
    return int(m.group(2)), (int(cnt_as.group(1)) if cnt_as else 0)

def jmx(table, name):
    bean = 'org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=%s,name=%s' % (table, name)
    out = nodetool('sjk', 'mx', '-mg', '-b', bean, '-f', 'Value', check=False)
    nums = re.findall(r'-?\d+(?:\.\d+)?', out)
    if not nums: raise RuntimeError('cannot parse JMX %s: %r' % (name, out[:200]))
    return int(float(nums[-1]))

def system_log():
    p = os.path.join(LOG, 'system.log')
    return open(p, errors='replace').read() if os.path.exists(p) else ''

def connect():
    zips = glob.glob(os.path.join(SRC, 'lib', 'cassandra-driver-internal-only-*.zip'))
    sys.path.insert(0, os.path.join(zips[0], 'cassandra-driver-' + re.search(r'-(\d+\.\d+\.\d+)\.zip$', zips[0]).group(1)))
    from cassandra.cluster import Cluster
    from cassandra.policies import DCAwareRoundRobinPolicy
    cl = Cluster([IP], port=NATIVE, protocol_version=4, load_balancing_policy=DCAwareRoundRobinPolicy(), token_metadata_enabled=False)
    s = cl.connect()
    log('driver connected')
    return cl, s

def rand_key(rnd, k):
    b = bytearray(rnd.getrandbits(8) for _ in range(k))
    for i in range(k):
        if b[i] in (0, 0xFE): b[i] = 0x41
    return bytes(b)

def arms():
    cl, s = connect()
    s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
    plan = [('c32-first', 32, 5), ('K100', 100, 5), ('K127', 127, 5), ('K128', 128, 5), ('K200', 200, 5), ('K1000', 1000, 5),
            ('K16000', 16000, 5), ('K60000-N5', 60000, 5), ('K60000-N1', 60000, 1), ('K65535-N5', 65535, 5), ('K65535-N1', 65535, 1),
            ('c32-last', 32, 5)]
    if A.quick: plan = [('c32-first', 32, 5), ('K200', 200, 5), ('K1000', 1000, 5)]
    rows = []
    fn = os.path.join(OUT, 'arms.csv')
    cols = ['arm', 'K', 'N', 'table', 'int_pre', 'int_post', 'int_flush', 'applystate_pre', 'applystate_post', 'applystate_flush',
            'onheap_pre', 'onheap_post', 'offheap_pre', 'offheap_post', 'cols_post', 'flush_logged_before_explicit', 'write_s']
    with open(fn, 'w', newline='') as f:
        w = csv.DictWriter(f, cols); w.writeheader()
        for i, (arm, K, N) in enumerate(plan):
            t = 't%02d' % i
            s.execute("CREATE TABLE ks.%s (k blob PRIMARY KEY, v int) WITH memtable = 'trie'" % t)
            ins = s.prepare('INSERT INTO ks.%s (k, v) VALUES (?, ?)' % t)
            time.sleep(1)
            row = {'arm': arm, 'K': K, 'N': N, 'table': t}
            row['int_pre'], row['applystate_pre'] = hist('%s-pre' % arm)
            row['onheap_pre'] = jmx(t, 'MemtableOnHeapDataSize'); row['offheap_pre'] = jmx(t, 'MemtableOffHeapDataSize')
            rnd = random.Random(1000 * K + N + i)
            t0 = time.time()
            for _ in range(N):
                s.execute(ins, (rand_key(rnd, K), 1), timeout=60)
            row['write_s'] = round(time.time() - t0, 2)
            row['int_post'], row['applystate_post'] = hist('%s-post' % arm)
            row['onheap_post'] = jmx(t, 'MemtableOnHeapDataSize'); row['offheap_post'] = jmx(t, 'MemtableOffHeapDataSize')
            row['cols_post'] = jmx(t, 'MemtableColumnsCount')
            row['flush_logged_before_explicit'] = len(re.findall(r'Enqueuing flush of ks\.%s,' % t, system_log()))
            nodetool('flush', 'ks', t)
            time.sleep(2)
            row['int_flush'], row['applystate_flush'] = hist('%s-flush' % arm)
            log('ARM %s' % row)
            w.writerow(row); f.flush()
    cl.shutdown()

def poscontrol():
    cl, s = connect()
    s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
    s.execute("CREATE TABLE ks.pc (k blob PRIMARY KEY, v blob) WITH memtable = 'trie'")
    ins = s.prepare('INSERT INTO ks.pc (k, v) VALUES (?, ?)')
    time.sleep(1)
    rnd = random.Random(99)
    int_pre, as_pre = hist('pc-pre')
    fn = os.path.join(OUT, 'poscontrol.csv')
    first_flush = None
    with open(fn, 'w', newline='') as f:
        w = csv.writer(f); w.writerow(['writes', 'onheap', 'enqueued_flush_lines', 'reason_memtable_limit', 'int_bytes'])
        n = 0
        while n < 400:
            for _ in range(10):
                s.execute(ins, (rand_key(rnd, 32), bytes(rnd.getrandbits(8) for _ in range(100 * 1024))), timeout=60)
                n += 1
            time.sleep(1)
            on = jmx('pc', 'MemtableOnHeapDataSize')
            lg = system_log()
            fl = re.findall(r'Enqueuing flush of ks\.pc, Reason: (\w+)', lg)
            w.writerow([n, on, len(fl), 'MEMTABLE_LIMIT' in fl, ''])
            f.flush()
            log('POSCONTROL writes=%d onheap=%d flushes=%s' % (n, on, fl))
            if fl:
                first_flush = (n, on); break
    int_post, as_post = hist('pc-post')
    open(os.path.join(OUT, 'poscontrol.summary'), 'w').write('int_pre=%d int_post=%d applystate_pre=%d applystate_post=%d first_flush=%s\n' % (int_pre, int_post, as_pre, as_post, first_flush))
    open(os.path.join(OUT, 'poscontrol.flushlines'), 'w').write(''.join(l + '\n' for l in system_log().splitlines() if 'Enqueuing flush of ks.pc' in l))
    cl.shutdown()

try:
    setup_conf()
    start_node()
    (arms if A.mode == 'arms' else poscontrol)()
    log('DONE label=%s' % A.label)
except BaseException as e:
    log('FAILED: %r' % (e,))
    stop_node()
    raise
finally:
    stop_node()
    left = subprocess.run("ps -eo pid,cmd | grep '[C]assandraDaemon' | grep -- '%s' | cut -c1-80" % OUT, shell=True, stdout=subprocess.PIPE, universal_newlines=True).stdout
    log('leftover processes for this run: %r' % left)
