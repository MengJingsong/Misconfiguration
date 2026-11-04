#!/usr/bin/env python3
"""Cluster tier driver (B3 as amended 2026-10-27), case per-partition-limit-incrementRowCount-rowsincurrentpartition--autonomous (tag q77, slot 7). Not upstream code. Usage:
  cluster-run.py <tree> <nodedir> <outdir> load        create ks.t_small (4 x 30000 x 100 B), ks.t_med (4 x 300 x 10 KiB), ks.t_big (4 x 300 x 100 KiB); flush, compact
  cluster-run.py <tree> <nodedir> <outdir> life U|C    one node lifetime: U uncapped; C with read_thresholds_enabled and local_read_size_fail_threshold 20MiB
Own ports: 127.0.7.1, storage 7000, ssl 7001, native 9042, JMX 7170. Stops the node on any exit. A failed first-trigger check stops with exit 3.
Env STAGE4_SCALE=small shrinks the data (shakedown only): t_small 4 x 3000 rows and a smaller query set."""
import sys, os, subprocess, time, json, shutil, signal, resource, re, atexit, random
tree, node, out, mode = sys.argv[1:5]; arg = sys.argv[5] if len(sys.argv) > 5 else None
HARN = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HARN)
import analyze_cluster as ac
DRIVER = os.path.expanduser('~/s4-b11-q77-drv/cassandra-driver-3.29.0')
ADDR, STORAGE, SSL, NATIVE, JMX = '127.0.7.1', 7000, 7001, 9042, 7170
SMALL = os.environ.get('STAGE4_SCALE') == 'small'
if SMALL: ac.PP['t_small'] = 3000
PP, P = ac.PP, ac.P
WID = ac.WIDTH
resource.setrlimit(resource.RLIMIT_NOFILE, (100000, 100000))
os.makedirs(out, exist_ok=True)
LOG = open(os.path.join(out, 'session.log'), 'a')
def log(*a):
    m = '[%s] %s' % (time.strftime('%FT%T%z'), ' '.join(str(x) for x in a)); print(m, flush=True); LOG.write(m + '\n'); LOG.flush()
def sh(cmd, check=True, timeout=None, quiet=False):
    log('+', cmd if isinstance(cmd, str) else ' '.join(cmd))
    t0 = time.time()
    p = subprocess.run(cmd, shell=isinstance(cmd, str), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    if not quiet: log(p.stdout.strip()[-2500:])
    log('  exit', p.returncode, 'in %.1fs' % (time.time() - t0))
    if check and p.returncode: raise RuntimeError('command failed: %s' % cmd)
    return p.stdout
NT = [os.path.join(tree, 'bin/nodetool'), '-p', str(JMX)]
PIDF = os.path.join(node, 'cassandra.pid')
def daemons():
    return subprocess.run("ps -eo pid,args | grep '[j]ava.*%s.*CassandraDaemon' | awk '{print $1}'" % tree, shell=True, stdout=subprocess.PIPE, text=True).stdout.split()
def node_pid():
    try: pid = int(open(PIDF).read().strip()); os.kill(pid, 0); return pid
    except Exception: return None
def stop_node():
    pid = node_pid()
    if pid:
        try:
            log('stopping node: nodetool drain'); subprocess.run(NT + ['drain'], timeout=240, stdout=LOG, stderr=LOG, stdin=subprocess.DEVNULL)
        except Exception as e: log('drain failed', e)
        try:
            os.kill(pid, signal.SIGTERM)
            for _ in range(90):
                try: os.kill(pid, 0); time.sleep(1)
                except OSError: break
            else: os.kill(pid, signal.SIGKILL)
        except OSError: pass
    log('daemons left:', daemons())
atexit.register(stop_node)

def make_conf(label, control):
    conf = node + '/conf'
    shutil.rmtree(conf, ignore_errors=True); shutil.copytree(tree + '/conf', conf)
    lines = {
        'cluster_name': "'q77'", 'num_tokens': '1',
        'data_file_directories': '\n    - %s/data' % node,
        'commitlog_directory': node + '/commitlog', 'hints_directory': node + '/hints', 'saved_caches_directory': node + '/saved_caches', 'cdc_raw_directory': node + '/cdc_raw',
        'listen_address': ADDR, 'rpc_address': ADDR,
        'seed_provider': '\n  - class_name: org.apache.cassandra.locator.SimpleSeedProvider\n    parameters:\n      - seeds: "%s:%d"' % (ADDR, STORAGE),
        'storage_port': str(STORAGE), 'ssl_storage_port': str(SSL), 'native_transport_port': str(NATIVE),
        'row_cache_size': '0MiB', 'key_cache_size': '100MiB', 'counter_cache_size': '0MiB',
        'read_request_timeout': '60000ms', 'native_transport_timeout': '60000ms', 'range_request_timeout': '60000ms',
        'commitlog_total_space': '2GiB', 'auto_snapshot': 'false', 'cdc_enabled': 'false', 'concurrent_compactors': '2',
    }
    if control: lines.update({'read_thresholds_enabled': 'true', 'local_read_size_fail_threshold': '20MiB'})
    outl, skip = [], False
    for l in open(tree + '/conf/cassandra.yaml').read().splitlines():
        m = re.match(r'^([A-Za-z_]+):', l)
        if m:
            skip = m.group(1) in lines
            if skip: continue
        elif skip and (l.startswith((' ', '\t', '-')) or l.strip() == ''): continue
        else: skip = False
        outl.append(l)
    outl.append('# ---- stage4 q77 (B3a as amended) ----'); outl += ['%s: %s' % (k, v) for k, v in lines.items()]
    open(conf + '/cassandra.yaml', 'w').write('\n'.join(outl) + '\n')
    shutil.copy(conf + '/cassandra.yaml', os.path.join(out, 'cassandra.yaml.%s' % label))
    env = open(conf + '/cassandra-env.sh').read(); assert env.count('JMX_PORT="7199"') == 1
    open(conf + '/cassandra-env.sh', 'w').write(env.replace('JMX_PORT="7199"', 'JMX_PORT="%d"' % JMX))
    with open(conf + '/jvm11-server.options', 'a') as f: f.write('\n# stage4 q77\n-XX:+AlwaysPreTouch\n-XX:HeapDumpPath=%s/dumps\n' % node)
    os.makedirs(node + '/dumps', exist_ok=True)
    log('conf %s: control=%s' % (label, control))

def start_node(label):
    if node_pid() or daemons(): raise RuntimeError('a daemon of this tree is running: %s' % daemons())
    for p in (STORAGE, SSL, NATIVE):
        if subprocess.run("ss -ltn | grep -q '%s:%d '" % (ADDR, p), shell=True).returncode == 0: raise SystemExit('port %s:%d busy' % (ADDR, p))
    if subprocess.run("ss -ltn | grep -q ':%d '" % JMX, shell=True).returncode == 0: raise SystemExit('JMX port %d busy' % JMX)
    env = dict(os.environ, MAX_HEAP_SIZE='2G', CASSANDRA_CONF=node + '/conf', CASSANDRA_LOG_DIR=node + '/logs')
    env.pop('HEAP_NEWSIZE', None)
    log('+ bin/cassandra -p', PIDF, '(ulimit -n %d)' % resource.getrlimit(resource.RLIMIT_NOFILE)[0])
    subprocess.run([os.path.join(tree, 'bin/cassandra'), '-p', PIDF], env=env, stdout=open(node + '/logs/stdout-%s.log' % label, 'w'), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=120)
    t0 = time.time()
    while time.time() - t0 < 400:
        time.sleep(4)
        if not node_pid() and time.time() - t0 > 12: raise RuntimeError('daemon died during start')
        st = subprocess.run(NT + ['status'], stdout=subprocess.PIPE, text=True, stderr=subprocess.DEVNULL).stdout
        sb = subprocess.run(NT + ['statusbinary'], stdout=subprocess.PIPE, text=True, stderr=subprocess.DEVNULL).stdout.strip()
        if re.search(r'^UN\s+' + re.escape(ADDR), st, re.M) and sb == 'running':
            log('node up (%s) after %.0f s, pid %s' % (label, time.time() - t0, node_pid())); return node_pid()
    raise RuntimeError('node did not come up')

sys.path.insert(0, DRIVER)
def cql(stmt, timeout=600):
    from cassandra.cluster import Cluster
    from cassandra.policies import DCAwareRoundRobinPolicy
    c = Cluster([ADDR], port=NATIVE, protocol_version=4, load_balancing_policy=DCAwareRoundRobinPolicy(local_dc='datacenter1'), token_metadata_enabled=False)
    s = c.connect()
    try:
        r = s.execute(stmt, timeout=timeout); return list(r) if r else []
    finally: c.shutdown()
def client(*args, timeout=1800):
    p = subprocess.run([sys.executable, '-I', os.path.join(HARN, 'loader.py'), DRIVER, ADDR, str(NATIVE)] + [str(a) for a in args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    return p.returncode, p.stdout

def query(pid, table, L, fetch, rep, tag, extra=None):
    sh(['jcmd', str(pid), 'GC.run'], check=False, quiet=True); time.sleep(3)
    rc, o = client('q', table, L, fetch)
    try: q = json.loads(o.strip().splitlines()[-1])
    except Exception: raise RuntimeError('client output not JSON: %s' % o[-500:])
    q.update(table=table, L=str(L), fetch=str(fetch), rep=rep, tag=tag)
    if extra: q.update(extra)
    time.sleep(1.5)
    return q

def du():
    return int(subprocess.run(['du', '-sb', node + '/data'], stdout=subprocess.PIPE, text=True).stdout.split()[0])

def life(which):
    control = which == 'C'; od = os.path.join(out, which); os.makedirs(od, exist_ok=True)
    syslog = node + '/logs/system.log'; offs = os.path.getsize(syslog) if os.path.exists(syslog) else 0
    make_conf(which, control); start_node(which); pid = node_pid()
    sp = subprocess.Popen(['java', '-cp', os.path.join(out, 'tools'), 'Jmx', str(JMX), 'poll', '25', os.path.join(od, 'alloc.csv')], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    qf = open(os.path.join(od, 'queries.jsonl'), 'w')
    def rec(q): qf.write(json.dumps(q) + '\n'); qf.flush(); log('Q', q['table'], 'n', q['L'], 'fetch', q['fetch'], 'rep', q.get('rep'), 'rows', q['rows'], 'pages', q['pages'], 'err', (q['err'] or '-')[:100])
    rc = 0
    try:
        time.sleep(20)
        if which == 'U':
            shapes = [('t_small', L, 'none') for L in (1, 10, 100, 1000, 10000, 'none')] + [(t, L, 'none') for t in ('t_med', 't_big') for L in (1, 10, 100, 'none')] + [('t_big', 100, 100), ('t_small', 10000, 5000)]
            if SMALL: shapes = [s for s in shapes if s[1] != 10000]
        else:
            shapes = [('t_big', 10, 'none'), ('t_big', 100, 'none'), ('t_big', 'none', 'none'), ('t_med', 'none', 'none'), ('t_small', 10000, 'none')]
            if SMALL: shapes = shapes[:4]
        sh_trig = ('t_big', 100, 'none')
        for (t, L, f) in shapes:        # warm-up: every shape once (kept in the file with warm=true, not in the readings)
            q = query(pid, t, L, f, 0, 'warm', {'warm': True}); rec(q)
        if not control: dbefore = du()
        q = query(pid, *sh_trig, 0, 'trigger', {'trigger': True})
        S = ac.load_samples(os.path.join(od, 'alloc.csv')); A = ac.window_alloc(S, q['t0_ms'], q['t1_ms']); rec(q)
        if not control:
            ok = (not q['err']) and q['rows'] == 400 and A is not None and A >= 40e6
            log('FIRST-TRIGGER CHECK (U: t_big n=100 returns 400 rows, allocates >= 40 MB)', 'ok' if ok else 'FAILED', 'rows', q['rows'], 'A', A)
        else:
            ok = ac.is_abort(q)
            log('FIRST-TRIGGER CHECK (C: t_big n=100 fails with a read-size abort)', 'ok' if ok else 'FAILED', 'err', q['err'])
        if not ok: return 3
        order = [(s, r) for s in shapes for r in (1, 2, 3)]; random.Random(77).shuffle(order)
        for (t, L, f), r in order:
            q = query(pid, t, L, f, r, 'run'); rec(q)
            time.sleep(2)
        if not control:
            open(os.path.join(od, 'du.txt'), 'w').write('before %d\nafter %d\n' % (dbefore, du()))
        sh(NT + ['tablestats', 'ks'], check=False, quiet=True)
    finally:
        sp.terminate(); qf.close()
        with open(syslog, errors='replace') as f: f.seek(offs); seg = f.read()
        open(os.path.join(od, 'system.log.segment'), 'w').write(seg)
        errs = [l for l in seg.splitlines() if l.startswith('ERROR')]; log('ERROR lines in segment:', len(errs), errs[:3])
        log('OOM lines:', len([l for l in seg.splitlines() if 'OutOfMemory' in l]))
        stop_node()
    return rc

shutil.copytree(HARN, os.path.join(out, 'tools_src'), dirs_exist_ok=True)
os.makedirs(os.path.join(out, 'tools'), exist_ok=True); sh(['javac', '-d', os.path.join(out, 'tools'), HARN + '/Jmx.java'])
log('cluster-run start mode=%s %s tree=%s head=%s small=%s' % (mode, arg, tree, subprocess.run(['git', '-C', tree, 'rev-parse', '--short', 'HEAD'], stdout=subprocess.PIPE, text=True).stdout.strip(), SMALL))
log('df:', subprocess.run(['df', '-T', node if os.path.exists(node) else os.path.dirname(node)], stdout=subprocess.PIPE, text=True).stdout.splitlines()[-1])
if mode == 'load':
    shutil.rmtree(node, ignore_errors=True)
    for d in ('data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw', 'logs'): os.makedirs(os.path.join(node, d))
    make_conf('load', False); start_node('load')
    cql("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    t0 = time.time()
    for t in PP:
        cql("CREATE TABLE IF NOT EXISTS ks.%s (pk int, ck int, v blob, PRIMARY KEY (pk, ck)) WITH compression = {'enabled':'false'} AND caching = {'keys':'ALL','rows_per_partition':'NONE'}" % t)
        rc, o = client('load', t, P, PP[t], WID[t]); log(o.strip()[-300:]); assert rc == 0
        sh(NT + ['flush', 'ks', t], quiet=True)
        sh(NT + ['compact', 'ks', t], quiet=True, check=False)
    log('load took %.1fs' % (time.time() - t0))
    log(sh(NT + ['tablestats', 'ks'], check=False, quiet=True)[-2500:])
    for t in PP:
        for pk in range(1, P + 1):
            rows = cql("SELECT count(*) FROM ks.%s WHERE pk = %d" % (t, pk))[0][0]
            assert rows == PP[t], (t, pk, rows)
        log('rows in ks.%s: %d partitions x %d' % (t, P, PP[t]))
    sh(['du', '-sb', node + '/data'], quiet=False)
    sys.exit(0)
if mode == 'life':
    sys.exit(life(arg))
