#!/usr/bin/env python3
"""Cluster tier driver (case file B3 as amended B3i). Usage: cluster-run.py <nodetree> <nodedir> <outdir> <driver-dir> <sampler-dir> [arms...]
Arms (default all, in order): A A2 B K64 K128 K256 K512 hb.  One single-node Cassandra on 127.0.0.31 with its own ports, restarted per arm with a fresh data directory.
Reading sources: JmxSampler (100 ms: RssAnon of the node PID, AllMemtablesOffHeapSize, MemtableOffHeapSize, OverSizedMutations) and per-row client results.
Stops the node on any exit; kills by PID only. Never runs ant."""
import sys, os, re, time, json, signal, subprocess, shutil, atexit, resource
tree, node, out, drv, smp = [os.path.abspath(a) for a in sys.argv[1:6]]
ARMS = sys.argv[6:] or ['A', 'A2', 'B', 'K64', 'K128', 'K256', 'K512', 'hb']
ADDR, STORAGE, NATIVE, JMX = '127.0.0.31', 7031, 9031, 7331
NT = [os.path.join(tree, 'bin/nodetool'), '-p', str(JMX)]
PIDF = os.path.join(node, 'cassandra.pid')
MiB = 1 << 20
resource.setrlimit(resource.RLIMIT_NOFILE, (100000, 100000))
os.makedirs(out, exist_ok=True)
LOG = open(os.path.join(out, 'session.log'), 'a')
SCALE = float(os.environ.get('STAGE4_SCALE', '1'))      # shakedown switch only: scales row counts down
def nrows(n): return max(1, int(n * SCALE))
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
SAMPLER = [None]
def stop_sampler():
    if SAMPLER[0] and SAMPLER[0].poll() is None:
        SAMPLER[0].terminate()
        try: SAMPLER[0].wait(10)
        except Exception: SAMPLER[0].kill()
def stop_node():
    stop_sampler()
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
# per-arm yaml values; everything else is common
COMMON = {'native_transport_max_request_data_in_flight': '512MiB', 'native_transport_max_request_data_in_flight_per_ip': '256MiB',
          'memtable_heap_space': '256MiB', 'write_request_timeout': '60000ms', 'native_transport_timeout': '60s', 'request_timeout': '60000ms'}
CFG = {  # label: (allocation type, offheap MiB, frame, max_mutation or None, commitlog segment or None)
    'A':    ('offheap_objects', 256, '16MiB', None, None),
    'A2':   ('offheap_objects', 256, '64MiB', None, None),
    'B':    ('offheap_objects', 256, '128MiB', '64MiB', '128MiB'),
    'K64':  ('offheap_objects', 64, '16MiB', None, None),
    'K128': ('offheap_objects', 128, '16MiB', None, None),
    'K256': ('offheap_objects', 256, '16MiB', None, None),
    'K512': ('offheap_objects', 512, '16MiB', None, None),
    'hb':   ('heap_buffers', 256, '16MiB', None, None),
}
WORK = {  # label: list of (block name, S MiB, rows)
    'A':    [('s1', 1, 100), ('s8', 8, 100), ('s15', 15, 100), ('s17', 17, 1)],
    'A2':   [('s17', 17, 1)],
    'B':    [('s17', 17, 5), ('s60', 60, 5)],
    'K64':  [('s8', 8, 100)], 'K128': [('s8', 8, 100)], 'K256': [('s8', 8, 100)], 'K512': [('s8', 8, 100)], 'hb': [('s8', 8, 100)],
}
def setup_node(label):
    shutil.rmtree(node, ignore_errors=True)
    for d in ('data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw', 'logs'): os.makedirs(os.path.join(node, d))
    shutil.copytree(os.path.join(tree, 'conf'), os.path.join(node, 'conf'))
    envsh = os.path.join(node, 'conf/cassandra-env.sh'); t = open(envsh).read()
    assert 'JMX_PORT="7199"' in t; open(envsh, 'w').write(t.replace('JMX_PORT="7199"', 'JMX_PORT="%d"' % JMX))
    y = os.path.join(node, 'conf/cassandra.yaml'); txt = open(y).read()
    txt = re.sub(r'^listen_address:.*$', 'listen_address: ' + ADDR, txt, flags=re.M); txt = re.sub(r'^rpc_address:.*$', 'rpc_address: ' + ADDR, txt, flags=re.M)
    txt = re.sub(r'- seeds: ".*"', '- seeds: "%s:%d"' % (ADDR, STORAGE), txt)
    alloc, off, frame, mm, seg = CFG[label]
    kv = dict(COMMON, storage_port=STORAGE, native_transport_port=NATIVE, cluster_name="'nc-stage4'", auto_snapshot='false', cdc_enabled='false',
              commitlog_directory=node + '/commitlog', hints_directory=node + '/hints', saved_caches_directory=node + '/saved_caches', cdc_raw_directory=node + '/cdc_raw',
              key_cache_size='0MiB', memtable_allocation_type=alloc, memtable_offheap_space='%dMiB' % off, native_transport_max_frame_size=frame)
    if mm: kv['max_mutation_size'] = mm
    if seg: kv['commitlog_segment_size'] = seg
    for k, v in kv.items(): txt = setkey(txt, k, v)
    txt = re.sub(r'^data_file_directories:\n(\s+-.*\n)?', '', txt, flags=re.M)
    txt += '\ndata_file_directories:\n    - %s/data\n' % node
    open(y, 'w').write(txt)
def start_node(label):
    env = dict(os.environ, MAX_HEAP_SIZE='2G', HEAP_NEWSIZE='512M', CASSANDRA_CONF=node + '/conf', CASSANDRA_LOG_DIR=node + '/logs',
               MALLOC_ARENA_MAX='1', MALLOC_MMAP_THRESHOLD_='65536', MALLOC_TRIM_THRESHOLD_='0',
               JVM_EXTRA_OPTS='-XX:+AlwaysPreTouch -XX:MaxDirectMemorySize=1g')
    if os.path.exists(PIDF): os.remove(PIDF)
    log('start node arm', label)
    subprocess.run([os.path.join(tree, 'bin/cassandra'), '-p', PIDF], env=env, stdout=open(node + '/logs/stdout-%s.log' % label, 'w'), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=120)
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
    ev = os.path.join(out, label); os.makedirs(ev, exist_ok=True)
    open(ev + '/cmdline.txt', 'w').write(open('/proc/%d/cmdline' % p, 'rb').read().replace(b'\0', b' ').decode())
    open(ev + '/yaml-keys.txt', 'w').write('\n'.join(l for l in open(node + '/conf/cassandra.yaml').read().splitlines()
        if re.match(r'(memtable_|native_transport_max|native_transport_timeout|max_mutation_size|commitlog_segment_size|listen_address|rpc_address|storage_port|native_transport_port|cluster_name)', l)))
    return p

sys.path.insert(0, drv)
def connect():
    from cassandra.cluster import Cluster
    from cassandra.policies import DCAwareRoundRobinPolicy
    c = Cluster([ADDR], port=NATIVE, protocol_version=4, load_balancing_policy=DCAwareRoundRobinPolicy(local_dc='datacenter1'), token_metadata_enabled=False, connect_timeout=30)
    return c, c.connect()

def run_arm(label):
    alloc, off, frame, mm, seg = CFG[label]
    ev = os.path.join(out, label); S = dict(label=label, cfg=dict(zip(('alloc', 'offheap_mib', 'frame', 'max_mutation', 'segment'), CFG[label])), marks={}, blocks=[])
    log('=== arm', label, CFG[label])
    setup_node(label); p = start_node(label); S['pid'] = p
    time.sleep(10)
    c, s = connect()
    s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    s.execute("CREATE TABLE IF NOT EXISTS ks.t (pk int PRIMARY KEY, v blob) WITH compression = {'enabled':'false'}")
    sh(NT + ['disableautocompaction'], check=False)
    c.shutdown()
    sampcsv = os.path.join(ev, 'samples.csv')
    SAMPLER[0] = subprocess.Popen(['java', '-cp', smp, 'JmxSampler', str(JMX), str(p), sampcsv, '100'], stdout=open(ev + '/sampler.out', 'w'), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    time.sleep(12)    # idle baseline
    S['marks']['baseline_end'] = int(time.time() * 1000)
    rows = open(os.path.join(ev, 'rows.jsonl'), 'w')
    base = 0
    for name, smib, n in WORK[label]:
        n = nrows(n); c, s = connect(); ps = s.prepare('INSERT INTO ks.t (pk, v) VALUES (?, ?)')
        a = int(time.time() * 1000); ok = err = 0; first = None
        for i in range(n):
            blob = os.urandom(smib * MiB); t0 = time.time()
            try: s.execute(ps, (base + i, blob), timeout=120); st = 'ok'; ok += 1
            except Exception as e:
                st = 'err'; err += 1; msg = (type(e).__name__ + ': ' + str(e))[:400]; first = first or msg
                rows.write(json.dumps(dict(block=name, i=i, status='err', msg=msg, ms=int((time.time() - t0) * 1000))) + '\n'); rows.flush(); continue
            rows.write(json.dumps(dict(block=name, i=i, status='ok', ms=int((time.time() - t0) * 1000))) + '\n'); rows.flush()
        b = int(time.time() * 1000); base += 1000
        S['blocks'].append(dict(name=name, S_mib=smib, rows=n, ok=ok, err=err, first_err=first, a=a, b=b)); log('block', name, 'ok', ok, 'err', err, first or '')
        try: c.shutdown()
        except Exception: pass
        time.sleep(3)
    time.sleep(15)    # settle
    S['marks']['end'] = int(time.time() * 1000)
    stop_sampler()
    lg = open(node + '/logs/system.log', errors='replace').read()
    S['log'] = dict(ISE=lg.count('IllegalStateException'), NativeCell=lg.count('NativeCell'), ERROR_lines=len([l for l in lg.splitlines() if l.startswith('ERROR')]),
                    oversized=lg.count('oversized mutation'), global_offheap=[l[-120:] for l in lg.splitlines() if 'Global memtable' in l],
                    errors_head=[l[:300] for l in lg.splitlines() if l.startswith('ERROR')][:5])
    open(ev + '/system.log.excerpt', 'w').write('\n'.join(l[:400] for l in lg.splitlines() if l.startswith(('ERROR', 'WARN')) or 'Global memtable' in l or 'IllegalState' in l or 'oversized' in l.lower())[:20000])
    stop_node()
    shutil.copy(node + '/logs/system.log', ev + '/system.log')
    json.dump(S, open(os.path.join(ev, 'arm.json'), 'w'), indent=1)
    shutil.rmtree(os.path.join(node, 'data'), ignore_errors=True); shutil.rmtree(os.path.join(node, 'commitlog'), ignore_errors=True)
    log('arm', label, 'done')

log('cluster-run start tree=%s head=%s arms=%s scale=%s' % (tree, sh(['git', '-C', tree, 'rev-parse', '--short', 'HEAD'], quiet=True).strip(), ARMS, SCALE))
log('df:', sh('df -T ~ | tail -1', quiet=True).strip())
for p in (STORAGE, NATIVE, JMX):
    if subprocess.run("ss -ltn | grep -q ':%d '" % p, shell=True).returncode == 0: raise SystemExit('port %d busy' % p)
for a in ARMS: run_arm(a)
log('cluster-run done')
