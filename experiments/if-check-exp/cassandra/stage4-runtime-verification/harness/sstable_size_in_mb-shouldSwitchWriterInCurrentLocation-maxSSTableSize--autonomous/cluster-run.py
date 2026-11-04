#!/usr/bin/env python3
"""Cluster tier driver for the two MajorLeveledCompactionWriter cases (identical file in both harness folders).
Usage: cluster-run.py <case sml1|lcl2> <tree> <nodedir> <outdir> <arm> [<arm> ...]
One node lifetime for all arms. Auto-compaction stays disabled (B3i). Stops the node on any exit.
Arms  sml1: s5 s20 s80 s160 stcs wide20      lcl2: f10a f2 f31 s40 f10b"""
import sys, os, subprocess, time, json, shutil, signal, resource, re, threading, glob, atexit

case, tree, node, out = sys.argv[1:5]; arms = sys.argv[5:]
HARN = os.path.dirname(os.path.abspath(__file__))
DRIVER = os.path.expanduser('~/stage4-seg/driver/cassandra-driver-3.29.0')
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

NT = os.path.join(tree, 'bin/nodetool')
PIDF = os.path.join(node, 'cassandra.pid')
def daemons(): 
    o = subprocess.run("ps -eo pid,args | grep '[j]ava.*%s.*CassandraDaemon' | awk '{print $1}'" % tree, shell=True, stdout=subprocess.PIPE, text=True).stdout.split()
    return o
def stop_node():
    if os.path.exists(PIDF):
        pid = int(open(PIDF).read().strip())
        try:
            os.kill(pid, 0)
            log('stopping node: nodetool drain'); subprocess.run([NT, 'drain'], timeout=180, stdout=LOG, stderr=LOG, stdin=subprocess.DEVNULL)
            os.kill(pid, signal.SIGTERM)
            for _ in range(60):
                try: os.kill(pid, 0); time.sleep(1)
                except OSError: break
            else: os.kill(pid, signal.SIGKILL)
        except OSError: pass
    log('daemons left:', daemons())
atexit.register(stop_node)

SPEC = {
  'sml1': dict(kind='part', phases=8, per_phase=5000, schema='(pk bigint, ck int, v blob, PRIMARY KEY (pk, ck))', total_rows=400000),
  'lcl2': dict(kind='flat', phases=6, per_phase=100000, schema='(id bigint PRIMARY KEY, v blob)', total_rows=600000),
}[case]
LCS = lambda size=None, fan=None: "{'class':'LeveledCompactionStrategy'%s%s}" % ((",'sstable_size_in_mb':'%s'" % size) if size else '', (",'fanout_size':'%s'" % fan) if fan else '')
ARMDEF = {
  'sml1': {'s5': LCS(5), 's20': LCS(20), 's80': LCS(80), 's160': LCS(), 'stcs': "{'class':'SizeTieredCompactionStrategy'}", 'wide20': LCS(20)},
  'lcl2': {'f10a': LCS(10, 10), 'f2': LCS(10, 2), 'f31': LCS(10, 31), 's40': LCS(40, 10), 'f10b': LCS(10, 10)},
}[case]

# ---- node ----
def setup_node():
    shutil.rmtree(node, ignore_errors=True)
    for d in ('data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw', 'logs'): os.makedirs(os.path.join(node, d))
    shutil.copytree(os.path.join(tree, 'conf'), os.path.join(node, 'conf'))
    y = os.path.join(node, 'conf/cassandra.yaml'); txt = open(y).read()
    def setkey(k, v):
        nonlocal txt
        if re.search(r'^%s:' % k, txt, re.M): txt = re.sub(r'^%s:.*$' % k, '%s: %s' % (k, v), txt, flags=re.M)
        else: txt += '\n%s: %s\n' % (k, v)
    setkey('compaction_throughput', '0MiB/s'); setkey('auto_snapshot', 'false'); setkey('cdc_enabled', 'false')
    setkey('commitlog_directory', node + '/commitlog'); setkey('hints_directory', node + '/hints'); setkey('saved_caches_directory', node + '/saved_caches')
    setkey('cdc_raw_directory', node + '/cdc_raw')
    txt = re.sub(r'^data_file_directories:\n(\s+-.*\n)?', '', txt, flags=re.M)
    txt += '\ndata_file_directories:\n    - %s/data\n' % node
    open(y, 'w').write(txt)
    shutil.copy(y, os.path.join(out, 'cassandra.yaml.used'))
    for k in ('compaction_throughput', 'auto_snapshot', 'data_file_directories', 'commitlog_directory'):
        assert len(re.findall(r'^%s:' % k, txt, re.M)) == 1, k
def start_node():
    assert not daemons(), 'a daemon of this tree is already running'
    env = dict(os.environ, MAX_HEAP_SIZE='2G', HEAP_NEWSIZE='512M', CASSANDRA_CONF=node + '/conf', CASSANDRA_LOG_DIR=node + '/logs')
    log('+ bin/cassandra -p', PIDF, '(ulimit -n %d)' % resource.getrlimit(resource.RLIMIT_NOFILE)[0])
    subprocess.run([os.path.join(tree, 'bin/cassandra'), '-p', PIDF], env=env, stdout=open(node + '/logs/stdout.log', 'w'), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=60)
    for i in range(60):
        time.sleep(5)
        if not daemons(): raise RuntimeError('daemon died during start')
        st = subprocess.run([NT, 'status'], stdout=subprocess.PIPE, text=True, stderr=subprocess.DEVNULL).stdout
        sb = subprocess.run([NT, 'statusbinary'], stdout=subprocess.PIPE, text=True, stderr=subprocess.DEVNULL).stdout.strip()
        if re.search(r'^UN', st, re.M) and sb == 'running': log('node up'); return
    raise RuntimeError('node did not come up')

# ---- cql ----
sys.path.insert(0, DRIVER)
def cql(stmt):
    from cassandra.cluster import Cluster
    from cassandra.policies import DCAwareRoundRobinPolicy
    c = Cluster(['127.0.0.1'], protocol_version=5, load_balancing_policy=DCAwareRoundRobinPolicy(local_dc='datacenter1'), token_metadata_enabled=False)
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
    o = os.path.join(out, label); os.makedirs(o, exist_ok=True)
    tbl = 't_' + label
    S = {}
    log('=== arm', label, 'table', tbl)
    cql("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    cql('CREATE TABLE ks.%s %s WITH compression = {\'enabled\':\'false\'} AND compaction = %s' % (tbl, SPEC['schema'], ARMDEF[label]))
    opts = cql("SELECT compaction FROM system_schema.tables WHERE keyspace_name='ks' AND table_name='%s'" % tbl)
    S['compaction_option'] = dict(opts[0].compaction); log('DESCRIBE compaction =', S['compaction_option'])
    sh([NT, 'disableautocompaction', 'ks', tbl])
    tdir_glob = node + '/data/ks/' + tbl + '-*'
    # load
    t0 = time.time(); per = int(os.environ.get('STAGE4_PER_PHASE', SPEC['per_phase']))
    for ph in range(SPEC['phases']):
        procs = []; q = per // 4
        for w in range(4):
            procs.append(loader([SPEC['kind'], tbl, ph * per + w * q, q if w < 3 else per - 3 * q]))
        for p in procs:
            o_ = p.communicate()[0]; log(o_.strip()[-200:]); assert p.returncode == 0, 'loader failed'
        sh([NT, 'flush', 'ks', tbl], quiet=True)
    if label == 'wide20':
        p = loader(['wide', tbl, -1, 60]); o_ = p.communicate()[0]; log(o_.strip()); assert p.returncode == 0
        sh([NT, 'flush', 'ks', tbl], quiet=True)
    S['load_s'] = round(time.time() - t0, 1)
    tdirs = glob.glob(tdir_glob); assert len(tdirs) == 1, tdirs; tdir = tdirs[0]
    pre = sorted(glob.glob(tdir + '/*-Data.db')); S['input_files'] = len(pre); S['input_bytes'] = sum(os.path.getsize(f) for f in pre)
    S['pre_du_table'] = dsize(tdir)
    log('input: %d Data.db files, %d bytes; table dir %d bytes' % (S['input_files'], S['input_bytes'], S['pre_du_table']))
    sh([NT, 'tablestats', 'ks.' + tbl], quiet=False)
    # sampler
    samples = []; stop = threading.Event()
    def samp():
        while not stop.is_set():
            samples.append((int(time.time() * 1000), dsize(tdir), dsize(node + '/data'), dsize(node + '/commitlog'))); stop.wait(0.25)
    th = threading.Thread(target=samp); th.start()
    syslog = node + '/logs/system.log'; off = os.path.getsize(syslog)
    t1 = int(time.time() * 1000)
    outc = sh([NT, 'compact', 'ks', tbl], timeout=3600)
    t2 = int(time.time() * 1000)
    time.sleep(3)
    stop.set(); th.join()
    S['compact_ms'] = t2 - t1
    cs = sh([NT, 'compactionstats'], quiet=False)
    S['compactionstats_idle'] = bool(re.search(r'pending tasks\s+0', cs)) and 'compactions completed' in cs
    with open(syslog, errors='replace') as f: f.seek(off); newlog = f.read()
    open(os.path.join(o, 'system.log.segment'), 'w').write(newlog)
    S['compacted_lines'] = [l for l in newlog.splitlines() if 'Compacted (' in l and tbl in l]
    S['errors_in_log'] = [l for l in newlog.splitlines() if l.startswith('ERROR')][:5]
    with open(os.path.join(o, 'du.csv'), 'w') as f:
        f.write('epoch_ms,table_dir_bytes,node_data_bytes,commitlog_bytes\n')
        for r in samples: f.write(','.join(str(x) for x in r) + '\n')
    S['du_table_peak'] = max(r[1] for r in samples if r[0] >= t1 - 1000); S['du_table_end'] = samples[-1][1]
    S['du_table_in_window'] = [r[1] for r in samples if t1 <= r[0] <= t2]
    S['du_node_peak'] = max(r[2] for r in samples if r[0] >= t1 - 1000)
    files = sorted(glob.glob(tdir + '/*-Data.db'))
    sizes = [os.path.getsize(f) for f in files]
    lv = {}
    md = sh([os.path.join(tree, 'tools/bin/sstablemetadata')] + files, quiet=True)
    open(os.path.join(o, 'sstablemetadata.out'), 'w').write(md)
    cur = None
    for line in md.splitlines():
        m = re.match(r'SSTable: (.*)-Data', line) or re.match(r'SSTable: (.*?)(-big)?$', line)
        if line.startswith('SSTable:'): cur = os.path.basename(line.split(':', 1)[1].strip())
        if line.startswith('SSTable Level:') and cur: lv[cur] = int(line.split(':')[1])
    rows = []
    for f, sz in zip(files, sizes):
        key = os.path.basename(f).replace('-Data.db', '')
        level = next((v for k, v in lv.items() if os.path.basename(k).startswith(key) or key in k), None)
        rows.append((key, sz, level))
    with open(os.path.join(o, 'files.csv'), 'w') as f:
        f.write('file,data_bytes,level\n')
        for r in rows: f.write('%s,%d,%s\n' % r)
    S['files'] = len(files); S['bytes'] = sum(sizes); S['levels'] = {str(l): sum(1 for r in rows if r[2] == l) for l in sorted({r[2] for r in rows if r[2] is not None})}
    S['sizes_sorted_desc'] = sorted(sizes, reverse=True)[:5]
    ts = sh([NT, 'tablestats', 'ks.' + tbl], quiet=True); open(os.path.join(o, 'tablestats.after'), 'w').write(ts)
    rc = loader(['count', tbl, SPEC['kind']]); o_ = rc.communicate()[0]; log(o_.strip()[-100:])
    S['readback'] = int(re.search(r'COUNT (\d+)', o_).group(1))
    S['expected_rows'] = (SPEC['phases'] * per * (10 if SPEC['kind'] == 'part' else 1)) + (60 if label == 'wide20' else 0)
    cql('DROP TABLE ks.' + tbl)
    json.dump(S, open(os.path.join(o, 'summary.json'), 'w'), indent=1)
    log('ARM %s: files=%d bytes=%d levels=%s peak_table_du=%d input=%d compact_ms=%d readback=%d/%d' % (label, S['files'], S['bytes'], S['levels'], S['du_table_peak'], S['input_bytes'], S['compact_ms'], S['readback'], S['expected_rows']))
    time.sleep(5)

log('cluster-run start case=%s tree=%s head=%s arms=%s' % (case, tree, subprocess.run(['git', '-C', tree, 'rev-parse', '--short', 'HEAD'], stdout=subprocess.PIPE, text=True).stdout.strip(), arms))
log('df:', subprocess.run(['df', '-T', os.path.expanduser('~')], stdout=subprocess.PIPE, text=True).stdout.splitlines()[-1])
for p in (7000, 7199, 9042):
    if subprocess.run("ss -ltn | grep -q ':%d '" % p, shell=True).returncode == 0: raise SystemExit('port %d busy' % p)
setup_node(); start_node()
try:
    for a in arms: run_arm(a)
finally:
    stop_node()
log('cluster-run done')
