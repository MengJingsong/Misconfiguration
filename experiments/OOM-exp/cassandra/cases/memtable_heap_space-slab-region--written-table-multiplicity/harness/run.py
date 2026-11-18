#!/usr/bin/env python3
"""C6 stage-2 lifetime driver (design §2.5; frozen sha256 2a16e1e2...; directory amendment A1 of 2026-11-18: everything under
/mydata/s4/c6-w2 instead of /mydata/c6). One node lifetime per call, on pc91.
usage:
  run.py build <label> <restore-template|-> <first> <last> <out-template>   schema-template lifetime (8 GiB heap, 14G scope)
  run.py life <label> <arm> <heap> <template> <M>                           arm: T | C | I | D8 ; heap: 2G | 4G | 8G
  run.py shakedown                                                           start/stop with no user tables (not a reading)
  run.py down                                                                stop this harness's node, if any
Output: /mydata/s4/c6-w2/logs/<label>/ (session.log, summary.json, hist-*.txt, client.csv, acks.csv, sampler.csv, rss.csv,
system.log, debug.log, gc.log*, stdout.txt, scan-*.json, yaml.diff, env.diff, jvm-cmdline.txt)."""
import json, os, re, shutil, subprocess, sys, threading, time

W = '/mydata/s4/c6-w2'
C = W + '/cassandra'
RD = W + '/run'
HARNESS = os.path.dirname(os.path.abspath(__file__))
ADDR, JMXPORT = '127.0.9.1', 7196
G_ON = 'org.apache.cassandra.metrics:type=Table,name=AllMemtablesOnHeapDataSize'
SAMPLER_BEANS = [
    ('java.lang:type=Memory', 'HeapMemoryUsage'),
    ('java.lang:type=MemoryPool,name=G1 Old Gen', 'Usage'),
    ('java.lang:type=MemoryPool,name=G1 Old Gen', 'CollectionUsage'),
    ('java.lang:type=GarbageCollector,name=G1 Young Generation', 'CollectionCount'),
    ('java.lang:type=GarbageCollector,name=G1 Young Generation', 'CollectionTime'),
    ('java.lang:type=GarbageCollector,name=G1 Old Generation', 'CollectionCount'),
    ('java.lang:type=GarbageCollector,name=G1 Old Generation', 'CollectionTime'),
    (G_ON, 'Value'),
    ('org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation', 'Count'),
    ('org.apache.cassandra.metrics:type=ThreadPools,path=request,scope=MutationStage,name=CompletedTasks', 'Value'),
    ('org.apache.cassandra.metrics:type=ThreadPools,path=request,scope=MutationStage,name=PendingTasks', 'Value'),
    ('org.apache.cassandra.metrics:type=DroppedMessage,scope=MUTATION_REQ,name=Dropped', 'Count'),
]
SAMPLER_COLS = 'ms,heap_used,old_used,old_coll_used,young_n,young_ms,old_n,old_ms,K,blocked,mut_completed,mut_pending,mut_dropped'
ARM_ALLOC = {'T': 'heap_buffers', 'C': 'heap_buffers', 'I': 'unslabbed_heap_buffers', 'D8': 'heap_buffers', 'B': 'heap_buffers',
             'S': 'heap_buffers'}
SCOPE = {'2G': '8G', '4G': '10G', '8G': '14G'}

args = sys.argv[1:]
if not args or args[0] not in ('build', 'life', 'shakedown', 'down'):
    sys.exit(__doc__)
mode = args[0]
label = args[1] if mode in ('build', 'life') else mode
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
    for _ in range(120):
        if pid_of() is None:
            return
        time.sleep(1)
    log(f'node did not stop; kill -9 {pid}')
    subprocess.run(['kill', '-9', str(pid)])
    time.sleep(2)


def fail(msg):
    note('FAIL', msg)
    stop_samplers()
    stop_node()
    collect()
    sys.exit(1)


def client(*a, timeout=3600, quiet=False):
    rc, out = sh(f'python3 -I {HARNESS}/client.py {ADDR} ' + ' '.join(str(x) for x in a), timeout=timeout, check=False,
                 env=dict(os.environ, CASSANDRA_HOME=C), quiet=quiet)
    js = [l for l in out.splitlines() if l.startswith('{')]
    return json.loads(js[-1]) if js else None


def jmx(*pairs):
    _, out = sh(f'java -cp {W}/jmxcls Jmx {JMXPORT} get ' + ' '.join(f"'{b}' {a}" for b, a in pairs), check=False, quiet=True, timeout=120)
    res = {}
    for l in out.splitlines():
        p = l.rsplit('|', 2)
        if len(p) == 3:
            res[p[0] + '|' + p[1]] = p[2]
    return [res.get(b + '|' + a) for b, a in pairs]


def hist(pid, tag, timeout=300):
    try:
        rc, out = sh(f'jcmd {pid} GC.class_histogram', check=False, quiet=True, timeout=timeout)
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
    cmd = (f"java -cp {W}/jmxcls Jmx {JMXPORT} poll 1000 100000 {stopf} " + ' '.join(f"'{b}' {a}" for b, a in SAMPLER_BEANS))
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


# ---------------- node ----------------
def write_conf(alloc):
    if os.path.exists(RD):
        shutil.rmtree(RD)
    for d in ('logs', 'data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw', 'dump'):
        os.makedirs(f'{RD}/{d}')
    shutil.copytree(C + '/conf', RD + '/conf')
    env_sh = open(RD + '/conf/cassandra-env.sh').read()
    if 'JMX_PORT="7199"' not in env_sh:
        fail('JMX_PORT line not found in cassandra-env.sh')
    open(RD + '/conf/cassandra-env.sh', 'w').write(env_sh.replace('JMX_PORT="7199"', f'JMX_PORT="{JMXPORT}"', 1))
    lines = ['cluster_name: c6', f'listen_address: {ADDR}', f'rpc_address: {ADDR}',
             'seed_provider:', '  - class_name: org.apache.cassandra.locator.SimpleSeedProvider', '    parameters:', f'      - seeds: "{ADDR}:7000"',
             'data_file_directories:', f'    - {RD}/data', f'commitlog_directory: {RD}/commitlog', f'hints_directory: {RD}/hints',
             f'saved_caches_directory: {RD}/saved_caches', f'cdc_raw_directory: {RD}/cdc_raw']
    if alloc != 'heap_buffers':
        lines.append(f'memtable_allocation_type: {alloc}')
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
    open(RD + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- c6 lines ----\n' + '\n'.join(lines) + '\n')
    sh(f'diff {C}/conf/cassandra.yaml {RD}/conf/cassandra.yaml > {LOGS}/yaml.diff; true', check=False)
    sh(f'diff {C}/conf/cassandra-env.sh {RD}/conf/cassandra-env.sh > {LOGS}/env.diff; true', check=False)


def restore(tmpl):
    for d in ('data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw'):
        shutil.rmtree(f'{RD}/{d}')
        sh(f'cp -a {W}/tmpl/{tmpl}/{d} {RD}/{d}', check=True, quiet=True)
    note('restored', tmpl)


NODE = {'popen': None}


def start(heap, alloc, tmpl=None):
    if pid_of() is not None:
        fail('a node of this harness is already running')
    busy = sh('ss -ltn', quiet=True)[1]
    for w in (f'{ADDR}:7000', f'{ADDR}:9042', f':{JMXPORT}'):
        if re.search(re.escape(w) + r'\s', busy):
            fail(f'port {w} is busy')
    mem = int(re.search(r'MemAvailable:\s+(\d+)', open('/proc/meminfo').read()).group(1)) // 1024
    note('cotenancy', {'daemons': daemons() or 'none', 'MemAvailable_MiB': mem})
    if mem < 30 * 1024:
        fail('MemAvailable < 30 GiB')
    write_conf(alloc)
    if tmpl:
        restore(tmpl)
    env = dict(os.environ, CASSANDRA_CONF=RD + '/conf', CASSANDRA_LOG_DIR=RD + '/logs', CASSANDRA_HEAPDUMP_DIR=RD + '/dump',
               MAX_HEAP_SIZE=heap, XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}')
    for k in ('HEAP_NEWSIZE', 'JVM_EXTRA_OPTS', 'JVM_OPTS'):
        env.pop(k, None)
    scope = SCOPE[heap]
    unit = f'c6-{label.lower()}-{int(time.time())}'
    cmd = (f"systemd-run --user --scope --unit={unit} -p MemoryMax={scope} -p MemorySwapMax=0 "
           f"bash -c 'ulimit -n 100000 && exec bin/cassandra -f -p {RD}/cassandra.pid' > {RD}/stdout.txt 2>&1")
    log('+ ' + cmd)
    NODE['popen'] = subprocess.Popen(cmd, shell=True, cwd=C, env=env)
    t0 = time.time()
    while time.time() - t0 < 600:
        time.sleep(3)
        if NODE['popen'].poll() is not None:
            fail(f'node died during start (exit {NODE["popen"].returncode})')
        if pid_of() and client('probe', quiet=True, timeout=120):
            break
    else:
        fail('node not serving after 600 s')
    pid = pid_of()
    cg = cgroup_path(pid)
    want_max = str(int(scope[:-1]) << 30)
    mmax, sw = readf(cg + '/memory.max'), readf(cg + '/memory.swap.max')
    jvm = open(f'/proc/{pid}/cmdline').read().replace('\0', ' ')
    open(LOGS + '/jvm-cmdline.txt', 'w').write(jvm + '\n')
    flags = {f: (f in jvm) for f in ('-XX:+UseG1GC', '-XX:G1HeapRegionSize=16m', '-XX:+AlwaysPreTouch', '-XX:+HeapDumpOnOutOfMemoryError',
                                     '-XX:OnOutOfMemoryError=kill -9 %p', f'-Xmx{heap}', '-XX:G1NewSizePercent=50')}
    mdm = re.findall(r'-XX:MaxDirectMemorySize=\S+', jvm)
    note('start', {'pid': pid, 'up_s': round(time.time() - t0), 'unit': unit, 'cgroup': cg, 'memory.max': mmax, 'swap.max': sw,
                   'scope_ok': mmax == want_max and sw == '0', 'flags': flags, 'flags_ok': all(flags.values()),
                   'MaxDirectMemorySize': mdm, 'xmx': re.findall(r'-Xmx\S+', jvm)})
    if mmax != want_max or sw != '0':
        fail('scope not applied')
    if not all(flags.values()):
        fail('JVM flags differ')
    return pid, cg


def readback(alloc, heap):
    names = ['memtable_allocation_type', 'memtable_heap_space', 'memtable_offheap_space', 'memtable_cleanup_threshold',
             'memtable_flush_writers', 'commitlog_total_space', 'num_tokens', 'key_cache_size', 'counter_cache_size',
             'prepared_statements_cache_size', 'tables_fail_threshold', 'tables_warn_threshold']
    got = client('settings', *names, quiet=True)
    s = got and got.get('settings') or {}
    quarter = {'2G': '512MiB', '4G': '1024MiB', '8G': '2048MiB'}[heap]
    ok = s.get('memtable_allocation_type') == alloc and s.get('memtable_heap_space') == quarter
    note('settings', {'values': s, 'ok': ok})
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
    for f in ('system.log', 'debug.log'):
        try:
            out += [l.rstrip() for l in open(f'{RD}/logs/{f}') if 'Enqueuing flush of ks.' in l]
        except OSError:
            pass
    return out


def scan_dump(path, tag):
    rc, out = sh(f'python3 -I {HARNESS}/hprof_scan.py {path}', check=False, timeout=1800, cwd='/')
    js = [l for l in out.splitlines() if l.startswith('{')]
    r = json.loads(js[-1]) if js else {'error': out[-500:]}
    json.dump(r, open(f'{LOGS}/scan-{tag}.json', 'w'))
    note('scan ' + tag, r)
    return r


def finish():
    left = daemons()
    note('end', {'daemons_left': left or 'none'})
    if pid_of() is None:
        shutil.rmtree(RD, ignore_errors=True)


# ---------------- modes ----------------
def mode_shakedown():
    pid, cg = start('8G', 'heap_buffers')
    readback('heap_buffers', '8G')
    note('tablecount', client('tablecount', quiet=True))
    time.sleep(20)
    start_samplers(pid, cg)
    time.sleep(10)
    hist2(pid, 'idle')
    time.sleep(5)
    stop_samplers()
    stop_node()
    collect()
    finish()


def mode_build(restore_t, first, last, out_t):
    pid, cg = start('8G', 'heap_buffers', None if restore_t == '-' else restore_t)
    readback('heap_buffers', '8G')
    note('tablecount_start', client('tablecount', quiet=True))
    time.sleep(20)
    hist2(pid, f'n{first}')
    for a in range(first, last + 1, 500):
        b = min(a + 499, last)
        r = client('schema', a, b, LOGS, timeout=3600)
        note(f'schema {a}-{b}', r)
        if not r or not r.get('agreement'):
            fail('schema creation failed')
        hist2(pid, f'n{b + 1}')
    note('tablecount_end', client('tablecount', quiet=True))
    sh(f'bin/nodetool -h 127.0.0.1 -p {JMXPORT} drain', timeout=900)
    stop_node()
    collect()
    note('commitlog_after_drain', sh(f'ls -la {RD}/commitlog', check=False, quiet=True)[1])
    tdirs = len([d for d in os.listdir(f'{RD}/data/ks')]) if os.path.isdir(f'{RD}/data/ks') else 0
    sst = sh(f'find {RD}/data/ks -name "*-Data.db" | wc -l', check=False, quiet=True)[1].strip()
    note('template_check', {'ks_table_dirs': tdirs, 'ks_sstables': sst})
    dst = f'{W}/tmpl/{out_t}'
    shutil.rmtree(dst, ignore_errors=True)
    os.makedirs(dst)
    for d in ('data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw'):
        sh(f'cp -a {RD}/{d} {dst}/{d}', quiet=True)
    shutil.copy(RD + '/conf/cassandra.yaml', dst + '/cassandra.yaml')
    note('template', dst)
    finish()


def wait_death(limit):
    t0 = time.time()
    while time.time() - t0 < limit:
        if pid_of() is None:
            return True
        time.sleep(1)
    return pid_of() is None


def mode_life(arm, heap, tmpl, M):
    alloc = ARM_ALLOC[arm]
    pid, cg = start(heap, alloc, tmpl)
    readback(alloc, heap)
    tc = client('tablecount', quiet=True)
    note('tablecount', tc)
    if not tc or tc.get('tables') != M:
        fail(f'table count {tc} != {M}')
    replay = sh(f"grep -E 'Replaying|replayed|No commitlog files' {RD}/logs/system.log | head -5", check=False, quiet=True)[1]
    note('commitlog_replay_lines', replay)
    time.sleep(20)
    start_samplers(pid, cg)
    time.sleep(10)
    note('L0', hist2(pid, 's0'))
    time.sleep(10)
    note('flush_lines_before', len(flush_lines()))
    if arm in ('T', 'I'):
        r = client('spread', 1, M - 1, 100, 8, LOGS, timeout=1200)
    elif arm == 'C':
        r = client('fill', 't0', 1, M - 1, 100, 8, LOGS, timeout=1200)
    elif arm == 'D8':
        r = None
        steps = [(1, 500), (501, 1000), (1001, 2000), (2001, M - 1)]
        for a, b in steps:
            rr = client('spread', a, b, 100, 8, LOGS, timeout=1200)
            note(f'D8 write {a}-{b}', rr)
            time.sleep(10)
            hist2(pid, f'w{b}')
        # diagnostic (after the D8 readings): per-table counted on-heap bytes of the system keyspaces (source of K at s0)
        sysk = {}
        for ks in ('system', 'system_schema', 'system_distributed', 'system_auth', 'system_traces'):
            _, out = sh(f"java -cp {W}/jmxcls Jmx {JMXPORT} query 'org.apache.cassandra.metrics:type=Table,keyspace={ks},scope=*,name=MemtableOnHeapDataSize' Value",
                        check=False, quiet=True, timeout=120)
            for l in out.splitlines():
                m = re.search(r'scope=([^,|]+).*\|Value\|(-?\d+)$', l)
                if m and int(m.group(2)) > 0:
                    sysk[f'{ks}.{m.group(1)}'] = int(m.group(2))
        note('D8 system tables on-heap (counted)', sysk)
    note('client', r)
    fl = flush_lines()
    note('flush_lines_ks', fl[:20])
    alive = pid_of() is not None
    if alive and arm == 'T' and r and r.get('stopped') != 'end':
        log('client stalled with the node alive: wait <= 300 s for an OOM')
        alive = not wait_death(300)
    if not alive:
        # OOM path: shipped HeapDumpOnOutOfMemoryError then kill -9 %p
        wait_death(180)
        stop_samplers()
        out = readf(RD + '/stdout.txt') or ''
        oom_lines = [l for l in out.splitlines() if 'OutOfMemoryError' in l or 'Dumping heap' in l or 'Heap dump file' in l
                     or 'kill -9' in l or 'Killed' in l]
        dumps = [f for f in os.listdir(RD + '/dump') if f.endswith('.hprof')]
        dinfo = []
        for d in dumps:
            p = f'{RD}/dump/{d}'
            birth = sh(f'stat -c "%W %Y %s" {p}', check=False, quiet=True)[1].split()
            dinfo.append({'file': d, 'birth_s': birth[0], 'mtime_s': birth[1], 'bytes': birth[2]})
        note('oom', {'stdout_lines': oom_lines[:20], 'dumps': dinfo, 'exit': NODE['popen'].poll()})
        collect()
        for d in dumps:
            scan_dump(f'{RD}/dump/{d}', 'oom')
            os.remove(f'{RD}/dump/{d}')
        finish()
        return
    # surviving lifetime
    time.sleep(10)
    note('U_end', hist2(pid, 'end'))
    if label.endswith('-1') or arm == 'D8':
        rc, _ = sh(f'jcmd {pid} GC.heap_dump {RD}/dump/end.hprof', check=False, timeout=900)
        stop_samplers()
        stop_node()
        collect()
        scan_dump(f'{RD}/dump/end.hprof', 'end')
        try:
            os.remove(f'{RD}/dump/end.hprof')
        except OSError:
            pass
    else:
        stop_samplers()
        stop_node()
        collect()
    finish()


try:
    sh(f'mkdir -p {W}/jmxcls && javac -d {W}/jmxcls {HARNESS}/Jmx.java', cwd='/', quiet=True)
    if mode == 'down':
        stop_node()
        note('down', daemons() or 'none')
    elif mode == 'shakedown':
        mode_shakedown()
    elif mode == 'build':
        mode_build(args[2], int(args[3]), int(args[4]), args[5])
    else:
        mode_life(args[2], args[3], args[4], int(args[5]))
    note('DONE', True)
except SystemExit:
    raise
except Exception as e:
    fail(f'exception {e!r}')
