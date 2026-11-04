#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of WRITE_BUFFER_SIZE-append-remaining--autonomous (audit amendments R1-R3, 2026-10-20).
usage: cluster-run.py main | mhb1 <rep> | analyze | down
  main        one lifetime of A and B with the default MAX_HINT_BUFFERS (3): wipe ~/stage4-wbs, yaml (B3a), start A (the
              seed, Byteman wbs.btm) then B, UN on both, statushandoff; control with B up (B3h: 256 MiB of 1 MiB values,
              no hint expected); stop B (drain, stopdaemon) and wait for A to see it DN; the lifetime baseline (GC, 10 s);
              then the arms (B3e steps 3 and 5): 100 KiB, 1 MiB, 8 MiB values, each twice (B3h), 2 GiB of values per arm
              (B3c: the first half with 1 request in flight, the second with 8), then max_hints_size_per_host set live to
              64 MiB over JMX and read back, and the 1 MiB arm twice. Before every arm (R2): drop the previous keyspace,
              clear snapshots, truncatehints until A's hints directory holds no .hints file, create a new keyspace, GC.
  mhb1 <rep>  one lifetime with -Dcassandra.MAX_HINT_BUFFERS=1 on A (B3e step 4): set-up as main without the control,
              stop B, baseline, one 1 MiB arm (2 GiB, the same two halves) with each half bounded by WBS_MHB_MAX_S (90 s)
              and three thread dumps of A during the first half; A is stopped (kill -9 if stopdaemon does not return).
  analyze     reads main/arms.json and mhb1-*/arms.json, writes analysis.txt with the cross-arm B3f relations.
  down        stop both nodes of this harness.
A = 127.0.0.2 (JMX 7102, coordinator, measured), B = 127.0.0.3 (JMX 7103); both on this host (environment deviation:
the audit assumed pc57 + pc50). A is sampled every second (JMX: direct pool MemoryUsed/Count, heap used, TotalHints,
TotalHintsInProgress; the .hints files of A's hints directory: bytes, count, largest). Output:
~/stage4-logs/wbs/<run>/cluster/<lifetime>/ (summary.txt with EXPECTED lines, session.log, samples.csv, hints.csv,
arms.json, wbs.trace copy, keys-*.csv, thread dumps, NMT summaries, logs). Exit 1: a set-up check failed; both nodes
are stopped on any exit. A reading that misses a prediction is recorded as EXPECTED ... NO and the run goes on.
Environment: WBS_RUN (default run1), CASSANDRA_HOME (default ~/cassandra-run1), WBS_BYTES (values per arm, default
2 GiB), WBS_SIZES (comma list, default 102400,1048576,8388608), WBS_REPS (default 2), WBS_CTRL_BYTES (default 256 MiB),
WBS_MHB_MAX_S (default 90), WBS_LIMIT_ARMS (default 2). From the internode_max_message_size-inferMessageSize harness's
cluster-run.py (node start/stop, sampler) and the max_hints_size_per_host harness (writer, refusal trace)."""
import json, os, re, statistics, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-run1')
HARNESS = os.path.dirname(os.path.abspath(__file__))
WBS = os.environ.get('WBS', HOME + '/stage4-wbs')
RUN = os.environ.get('WBS_RUN', 'run1')
KIB, MIB, GIB = 1024, 1 << 20, 1 << 30
ARM_BYTES = int(os.environ.get('WBS_BYTES', 2 * GIB))
SIZES = [int(x) for x in os.environ.get('WBS_SIZES', '102400,1048576,8388608').split(',')]
REPS = int(os.environ.get('WBS_REPS', 2))
CTRL_BYTES = int(os.environ.get('WBS_CTRL_BYTES', 256 * MIB))
MHB_MAX_S = float(os.environ.get('WBS_MHB_MAX_S', 90))
LIMIT_ARMS = int(os.environ.get('WBS_LIMIT_ARMS', 2))
NODES = {'A': ('127.0.0.2', 7102), 'B': ('127.0.0.3', 7103)}
WRITE_BUFFER = 256 * KIB
SLAB = 32 * MIB
LIMIT_MIB = 64
CLIENT = HARNESS + '/client.py'
JMXCP = WBS + '/jmx'
BM = C + '/build/lib/jars/byteman-4.0.20.jar'
TRACE = WBS + '/A/wbs.trace'          # current A start's trace (wbs-<n>.trace); set by start_node
STARTS = {'A': 0}
CURRENT = {'mhb': None}
SP = 'org.apache.cassandra.db:type=StorageProxy'
COLS = [('direct_used', 'java.nio:type=BufferPool,name=direct', 'MemoryUsed'),
        ('direct_count', 'java.nio:type=BufferPool,name=direct', 'Count'),
        ('heap_used', 'java.lang:type=Memory', 'HeapMemoryUsage'),
        ('total_hints', 'org.apache.cassandra.metrics:type=Storage,name=TotalHints', 'Count'),
        ('hints_in_progress', 'org.apache.cassandra.metrics:type=Storage,name=TotalHintsInProgress', 'Count')]

args = sys.argv[1:]
if not args or args[0] not in ('main', 'mhb1', 'analyze', 'down') or (args[0] == 'mhb1' and len(args) != 2):
    sys.exit(__doc__)
MODE = args[0]
TAG = f'mhb1-{args[1]}' if MODE == 'mhb1' else MODE
ROOT = f'{HOME}/stage4-logs/wbs/{RUN}/cluster'
LOGS = f'{ROOT}/{TAG}'
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
SUMMARY = open(LOGS + '/summary.txt', 'a' if MODE == 'down' else 'w')
EXPECT = {'yes': 0, 'no': 0}
CHILDREN = []


# ---------------------------------------------------------------- plumbing

def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, file=sys.stderr)
    SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush(); log(s)


def sh(cmd, timeout=600, check=True, env=None, cwd=C, quiet=False):
    log('+ ' + cmd)
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
    except subprocess.TimeoutExpired as e:
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
    """the node's java pid: from its pid file (remembered), else the remembered pid; None once that process is gone.
    stopdaemon deletes the pid file before the JVM exits (shakedown1 of mhb1: a hung JVM outlived it), so the pid is kept."""
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
    # java processes only: on a shared host another session's shell can carry the text "CassandraDaemon" (seen 2026-10-21:
    # an ssh wait loop of another agent), which a plain grep of ps would count
    return sh("ps -eo cmd | grep -E '^[^ ]*java .*org\\.apache\\.cassandra\\.service\\.CassandraDaemon' || true",
              check=False, quiet=True)[1].strip()


def nodetool(node, cmd, timeout=180, check=False, quiet=True):
    return sh(f'bin/nodetool -h 127.0.0.1 -p {NODES[node][1]} {cmd}', timeout=timeout, check=check, quiet=quiet)


def stop_node(node, wait_s=120):
    pid0 = pid_of(node)
    if pid0 is None:
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
                 env=dict(os.environ, CASSANDRA_HOME=C))
    js = [l for l in out.splitlines() if l.startswith('{')]
    if not js:
        return None
    return json.loads(js[-1])


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


def start_node(node, mhb=None):
    if pid_of(node) is not None:
        fail(f'{node} is already running')
    PIDS.pop(node, None)
    _, y = sh(f'{HARNESS}/make-node-yaml.sh {node}', env=dict(os.environ, CASSANDRA_HOME=C, WBS=WBS))
    note(y.strip().splitlines()[-1][:1200])
    N = f'{WBS}/{node}'
    env = dict(os.environ, CASSANDRA_CONF=N + '/conf', CASSANDRA_LOG_DIR=N + '/logs', MAX_HEAP_SIZE='2G', HEAP_NEWSIZE='400M')
    env.pop('JVM_EXTRA_OPTS', None)
    extra = ''
    global TRACE
    if node == 'A':
        STARTS['A'] += 1
        TRACE = f'{WBS}/A/wbs-{STARTS["A"]}.trace'   # Byteman traceOpen truncates: one file per start
        extra = f'-javaagent:{BM}=script:{HARNESS}/wbs.btm -Dstage4.trace={TRACE} -Dorg.jboss.byteman.verbose=false'
        if mhb is not None:
            extra += f' -Dcassandra.MAX_HINT_BUFFERS={mhb}'
    note(f'start {node}: MAX_HEAP_SIZE=2G JVM_EXTRA_OPTS="{extra}"')
    # JVM_EXTRA_OPTS scoped to the bin/cassandra command only (HANDOFF lesson), never exported
    sh(f'JVM_EXTRA_OPTS="{extra}" bin/cassandra -p {N}/cassandra.pid > {N}/stdout.txt 2>&1', env=env)
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


def wait_b_down(timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if status_of('A').get(NODES['B'][0]) == 'DN':
            note(f'A sees B DN after {time.time() - t0:.0f} s')
            return
        time.sleep(2)
    fail('A does not see B down')


def hints_files():
    d = f'{WBS}/A/hints'
    out = []
    try:
        for e in os.scandir(d):
            if e.name.endswith('.hints'):
                try:
                    out.append((e.name, e.stat().st_size))
                except OSError:
                    pass
    except OSError:
        pass
    return out


class Sampler:
    """A every second: one Jmx poll JVM for the JMX columns, a thread for A's .hints files"""

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
        self.hf.write('ms,hints_bytes,hints_files,largest_file\n'); self.hf.flush()
        self.alive = True
        self.t = threading.Thread(target=self._hints, daemon=True)
        self.t.start()

    def _hints(self):
        nxt = time.time()
        while self.alive:
            fs = hints_files()
            self.hf.write(f'{int(time.time() * 1000)},{sum(s for _, s in fs)},{len(fs)},{max([s for _, s in fs] or [0])}\n')
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


def read_samples():
    """every sampler file of this lifetime (one per A start), merged by time"""
    import glob
    rows, hrows = [], []
    for fn in glob.glob(f'{LOGS}/samples-jmx-*.csv'):
        for l in open(fn).read().splitlines()[1:]:
            parts = l.split(',')
            if len(parts) == len(COLS) + 1 and parts[0].isdigit():
                rows.append([int(parts[0])] + [num(x) for x in parts[1:]])
    for fn in glob.glob(f'{LOGS}/hints-*.csv'):
        for l in open(fn).read().splitlines()[1:]:
            p = l.split(',')
            if len(p) == 4 and p[0].isdigit():
                hrows.append([int(p[0]), int(p[1]), int(p[2]), int(p[3])])
    return sorted(rows), sorted(hrows)


def ci(name):
    return 1 + [c for c, _, _ in COLS].index(name)


def trace_lines(path=None):
    try:
        return open(path or TRACE, errors='replace').read().splitlines()
    except OSError:
        return []


def tms(l):
    m = re.search(r' ms=(\d+)', l)
    return int(m.group(1)) if m else None


def trace_stats(t0, t1):
    created, waiting, app, wr, refuse, flush = [], 0, [], [], [], 0
    for l in trace_lines():
        ms = tms(l)
        if l.startswith('created='):
            created.append((ms, int(l.split()[0].split('=')[1]), int(l.split()[1].split('=')[1]), int(l.split()[2].split('=')[1])))
        if ms is None or ms < t0 or ms > t1:
            continue
        if l.startswith('waiting'):
            waiting += 1
        elif l.startswith('app '):
            d = dict(kv.split('=', 1) for kv in l.split()[1:])
            app.append((int(d['sz']), int(d['rem']), int(d['cap']), d['direct']))
        elif l.startswith('wr '):
            d = dict(kv.split('=', 1) for kv in l.split()[1:])
            wr.append((int(d['sz']), d['buf']))
        elif l.startswith('refuse'):
            d = dict(kv.split('=', 1) for kv in l.split()[1:])
            refuse.append((ms, int(d['checked']), int(d['limit'])))
        elif l.startswith('flush'):
            flush += 1
    return {'created_total_by_t1': len([c for c in created if c[0] <= t1]),
            'created_in_window': len([c for c in created if t0 <= c[0] <= t1]),
            'created_lines': [c for c in created if c[0] <= t1],
            'waiting': waiting, 'app': len(app), 'app_over_cap': sum(1 for a in app if a[0] > a[2]),
            'app_max_sz': max([a[0] for a in app] or [0]), 'app_caps': sorted({a[2] for a in app}),
            'app_direct': sorted({a[3] for a in app}),
            'app_bytes': sum(a[0] for a in app),
            'wr': len(wr), 'wr_direct_hint': sum(1 for w in wr if w[1] == 'false'),
            'wr_buf_max': max([w[0] for w in wr if w[1] == 'true'] or [0]),
            'wr_hint_max': max([w[0] for w in wr if w[1] == 'false'] or [0]),
            'refuse': len(refuse), 'refuse_first': refuse[0] if refuse else None,
            'refuse_min_checked': min([r[1] for r in refuse] or [0]), 'flush': flush}


def nmt(pid, name):
    _, out = sh(f'jcmd {pid} VM.native_memory summary', check=False, quiet=True)
    open(f'{LOGS}/nmt-{name}.txt', 'w').write(out)
    m = re.search(r'-\s+Other \(reserved=\d+KB, committed=(\d+)KB\)', out)
    return int(m.group(1)) * 1024 if m else None


def hinted_created():
    _, out = sh(f"java -cp {JMXCP} Jmx 7102 query 'org.apache.cassandra.metrics:type=HintsService,name=Hints_created*' Count",
                check=False, quiet=True)
    tot = 0
    for l in out.splitlines():
        p = l.rsplit('|', 2)
        if len(p) == 3 and num(p[2]) is not None:
            tot += int(num(p[2]))
    return tot


# ---------------------------------------------------------------- set-up and arms

def setup(mhb=None, control=True):
    note(f'cluster-run {TAG} {time.strftime("%F %T %Z")} host {os.uname().nodename.split(".")[0]} clone {C} '
         f'{sh("git describe --tags; git rev-parse --short HEAD", quiet=True)[1].split()} run {RUN}')
    note('harness md5: ' + sh('md5sum cluster-run.py client.py make-node-yaml.sh Jmx.java wbs.btm', quiet=True,
                              cwd=HARNESS)[1].replace('\n', ' ')[:700])
    note(f'settings: ARM_BYTES={ARM_BYTES} SIZES={SIZES} REPS={REPS} CTRL_BYTES={CTRL_BYTES} MHB={mhb or "default (3)"} '
         f'MHB_MAX_S={MHB_MAX_S} LIMIT_ARMS={LIMIT_ARMS}')
    if any_daemon():
        fail('a CassandraDaemon is already running on this host: ' + any_daemon()[:200])
    _, df = sh(f'df -k {HOME}', quiet=True)
    free_gb = int(df.splitlines()[-1].split()[3]) / 1048576
    note(f'free on {HOME}: {free_gb:.1f} GiB')
    if free_gb < 20:
        fail('less than 20 GiB free (B3a asks >= 20 GiB, B4 >= 10 GiB)')
    os.makedirs(JMXCP, exist_ok=True)
    sh(f'javac -d {JMXCP} {HARNESS}/Jmx.java')
    sh(f'rm -rf {WBS}/A {WBS}/B')
    start_node('A', mhb)
    time.sleep(15)
    start_node('B')
    wait_up(['A', 'B'])
    sh(f'cp {WBS}/A/conf/cassandra.yaml {LOGS}/A-cassandra.yaml; cp {WBS}/B/conf/cassandra.yaml {LOGS}/B-cassandra.yaml')
    _, sho = nodetool('A', 'statushandoff')
    note('A statushandoff: ' + sho.strip().replace('\n', ' '))
    if 'running' not in sho.lower():
        fail('hinted handoff not running on A')
    created0 = [l for l in trace_lines() if l.startswith('created=')]
    note(f'A trace at start: {len(created0)} created line(s): {created0[:3]}')
    if not os.path.exists(TRACE):
        fail('no Byteman trace on A (agent not loaded?)')
    p = client('probe', NODES['A'][0])
    if not p or not p.get('ok'):
        fail('probe')
    note(f'probe: {p}')
    _, cmdl = sh(f'cat /proc/{pid_of("A")}/cmdline | tr "\\0" " "', quiet=True)
    for flag in ('-Xmx2G', '-XX:MaxDirectMemorySize=1g', '-XX:NativeMemoryTracking=summary', 'byteman', 'MAX_HINT_BUFFERS'):
        note(f'A command line has {flag}: {flag in cmdl}')
    CURRENT['mhb'] = mhb
    sm = Sampler('setup')
    arms = []
    if control:
        arms.append(control_arm())
    note('stopping B (drain, stopdaemon) for the hint arms')
    nodetool('B', 'drain', timeout=300, quiet=False)
    stop_node('B')
    wait_b_down()
    return sm, arms


def control_arm():
    """B3h baseline: B up, 1 MiB values, no hint expected"""
    client('schema', NODES['A'][0], 'ksctl')
    th0 = num(jmx('A', (COLS[3][1], 'Count')).get((COLS[3][1], 'Count'))) or 0
    t0 = int(time.time() * 1000)
    w = client('write', NODES['A'][0], 'ksctl', MIB, CTRL_BYTES, 8, 0, 600, f'{LOGS}/keys-control.csv')
    time.sleep(5)
    t1 = int(time.time() * 1000)
    th1 = num(jmx('A', (COLS[3][1], 'Count')).get((COLS[3][1], 'Count'))) or 0
    hb = sum(s for _, s in hints_files())
    note(f'control (B up): writes {w}; TotalHints +{th1 - th0:.0f}; A hints bytes {hb}')
    expect('control: B up, no hint is written (A .hints bytes <= 1 MiB, TotalHints +0)', hb <= MIB and th1 - th0 == 0)
    expect('control: every write succeeded', bool(w) and w['failed'] == 0 and w['succeeded'] == w['written'])
    client('drop', NODES['A'][0], 'ksctl')
    return {'name': 'control', 't0': t0, 't1': t1, 'write': [w], 'total_hints_delta': th1 - th0, 'hints_bytes_end': hb}


def reset(ks_prev, ks_new, sm, tag):
    """R2 between arms, corrected after run-1 attempt 1 (results §3 D2): truncatehints deletes only closed files
    (HintsStore.deleteAllHints, HintsStore.java:167-181), never the file the writer has open, so A is restarted (a clean
    stop closes the writer; a restarted A catalogues every file as closed) before truncatehints; B stays down.
    Returns the new sampler (the JMX poll connection ends with the JVM)."""
    if ks_prev:
        client('drop', NODES['A'][0], ks_prev)
    nodetool('A', 'clearsnapshot --all', quiet=False)
    sm.close()
    stop_node('A')
    start_node('A', CURRENT['mhb'])
    wait_up(['A'])
    wait_b_down()
    sm = Sampler(tag)
    for i in range(10):
        nodetool('A', 'truncatehints', quiet=False)
        time.sleep(3)
        if not hints_files():
            break
    _, ph = nodetool('A', 'listpendinghints')
    note(f'reset ({tag}): dropped {ks_prev}; A restarted (trace {os.path.basename(TRACE)}); .hints files after truncatehints: '
         f'{hints_files()}; listpendinghints: ' + ph.strip().replace('\n', ' | ')[:300])
    if hints_files():
        fail('hints files remain after a restart and truncatehints (B3e step 3: du must return to baseline)')
    r = client('schema', NODES['A'][0], ks_new)
    if not r:
        fail(f'schema {ks_new}')
    return sm


def thread_dumps(n, gap, delay, label):
    def run():
        time.sleep(delay)
        for k in range(n):
            pid = pid_of('A')
            if pid is None:
                return
            _, out = sh(f'jcmd {pid} Thread.print', check=False, quiet=True, timeout=120)
            open(f'{LOGS}/threads-{label}-{k + 1}.txt', 'w').write(out)
            time.sleep(gap)
    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t


def arm(name, ks, size, base, max_s=1800, dumps=False):
    pidA = pid_of('A')
    th0 = num(jmx('A', (COLS[3][1], 'Count')).get((COLS[3][1], 'Count'))) or 0
    hc0 = hinted_created()
    nmt0 = nmt(pidA, name + '-before')
    t0 = int(time.time() * 1000)
    td = thread_dumps(3, 5, 30, name) if dumps else None
    half = ARM_BYTES // 2
    w1 = client('write', NODES['A'][0], ks, size, half, 1, 0, max_s, f'{LOGS}/keys-{name}.csv')
    w8 = client('write', NODES['A'][0], ks, size, half, 8, 10_000_000, max_s, f'{LOGS}/keys-{name}.csv')
    t_w = int(time.time() * 1000)
    time.sleep(10)                                   # settle: ten hints_flush_period
    t1 = int(time.time() * 1000)
    if td:
        td.join(timeout=120)
    th1 = num(jmx('A', (COLS[3][1], 'Count')).get((COLS[3][1], 'Count'))) or 0
    hc1 = hinted_created()
    nmt1 = nmt(pidA, name + '-after')
    fs = hints_files()
    _, ph = nodetool('A', 'listpendinghints')
    open(f'{LOGS}/listpendinghints-{name}.txt', 'w').write(ph)
    ws = [w for w in (w1, w8) if w]
    written = sum(w['written'] for w in ws)
    ok = sum(w['succeeded'] for w in ws)
    st = trace_stats(t0, t1)
    a = {'trace_file': os.path.basename(TRACE), 'name': name, 'ks': ks, 'size': size, 't0': t0, 't_w': t_w, 't1': t1, 'write': [w1, w8], 'written': written,
         'succeeded': ok, 'total_hints_delta': th1 - th0, 'hints_created_delta': hc1 - hc0,
         'hints_bytes_end': sum(s for _, s in fs), 'hints_files_end': len(fs), 'hints_file_sizes': sorted(s for _, s in fs),
         'nmt_other_before': nmt0, 'nmt_other_after': nmt1, 'trace': {k: v for k, v in st.items() if k != 'created_lines'},
         'created_lines': st['created_lines'], 'base': base}
    note(f'arm {name}: size {size}; writes c1 {w1}; c8 {w8}')
    note(f'arm {name}: written {written}, succeeded {ok}, TotalHints +{th1 - th0:.0f}, Hints_created +{hc1 - hc0}; '
         f'.hints files {len(fs)} bytes {a["hints_bytes_end"]} largest {max([s for _, s in fs] or [0])}; trace {a["trace"]}')
    return a


def peaks(a, rows, hrows):
    wr = [r for r in rows if a['t0'] <= r[0] <= a['t1']]
    hr = [r for r in hrows if a['t0'] <= r[0] <= a['t1']]
    b = a['base']
    a['samples'] = len(wr)
    a['direct_peak'] = max([r[ci('direct_used')] for r in wr if r[ci('direct_used')] is not None] or [0])
    a['direct_peak_delta'] = a['direct_peak'] - b['direct_used']
    a['direct_count_peak_delta'] = max([r[ci('direct_count')] for r in wr if r[ci('direct_count')] is not None] or [0]) - b['direct_count']
    a['heap_peak'] = max([r[ci('heap_used')] for r in wr if r[ci('heap_used')] is not None] or [0])
    a['hints_bytes_peak'] = max([r[1] for r in hr] or [0])
    a['hints_files_peak'] = max([r[2] for r in hr] or [0])
    a['largest_file_peak'] = max([r[3] for r in hr] or [0])
    # growth in the last 40 % of the write window (the plateau check of the limit arms)
    tcut = a['t0'] + 0.6 * (a['t_w'] - a['t0'])
    late = [r[1] for r in hr if tcut <= r[0] <= a['t_w']]
    a['hints_growth_late'] = (max(late) - min(late)) if late else None
    a['slabs_total'] = a['trace']['created_total_by_t1']
    a['attributable_direct'] = a['slabs_total'] * SLAB + WRITE_BUFFER
    note(f'arm {a["name"]}: {len(wr)} samples; direct peak {a["direct_peak"] / MIB:.2f} MiB '
         f'({a["direct_peak_delta"] / MIB:+.2f} MiB over the lifetime baseline, Count {a["direct_count_peak_delta"]:+.0f}); '
         f'heap peak {a["heap_peak"] / MIB:.0f} MiB; hints bytes peak {a["hints_bytes_peak"] / MIB:.1f} MiB, files peak '
         f'{a["hints_files_peak"]}, largest {a["largest_file_peak"] / MIB:.2f} MiB; slabs created by the end {a["slabs_total"]} '
         f'(attributable {a["attributable_direct"] / MIB:.2f} MiB); late growth '
         f'{(a["hints_growth_late"] or 0) / MIB:.2f} MiB')


def judge_hint_arm(a, mhb):
    n = a['name']
    s = a['size']
    vals = a['written'] * s
    if mhb is None:
        expect(f'{n}: attributable hint direct memory (slabs x 32 MiB + 256 KiB) {a["attributable_direct"] / MIB:.2f} MiB is within '
               f'~32-96 MiB + 256 KiB and >= 100 x 256 KiB (B3f)',
               SLAB + WRITE_BUFFER <= a['attributable_direct'] <= 3 * SLAB + WRITE_BUFFER and a['attributable_direct'] >= 100 * WRITE_BUFFER)
        ratio = a['hints_bytes_end'] / vals if vals else 0
        a['du_ratio'] = ratio
        expect(f'{n}: hints on disk {a["hints_bytes_end"]} B = {ratio:.4f} x the {vals} B of values written (~2 GiB in full: 0.95-1.10)',
               0.95 <= ratio <= 1.10)
        expect(f'{n}: files of ~128 MiB: {a["hints_files_end"]} files, largest {max(a["hints_file_sizes"] or [0])} B '
               f'(largest >= 128 MiB, count 14-18)',
               max(a['hints_file_sizes'] or [0]) >= 128 * MIB and 14 <= a['hints_files_end'] <= 18)
        expect(f'{n}: every write hinted and every hint stored: Hints_created +{a["hints_created_delta"]} = written {a["written"]} '
               f'= entries appended {a["trace"]["app"]}', a['hints_created_delta'] == a['written'] == a['trace']['app'])
        if s > WRITE_BUFFER:
            expect(f'{n}: every entry larger than the 256 KiB buffer bypasses it: app sz>cap {a["trace"]["app_over_cap"]} and direct '
                   f'channel writes {a["trace"]["wr_direct_hint"]} = written {a["written"]}',
                   a['trace']['app_over_cap'] == a['written'] == a['trace']['wr_direct_hint'])
        else:
            expect(f'{n}: entries of {s} B fit the buffer: app sz>cap {a["trace"]["app_over_cap"]} = 0, direct channel writes '
                   f'{a["trace"]["wr_direct_hint"]} = 0', a['trace']['app_over_cap'] == 0 and a['trace']['wr_direct_hint'] == 0)
        expect(f'{n}: claim-wrong guard — the direct peak is not within ~1 MiB of baseline while the slabs stay at 1 '
               f'(delta {a["direct_peak_delta"] / MIB:+.2f} MiB, slabs {a["slabs_total"]})',
               not (abs(a['direct_peak_delta']) <= MIB and a['slabs_total'] <= 1))
    else:
        expect(f'{n}: MAX_HINT_BUFFERS=1: attributable {a["attributable_direct"] / MIB:.2f} MiB <= ~32 MiB + 256 KiB (one slab)',
               a['attributable_direct'] <= SLAB + WRITE_BUFFER)
        note(f'NOTE {n}: source-derived pre-run note (results §3): with one buffer the writer that fills the slab waits in take() '
             f'for a recycle that cannot start; waiting lines {a["trace"]["waiting"]}, written {a["written"]}, succeeded '
             f'{a["succeeded"]}, Hints_created +{a["hints_created_delta"]}, hints bytes {a["hints_bytes_end"]}')


def judge_limit_arm(a):
    n = a['name']
    lim = LIMIT_MIB * MIB
    expect(f'{n}: per-host limit {LIMIT_MIB} MiB: disk stops near it: final {a["hints_bytes_end"] / MIB:.2f} MiB in '
           f'[64, 64 + 128 + 32] MiB', lim <= a['hints_bytes_end'] <= lim + 128 * MIB + SLAB)
    expect(f'{n}: growth stopped: {(a["hints_growth_late"] or 0) / MIB:.2f} MiB in the last 40 % of the write window (< 32 MiB) '
           f'while the limit-0 arms grow to ~2 GiB', a['hints_growth_late'] is not None and a['hints_growth_late'] < SLAB)
    rf = a['trace']['refuse_first']
    expect(f'{n}: refusals at the check: {a["trace"]["refuse"]} refuse lines, first {rf}, every operand above the limit '
           f'(min checked {a["trace"]["refuse_min_checked"]})',
           a['trace']['refuse'] > 0 and a['trace']['refuse_min_checked'] > lim)
    expect(f'{n}: writes still succeed at CL ONE: succeeded {a["succeeded"]} = written {a["written"]}',
           a['succeeded'] == a['written'] and a['written'] > 0)


def baseline(name='baseline'):
    sh(f'jcmd {pid_of("A")} GC.run', check=False, quiet=True)
    time.sleep(3)
    t0 = int(time.time() * 1000)
    time.sleep(10)
    t1 = int(time.time() * 1000)
    rows, _ = read_samples()
    w = [r for r in rows if t0 <= r[0] <= t1]
    b = {c: statistics.median([r[ci(c)] for r in w if r[ci(c)] is not None] or [0]) for c, _, _ in COLS}
    b['t0'], b['t1'] = t0, t1
    st = trace_stats(0, t1)
    b['slabs_at_baseline'] = st['created_total_by_t1']
    note(f'{name} (median of 10 s after GC, B down, A restarted, before the arm\'s first hint): direct {b["direct_used"] / MIB:.3f} MiB, Count '
         f'{b["direct_count"]:.0f}, heap {b["heap_used"] / MIB:.0f} MiB; slabs already created {b["slabs_at_baseline"]} '
         f'(the periodic flush creates the first at start-up)')
    return b


def finish(sm, arms):
    sm.close()
    rows, hrows = read_samples()
    for a in arms:
        if 'base' in a:
            peaks(a, rows, hrows)
    sh(f'cp {WBS}/A/wbs-*.trace {LOGS}/', check=False)
    for n in NODES:
        sh(f'cp {WBS}/{n}/logs/system.log {LOGS}/{n}-system.log; cp {WBS}/{n}/logs/gc.log* {LOGS}/ 2>/dev/null; '
           f'for f in {LOGS}/gc.log*; do [ -e "$f" ] && mv "$f" "{LOGS}/{n}-$(basename $f)"; done', check=False)
    for n in NODES:
        _, e = sh(f"grep -c '^ERROR' {WBS}/{n}/logs/system.log", check=False, quiet=True)
        note(f'{n} system.log ERROR lines: {e.strip()}')
    return rows, hrows


def save(arms):
    with open(f'{LOGS}/arms.json', 'w') as f:
        json.dump(arms, f, indent=1, default=str)


def main_lifetime():
    sm, arms = setup()
    prev = None
    plan = [(f's{s // KIB}k-r{r}', s, False) for s in SIZES for r in range(1, REPS + 1)]
    plan += [(f'limit64-r{r}', MIB, True) for r in range(1, LIMIT_ARMS + 1)]
    for name, s, limit in plan:
        ks = 'ks' + re.sub(r'[^a-z0-9]', '', name)
        sm = reset(prev, ks, sm, name)
        if limit:      # the live setter does not survive the restart: set it after each one, read back
            r = sh(f"java -cp {JMXCP} Jmx 7102 setint '{SP}' MaxHintsSizePerHostInMiB {LIMIT_MIB}", check=False)[1].strip()
            note(f'per-host limit set live: {r}')
            if not r.endswith(f'|{LIMIT_MIB}'):
                fail('limit read-back')
        base = baseline(f'baseline {name}')
        a = arm(name, ks, s, base)
        a['limit'] = limit
        arms.append(a); prev = ks
        save(arms)
    finish(sm, arms)
    for a in arms:
        if a['name'] == 'control':
            continue
        if a.get('limit'):
            judge_limit_arm(a)
        else:
            judge_hint_arm(a, None)
    save(arms)
    stop_all()


def mhb1_lifetime():
    sm, arms = setup(mhb=1, control=False)
    sm = reset(None, 'ksmhb1', sm, 'mhb1-s1024k')
    base = baseline('baseline mhb1-s1024k')
    a = arm('mhb1-s1024k', 'ksmhb1', MIB, base, max_s=MHB_MAX_S, dumps=True)
    arms.append(a)
    save(arms)
    finish(sm, arms)
    for k in (1, 2, 3):
        f = f'{LOGS}/threads-{a["name"]}-{k}.txt'
        if os.path.exists(f):
            txt = open(f).read()
            parked = len(re.findall(r'at org\.apache\.cassandra\.hints\.HintsBufferPool\.switchCurrentBuffer\(HintsBufferPool\.java:118\)', txt))
            blocks = txt.split('\n\n')
            mut = sum(1 for b in blocks if b.lstrip().startswith('"MutationStage') and 'HintsBufferPool' in b)
            note(f'thread dump {k}: frames at HintsBufferPool.switchCurrentBuffer(:118): {parked}; '
                 f'MutationStage threads with a HintsBufferPool frame: {mut}')
    judge_hint_arm(a, 1)
    save(arms)
    stop_all()


def analyze():
    out = open(f'{ROOT}/analysis.txt', 'w')

    def say(s):
        print(s); out.write(s + '\n')
    try:
        main = json.load(open(f'{ROOT}/main/arms.json'))
    except OSError:
        sys.exit('no main/arms.json')
    mhb = []
    for d in sorted(os.listdir(ROOT)):
        if d.startswith('mhb1-') and os.path.exists(f'{ROOT}/{d}/arms.json'):
            mhb += json.load(open(f'{ROOT}/{d}/arms.json'))
    hint = [a for a in main if a['name'] != 'control' and not a.get('limit')]
    lim = [a for a in main if a.get('limit')]
    ok = {'yes': 0, 'no': 0}

    def ex(desc, cond):
        ok['yes' if cond else 'no'] += 1
        say(f'EXPECTED: {desc} — {"yes" if cond else "NO"}')
    say('arm, size, written, succeeded, hints_bytes_end, du_ratio, files, slabs_total, attributable_MiB, direct_peak_delta_MiB, '
        'heap_peak_MiB, waiting, refuse')
    for a in main + mhb:
        if 'base' not in a:
            continue
        say(f"{a['name']}, {a['size']}, {a['written']}, {a['succeeded']}, {a['hints_bytes_end']}, "
            f"{a.get('du_ratio', 0):.4f}, {a['hints_files_end']}, {a['slabs_total']}, {a['attributable_direct'] / MIB:.2f}, "
            f"{a['direct_peak_delta'] / MIB:.2f}, {a['heap_peak'] / MIB:.0f}, {a['trace']['waiting']}, {a['trace']['refuse']}")
    rat = [a['du_ratio'] for a in hint if a.get('du_ratio')]
    if rat:
        ex(f'X1 value size does not change the disk total: du ratios {[round(r, 4) for r in rat]} within 5 % of each other',
           max(rat) / min(rat) <= 1.05)
    first_of_size = {}
    for a in hint:
        first_of_size.setdefault(a['size'], a)
    say('slabs created during each size\'s first arm: ' + ', '.join(f"{s}: {a['trace']['created_in_window']}" for s, a in first_of_size.items()))
    if hint and lim:
        lim_end = max(a['hints_bytes_end'] for a in lim)
        ex(f'X2 positive control (disk): the limit arms end at {lim_end / MIB:.1f} MiB while the same 1 MiB workload with limit 0 '
           f'ends at {min(a["hints_bytes_end"] for a in hint if a["size"] == MIB) / MIB:.1f} MiB',
           lim_end < min(a['hints_bytes_end'] for a in hint if a['size'] == MIB) / 4)
    if hint and mhb:
        dflt = max(a['direct_peak_delta'] for a in hint)
        m1 = max(a['direct_peak_delta'] for a in mhb)
        ex(f'X3 memory-side control (R1): MAX_HINT_BUFFERS=1 peak direct delta {m1 / MIB:.2f} MiB is lower than the default '
           f'run\'s {dflt / MIB:.2f} MiB', m1 < dflt)
        ex(f'X4 slabs: default lifetime {max(a["slabs_total"] for a in hint)} vs MAX_HINT_BUFFERS=1 {max(a["slabs_total"] for a in mhb)} '
           f'(B3f: the slab count governs, not the 256 KiB buffer)', max(a['slabs_total'] for a in mhb) < max(a['slabs_total'] for a in hint))
    say(f'analysis EXPECTED yes={ok["yes"]} no={ok["no"]}')


if __name__ == '__main__':
    try:
        if MODE == 'down':
            stop_all()
        elif MODE == 'analyze':
            analyze()
        elif MODE == 'main':
            main_lifetime()
        else:
            mhb1_lifetime()
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
        if MODE in ('main', 'mhb1'):
            note(f'EXPECTED totals: yes={EXPECT["yes"]} no={EXPECT["no"]}')
            if MODE != 'down':
                note('daemons left: ' + (any_daemon() or 'none'))
