#!/usr/bin/env python3
"""Cluster tier driver shared by the three counter_cache_size autonomous cases (B3 of each file, with the audit's amendments).
Usage: cluster-run.py <tree> <nodedir> <outdir> <arm> [<arm> ...]
Arms (counter_cache_size in the node's yaml, MiB; 'def' = key left empty = auto):
  c0 c1 c8 c64 cdef   fresh node, counter_write pass 1 (P = 600,000 keys x 5 counters) then pass 2 (the last 50,000 keys of pass 1 once more)
  c8b                 repeat of c8
  rt64                start at 64, pass 1, runtime setCounterCacheCapacityInMB(8) over JMX, pass 2
  r8                  start at 8, REGULAR-table writes only (stress 'write'), counter cache must stay empty
  sv8                 start at 8, pass 1, flush, saveCaches over JMX, copy saved_caches to <nodedir>.saved, stop (data kept)
  rl0 rl1 rl8         restart the sv8 node dir (data kept, saved file restored) with capacity 0 / 1 / 8; no writes; sample the reload
Own tag cc: loopback 127.39.9.1, JMX 7439. Stops the node on any exit; kills by PID only."""
import sys, os, subprocess, time, json, shutil, signal, resource, re, atexit, csv

tree, node, out = sys.argv[1:4]; arms = sys.argv[4:]
HARN = os.path.dirname(os.path.abspath(__file__))
ADDR = '127.39.9.1'; JMX = '7439'; JBIN = os.path.expanduser('~/s4-cc/bin')
P = int(os.environ.get('STAGE4_N', '600000')); HOT = int(os.environ.get('STAGE4_HOT', '50000'))
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
def configure(cap):
    if not os.path.isdir(os.path.join(node, 'conf')):
        for d in ('data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw', 'logs'): os.makedirs(os.path.join(node, d), exist_ok=True)
        shutil.copytree(os.path.join(tree, 'conf'), os.path.join(node, 'conf'))
        env = os.path.join(node, 'conf/cassandra-env.sh'); t = open(env).read()
        t = re.sub(r'^JMX_PORT="7199"', 'JMX_PORT="%s"' % JMX, t, flags=re.M); open(env, 'w').write(t)
        assert 'JMX_PORT="%s"' % JMX in t
        y = os.path.join(node, 'conf/cassandra.yaml'); txt = open(y).read()
        txt = re.sub(r'^data_file_directories:\n(\s+-.*\n)?', '', txt, flags=re.M)
        txt += '\ndata_file_directories:\n    - %s/data\n' % node
        open(y, 'w').write(txt)
    y = os.path.join(node, 'conf/cassandra.yaml'); txt = open(y).read()
    for k, v in (('cluster_name', "'cc-test'"), ('listen_address', ADDR), ('rpc_address', ADDR), ('commitlog_directory', node + '/commitlog'),
                 ('hints_directory', node + '/hints'), ('saved_caches_directory', node + '/saved_caches'), ('cdc_raw_directory', node + '/cdc_raw'),
                 ('cdc_enabled', 'false'), ('auto_snapshot', 'false'), ('row_cache_size', '0MiB'),
                 ('counter_cache_size', '' if cap is None else '%dMiB' % cap), ('counter_cache_save_period', '3600s'), ('commitlog_total_space', '1024MiB')):
        txt = setkey(txt, k, v)
    txt = re.sub(r'- seeds: ".*"', '- seeds: "%s:7000"' % ADDR, txt)
    open(y, 'w').write(txt)
    for k in ('counter_cache_size', 'listen_address', 'data_file_directories', 'row_cache_size', 'counter_cache_save_period'):
        assert len(re.findall(r'^%s:' % k, txt, re.M)) == 1, k
    return y
def daemon_up():
    p = pid()
    return bool(p and alive(p))
def start_node(label, cap, wipe_saved=True):
    assert not daemon_up(), 'a daemon is already running for this node dir'
    if wipe_saved:
        shutil.rmtree(os.path.join(node, 'saved_caches'), ignore_errors=True); os.makedirs(os.path.join(node, 'saved_caches'))
    y = configure(cap); shutil.copy(y, os.path.join(out, 'cassandra.yaml.%s' % label))
    env = dict(os.environ, MAX_HEAP_SIZE='2G', HEAP_NEWSIZE='512M', CASSANDRA_CONF=node + '/conf', CASSANDRA_LOG_DIR=node + '/logs')
    log('+ bin/cassandra -p', PIDF, 'counter_cache_size', cap)
    subprocess.run([os.path.join(tree, 'bin/cassandra'), '-p', PIDF], env=env, stdout=open(node + '/logs/stdout.log', 'a'), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=60)
    for i in range(80):
        time.sleep(5)
        if not daemon_up(): raise RuntimeError('daemon died during start')
        st = subprocess.run(NT + ['status'], stdout=subprocess.PIPE, text=True, stderr=subprocess.DEVNULL).stdout
        sb = subprocess.run(NT + ['statusbinary'], stdout=subprocess.PIPE, text=True, stderr=subprocess.DEVNULL).stdout.strip()
        if re.search(r'^UN', st, re.M) and sb == 'running': log('node up, pid', pid()); return
    raise RuntimeError('node did not come up')

def cache(scope='CounterCache'):
    s = subprocess.run(['java', '-cp', JBIN, 'Jmx', JMX, 'once', scope], stdout=subprocess.PIPE, text=True, stderr=subprocess.STDOUT).stdout.strip().splitlines()[-1]
    t, size, cap, ent, hits, req = s.split(',')
    return dict(t_ms=int(t), size=int(float(size)), capacity=int(float(cap)), entries=int(float(ent)), hits=int(hits), requests=int(req))
def hist(o, tag):
    f = os.path.join(o, 'hist-%s.txt' % tag)
    t0 = time.time(); txt = subprocess.run(['jcmd', str(pid()), 'GC.class_histogram'], stdout=subprocess.PIPE, text=True).stdout
    open(f, 'w').write(txt)
    heap = subprocess.run(['jcmd', str(pid()), 'GC.heap_info'], stdout=subprocess.PIPE, text=True).stdout
    open(os.path.join(o, 'heapinfo-%s.txt' % tag), 'w').write(heap)
    return f

def stress(o, label, args, samples, hist_every=60):
    logf = open(os.path.join(o, 'stress-%s.out' % label), 'w')
    cmd = [STRESS] + args + ['-node', ADDR, '-port', 'native=9042']
    log('+', ' '.join(cmd))
    p = subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    t0 = time.time(); last_h = t0; k = 0
    while p.poll() is None:
        time.sleep(10)
        c = cache(); c['phase'] = label; samples.append(c)
        if time.time() - last_h >= hist_every:
            k += 1; f = hist(o, '%s-%02d' % (label, k)); last_h = time.time(); samples[-1]['hist'] = os.path.basename(f)
        if time.time() - t0 > 1500: p.terminate(); raise RuntimeError('stress exceeded 25 min')
    log('stress %s exit %s after %.0fs' % (label, p.returncode, time.time() - t0))
    if p.returncode: raise RuntimeError('stress failed')
    tail = open(os.path.join(o, 'stress-%s.out' % label)).read()
    m = re.search(r'Results:.*', tail, re.S); open(os.path.join(o, 'stress-%s.results' % label), 'w').write(m.group(0) if m else tail[-3000:])
    assert re.search(r'Total errors\s*:\s*0', tail), 'EXPECTED 0 stress errors'
    return time.time() - t0

def snap(o, samples, phase, with_hist=True):
    c = cache(); c['phase'] = phase
    if with_hist: c['hist'] = os.path.basename(hist(o, phase))
    samples.append(c); log(phase, c); return c
def write_samples(o, samples):
    with open(os.path.join(o, 'samples.csv'), 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=['t_ms', 'phase', 'size', 'capacity', 'entries', 'hits', 'requests', 'hist']); w.writeheader()
        for s_ in samples: w.writerow({k: s_.get(k, '') for k in w.fieldnames})
def finish(o, S, samples):
    S['jmx_final'] = cache()
    S['nodetool_info'] = sh("%s info | grep -i 'counter cache'" % ' '.join(NT), check=False, quiet=True).strip()
    S['errors_in_log'] = sh("grep -c '^ERROR' %s/logs/system.log || true" % node, check=False, quiet=True).strip()
    S['init_log'] = sh("grep -h 'counter cache' %s/logs/system.log | tail -n 8" % node, check=False, quiet=True).strip()
    sh("cp %s/logs/system.log %s/system.log.full" % (node, o), check=False, quiet=True)
    write_samples(o, samples); open(os.path.join(o, 'summary.json'), 'w').write(json.dumps(S, indent=1))

CAP = {'c0': 0, 'c1': 1, 'c8': 8, 'c64': 64, 'cdef': None, 'c8b': 8, 'rt64': 64, 'r8': 8, 'sv8': 8, 'rl0': 0, 'rl1': 1, 'rl8': 8}
def run_arm(label):
    o = os.path.join(out, label); shutil.rmtree(o, ignore_errors=True); os.makedirs(o)
    cap = CAP[label]; log('=== arm', label, 'counter_cache_size', 'default(unset)' if cap is None else '%d MiB' % cap)
    reuse = label.startswith('rl')
    if not reuse: shutil.rmtree(node, ignore_errors=True)
    elif os.path.isdir(node + '.saved'):
        shutil.rmtree(os.path.join(node, 'saved_caches'), ignore_errors=True); shutil.copytree(node + '.saved', os.path.join(node, 'saved_caches'))
        open(os.path.join(o, 'saved_caches.ls'), 'w').write(sh('ls -l --time-style=+%%s %s/saved_caches' % node, quiet=True))
    else: raise RuntimeError('no saved cache; run sv8 first')
    start_node(label, cap, wipe_saved=not reuse)
    S = dict(arm=label, knob_mib=cap, pid=pid()); samples = []
    S['jvm_flags'] = subprocess.run(['jcmd', str(pid()), 'VM.flags'], stdout=subprocess.PIPE, text=True).stdout.strip()
    il = sh("grep -h 'Initializing counter cache' %s/logs/system.log | tail -n 1" % node, check=False, quiet=True).strip(); S['init_log'] = il; log(il)
    if cap is not None: assert ('capacity of %d MiBs' % cap) in il, 'EXPECTED the knob in the init log'
    if reuse:
        # the reload runs at start-up; sample for 60 s
        for i in range(12):
            c = cache(); c['phase'] = 'reload+%ds' % (5 * i); samples.append(c); log(c); time.sleep(5)
        snap(o, samples, 'reload-end'); finish(o, S, samples); stop_node(); return
    snap(o, samples, 't0')
    if label == 'r8':
        stress(o, 'regular', ['write', 'n=%d' % (P // 2), 'no-warmup', '-pop', 'seq=1..%d' % (P // 2), '-rate', 'threads=64'], samples)
        snap(o, samples, 'end-regular'); finish(o, S, samples); stop_node(); return
    stress(o, 'pass1', ['counter_write', 'n=%d' % P, 'no-warmup', '-pop', 'seq=1..%d' % P, '-rate', 'threads=64'], samples)
    c = snap(o, samples, 'end-pass1')
    if cap != 0: assert c['entries'] > 0, 'EXPECTED entries > 0 after pass 1 (first trigger did not fire)'
    if label == 'sv8':
        sh(NT + ['flush']); log(sh(['java', '-cp', JBIN, 'Jmx', JMX, 'save'], quiet=True))
        time.sleep(5); open(os.path.join(o, 'saved_caches.ls'), 'w').write(sh('ls -l --time-style=+%%s %s/saved_caches' % node, quiet=True))
        shutil.rmtree(node + '.saved', ignore_errors=True); shutil.copytree(os.path.join(node, 'saved_caches'), node + '.saved')
        snap(o, samples, 'after-save'); finish(o, S, samples); stop_node(); return
    if label == 'rt64':
        log(sh(['java', '-cp', JBIN, 'Jmx', JMX, 'set', 'counter', '8'], quiet=True))
        t0 = time.time()
        while time.time() - t0 < 30:
            time.sleep(5); c = cache(); c['phase'] = 'after-setcap'; samples.append(c)
        snap(o, samples, 'after-setcap-hist')
    stress(o, 'pass2', ['counter_write', 'n=%d' % HOT, 'no-warmup', '-pop', 'seq=%d..%d' % (P - HOT + 1, P), '-rate', 'threads=64'], samples)
    snap(o, samples, 'end-pass2'); finish(o, S, samples); stop_node()

try:
    for a in arms: run_arm(a)
finally:
    pass
log('ALL ARMS DONE', arms)
