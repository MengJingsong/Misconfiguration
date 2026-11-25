#!/usr/bin/env python3
"""B25 stage-2 lifetime runner (design §2.5, frozen sha256 895b55b0...; base: R21's run.py, reduced). One node lifetime per call,
on pc99, under /mydata/s4/b25. Node in `systemd-run --user --scope -p MemorySwapMax=0` WITHOUT MemoryMax (memory.max must read
'max'); client RawGen in its own scope (MemoryMax=4G, -Xmx3g); nodetool a separate short-lived JVM.
usage:
  run.py life <label> <build U|P> <arm T|C|I|C0> <heap 2G|4096M|8192M|15872M> <K_max> [cells threads]
  run.py diag <label> <build U|P>                     arm D (§2.6): sessions 0..2 as T, stop client, nodetool flush, 30 s,
                                                      2 histograms + live dump D1, profileload b25 t0 (no client), dump D2,
                                                      idle 300 s, dump D3
  run.py shakedown <label> <build> <sessions> [cells threads]   Step A (4): not a reading; checks n_k, nodetool output, ERRORs
  run.py down                                         stop this harness's node and client, if any
Session schedule (T/C/I/C0): for k = 0..K_max-1: hot table t<k> (s_k); at s_k + 1 s the arm's nodetool command; next phase at
max(s_k + 16 s, return + 2 s). After the last session (or at the OOM): tail, hot table ttail for 60 s, no profileload. Endpoint
checks every 1 s. OOM: wait <= 300 s (600 s above 4 GiB) for the dump and the kill; every dump is analysed after the lifetime
(hprof_scan.py, hprof_reach.py) and deleted, JSONs kept. Surviving lifetime: stop the client, 10 s, two GC.class_histogram, one
GC.heap_dump (live). Output: /mydata/s4/b25/logs/<label>/."""
import json, os, re, shutil, subprocess, sys, threading, time

W = '/mydata/s4/b25'
BUILDS = {'U': W + '/cassandra-u', 'P': W + '/cassandra-p'}
SHA = {'U': '570b5249d9b9a43f6809eb3da562737492192026f974b2edbd20e94bea90176e',
       'P': '43823304885fa0e2cd90a92fedc957873fcd861046b3817c1fee98814da9e9ce'}
JAR = 'build/apache-cassandra-5.0.9-SNAPSHOT.jar'
RD = W + '/run'
HARNESS = os.path.dirname(os.path.abspath(__file__))
ADDR, JMXPORT = '127.0.0.1', 7199
G_ON = 'org.apache.cassandra.metrics:type=Table,name=AllMemtablesOnHeapDataSize'
TP = 'org.apache.cassandra.metrics:type=ThreadPools,path=request,scope={},name={}'
SAMPLER_BEANS = [
    ('java.lang:type=Memory', 'HeapMemoryUsage'),
    ('java.lang:type=MemoryPool,name=G1 Old Gen', 'Usage'),
    ('java.lang:type=MemoryPool,name=G1 Old Gen', 'CollectionUsage'),
    ('java.lang:type=GarbageCollector,name=G1 Young Generation', 'CollectionCount'),
    ('java.lang:type=GarbageCollector,name=G1 Old Generation', 'CollectionCount'),
    ('java.lang:type=GarbageCollector,name=G1 Old Generation', 'CollectionTime'),
    (G_ON, 'Value'),
    ('org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation', 'Count'),
    ('org.apache.cassandra.metrics:type=MemtablePool,name=PendingFlushTasks', 'Value'),
    (TP.format('ReadStage', 'CompletedTasks'), 'Value'),
    (TP.format('MutationStage', 'CompletedTasks'), 'Value'),
    ('org.apache.cassandra.metrics:type=DroppedMessage,scope=_SAMPLE,name=Dropped', 'Count'),
]
SAMPLER_COLS = 'ms,heap_used,old_used,old_coll_used,young_n,old_n,old_ms,K_pool,blocked,pending_flush,read_done,mut_done,sample_dropped'
POOL = {'2G': '512MiB', '4096M': '1024MiB', '8192M': '2048MiB', '15872M': '3968MiB'}
OOMWAIT = {'2G': 300, '4096M': 300, '8192M': 600, '15872M': 600}
CMD = {'T': '', 'I': '', 'C': '-a WRITES,WRITE_SIZE,LOCAL_READ_TIME,CAS_CONTENTIONS ', 'C0': None, 'D': '', 'I2': ''}
ALLOC = {'I2': 'unslabbed_heap_buffers'}   # optional P5 arm I2: the one constraint changed, intervention arm only (V6 exception)
RATE = 28

args = sys.argv[1:]
if not args or args[0] not in ('life', 'diag', 'shakedown', 'down'):
    sys.exit(__doc__)
mode = args[0]
if mode == 'down':
    label, BUILD = 'down', 'U'
else:
    label, BUILD = args[1], args[2]
if BUILD not in BUILDS:
    sys.exit(__doc__)
C = BUILDS[BUILD]
LOGS = f'{W}/logs/{label}'
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
SUM = {'label': label, 'mode': mode, 'args': args}
if os.path.exists(LOGS + '/summary.json') and mode != 'down':
    sys.exit(f'{LOGS}/summary.json exists: use a new label')
XDG = dict(os.environ, XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}')


def log(s):
    line = f'[{time.strftime("%F %T")} {int(time.time()*1000)}] {s}'
    SESSION.write(line + '\n'); SESSION.flush()


def note(k, v):
    SUM[k] = v
    log(f'{k}: {json.dumps(v)}')
    if mode != 'down':
        json.dump(SUM, open(LOGS + '/summary.json', 'w'), indent=1)


def sh(cmd, timeout=600, check=True, env=None, cwd=None, quiet=False):
    if not quiet:
        log('+ ' + cmd)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd or C)
    out = r.stdout + r.stderr
    if not quiet:
        SESSION.write(out[-3000:] + '\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed ({r.returncode}): {cmd}\n{out[-1500:]}')
    return r.returncode, out


def readf(p):
    try:
        return open(p).read().strip()
    except OSError:
        return None


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


def client_pids():
    return [int(x) for x in sh(f"pgrep -f '[R]awGen {RD}/hot' || true", check=False, quiet=True)[1].split()]


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


CL = {'popen': None}


def stop_client():
    p = CL['popen']
    try:
        open(f'{RD}/client.stop', 'w').close()
    except OSError:
        pass
    if p is not None:
        try:
            p.wait(timeout=40)
        except subprocess.TimeoutExpired:
            pass
    for x in client_pids():
        subprocess.run(['kill', '-9', str(x)])
    if p is not None:
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()
    CL['popen'] = None


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
        return {'timeout': True}
    open(f'{LOGS}/hist-{tag}.txt', 'w').write(out)
    r = {'ms': int(time.time() * 1000)}
    for l in out.splitlines():
        m = re.match(r'\s*\d+:\s+(\d+)\s+(\d+)\s+(\S+)', l)
        if m and m.group(3) in ('[B', 'org.apache.cassandra.metrics.Sampler$Sample', 'com.clearspring.analytics.stream.Counter',
                                'java.nio.HeapByteBuffer'):
            r[m.group(3)] = [int(m.group(1)), int(m.group(2))]
        m = re.match(r'Total\s+(\d+)\s+(\d+)', l.strip())
        if m:
            r['total'] = int(m.group(2))
    return r


def hist2(pid, tag):
    h1 = hist(pid, tag + '-1')
    h2 = hist(pid, tag + '-2')
    k = jmx((G_ON, 'Value'))[0]
    h2['h1_total'] = h1.get('total')
    h2['K_pool'] = int(k) if k and k.isdigit() else k
    note('hist ' + tag, h2)
    return h2


def cgroup_path(pid):
    for l in open(f'/proc/{pid}/cgroup'):
        if l.startswith('0::'):
            return '/sys/fs/cgroup' + l.strip()[3:]
    return None


SAMP = {'proc': None, 'stop': threading.Event(), 'thread': None, 'last_events': None}


def start_samplers(pid, cg):
    stopf = f'{RD}/sampler.stop'
    cmd = f"java -cp {W}/cls Jmx {JMXPORT} poll 500 1000000 {stopf} " + ' '.join(f"'{b}' {a}" for b, a in SAMPLER_BEANS)
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


def write_conf(arm=None):
    if os.path.exists(RD):
        shutil.rmtree(RD)
    for d in ('logs', 'data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw', 'dump'):
        os.makedirs(f'{RD}/{d}')
    shutil.copytree(C + '/conf', RD + '/conf')
    lines = ['cluster_name: b25', f'listen_address: {ADDR}', f'rpc_address: {ADDR}',
             'seed_provider:', '  - class_name: org.apache.cassandra.locator.SimpleSeedProvider', '    parameters:', f'      - seeds: "{ADDR}:7000"',
             'data_file_directories:', f'    - {RD}/data', f'commitlog_directory: {RD}/commitlog', f'hints_directory: {RD}/hints',
             f'saved_caches_directory: {RD}/saved_caches', f'cdc_raw_directory: {RD}/cdc_raw']
    if arm in ALLOC:
        lines.append(f'memtable_allocation_type: {ALLOC[arm]}')
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
    open(RD + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- b25 environment lines ----\n' + '\n'.join(lines) + '\n')
    sh(f'diff {C}/conf/cassandra.yaml {RD}/conf/cassandra.yaml > {LOGS}/yaml.diff; true', check=False)


NODE = {'popen': None}


def admin(*a, timeout=300):
    rc, out = sh(f'python3 -I {HARNESS}/client.py {ADDR} ' + ' '.join(str(x) for x in a), timeout=timeout, check=False,
                 env=dict(os.environ, CASSANDRA_HOME=C), quiet=True, cwd='/')
    js = [l for l in out.splitlines() if l.startswith('{')]
    return json.loads(js[-1]) if js else None


def start(heap, arm=None):
    if pid_of() is not None:
        fail('a node of this harness is already running')
    busy = sh('ss -ltn', quiet=True)[1]
    for w in (f'{ADDR}:7000', f'{ADDR}:9042', f':{JMXPORT}'):
        if re.search(re.escape(w) + r'\s', busy):
            fail(f'port {w} is busy')
    d = sh("ps -eo pid,cmd | grep '[C]assandraDaemon' | cut -c1-160 || true", check=False, quiet=True)[1].strip()
    mem = int(re.search(r'MemAvailable:\s+(\d+)', open('/proc/meminfo').read()).group(1)) // 1024
    note('cotenancy', {'daemons': d or 'none', 'MemAvailable_MiB': mem})
    if mem < 40 * 1024:
        fail('MemAvailable < 40 GiB')
    write_conf(arm)
    env = dict(XDG, CASSANDRA_CONF=RD + '/conf', CASSANDRA_LOG_DIR=RD + '/logs', CASSANDRA_HEAPDUMP_DIR=RD + '/dump', MAX_HEAP_SIZE=heap)
    for k in ('HEAP_NEWSIZE', 'JVM_EXTRA_OPTS', 'JVM_OPTS', 'CASSANDRA_INCLUDE'):
        env.pop(k, None)
    unit = f'b25-{label.lower()}-{int(time.time())}'
    cmd = (f"systemd-run --user --scope --unit={unit} -p MemorySwapMax=0 "
           f"bash -c 'ulimit -n 100000 && exec bin/cassandra -f -p {RD}/cassandra.pid' > {RD}/stdout.txt 2>&1")
    log('+ ' + cmd)
    NODE['popen'] = subprocess.Popen(cmd, shell=True, cwd=C, env=env)
    t0 = time.time()
    while time.time() - t0 < 300:
        time.sleep(3)
        if NODE['popen'].poll() is not None:
            fail(f'node died during start (exit {NODE["popen"].returncode})')
        if pid_of() and 'Starting listening for CQL clients' in (readf(RD + '/logs/system.log') or '') and admin('probe', timeout=60):
            break
    else:
        fail('node not serving after 300 s (invalid lifetime)')
    pid = pid_of()
    cg = cgroup_path(pid)
    mmax, sw = readf(cg + '/memory.max'), readf(cg + '/memory.swap.max')
    jvm = open(f'/proc/{pid}/cmdline').read().replace('\0', ' ')
    open(LOGS + '/jvm-cmdline.txt', 'w').write(jvm + '\n')
    flags = {f: (f in jvm) for f in ('-XX:+UseG1GC', '-XX:G1HeapRegionSize=16m', '-XX:+HeapDumpOnOutOfMemoryError',
                                     '-XX:OnOutOfMemoryError=kill -9 %p', f'-Xmx{heap}')}
    note('start', {'pid': pid, 'up_s': round(time.time() - t0), 'unit': unit, 'cgroup': cg, 'memory.max': mmax, 'swap.max': sw,
                   'flags': flags, 'MaxDirectMemorySize': re.findall(r'-XX:MaxDirectMemorySize=\S+', jvm),
                   'HeapDumpPath': re.findall(r'-XX:HeapDumpPath=\S+', jvm), 'xmx': re.findall(r'-Xmx\S+', jvm),
                   'xms': re.findall(r'-Xms\S+', jvm), 'xmn': re.findall(r'-Xmn\S+', jvm)})
    if mmax != 'max' or sw != '0':
        fail('scope not applied')
    if not all(flags.values()):
        fail('JVM flags differ')
    return pid, cg


SETTINGS = ['memtable_allocation_type', 'memtable_heap_space', 'memtable_offheap_space', 'memtable_cleanup_threshold',
            'memtable_flush_writers', 'commitlog_segment_size', 'max_mutation_size', 'commitlog_total_space', 'concurrent_reads',
            'concurrent_writes', 'native_transport_max_request_data_in_flight', 'native_transport_max_request_data_in_flight_per_ip',
            'native_transport_max_message_size', 'key_cache_size', 'row_cache_size', 'tables_warn_threshold', 'tables_fail_threshold',
            'read_thresholds_enabled', 'memtable', 'native_transport_max_concurrent_connections']


def readback(heap, arm=None):
    got = admin('settings', *SETTINGS)
    s = got and got.get('settings') or {}
    exp = {'memtable_allocation_type': ALLOC.get(arm, 'heap_buffers'), 'memtable_heap_space': POOL[heap], 'memtable_offheap_space': POOL[heap],
           'commitlog_segment_size': '32MiB', 'concurrent_reads': '32', 'concurrent_writes': '32', 'row_cache_size': '0MiB',
           'native_transport_max_message_size': '16777216B', 'read_thresholds_enabled': 'false'}
    bad = {k: [v, s.get(k)] for k, v in exp.items() if s.get(k) != v}
    note('settings', {'values': s, 'expected': exp, 'mismatch': bad, 'ok': not bad})
    if bad:
        fail('settings read-back differs')


def build_info():
    jar = f'{C}/{JAR}'
    sha = sh(f'sha256sum {jar}', check=False, quiet=True)[1].split()[0]
    _, jp = sh(f"javap -c -p -cp {jar} 'org.apache.cassandra.metrics.Sampler'", check=False, quiet=True, cwd='/')
    blk, on = [], False
    for l in jp.splitlines():
        if 'public void addSample(' in l:
            on = True
        if on:
            blk.append(l.strip())
            if l.strip().endswith('return'):
                break
    mb = [x for x in blk if 'minimalBufferFor' in x]
    note('build', {'build': BUILD, 'tree': C, 'jar_sha256': sha, 'addSample_minimalBufferFor': mb})
    if sha != SHA[BUILD] or (BUILD == 'P') != bool(mb):
        fail('build differs from the planned one')


def collect():
    for f in ('logs/system.log', 'logs/debug.log', 'stdout.txt'):
        sh(f'cp {RD}/{f} {LOGS}/ 2>/dev/null; true', check=False, quiet=True)
    sh(f'cp {RD}/logs/gc.log* {LOGS}/ 2>/dev/null; true', check=False, quiet=True)
    if SAMP['last_events'] is not None:
        open(LOGS + '/memory.events', 'w').write(SAMP['last_events'] + '\n')


def analyse_dump(path, tag):
    """hprof_scan.py + hprof_reach.py on the kept dump (node already down or idle), JSONs kept, dump deleted"""
    st = os.stat(path)
    t0 = time.time()
    sh(f'nice -n 10 python3 -I {HARNESS}/hprof_scan.py {path} > {LOGS}/scan-{tag}.json 2> {LOGS}/scan-{tag}.err', check=False,
       timeout=3600, cwd='/', quiet=True)
    t1 = time.time()
    sh(f'nice -n 10 python3 -I {HARNESS}/hprof_reach.py {path} > {LOGS}/reach-{tag}.json 2> {LOGS}/reach-{tag}.err', check=False,
       timeout=3600, cwd='/', quiet=True)
    t2 = time.time()
    r = {}
    try:
        rj = json.load(open(f'{LOGS}/reach-{tag}.json'))
        r = {'R_s': rj['R_s'], 'reachable_regions': rj['reachable']['regions'], 'regions_in_dump': rj['regions_in_dump'],
             'counted': rj['reachable']['counted'], 'reachable_MiB': rj['reachable']['shallow_MiB'],
             'only_via_sampler_MiB': rj['only_via_sampler_shallow_MiB']}
        sj = json.load(open(f'{LOGS}/scan-{tag}.json'))
        live_alloc_regions = sum((a.get('regionCount') or 0) for a in sj.get('allocators', []) if a.get('state') != 'DISCARDED')
        pool = sj.get('pool') if isinstance(sj.get('pool'), dict) else {}
        r.update({'K_pool_allocated': pool.get('allocated'), 'K_pool_reclaiming': pool.get('reclaiming'),
                  'allocators_by_state': sj.get('allocators_by_state'), 'nondiscarded_regionCount': live_alloc_regions,
                  'uncounted_regions': rj['reachable']['regions'] - live_alloc_regions})
    except Exception as e:
        r['error'] = repr(e)
    note('dump ' + tag, dict(r, bytes=st.st_size, scan_s=round(t1 - t0, 1), reach_s=round(t2 - t1, 1)))
    os.remove(path)


def finish():
    d = sh("ps -eo pid,cmd | grep '[C]assandraDaemon' | cut -c1-160 || true", check=False, quiet=True)[1].strip()
    note('end', {'daemons_left': d or 'none', 'clients_left': client_pids()})
    if pid_of() is None:
        shutil.rmtree(RD, ignore_errors=True)


def fail(msg):
    note('FAIL', msg)
    stop_client()
    stop_samplers()
    stop_node()
    collect()
    finish()
    sys.exit(1)


def oom_seen():
    out = readf(RD + '/stdout.txt') or ''
    return 'java.lang.OutOfMemoryError' in out or 'Dumping heap to' in out


def wait_death(limit):
    t0 = time.time()
    while time.time() - t0 < limit:
        if pid_of() is None:
            return True
        time.sleep(1)
    return pid_of() is None


def start_client(cells, threads):
    open(f'{RD}/hot', 'w').write('t0\n')
    try:
        os.remove(f'{RD}/client.stop')
    except OSError:
        pass
    cmd = (f"systemd-run --user --scope --unit=b25c-{label.lower()}-{int(time.time())} -p MemoryMax=4G -p MemorySwapMax=0 "
           f"java -Xmx3g -Dlogback.configurationFile={HARNESS}/logback-client.xml -cp '{W}/cls:{C}/build/lib/jars/*' RawGen "
           f"{RD}/hot {LOGS}/rawgen.csv {RD}/client.stop {RATE} {cells} {threads} 7200 > {LOGS}/rawgen.out 2>&1")
    log('+ ' + cmd)
    CL['popen'] = subprocess.Popen(cmd, shell=True, cwd='/', env=XDG)


def set_hot(t):
    open(f'{RD}/hot.tmp', 'w').write(t + '\n')
    os.replace(f'{RD}/hot.tmp', f'{RD}/hot')


def reads_between(t, a_ms, b_ms):
    n = n1 = 0
    try:
        for l in open(LOGS + '/rawgen.csv.reads'):
            p = l.strip().split(',')
            if len(p) == 3 and p[1] == t and a_ms <= int(p[0]) <= b_ms:
                n += 1
                n1 += p[2] == '1'
    except OSError:
        pass
    return n, n1


def nodetool_bg(cmdargs, tag):
    f = open(f'{LOGS}/nt-{tag}.txt', 'w')
    return subprocess.Popen(f'bin/nodetool -h 127.0.0.1 -p {JMXPORT} {cmdargs}', shell=True, cwd=C, stdout=f, stderr=subprocess.STDOUT,
                            env={k: v for k, v in os.environ.items() if k not in ('MAX_HEAP_SIZE', 'JVM_OPTS', 'HEAP_NEWSIZE')})


def sessions(arm, K, tail=True, endpoint=True):
    """the session schedule; returns 'oom' or 'done'"""
    sess = []
    for k in range(K):
        t = f't{k}'
        s_k = time.time()
        set_hot(t)
        rec = {'k': k, 's_ms': int(s_k * 1000)}
        while time.time() < s_k + 1:
            time.sleep(0.1)
        ret = None
        if CMD[arm] is not None:
            rec['nt_start_ms'] = int(time.time() * 1000)
            p = nodetool_bg(f'profileload {CMD[arm]}b25 {t}', f's{k}')
            while p.poll() is None:
                if pid_of() is None or oom_seen():
                    break
                if time.time() - rec['nt_start_ms'] / 1000 > 90:
                    p.kill()
                    break
                time.sleep(0.2)
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
            ret = time.time()
            rec['nt_return_ms'] = int(ret * 1000)
            rec['nt_rc'] = p.returncode
            out = readf(f'{LOGS}/nt-s{k}.txt') or ''
            rec['nt_names_keys'] = f'k{k}-' in out
            rec['nt_has_reads'] = 'READS' in out or 'Frequency of reads' in out
            rec['n_k'], rec['n_k_1row'] = reads_between(t, rec['nt_start_ms'], rec['nt_return_ms'])
        if pid_of() is None or oom_seen():
            rec['endpoint'] = 'oom'
            sess.append(rec)
            note('sessions', sess)
            return 'oom', sess
        nxt = max(s_k + 16, (ret + 2) if ret else 0)
        while time.time() < nxt:
            if pid_of() is None or oom_seen():
                rec['endpoint'] = 'oom'
                sess.append(rec)
                note('sessions', sess)
                return 'oom', sess
            time.sleep(0.5)
        if CMD[arm] is None:
            rec['n_k'], rec['n_k_1row'] = reads_between(t, rec['s_ms'] + 1000, int(time.time() * 1000))
        sess.append(rec)
        log(f'session {json.dumps(rec)}')
    note('sessions', sess)
    if tail:
        set_hot('ttail')
        t1 = time.time()
        while time.time() - t1 < 60:
            if pid_of() is None or oom_seen():
                note('tail', {'endpoint': 'oom', 'at_s': round(time.time() - t1)})
                return 'oom', sess
            time.sleep(1)
        note('tail', {'endpoint': 'none', 'reads': reads_between('ttail', int(t1 * 1000), int(time.time() * 1000))})
    return 'done', sess


def client_last():
    try:
        lines = open(LOGS + '/rawgen.csv').read().splitlines()
        return lines[-1]
    except Exception:
        return None


def oom_path(heap):
    t0 = time.time()
    lim = OOMWAIT.get(heap, 300)
    while time.time() - t0 < lim and pid_of() is not None:
        time.sleep(1)
    if not wait_death(30):
        log('node still alive after the OOM wait: kill -9 by PID')
        pp = pid_of()
        if pp:
            subprocess.run(['kill', '-9', str(pp)])
        wait_death(30)
    stop_client()
    stop_samplers()
    out = readf(RD + '/stdout.txt') or ''
    oom_lines = [l for l in out.splitlines() if ('OutOfMemoryError' in l and 'JVM Arguments' not in l and 'CompileCommand' not in l) or 'Dumping heap' in l or 'Heap dump file' in l
                 or 'kill -9' in l or 'Killed' in l][:20]
    dumps = sorted(f for f in os.listdir(RD + '/dump') if f.endswith('.hprof'))
    note('oom', {'stdout_lines': oom_lines, 'dumps': dumps, 'waited_s': round(time.time() - t0), 'client_last': client_last()})
    # initiating error from system.log/debug.log (first OOM line and its thread)
    first = []
    for f in ('logs/system.log', 'logs/debug.log'):
        for l in (readf(f'{RD}/{f}') or '').splitlines():
            if 'java.lang.OutOfMemoryError' in l and 'JVM Arguments' not in l and 'CompileCommand' not in l:
                first.append(f + ': ' + l[:300])
                break
    note('oom_first_log_lines', first)
    collect()
    for i, d in enumerate(dumps):
        analyse_dump(f'{RD}/dump/{d}', 'oom' if i == 0 else f'oom{i}')


def mode_life(arm, heap, K, cells, threads):
    pid, cg = start(heap, arm)
    build_info()
    readback(heap, arm)
    sc = admin('schema', K, timeout=900)
    note('schema', sc)
    if not sc or sc.get('tables_n') != K + 1:
        fail('schema failed')
    start_samplers(pid, cg)
    time.sleep(10)
    t_work = time.time()
    note('workload_start', {'ms': int(t_work * 1000), 'arm': arm, 'K_max': K, 'rate': RATE, 'cells': cells, 'threads': threads,
                            'nodetool': CMD[arm]})
    start_client(cells, threads)
    time.sleep(4)
    endpoint, sess = sessions(arm, K)
    note('endpoint', {'endpoint': endpoint, 'sessions_done': len(sess), 'at_s': round(time.time() - t_work)})
    if endpoint == 'oom':
        oom_path(heap)
        finish()
        return
    stop_client()
    note('client_end', client_last())
    time.sleep(10)
    note('hist_end', hist2(pid, 'end'))
    rc, out = sh(f'jcmd {pid} GC.heap_dump {RD}/dump/end.hprof', check=False, timeout=1800, cwd='/')
    note('end_dump', {'rc': rc, 'out': out[-200:]})
    errs = [l[:300] for l in (readf(RD + '/logs/system.log') or '').splitlines() if l.startswith('ERROR')]
    note('system_log_errors', errs[:20])
    stop_samplers()
    stop_node()
    collect()
    if os.path.exists(f'{RD}/dump/end.hprof'):
        analyse_dump(f'{RD}/dump/end.hprof', 'end')
    finish()


def mode_diag():
    heap = '2G'
    pid, cg = start(heap)
    build_info()
    readback(heap)
    sc = admin('schema', 3)
    note('schema', sc)
    if not sc or sc.get('tables_n') != 4:
        fail('schema failed')
    start_samplers(pid, cg)
    time.sleep(10)
    note('workload_start', {'ms': int(time.time() * 1000), 'arm': 'D', 'K': 3})
    start_client(9, 1)
    time.sleep(4)
    endpoint, sess = sessions('D', 3, tail=False)
    if endpoint == 'oom':
        oom_path(heap)
        finish()
        return
    stop_client()
    note('client_end', client_last())
    rc, out = sh(f'bin/nodetool -h 127.0.0.1 -p {JMXPORT} flush', check=False, timeout=600)
    note('flush', {'rc': rc})
    time.sleep(30)
    dumps = []
    note('hist_D1', hist2(pid, 'D1'))
    sh(f'jcmd {pid} GC.heap_dump {RD}/dump/D1.hprof', check=False, timeout=1800, cwd='/'); dumps.append('D1')
    t0 = time.time()
    rc, out = sh(f'bin/nodetool -h 127.0.0.1 -p {JMXPORT} profileload b25 t0', check=False, timeout=120,
                 env={k: v for k, v in os.environ.items() if k != 'MAX_HEAP_SIZE'})
    open(f'{LOGS}/nt-D2.txt', 'w').write(out)
    note('D2_profileload', {'rc': rc, 'seconds': round(time.time() - t0, 1)})
    note('hist_D2', hist2(pid, 'D2'))
    sh(f'jcmd {pid} GC.heap_dump {RD}/dump/D2.hprof', check=False, timeout=1800, cwd='/'); dumps.append('D2')
    t1 = time.time()
    while time.time() - t1 < 300:
        if pid_of() is None:
            fail('node gone during the 300 s idle')
        time.sleep(2)
    note('hist_D3', hist2(pid, 'D3'))
    sh(f'jcmd {pid} GC.heap_dump {RD}/dump/D3.hprof', check=False, timeout=1800, cwd='/'); dumps.append('D3')
    errs = [l[:300] for l in (readf(RD + '/logs/system.log') or '').splitlines() if l.startswith('ERROR')]
    note('system_log_errors', errs[:20])
    stop_samplers()
    stop_node()
    collect()
    for d in dumps:
        if os.path.exists(f'{RD}/dump/{d}.hprof'):
            analyse_dump(f'{RD}/dump/{d}.hprof', d)
    finish()


def mode_shakedown(K, cells, threads):
    heap = '2G'
    pid, cg = start(heap)
    build_info()
    readback(heap)
    note('schema', admin('schema', K))
    start_samplers(pid, cg)
    time.sleep(5)
    start_client(cells, threads)
    time.sleep(4)
    endpoint, sess = sessions('T', K, tail=False)
    note('endpoint', endpoint)
    stop_client()
    note('client_end', client_last())
    note('rawgen_out', (readf(LOGS + '/rawgen.out') or '')[-800:])
    errs = [l[:300] for l in (readf(RD + '/logs/system.log') or '').splitlines() if l.startswith('ERROR')]
    note('system_log_errors', errs[:10])
    stop_samplers()
    stop_node()
    collect()
    finish()


try:
    if mode != 'down':
        sh(f'mkdir -p {W}/cls && javac -nowarn -d {W}/cls {HARNESS}/Jmx.java && javac -nowarn -cp "{C}/build/lib/jars/*" -d {W}/cls {HARNESS}/RawGen.java',
           cwd='/', quiet=True)
    if mode == 'down':
        stop_client()
        stop_node()
        log('down: ' + (sh("ps -eo pid,cmd | grep '[C]assandraDaemon' | cut -c1-160 || true", check=False, quiet=True)[1].strip() or 'none'))
    elif mode == 'shakedown':
        mode_shakedown(int(args[3]), int(args[4]) if len(args) > 4 else 9, int(args[5]) if len(args) > 5 else 1)
    elif mode == 'diag':
        mode_diag()
    else:
        arm, heap, K = args[3], args[4], int(args[5])
        if arm not in ('T', 'C', 'I', 'C0', 'I2') or heap not in POOL or (arm == 'I') != (BUILD == 'P'):
            sys.exit(__doc__)
        mode_life(arm, heap, K, int(args[6]) if len(args) > 6 else 9, int(args[7]) if len(args) > 7 else 1)
    note('DONE', True)
except SystemExit:
    raise
except Exception as e:
    fail(f'exception {e!r}')
