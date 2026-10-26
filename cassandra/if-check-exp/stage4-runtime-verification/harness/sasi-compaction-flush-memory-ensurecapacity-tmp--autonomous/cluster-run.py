#!/usr/bin/env python3
"""Cluster tier (B3 as amended, B5.2/B5.3/B5.9) of sasi-compaction-flush-memory-ensurecapacity-tmp--autonomous.
Usage: cluster-run.py <outdir> <heap e.g. 8g> <arms> [rows] [datadir-suffix]
  arms: comma list of name:mode:cap:L, mode CONTAINS|PREFIX|NONE (NONE = table without index), cap = MiB or 'def' (option unset), L = value length.
        e.g. c8:CONTAINS:8:200,p8:PREFIX:8:200,none:NONE:def:200
One node on 127.0.2.1 (JMX 7120, native 9042, storage 7000; Byteman agent port 19120 unused), tree $S4_TREE (default ~/s4-b7-st),
data on /dev/shm/s4-b7-st-data/<suffix>. For each arm: new keyspace + table (autocompaction off), index (unless NONE) created BEFORE the load,
ROWS rows loaded in chunks of 25,000 with `nodetool flush` after each chunk, wait until the memtable index builds are done, full GC + baseline
class histogram, then `nodetool compact` with a class-histogram sampler (every ~1 s) and the pool sampler running; keyspace dropped afterwards.
Everything is logged to <outdir>/session.log; the node and the samplers are stopped on any exit."""
import os, sys, time, subprocess, shutil, signal, json, yaml, glob, re, atexit, threading

outdir, heap, arms = sys.argv[1], sys.argv[2], sys.argv[3].split(',')
rows = int(sys.argv[4]) if len(sys.argv) > 4 else 200000
suffix = sys.argv[5] if len(sys.argv) > 5 else 'cl'
CHUNK = 25000
HOME = os.path.expanduser('~')
TREE = os.environ.get('S4_TREE', HOME + '/s4-b7-st')
HARN = os.path.dirname(os.path.abspath(__file__))
WORK = '/dev/shm/s4-b7-st-data/' + suffix
JMX, NATIVE, STORAGE, ADDR = 7120, 9042, 7000, '127.0.2.1'
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
        LOG.write(r.stdout[-3000:] + '\n'); LOG.flush()
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

def nt(args, timeout=1800):
    return sh('%s/bin/nodetool -h 127.0.0.1 -p %d %s' % (TREE, JMX, args), timeout=timeout)

def mkconf():
    d = WORK
    for s in ['data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw', 'logs', 'heapdumps']:
        os.makedirs('%s/%s' % (d, s), exist_ok=True)
    conf = d + '/conf'
    shutil.copytree(TREE + '/conf', conf)
    y = yaml.safe_load(open(conf + '/cassandra.yaml'))
    y.update({'cluster_name': 's4st', 'num_tokens': 1, 'listen_address': ADDR, 'rpc_address': ADDR,
              'seed_provider': [{'class_name': 'org.apache.cassandra.locator.SimpleSeedProvider', 'parameters': [{'seeds': '%s:%d' % (ADDR, STORAGE)}]}],
              'storage_port': STORAGE, 'native_transport_port': NATIVE, 'sasi_indexes_enabled': True, 'auto_snapshot': False,
              'concurrent_compactors': 1, 'compaction_throughput': '0MiB/s', 'memtable_allocation_type': 'heap_buffers', 'memtable_heap_space': '512MiB',
              'data_file_directories': [d + '/data'], 'commitlog_directory': d + '/commitlog', 'hints_directory': d + '/hints',
              'saved_caches_directory': d + '/saved_caches', 'cdc_raw_directory': d + '/cdc_raw'})
    yaml.safe_dump(y, open(conf + '/cassandra.yaml', 'w'), default_flow_style=False)
    env = open(conf + '/cassandra-env.sh').read().replace('JMX_PORT="7199"', 'JMX_PORT="%d"' % JMX)
    open(conf + '/cassandra-env.sh', 'w').write(env)
    lb = open(conf + '/logback.xml').read().replace('<maxFileSize>50MB</maxFileSize>', '<maxFileSize>2GB</maxFileSize>').replace('<totalSizeCap>5GB</totalSizeCap>', '<totalSizeCap>4GB</totalSizeCap>')
    open(conf + '/logback.xml', 'w').write(lb)
    return d, conf

def start(restart_heap=None):
    global heap
    # restart_heap: the OOM probe restarts the node at a lower heap; autocompaction is off in the restarted JVM (it is a runtime setting)
    if restart_heap:
        d, conf = WORK, WORK + '/conf'; heap = restart_heap
        y = yaml.safe_load(open(conf + '/cassandra.yaml')); y['memtable_heap_space'] = '32MiB'
        yaml.safe_dump(y, open(conf + '/cassandra.yaml', 'w'), default_flow_style=False)
    else:
        d, conf = mkconf()
    e = dict(os.environ)
    bm = '%s/build/lib/jars/byteman-4.0.20.jar' % TREE
    e.update(CASSANDRA_HOME=TREE, CASSANDRA_CONF=conf, CASSANDRA_LOG_DIR=d + '/logs', MAX_HEAP_SIZE=heap, CASSANDRA_HEAPDUMP_DIR=d + '/heapdumps',
             JVM_EXTRA_OPTS=('-Dcassandra.autocompaction_on_startup_enabled=false ' if restart_heap else '') + '-Dcassandra.ring_delay_ms=5000 -Duser.timezone=UTC -javaagent:%s=script:%s/lts.btm -Dstage4.trace=%s/lts-trace.txt' % (bm, HARN, outdir))
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

def parse_histo(txt):
    out = {'total_bytes': None}
    for l in txt.splitlines():
        m = re.match(r'\s*\d+:\s+(\d+)\s+(\d+)\s+(\S+)', l)
        if m:
            by, cls = int(m.group(2)), m.group(3)
            if cls in ('[J', '[C', '[B', '[I'): out[cls] = by
        m = re.match(r'\s*Total\s+(\d+)\s+(\d+)', l)
        if m: out['total_bytes'] = int(m.group(2))
    return out
def histo(pid, tag=None):
    r = subprocess.run(['jcmd', str(pid), 'GC.class_histogram'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=900, stdin=subprocess.DEVNULL)
    if tag: open('%s/histogram-%s.txt' % (outdir, tag), 'w').write('\n'.join(r.stdout.splitlines()[:25]) + '\n')
    return parse_histo(r.stdout)
class Hist(threading.Thread):
    def __init__(self, pid, path, every):
        super().__init__(daemon=True); self.pid, self.path, self.every, self.halt = pid, path, every, False
    def run(self):
        with open(self.path, 'w') as f:
            while not self.halt:
                t = now_ms()
                try: h = histo(self.pid)
                except Exception as ex: h = {'error': repr(ex)}
                h['epoch_ms'] = t; h['t_done_ms'] = now_ms()
                f.write(json.dumps(h) + '\n'); f.flush()
                for _ in range(int(self.every * 10)):
                    if self.halt: break
                    time.sleep(0.1)
def fsize(pattern):
    return sorted((os.path.basename(f), os.path.getsize(f)) for f in glob.glob(pattern))
def log_text(path, off):
    with open(path, 'rb') as f:
        f.seek(off); return f.read().decode('utf8', 'replace')
PATS = ['Flushed index segment', 'Index flush to', 'Scheduling index flush', 'OutOfMemoryError', 'Failed to build index segment', 'Failed to flush index', 'reverting to default']
def counts(path, off):
    t = log_text(path, off); return {p: t.count(p) for p in PATS}

summary = dict(rows=rows, heap=heap, arms=arms, host=os.uname().nodename, tree=TREE, arm_results=[])
try:
    log('run rows', rows, 'heap', heap, 'arms', arms, 'host', os.uname().nodename)
    for pat in (':%d ' % JMX, '%s:%d ' % (ADDR, NATIVE), '%s:%d ' % (ADDR, STORAGE), '%s:7001 ' % ADDR):
        if sh('ss -ltn | grep -q "%s"' % pat).returncode == 0:
            raise RuntimeError('port busy: %s' % pat)
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
    time.sleep(3)
    cql = lambda q, tm=600: sh('python3 %s/cql.py %s %s %d "%s"' % (HARN, TREE, ADDR, NATIVE, q), check=True, timeout=tm)
    for n, spec in enumerate(arms):
        name, mode, cap, L = spec.split(':'); L = int(L)
        ks = 'k_' + name
        a = dict(arm=name, mode=mode, cap=cap, L=L, ks=ks, rows=rows)
        log('=== arm', spec)
        cql("CREATE KEYSPACE %s WITH replication = {'class':'SimpleStrategy','replication_factor':1}" % ks)
        cql("CREATE TABLE %s.t (id bigint PRIMARY KEY, v text)" % ks)
        nt('disableautocompaction %s t' % ks)
        if mode != 'NONE':
            opts = "'mode':'%s'" % mode + ('' if cap == 'def' else ",'max_compaction_flush_memory_in_mb':'%s'" % cap)
            cql("CREATE CUSTOM INDEX t_v ON %s.t(v) USING 'org.apache.cassandra.index.sasi.SASIIndex' WITH OPTIONS = {%s}" % (ks, opts))
            a['options'] = opts
        off0 = os.path.getsize(slog)
        a['t_load_start'] = now_ms()
        nchunks = 0
        for start_row in range(0, rows, CHUNK):
            cnt = min(CHUNK, rows - start_row)
            sh('python3 %s/loader.py %s %s %d %s %d %d %d' % (HARN, TREE, ADDR, NATIVE, ks, start_row, cnt, L), check=True, timeout=1800)
            nt('flush %s t' % ks); nchunks += 1
            if p.poll() is not None: raise RuntimeError('node died during load of %s' % name)
        # wait for the memtable-flush index builds (one 'Index flush to' per sstable)
        t_end = time.time() + 3600
        while mode != 'NONE' and time.time() < t_end:
            c = counts(slog, off0)
            nss = len(fsize('%s/data/%s/t-*/*-Data.db' % (d, ks)))
            if (c['Index flush to'] >= nss and c['Scheduling index flush'] == c['Index flush to'] and nss >= nchunks) or c['OutOfMemoryError'] or p.poll() is not None: break
            time.sleep(3)
        a['t_load_end'] = now_ms()
        a['load_log'] = counts(slog, off0)
        a['sstables'] = fsize('%s/data/%s/t-*/*-Data.db' % (d, ks))
        a['si_after_load'] = fsize('%s/data/%s/t-*/*SI_*.db' % (d, ks))
        if p.poll() is not None: raise RuntimeError('node died after load of %s' % name)
        time.sleep(5)
        if os.environ.get('PROBE_HEAP'):   # OOM probe: load at the main heap, restart at PROBE_HEAP for the compaction
            nt('drain'); stop_all(); pids.clear()
            d, p = start(os.environ['PROBE_HEAP'])
            if not wait_binary(p): raise RuntimeError('node did not restart')
            smp = subprocess.Popen(['java', '-cp', WORK + '/sampler', 'PoolSampler', str(JMX), outdir + '/pool2.csv', '250'], stdout=open(outdir + '/sampler2.out', 'w'), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True); pids['sampler'] = smp.pid
            time.sleep(5); a['restart_heap'] = os.environ['PROBE_HEAP']
        sh('jcmd %d GC.run' % p.pid, quiet=True); time.sleep(3)
        a['baseline'] = histo(p.pid, name + '-baseline')
        off = os.path.getsize(slog)
        hs = Hist(p.pid, '%s/histo-%s.jsonl' % (outdir, name), 1.0); hs.start()
        a['t_compact_start'] = now_ms()
        r = nt('compact %s t' % ks, 7200)
        a['t_compact_end'] = now_ms(); a['compact_rc'] = r.returncode; a['compact_out'] = r.stdout[-300:]
        time.sleep(6)
        hs.halt = True; hs.join(timeout=120)
        a['compact_log'] = counts(slog, off)
        a['node_alive'] = p.poll() is None
        sh("tail -c +%d %s | grep -e 'Index flush to' -e 'Flushed index segment' -e 'Failed to' -e 'OutOfMemory' > %s/segments-%s.txt" % (off + 1, slog, outdir, name), quiet=True)
        if p.poll() is None:
            a['sstables_after'] = fsize('%s/data/%s/t-*/*-Data.db' % (d, ks))
            a['si_after'] = fsize('%s/data/%s/t-*/*SI_*.db' % (d, ks))
            a['after'] = histo(p.pid, name + '-after')
            sh('echo "$(date +%s%3N)" > /dev/null', quiet=True)
            cql("DROP KEYSPACE %s" % ks)
            time.sleep(5)
        summary['arm_results'].append(a)
        json.dump(summary, open(outdir + '/summary.json', 'w'), indent=1)
        if p.poll() is not None:
            log('node died in arm', name); break
    sh("grep -v 'Rejecting' %s/logs/system.log > %s/system.log.filtered" % (d, outdir), quiet=True)
    sh('df -h %s | tail -1' % WORK)
except Exception as ex:
    log('ERROR', repr(ex)); summary['error'] = repr(ex)
finally:
    json.dump(summary, open(outdir + '/summary.json', 'w'), indent=1)
    stop_all(); pids.clear(); time.sleep(1)
    if os.environ.get('KEEP_DATA') != '1': shutil.rmtree(WORK, ignore_errors=True)
    log('done')
