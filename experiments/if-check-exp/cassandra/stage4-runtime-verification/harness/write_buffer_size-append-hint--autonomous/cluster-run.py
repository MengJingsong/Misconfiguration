#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of write_buffer_size-append-hint--autonomous (audit amendments of 2026-10-28).
usage: cluster-run.py main | analyze | down | list
  main     every arm of B3e in one script, resumable (arms already in arms.json are skipped; HWB_ONLY=name,name runs a subset).
           Set-up (once, when ~/s4-hwb/n-hwb2 does not exist): wipe, yaml (B3a), start A (the seed, Byteman hwb.btm) then B, UN on
           both, statushandoff, a control with B up (B3h: 128 MiB of 1 MiB values, no hint expected), B stopped (drain, stopdaemon),
           A sees B DN.  Each arm: drop the previous keyspace, clear snapshots, stop A, start A with the arm's build and yaml lines
           (B stays down), truncatehints until A's hints directory holds no .hints file, new keyspace, GC, baseline (median of 10 s),
           then the load of one payload size, 1 GiB of values (HWB_BYTES), HWB_CONC requests in flight, then a settle of three
           hints_flush_periods; the sampler of A runs all the time (1 s: direct pool, heap, TotalHints, RSS, the .hints files).
  analyze  reads arms.json, writes analysis.txt (cross-arm relations).
  down     stop both nodes of this harness.
A = 127.0.0.2 (JMX 7102, coordinator, measured), B = 127.0.0.3 (JMX 7103), both on this host.
Output: ~/s4-hwb/logs/write_buffer_size-append-hint--autonomous/<run>/cluster/ (summary.txt with EXPECTED lines, session.log, samples/hints csv per arm, arms.json,
traces, NMT, logs). Exit 1: a set-up check failed; both nodes are stopped on any exit. A reading that misses a prediction is
recorded as EXPECTED ... NO and the run goes on; the AI judges it in the results file.
Environment: HWB_RUN (default run1), HWB_BYTES, HWB_REPS, HWB_ONLY, HWB_SEED. From the WRITE_BUFFER_SIZE-append-remaining
harness's cluster-run.py (node start/stop, sampler, arm, reset)."""
import glob, json, os, random, re, statistics, subprocess, sys, threading, time

# ------------------------------------------------------------------ the case (the only part that differs between the two harness folders)
STEM = 'write_buffer_size-append-hint--autonomous'
NODES_DIR = 'n-hwb2'
BUILDS = {'b256k': ('base', 262144), 'b64k': ('var-64k', 65536), 'b1024k': ('var-1024k', 1048576)}                   # name -> (directory under ~/s4-hwb, WRITE_BUFFER_SIZE)
PAYLOADS = [1024, 409600]               # value sizes, bytes
CONC = {1024: 32, 409600: 8}                       # requests in flight by payload
CONTROLS = [('ctl-seg128-p1k', 'b256k', 1024, ['commitlog_segment_size=128MiB'], 'slab128'),
            ('ctl-perhost64-p1k', 'b256k', 1024, ['max_hints_size_per_host=64MiB'], 'perhost')]               # (name, build, payload, yaml lines, kind)
DELIVER = False                 # per-build delivery check (case 1 only)
FLUSH_PERIOD_S = 1          # hints_flush_period in seconds (the yaml default is 10 s; case 2 sets 1 s)
EXTRA_YAML = ['hints_flush_period=1000ms']           # lines for every arm
# ------------------------------------------------------------------

HOME = os.path.expanduser('~')
S4 = HOME + '/s4-hwb'
BASE = S4 + '/base'                 # the built copy made by copy-source.sh; nodetool, driver, Byteman jar come from it
HARNESS = os.path.dirname(os.path.abspath(__file__))
WBS = S4 + '/' + NODES_DIR
RUN = os.environ.get('HWB_RUN', 'run1')
KIB, MIB, GIB = 1024, 1 << 20, 1 << 30
ARM_BYTES = int(os.environ.get('HWB_BYTES', GIB))
REPS = int(os.environ.get('HWB_REPS', 2))
ONLY = [x for x in os.environ.get('HWB_ONLY', '').split(',') if x]
SEED = int(os.environ.get('HWB_SEED', 20261028))
CTRL_BYTES = 128 * MIB
NODES = {'A': ('127.0.0.2', 7102), 'B': ('127.0.0.3', 7103)}
CLIENT = HARNESS + '/client.py'
JMXCP = S4 + '/jmx'
BM = BASE + '/build/lib/jars/byteman-4.0.20.jar'
STARTS = {'A': 0}
TRACE = ''
CUR = {'build': 'b256k'}
SP = 'org.apache.cassandra.db:type=StorageProxy'
COLS = [('direct_used', 'java.nio:type=BufferPool,name=direct', 'MemoryUsed'),
        ('direct_count', 'java.nio:type=BufferPool,name=direct', 'Count'),
        ('heap_used', 'java.lang:type=Memory', 'HeapMemoryUsage'),
        ('total_hints', 'org.apache.cassandra.metrics:type=Storage,name=TotalHints', 'Count'),
        ('hints_in_progress', 'org.apache.cassandra.metrics:type=Storage,name=TotalHintsInProgress', 'Count')]

args = sys.argv[1:]
if not args or args[0] not in ('main', 'analyze', 'down', 'list'):
    sys.exit(__doc__)
MODE = args[0]
ROOT = f'{S4}/logs/{STEM}/{RUN}/cluster'
LOGS = ROOT
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
SUMMARY = open(LOGS + '/summary.txt', 'a')
EXPECT = {'yes': 0, 'no': 0}
CHILDREN = []


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, file=sys.stderr)
    SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush(); log(s)


def sh(cmd, timeout=600, check=True, env=None, cwd=BASE, quiet=False):
    log('+ ' + cmd)
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
    except subprocess.TimeoutExpired:
        log(f'  TIMEOUT after {timeout} s')
        if check:
            raise RuntimeError(f'command timed out: {cmd}')
        return 124, ''
    out = (r.stdout or '') + (r.stderr or '')
    if not quiet:
        SESSION.write(out[-6000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed rc={r.returncode}: {cmd}\n{out[-1200:]}')
    return r.returncode, out


def expect(desc, cond):
    EXPECT['yes' if cond else 'no'] += 1
    note(f'EXPECTED: {desc} — {"yes" if cond else "NO (recorded; the AI judges it in the results file)"}')
    return cond


PIDS = {}


def pid_of(node):
    f = f'{WBS}/{node}/cassandra.pid'
    try:
        PIDS[node] = int(open(f).read().strip())
    except (ValueError, OSError):
        pass
    pid = PIDS.get(node)
    if pid is None:
        return None
    try:
        return pid if 'CassandraDaemon' in open(f'/proc/{pid}/cmdline').read() else None
    except OSError:
        return None


def any_daemon():
    # java processes only (another session's shell can carry the text "CassandraDaemon")
    return sh("ps -eo cmd | grep -E '^[^ ]*java .*org\\.apache\\.cassandra\\.service\\.CassandraDaemon' || true",
              check=False, quiet=True)[1].strip()


def nodetool(node, cmd, timeout=180, check=False, quiet=True):
    return sh(f'bin/nodetool -h 127.0.0.1 -p {NODES[node][1]} {cmd}', timeout=timeout, check=check, quiet=quiet)


def stop_node(node, wait_s=120):
    if pid_of(node) is None:
        return
    nodetool(node, 'stopdaemon', timeout=wait_s, quiet=False)
    for _ in range(wait_s):
        if pid_of(node) is None:
            return
        time.sleep(1)
    pid = pid_of(node)
    if pid is not None:
        note(f'{node} did not stop within {wait_s} s; kill -9 {pid}')
        subprocess.run(['kill', '-9', str(pid)])
        time.sleep(3)


def stop_all():
    for n in ('B', 'A'):
        stop_node(n)
    left = any_daemon()
    if left:
        log('WARNING: a CassandraDaemon is still running: ' + left[:300])
    return not left


def fail(msg):
    note('FAIL: ' + msg)
    for p in CHILDREN:
        if p.poll() is None:
            p.kill()
    stop_all()
    sys.exit(1)


def client(*a, timeout=3600):
    rc, out = sh(f'python3 {CLIENT} ' + ' '.join(str(x) for x in a), timeout=timeout, check=False,
                 env=dict(os.environ, CASSANDRA_HOME=BASE))
    js = [l for l in out.splitlines() if l.startswith('{')]
    return json.loads(js[-1]) if js else None


def jmx(node, *pairs):
    _, out = sh(f'java -cp {JMXCP} Jmx {NODES[node][1]} get ' + ' '.join(f"'{x}'" for p in pairs for x in p),
                check=False, quiet=True, timeout=120)
    res = {}
    for l in out.splitlines():
        parts = l.rsplit('|', 2)
        if len(parts) == 3:
            res[(parts[0], parts[1])] = parts[2]
    return res


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def start_node(node, build='b256k', yaml_extra=()):
    if pid_of(node) is not None:
        fail(f'{node} is already running')
    PIDS.pop(node, None)
    home = S4 + '/' + (BUILDS[build][0] if node == 'A' else 'base')
    ylines = ' '.join(f"'{x}'" for x in list(EXTRA_YAML) + list(yaml_extra))
    _, y = sh(f'{HARNESS}/make-node-yaml.sh {node} {ylines}', env=dict(os.environ, CASSANDRA_HOME=home, HWB_NODES=WBS))
    note(y.strip().splitlines()[-1][:1500])
    N = f'{WBS}/{node}'
    env = dict(os.environ, CASSANDRA_HOME=home, CASSANDRA_CONF=N + '/conf', CASSANDRA_LOG_DIR=N + '/logs', MAX_HEAP_SIZE='2G', HEAP_NEWSIZE='400M')
    env.pop('JVM_EXTRA_OPTS', None)
    extra = ''
    global TRACE
    if node == 'A':
        STARTS['A'] += 1
        TRACE = f'{WBS}/A/hwb-{int(time.time())}-{STARTS["A"]}.trace'
        extra = f'-javaagent:{BM}=script:{HARNESS}/hwb.btm -Dstage4.trace={TRACE} -Dorg.jboss.byteman.verbose=false'
    note(f'start {node} ({build if node == "A" else "base"}): CASSANDRA_HOME={home} MAX_HEAP_SIZE=2G JVM_EXTRA_OPTS="{extra}"')
    sh(f'JVM_EXTRA_OPTS="{extra}" {home}/bin/cassandra -p {N}/cassandra.pid > {N}/stdout.txt 2>&1', env=env, cwd=home)
    for _ in range(30):
        time.sleep(1)
        if pid_of(node) is not None:
            return
    fail(f'{node} did not start; see {N}/stdout.txt')


def status_of(via):
    _, st = nodetool(via, 'status')
    return {a: s for s, a in re.findall(r'^([UD][NLJM])\s+(\S+)\s', st, re.M)}


def wait_up(nodes, timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        ok = True
        for via in nodes:
            if pid_of(via) is None:
                fail(f'{via} died during start')
            st = status_of(via)
            _, sb = nodetool(via, 'statusbinary')
            ok = ok and all(st.get(NODES[n][0]) == 'UN' for n in nodes) and re.search(r'^running\s*$', sb, re.M) is not None
        if ok:
            log(f'{nodes} UN and serving after {time.time() - t0:.0f} s')
            return
        time.sleep(3)
    fail(f'{nodes} not UN within the timeout')


def wait_b_down(timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if status_of('A').get(NODES['B'][0]) == 'DN':
            note(f'A sees B DN after {time.time() - t0:.0f} s')
            return
        time.sleep(2)
    fail('A does not see B down')


def hints_files():
    out = []
    try:
        for e in os.scandir(f'{WBS}/A/hints'):
            if e.name.endswith('.hints'):
                try:
                    out.append((e.name, e.stat().st_size))
                except OSError:
                    pass
    except OSError:
        pass
    return out


def rss_of(node):
    pid = pid_of(node)
    try:
        for l in open(f'/proc/{pid}/status'):
            if l.startswith('VmRSS:'):
                return int(l.split()[1]) * 1024
    except (OSError, TypeError):
        pass
    return 0


class Sampler:
    """A every second: one Jmx poll JVM for the JMX columns, a thread for A's .hints files and A's RSS"""

    def __init__(self, tag):
        self.stop = f'{LOGS}/sampler.stop'
        if os.path.exists(self.stop):
            os.remove(self.stop)
        self.jf = open(f'{LOGS}/samples-jmx-{tag}.csv', 'w')
        self.jf.write('ms,' + ','.join(c for c, _, _ in COLS) + '\n'); self.jf.flush()
        cmd = ['java', '-cp', JMXCP, 'Jmx', str(NODES['A'][1]), 'poll', '1000', '100000000', self.stop]
        for _, bean, attr in COLS:
            cmd += [bean, attr]
        log('+ ' + ' '.join(cmd))
        self.p = subprocess.Popen(cmd, stdout=self.jf, stderr=subprocess.STDOUT)
        CHILDREN.append(self.p)
        self.hf = open(f'{LOGS}/hints-{tag}.csv', 'w')
        self.hf.write('ms,hints_bytes,hints_files,largest_file,rss\n'); self.hf.flush()
        self.alive = True
        self.t = threading.Thread(target=self._hints, daemon=True)
        self.t.start()

    def _hints(self):
        nxt = time.time()
        while self.alive:
            fs = hints_files()
            self.hf.write(f'{int(time.time() * 1000)},{sum(s for _, s in fs)},{len(fs)},{max([s for _, s in fs] or [0])},{rss_of("A")}\n')
            self.hf.flush()
            nxt += 1.0
            time.sleep(max(0.0, nxt - time.time()))

    def close(self):
        open(self.stop, 'w').close()
        self.alive = False
        self.t.join()
        try:
            self.p.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.p.kill()
        self.jf.close(); self.hf.close()


def read_samples(tag):
    rows, hrows = [], []
    for l in open(f'{LOGS}/samples-jmx-{tag}.csv').read().splitlines()[1:]:
        p = l.split(',')
        if len(p) == len(COLS) + 1 and p[0].isdigit():
            rows.append([int(p[0])] + [num(x) for x in p[1:]])
    for l in open(f'{LOGS}/hints-{tag}.csv').read().splitlines()[1:]:
        p = l.split(',')
        if len(p) == 5 and p[0].isdigit():
            hrows.append([int(x) for x in p])
    return sorted(rows), sorted(hrows)


def ci(name):
    return 1 + [c for c, _, _ in COLS].index(name)


def trace_lines():
    try:
        return open(TRACE, errors='replace').read().splitlines()
    except OSError:
        return []


def kv(l):
    return dict(x.split('=', 1) for x in l.split()[1:] if '=' in x)


def trace_stats(t0, t1):
    created, waiting, caps, flush_last, refuse = [], 0, set(), None, []
    asamp = []
    for l in trace_lines():
        d = kv(l)
        ms = int(d['ms']) if 'ms' in d else None
        if l.startswith('created='):
            d = dict(x.split('=', 1) for x in l.split() if '=' in x)
            created.append((int(d['ms']), int(d['created']), int(d['size'])))
        elif l.startswith('waiting') and ms and t0 <= ms <= t1:
            waiting += 1
        elif l.startswith('asamp') and ms and t0 <= ms <= t1:
            caps.add(int(d['cap'])); asamp.append((int(d['sz']), int(d['cap']), d['direct']))
        elif l.startswith('refuse') and ms and t0 <= ms <= t1:
            refuse.append((int(d['checked']), int(d['limit'])))
        elif l.startswith('flush') and ms and ms <= t1:
            flush_last = d
    return {'created': created, 'waiting': waiting, 'caps': sorted(caps), 'asamp': len(asamp),
            'asamp_max_sz': max([a[0] for a in asamp] or [0]), 'asamp_direct': sorted({a[2] for a in asamp}),
            'refuse_samples': len(refuse), 'refuse_min_checked': min([r[0] for r in refuse] or [0]),
            'flush_last': flush_last}


def nmt(pid, name):
    _, out = sh(f'jcmd {pid} VM.native_memory summary', check=False, quiet=True)
    open(f'{LOGS}/nmt-{name}.txt', 'w').write(out)
    m = re.search(r'-\s+Other \(reserved=\d+KB, committed=(\d+)KB\)', out)
    return int(m.group(1)) * 1024 if m else None


def jmx_sum(pattern, attr='Count'):
    _, out = sh(f"java -cp {JMXCP} Jmx 7102 query '{pattern}' {attr}", check=False, quiet=True)
    tot = 0
    for l in out.splitlines():
        p = l.rsplit('|', 2)
        if len(p) == 3 and num(p[2]) is not None:
            tot += int(num(p[2]))
    return tot


def hinted_created():
    return jmx_sum('org.apache.cassandra.metrics:type=HintsService,name=Hints_created*')


def hinted_succeeded():
    return jmx_sum('org.apache.cassandra.metrics:type=HintsService,name=HintsSucceeded')


def du_hints():
    _, o = sh(f'du -sb {WBS}/A/hints', check=False, quiet=True)
    try:
        return int(o.split()[0])
    except (ValueError, IndexError):
        return -1


# ------------------------------------------------------------------ set-up and arms

def setup_once():
    note(f'cluster-run {STEM} {time.strftime("%F %T %Z")} host {os.uname().nodename.split(".")[0]} base {BASE} '
         f'{sh("git describe --tags; git rev-parse --short HEAD", quiet=True)[1].split()} run {RUN}')
    note('harness md5: ' + sh('md5sum cluster-run.py client.py make-node-yaml.sh Jmx.java hwb.btm', quiet=True, cwd=HARNESS)[1].replace('\n', ' ')[:900])
    for b, (d, c) in BUILDS.items():
        _, jp = sh(f'javap -constants -p -cp {S4}/{d}/build/classes/main org.apache.cassandra.hints.HintsWriteExecutor | grep WRITE_BUFFER_SIZE',
                   quiet=True)
        note(f'build {b} ({d}): {jp.strip()} (expected {c})')
        if str(c) not in jp:
            fail(f'build {b}: constant is not {c}')
    note(f'settings: ARM_BYTES={ARM_BYTES} PAYLOADS={PAYLOADS} CONC={CONC} REPS={REPS} SEED={SEED} FLUSH_PERIOD_S={FLUSH_PERIOD_S} EXTRA_YAML={EXTRA_YAML}')
    if any_daemon():
        fail('a CassandraDaemon is already running on this host: ' + any_daemon()[:200])
    _, df = sh(f'df -k {HOME}', quiet=True)
    free_gb = int(df.splitlines()[-1].split()[3]) / 1048576
    note(f'free on {HOME}: {free_gb:.1f} GiB')
    if free_gb < 20:
        fail('less than 20 GiB free (B3a asks >= 20 GiB)')
    os.makedirs(JMXCP, exist_ok=True)
    sh(f'javac -d {JMXCP} {HARNESS}/Jmx.java')
    sh(f'rm -rf {WBS}')
    os.makedirs(WBS)
    start_node('A', 'b256k')
    time.sleep(15)
    start_node('B')
    wait_up(['A', 'B'])
    sh(f'cp {WBS}/A/conf/cassandra.yaml {LOGS}/A-cassandra.yaml; cp {WBS}/B/conf/cassandra.yaml {LOGS}/B-cassandra.yaml')
    _, sho = nodetool('A', 'statushandoff')
    note('A statushandoff: ' + sho.strip().replace('\n', ' '))
    if 'running' not in sho.lower():
        fail('hinted handoff not running on A')
    if not os.path.exists(TRACE):
        fail('no Byteman trace on A (agent not loaded?)')
    p = client('probe', NODES['A'][0])
    if not p or not p.get('ok'):
        fail('probe')
    note(f'probe: {p}')
    _, cmdl = sh(f'cat /proc/{pid_of("A")}/cmdline | tr "\\0" " "', quiet=True)
    for flag in ('-Xmx2G', '-XX:MaxDirectMemorySize=1g', '-XX:NativeMemoryTracking=summary', 'byteman'):
        note(f'A command line has {flag}: {flag in cmdl}')
    sm = Sampler('setup')
    control_arm()
    sm.close()
    note('stopping B (drain, stopdaemon) for the hint arms')
    nodetool('B', 'drain', timeout=300, quiet=False)
    stop_node('B')
    wait_b_down()
    stop_node('A')


def control_arm():
    """B3h: B up, 1 MiB values, no hint expected"""
    client('schema', NODES['A'][0], 'ksctl')
    th0 = num(jmx('A', (COLS[3][1], 'Count')).get((COLS[3][1], 'Count'))) or 0
    t0 = int(time.time() * 1000)
    w = client('write', NODES['A'][0], 'ksctl', MIB, CTRL_BYTES, 8, 0, 600, f'{LOGS}/keys-control.csv')
    time.sleep(5)
    th1 = num(jmx('A', (COLS[3][1], 'Count')).get((COLS[3][1], 'Count'))) or 0
    hb = sum(s for _, s in hints_files())
    note(f'control (B up): writes {w}; TotalHints +{th1 - th0:.0f}; A hints bytes {hb}')
    expect('control: B up, no hint is written (A .hints bytes <= 1 MiB, TotalHints +0)', hb <= MIB and th1 - th0 == 0)
    expect('control: every write succeeded', bool(w) and w['failed'] == 0 and w['succeeded'] == w['written'])
    client('drop', NODES['A'][0], 'ksctl')


def reset(prev_ks, ks_new, sm, tag, build, yaml_extra):
    """between arms (the previous case's D2): drop the keyspace, restart A (a clean stop closes the writer), truncatehints
    until no .hints file is left. B stays down. Returns the new sampler."""
    if prev_ks and pid_of('A') is not None:
        client('drop', NODES['A'][0], prev_ks)
        nodetool('A', 'clearsnapshot --all', quiet=False)
    if sm:
        sm.close()
    stop_node('A')
    start_node('A', build, yaml_extra)
    wait_up(['A'])
    wait_b_down()
    sm = Sampler(tag)
    for i in range(10):
        nodetool('A', 'truncatehints', quiet=False)
        time.sleep(3)
        if not hints_files():
            break
    _, ph = nodetool('A', 'listpendinghints')
    note(f'reset ({tag}): dropped {prev_ks}; A restarted on {build} (trace {os.path.basename(TRACE)}); .hints files after truncatehints: '
         f'{hints_files()}; listpendinghints: ' + ph.strip().replace('\n', ' | ')[:200])
    if hints_files():
        fail('hints files remain after a restart and truncatehints')
    r = client('schema', NODES['A'][0], ks_new)
    if not r:
        fail(f'schema {ks_new}')
    return sm


def baseline(tag, name):
    sh(f'jcmd {pid_of("A")} GC.run', check=False, quiet=True)
    time.sleep(3)
    t0 = int(time.time() * 1000)
    time.sleep(10)
    t1 = int(time.time() * 1000)
    rows, _ = read_samples(tag)
    w = [r for r in rows if t0 <= r[0] <= t1]
    b = {c: statistics.median([r[ci(c)] for r in w if r[ci(c)] is not None] or [0]) for c, _, _ in COLS}
    b['t0'], b['t1'] = t0, t1
    st = trace_stats(0, t1)
    b['slab_bytes'] = sum(c[2] for c in st['created'] if c[0] <= t1)
    b['slabs'] = len([c for c in st['created'] if c[0] <= t1])
    b['residual'] = b['direct_used'] - b['slab_bytes']          # direct memory that is not a hint slab: carries the write buffer
    note(f'{name}: baseline (median of 10 s after GC, B down, A restarted, before the first hint): direct {b["direct_used"] / MIB:.3f} MiB, '
         f'Count {b["direct_count"]:.0f}, heap {b["heap_used"] / MIB:.0f} MiB; slabs already created {b["slabs"]} ({b["slab_bytes"] / MIB:.0f} MiB); '
         f'direct minus slabs {b["residual"]:.0f} B')
    return b


def arm(name, build, ks, size, tag, base, total=None, max_s=1800):
    pidA = pid_of('A')
    total = total or ARM_BYTES
    th0 = num(jmx('A', (COLS[3][1], 'Count')).get((COLS[3][1], 'Count'))) or 0
    hc0 = hinted_created()
    nmt0 = nmt(pidA, name + '-before')
    t0 = int(time.time() * 1000)
    w = client('write', NODES['A'][0], ks, size, total, CONC.get(size, 8), 0, max_s, f'{LOGS}/keys-{name}.csv')
    t_w = int(time.time() * 1000)
    time.sleep(3 * FLUSH_PERIOD_S + 2)                       # settle: three hints_flush_periods (B3e step 4)
    t1 = int(time.time() * 1000)
    th1 = num(jmx('A', (COLS[3][1], 'Count')).get((COLS[3][1], 'Count'))) or 0
    hc1 = hinted_created()
    nmt1 = nmt(pidA, name + '-after')
    fs = hints_files()
    du = du_hints()
    rss_end = rss_of('A')
    _, ph = nodetool('A', 'listpendinghints')
    open(f'{LOGS}/listpendinghints-{name}.txt', 'w').write(ph)
    st = trace_stats(t0, t1)
    a = {'name': name, 'build': build, 'ks': ks, 'size': size, 'tag': tag, 't0': t0, 't_w': t_w, 't1': t1, 'write': w,
         'written': w['written'] if w else 0, 'succeeded': w['succeeded'] if w else 0,
         'total_hints_delta': th1 - th0, 'hints_created_delta': hc1 - hc0, 'hints_bytes_end': sum(s for _, s in fs),
         'hints_files_end': len(fs), 'hints_file_sizes': sorted(s for _, s in fs), 'du_hints': du,
         'nmt_other_before': nmt0, 'nmt_other_after': nmt1, 'rss_end': rss_end, 'trace': st, 'base': base,
         'trace_file': os.path.basename(TRACE)}
    note(f'arm {name}: {build} size {size}; write {w}')
    note(f'arm {name}: TotalHints +{th1 - th0:.0f}, Hints_created +{hc1 - hc0}; .hints files {len(fs)} bytes {a["hints_bytes_end"]} '
         f'(du {du}) largest {max([s for _, s in fs] or [0])}; caps traced {st["caps"]}; flush_last {st["flush_last"]}')
    return a


def peaks(a):
    rows, hrows = read_samples(a['tag'])
    wr = [r for r in rows if a['t0'] <= r[0] <= a['t1']]
    hr = [r for r in hrows if a['t0'] <= r[0] <= a['t1']]
    b = a['base']
    a['samples'] = len(wr)
    a['direct_peak'] = max([r[ci('direct_used')] for r in wr if r[ci('direct_used')] is not None] or [0])
    a['direct_peak_delta'] = a['direct_peak'] - b['direct_used']
    a['direct_count_peak'] = max([r[ci('direct_count')] for r in wr if r[ci('direct_count')] is not None] or [0])
    a['heap_peak'] = max([r[ci('heap_used')] for r in wr if r[ci('heap_used')] is not None] or [0])
    a['rss_peak'] = max([r[4] for r in hr] or [0])
    a['hints_bytes_peak'] = max([r[1] for r in hr] or [0])
    a['hints_files_peak'] = max([r[2] for r in hr] or [0])
    a['largest_file_peak'] = max([r[3] for r in hr] or [0])
    tcut = a['t0'] + 0.6 * (a['t_w'] - a['t0'])
    late = [r[1] for r in hr if tcut <= r[0] <= a['t_w']]
    a['hints_growth_late'] = (max(late) - min(late)) if late else None
    cr = [c for c in a['trace']['created'] if c[0] <= a['t1']]
    a['slabs_total'] = len(cr)
    a['slab_bytes'] = sum(c[2] for c in cr)
    a['slab_sizes'] = sorted({c[2] for c in cr})
    cap = a['trace']['caps'][0] if a['trace']['caps'] else BUILDS[a['build']][1]
    a['cap'] = cap
    a['attributable'] = a['slab_bytes'] + cap
    a['peak_residual'] = a['direct_peak'] - a['slab_bytes']
    note(f'arm {a["name"]}: {len(wr)} samples; direct peak {a["direct_peak"] / MIB:.2f} MiB ({a["direct_peak_delta"] / MIB:+.2f} MiB over the baseline), '
         f'Count peak {a["direct_count_peak"]:.0f}; heap peak {a["heap_peak"] / MIB:.0f} MiB; RSS peak {a["rss_peak"] / MIB:.0f} MiB; hints bytes peak '
         f'{a["hints_bytes_peak"] / MIB:.1f} MiB, files peak {a["hints_files_peak"]}, largest {a["largest_file_peak"] / MIB:.2f} MiB; '
         f'slabs {a["slabs_total"]} of sizes {a["slab_sizes"]} (attributable {a["attributable"] / MIB:.2f} MiB); direct minus slabs at peak '
         f'{a["peak_residual"]:.0f} B; late growth {(a["hints_growth_late"] or 0) / MIB:.2f} MiB')


def fl(a, key, default=0):
    f = a['trace']['flush_last']
    try:
        return int(f[key]) if f else default
    except (KeyError, ValueError):
        return default


def judge(a, kind):
    n = a['name']
    s = a['size']
    vals = a['written'] * s
    cap = a['cap']
    if kind == 'hint':
        ratio = a['hints_bytes_end'] / vals if vals else 0
        a['du_ratio'] = ratio
        expect(f'{n}: traced aggregation-buffer capacity {a["trace"]["caps"]} is the build constant {BUILDS[a["build"]][1]}',
               a['trace']['caps'] == [BUILDS[a['build']][1]])
        expect(f'{n}: hints on disk {a["hints_bytes_end"]} B = {ratio:.4f} x the {vals} B of values written (in full: 0.95-1.10)', 0.95 <= ratio <= 1.10)
        expect(f'{n}: every write hinted: Hints_created +{a["hints_created_delta"]} = written {a["written"]} = entries appended (last flush line) {fl(a, "app")}',
               a['hints_created_delta'] == a['written'] == fl(a, 'app'))
        if s + 12 > cap:
            expect(f'{n}: every entry larger than the {cap} B buffer bypasses it: over={fl(a, "over")} = written {a["written"]}, direct channel writes wrdirect={fl(a, "wrdirect")}',
                   fl(a, 'over') == a['written'] and fl(a, 'wrdirect') == a['written'])
        else:
            expect(f'{n}: entries of {s + 12} B fit the {cap} B buffer: over={fl(a, "over")} = 0, wrdirect={fl(a, "wrdirect")} = 0',
                   fl(a, 'over') == 0 and fl(a, 'wrdirect') == 0)
        expect(f'{n}: appended entry bytes {fl(a, "appbytes")} + 42 B header x {a["hints_files_end"]} files = hints on disk {a["hints_bytes_end"]} (every appended byte reached a file; entry = hint + 12 B)',
               fl(a, 'appbytes') + 42 * a['hints_files_end'] == a['hints_bytes_end'])
        expect(f'{n}: hint files roll at about 128 MiB: largest {max(a["hints_file_sizes"] or [0])} B in [128 MiB, 128 MiB + 4 MiB + one entry]',
               128 * MIB <= max(a['hints_file_sizes'] or [0]) <= 128 * MIB + 4 * MIB + s + 12 + 8 * MIB if vals > 128 * MIB else True)
    return a


def arm_list():
    arms = []
    for b in BUILDS:
        for p in PAYLOADS:
            for r in range(1, REPS + 1):
                arms.append((f'{b}-p{p // KIB}k-r{r}', b, p, [], 'hint'))
    random.Random(SEED).shuffle(arms)
    arms += [(n, b, p, y, k) for n, b, p, y, k in CONTROLS]
    if DELIVER:
        arms += [(f'deliver-{b}', b, 200 * KIB, [], 'deliver') for b in BUILDS]
    return arms


def load_arms():
    try:
        return json.load(open(f'{LOGS}/arms.json'))
    except (OSError, ValueError):
        return []


def save(arms):
    with open(f'{LOGS}/arms.json', 'w') as f:
        json.dump(arms, f, indent=1, default=str)


def deliver_arm(a, sm_ref):
    """B3e step 6 (amended R5): start B, raise the throttle, wait for Hints_succeeded to rise by the hints written"""
    s0 = hinted_succeeded()
    start_node('B')
    wait_up(['A', 'B'])
    nodetool('A', 'sethintedhandoffthrottlekb 100000', quiet=False)
    t0 = time.time()
    left = a['hints_files_end']
    while time.time() - t0 < 300:
        if hinted_succeeded() - s0 >= a['written'] and not hints_files():
            break
        time.sleep(3)
    a['deliver_s'] = round(time.time() - t0, 1)
    a['succeeded_delta'] = hinted_succeeded() - s0
    a['hints_files_after_delivery'] = len(hints_files())
    note(f'arm {a["name"]}: delivery to B: Hints_succeeded +{a["succeeded_delta"]} of {a["written"]} written in {a["deliver_s"]} s; '
         f'.hints files before {left} after {a["hints_files_after_delivery"]}')
    expect(f'{a["name"]}: every hint stored under build {a["build"]} was delivered: Hints_succeeded +{a["succeeded_delta"]} = written {a["written"]}, no .hints file left',
           a['succeeded_delta'] == a['written'] and a['hints_files_after_delivery'] == 0)
    nodetool('B', 'drain', timeout=300, quiet=False)
    stop_node('B')
    wait_b_down()


def main_lifetime():
    arms = load_arms()
    done = {a['name'] for a in arms}
    if not os.path.exists(f'{WBS}/A/conf') or not arms and not os.path.exists(f'{LOGS}/formed'):
        setup_once()
        open(f'{LOGS}/formed', 'w').write(time.strftime('%F %T'))
    else:
        note(f'resume: {len(done)} arms done: {sorted(done)}')
        if any_daemon():
            fail('a CassandraDaemon is already running on this host: ' + any_daemon()[:200])
    plan = arm_list()
    note('plan: ' + ', '.join(p[0] for p in plan))
    prev, sm = None, None
    for name, build, size, yaml_extra, kind in plan:
        if name in done or (ONLY and name not in ONLY):
            continue
        ks = 'ks' + re.sub(r'[^a-z0-9]', '', name)
        sm = reset(prev, ks, sm, name, build, yaml_extra)
        base = baseline(name, name)
        total = 250 * 200 * KIB if kind == 'deliver' else None
        a = arm(name, build, ks, size, name, base, total)
        a['kind'] = kind
        a['yaml_extra'] = yaml_extra
        sm.close(); sm = None
        peaks(a)
        if kind == 'hint':
            judge(a, 'hint')
        elif kind == 'deliver':
            sm = Sampler(name + '-deliver')
            deliver_arm(a, sm)
        else:
            judge_control(a, kind)
        for n in ('A', 'B'):
            sh(f'cp {WBS}/{n}/logs/system.log {LOGS}/{name}-{n}-system.log', check=False)
            _, e = sh(f"grep -c '^ERROR' {WBS}/{n}/logs/system.log", check=False, quiet=True)
            a[f'{n}_errors'] = e.strip()
        sh(f'cp {WBS}/A/hwb-*.trace {LOGS}/ 2>/dev/null; cp {WBS}/A/logs/gc.log* {LOGS}/ 2>/dev/null', check=False)
        arms.append(a)
        save(arms)
        prev = ks
    if sm:
        sm.close()
    stop_all()
    judge_controls_vs_reference(arms)
    note('daemons left: ' + (any_daemon() or 'none'))


def reference(arms, build='b256k', size=None):
    xs = [a for a in arms if a.get('kind') == 'hint' and a['build'] == build and (size is None or a['size'] == size)]
    return xs


def judge_control(a, kind):
    n = a['name']
    if kind == 'filesize':
        mx = max(a['hints_file_sizes'] or [0])
        expect(f'{n}: max_hints_file_size 8MiB: files roll at about 8 MiB: largest {mx} B <= 8 MiB + one entry ({8 * MIB + a["size"] + 12}), count {a["hints_files_end"]} >= 100',
               mx <= 8 * MIB + a['size'] + 12 and a['hints_files_end'] >= 100)
    elif kind == 'perhost':
        lim = 64 * MIB
        expect(f'{n}: max_hints_size_per_host 64MiB: disk stops near it: final {a["hints_bytes_end"] / MIB:.2f} MiB in [64, 64 + 128 + 32] MiB',
               lim <= a['hints_bytes_end'] <= lim + 128 * MIB + 32 * MIB)
        expect(f'{n}: growth stopped: {(a["hints_growth_late"] or 0) / MIB:.2f} MiB in the last 40 % of the write window (< 32 MiB)',
               a['hints_growth_late'] is not None and a['hints_growth_late'] < 32 * MIB)
        expect(f'{n}: refusals at the check: refuse={fl(a, "refuse")} > 0, sampled operands above the limit (min {a["trace"]["refuse_min_checked"]})',
               fl(a, 'refuse') > 0 and a['trace']['refuse_min_checked'] > lim)
        expect(f'{n}: writes still succeed at CL ONE: succeeded {a["succeeded"]} = written {a["written"]}', a['succeeded'] == a['written'] > 0)
    elif kind.startswith('slab'):
        want = int(kind[4:]) * MIB
        expect(f'{n}: slab size follows max(2 x max_mutation_size, 32 MiB): traced slab sizes {a["slab_sizes"]} = [{want}]', a['slab_sizes'] == [want])
        expect(f'{n}: attributable direct memory {a["attributable"] / MIB:.1f} MiB = slabs x {want // MIB} MiB + buffer', a['attributable'] == a['slab_bytes'] + a['cap'])


def judge_controls_vs_reference(arms):
    ref = reference(arms)
    for a in arms:
        k = a.get('kind', '')
        if k in ('filesize', 'perhost') or k.startswith('slab'):
            r = [x for x in ref if x['size'] == a['size']]
            if not r:
                continue
            m = max(x['direct_peak'] for x in r)
            if k.startswith('slab'):
                want = int(k[4:]) * MIB
                if want > 32 * MIB:
                    expect(f'{a["name"]}: memory control moves the pool: direct peak {a["direct_peak"] / MIB:.1f} MiB > reference builds\' max {m / MIB:.1f} MiB + 16 MiB',
                           a['direct_peak'] > m + 16 * MIB)
                else:
                    expect(f'{a["name"]}: slab stays at the floor: direct peak {a["direct_peak"] / MIB:.1f} MiB within one slab of the reference max {m / MIB:.1f} MiB',
                           a['direct_peak'] <= m + 32 * MIB)
            elif k == 'perhost':
                full = min(x['hints_bytes_end'] for x in r)
                expect(f'{a["name"]}: disk control moves disk: {a["hints_bytes_end"] / MIB:.1f} MiB vs {full / MIB:.1f} MiB with the limit off', a['hints_bytes_end'] < full / 4)
            elif k == 'filesize':
                expect(f'{a["name"]}: file-size control: total on disk equal to the reference ({a["hints_bytes_end"]} vs min {min(x["hints_bytes_end"] for x in r)}) but in {a["hints_files_end"]} files vs {max(x["hints_files_end"] for x in r)}',
                       a['hints_files_end'] > 4 * max(x['hints_files_end'] for x in r))


def analyze():
    out = open(f'{ROOT}/analysis.txt', 'w')

    def say(s):
        print(s); out.write(s + '\n')
    arms = load_arms()
    ok = {'yes': 0, 'no': 0}

    def ex(desc, cond):
        ok['yes' if cond else 'no'] += 1
        say(f'EXPECTED: {desc} — {"yes" if cond else "NO"}')
    hint = [a for a in arms if a.get('kind') == 'hint']
    say('arm, build, cap, size, written, succeeded, hints_bytes_end, du_ratio, files, slabs, slab_MiB, attributable_MiB, direct_peak_MiB, '
        'direct_peak_delta_MiB, peak_residual_B, base_residual_B, heap_peak_MiB, rss_peak_MiB, over, wrdirect')
    for a in arms:
        if 'direct_peak' not in a:
            continue
        say(f"{a['name']}, {a['build']}, {a['cap']}, {a['size']}, {a['written']}, {a['succeeded']}, {a['hints_bytes_end']}, "
            f"{a.get('du_ratio', 0):.4f}, {a['hints_files_end']}, {a['slabs_total']}, {a['slab_bytes'] / MIB:.0f}, {a['attributable'] / MIB:.2f}, "
            f"{a['direct_peak'] / MIB:.2f}, {a['direct_peak_delta'] / MIB:.2f}, {a['peak_residual']:.0f}, {a['base']['residual']:.0f}, "
            f"{a['heap_peak'] / MIB:.0f}, {a['rss_peak'] / MIB:.0f}, {fl(a, 'over')}, {fl(a, 'wrdirect')}")
    for p in PAYLOADS:
        xs = [a for a in hint if a['size'] == p]
        if not xs:
            continue
        r = [a['du_ratio'] for a in xs]
        ex(f'X1 payload {p}: hint disk equal across builds and reps: du ratios {[round(x, 4) for x in r]} within 2 % of each other', max(r) / min(r) <= 1.02)
        by = {}
        for a in xs:
            by.setdefault(a['build'], []).append(a)
        sizes = {b: [a['hints_bytes_end'] for a in v] for b, v in by.items()}
        say(f'payload {p}: hint bytes by build {sizes}')
        say(f'payload {p}: direct peak (MiB) by build ' + str({b: [round(a['direct_peak'] / MIB, 1) for a in v] for b, v in by.items()}) +
            '; slabs by build ' + str({b: [a['slabs_total'] for a in v] for b, v in by.items()}) +
            '; peak minus slabs (KiB) by build ' + str({b: [round(a['peak_residual'] / KIB) for a in v] for b, v in by.items()}))
        # R6 / R4: the excess over the constants' difference equals the slab difference
        ref = [a for a in xs if a['build'] == 'b256k']
        for b, v in by.items():
            if b == 'b256k' or not ref:
                continue
            for a in v:
                for rr in ref:
                    dpool = a['direct_peak'] - rr['direct_peak']
                    dcon = BUILDS[b][1] - BUILDS['b256k'][1]
                    dslab = a['slab_bytes'] - rr['slab_bytes']
                    say(f'  {a["name"]} vs {rr["name"]}: pool diff {dpool / MIB:+.2f} MiB; constants diff {dcon / MIB:+.2f} MiB; slab diff {dslab / MIB:+.0f} MiB; '
                        f'pool diff minus constants diff minus slab diff {(dpool - dcon - dslab) / MIB:+.2f} MiB')
    res = {}
    for a in arms:
        if a.get('kind') in ('hint',) and 'base' in a:
            res.setdefault(a['build'], []).append(a['base']['residual'])
    say('baseline direct minus slabs (B) by build: ' + str({b: [round(x) for x in v] for b, v in res.items()}))
    if 'b256k' in res:
        m0 = statistics.median(res['b256k'])
        for b, v in res.items():
            d = statistics.median(v) - m0
            say(f'  build {b}: median baseline residual minus the 256 KiB build\'s {d:+.0f} B; constants difference {BUILDS[b][1] - BUILDS["b256k"][1]:+d} B')
    say(f'analysis EXPECTED yes={ok["yes"]} no={ok["no"]}')


if __name__ == '__main__':
    try:
        if MODE == 'down':
            stop_all()
        elif MODE == 'analyze':
            analyze()
        elif MODE == 'list':
            for x in arm_list():
                print(x)
        else:
            main_lifetime()
    except SystemExit:
        raise
    except BaseException as e:
        import traceback
        note('FAIL: exception ' + repr(e)[:500])
        log(traceback.format_exc())
        for p in CHILDREN:
            if p.poll() is None:
                p.kill()
        stop_all()
        sys.exit(1)
    finally:
        if MODE == 'main':
            note(f'EXPECTED totals (this invocation): yes={EXPECT["yes"]} no={EXPECT["no"]}')
            note('daemons left: ' + (any_daemon() or 'none'))
