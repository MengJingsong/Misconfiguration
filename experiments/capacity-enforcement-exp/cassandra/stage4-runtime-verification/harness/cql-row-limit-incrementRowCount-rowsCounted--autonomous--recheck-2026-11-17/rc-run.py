#!/usr/bin/env python3
"""Driver of the recheck run (case cql-row-limit-incrementRowCount-rowsCounted--autonomous, design section
"Stage-4 design for the recheck claim (2026-11-17)", S1-S5). Not upstream code. Runs on pc75 from /mydata/s4/rowlim-rc/harness.
  rc-run.py load       load lifetime (no agent): ks.w16k / ks.w128k / ks.w1m, 600 rows each of 16 KiB / 128 KiB / 1 MiB; flush, compact, count
  rc-run.py life K     instrument check (U settings + probes): L(32, 128 KiB) and P(128, 1 MiB) once each; not a reading
  rc-run.py life U     shipped guardrails + probes: warm-up, first-trigger check, U arms x 3 (seed 75)
  rc-run.py life C     read_thresholds_enabled + local_read_size_fail_threshold 40MiB + probes: warm-up, trigger, C arms x 3
Each lifetime runs the node in `systemd-run --user --scope -p MemoryMax=12G -p MemorySwapMax=0 bin/cassandra -f` and stops it on exit.
Writes <RUN>/logs/<lifetime>/{session.log,queries.jsonl,alloc.csv,memory.csv,histos.txt,marker.txt copy,gc log copy,...}."""
import sys, os, subprocess, time, json, shutil, signal, re, threading, atexit, random, resource
RUN = '/mydata/s4/rowlim-rc'
TREE, NODE = RUN + '/tree', RUN + '/node'
HARN = os.path.dirname(os.path.abspath(__file__))
DRV = RUN + '/drv/cassandra-driver-3.29.0'
TABLES = {'w16k': 16384, 'w128k': 131072, 'w1m': 1048576}
ROWS = 600
PAUSE_MS = 8000
MEMMAX = '12G'
mode = sys.argv[1]; arg = sys.argv[2] if len(sys.argv) > 2 else None
label = 'load' if mode == 'load' else arg
OUT = os.path.join(RUN, 'logs', label)
os.makedirs(OUT, exist_ok=True)
resource.setrlimit(resource.RLIMIT_NOFILE, (100000, 100000))
LOG = open(os.path.join(OUT, 'session.log'), 'a')
def ms(): return int(time.time() * 1000)
def log(*a):
    m = '[%s %d] %s' % (time.strftime('%FT%T%z'), ms(), ' '.join(str(x) for x in a)); print(m, flush=True); LOG.write(m + '\n'); LOG.flush()
def sh(cmd, check=True, timeout=None, quiet=False):
    log('+', cmd if isinstance(cmd, str) else ' '.join(cmd))
    t0 = time.time()
    p = subprocess.run(cmd, shell=isinstance(cmd, str), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    if not quiet: log(p.stdout.strip()[-3000:])
    log('  exit', p.returncode, 'in %.1fs' % (time.time() - t0))
    if check and p.returncode: raise RuntimeError('command failed: %s' % cmd)
    return p.stdout
NT = [TREE + '/bin/nodetool', '-p', '7199']
LDIR = NODE + '/logs-' + label
PIDF = LDIR + '/cassandra.pid'
MARK = LDIR + '/marker.txt'
STATE = {'proc': None, 'unit': None, 'cg': None, 'memmax': 0, 'stop': False}

def daemons():
    return subprocess.run("ps -eo pid,args | grep '[C]assandraDaemon' | grep -F '%s' | awk '{print $1}'" % TREE, shell=True, stdout=subprocess.PIPE, text=True).stdout.split()
def node_pid():
    # bin/cassandra -f writes no pidfile (only the background mode does), so find the daemon of this tree by its command line
    d = daemons()
    return int(d[0]) if len(d) == 1 else None

def make_conf(control):
    conf = NODE + '/conf-' + label
    shutil.rmtree(conf, ignore_errors=True); shutil.copytree(TREE + '/conf', conf)
    lines = {
        'num_tokens': '1',
        'data_file_directories': '\n    - %s/data' % NODE,
        'commitlog_directory': NODE + '/commitlog', 'hints_directory': NODE + '/hints',
        'saved_caches_directory': NODE + '/saved_caches', 'cdc_raw_directory': NODE + '/cdc_raw',
        'row_cache_size': '0MiB', 'counter_cache_size': '0MiB',
        'read_request_timeout': '60000ms', 'native_transport_timeout': '60000ms',
        'auto_snapshot': 'false',
    }
    if control: lines.update({'read_thresholds_enabled': 'true', 'local_read_size_fail_threshold': '40MiB'})
    outl, skip = [], False
    for l in open(TREE + '/conf/cassandra.yaml').read().splitlines():
        m = re.match(r'^([A-Za-z_]+):', l)
        if m:
            skip = m.group(1) in lines
            if skip: continue
        elif skip and (l.startswith((' ', '\t', '-')) or l.strip() == ''): continue
        else: skip = False
        outl.append(l)
    outl.append('# ---- stage4 recheck rowlim-rc (design S1) ----'); outl += ['%s: %s' % (k, v) for k, v in lines.items()]
    open(conf + '/cassandra.yaml', 'w').write('\n'.join(outl) + '\n')
    shutil.copy(conf + '/cassandra.yaml', os.path.join(OUT, 'cassandra.yaml.%s' % label))
    log('conf %s: control=%s; yaml lines changed: %s' % (label, control, sorted(lines)))
    return conf

def mem_sampler():
    f = open(os.path.join(OUT, 'memory.csv'), 'a'); f.write('epoch_ms,memory_current\n')
    while not STATE['stop']:
        cg = STATE['cg']
        if cg:
            try:
                v = int(open('/sys/fs/cgroup' + cg + '/memory.current').read()); STATE['memmax'] = max(STATE['memmax'], v)
                f.write('%d,%d\n' % (ms(), v)); f.flush()
            except Exception: pass
        time.sleep(1)

def start_node(agent):
    if node_pid() or daemons(): raise RuntimeError('a daemon of this tree is running: %s' % daemons())
    for p in (7000, 7199, 9042):
        if subprocess.run("ss -ltn | grep -q ':%d '" % p, shell=True).returncode == 0: raise SystemExit('port %d busy' % p)
    shutil.rmtree(LDIR, ignore_errors=True); os.makedirs(LDIR)
    conf = make_conf(label == 'C')
    extra = '-Xlog:gc:file=%s/gc-%s.log:time,uptimemillis' % (LDIR, label)
    if agent:
        extra += ' -javaagent:%s/build/lib/jars/byteman-4.0.20.jar=script:%s/probes.btm -Ds4rc.pause_ms=%d -Ds4rc.marker=%s' % (TREE, HARN, PAUSE_MS, MARK)
    env = dict(os.environ, MAX_HEAP_SIZE='8G', CASSANDRA_CONF=conf, CASSANDRA_LOG_DIR=LDIR, JVM_EXTRA_OPTS=extra)
    env.pop('HEAP_NEWSIZE', None)
    unit = 's4rc-%s-%d' % (label, int(time.time())); STATE['unit'] = unit
    cmd = ['systemd-run', '--user', '--scope', '--unit=' + unit, '-p', 'MemoryMax=' + MEMMAX, '-p', 'MemorySwapMax=0',
           TREE + '/bin/cassandra', '-f', '-p', PIDF]
    log('+', ' '.join(cmd), '| JVM_EXTRA_OPTS=' + extra, '| MAX_HEAP_SIZE=8G')
    STATE['proc'] = subprocess.Popen(cmd, env=env, stdout=open(LDIR + '/stdout.log', 'w'), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    t0 = time.time()
    while time.time() - t0 < 400:
        time.sleep(4)
        if STATE['proc'].poll() is not None: raise RuntimeError('daemon died during start (exit %s)' % STATE['proc'].returncode)
        if not STATE['cg']:
            cg = subprocess.run(['systemctl', '--user', 'show', '-p', 'ControlGroup', '--value', unit + '.scope'], stdout=subprocess.PIPE, text=True).stdout.strip()
            if cg: STATE['cg'] = cg; log('scope cgroup', cg, 'memory.max', open('/sys/fs/cgroup' + cg + '/memory.max').read().strip(), 'memory.swap.max', open('/sys/fs/cgroup' + cg + '/memory.swap.max').read().strip())
        st = subprocess.run(NT + ['status'], stdout=subprocess.PIPE, text=True, stderr=subprocess.DEVNULL).stdout
        sb = subprocess.run(NT + ['statusbinary'], stdout=subprocess.PIPE, text=True, stderr=subprocess.DEVNULL).stdout.strip()
        if re.search(r'^UN\s+127\.0\.0\.1', st, re.M) and sb == 'running':
            log('node up (%s) after %.0f s, pid %s' % (label, time.time() - t0, node_pid())); return node_pid()
    raise RuntimeError('node did not come up')

def stop_node():
    if STATE['cg']:
        try: log('scope memory.events (before stop):', open('/sys/fs/cgroup' + STATE['cg'] + '/memory.events').read().replace('\n', '; '))
        except Exception as e: log('memory.events gone:', e)
    pid = node_pid()
    if pid:
        try:
            log('stopping node: nodetool drain'); subprocess.run(NT + ['drain'], timeout=300, stdout=LOG, stderr=LOG, stdin=subprocess.DEVNULL)
        except Exception as e: log('drain failed', e)
        try:
            os.kill(pid, signal.SIGTERM)
            for _ in range(90):
                try: os.kill(pid, 0); time.sleep(1)
                except OSError: break
            else: os.kill(pid, signal.SIGKILL); log('SIGKILL sent')
        except OSError: pass
    if STATE['proc']:
        try: STATE['proc'].wait(timeout=60)
        except Exception: STATE['proc'].kill()
    if STATE['cg']:
        try: log('scope memory.events:', open('/sys/fs/cgroup' + STATE['cg'] + '/memory.events').read().replace('\n', '; '))
        except Exception as e: log('memory.events gone:', e)
    STATE['stop'] = True
    log('scope max memory.current sampled: %.2f GiB' % (STATE['memmax'] / 2**30))
    if STATE['unit']: log('scope state:', subprocess.run(['systemctl', '--user', 'is-active', STATE['unit'] + '.scope'], stdout=subprocess.PIPE, text=True).stdout.strip())
    log('daemons left:', daemons())
atexit.register(stop_node)

def client(*args, timeout=900):
    return subprocess.Popen([sys.executable, '-I', os.path.join(HARN, 'client.py'), DRV] + [str(a) for a in args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL)

HF = None
def histo(pid, tag):
    t0 = ms()
    p = subprocess.run(['jcmd', str(pid), 'GC.class_histogram'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120)
    t1 = ms(); tot = bt = None
    lines = p.stdout.splitlines()
    for l in lines:
        m = re.match(r'^Total\s+(\d+)\s+(\d+)', l)
        if m: tot = int(m.group(2))
        m = re.match(r'^\s*\d+:\s+(\d+)\s+(\d+)\s+\[B\b', l)
        if m and bt is None: bt = int(m.group(2))
    HF.write('## %s t0=%d t1=%d total=%s B=%s\n%s\n%s\n' % (tag, t0, t1, tot, bt, '\n'.join(lines[1:9]), '\n'.join(l for l in lines if l.startswith('Total')))); HF.flush()
    return {'t0': t0, 't1': t1, 'total': tot, 'bytesB': bt}

class Marker:
    def __init__(self): self.off = 0
    def new(self):
        if not os.path.exists(MARK): return []
        with open(MARK) as f:
            f.seek(self.off); data = f.read()
        if not data.endswith('\n'): data = data[:data.rfind('\n') + 1]
        self.off += len(data.encode())
        return [l for l in data.splitlines() if l.strip()]
MK = Marker()

def arm_params(arm):
    kind, n, t = arm
    if kind == 'L': return t, n, 'none'
    return t, 'none', n          # P: no LIMIT, fetch size n, first page only

def arm_id(arm): return '%s%s-%s' % arm

def query(pid, arm, rep, tag):
    MK.new()
    B = histo(pid, '%s rep%s %s B' % (arm_id(arm), rep, tag)); time.sleep(2)
    t, L, f = arm_params(arm)
    p = client('q', t, L, f)
    probes = []
    def consume(lines):
        for l in lines:
            w = l.split()
            if len(w) < 3 or w[0] not in ('PR', 'PC', 'PA'): log('marker?', l); continue
            if w[1] == 'start':
                pr = {'kind': w[0], 'start_ms': int(w[2]), 'info': ' '.join(w[3:])[:600]}
                pr['hist'] = histo(pid, '%s rep%s %s %s' % (arm_id(arm), rep, tag, w[0])); probes.append(pr)
                consume(MK.new())
            elif w[1] == 'end':
                for pr in reversed(probes):
                    if pr['kind'] == w[0] and 'end_ms' not in pr: pr['end_ms'] = int(w[2]); break
    while p.poll() is None:
        consume(MK.new()); time.sleep(0.02)
    out = p.stdout.read()
    time.sleep(0.5); consume(MK.new())
    try: q = json.loads(out.strip().splitlines()[-1])
    except Exception: raise RuntimeError('client output not JSON: %s' % out[-800:])
    time.sleep(2)
    B2 = histo(pid, '%s rep%s %s B2' % (arm_id(arm), rep, tag))
    for pr in probes: pr['inside'] = ('end_ms' in pr) and pr['hist']['t1'] < pr['end_ms']
    q.update(arm=arm_id(arm), kind=arm[0], N=arm[1], table=arm[2], W=TABLES[arm[2]], rep=rep, tag=tag, B=B, B2=B2, probes=probes)
    return q

def life(which):
    global HF
    agent = True
    pid = start_node(agent)
    sp = subprocess.Popen(['java', '-cp', RUN + '/tools', 'Jmx', '7199', 'poll', '25', os.path.join(OUT, 'alloc.csv')], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    HF = open(os.path.join(OUT, 'histos.txt'), 'a')
    qf = open(os.path.join(OUT, 'queries.jsonl'), 'a')
    def rec(q):
        qf.write(json.dumps(q) + '\n'); qf.flush()
        log('Q', q['arm'], 'rep', q['rep'], q['tag'], 'rows', q['rows'], 'err', (q['err'] or '-')[:160], '| B %.1f MB B2-B %+.1f MB |' % (q['B']['total'] / 1e6, (q['B2']['total'] - q['B']['total']) / 1e6),
            ' '.join('%s H=%.1fMB inside=%s %s' % (pr['kind'], (pr['hist']['total'] - q['B']['total']) / 1e6, pr['inside'], pr['info'][:90]) for pr in q['probes']))
    rc = 0
    try:
        time.sleep(15)
        if which == 'K':
            for arm in (('L', 32, 'w128k'), ('P', 128, 'w1m')):
                rec(query(pid, arm, 0, 'check'))
            return 0
        if which == 'U':
            arms = [('L', n, t) for t in ('w16k', 'w128k', 'w1m') for n in (32, 128, 512)] + [('L', 'none', 'w128k'), ('P', 128, 'w1m'), ('P', 512, 'w1m')]
        else:
            arms = [('L', 128, 'w1m'), ('L', 512, 'w1m'), ('L', 512, 'w128k'), ('P', 128, 'w1m'), ('L', 32, 'w1m'), ('L', 128, 'w128k'), ('L', 512, 'w16k')]
        for arm in arms: rec(query(pid, arm, 0, 'warm'))
        q = query(pid, ('L', 128, 'w1m'), 0, 'trigger'); rec(q)
        if which == 'U':
            pcs = [pr for pr in q['probes'] if pr['kind'] == 'PC']
            hc = (pcs[0]['hist']['total'] - q['B']['total']) if pcs else None
            ok = (not q['err']) and q['rows'] == 128 and hc is not None and hc >= 64 * 2**20
            log('FIRST-TRIGGER CHECK (U: L(128, 1 MiB) returns 128 rows and H_C >= 64 MiB)', 'ok' if ok else 'FAILED', 'rows', q['rows'], 'H_C', hc)
        else:
            pa = [pr for pr in q['probes'] if pr['kind'] == 'PA']
            ok = bool(q['err']) and bool(pa) and ('read_size' in json.dumps(q.get('err_codes', {})).lower() or 'size' in q['err'].lower())
            log('FIRST-TRIGGER CHECK (C: L(128, 1 MiB) fails with a read-size failure and PA fires)', 'ok' if ok else 'FAILED', 'err', q['err'], 'PA', len(pa))
        if not ok: return 3
        order = [(a, r) for a in arms for r in (1, 2, 3)]; random.Random(75).shuffle(order)
        for arm, r in order:
            rec(query(pid, arm, r, 'run'))
        sh(NT + ['tablestats', 'ks'], check=False, quiet=True)
    finally:
        sp.terminate(); qf.close()
        for f in os.listdir(LDIR):
            if f.startswith('gc-') or f in ('marker.txt', 'stdout.log'): shutil.copy(os.path.join(LDIR, f), OUT)
        if os.path.exists(LDIR + '/system.log'):
            seg = open(LDIR + '/system.log', errors='replace').read().splitlines()
            errs = [l for l in seg if l.startswith('ERROR')]
            log('system.log ERROR lines:', len(errs), errs[:3])
            log('java.lang.OutOfMemoryError lines:', len([l for l in seg if 'java.lang.OutOfMemoryError' in l]))
            log('Byteman/rule lines in stdout:', len([l for l in open(LDIR + '/stdout.log', errors='replace') if 'Rule' in l or 'byteman' in l.lower()]))
            open(os.path.join(OUT, 'system-log-grep.txt'), 'w').write('\n'.join(l for l in seg if l.startswith(('ERROR', 'WARN')) or 'Heap size' in l or 'JVM Arguments' in l or 'OutOfMemory' in l) + '\n')
        stop_node()
    return rc

threading.Thread(target=mem_sampler, daemon=True).start()
os.makedirs(RUN + '/tools', exist_ok=True)
if not os.path.exists(RUN + '/tools/Jmx.class'): sh(['javac', '-d', RUN + '/tools', HARN + '/Jmx.java'])
log('rc-run start mode=%s %s tree=%s head=%s pid=%d' % (mode, arg, TREE, subprocess.run(['git', '-C', TREE, 'describe', '--tags'], stdout=subprocess.PIPE, text=True).stdout.strip(), os.getpid()))
log('df:', subprocess.run(['df', '-T', RUN], stdout=subprocess.PIPE, text=True).stdout.splitlines()[-1])
if mode == 'load':
    shutil.rmtree(NODE, ignore_errors=True)
    for d in ('data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw'): os.makedirs(os.path.join(NODE, d))
    start_node(False)
    def cql(stmt):
        p = subprocess.run([sys.executable, '-I', '-c', 'import sys; sys.path.insert(0, %r)\nfrom cassandra.cluster import Cluster\nc = Cluster(["127.0.0.1"], protocol_version=4, schema_metadata_enabled=False, token_metadata_enabled=False)\ns = c.connect()\nprint(list(s.execute(%r, timeout=600)))\nc.shutdown()' % (DRV, stmt)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        log('cql', stmt, '->', p.stdout.strip()[-300:]); return p.stdout
    cql("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    t0 = time.time()
    for t, w in TABLES.items():
        cql("CREATE TABLE IF NOT EXISTS ks.%s (pk int, ck int, v blob, PRIMARY KEY (pk, ck)) WITH compression = {'enabled':'false'} AND caching = {'keys':'ALL','rows_per_partition':'NONE'}" % t)
        p = client('load', t, ROWS, w, 8 if w >= 2**20 else 16); o = p.communicate()[0]; log(o.strip()[-300:]); assert p.returncode == 0
        sh(NT + ['flush', 'ks', t], quiet=True)
    sh(NT + ['compact', 'ks'], quiet=False, timeout=1800)
    for _ in range(90):
        cs = sh(NT + ['compactionstats'], check=False, quiet=True)
        if re.search(r'pending tasks\s*:?\s*0\b', cs): break
        time.sleep(10)
    log('load + flush + compact took %.1fs' % (time.time() - t0))
    log(sh(NT + ['tablestats', 'ks'], check=False, quiet=True)[-3000:])
    for t in TABLES:
        o = cql("SELECT count(*) FROM ks.%s WHERE pk = 1" % t)
        assert ('count=%d' % ROWS) in o or ('(%d,)' % ROWS) in o or ('%d' % ROWS) in o, o
    sh(['du', '-sb', NODE + '/data'])
    sys.exit(0)
if mode == 'life':
    sys.exit(life(arg))
