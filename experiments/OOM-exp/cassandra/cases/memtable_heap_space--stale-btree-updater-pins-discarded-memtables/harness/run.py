#!/usr/bin/env python3
"""R21 stage-2 lifetime driver (R21 design §2.5, frozen sha256 4efd3a2d...): R16's run.py with (a) a build argument U/P selecting
/mydata/s4/r21/cassandra-u or cassandra-p (build, jar sha256 and the javap of BTree$Updater.reset() in summary.json); (b) arms T (hot,
cw 32), I (hot, cw 4), C (perthread, cw 32), Q (quad: pk = thread mod 4, cw 32); (c) the node scope WITHOUT MemoryMax (MemorySwapMax=0
only; memory.max must read 'max'); (d) every OOM dump and every end dump moved to /mydata/s4/r21/dumps/<label>--<tag>.hprof for
reachq.sh (scan, reach, refs on the first OOM dump of each build+arm) instead of scanned inline; (e) mode idle (§2.6); (f) the
queue back-pressure (> 6 dumps waiting: wait until <= 3). One node lifetime per call, on pc75, under /mydata/s4/r21.
usage:
  run.py life <label> <build> <arm> <heap> [R]       build: U | P ; arm: T | I | C | Q ; heap: 2G | 15872M ; R default 160 / 1792
  run.py idle <label> <build>                        2 GiB, defaults, perthread R = 160: s0; 3 x {60 s load, stop client, nodetool
                                                     flush, 30 s idle, 2 histograms, live dump}; 300 s idle; 2 histograms, live dump
  run.py shakedown <build> [selftest]                start, schema, 20 s of HotGen perthread R = 64 (source-binding check; with
                                                     selftest: HotGen --gate-selftest), end dump (timing of hprof_reach.py), stop
  run.py down                                        stop this harness's node, if any
Below, R16's text. Output: /mydata/s4/r21/logs/<label>/ (session.log, summary.json, hist-*.txt, hotgen.csv, sampler.csv, rss.csv, ss-*.txt,
system.log, debug.log, gc.log*, stdout.txt, scan-*.json, yaml.diff, jvm-cmdline.txt, memory.events)."""
import json, os, re, shutil, subprocess, sys, threading, time

W = '/mydata/s4/r21'
BUILDS = {'U': W + '/cassandra-u', 'P': W + '/cassandra-p'}
JAR = 'build/apache-cassandra-5.0.9-SNAPSHOT.jar'
C = BUILDS['U']   # replaced by the lifetime's build below
DUMPS = W + '/dumps'
RD = W + '/run'
HARNESS = os.path.dirname(os.path.abspath(__file__))
ADDR, JMXPORT = '127.0.0.1', 7199
G_ON = 'org.apache.cassandra.metrics:type=Table,name=AllMemtablesOnHeapDataSize'
G_ON_T = 'org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=t,name=AllMemtablesOnHeapDataSize'
MS = 'org.apache.cassandra.metrics:type=ThreadPools,path=request,scope=MutationStage,name='
SAMPLER_BEANS = [
    ('java.lang:type=Memory', 'HeapMemoryUsage'),
    ('java.lang:type=MemoryPool,name=G1 Old Gen', 'Usage'),
    ('java.lang:type=MemoryPool,name=G1 Old Gen', 'CollectionUsage'),
    ('java.lang:type=GarbageCollector,name=G1 Young Generation', 'CollectionCount'),
    ('java.lang:type=GarbageCollector,name=G1 Young Generation', 'CollectionTime'),
    ('java.lang:type=GarbageCollector,name=G1 Old Generation', 'CollectionCount'),
    ('java.lang:type=GarbageCollector,name=G1 Old Generation', 'CollectionTime'),
    (G_ON, 'Value'),
    (G_ON_T, 'Value'),
    ('org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation', 'Count'),
    ('org.apache.cassandra.metrics:type=MemtablePool,name=PendingFlushTasks', 'Value'),
    (MS + 'ActiveTasks', 'Value'),
    (MS + 'PendingTasks', 'Value'),
    (MS + 'CompletedTasks', 'Value'),
    ('org.apache.cassandra.metrics:type=DroppedMessage,scope=MUTATION_REQ,name=Dropped', 'Count'),
    ('org.apache.cassandra.metrics:type=ClientRequest,scope=Write,name=Timeouts', 'Count'),
]
SAMPLER_COLS = ('ms,heap_used,old_used,old_coll_used,young_n,young_ms,old_n,old_ms,K,K_t,blocked,pending_flush,mut_active,'
                'mut_pending,mut_completed,mut_dropped,write_timeouts')
RDEF = {'2G': 160, '4G': 160, '8G': 1792, '15872M': 1792}
POOL = {'2G': '512MiB', '4G': '1024MiB', '8G': '2048MiB', '15872M': '3968MiB'}
CW = {'I': 4}
HOT = ('T', 'I')
WMODE = {'T': 'hot', 'I': 'hot', 'C': 'perthread', 'Q': 'quad'}
OOMWAIT = {'15872M': 600}

args = sys.argv[1:]
if not args or args[0] not in ('life', 'idle', 'shakedown', 'down'):
    sys.exit(__doc__)
mode = args[0]
if mode in ('life', 'idle'):
    label, BUILD = args[1], args[2]
elif mode == 'shakedown':
    BUILD = args[1]
    label = f'shakedown-{BUILD}' + ('-selftest' if len(args) > 2 and args[2] == 'selftest' else '')
else:
    label, BUILD = 'down', 'U'
if BUILD not in BUILDS:
    sys.exit(__doc__)
C = BUILDS[BUILD]
LOGS = f'{W}/logs/{label}'
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
SUM = {'label': label, 'mode': mode, 'args': args}


def log(s):
    line = f'[{time.strftime("%F %T")} {int(time.time()*1000)}] {s}'
    SESSION.write(line + '\n'); SESSION.flush()


def note(k, v):
    SUM[k] = v
    log(f'{k}: {json.dumps(v)}')
    json.dump(SUM, open(LOGS + '/summary.json', 'w'), indent=1)


def sh(cmd, timeout=600, check=True, env=None, cwd=C, quiet=False):
    if not quiet:
        log('+ ' + cmd)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
    out = r.stdout + r.stderr
    if not quiet:
        SESSION.write(out[-4000:] + '\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed ({r.returncode}): {cmd}\n{out[-1500:]}')
    return r.returncode, out


def pid_of():
    for d in os.listdir('/proc'):
        if not d.isdigit():
            continue
        try:
            cl = open(f'/proc/{d}/cmdline').read()
        except OSError:
            continue
        if 'CassandraDaemon' in cl and f'-Dcassandra-pidfile={RD}/cassandra.pid' in cl:
            return int(d)
    return None


def daemons():
    return sh("ps -eo pid,cmd | grep '[C]assandraDaemon' | cut -c1-160 || true", check=False, quiet=True)[1].strip()


def stop_node(sig='TERM'):
    pid = pid_of()
    if pid is None:
        return
    log(f'stopping node pid {pid} (SIG{sig})')
    subprocess.run(['kill', '-' + sig, str(pid)])
    for _ in range(90):
        if pid_of() is None:
            return
        time.sleep(1)
    log(f'node did not stop; kill -9 {pid}')
    subprocess.run(['kill', '-9', str(pid)])
    time.sleep(2)


HG = {'popen': None, 'stop': None}


def stop_client():
    p = HG['popen']
    if p is None:
        return
    if HG['stop']:
        open(HG['stop'], 'w').close()
    try:
        p.wait(timeout=20)
    except subprocess.TimeoutExpired:
        # kill the java client by its unique stats-file argument (by PID)
        out = sh(f"pgrep -f 'HotGen .* {LOGS}/hotgen.csv'", check=False, quiet=True)[1].split()
        for x in out:
            subprocess.run(['kill', '-9', x])
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()
    HG['popen'] = None


def fail(msg):
    note('FAIL', msg)
    stop_client()
    stop_samplers()
    stop_node()
    collect()
    finish()
    sys.exit(1)


def client(*a, timeout=300, quiet=False):
    rc, out = sh(f'python3 -I {HARNESS}/client.py {ADDR} ' + ' '.join(str(x) for x in a), timeout=timeout, check=False,
                 env=dict(os.environ, CASSANDRA_HOME=C), quiet=quiet, cwd='/')
    js = [l for l in out.splitlines() if l.startswith('{')]
    return json.loads(js[-1]) if js else None


def jmx(*pairs):
    _, out = sh(f'java -cp {W}/cls Jmx {JMXPORT} get ' + ' '.join(f"'{b}' {a}" for b, a in pairs), check=False, quiet=True, timeout=120)
    res = {}
    for l in out.splitlines():
        p = l.rsplit('|', 2)
        if len(p) == 3:
            res[p[0] + '|' + p[1]] = p[2]
    return [res.get(b + '|' + a) for b, a in pairs]


def hist(pid, tag, timeout=300):
    try:
        rc, out = sh(f'jcmd {pid} GC.class_histogram', check=False, quiet=True, timeout=timeout, cwd='/')
    except subprocess.TimeoutExpired:
        return {'bb': None, 'bn': None, 'total': None, 'timeout': True}
    open(f'{LOGS}/hist-{tag}.txt', 'w').write(out)
    bb = bn = tot = None
    for l in out.splitlines():
        m = re.match(r'\s*\d+:\s+(\d+)\s+(\d+)\s+(\S+)', l)
        if m and m.group(3) == '[B':
            bn, bb = int(m.group(1)), int(m.group(2))
        m = re.match(r'Total\s+(\d+)\s+(\d+)', l.strip())
        if m:
            tot = int(m.group(2))
    return {'bb': bb, 'bn': bn, 'total': tot, 'ms': int(time.time() * 1000)}


def hist2(pid, tag):
    h1 = hist(pid, tag + '-1')
    h2 = hist(pid, tag + '-2')
    k = jmx((G_ON, 'Value'))[0]
    r = {'h1_total': h1['total'], 'total': h2['total'], 'bb': h2['bb'], 'bn': h2['bn'], 'K': int(k) if k and k.isdigit() else k,
         'ms': h2.get('ms')}
    note('hist ' + tag, r)
    return r


def readf(p):
    try:
        return open(p).read().strip()
    except OSError:
        return None


def cgroup_path(pid):
    for l in open(f'/proc/{pid}/cgroup'):
        if l.startswith('0::'):
            return '/sys/fs/cgroup' + l.strip()[3:]
    return None


# ---------------- samplers ----------------
SAMP = {'proc': None, 'stop': threading.Event(), 'thread': None, 'last_events': None}


def start_samplers(pid, cg):
    stopf = f'{RD}/sampler.stop'
    cmd = (f"java -cp {W}/cls Jmx {JMXPORT} poll 500 100000 {stopf} " + ' '.join(f"'{b}' {a}" for b, a in SAMPLER_BEANS))
    f = open(LOGS + '/sampler.csv', 'w')
    f.write(SAMPLER_COLS + '\n'); f.flush()
    SAMP['proc'] = subprocess.Popen(cmd, shell=True, stdout=f, stderr=open(LOGS + '/sampler.err', 'w'), cwd='/')

    def rssloop():
        rf = open(LOGS + '/rss.csv', 'w')
        rf.write('ms,rss_anon_kb,cg_current,cg_oom_kill,cg_oom\n')
        while not SAMP['stop'].is_set():
            st = readf(f'/proc/{pid}/status')
            if st is None:
                rf.write(f'{int(time.time()*1000)},gone,,,\n'); rf.flush()
                break
            m = re.search(r'RssAnon:\s+(\d+)', st)
            ev = readf(cg + '/memory.events') or ''
            if ev:
                SAMP['last_events'] = ev
            ok = re.search(r'oom_kill (\d+)', ev); oo = re.search(r'^oom (\d+)', ev, re.M)
            rf.write(f"{int(time.time()*1000)},{m.group(1) if m else ''},{readf(cg + '/memory.current')},"
                     f"{ok.group(1) if ok else ''},{oo.group(1) if oo else ''}\n")
            rf.flush()
            SAMP['stop'].wait(1)
        rf.close()

    SAMP['thread'] = threading.Thread(target=rssloop, daemon=True)
    SAMP['thread'].start()


def stop_samplers():
    try:
        open(f'{RD}/sampler.stop', 'w').close()
    except OSError:
        pass
    SAMP['stop'].set()
    p = SAMP['proc']
    if p is not None:
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()
    if SAMP['thread'] is not None:
        SAMP['thread'].join(timeout=5)


def sampler_rows():
    try:
        lines = open(LOGS + '/sampler.csv').read().splitlines()[1:]
    except OSError:
        return []
    cols = SAMPLER_COLS.split(',')
    out = []
    for l in lines:
        p = l.split(',')
        if len(p) == len(cols):
            out.append(dict(zip(cols, p)))
    return out


# ---------------- node ----------------
def write_conf(arm):
    if os.path.exists(RD):
        shutil.rmtree(RD)
    for d in ('logs', 'data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw', 'dump'):
        os.makedirs(f'{RD}/{d}')
    shutil.copytree(C + '/conf', RD + '/conf')
    lines = ['cluster_name: r21', f'listen_address: {ADDR}', f'rpc_address: {ADDR}',
             'seed_provider:', '  - class_name: org.apache.cassandra.locator.SimpleSeedProvider', '    parameters:', f'      - seeds: "{ADDR}:7000"',
             'data_file_directories:', f'    - {RD}/data', f'commitlog_directory: {RD}/commitlog', f'hints_directory: {RD}/hints',
             f'saved_caches_directory: {RD}/saved_caches', f'cdc_raw_directory: {RD}/cdc_raw']
    if arm in CW:
        lines.append(f'concurrent_writes: {CW[arm]}')
    keys = {l.split(':', 1)[0] for l in lines if re.match(r'^[A-Za-z_]+:', l)}
    out, skip = [], False
    for l in open(RD + '/conf/cassandra.yaml').read().splitlines():
        m = re.match(r'^([A-Za-z_]+):', l)
        if m:
            skip = m.group(1) in keys
            if skip:
                continue
        elif skip and (l.startswith((' ', '\t', '-')) or l.strip() == '' or l.lstrip().startswith('#')):
            continue
        else:
            skip = False
        out.append(l)
    open(RD + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- r21 lines ----\n' + '\n'.join(lines) + '\n')
    sh(f'diff {C}/conf/cassandra.yaml {RD}/conf/cassandra.yaml > {LOGS}/yaml.diff; true', check=False)


NODE = {'popen': None}


def start(heap, arm):
    if pid_of() is not None:
        fail('a node of this harness is already running')
    d = daemons()
    busy = sh('ss -ltn', quiet=True)[1]
    for w in (f'{ADDR}:7000', f'{ADDR}:9042', f':{JMXPORT}'):
        if re.search(re.escape(w) + r'\s', busy):
            fail(f'port {w} is busy')
    mem = int(re.search(r'MemAvailable:\s+(\d+)', open('/proc/meminfo').read()).group(1)) // 1024
    note('cotenancy', {'daemons': d or 'none', 'MemAvailable_MiB': mem})
    if mem < 40 * 1024:
        fail('MemAvailable < 40 GiB')
    write_conf(arm)
    env = dict(os.environ, CASSANDRA_CONF=RD + '/conf', CASSANDRA_LOG_DIR=RD + '/logs', CASSANDRA_HEAPDUMP_DIR=RD + '/dump',
               MAX_HEAP_SIZE=heap, XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}')
    for k in ('HEAP_NEWSIZE', 'JVM_EXTRA_OPTS', 'JVM_OPTS', 'CASSANDRA_INCLUDE'):
        env.pop(k, None)
    unit = f'r21-{label.lower()}-{int(time.time())}'
    cmd = (f"systemd-run --user --scope --unit={unit} -p MemorySwapMax=0 "
           f"bash -c 'ulimit -n 100000 && exec bin/cassandra -f -p {RD}/cassandra.pid' > {RD}/stdout.txt 2>&1")
    log('+ ' + cmd)
    NODE['popen'] = subprocess.Popen(cmd, shell=True, cwd=C, env=env)
    t0 = time.time()
    while time.time() - t0 < 300:
        time.sleep(3)
        if NODE['popen'].poll() is not None:
            fail(f'node died during start (exit {NODE["popen"].returncode})')
        if pid_of() and 'Starting listening for CQL clients' in (readf(RD + '/logs/system.log') or '') and client('probe', quiet=True, timeout=60):
            break
    else:
        fail('node not serving after 300 s (invalid lifetime)')
    pid = pid_of()
    cg = cgroup_path(pid)
    want_max = 'max'   # R21 §2.3: no container limit
    mmax, sw = readf(cg + '/memory.max'), readf(cg + '/memory.swap.max')
    jvm = open(f'/proc/{pid}/cmdline').read().replace('\0', ' ')
    open(LOGS + '/jvm-cmdline.txt', 'w').write(jvm + '\n')
    flags = {f: (f in jvm) for f in ('-XX:+UseG1GC', '-XX:G1HeapRegionSize=16m', '-XX:+HeapDumpOnOutOfMemoryError',
                                     '-XX:OnOutOfMemoryError=kill -9 %p', f'-Xmx{heap}', '-XX:G1NewSizePercent=50',
                                     '-XX:MaxGCPauseMillis=300')}
    mdm = re.findall(r'-XX:MaxDirectMemorySize=\S+', jvm)
    hdp = re.findall(r'-XX:HeapDumpPath=\S+', jvm)
    note('start', {'pid': pid, 'up_s': round(time.time() - t0), 'unit': unit, 'cgroup': cg, 'memory.max': mmax, 'swap.max': sw,
                   'scope_ok': mmax == want_max and sw == '0', 'flags': flags, 'flags_ok': all(flags.values()),
                   'MaxDirectMemorySize': mdm, 'HeapDumpPath': hdp, 'xmx': re.findall(r'-Xmx\S+', jvm),
                   'xms': re.findall(r'-Xms\S+', jvm), 'xmn': re.findall(r'-Xmn\S+', jvm)})
    if mmax != want_max or sw != '0':
        fail('scope not applied')
    if not all(flags.values()):
        fail('JVM flags differ')
    return pid, cg


def readback(arm, heap):
    names = ['memtable_allocation_type', 'memtable_heap_space', 'memtable_offheap_space', 'memtable_cleanup_threshold',
             'memtable_flush_writers', 'concurrent_writes', 'concurrent_counter_writes', 'native_transport_max_request_data_in_flight',
             'native_transport_max_request_data_in_flight_per_ip', 'native_transport_max_message_size', 'write_request_timeout',
             'max_mutation_size', 'commitlog_segment_size', 'commitlog_total_space', 'native_transport_throw_on_overload',
             'hinted_handoff_enabled', 'key_cache_size', 'batch_size_fail_threshold', 'native_transport_timeout']
    got = client('settings', *names, quiet=True)
    s = got and got.get('settings') or {}
    exp = {'memtable_allocation_type': 'heap_buffers', 'memtable_heap_space': POOL[heap],
           'concurrent_writes': str(CW.get(arm, 32)), 'write_request_timeout': '2000ms', 'commitlog_segment_size': '32MiB'}
    for k, v in exp.items():
        log(f'EXPECTED {k}={v} GOT {s.get(k)} {"OK" if s.get(k) == v else "MISMATCH"}')
    ok = all(s.get(k) == v for k, v in exp.items())
    note('settings', {'values': s, 'expected': exp, 'ok': ok})
    if not ok:
        fail('settings read-back differs')


def collect():
    for f in ('logs/system.log', 'logs/debug.log', 'stdout.txt'):
        sh(f'cp {RD}/{f} {LOGS}/ 2>/dev/null; true', check=False, quiet=True)
    sh(f'cp {RD}/logs/gc.log* {LOGS}/ 2>/dev/null; true', check=False, quiet=True)
    if SAMP['last_events'] is not None:
        open(LOGS + '/memory.events', 'w').write(SAMP['last_events'] + '\n')


def flush_lines():
    out = []
    try:
        out += [l.rstrip() for l in open(f'{RD}/logs/debug.log')
                if 'Enqueuing flush of ks.t' in l or 'Writing Memtable-t@' in l or 'High update contention' in l
                or 'Flushing largest' in l or 'Completed flushing' in l and '/ks/' in l]
    except OSError:
        pass
    return out


def queue_dump(path, tag, scanonly=False):
    """R21 (d): move the dump to the analysis queue (reachq.sh); the first OOM dump of each build+arm also gets hprof_refs.py"""
    os.makedirs(DUMPS, exist_ok=True)
    dst = f'{DUMPS}/{label}--{tag}.hprof'
    st = os.stat(path)
    flag = None
    if tag == 'oom' and mode == 'life':
        flag = f'{W}/refs-flag-{BUILD}{args[3]}'
        if os.path.exists(flag):
            flag = None
        else:
            open(flag, 'w').write(label + '\n')
            open(dst + '.refs', 'w').close()
    if scanonly:
        open(dst + '.scanonly', 'w').close()
    shutil.move(path, dst)
    note('dump_queued ' + tag, {'file': dst, 'bytes': st.st_size, 'refs': bool(flag), 'scanonly': scanonly})


def queue_wait():
    """R21 (f): if more than 6 dumps wait for analysis, wait (bounded, 30 min) until <= 3"""
    def n():
        return len([f for f in os.listdir(DUMPS) if f.endswith('.hprof')]) if os.path.isdir(DUMPS) else 0
    if n() <= 6:
        return
    t0 = time.time()
    log(f'queue has {n()} dumps: waiting until <= 3')
    while n() > 3 and time.time() - t0 < 1800:
        time.sleep(5)
    note('queue_wait', {'waited_s': round(time.time() - t0), 'left': n()})


def build_info():
    jar = f'{C}/{JAR}'
    sha = sh(f'sha256sum {jar}', check=False, quiet=True)[1].split()[0]
    _, jp = sh(f"javap -c -p -cp {jar} 'org.apache.cassandra.utils.btree.BTree$Updater'", check=False, quiet=True, cwd='/')
    blk, on = [], False
    for l in jp.splitlines():
        if 'void reset();' in l:
            on = True
        if on:
            blk.append(l.strip())
            if l.strip().endswith('return'):
                break
    nulls = [x for x in blk if 'putfield' in x]
    note('build', {'build': BUILD, 'tree': C, 'jar_sha256': sha, 'reset_putfields': nulls,
                   'reset_nulls_updateF': any('updateF' in x for x in nulls), 'reset_nulls_comparator': any('comparator' in x for x in nulls)})
    exp = {'U': '570b5249d9b9a43f6809eb3da562737492192026f974b2edbd20e94bea90176e',
           'P': '5817c26b8fbb4af726a56816f746699f9007f083c7230f42ee47c5120ee2d609'}[BUILD]
    if sha != exp or (BUILD == 'P') != any('updateF' in x for x in nulls):
        fail('build differs from the planned one')


def finish():
    left = daemons()
    note('end', {'daemons_left': left or 'none'})
    if pid_of() is None:
        shutil.rmtree(RD, ignore_errors=True)


def wait_death(limit):
    t0 = time.time()
    while time.time() - t0 < limit:
        if pid_of() is None:
            return True
        time.sleep(1)
    return pid_of() is None


def ss_clients(tag):
    _, out = sh("ss -tn state established '( dport = :9042 )'", check=False, quiet=True)
    open(f'{LOGS}/ss-{tag}.txt', 'w').write(out)
    ips = set()
    for l in out.splitlines()[1:]:
        p = l.split()
        if len(p) >= 4:
            ip = p[2].rsplit(':', 1)[0].strip('[]').replace('::ffff:', '')
            if re.match(r'127\.0\.0\.1[1-4]$', ip):
                ips.add(ip)
    return sorted(ips)


def stats_last():
    try:
        lines = open(LOGS + '/hotgen.csv').read().splitlines()
    except OSError:
        return None
    if len(lines) < 2:
        return None
    p = lines[-1].split(',')
    return {'ms': int(p[0]), 'req_ok': int(p[1]), 'rows_ok': int(p[2]), 'errs': [int(x) for x in p[3:8]], 'conn': int(p[8]),
            'gated_now': int(p[9]), 'gate_waits': int(p[10]), 'gate_wait_ms': int(p[11]), 'gate_polls': int(p[12]),
            'gate_poll_err': int(p[13]), 'retired': int(p[14])}


def start_client(nips, tpi, R, wmode, secs, rate=0, selftest=False):
    HG['stop'] = f'{LOGS}/hotgen.stop'
    try:
        os.remove(HG['stop'])
    except OSError:
        pass
    cmd = (f"systemd-run --user --scope --unit=r21c-{label.lower()}-{int(time.time())} -p MemoryMax=4G -p MemorySwapMax=0 "
           f"java -Xmx3g -Dlogback.configurationFile={HARNESS}/logback-client.xml -cp '{W}/cls:{C}/build/lib/jars/*' HotGen {nips} {tpi} {R} {wmode} {secs} {LOGS}/hotgen.csv {HG['stop']}"
           + (f' {rate}' if rate else ' 0') + (' --gate-selftest' if selftest else '') + f" > {LOGS}/hotgen.out 2>&1")
    log('+ ' + cmd)
    HG['popen'] = subprocess.Popen(cmd, shell=True, cwd='/', env=dict(os.environ, XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}'))


def node_oom_path(t_work, limit=300):
    """the node is gone (or going): shipped HeapDumpOnOutOfMemoryError then kill -9 %p (wait <= 300 s, 600 s at 15,872 MiB)"""
    t0 = time.time()
    while time.time() - t0 < limit:
        out = readf(RD + '/stdout.txt') or ''
        if pid_of() is None or 'Heap dump file created' in out:
            if pid_of() is None:
                break
        time.sleep(1)
    if not wait_death(60):
        log('node still alive after the OOM wait: kill -9 by PID')
        pp = pid_of()
        if pp:
            subprocess.run(['kill', '-9', str(pp)])
        wait_death(30)
    stop_client()
    stop_samplers()
    out = readf(RD + '/stdout.txt') or ''
    oom_lines = [l for l in out.splitlines() if 'OutOfMemoryError' in l or 'Dumping heap' in l or 'Heap dump file' in l
                 or 'kill -9' in l or 'Killed' in l]
    dumps = [f for f in os.listdir(RD + '/dump') if f.endswith('.hprof')]
    dinfo = []
    for d in dumps:
        p = f'{RD}/dump/{d}'
        st = sh(f'stat -c "%W %Y %s" {p}', check=False, quiet=True)[1].split()
        dinfo.append({'file': d, 'birth_s': st[0], 'mtime_s': st[1], 'bytes': st[2]})
    note('oom', {'stdout_lines': oom_lines[:20], 'dumps': dinfo, 'exit': NODE['popen'].poll(),
                 'since_workload_s': round(time.time() - t_work)})
    collect()
    note('flush_lines', [l[-260:] for l in flush_lines()][:80])
    note('client_end', stats_last())
    for d in dumps:
        queue_dump(f'{RD}/dump/{d}', 'oom', scanonly=(args[4] if len(args) > 4 else '') == '15872M')


def oom_seen():
    out = readf(RD + '/stdout.txt') or ''
    return 'java.lang.OutOfMemoryError: Java heap space' in out or 'Dumping heap to' in out


def mode_life(arm, heap, R, rate):
    queue_wait()
    pid, cg = start(heap, arm)
    build_info()
    readback(arm, heap)
    sc = client('schema', quiet=True)
    note('schema', sc)
    if not sc or 'ks' in str(sc.get('error', '')):
        fail('schema failed')
    sh(f'bin/nodetool -h 127.0.0.1 -p {JMXPORT} setlogginglevel org.apache.cassandra.db.memtable.SkipListMemtable TRACE', check=False)
    start_samplers(pid, cg)
    time.sleep(15)
    note('L0', hist2(pid, 's0'))
    time.sleep(10)
    wmode = WMODE[arm]
    secs = 240
    t_work = time.time()
    note('workload_start', {'ms': int(t_work * 1000), 'mode': wmode, 'R': R, 'S_MiB': R * 8192 / 1048576, 'secs': secs, 'rate': rate})
    start_client(4, 9, R, wmode, secs, rate)
    ips_seen, checked, last_ok_ms, last_req = set(), False, time.time(), -1
    gated_max = 0
    outcome = None
    while True:
        time.sleep(1)
        el = time.time() - t_work
        if el < 40 and len(ips_seen) < 4:
            ips_seen |= set(ss_clients('t%d' % int(el)))
        st = stats_last()
        if st and st['req_ok'] != last_req:
            last_req, last_ok_ms = st['req_ok'], time.time()
        if st:
            gated_max = max(gated_max, st['gated_now'])
        if not checked and (el >= 20 or pid_of() is None or oom_seen()):
            rows = sampler_rows()
            act = [int(r['mut_active']) for r in rows if r['mut_active'].isdigit() and int(r['ms']) >= t_work * 1000]
            need = CW[arm] - 1 if arm in CW else 1 if arm == 'Crm' else 24
            fc = {'req_ok': st and st['req_ok'], 'max_mut_active': max(act) if act else None, 'need_active': need,
                  'client_ips': sorted(ips_seen), 'at_s': round(el), 'sampler_workload_samples': len(act)}
            fc['ok'] = bool(st and st['req_ok'] >= 5 and act and max(act) >= need and len(ips_seen) == 4)
            # design §2.5 step 6: if the sampler stalled before its first workload sample in a hot arm, the dump's writer stacks count
            fc['deferred_to_dump'] = (not fc['ok'] and not act and arm in HOT and bool(st and st['req_ok'] >= 5)
                                      and len(ips_seen) == 4)
            note('first_trigger', fc)
            checked = True
            if not fc['ok'] and not fc['deferred_to_dump'] and pid_of() is not None \
                    and not oom_seen():
                fail('first-trigger check failed (invalid lifetime)')
        if pid_of() is None or oom_seen():
            outcome = 'node_gone'
            break
        if HG['popen'] is not None and HG['popen'].poll() is not None:
            outcome = 'client_done'
            break
        if time.time() - last_ok_ms > 60:
            outcome = 'client_stalled'
            break
        if el > secs + 60:
            outcome = 'client_overrun'
            break
    note('workload_outcome', {'outcome': outcome, 'at_s': round(time.time() - t_work), 'client': stats_last(), 'gated_max': gated_max})
    if outcome == 'client_stalled':
        log('client stalled with the node alive: wait <= 120 s for an OOM')
        t1 = time.time()
        while time.time() - t1 < 120:
            if pid_of() is None or oom_seen():
                outcome = 'node_gone'
                break
            time.sleep(1)
        if outcome != 'node_gone':
            stop_client()
            note('stalled_alive', {'msg': 'no OOM within 120 s of the stall; classify from gc.log'})
            h = hist(pid, 'stall', timeout=60)
            note('hist stall', h)
            stop_samplers()
            subprocess.run(['kill', '-9', str(pid)])
            wait_death(30)
            collect()
            note('flush_lines', [l[-300:] for l in flush_lines()][:150])
            finish()
            return
    if outcome == 'node_gone':
        node_oom_path(t_work, OOMWAIT.get(heap, 300))
        # first-trigger fallback (writer stacks in the dump) is read by analyze.py from scan-oom.json after reachq.sh
        finish()
        return
    # surviving lifetime
    stop_client()
    note('client_end', stats_last())
    time.sleep(10)
    note('U_end', hist2(pid, 'end'))
    note('flush_lines', [l[-300:] for l in flush_lines()][:150])
    if heap != '15872M':
        rc, out = sh(f'jcmd {pid} GC.heap_dump {RD}/dump/end.hprof', check=False, timeout=1200, cwd='/')
        note('end_dump', {'rc': rc, 'out': out[-200:]})
        stop_samplers()
        stop_node()
        collect()
        if os.path.exists(f'{RD}/dump/end.hprof'):
            queue_dump(f'{RD}/dump/end.hprof', 'end')
    else:
        stop_samplers()
        stop_node()
        collect()
    finish()


def live_dump(pid, tag):
    rc, out = sh(f'jcmd {pid} GC.heap_dump {RD}/dump/{tag}.hprof', check=False, timeout=1200, cwd='/')
    note('dump ' + tag, {'rc': rc, 'out': out[-200:]})
    if os.path.exists(f'{RD}/dump/{tag}.hprof'):
        queue_dump(f'{RD}/dump/{tag}.hprof', tag)


def mode_idle():
    """R21 §2.6 idle-retention reading: 2 GiB, all defaults, perthread R = 160"""
    heap, arm, R = '2G', 'C', 160
    queue_wait()
    pid, cg = start(heap, arm)
    build_info()
    readback(arm, heap)
    sc = client('schema', quiet=True)
    note('schema', sc)
    if not sc or 'ks' in str(sc.get('error', '')):
        fail('schema failed')
    sh(f'bin/nodetool -h 127.0.0.1 -p {JMXPORT} setlogginglevel org.apache.cassandra.db.memtable.SkipListMemtable TRACE', check=False)
    start_samplers(pid, cg)
    time.sleep(15)
    note('L0', hist2(pid, 's0'))
    time.sleep(10)
    for n in (1, 2, 3):
        t_work = time.time()
        note(f'cycle{n}_start', {'ms': int(t_work * 1000), 'mode': 'perthread', 'R': R, 'secs': 60})
        start_client(4, 9, R, 'perthread', 60)
        while HG['popen'].poll() is None and time.time() - t_work < 150:
            if pid_of() is None or oom_seen():
                break
            time.sleep(1)
        if pid_of() is None or oom_seen():
            note('workload_outcome', {'outcome': 'node_gone', 'cycle': n, 'at_s': round(time.time() - t_work)})
            node_oom_path(t_work)
            finish()
            return
        stop_client()
        note(f'cycle{n}_client_end', stats_last())
        shutil.copy(LOGS + '/hotgen.csv', LOGS + f'/hotgen-c{n}.csv')
        rc, out = sh(f'bin/nodetool -h 127.0.0.1 -p {JMXPORT} flush', check=False, timeout=300)
        note(f'cycle{n}_flush', {'rc': rc, 'at_s': round(time.time() - t_work)})
        time.sleep(30)
        note(f'hist c{n}', hist2(pid, f'c{n}'))
        live_dump(pid, f'c{n}')
    t_idle = time.time()
    while time.time() - t_idle < 300:
        if pid_of() is None:
            fail('node gone during the 300 s idle')
        time.sleep(2)
    note('hist idle300', hist2(pid, 'idle300'))
    live_dump(pid, 'idle300')
    note('flush_lines', [l[-300:] for l in flush_lines()][:150])
    stop_samplers()
    stop_node()
    collect()
    finish()


def mode_shakedown(selftest):
    pid, cg = start('2G', 'T')
    build_info()
    readback('T', '2G')
    note('schema', client('schema', quiet=True))
    start_samplers(pid, cg)
    start_client(4, 9, 64, 'perthread', 20, 0, selftest)
    ips = set()
    for i in range(18):
        time.sleep(1)
        ips |= set(ss_clients('t%d' % i))
    note('shakedown_client_ips', sorted(ips))
    HG['popen'].wait(timeout=180)
    HG['popen'] = None
    note('client_end', stats_last())
    note('hotgen_out', (readf(LOGS + '/hotgen.out') or '')[-600:])
    rows = sampler_rows()
    note('sampler_last', rows[-1] if rows else None)
    if not selftest:
        # Step A (7): time hprof_reach.py on the shakedown's end dump (not a reading; the dump is deleted)
        rc, out = sh(f'jcmd {pid} GC.heap_dump {RD}/dump/end.hprof', check=False, timeout=1200, cwd='/')
        t0 = time.time()
        rc, out = sh(f'python3 -I {HARNESS}/hprof_reach.py {RD}/dump/end.hprof', check=False, timeout=1800, cwd='/', quiet=True)
        note('reach_timing', {'seconds': round(time.time() - t0, 1), 'bytes': os.path.getsize(f'{RD}/dump/end.hprof'),
                              'out': out[-900:]})
        os.remove(f'{RD}/dump/end.hprof')
    errs = [l for l in (readf(RD + '/logs/system.log') or '').splitlines() if l.startswith('ERROR')]
    note('system_log_errors', errs[:10])
    stop_samplers()
    stop_node()
    collect()
    finish()


try:
    sh(f'mkdir -p {W}/cls && javac -d {W}/cls {HARNESS}/Jmx.java && javac -cp "{C}/build/lib/jars/*" -d {W}/cls {HARNESS}/HotGen.java',
       cwd='/', quiet=True)
    if mode == 'down':
        stop_node()
        note('down', daemons() or 'none')
    elif mode == 'shakedown':
        mode_shakedown(len(args) > 2 and args[2] == 'selftest')
    elif mode == 'idle':
        mode_idle()
    else:
        arm, heap = args[3], args[4]
        if arm not in WMODE:
            sys.exit(__doc__)
        R = int(args[5]) if len(args) > 5 else RDEF[heap]
        mode_life(arm, heap, R, 0)
    note('DONE', True)
except SystemExit:
    raise
except Exception as e:
    fail(f'exception {e!r}')
