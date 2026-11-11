#!/usr/bin/env python3
"""Cluster tier for nopcache_capacity-setcapacity-capacity--autonomous (B3 with the audit's amendments).
Usage: cluster-run.py <tree> <nodedir> <outdir> <arm> [<arm> ...]
Arms:  A    row_cache_size 0MiB (NopCache): load, 2 read passes, setcachecapacity 0 64 0 (expect rejection), setcachecapacity 0 0 0 (expect ok), 2 more read passes
       B32  OHCProvider row_cache_size 32MiB: load, 2 read passes, setcachecapacity 0 64 0 (expect ok), 2 more read passes
       AP   as A, run with the patched tree (NopCacheProvider guard `if (false)`): `cluster-run.py <tree-nopguard> ... AP`
       B8   OHCProvider row_cache_size 8MiB: load, 2 read passes (a third knob value, no runtime change)
Own tag nc: loopback 127.39.8.1, JMX 7438. Stops the node on any exit; kills by PID only."""
import sys, os, subprocess, time, json, shutil, signal, resource, re, atexit, csv

tree, node, out = sys.argv[1:4]; arms = sys.argv[4:]
HARN = os.path.dirname(os.path.abspath(__file__))
ADDR = '127.39.8.1'; JMX = '7438'; JBIN = os.path.expanduser('~/s4-cc/bin')
NPART = int(os.environ.get('STAGE4_NP', '20000'))
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
    return p
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
def configure(rowmib):
    for d in ('data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw', 'logs'): os.makedirs(os.path.join(node, d), exist_ok=True)
    shutil.copytree(os.path.join(tree, 'conf'), os.path.join(node, 'conf'))
    env = os.path.join(node, 'conf/cassandra-env.sh'); t = open(env).read()
    t = re.sub(r'^JMX_PORT="7199"', 'JMX_PORT="%s"' % JMX, t, flags=re.M); open(env, 'w').write(t)
    assert 'JMX_PORT="%s"' % JMX in t
    y = os.path.join(node, 'conf/cassandra.yaml'); txt = open(y).read()
    txt = re.sub(r'^data_file_directories:\n(\s+-.*\n)?', '', txt, flags=re.M)
    txt += '\ndata_file_directories:\n    - %s/data\n' % node
    kv = [('cluster_name', "'nc-test'"), ('listen_address', ADDR), ('rpc_address', ADDR), ('commitlog_directory', node + '/commitlog'),
          ('hints_directory', node + '/hints'), ('saved_caches_directory', node + '/saved_caches'), ('cdc_raw_directory', node + '/cdc_raw'),
          ('cdc_enabled', 'false'), ('auto_snapshot', 'false'), ('row_cache_size', '%dMiB' % rowmib), ('row_cache_save_period', '0s'),
          ('counter_cache_size', '0MiB'), ('commitlog_total_space', '1024MiB')]
    if rowmib > 0: kv.append(('row_cache_class_name', 'org.apache.cassandra.cache.OHCProvider'))
    for k, v in kv: txt = setkey(txt, k, v)
    txt = re.sub(r'- seeds: ".*"', '- seeds: "%s:7000"' % ADDR, txt)
    open(y, 'w').write(txt)
    for k in ('row_cache_size', 'listen_address', 'data_file_directories'): assert len(re.findall(r'^%s:' % k, txt, re.M)) == 1, k
    return y
def daemon_up():
    p = pid()
    return bool(p and alive(p))
def start_node(label, rowmib):
    assert not daemon_up()
    y = configure(rowmib); shutil.copy(y, os.path.join(out, 'cassandra.yaml.%s' % label))
    env = dict(os.environ, MAX_HEAP_SIZE='2G', HEAP_NEWSIZE='512M', CASSANDRA_CONF=node + '/conf', CASSANDRA_LOG_DIR=node + '/logs')
    log('+ bin/cassandra -p', PIDF, 'row_cache_size', rowmib)
    subprocess.run([os.path.join(tree, 'bin/cassandra'), '-p', PIDF], env=env, stdout=open(node + '/logs/stdout.log', 'a'), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=60)
    for i in range(80):
        time.sleep(5)
        if not daemon_up(): raise RuntimeError('daemon died during start')
        st = subprocess.run(NT + ['status'], stdout=subprocess.PIPE, text=True, stderr=subprocess.DEVNULL).stdout
        sb = subprocess.run(NT + ['statusbinary'], stdout=subprocess.PIPE, text=True, stderr=subprocess.DEVNULL).stdout.strip()
        if re.search(r'^UN', st, re.M) and sb == 'running': log('node up, pid', pid()); return
    raise RuntimeError('node did not come up')
def cache(scope='RowCache'):
    s = subprocess.run(['java', '-cp', JBIN, 'Jmx', JMX, 'once', scope], stdout=subprocess.PIPE, text=True, stderr=subprocess.STDOUT).stdout.strip().splitlines()[-1]
    t, size, cap, ent, hits, req = s.split(',')
    d = dict(t_ms=int(t), size=int(float(size)), capacity=int(float(cap)), entries=int(float(ent)), hits=int(hits), requests=int(req))
    d['rssAnon'] = rss(); return d
def rss():
    for l in open('/proc/%d/status' % pid()):
        if l.startswith('RssAnon:'): return int(l.split()[1]) * 1024
def hist(o, tag):
    f = os.path.join(o, 'hist-%s.txt' % tag)
    open(f, 'w').write(subprocess.run(['jcmd', str(pid()), 'GC.class_histogram'], stdout=subprocess.PIPE, text=True).stdout)
def stress(o, label, args, samples):
    logf = open(os.path.join(o, 'stress-%s.out' % label), 'w')
    cmd = [STRESS] + args + ['-node', ADDR, '-port', 'native=9042']
    log('+', ' '.join(cmd))
    p = subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    t0 = time.time()
    while p.poll() is None:
        time.sleep(5)
        c = cache(); c['phase'] = label; samples.append(c)
        if time.time() - t0 > 1200: p.terminate(); raise RuntimeError('stress exceeded 20 min')
    log('stress %s exit %s after %.0fs' % (label, p.returncode, time.time() - t0))
    txt = open(os.path.join(o, 'stress-%s.out' % label)).read()
    m = re.search(r'Results:.*', txt, re.S); open(os.path.join(o, 'stress-%s.results' % label), 'w').write(m.group(0) if m else txt[-3000:])
    if p.returncode or not re.search(r'Total errors\s*:\s*0', txt): raise RuntimeError('stress failed')
def snap(o, samples, phase, h=False):
    c = cache(); c['phase'] = phase
    if h: hist(o, phase)
    samples.append(c); log(phase, c); return c
def setcap(o, tag, args):
    p = sh(NT + ['setcachecapacity'] + args, check=False, quiet=True)
    open(os.path.join(o, 'setcap-%s.out' % tag), 'w').write('cmd: nodetool setcachecapacity %s\nexit: %d\n%s\n' % (' '.join(args), p.returncode, p.stdout))
    log('setcachecapacity', args, 'exit', p.returncode, p.stdout.strip()[-300:]); return p.returncode
def keycap(): 
    return sh("%s info | grep -i '^Key Cache'" % ' '.join(NT), check=False, quiet=True).stdout.strip()

ARM = {'A': 0, 'AP': 0, 'B32': 32, 'B8': 8}
def run_arm(label):
    o = os.path.join(out, label); shutil.rmtree(o, ignore_errors=True); os.makedirs(o)
    rowmib = ARM[label]; log('=== arm', label, 'row_cache_size', rowmib, 'MiB')
    shutil.rmtree(node, ignore_errors=True)
    start_node(label, rowmib)
    S = dict(arm=label, knob_mib=rowmib, pid=pid()); samples = []
    S['row_init_log'] = sh("grep -h 'row cache' %s/logs/system.log | head -n 3" % node, check=False, quiet=True).stdout.strip(); log(S['row_init_log'])
    assert ('capacity of %d MiBs' % rowmib) in S['row_init_log'], 'EXPECTED the knob in the init log'
    S['jvm_flags'] = subprocess.run(['jcmd', str(pid()), 'VM.flags'], stdout=subprocess.PIPE, text=True).stdout.strip()
    snap(o, samples, 't0', True)
    prof = 'profile=' + os.path.join(HARN, 'rc.yaml')
    sh([STRESS, 'user', prof, 'ops(insert=1)', 'n=%d' % NPART, 'no-warmup', '-pop', 'seq=1..%d' % NPART, '-rate', 'threads=32', '-node', ADDR, '-port', 'native=9042'], quiet=True, timeout=1500)
    sh(NT + ['flush', 'ks', 't']); snap(o, samples, 'after-load', True)
    S['tablestats'] = sh(NT + ['tablestats', 'ks.t'], quiet=True).stdout; open(os.path.join(o, 'tablestats.txt'), 'w').write(S['tablestats'])
    S['info_before'] = keycap()
    rd = ['user', prof, 'ops(read1=1)', 'n=%d' % NPART, 'no-warmup', '-pop', 'seq=1..%d' % NPART, '-rate', 'threads=32']
    for i in (1, 2):
        stress(o, 'pass%d' % i, rd, samples); snap(o, samples, 'end-pass%d' % i, True)
    if label in ('A', 'AP', 'B32'):
        rc = setcap(o, 'req64', ['0', '64', '0']); S['req64_exit'] = rc
        S['info_after_req64'] = keycap()
        snap(o, samples, 'after-req64', True)
        if label == 'A':
            S['req0_exit'] = setcap(o, 'req0', ['0', '0', '0'])
        for i in (3, 4):
            stress(o, 'pass%d' % i, rd, samples); snap(o, samples, 'end-pass%d' % i, True)
    S['nodetool_info_row'] = sh("%s info | grep -i 'row cache'" % ' '.join(NT), check=False, quiet=True).stdout.strip()
    S['errors_in_log'] = sh("grep -c '^ERROR' %s/logs/system.log || true" % node, check=False, quiet=True).stdout.strip()
    S['log_nop_lines'] = sh("grep -i 'NopCache\\|not permitted' %s/logs/system.log | head -n 5" % node, check=False, quiet=True).stdout.strip()
    sh("cp %s/logs/system.log %s/system.log.full" % (node, o), check=False, quiet=True)
    with open(os.path.join(o, 'samples.csv'), 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=['t_ms', 'phase', 'size', 'capacity', 'entries', 'hits', 'requests', 'rssAnon']); w.writeheader()
        for s_ in samples: w.writerow({k: s_.get(k, '') for k in w.fieldnames})
    open(os.path.join(o, 'summary.json'), 'w').write(json.dumps(S, indent=1))
    stop_node()
try:
    for a in arms: run_arm(a)
finally:
    pass
log('ALL ARMS DONE', arms)
