#!/usr/bin/env python3
"""Cluster tier, one label (stage 4, own harness; B3 as amended B5).
Usage: cluster-run.py <label> <kind: m|a|tc> <cap_mb|-> <outdir> [rows_scale]
Labels (cluster-all.sh): m (kind m, default option), c1 / c16 (kind a, option 1 / 16), tc (kind tc, default option).
One node from ~/s4-pw (never ran ant while a node runs): loopback 127.0.30.1, JMX 7330, native 9352, storage 7030 (Byteman 9330 unused).
Data under ~/s4-pw-data/<label>. Heap 2 GiB. Autocompaction disabled on the table before loading, so every segment line in the compaction window is from the one `nodetool compact`.
Everything is logged to <outdir>/session.log and summary.json; the node, sampler and thread are stopped on any exit. rows_scale divides the row counts (instrument check only)."""
import os, sys, time, subprocess, shutil, signal, json, glob, re, atexit, threading, gzip
import yaml

label, kind, cap, outdir = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
SC = int(sys.argv[5]) if len(sys.argv) > 5 else 1
HOME = os.path.expanduser('~'); TREE = HOME + '/s4-pw'
HARN = os.path.dirname(os.path.abspath(__file__))
WORK = HOME + '/s4-pw-data/' + label
JMX, NATIVE, STORAGE, ADDR = 7330, 9352, 7030, '127.0.30.1'
TABLE = 'tc' if kind == 'tc' else 't'
os.makedirs(outdir, exist_ok=True)
LOG = open(outdir + '/session.log', 'a')
pids = {}
def now_ms(): return int(time.time() * 1000)
def log(*a):
    s = '[%s.%03dZ] %s' % (time.strftime('%FT%T', time.gmtime()), now_ms() % 1000, ' '.join(str(x) for x in a))
    LOG.write(s + '\n'); LOG.flush(); print(s, flush=True)
def sh(cmd, timeout=900, check=False, quiet=False):
    log('+', cmd)
    r = subprocess.run(['bash', '-c', cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    if r.stdout.strip() and not quiet:
        LOG.write(r.stdout[-3000:] + '\n'); LOG.flush()
    if check and r.returncode:
        raise RuntimeError('command failed rc=%d: %s' % (r.returncode, cmd))
    return r
def alive(pid):
    """Reaps the child if it has exited (a zombie still has a /proc entry), then reports whether it runs."""
    try:
        r = os.waitpid(pid, os.WNOHANG)
        return r[0] == 0
    except ChildProcessError:
        return os.path.exists('/proc/%d' % pid)
def stop_all():
    for p in list(pids.values()):
        try: os.kill(p, signal.SIGTERM)
        except Exception: pass
    t0 = time.time()
    while time.time() - t0 < 120 and any(alive(p) for p in pids.values()):
        time.sleep(1)
    for n, p in list(pids.items()):
        if alive(p):
            log('SIGKILL', n, p)
            try: os.kill(p, signal.SIGKILL)
            except Exception: pass
    log('stopped', dict(pids), 'after %.0f s' % (time.time() - t0))
atexit.register(stop_all)
def nt(args, timeout=1800): return sh('%s/bin/nodetool -h 127.0.0.1 -p %d %s' % (TREE, JMX, args), timeout=timeout)

def mkconf():
    for sub in ['data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw', 'logs']:
        os.makedirs('%s/%s' % (WORK, sub), exist_ok=True)
    conf = WORK + '/conf'
    shutil.copytree(TREE + '/conf', conf)
    y = yaml.safe_load(open(conf + '/cassandra.yaml'))
    y.update({'cluster_name': 's4pw', 'num_tokens': 1, 'listen_address': ADDR, 'rpc_address': ADDR,
              'seed_provider': [{'class_name': 'org.apache.cassandra.locator.SimpleSeedProvider', 'parameters': [{'seeds': '%s:%d' % (ADDR, STORAGE)}]}],
              'storage_port': STORAGE, 'native_transport_port': NATIVE, 'sasi_indexes_enabled': True, 'auto_snapshot': False,
              'data_file_directories': [WORK + '/data'], 'commitlog_directory': WORK + '/commitlog', 'hints_directory': WORK + '/hints',
              'saved_caches_directory': WORK + '/saved_caches', 'cdc_raw_directory': WORK + '/cdc_raw'})
    yaml.safe_dump(y, open(conf + '/cassandra.yaml', 'w'), default_flow_style=False)
    env = open(conf + '/cassandra-env.sh').read()
    assert 'JMX_PORT="7199"' in env
    open(conf + '/cassandra-env.sh', 'w').write(env.replace('JMX_PORT="7199"', 'JMX_PORT="%d"' % JMX))
    lb = open(conf + '/logback.xml').read()
    lb = lb.replace('<maxFileSize>50MB</maxFileSize>', '<maxFileSize>6GB</maxFileSize>').replace('<totalSizeCap>5GB</totalSizeCap>', '<totalSizeCap>20GB</totalSizeCap>')
    open(conf + '/logback.xml', 'w').write(lb)   # no size rolling inside a run: log counts come from one file
    return conf

def start():
    conf = mkconf()
    e = dict(os.environ)
    e.update(CASSANDRA_HOME=TREE, CASSANDRA_CONF=conf, CASSANDRA_LOG_DIR=WORK + '/logs', MAX_HEAP_SIZE='2G', HEAP_NEWSIZE='400M',
             JVM_EXTRA_OPTS='-Dcassandra.ring_delay_ms=5000 -Duser.timezone=UTC')
    cmd = 'ulimit -n 100000; exec %s/bin/cassandra -f -p %s/pid' % (TREE, WORK)
    log('start node', cmd)
    p = subprocess.Popen(['bash', '-c', cmd], env=e, stdout=open(WORK + '/stdout.log', 'w'), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    pids['node'] = p.pid
    return p

def wait_binary(p, tmax=300):
    t0 = time.time()
    while time.time() - t0 < tmax:
        if p.poll() is not None:
            log('node died during start rc', p.returncode); return False
        r = nt('statusbinary', 60)
        if 'running' in r.stdout and 'not running' not in r.stdout:
            return True
        time.sleep(3)
    return False

SLOG = WORK + '/logs/system.log'
def window(off):
    """Counts and samples from system.log bytes after `off`."""
    with open(SLOG, 'rb') as f:
        f.seek(off); txt = f.read().decode('utf8', 'replace')
    lines = txt.split('\n')
    out = {'rejecting_writer_total': 0, 'cant_add_total': 0, 'err_rejecting_builder': 0, 'oom': txt.count('OutOfMemoryError'), 'flushed_segment_total': 0}
    for col in 'abc':
        out['rejecting_writer_col_' + col] = len(re.findall(r'Rejecting value \(size [^)]*\) for column %s \(analyzed' % col, txt))
        out['cant_add_col_' + col] = len(re.findall(r"Can't add term of column %s " % col, txt))
    out['rejecting_writer_total'] = txt.count('Rejecting value (size')
    out['cant_add_total'] = txt.count("Can't add term")
    out['err_rejecting_builder'] = txt.count('Rejecting value (value size')
    segs = re.findall(r'Flushed index segment \S*?SI_(\w+?)\.db_\d+', txt)
    out['flushed_segment_total'] = txt.count('Flushed index segment')
    for name in sorted(set(segs)): out['flushed_segment_' + name] = segs.count(name)
    out['index_flush_lines'] = txt.count('Index flush to')
    out['error_lines_other'] = len([l for l in lines if l.startswith('ERROR') and 'Rejecting value (value size' not in l])
    return out, [l for l in lines if 'Rejecting value (size' in l or "Can't add term" in l]

def files():
    si, da = {}, {}
    for f in glob.glob(WORK + '/data/ks/%s-*/*' % TABLE):
        b = os.path.basename(f); sz = os.path.getsize(f)
        m = re.search(r'-(SI_\w+?\.db)$', b)
        if m: si[b] = sz
        elif b.endswith('-Data.db'): da[b] = sz
    return {'si': dict(sorted(si.items())), 'si_bytes_by_index': {n: sum(v for k, v in si.items() if k.endswith('SI_%s.db' % n)) for n in ('t_a_idx', 't_b_idx', 'tc_c_idx')},
            'data': dict(sorted(da.items())), 'data_bytes': sum(da.values())}
def dirbytes(path):
    t = 0
    for r, ds, fs in os.walk(path):
        for f in fs:
            try: t += os.path.getsize(os.path.join(r, f))
            except OSError: pass
    return t

class Histo(threading.Thread):
    """Samples GC.class_histogram every 3 s during the compaction: live DynamicTokenTreeBuilder instances, and the data directory bytes."""
    def __init__(self, pid, path):
        super().__init__(daemon=True); self.pid = pid; self.path = path; self.stop = threading.Event()
    def run(self):
        with open(self.path, 'w') as f:
            f.write('epoch_ms,dttb_instances,histogram_total_bytes,datadir_bytes\n')
            while not self.stop.is_set():
                r = subprocess.run(['jcmd', str(self.pid), 'GC.class_histogram'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL)
                n = 0; tot = ''
                for l in r.stdout.splitlines():
                    if l.rstrip().endswith('DynamicTokenTreeBuilder'): n = int(l.split()[1])
                    if l.strip().startswith('Total'): tot = l.split()[2]
                f.write('%d,%d,%s,%d\n' % (now_ms(), n, tot, dirbytes(WORK + '/data'))); f.flush()
                self.stop.wait(3)

summary = dict(label=label, kind=kind, cap=cap, scale=SC, host=os.uname().nodename)
def phase(name, off):
    w, samples = window(off)
    summary['log_' + name] = w
    with open(outdir + '/rejection-samples.txt', 'a') as f:
        f.write('== %s: %d lines; first 3 and last 3 ==\n' % (name, len(samples)))
        for l in samples[:3] + samples[-3:]: f.write(l[:300] + '\n')
    return os.path.getsize(SLOG)

def loadcmd(first, last):
    return 'python3 %s/loader.py %s %s %d load %s %d %d' % (HARN, TREE, ADDR, NATIVE, kind, first, last)
def query(i):
    r = sh('python3 %s/loader.py %s %s %d query %s %d' % (HARN, TREE, ADDR, NATIVE, kind, i), timeout=300)
    return [l for l in r.stdout.splitlines() if l.startswith('query')]

try:
    log('run', label, 'kind', kind, 'cap', cap, 'scale', SC, 'host', os.uname().nodename)
    for port in (JMX, NATIVE, STORAGE):
        if sh('ss -ltn | grep -q ":%d "' % port, quiet=True).returncode == 0:
            raise RuntimeError('port %d busy' % port)
    shutil.rmtree(WORK, ignore_errors=True); os.makedirs(WORK)
    sh('mkdir -p %s/sampler && javac -d %s/sampler %s/HeapSampler.java' % (WORK, WORK, HARN), check=True)
    p = start()
    if not wait_binary(p): raise RuntimeError('node did not start')
    log('node up'); time.sleep(5)
    cmdline = open('/proc/%d/cmdline' % p.pid, 'rb').read().replace(b'\0', b' ').decode()
    open(outdir + '/node-cmdline.txt', 'w').write(cmdline + '\n')
    summary['xmx'] = re.findall(r'-Xmx\S+', cmdline); summary['xms'] = re.findall(r'-Xms\S+', cmdline)
    smp = subprocess.Popen(['java', '-cp', WORK + '/sampler', 'HeapSampler', str(JMX), outdir + '/heap.csv', '500'], stdout=open(outdir + '/sampler.out', 'w'),
                           stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    pids['sampler'] = smp.pid; time.sleep(3)
    summary['schema_out'] = sh('python3 %s/loader.py %s %s %d schema %s %s' % (HARN, TREE, ADDR, NATIVE, kind, cap), check=True).stdout.strip().splitlines()[-1]
    nt('disableautocompaction ks %s' % TABLE)
    summary['autocompaction_state'] = nt('compactionstats').stdout.strip()[:200]
    off = os.path.getsize(SLOG)
    steps = {'m': [(0, 100000 // SC), (100000 // SC, 400000 // SC)], 'a': [(0, 400000 // SC)], 'tc': [(0, 2000 // SC), (2000 // SC, 8000 // SC)]}[kind]
    summary['steps'] = []
    for n, (first, last) in enumerate(steps, 1):
        t0 = now_ms()
        r = sh(loadcmd(first, last), timeout=3600, check=True)
        off = phase('load%d' % n, off)
        nt('flush ks %s' % TABLE); time.sleep(15)   # index flush tasks log after the nodetool call returns
        off = phase('flush%d' % n, off)
        f = files()
        summary['steps'].append({'n': n, 'rows_total': last, 't_start': t0, 't_end': now_ms(), 'load_out': [l for l in r.stdout.splitlines() if l.startswith('loaded')], 'files_after_flush': f})
        summary['tablestats_%d' % n] = nt('tablestats ks.%s' % TABLE).stdout[:1500]
    summary['queries_before_compact'] = query(12345 // SC)
    # compaction: MAJOR_COMPACTION, not FLUSH, so maxMemorySize is the index option (PerSSTableIndexWriter.java:368)
    h = Histo(p.pid, outdir + '/compaction-histo.csv'); h.start()
    summary['t_compact_start'] = now_ms()
    nt('compact ks %s' % TABLE, 3600)
    time.sleep(15)
    summary['t_compact_end'] = now_ms(); h.stop.set(); h.join(30)
    off = phase('compact', off)
    summary['files_after_compact'] = files()
    summary['queries_after_compact'] = query(12345 // SC)
    sh('df -h %s | tail -1' % WORK)
    sh("%s/bin/nodetool -h 127.0.0.1 -p %d tablestats ks.%s | head -30" % (TREE, JMX, TABLE), quiet=False)
    # keep SASI/ERROR lines (not the rejection floods) in the output dir, the full log gzipped on the node
    sh("grep -v -e 'Rejecting value (size' -e \"Can't add term\" %s > %s/system.log.filtered" % (SLOG, outdir), quiet=True)
    sh("gzip -c %s > %s/stage4-logs/pw/%s-system.log.gz" % (SLOG, HOME, label), quiet=True)
except Exception as ex:
    log('ERROR', repr(ex)); summary['error'] = repr(ex)
finally:
    json.dump(summary, open(outdir + '/summary.json', 'w'), indent=1)
    stop_all(); pids.clear(); time.sleep(1)
    shutil.rmtree(WORK, ignore_errors=True)
    log('done', 'error' in summary)
