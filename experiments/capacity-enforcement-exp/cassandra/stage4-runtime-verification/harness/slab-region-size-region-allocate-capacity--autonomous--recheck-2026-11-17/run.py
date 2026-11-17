#!/usr/bin/env python3
"""Stage 4 of the recheck claim of slab-region-size-region-allocate-capacity--autonomous (design section of 2026-11-17, frozen
git hash-object cd3c3273a7015fe24a1f7d6abd0f90301b924c7a). One node lifetime per call, on pc91.
usage: run.py <arm>        arms: H2048 U2048 H256 H64 (order of the design: H2048, U2048, H256, H64)
       run.py down         stop this harness's node, if any
Lifetime: write conf under /mydata/s4/slabrc-run/conf (shipped conf + cluster name, address 127.0.6.1, directories, the arm's
memtable_allocation_type / memtable_heap_space; JMX port 7160), start bin/cassandra -f (MAX_HEAP_SIZE=8G) inside
systemd-run --user --scope -p MemoryMax=12G -p MemorySwapMax=0, read back the settings and JVM flags, create ks.t0..ks.t400,
20 s idle, two GC.run, then the steps s0, c1, s50, s100, s200, s400 (and pc for H64), each followed by 10 s idle and the
measurement M (two class histograms, gauges, per-table gauges, heap used, cgroup memory.current, flush lines).
Output: /mydata/s4/slabrc-logs/<RUN>/<arm>/ (session.log with every command, summary.txt, steps.json, hist-<step>-<i>.txt,
system.log, stdout.txt). Exit 1 on a failed set-up check (the node is then stopped)."""
import json, os, re, shutil, subprocess, sys, time

C = os.environ.get('CASSANDRA_HOME', '/mydata/s4/slabrc')
RD = '/mydata/s4/slabrc-run'
RUN = os.environ.get('SR_RUN', 'run1')
HARNESS = os.path.dirname(os.path.abspath(__file__))
ADDR, JMXPORT, BUDGET = '127.0.6.1', 7160, '12G'
NT = 400
ARMS = {'H2048': ('heap_buffers', None), 'U2048': ('unslabbed_heap_buffers', None),
        'H256': ('heap_buffers', '256MiB'), 'H64': ('heap_buffers', '64MiB')}
G_ON = 'org.apache.cassandra.metrics:type=Table,name=AllMemtablesOnHeapDataSize'
G_OFF = 'org.apache.cassandra.metrics:type=Table,name=AllMemtablesOffHeapDataSize'
G_PEND = 'org.apache.cassandra.metrics:type=MemtablePool,name=PendingFlushTasks'
G_HEAP = 'java.lang:type=Memory'
PER_TABLE = 'org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=*,name=MemtableOnHeapDataSize'

args = sys.argv[1:]
if len(args) != 1 or (args[0] not in ARMS and args[0] != 'down'):
    sys.exit(__doc__)
arm = args[0]
LOGS = f'/mydata/s4/slabrc-logs/{RUN}/{arm}'
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
SUMMARY = open(LOGS + '/summary.txt', 'a' if arm == 'down' else 'w')


def log(s):
    line = f'[{time.strftime("%F %T")} {int(time.time()*1000)}] {s}'
    print(line, file=sys.stderr, flush=True)
    SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    SUMMARY.write(s + '\n'); SUMMARY.flush(); log(s)


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
    """the java process whose command line carries this harness's pidfile property (bin/cassandra -f writes no pidfile;
    defect 2 of the results file)"""
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
    return sh("ps -eo pid,cmd | grep '[C]assandraDaemon' | cut -c1-200 || true", check=False, quiet=True)[1].strip()


def stop_node():
    pid = pid_of()
    if pid is None:
        return
    log(f'stopping node pid {pid} (SIGTERM)')
    subprocess.run(['kill', str(pid)])
    for _ in range(120):
        if pid_of() is None:
            return
        time.sleep(1)
    log(f'node did not stop; kill -9 {pid}')
    subprocess.run(['kill', '-9', str(pid)])
    time.sleep(2)


NODE = None


def fail(msg):
    note('FAIL: ' + msg)
    stop_node()
    sys.exit(1)


def client(*a, timeout=3600):
    rc, out = sh(f'python3 -I {HARNESS}/client.py ' + ' '.join(str(x) for x in a), timeout=timeout, check=False,
                 env=dict(os.environ, CASSANDRA_HOME=C), quiet=(a[0] == 'probe'))
    js = [l for l in out.splitlines() if l.startswith('{')]
    return json.loads(js[-1]) if rc == 0 and js else None


def jmx(*pairs):
    _, out = sh(f'java -cp {LOGS}/jmxcls Jmx {JMXPORT} get ' + ' '.join(f"'{b}' {a}" for b, a in pairs), check=False, quiet=True, timeout=120)
    res = {}
    for l in out.splitlines():
        p = l.rsplit('|', 2)
        if len(p) == 3:
            res[p[0] + '|' + p[1]] = p[2]
    return [res.get(b + '|' + a) for b, a in pairs]


def per_table():
    _, out = sh(f"java -cp {LOGS}/jmxcls Jmx {JMXPORT} query '{PER_TABLE}' Value", check=False, quiet=True, timeout=120)
    vals = {}
    for l in out.splitlines():
        m = re.search(r'scope=(t\d+)[,|].*\|Value\|(-?\d+)$', l)
        if m:
            vals[m.group(1)] = int(m.group(2))
    return vals


def hist(pid, tag):
    rc, out = sh(f'jcmd {pid} GC.class_histogram', check=False, quiet=True, timeout=300)
    open(f'{LOGS}/hist-{tag}.txt', 'w').write(out)
    bb = bn = tot = None
    for l in out.splitlines():
        m = re.match(r'\s*\d+:\s+(\d+)\s+(\d+)\s+(\S+)', l)
        if m and m.group(3) == '[B':
            bn, bb = int(m.group(1)), int(m.group(2))
        m = re.match(r'Total\s+(\d+)\s+(\d+)', l.strip())
        if m:
            tot = int(m.group(2))
    return {'bb': bb, 'bn': bn, 'total': tot}


def cgroup_path(pid):
    for l in open(f'/proc/{pid}/cgroup'):
        if l.startswith('0::'):
            return '/sys/fs/cgroup' + l.strip()[3:]
    return None


def readf(p):
    try:
        return open(p).read().strip()
    except OSError:
        return None


def flush_lines():
    try:
        return [l.rstrip() for l in open(RD + '/logs/system.log') if 'Enqueuing flush of ks.' in l]
    except OSError:
        return []


def measure(pid, step, cg, extra=None):
    time.sleep(10)
    g1 = jmx((G_ON, 'Value'), (G_OFF, 'Value'), (G_PEND, 'Value'))
    h1 = hist(pid, step + '-1')
    h2 = hist(pid, step + '-2')
    heap_used, g_on, g_off = jmx((G_HEAP, 'HeapMemoryUsage'), (G_ON, 'Value'), (G_OFF, 'Value'))
    pt = per_table()
    fl = flush_lines()
    m = {'step': step, 'ms': int(time.time() * 1000), 'bb': h2['bb'], 'bn': h2['bn'], 'hist_total': h2['total'], 'bb_first': h1['bb'],
         'heap_used': int(heap_used) if heap_used and heap_used.isdigit() else heap_used,
         'on': int(g_on) if g_on and g_on.lstrip('-').isdigit() else g_on, 'off': int(g_off) if g_off and g_off.lstrip('-').isdigit() else g_off,
         'on_before_hist': g1[0], 'pending': g1[2], 'tables_with_data': sum(1 for v in pt.values() if v > 0), 'tables_seen': len(pt),
         'per_table_sum': sum(pt.values()), 'small_with_data': sum(1 for k, v in pt.items() if k != 't0' and v > 0), 't0_on': pt.get('t0'),
         'flush_lines': len(fl), 'flush_lines_small': sum(1 for l in fl if not re.search(r'flush of ks\.t0,', l)),
         'flush_t0_limit': sum(1 for l in fl if re.search(r'flush of ks\.t0, Reason: MEMTABLE_LIMIT', l)),
         'cg_current': readf(cg + '/memory.current') if cg else None, 'cg_oom_kill': readf(cg + '/memory.events') if cg else None}
    if extra:
        m.update(extra)
    note(f'M {step}: ' + json.dumps(m))
    if m['bb'] is None or h1['bb'] is None:
        fail(f'class histogram unreadable at {step}')
    return m


def write_conf(alloc, space):
    if os.path.exists(RD):
        shutil.rmtree(RD)
    for d in ('logs', 'data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw'):
        os.makedirs(f'{RD}/{d}')
    shutil.copytree(C + '/conf', RD + '/conf')
    env_sh = open(RD + '/conf/cassandra-env.sh').read()
    if 'JMX_PORT="7199"' not in env_sh:
        fail('JMX_PORT line not found in cassandra-env.sh')
    open(RD + '/conf/cassandra-env.sh', 'w').write(env_sh.replace('JMX_PORT="7199"', f'JMX_PORT="{JMXPORT}"', 1))
    lines = ['cluster_name: stage4-slabrc', f'listen_address: {ADDR}', f'rpc_address: {ADDR}',
             'seed_provider:', '  - class_name: org.apache.cassandra.locator.SimpleSeedProvider', '    parameters:', f'      - seeds: "{ADDR}:7000"',
             'data_file_directories:', f'    - {RD}/data', f'commitlog_directory: {RD}/commitlog', f'hints_directory: {RD}/hints',
             f'saved_caches_directory: {RD}/saved_caches', f'cdc_raw_directory: {RD}/cdc_raw', f'memtable_allocation_type: {alloc}']
    if space:
        lines.append(f'memtable_heap_space: {space}')
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
    open(RD + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 slabrc lines ----\n' + '\n'.join(lines) + '\n')
    sh(f'diff {C}/conf/cassandra.yaml {RD}/conf/cassandra.yaml | grep "^[<>]" | grep -v "^< *#" | head -40', check=False)
    sh(f'diff {C}/conf/cassandra-env.sh {RD}/conf/cassandra-env.sh', check=False)


def lifetime():
    alloc, space = ARMS[arm]
    note(f'run.py {arm} {time.strftime("%F %T %Z")} host {os.uname().nodename.split(".")[0]} tree {C} alloc={alloc} '
         f'memtable_heap_space={space or "default"} budget MemoryMax={BUDGET}')
    if pid_of() is not None:
        fail('a node of this harness is already running')
    busy = sh('ss -ltn', quiet=True)[1]
    for w in (f'{ADDR}:7000', f'{ADDR}:9042', f'127.0.0.1:{JMXPORT}'):
        if re.search(r'\s' + re.escape(w) + r'\s', busy):
            fail(f'port {w} is busy')
    note('CassandraDaemon processes before start: ' + (daemons() or 'none'))
    sh(f'mkdir -p {LOGS}/jmxcls && javac -d {LOGS}/jmxcls {HARNESS}/Jmx.java', cwd='/')
    write_conf(alloc, space)
    env = dict(os.environ, CASSANDRA_CONF=RD + '/conf', CASSANDRA_LOG_DIR=RD + '/logs')
    for k in ('HEAP_NEWSIZE', 'JVM_EXTRA_OPTS'):
        env.pop(k, None)
    env['MAX_HEAP_SIZE'] = '8G'   # amendment of 2026-11-17 (runbook defect 1): the shipped default heap is 31 GiB here
    unit = f'slabrc-{arm.lower()}-{int(time.time())}'
    cmd = (f"systemd-run --user --scope --unit={unit} -p MemoryMax={BUDGET} -p MemorySwapMax=0 "
           f"bash -c 'ulimit -n 100000 && exec bin/cassandra -f -p {RD}/cassandra.pid' > {RD}/stdout.txt 2>&1")
    log('+ ' + cmd)
    global NODE
    NODE = subprocess.Popen(cmd, shell=True, cwd=C, env=env)
    t_start = time.time()
    up = False
    while time.time() - t_start < 300:
        time.sleep(3)
        if NODE.poll() is not None:
            fail(f'node died during start (exit {NODE.returncode}); see {RD}/stdout.txt')
        if pid_of() and client('probe', ADDR):
            up = True
            break
    if not up:
        fail('node not serving after 300 s')
    pid = pid_of()
    note(f'node up after {time.time()-t_start:.0f} s, pid {pid}, scope {unit}')
    cg = cgroup_path(pid)
    mmax, sw = readf(cg + '/memory.max'), readf(cg + '/memory.swap.max')
    note(f'EXPECTED cgroup {cg}: memory.max {mmax} (12 GiB = {12 << 30}) swap.max {sw}: ' +
         ('yes' if mmax == str(12 << 30) and sw == '0' else 'NO'))
    if mmax != str(12 << 30):
        fail('budget not applied')
    want = {'memtable_allocation_type': alloc, 'memtable_heap_space': space or '2048MiB'}
    got = client('settings', ADDR, *want.keys(), 'memtable_offheap_space', 'memtable_cleanup_threshold', 'memtable_flush_writers', 'num_tokens')
    note('settings read back: ' + json.dumps(got and got.get('settings')))
    bad = [k for k, v in want.items() if not got or str(got['settings'].get(k)) != v]
    note('EXPECTED settings read-back equals the arm: ' + ('yes' if not bad else 'NO ' + json.dumps(bad)))
    if bad:
        fail('settings read-back differs')
    jvm = open(f'/proc/{pid}/cmdline').read().replace('\0', ' ')
    xmx = re.findall(r'-Xmx\S+', jvm)
    flags_ok = all(x in jvm for x in ('-XX:+UseG1GC', '-XX:G1HeapRegionSize=16m', '-XX:+AlwaysPreTouch', '-Xmx8G'))
    note(f'EXPECTED JVM flags UseG1GC, G1HeapRegionSize=16m, AlwaysPreTouch, -Xmx8G: {"yes" if flags_ok else "NO"}; heap {xmx}')
    if not flags_ok:
        fail('JVM flags differ')
    open(LOGS + '/jvm-cmdline.txt', 'w').write(jvm + '\n')
    s = client('schema', ADDR, NT, timeout=3600)
    note('schema: ' + json.dumps(s))
    if not s or not s.get('agreement'):
        fail('schema creation failed')
    time.sleep(20)
    for _ in range(2):
        sh(f'jcmd {pid} GC.run', check=False)
        time.sleep(3)
    # Defect 3 (results file): the first per-table JMX pattern query caches about 97k ObjectName property maps (live heap), which
    # the frozen order of M put between the s0 and c1 histograms. Warm the instrument before the baseline; s0pre (histograms
    # before the warm-up) shows the instrument's own heap with no write in between. s0pre is diagnostic, not a reading.
    pre = {'pre1': hist(pid, 's0pre-1'), 'pre2': hist(pid, 's0pre-2')}
    pre['per_table_tables'] = len(per_table())
    pre['gauges'] = jmx((G_ON, 'Value'), (G_OFF, 'Value'), (G_PEND, 'Value'), (G_HEAP, 'HeapMemoryUsage'))
    note('s0pre (before the instrument warm-up; diagnostic): ' + json.dumps(pre))
    steps = [measure(pid, 's0', cg, {'s0pre': pre})]
    r = client('fill', ADDR, 't0', 1, 400, 16)
    note('c1 write: ' + json.dumps(r))
    steps.append(measure(pid, 'c1', cg, {'client': r}))
    first = 1
    for n in (50, 100, 200, 400):
        r = client('one', ADDR, first, n)
        note(f's{n} write: ' + json.dumps(r))
        steps.append(measure(pid, f's{n}', cg, {'client': r, 'N': n}))
        first = n + 1
    if arm == 'H64':
        r = client('fill', ADDR, 't0', 401, 40000, 32)
        note('pc write: ' + json.dumps(r))
        t0 = time.time()
        zeros = 0
        while time.time() - t0 < 300 and zeros < 3:
            p = jmx((G_PEND, 'Value'))[0]
            zeros = zeros + 1 if p == '0' else 0
            time.sleep(1)
        note(f'pending flush tasks 0 (3 reads) after {time.time()-t0:.0f} s: ' + ('yes' if zeros >= 3 else 'NO'))
        time.sleep(5)
        steps.append(measure(pid, 'pc', cg, {'client': r}))
    json.dump({'arm': arm, 'alloc': alloc, 'space': space, 'pid': pid, 'xmx': xmx, 'unit': unit, 'cgroup': cg, 'memory_max': mmax,
               'settings': got and got.get('settings'), 'schema': s, 'steps': steps}, open(LOGS + '/steps.json', 'w'), indent=1)
    oom = readf(cg + '/memory.events')
    note('memory.events at the end: ' + (oom or '').replace('\n', '; '))
    stop_node()
    if NODE.poll() is None:
        NODE.wait(timeout=60)
    sh(f'cp {RD}/logs/system.log {LOGS}/system.log', check=False)
    sh(f'cp {RD}/stdout.txt {LOGS}/stdout.txt', check=False)
    errs = sh(f"grep -c '^ERROR' {LOGS}/system.log || true", check=False, quiet=True)[1].strip()
    note(f'ERROR lines in system.log: {errs}')
    time.sleep(3)
    left = daemons()
    note('EXPECTED nothing left running (no CassandraDaemon): ' + ('yes' if not left else 'NO ' + left))
    sh(f'rm -rf {RD}', check=False)


if arm == 'down':
    stop_node()
    note('down; CassandraDaemon left: ' + (daemons() or 'none'))
else:
    try:
        lifetime()
    except SystemExit:
        raise
    except Exception as e:
        fail(f'exception {e!r}')
