#!/usr/bin/env python3
"""Cluster tier driver for key_cache_size-create-size--autonomous (B3, with the audit's B3i).
Usage: cluster-run.py <tree> <nodedir> <outdir> <arm> [<arm> ...]
Arms: load | k0 k4 k16 k64 k512 k16b (key_cache_size MiB, two read passes) | rt (64, then setcachecapacity 16 0 0 after pass 1)
Env STAGE4_N overrides the reads per pass (shakedown only), STAGE4_LOADN the load size.
Own tag kc: loopback 127.31.7.1, JMX 7491. Stops the node on any exit; kills by PID only."""
import sys, os, subprocess, time, json, shutil, signal, resource, re, atexit, csv

tree, node, out = sys.argv[1:4]; arms = sys.argv[4:]
HARN = os.path.dirname(os.path.abspath(__file__))
DRIVER = os.path.expanduser('~/s4-kc/driver/cassandra-driver-3.29.0')
ADDR = '127.31.7.1'; JMX = '7491'
P = int(os.environ.get('STAGE4_LOADN', '1000000')); N = int(os.environ.get('STAGE4_N', '3000000'))
resource.setrlimit(resource.RLIMIT_NOFILE, (100000, 100000))
os.makedirs(out, exist_ok=True)
LOG = open(os.path.join(out, 'session.log'), 'a')
def log(*a):
    m = '[%s] %s' % (time.strftime('%FT%T%z'), ' '.join(str(x) for x in a)); print(m, flush=True); LOG.write(m + '\n'); LOG.flush()
def sh(cmd, check=True, timeout=None, quiet=False):
    log('+', cmd if isinstance(cmd, str) else ' '.join(cmd))
    t0 = time.time()
    p = subprocess.run(cmd, shell=isinstance(cmd, str), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    if not quiet: log(p.stdout.strip()[-2000:])
    log('  exit', p.returncode, 'in %.1fs' % (time.time() - t0))
    if check and p.returncode: raise RuntimeError('command failed: %s' % cmd)
    return p.stdout

NT = [os.path.join(tree, 'bin/nodetool'), '-p', JMX]
STRESS = os.path.join(tree, 'tools/bin/cassandra-stress')
PIDF = os.path.join(node, 'cassandra.pid')
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
        try: subprocess.run(NT + ['drain'], timeout=180, stdout=LOG, stderr=LOG, stdin=subprocess.DEVNULL)
        except Exception as e: log('drain failed', e)
        os.kill(p, signal.SIGTERM)
        for _ in range(90):
            if not alive(p): break
            time.sleep(1)
        else: os.kill(p, signal.SIGKILL)
    log('node pid alive after stop:', bool(pid() and alive(pid())))
atexit.register(stop_node)

def setkey(txt, k, v):
    if re.search(r'^%s:' % k, txt, re.M): return re.sub(r'^%s:.*$' % k, '%s: %s' % (k, v), txt, flags=re.M)
    return txt + '\n%s: %s\n' % (k, v)
def configure(keysize):
    if not os.path.isdir(os.path.join(node, 'conf')):
        for d in ('data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw', 'logs'): os.makedirs(os.path.join(node, d), exist_ok=True)
        shutil.copytree(os.path.join(tree, 'conf'), os.path.join(node, 'conf'))
        env = os.path.join(node, 'conf/cassandra-env.sh'); t = open(env).read()
        t = re.sub(r'^JMX_PORT="7199"', 'JMX_PORT="%s"' % JMX, t, flags=re.M); open(env, 'w').write(t)
        assert 'JMX_PORT="%s"' % JMX in t
    y = os.path.join(node, 'conf/cassandra.yaml'); txt = open(y).read()
    txt = re.sub(r'^data_file_directories:\n(\s+-.*\n)?', '', txt, flags=re.M)
    txt += '\ndata_file_directories:\n    - %s/data\n' % node
    for k, v in (('cluster_name', "'kc-test'"), ('listen_address', ADDR), ('rpc_address', ADDR), ('commitlog_directory', node + '/commitlog'),
                 ('hints_directory', node + '/hints'), ('saved_caches_directory', node + '/saved_caches'), ('cdc_raw_directory', node + '/cdc_raw'),
                 ('cdc_enabled', 'false'), ('auto_snapshot', 'false'), ('row_cache_size', '0MiB'), ('counter_cache_size', '0MiB'),
                 ('key_cache_size', '%dMiB' % keysize), ('key_cache_save_period', '1h'), ('commitlog_total_space', '1024MiB')):
        txt = setkey(txt, k, v)
    txt = re.sub(r'- seeds: ".*"', '- seeds: "%s:7000"' % ADDR, txt)
    open(y, 'w').write(txt)
    for k in ('key_cache_size', 'listen_address', 'data_file_directories', 'row_cache_size'):
        assert len(re.findall(r'^%s:' % k, txt, re.M)) == 1, k
    return y
def daemon_up():
    p = pid()
    return bool(p and alive(p))
def start_node(label, keysize):
    assert not daemon_up(), 'a daemon is already running for this node dir'
    shutil.rmtree(os.path.join(node, 'saved_caches'), ignore_errors=True); os.makedirs(os.path.join(node, 'saved_caches'))
    y = configure(keysize); shutil.copy(y, os.path.join(out, 'cassandra.yaml.%s' % label))
    env = dict(os.environ, MAX_HEAP_SIZE='2G', HEAP_NEWSIZE='512M', CASSANDRA_CONF=node + '/conf', CASSANDRA_LOG_DIR=node + '/logs')
    log('+ bin/cassandra -p', PIDF, 'key_cache_size', keysize)
    subprocess.run([os.path.join(tree, 'bin/cassandra'), '-p', PIDF], env=env, stdout=open(node + '/logs/stdout.log', 'a'), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=60)
    for i in range(80):
        time.sleep(5)
        if not daemon_up(): raise RuntimeError('daemon died during start')
        st = subprocess.run(NT + ['status'], stdout=subprocess.PIPE, text=True, stderr=subprocess.DEVNULL).stdout
        sb = subprocess.run(NT + ['statusbinary'], stdout=subprocess.PIPE, text=True, stderr=subprocess.DEVNULL).stdout.strip()
        if re.search(r'^UN', st, re.M) and sb == 'running': log('node up, pid', pid()); return
    raise RuntimeError('node did not come up')

sys.path.insert(0, DRIVER)
SES = {}
def session():
    from cassandra.cluster import Cluster
    from cassandra.policies import DCAwareRoundRobinPolicy
    c = Cluster([ADDR], protocol_version=5, load_balancing_policy=DCAwareRoundRobinPolicy(local_dc='datacenter1'), token_metadata_enabled=False)
    SES['c'] = c; SES['s'] = c.connect(); return SES['s']
def close_session():
    if 'c' in SES: SES['c'].shutdown(); SES.clear()
def caches():
    r = list(SES['s'].execute("SELECT * FROM system_views.caches WHERE name='keys'", timeout=30))[0]
    return dict(size=r.size_bytes, capacity=r.capacity_bytes, entries=r.entry_count, requests=r.request_count, hits=r.hit_count)

def hist(o, tag):
    f = os.path.join(o, 'hist-%s.txt' % tag)
    t0 = time.time(); txt = subprocess.run(['jcmd', str(pid()), 'GC.class_histogram'], stdout=subprocess.PIPE, text=True).stdout
    open(f, 'w').write(txt)
    return f, round(time.time() - t0, 1)

def stress(o, label, args, n_samples_sink, hist_every=60):
    """Run a stress command in the background; sample caches every 10 s and take a histogram every hist_every s."""
    logf = open(os.path.join(o, 'stress-%s.out' % label), 'w')
    cmd = [STRESS] + args + ['-node', ADDR, '-port', 'native=9042']
    log('+', ' '.join(cmd))
    p = subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    t0 = time.time(); last_h = t0; k = 0
    while p.poll() is None:
        time.sleep(10)
        c = caches(); c['t_ms'] = int(time.time() * 1000); c['phase'] = label; n_samples_sink.append(c)
        if time.time() - last_h >= hist_every:
            k += 1; f, d = hist(o, '%s-%02d' % (label, k)); last_h = time.time(); n_samples_sink[-1]['hist'] = os.path.basename(f)
        if time.time() - t0 > 1500: p.terminate(); raise RuntimeError('stress exceeded 25 min')
    log('stress %s exit %s after %.0fs' % (label, p.returncode, time.time() - t0))
    if p.returncode: raise RuntimeError('stress failed')
    tail = open(os.path.join(o, 'stress-%s.out' % label)).read()
    m = re.search(r'Results:.*', tail, re.S); open(os.path.join(o, 'stress-%s.results' % label), 'w').write(m.group(0) if m else tail[-3000:])
    return time.time() - t0

def jmx_read(o):
    r = {}
    for a in ('Size', 'Capacity', 'Entries'):
        s = subprocess.run(NT + ['sjk', 'mx', '-mg', '-b', 'org.apache.cassandra.metrics:type=Cache,scope=KeyCache,name=' + a, '-f', 'Value'], stdout=subprocess.PIPE, text=True, stderr=subprocess.STDOUT).stdout.strip()
        r[a] = s
    open(os.path.join(o, 'jmx.txt'), 'w').write(json.dumps(r) + '\n'); log('jmx', r); return r

def run_load():
    o = os.path.join(out, 'load'); os.makedirs(o, exist_ok=True)
    shutil.rmtree(node, ignore_errors=True)
    start_node('load', 0); session()
    lo = sh([STRESS, 'user', 'profile=' + os.path.join(HARN, 'kc.yaml'), 'ops(insert=1)', 'n=%d' % P, 'no-warmup', '-pop', 'seq=1..%d' % P, '-rate', 'threads=64',
        '-node', ADDR, '-port', 'native=9042'], quiet=True, timeout=3000)
    m = re.search(r'Results:.*', lo, re.S); open(os.path.join(o, 'stress-load.results'), 'w').write(m.group(0) if m else lo[-3000:])
    assert re.search(r'Total partitions\s*:\s*1,000,000', lo) and re.search(r'Total errors\s*:\s*0', lo), 'EXPECTED 1,000,000 partitions written, 0 errors'
    sh(NT + ['flush', 'ks', 't']); sh(NT + ['compact', 'ks', 't'], timeout=3000)
    ts = sh(NT + ['tablestats', 'ks.t'], quiet=True); open(os.path.join(o, 'tablestats.txt'), 'w').write(ts)
    files = [f for dp, dn, fn in os.walk(node + '/data/ks') for f in fn if f.endswith('-Data.db')]
    du = sum(os.path.getsize(os.path.join(dp, f)) for dp, dn, fn in os.walk(node + '/data/ks') for f in fn)
    S = dict(data_files=len(files), du_bytes=du); open(os.path.join(o, 'summary.json'), 'w').write(json.dumps(S)); log('load summary', S)
    m = re.search(r'Number of partitions \(estimate\): (\d+)', ts); S['partitions_estimate'] = int(m.group(1)); log('partitions estimate', S['partitions_estimate'])
    assert 0.9 * P <= S['partitions_estimate'] <= 1.1 * P, 'EXPECTED about P partitions'
    open(os.path.join(o, 'summary.json'), 'w').write(json.dumps(S))
    assert len(files) == 1, 'EXPECTED one sstable after compaction'
    close_session(); stop_node()

ARM = {'k0': 0, 'k4': 4, 'k16': 16, 'k64': 64, 'k512': 512, 'k16b': 16, 'rt': 64}
def run_arm(label):
    o = os.path.join(out, label); shutil.rmtree(o, ignore_errors=True); os.makedirs(o)
    keysize = ARM[label]; log('=== arm', label, 'key_cache_size', keysize, 'MiB')
    start_node(label, keysize); session()
    S = dict(arm=label, knob_mib=keysize, pid=pid()); samples = []
    log_init = sh("grep -h 'Initializing key cache' %s/logs/system.log | tail -1" % node, check=False, quiet=True).strip(); S['init_log'] = log_init; log(log_init)
    assert ('capacity of %d MiBs' % keysize) in log_init, 'EXPECTED the knob in the init log'
    S['jvm_flags'] = subprocess.run(['jcmd', str(pid()), 'VM.flags'], stdout=subprocess.PIPE, text=True).stdout.strip()
    c = caches(); c['t_ms'] = int(time.time() * 1000); c['phase'] = 't0'; samples.append(c); log('t0', c)
    f, d = hist(o, 't0'); samples[-1]['hist'] = os.path.basename(f)
    prof = 'profile=' + os.path.join(HARN, 'kc.yaml')
    rd = ['user', prof, 'ops(read1=1)', 'n=%d' % N, 'no-warmup', '-pop', 'dist=uniform(1..%d)' % P, '-rate', 'threads=32']
    stress(o, 'pass1', rd, samples)
    c = caches(); c['t_ms'] = int(time.time() * 1000); c['phase'] = 'end-pass1'; samples.append(c); log('end-pass1', c)
    f, d = hist(o, 'end-pass1'); samples[-1]['hist'] = os.path.basename(f)
    if keysize > 0: assert c['entries'] > 0, 'EXPECTED entries > 0 after pass 1 (first trigger did not fire)'
    else: log('EXPECTED entries == 0 for cap 0:', c['entries'] == 0)
    if label == 'rt':
        log('+ nodetool setcachecapacity 16 0 0'); sh(NT + ['setcachecapacity', '16', '0', '0'])
        t0 = time.time()
        while time.time() - t0 < 30:
            time.sleep(5); c = caches(); c['t_ms'] = int(time.time() * 1000); c['phase'] = 'after-setcap'; samples.append(c)
        f, d = hist(o, 'after-setcap'); samples[-1]['hist'] = os.path.basename(f); log('after-setcap', samples[-1])
    stress(o, 'pass2', rd, samples)
    c = caches(); c['t_ms'] = int(time.time() * 1000); c['phase'] = 'end-pass2'; samples.append(c); log('end-pass2', c)
    f, d = hist(o, 'end-pass2'); samples[-1]['hist'] = os.path.basename(f)
    S['jmx'] = jmx_read(o)
    sh("%s info | grep -i 'key cache'" % ' '.join(NT), check=False)
    S['nodetool_info'] = sh("%s info | grep -i 'key cache'" % ' '.join(NT), check=False, quiet=True).strip()
    S['errors_in_log'] = sh("grep -c '^ERROR' %s/logs/system.log || true" % node, check=False, quiet=True).strip()
    sh("cp %s/logs/system.log %s/system.log.full" % (node, o), check=False, quiet=True)
    with open(os.path.join(o, 'samples.csv'), 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=['t_ms', 'phase', 'size', 'capacity', 'entries', 'requests', 'hits', 'hist']); w.writeheader()
        for s_ in samples: w.writerow({k: s_.get(k, '') for k in w.fieldnames})
    open(os.path.join(o, 'summary.json'), 'w').write(json.dumps(S, indent=1))
    close_session(); stop_node()

try:
    for a in arms:
        if a == 'load': run_load()
        else: run_arm(a)
finally:
    close_session()
log('ALL ARMS DONE', arms)
