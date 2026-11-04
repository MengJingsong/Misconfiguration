#!/usr/bin/env python3
"""Cluster tier (B3, amendments B5). Usage: cluster-run.py <outdir> <rows> <heap e.g. 2G> <arms e.g. 1024,8,32,128,def,1024> [datadir-suffix]
One node on 127.0.32.1 (JMX 7332, native 9354, storage 7032; Byteman 9332 unused) from ~/s4-pm, data under ~/s4-pm-data/<suffix>.
Loads ROWS rows (unique int v) into ks.t with no index, flushes, compacts to one sstable, disables autocompaction; then for each arm in order
creates the SASI index (PREFIX) with max_compaction_flush_memory_in_mb = arm (or no option for 'def'), waits for the build, drops the index.
Everything is logged to <outdir>/session.log; the node and the samplers are stopped on any exit."""
import os, sys, time, subprocess, shutil, signal, json, yaml, glob, re, atexit, threading

outdir, rows, heap, arms = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4].split(',')
suffix = sys.argv[5] if len(sys.argv) > 5 else 'cl'
HOME = os.path.expanduser('~')
TREE = os.environ.get('PM_TREE', HOME + '/s4-pm')   # PM_TREE only for shakedowns in a spare copy
HARN = os.path.dirname(os.path.abspath(__file__))
WORK = HOME + '/s4-pm-data/' + suffix
JMX, NATIVE, STORAGE, ADDR = 7332, 9354, 7032, '127.0.32.1'
os.makedirs(outdir, exist_ok=True)
LOG = open(outdir + '/session.log', 'a')
pids = {}
def now_ms(): return int(time.time() * 1000)
def log(*a):
    s = '[%s] %s' % (time.strftime('%FT%T', time.gmtime()) + '.%03dZ' % (now_ms() % 1000), ' '.join(str(x) for x in a))
    LOG.write(s + '\n'); LOG.flush(); print(s, flush=True)
def sh(cmd, timeout=600, check=False, quiet=False):
    log('+', cmd)
    r = subprocess.run(['bash', '-c', cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    if r.stdout.strip() and not quiet:
        LOG.write(r.stdout[-4000:] + '\n'); LOG.flush()
    if check and r.returncode:
        raise RuntimeError('command failed rc=%d: %s' % (r.returncode, cmd))
    return r
def stop_all():
    for name, p in list(pids.items()):
        try: os.kill(p, signal.SIGTERM)
        except Exception: pass
    t0 = time.time()
    while time.time() - t0 < 90 and any(os.path.exists('/proc/%d' % p) for p in pids.values()):
        time.sleep(1)
    for name, p in list(pids.items()):
        if os.path.exists('/proc/%d' % p):
            log('SIGKILL', name, p)
            try: os.kill(p, signal.SIGKILL)
            except Exception: pass
    log('stopped', pids)
atexit.register(stop_all)

def nt(args, timeout=900):
    return sh('%s/bin/nodetool -h 127.0.0.1 -p %d %s' % (TREE, JMX, args), timeout=timeout)

def mkconf():
    d = WORK
    for s in ['data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw', 'logs', 'heapdumps']:
        os.makedirs('%s/%s' % (d, s), exist_ok=True)
    conf = d + '/conf'
    shutil.copytree(TREE + '/conf', conf)
    y = yaml.safe_load(open(conf + '/cassandra.yaml'))
    y.update({'cluster_name': 's4pm', 'num_tokens': 1, 'listen_address': ADDR, 'rpc_address': ADDR,
              'seed_provider': [{'class_name': 'org.apache.cassandra.locator.SimpleSeedProvider', 'parameters': [{'seeds': '%s:%d' % (ADDR, STORAGE)}]}],
              'storage_port': STORAGE, 'native_transport_port': NATIVE, 'sasi_indexes_enabled': True, 'auto_snapshot': False,
              'concurrent_compactors': 1, 'memtable_heap_space': '256MiB',
              'data_file_directories': [d + '/data'], 'commitlog_directory': d + '/commitlog', 'hints_directory': d + '/hints',
              'saved_caches_directory': d + '/saved_caches', 'cdc_raw_directory': d + '/cdc_raw'})
    yaml.safe_dump(y, open(conf + '/cassandra.yaml', 'w'), default_flow_style=False)
    env = open(conf + '/cassandra-env.sh').read().replace('JMX_PORT="7199"', 'JMX_PORT="%d"' % JMX)
    open(conf + '/cassandra-env.sh', 'w').write(env)
    lb = open(conf + '/logback.xml').read().replace('<maxFileSize>50MB</maxFileSize>', '<maxFileSize>4GB</maxFileSize>').replace('<totalSizeCap>5GB</totalSizeCap>', '<totalSizeCap>20GB</totalSizeCap>')
    open(conf + '/logback.xml', 'w').write(lb)
    return d, conf

def start():
    d, conf = mkconf()
    e = dict(os.environ)
    e.update(CASSANDRA_HOME=TREE, CASSANDRA_CONF=conf, CASSANDRA_LOG_DIR=d + '/logs', MAX_HEAP_SIZE=heap, HEAP_NEWSIZE='400M' if False else '', CASSANDRA_HEAPDUMP_DIR=d + '/heapdumps',
             JVM_EXTRA_OPTS='-Dcassandra.ring_delay_ms=5000 -Duser.timezone=UTC')
    e.pop('HEAP_NEWSIZE', None)
    cmd = 'ulimit -n 100000; exec %s/bin/cassandra -f -p %s/pid' % (TREE, d)
    log('start node', cmd)
    p = subprocess.Popen(['bash', '-c', cmd], env=e, stdout=open(d + '/stdout.log', 'w'), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    pids['node'] = p.pid
    return d, p

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

CLASSES = {'builder': 'OnDiskIndexBuilder', 'dttb': 'DynamicTokenTreeBuilder', 'lohs': 'LongOpenHashSet', 'hmnode': 'java.util.HashMap$Node', 'hbb': 'java.nio.HeapByteBuffer', 'bytearr': '[B'}
def parse_histo(txt):
    out = {'total_bytes': None, 'total_inst': None}
    for l in txt.splitlines():
        m = re.match(r'\s*\d+:\s+(\d+)\s+(\d+)\s+(\S+)', l)
        if m:
            inst, by, cls = int(m.group(1)), int(m.group(2)), m.group(3)
            for k, pat in CLASSES.items():
                if (cls == pat) or (k in ('builder', 'dttb', 'lohs') and cls.endswith('.' + pat)):
                    out[k + '_inst'] = out.get(k + '_inst', 0) + inst; out[k + '_bytes'] = out.get(k + '_bytes', 0) + by
        m = re.match(r'\s*Total\s+(\d+)\s+(\d+)', l)
        if m:
            out['total_inst'], out['total_bytes'] = int(m.group(1)), int(m.group(2))
    return out
def histo(pid, tag=None, keep=False):
    r = subprocess.run(['jcmd', str(pid), 'GC.class_histogram'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=600, stdin=subprocess.DEVNULL)
    if keep and tag:
        open('%s/histogram-%s.txt' % (outdir, tag), 'w').write('\n'.join(r.stdout.splitlines()[:40]) + '\n')
    return parse_histo(r.stdout)

class Hist(threading.Thread):
    def __init__(self, pid, path, every):
        super().__init__(daemon=True); self.pid, self.path, self.every, self.stop = pid, path, every, False
    def run(self):
        with open(self.path, 'w') as f:
            while not self.stop:
                t = now_ms()
                try: h = histo(self.pid)
                except Exception as ex: h = {'error': repr(ex)}
                h['epoch_ms'] = t; h['t_done_ms'] = now_ms()
                f.write(json.dumps(h) + '\n'); f.flush()
                for _ in range(int(self.every * 10)):
                    if self.stop: break
                    time.sleep(0.1)

def si_files(d):
    return sorted((os.path.basename(f), os.path.getsize(f)) for f in glob.glob(d + '/data/ks/t-*/*SI_*.db'))
def data_files(d):
    return sorted((os.path.basename(f), os.path.getsize(f)) for f in glob.glob(d + '/data/ks/t-*/*-Data.db'))
def log_lines(path, off, pats):
    with open(path, 'rb') as f:
        f.seek(off); txt = f.read().decode('utf8', 'replace')
    return {p: txt.count(p) for p in pats}
PATS = ['Flushed index segment', 'Index flush to', 'Scheduling index flush', 'OutOfMemoryError', 'Failed to build index segment', 'Failed to flush index', 'reverting to default']

summary = dict(rows=rows, heap=heap, arms=arms, host=os.uname().nodename, arm_results=[])
try:
    log('run rows', rows, 'heap', heap, 'arms', arms, 'host', os.uname().nodename)
    for port in (JMX, NATIVE, STORAGE):
        if sh('ss -ltn | grep -q ":%d "' % port).returncode == 0:
            raise RuntimeError('port %d busy' % port)
    shutil.rmtree(WORK, ignore_errors=True); os.makedirs(WORK)
    sh('mkdir -p %s/sampler && javac -d %s/sampler %s/PoolSampler.java' % (WORK, WORK, HARN), check=True)
    d, p = start()
    if not wait_binary(p): raise RuntimeError('node did not start')
    log('node up'); time.sleep(5)
    slog = d + '/logs/system.log'
    cmdline = open('/proc/%d/cmdline' % p.pid, 'rb').read().replace(b'\0', b' ').decode()
    open(outdir + '/node-cmdline.txt', 'w').write(cmdline + '\n')
    summary['xmx'] = re.findall(r'-Xmx\S+', cmdline); summary['xms'] = re.findall(r'-Xms\S+', cmdline)
    smp = subprocess.Popen(['java', '-cp', WORK + '/sampler', 'PoolSampler', str(JMX), outdir + '/pool.csv', '250'],
                           stdout=open(outdir + '/sampler.out', 'w'), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    pids['sampler'] = smp.pid
    time.sleep(5)
    # phase 0: load without an index, flush, compact to one sstable
    summary['t_load_start'] = now_ms()
    r = sh('python3 %s/loader.py %s %s %d %d' % (HARN, TREE, ADDR, NATIVE, rows), timeout=7200, check=True)
    summary['t_load_end'] = now_ms()
    summary['load_out'] = [l for l in r.stdout.splitlines() if l.startswith('loaded')]
    nt('flush ks t'); time.sleep(3)
    summary['sstables_after_load_flush'] = len(data_files(d))
    nt('compact ks t', 3600); time.sleep(3)
    nt('disableautocompaction ks t')
    summary['data_files'] = data_files(d)
    summary['si_before'] = si_files(d)
    if len(summary['data_files']) != 1: raise RuntimeError('expected exactly one sstable, got %s' % summary['data_files'])
    nt('tablestats ks.t | head -40')
    summary['idle_histo'] = histo(p.pid, 'idle', keep=True)
    for n, arm in enumerate(arms):
        label = 'a%d-%s' % (n + 1, arm)
        a = dict(label=label, cap_mb=arm)
        sh('jcmd %d GC.run' % p.pid, quiet=True); time.sleep(3)
        a['baseline_histo'] = histo(p.pid)
        off = os.path.getsize(slog)
        hs = Hist(p.pid, '%s/histo-%s.jsonl' % (outdir, label), 0.5); hs.start()
        a['t_start'] = now_ms()
        opts = "'mode':'SPARSE'" + ('' if arm == 'def' else ",'max_compaction_flush_memory_in_mb':'%s'" % arm)
        sh('python3 %s/cql.py %s %s %d "CREATE CUSTOM INDEX t_v ON ks.t(v) USING \'org.apache.cassandra.index.sasi.SASIIndex\' WITH OPTIONS = {%s}"' % (HARN, TREE, ADDR, NATIVE, opts), check=True, timeout=600)
        a['options'] = opts
        tmax = time.time() + 3600; done = False
        while time.time() < tmax:
            c = log_lines(slog, off, PATS)
            if c['Index flush to'] >= 1 and c['Scheduling index flush'] >= 1:
                done = True; break
            if p.poll() is not None: raise RuntimeError('node died during arm %s' % label)
            if c['OutOfMemoryError']: break
            time.sleep(2)
        a['t_end'] = now_ms()
        time.sleep(8)
        hs.stop; hs.stop = True; hs.join(timeout=60)
        a['done'] = done
        a['log'] = log_lines(slog, off, PATS)
        a['si_after'] = si_files(d)
        a['compactionstats'] = nt('compactionstats').stdout[-600:]
        a['after_histo'] = histo(p.pid, label + '-after', keep=True)
        sh("tail -c +%d %s | grep -e 'Index flush to' -e 'Flushed index segment' > %s/segments-%s.txt" % (off + 1, slog, outdir, label), quiet=True)
        sh("tail -c +%d %s | grep -e 'OutOfMemory' -e '^ERROR' -e '^WARN.*SASI' > %s/errors-%s.txt" % (off + 1, slog, outdir, label), quiet=True)
        sh('python3 %s/cql.py %s %s %d "DROP INDEX ks.t_v"' % (HARN, TREE, ADDR, NATIVE), check=True)
        time.sleep(5)
        a['si_after_drop'] = si_files(d)
        summary['arm_results'].append(a)
        json.dump(summary, open(outdir + '/summary.json', 'w'), indent=1)
        if not done: raise RuntimeError('arm %s did not complete' % label)
    sh("grep -v 'Rejecting' %s/logs/system.log > %s/system.log.filtered" % (d, outdir), quiet=True)
    sh('df -h %s | tail -1' % WORK)
except Exception as ex:
    log('ERROR', repr(ex)); summary['error'] = repr(ex)
finally:
    json.dump(summary, open(outdir + '/summary.json', 'w'), indent=1)
    stop_all(); pids.clear(); time.sleep(1)
    if os.environ.get('KEEP_DATA') != '1': shutil.rmtree(WORK, ignore_errors=True)
    log('done')
