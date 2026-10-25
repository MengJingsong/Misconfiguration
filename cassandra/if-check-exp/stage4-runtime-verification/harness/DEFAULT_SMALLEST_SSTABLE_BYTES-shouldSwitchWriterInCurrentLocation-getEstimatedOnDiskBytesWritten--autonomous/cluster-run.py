#!/usr/bin/env python3
"""Cluster tier driver for DEFAULT_SMALLEST_SSTABLE_BYTES-shouldSwitchWriterInCurrentLocation-getEstimatedOnDiskBytesWritten--autonomous (B3, as amended B3i).
Usage: cluster-run.py <tree> <nodedir> <outdir> <arm> [<arm> ...]
One node lifetime per call (the node runs from <tree>'s build/). Auto-compaction stays disabled. The node is stopped on any exit.
Arms: plain (STCS, nodetool compact), split (STCS, compact -s), split2 (repeat), splitz (STCS compressed, compact -s),
      small (STCS small data, compact -s), lcs100 / lcs50 (LCS sstable_size_in_mb, nodetool compact; positive control)
The node listens on 127.0.0.77 (JMX 127.0.0.1:7277) so it cannot clash with another run on the host."""
import sys, os, subprocess, time, json, shutil, signal, resource, re, threading, glob, atexit

tree, node, out = sys.argv[1:4]; arms = sys.argv[4:]
HARN = os.path.dirname(os.path.abspath(__file__))
DRIVER = os.path.expanduser('~/s4-ss/driver/cassandra-driver-3.29.0')
HOST = '127.0.0.77'; JMX = '7277'
os.environ['STAGE4_HOST'] = HOST
resource.setrlimit(resource.RLIMIT_NOFILE, (100000, 100000))
os.makedirs(out, exist_ok=True)
LOG = open(os.path.join(out, 'session.log'), 'a')
def log(*a):
    m = '[%s] %s' % (time.strftime('%FT%T%z'), ' '.join(str(x) for x in a)); print(m, flush=True); LOG.write(m + '\n'); LOG.flush()
def sh(cmd, check=True, timeout=None, quiet=False):
    log('+', cmd if isinstance(cmd, str) else ' '.join(cmd))
    t0 = time.time()
    p = subprocess.run(cmd, shell=isinstance(cmd, str), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    if not quiet: log(p.stdout.strip()[-3000:])
    log('  exit', p.returncode, 'in %.1fs' % (time.time() - t0))
    if check and p.returncode: raise RuntimeError('command failed: %s' % cmd)
    return p.stdout

NT = [os.path.join(tree, 'bin/nodetool'), '-h', '127.0.0.1', '-p', JMX]
PIDF = os.path.join(node, 'cassandra.pid')
def daemons():
    return subprocess.run("ps -eo pid,args | grep '[j]ava.*%s.*CassandraDaemon' | awk '{print $1}'" % tree, shell=True, stdout=subprocess.PIPE, text=True).stdout.split()
def stop_node():
    if os.path.exists(PIDF):
        pid = int(open(PIDF).read().strip())
        try:
            os.kill(pid, 0)
            log('stopping node: nodetool drain'); subprocess.run(NT + ['drain'], timeout=180, stdout=LOG, stderr=LOG, stdin=subprocess.DEVNULL)
            os.kill(pid, signal.SIGTERM)
            for _ in range(60):
                try: os.kill(pid, 0); time.sleep(1)
                except OSError: break
            else: os.kill(pid, signal.SIGKILL)
        except OSError: pass
    log('daemons left:', daemons())
atexit.register(stop_node)

STCS = "{'class':'SizeTieredCompactionStrategy'}"
LCS = lambda size: "{'class':'LeveledCompactionStrategy','sstable_size_in_mb':'%s'}" % size
BIG = dict(phases=8, per=int(os.environ.get('STAGE4_PER_PHASE', 25000)))
SMALL = dict(phases=8, per=int(os.environ.get('STAGE4_PER_PHASE_SMALL', 1100)))
ARMDEF = {
  'plain':  dict(comp=STCS, nt=['compact'], data=BIG, compressed=False),
  'split':  dict(comp=STCS, nt=['compact', '-s'], data=BIG, compressed=False),
  'split2': dict(comp=STCS, nt=['compact', '-s'], data=BIG, compressed=False),
  'splitz': dict(comp=STCS, nt=['compact', '-s'], data=BIG, compressed=True),
  'small':  dict(comp=STCS, nt=['compact', '-s'], data=SMALL, compressed=False),
  'lcs100': dict(comp=LCS(100), nt=['compact'], data=BIG, compressed=False),
  'lcs50':  dict(comp=LCS(50), nt=['compact'], data=BIG, compressed=False),
}

def setup_node():
    shutil.rmtree(node, ignore_errors=True)
    for d in ('data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw', 'logs'): os.makedirs(os.path.join(node, d))
    shutil.copytree(os.path.join(tree, 'conf'), os.path.join(node, 'conf'))
    y = os.path.join(node, 'conf/cassandra.yaml'); txt = open(y).read()
    def setkey(k, v):
        nonlocal txt
        if re.search(r'^%s:' % k, txt, re.M): txt = re.sub(r'^%s:.*$' % k, '%s: %s' % (k, v), txt, flags=re.M)
        else: txt += '\n%s: %s\n' % (k, v)
    setkey('compaction_throughput', '0MiB/s'); setkey('auto_snapshot', 'false'); setkey('cdc_enabled', 'false'); setkey('concurrent_compactors', '1')
    setkey('listen_address', HOST); setkey('rpc_address', HOST)
    txt = re.sub(r'(- seeds:) ".*"', r'\1 "%s:7000"' % HOST, txt)
    setkey('commitlog_directory', node + '/commitlog'); setkey('hints_directory', node + '/hints'); setkey('saved_caches_directory', node + '/saved_caches')
    setkey('cdc_raw_directory', node + '/cdc_raw')
    txt = re.sub(r'^data_file_directories:\n(\s+-.*\n)?', '', txt, flags=re.M)
    txt += '\ndata_file_directories:\n    - %s/data\n' % node
    open(y, 'w').write(txt)
    shutil.copy(y, os.path.join(out, 'cassandra.yaml.used'))
    env = os.path.join(node, 'conf/cassandra-env.sh'); e = open(env).read()
    assert re.search(r'^JMX_PORT=', e, re.M), 'JMX_PORT line not found'
    e = re.sub(r'^JMX_PORT=.*$', 'JMX_PORT="%s"' % JMX, e, flags=re.M); open(env, 'w').write(e)
    for k in ('compaction_throughput', 'auto_snapshot', 'data_file_directories', 'commitlog_directory', 'listen_address', 'rpc_address', 'concurrent_compactors'):
        assert len(re.findall(r'^%s:' % k, txt, re.M)) == 1, k
def start_node():
    assert not daemons(), 'a daemon of this tree is already running'
    env = dict(os.environ, MAX_HEAP_SIZE='2G', HEAP_NEWSIZE='512M', CASSANDRA_CONF=node + '/conf', CASSANDRA_LOG_DIR=node + '/logs')
    log('+ bin/cassandra -p', PIDF, '(ulimit -n %d)' % resource.getrlimit(resource.RLIMIT_NOFILE)[0])
    subprocess.run([os.path.join(tree, 'bin/cassandra'), '-p', PIDF], env=env, stdout=open(node + '/logs/stdout.log', 'w'), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=60)
    for i in range(60):
        time.sleep(5)
        if not daemons(): raise RuntimeError('daemon died during start')
        st = subprocess.run(NT + ['status'], stdout=subprocess.PIPE, text=True, stderr=subprocess.DEVNULL).stdout
        sb = subprocess.run(NT + ['statusbinary'], stdout=subprocess.PIPE, text=True, stderr=subprocess.DEVNULL).stdout.strip()
        if re.search(r'^UN', st, re.M) and sb == 'running': log('node up'); return
    raise RuntimeError('node did not come up')

sys.path.insert(0, DRIVER)
def cql(stmt):
    from cassandra.cluster import Cluster
    from cassandra.policies import DCAwareRoundRobinPolicy
    c = Cluster([HOST], protocol_version=5, load_balancing_policy=DCAwareRoundRobinPolicy(local_dc='datacenter1'), token_metadata_enabled=False)
    s = c.connect()
    try:
        r = s.execute(stmt, timeout=300); return list(r) if r else []
    finally: c.shutdown()
def dsize(path):
    t = 0
    for dp, dn, fn in os.walk(path):
        for f in fn:
            try: t += os.stat(os.path.join(dp, f)).st_size
            except OSError: pass
    return t
def loader(args):
    return subprocess.Popen([sys.executable, os.path.join(HARN, 'loader.py'), DRIVER] + [str(a) for a in args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL)

def run_arm(label):
    A = ARMDEF[label]; o = os.path.join(out, label); os.makedirs(o, exist_ok=True)
    tbl = 't_' + label
    S = dict(arm=label, nodetool_args=A['nt'], compressed=A['compressed'])
    log('=== arm', label, 'table', tbl)
    cql("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    cql("CREATE TABLE ks.%s (pk bigint, ck int, v blob, PRIMARY KEY (pk, ck)) WITH compaction = %s%s" % (tbl, A['comp'], '' if A['compressed'] else " AND compression = {'enabled':'false'}"))
    opts = cql("SELECT compaction, compression FROM system_schema.tables WHERE keyspace_name='ks' AND table_name='%s'" % tbl)
    S['compaction_option'] = dict(opts[0].compaction); S['compression_option'] = dict(opts[0].compression); log('DESCRIBE', S['compaction_option'], S['compression_option'])
    sh(NT + ['disableautocompaction', 'ks', tbl])
    tdir_glob = node + '/data/ks/' + tbl + '-*'
    t0 = time.time(); per = A['data']['per']; phases = A['data']['phases']
    for ph in range(phases):
        procs = []; q = per // 4
        for w in range(4):
            procs.append(loader(['part', tbl, ph * per + w * q, q if w < 3 else per - 3 * q]))
        for p in procs:
            o_ = p.communicate()[0]; log(o_.strip()[-200:]); assert p.returncode == 0, 'loader failed'
        sh(NT + ['flush', 'ks', tbl], quiet=True)
    S['load_s'] = round(time.time() - t0, 1); S['partitions_loaded'] = phases * per; S['rows_loaded'] = phases * per * 10
    tdirs = glob.glob(tdir_glob); assert len(tdirs) == 1, tdirs; tdir = tdirs[0]
    pre = sorted(glob.glob(tdir + '/*-Data.db')); S['input_files'] = len(pre); S['input_bytes'] = sum(os.path.getsize(f) for f in pre)
    S['input_gen_max'] = max(int(re.search(r'-(\d+)-big-Data', f).group(1)) for f in pre)
    S['pre_du_table'] = dsize(tdir)
    log('input: %d Data.db files, %d bytes; table dir %d bytes' % (S['input_files'], S['input_bytes'], S['pre_du_table']))
    sh(NT + ['tablestats', 'ks.' + tbl], quiet=False)
    sh(NT + ['setlogginglevel', 'org.apache.cassandra.db.compaction.writers', 'DEBUG'], quiet=True)
    sh(NT + ['setlogginglevel', 'org.apache.cassandra.db.Directories', 'DEBUG'], quiet=True)
    pid = int(open(PIDF).read().strip())
    # samplers: table dir / node data / commit log every 0.25 s; RssAnon every 0.5 s; jcmd GC.heap_info every ~1 s
    samples = []; rss = []; stop = threading.Event()
    def samp():
        while not stop.is_set():
            samples.append((int(time.time() * 1000), dsize(tdir), dsize(node + '/data'), dsize(node + '/commitlog'))); stop.wait(0.25)
    def rsamp():
        while not stop.is_set():
            try:
                for l in open('/proc/%d/status' % pid):
                    if l.startswith('RssAnon:'): rss.append((int(time.time() * 1000), int(l.split()[1]))); break
            except OSError: pass
            stop.wait(0.5)
    heap = []
    def hsamp():  # jstat cannot attach (PerfDisableSharedMem), so `jcmd GC.heap_info` is sampled; it does not force a collection
        while not stop.is_set():
            try:
                r = subprocess.run(['jcmd', str(pid), 'GC.heap_info'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30, stdin=subprocess.DEVNULL).stdout
                m = re.search(r'total (\d+)K, used (\d+)K', r)
                if m: heap.append((int(time.time() * 1000), int(m.group(2))))
            except Exception: pass
            stop.wait(0.5)
    th = [threading.Thread(target=samp), threading.Thread(target=rsamp), threading.Thread(target=hsamp)]
    for t in th: t.start()
    dbg = node + '/logs/debug.log'; sysl = node + '/logs/system.log'; doff = os.path.getsize(dbg); soff = os.path.getsize(sysl)
    t1 = int(time.time() * 1000)
    sh(NT + A['nt'] + ['ks', tbl], timeout=3600)
    t2 = int(time.time() * 1000)
    time.sleep(3)
    stop.set(); [t.join() for t in th]
    S['compact_ms'] = t2 - t1
    cs = sh(NT + ['compactionstats'], quiet=False)
    S['compactionstats_idle'] = bool(re.search(r'pending tasks\s+0', cs)) and 'compactions completed' in cs
    assert os.path.getsize(dbg) >= doff and os.path.getsize(sysl) >= soff, 'log rolled during the arm'
    with open(dbg, errors='replace') as f: f.seek(doff); dlog = f.read()
    with open(sysl, errors='replace') as f: f.seek(soff); slog = f.read()
    open(os.path.join(o, 'debug.log.segment'), 'w').write(dlog); open(os.path.join(o, 'system.log.segment'), 'w').write(slog)
    S['compacted_lines'] = [l for l in slog.splitlines() if 'Compacted (' in l and tbl in l]
    S['errors_in_log'] = [l for l in slog.splitlines() if l.startswith('ERROR')][:5]
    S['switch_lines'] = [int(m.group(1)) for m in re.finditer(r'Switching writer, currentBytesToWrite = (\d+)', dlog)]
    S['space_check_lines'] = [dict(available=int(m.group(1)), asked=int(m.group(2))) for m in re.finditer(r'has (\d+) bytes available, checking if we can write (\d+) bytes', dlog)]
    S['space_warnings'] = [l for l in (dlog + slog).splitlines() if 'Not enough space' in l or 'insufficient space' in l or 'has only' in l][:5]
    with open(os.path.join(o, 'du.csv'), 'w') as f:
        f.write('epoch_ms,table_dir_bytes,node_data_bytes,commitlog_bytes\n')
        for r in samples: f.write(','.join(str(x) for x in r) + '\n')
    with open(os.path.join(o, 'rss.csv'), 'w') as f:
        f.write('epoch_ms,rss_anon_kb\n')
        for r in rss: f.write('%d,%d\n' % r)
    win = lambda rows: [r for r in rows if t1 - 1000 <= r[0] <= t2 + 3000]
    S['du_table_peak'] = max(r[1] for r in win(samples)); S['du_table_end'] = samples[-1][1]
    S['du_node_peak'] = max(r[2] for r in win(samples))
    S['rss_anon_peak_kb'] = max(r[1] for r in win(rss)) if win(rss) else None
    with open(os.path.join(o, 'heap.csv'), 'w') as f:
        f.write('epoch_ms,heap_used_kb\n')
        for r in heap: f.write('%d,%d\n' % r)
    S['heap_used_peak_kb'] = max([r[1] for r in win(heap)], default=None); S['heap_samples'] = len(win(heap)); S['heap_old_used_peak_kb'] = None
    files = glob.glob(tdir + '/*-Data.db')
    gen = lambda f: int(re.search(r'-(\d+)-big-Data', f).group(1))
    outs = sorted([f for f in files if gen(f) > S['input_gen_max']], key=gen)
    S['files_all'] = len(files); S['outputs'] = len(outs); S['output_sizes_in_creation_order'] = [os.path.getsize(f) for f in outs]
    S['bytes'] = sum(os.path.getsize(f) for f in files)
    S['output_lvls'] = {}
    if 'LeveledCompactionStrategy' in A['comp']:
        md = sh([os.path.join(tree, 'tools/bin/sstablemetadata')] + sorted(files), quiet=True)
        open(os.path.join(o, 'sstablemetadata.out'), 'w').write(md)
        cur = None
        for line in md.splitlines():
            if line.startswith('SSTable:'): cur = os.path.basename(line.split(':', 1)[1].strip())
            if line.startswith('SSTable Level:') and cur: S['output_lvls'][cur] = int(line.split(':')[1])
    ts = sh(NT + ['tablestats', 'ks.' + tbl], quiet=True); open(os.path.join(o, 'tablestats.after'), 'w').write(ts)
    rc = loader(['spot', tbl, 0, phases * per]); o_ = rc.communicate()[0]; log(o_.strip()[-200:])
    S['spot_check_ok'] = rc.returncode == 0
    cql('DROP TABLE ks.' + tbl)
    json.dump(S, open(os.path.join(o, 'summary.json'), 'w'), indent=1)
    log('ARM %s: outputs=%d bytes=%d peak_table_du=%d input=%d compact_ms=%d switches=%d space_asked=%s spot=%s' % (label, S['outputs'], S['bytes'], S['du_table_peak'], S['input_bytes'], S['compact_ms'], len(S['switch_lines']), [x['asked'] for x in S['space_check_lines']], S['spot_check_ok']))
    time.sleep(5)

log('cluster-run start tree=%s head=%s arms=%s' % (tree, subprocess.run(['git', '-C', tree, 'rev-parse', '--short', 'HEAD'], stdout=subprocess.PIPE, text=True).stdout.strip(), arms))
log('constant in this tree:', subprocess.run("grep -n 'DEFAULT_SMALLEST_SSTABLE_BYTES =' %s/src/java/org/apache/cassandra/db/compaction/writers/SplittingSizeTieredCompactionWriter.java" % tree, shell=True, stdout=subprocess.PIPE, text=True).stdout.strip())
log('df:', subprocess.run(['df', '-T', os.path.expanduser('~')], stdout=subprocess.PIPE, text=True).stdout.splitlines()[-1])
for a in arms: assert a in ARMDEF, a
if subprocess.run("ss -ltn | grep -E '127.0.0.77:|:7277 '", shell=True).returncode == 0: raise SystemExit('address/port busy')
setup_node(); start_node()
try:
    for a in arms: run_arm(a)
finally:
    stop_node()
log('cluster-run done')
