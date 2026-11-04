#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of internode_max_message_size-inferMessageSize-size--autonomous (amended 2026-10-20).
usage: cluster-run.py <label> <rep> | analyze | down
  <label> <rep>  one lifetime of both nodes (B3e steps 2-7): wipe ~/stage4-imm, write both yaml files with the label's
                 internode_max_message_size, start A (the seed) then B, wait for UN on both, create ks (RF 2) and ks.t, read
                 the limit back from system_views.settings on both nodes, GC B and take the baseline, then a 10 s control
                 (no writes) and, for S = 512 KiB, 4 MiB, 12 MiB, 20 INSERTs of S bytes at CL ALL through A (5 s settle after
                 each size). B is sampled every 200 ms (JMX: direct pool, heap, networking pool Size/UsedSize/OverflowSize,
                 inbound counters from A; /proc VmRSS); the 1 s readings are the samples at whole seconds. Then counters,
                 tpstats, flush, tablestats, count(*) at ONE through each node, and the log lines. Both nodes are stopped.
                 Labels (A / B): R0 default/default (amendment R1), R1 16MiB/16MiB, R2 16MiB/1MiB, R3 1MiB/1MiB.
                 <rep> is 1 or 2 (B3h: each run twice).
  analyze        reads every <label>-<rep>/phases.json of the run and writes analysis.txt: the B3f relations across runs.
  down           stop both nodes of this harness.
Two nodes on this host: A = 127.0.0.1 (JMX 7199, seed, the coordinator), B = 127.0.0.2 (JMX 7299, measured).
Output: ~/stage4-logs/imm/<run>/cluster/<label>-<rep>/ (summary.txt with EXPECTED lines, session.log, samples.csv,
phases.json, keys.csv, logs). Exit 1: a set-up check failed (a node not UN, the read-back, a client that could not
connect); on such a failure both nodes are stopped. A reading that misses a prediction is recorded as EXPECTED ... NO.
Environment: IMM_RUN (run folder name, default run1), CASSANDRA_HOME (default ~/cassandra-run5), IMM_N (writes per size,
default 20; a shakedown may lower it). From the internode_application_receive_queue_capacity harness's cluster-run.py."""
import calendar, json, os, re, statistics, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-run5')
HARNESS = os.path.dirname(os.path.abspath(__file__))
IMM = os.environ.get('IMM', HOME + '/stage4-imm')
RUN = os.environ.get('IMM_RUN', 'run1')
NW = int(os.environ.get('IMM_N', 20))
KIB, MIB = 1024, 1 << 20
SIZES = [512 * KIB, 4 * MIB, 12 * MIB]
NODES = {'A': ('127.0.0.1', 7199), 'B': ('127.0.0.2', 7299)}
LABELS = {'R0': (None, None), 'R1': ('16MiB', '16MiB'), 'R2': ('16MiB', '1MiB'), 'R3': ('1MiB', '1MiB')}
LIMIT_BYTES = {None: 128 * MIB, '16MiB': 16 * MIB, '1MiB': MIB}
CLIENT = HARNESS + '/client.py'
JMXCP = IMM + '/jmx'
POOL = 'org.apache.cassandra.metrics:type=BufferPool,scope=networking,name='
INB = 'org.apache.cassandra.metrics:type=InboundConnection,scope=127.0.0.1_7000,name='
TABLE_W = 'org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=t,name=WriteLatency'
DROP = 'org.apache.cassandra.metrics:type=DroppedMessage,scope=MUTATION_REQ,name=Dropped'
# sampled on B; (column, bean, attribute)
COLS = [('direct_used', 'java.nio:type=BufferPool,name=direct', 'MemoryUsed'),
        ('direct_count', 'java.nio:type=BufferPool,name=direct', 'Count'),
        ('heap_used', 'java.lang:type=Memory', 'HeapMemoryUsage'),
        ('pool_size', POOL + 'Size', 'Value'), ('pool_used', POOL + 'UsedSize', 'Value'),
        ('pool_overflow', POOL + 'OverflowSize', 'Value'),
        ('in_received_bytes', INB + 'ReceivedBytes', 'Value'), ('in_processed_bytes', INB + 'ProcessedBytes', 'Value'),
        ('in_error_count', INB + 'ErrorCount', 'Value'), ('in_error_bytes', INB + 'ErrorBytes', 'Value')]
MEM_COLS = ['direct_used', 'pool_size', 'pool_used', 'pool_overflow', 'heap_used', 'rss']
EXCEEDS = re.compile(r'Message of size (\d+) bytes exceeds allowed maximum of (\d+) bytes')

args = sys.argv[1:]
if not args or (args[0] in LABELS and len(args) != 2) or (args[0] not in LABELS and args[0] not in ('analyze', 'down')):
    sys.exit(__doc__)
label = args[0]
tag = f'{label}-{args[1]}' if label in LABELS else label
ROOT = f'{HOME}/stage4-logs/imm/{RUN}/cluster'
LOGS = f'{ROOT}/{tag}'
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
SUMMARY = open(LOGS + '/summary.txt', 'a' if label == 'down' else 'w')
EXPECT = {'yes': 0, 'no': 0}


# ---------------------------------------------------------------- plumbing

def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, file=sys.stderr)
    SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush(); log(s)


def sh(cmd, timeout=600, check=True, env=None, cwd=C, quiet=False):
    log('+ ' + cmd)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
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


def pid_of(node):
    f = f'{IMM}/{node}/cassandra.pid'
    try:
        pid = int(open(f).read().strip())
        return pid if 'CassandraDaemon' in open(f'/proc/{pid}/cmdline').read() else None
    except (ValueError, OSError):
        return None


def any_daemon():
    return sh("ps -eo cmd | grep '[C]assandraDaemon' || true", check=False, quiet=True)[1].strip()


def stop_node(node):
    if pid_of(node) is None:
        return
    sh(f'bin/nodetool -p {NODES[node][1]} stopdaemon', check=False, timeout=180)
    for _ in range(120):
        if pid_of(node) is None:
            return
        time.sleep(1)
    pid = pid_of(node)
    if pid is not None:
        log(f'{node} did not stop; kill -9 {pid}')
        subprocess.run(['kill', '-9', str(pid)])
        time.sleep(2)


def stop_all():
    for n in ('B', 'A'):
        stop_node(n)
    left = any_daemon()
    if left:
        log('WARNING: a CassandraDaemon is still running: ' + left[:300])
    return not left


CHILDREN = []


def fail(msg):
    note('FAIL: ' + msg)
    for p in CHILDREN:
        if p.poll() is None:
            p.kill()
    stop_all()
    sys.exit(1)


def client(*a, timeout=900):
    rc, out = sh(f'python3 {CLIENT} ' + ' '.join(str(x) for x in a), timeout=timeout, check=False,
                 env=dict(os.environ, CASSANDRA_HOME=C))
    js = [l for l in out.splitlines() if l.startswith('{')]
    if rc != 0 or not js:
        return None
    return json.loads(js[-1])


def jmx(node, *pairs):
    """{(bean, attr): value} from one JVM call"""
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


def start_node(node, limit):
    if pid_of(node) is not None:
        fail(f'{node} is already running')
    extra = [] if limit is None else [f'internode_max_message_size={limit}']
    _, y = sh(f'{HARNESS}/make-node-yaml.sh {node} ' + ' '.join(f"'{a}'" for a in extra),
              env=dict(os.environ, CASSANDRA_HOME=C, IMM=IMM))
    note(y.strip().splitlines()[-1][:900])
    N = f'{IMM}/{node}'
    env = dict(os.environ, CASSANDRA_CONF=N + '/conf', CASSANDRA_LOG_DIR=N + '/logs', MAX_HEAP_SIZE='1G')
    env.pop('HEAP_NEWSIZE', None); env.pop('JVM_EXTRA_OPTS', None)
    sh(f'bin/cassandra -p {N}/cassandra.pid > {N}/stdout.txt 2>&1', env=env)
    for _ in range(20):
        time.sleep(1)
        if pid_of(node) is not None:
            return
    fail(f'{node} did not start; see {N}/stdout.txt')


def wait_up(timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        ok = True
        for via in NODES:
            if pid_of(via) is None:
                fail(f'{via} died during start')
            _, st = sh(f'bin/nodetool -p {NODES[via][1]} status', check=False, quiet=True)
            _, sb = sh(f'bin/nodetool -p {NODES[via][1]} statusbinary', check=False, quiet=True)
            up = set(re.findall(r'^UN\s+(\S+)\s', st, re.M))
            ok = ok and up >= {a for a, _ in NODES.values()} and re.search(r'^running\s*$', sb, re.M) is not None
        if ok:
            log(f'both nodes UN and serving after {time.time() - t0:.0f} s')
            return
        time.sleep(3)
    fail('nodes not UN within the timeout')


def rss_kb(pid):
    try:
        for l in open(f'/proc/{pid}/status'):
            if l.startswith('VmRSS:'):
                return int(l.split()[1])
    except OSError:
        return None


class Sampler:
    """B every 200 ms: one Jmx poll JVM for the JMX columns, a thread for VmRSS; merged by time at the end"""

    def __init__(self, pid):
        self.stop = f'{LOGS}/sampler.stop'
        if os.path.exists(self.stop):
            os.remove(self.stop)
        self.jf = open(f'{LOGS}/samples-jmx.csv', 'w')
        self.jf.write('ms,' + ','.join(c for c, _, _ in COLS) + '\n'); self.jf.flush()
        cmd = ['java', '-cp', JMXCP, 'Jmx', str(NODES['B'][1]), 'poll', '200', '100000000', self.stop]
        for _, bean, attr in COLS:
            cmd += [bean, attr]
        log('+ ' + ' '.join(cmd))
        self.p = subprocess.Popen(cmd, stdout=self.jf, stderr=subprocess.STDOUT)
        CHILDREN.append(self.p)
        self.rss = []
        self.alive = True
        self.t = threading.Thread(target=self._rss, args=(pid,), daemon=True)
        self.t.start()

    def _rss(self, pid):
        nxt = time.time()
        while self.alive:
            self.rss.append((int(time.time() * 1000), rss_kb(pid)))
            nxt += 0.2
            time.sleep(max(0.0, nxt - time.time()))

    def close(self):
        open(self.stop, 'w').close()
        self.alive = False
        self.t.join()
        try:
            self.p.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.p.kill()
        self.jf.close()
        with open(f'{LOGS}/samples-rss.csv', 'w') as f:
            f.write('ms,rss_kb\n')
            for ms, kb in self.rss:
                f.write(f'{ms},{kb}\n')
        rows = []
        for l in open(f'{LOGS}/samples-jmx.csv').read().splitlines()[1:]:
            parts = l.split(',')
            if len(parts) == len(COLS) + 1 and parts[0].isdigit():
                rows.append([int(parts[0])] + [num(x) for x in parts[1:]])
        out = []
        j = 0
        for r in rows:          # nearest RSS sample in time
            while j + 1 < len(self.rss) and abs(self.rss[j + 1][0] - r[0]) <= abs(self.rss[j][0] - r[0]):
                j += 1
            kb = self.rss[j][1] if self.rss else None
            out.append(r + [None if kb is None else kb * 1024.0])
        with open(f'{LOGS}/samples.csv', 'w') as f:
            f.write('ms,' + ','.join(c for c, _, _ in COLS) + ',rss\n')
            for r in out:
                f.write(','.join('' if v is None else str(int(v)) for v in r) + '\n')
        return out


def colidx(name):
    return 1 + [c for c, _, _ in COLS].index(name) if name != 'rss' else len(COLS) + 1


def window(rows, t0, t1):
    return [r for r in rows if t0 <= r[0] <= t1]


def whole_seconds(rows):
    """the 1 s readings of B3d: the first sample of each second"""
    seen, out = set(), []
    for r in rows:
        s = r[0] // 1000
        if s not in seen:
            seen.add(s); out.append(r)
    return out


def grep_log(node, t0_ms):
    """exceeds-maximum lines (size, limit) and connection-close lines in node's system.log after t0 (UTC timestamps)"""
    f = f'{IMM}/{node}/logs/system.log'
    exc, closes, outb = [], 0, []
    if not os.path.exists(f):
        return exc, closes, outb
    for l in open(f, errors='replace'):
        m = re.search(r'(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),(\d{3})', l)
        if m:
            ts = calendar.timegm(time.strptime(m.group(1), '%Y-%m-%d %H:%M:%S'))   # the log is in UTC
            cur = int(ts * 1000) + int(m.group(2))
        else:
            cur = None
        if cur is not None and cur < t0_ms:
            continue
        e = EXCEEDS.search(l)
        if e:
            exc.append((int(e.group(1)), int(e.group(2)), cur))
        if 'terminating connection' in l:
            closes += 1
    return exc, closes, outb


# ---------------------------------------------------------------- one lifetime

def lifetime(label):
    la, lb = LABELS[label]
    rep = args[1]
    note(f'cluster-run {tag} {time.strftime("%F %T %Z")} host {os.uname().nodename.split(".")[0]} clone {C} '
         f'{sh("git describe --tags; git rev-parse --short HEAD", quiet=True)[1].split()} IMM_N={NW}')
    note(f'harness md5: ' + sh(f'cd {HARNESS} && md5sum cluster-run.py client.py make-node-yaml.sh Jmx.java', quiet=True,
                               cwd=HARNESS)[1].replace('\n', ' ')[:600])
    note(f'label {label}: A internode_max_message_size={la or "unset (default)"}, B={lb or "unset (default)"}')
    if any_daemon():
        fail('a CassandraDaemon is already running on this host: ' + any_daemon()[:200])
    _, df = sh(f'df -k {HOME}', quiet=True)
    free_gb = int(df.splitlines()[-1].split()[3]) / 1048576
    note(f'free on {HOME}: {free_gb:.1f} GiB')
    if free_gb < 10:
        fail('less than 10 GiB free (B4 asks 5 GiB per node)')
    os.makedirs(JMXCP, exist_ok=True)
    sh(f'javac -d {JMXCP} {HARNESS}/Jmx.java')
    sh(f'rm -rf {IMM}/A {IMM}/B')

    start_node('A', la)
    time.sleep(15)
    start_node('B', lb)
    wait_up()
    sh(f'cp {IMM}/A/conf/cassandra.yaml {LOGS}/A-cassandra.yaml; cp {IMM}/B/conf/cassandra.yaml {LOGS}/B-cassandra.yaml')
    if client('schema', '127.0.0.1') is None:
        fail('schema')
    readback = {}
    for n, (addr, _) in NODES.items():
        r = client('setting', addr, 'internode_max_message_size')
        readback[n] = r and r['value']
        r2 = client('setting', addr, 'native_transport_max_message_size')
        r3 = client('setting', addr, 'hinted_handoff_enabled')
        note(f'read-back {n}: internode_max_message_size={readback[n]} native_transport_max_message_size='
             f'{r2 and r2["value"]} hinted_handoff_enabled={r3 and r3["value"]}')
    _, rb = sh(f'grep -h "internode_max_message_size" {IMM}/A/logs/system.log | head -2', check=False, quiet=True)
    want = {'A': LIMIT_BYTES[la], 'B': LIMIT_BYTES[lb]}
    for n in NODES:
        v = readback[n] or ''
        m = re.match(r'^(\d+)(B|KiB|MiB)$', v.strip())
        got = int(m.group(1)) * {'B': 1, 'KiB': KIB, 'MiB': MIB}[m.group(2)] if m else None
        if got != want[n]:
            fail(f'read-back of {n}: {v!r}, expected {want[n]} bytes')
    _, info = sh(f'bin/nodetool -p 7299 info', check=False, quiet=True)
    (open(f'{LOGS}/B-info-start.txt', 'w')).write(info)

    pidB = pid_of('B')
    t_start = int(time.time() * 1000)
    # baseline (B3e step 4, B3h: GC first)
    sh(f'jcmd {pidB} GC.run', check=False)
    time.sleep(5)
    _, hi = sh(f'jcmd {pidB} GC.heap_info', check=False, quiet=True)
    open(f'{LOGS}/B-heap-baseline.txt', 'w').write(hi)
    beans = [(INB + x, 'Value') for x in ('ReceivedBytes', 'ProcessedBytes', 'ErrorCount', 'ErrorBytes', 'ReceivedCount',
                                          'ProcessedCount')] + [(TABLE_W, 'Count'), (DROP, 'Count')]
    if 'ERROR' in str(jmx('B', (INB + 'ReceivedBytes', 'Value'))):
        _, q = sh(f"java -cp {JMXCP} Jmx 7299 query 'org.apache.cassandra.metrics:type=InboundConnection,*' Value",
                  check=False, quiet=True)
        fail('B has no inbound metrics for 127.0.0.1_7000: ' + q[:400])
    s = Sampler(pidB)
    phases = []
    time.sleep(1)
    t0 = int(time.time() * 1000); time.sleep(10); t1 = int(time.time() * 1000)
    phases.append({'name': 'control', 't0': t0, 't1': t1})
    k = 0
    for size in SIZES:
        before = {n: jmx(n, *beans) for n in NODES}
        t0 = int(time.time() * 1000)
        w = client('write', '127.0.0.1', k, NW, size, f'{LOGS}/keys.csv', timeout=1800)
        t1 = int(time.time() * 1000)
        time.sleep(5)
        t2 = int(time.time() * 1000)
        after = {n: jmx(n, *beans) for n in NODES}
        d = {n: {b.split('name=')[-1].split(',')[0] if 'name=' in b else b: (num(after[n].get((b, a))) or 0) -
                 (num(before[n].get((b, a))) or 0) for b, a in beans} for n in NODES}
        phases.append({'name': f'S={size}', 'size': size, 't0': t0, 't1': t1, 't2': t2, 'write': w, 'delta': d})
        note(f'size {size}: writes {w}; B local writes +{d["B"]["WriteLatency"]:.0f}, A local writes '
             f'+{d["A"]["WriteLatency"]:.0f}; B inbound from A: received +{d["B"]["ReceivedBytes"]:.0f} B '
             f'(+{d["B"]["ReceivedCount"]:.0f} msgs), processed +{d["B"]["ProcessedBytes"]:.0f} B, errors '
             f'+{d["B"]["ErrorCount"]:.0f}; B dropped MUTATION_REQ +{d["B"]["Dropped"]:.0f}')
        k += NW
    rows = s.close()
    _, hi = sh(f'jcmd {pidB} GC.heap_info', check=False, quiet=True)
    open(f'{LOGS}/B-heap-end.txt', 'w').write(hi)

    # peaks against the control window's median (B3d)
    base_rows = window(rows, phases[0]['t0'], phases[0]['t1'])
    base = {c: statistics.median([r[colidx(c)] for r in base_rows if r[colidx(c)] is not None] or [0]) for c in MEM_COLS}
    note('baseline (median of the 10 s control, B): ' + ', '.join(f'{c}={base[c] / MIB:.2f}MiB' for c in MEM_COLS))
    for ph in phases[1:]:
        wr = window(rows, ph['t0'], ph['t2'])
        ws = whole_seconds(wr)
        ph['peak'] = {c: max([r[colidx(c)] for r in wr if r[colidx(c)] is not None] or [0]) - base[c] for c in MEM_COLS}
        ph['peak_1s'] = {c: max([r[colidx(c)] for r in ws if r[colidx(c)] is not None] or [0]) - base[c] for c in MEM_COLS}
        ph['samples'] = len(wr)
        note(f'{ph["name"]}: {len(wr)} samples; peak increment over baseline (200 ms / 1 s): ' +
             ', '.join(f'{c} {ph["peak"][c] / MIB:+.2f}/{ph["peak_1s"][c] / MIB:+.2f}MiB' for c in MEM_COLS))

    # after the workload (B3e step 6)
    _, tp = sh('bin/nodetool -p 7299 tpstats', check=False, quiet=True)
    open(f'{LOGS}/B-tpstats.txt', 'w').write(tp)
    m = re.search(r'^MUTATION_REQ\s+(\d+)', tp, re.M)
    note(f'B tpstats dropped MUTATION_REQ: {m.group(1) if m else "?"}')
    logs = {}
    for n in NODES:
        exc, closes, _ = grep_log(n, 0)   # the node directories are wiped per lifetime: the whole log is this lifetime
        # (read before the counts below: their replica reads are not part of the workload)
        logs[n] = {'exceeds': exc, 'closes': closes}
        by = {}
        for sz, lim, _ in exc:
            by[(sz, lim)] = by.get((sz, lim), 0) + 1
        note(f'{n} system.log (this lifetime, before the counts): {len(exc)} "exceeds allowed maximum" lines '
             f'{sorted(by.items())[:6]}, {closes} "terminating connection" lines')
        sh(f"grep -n 'exceeds allowed maximum\\|terminating connection\\|OversizedMessage' {IMM}/{n}/logs/system.log "
           f"| head -40 > {LOGS}/{n}-log-excerpt.txt", check=False)
        sh(f"grep -c '^ERROR' {IMM}/{n}/logs/system.log > {LOGS}/{n}-error-count.txt", check=False)
        sh(f"grep '^ERROR\\|^WARN' {IMM}/{n}/logs/system.log | cut -c1-300 | head -60 > {LOGS}/{n}-errors-warns.txt",
           check=False)
    counts = {}
    for n, (addr, port) in NODES.items():
        sh(f'bin/nodetool -p {port} flush ks t', check=False)
        _, ts = sh(f'bin/nodetool -p {port} tablestats ks.t', check=False, quiet=True)
        open(f'{LOGS}/{n}-tablestats.txt', 'w').write(ts)
        lw = re.search(r'Local write count: (\d+)', ts)
        np_ = re.search(r'Number of partitions \(estimate\): (\d+)', ts)
        r = client('count', addr)
        counts[n] = {'local_writes': int(lw.group(1)) if lw else None, 'partitions': int(np_.group(1)) if np_ else None,
                     'count_one': r and r['count']}
        note(f'{n}: tablestats local write count {counts[n]["local_writes"]}, partitions (estimate) '
             f'{counts[n]["partitions"]}; count(*) at ONE through {n}: {counts[n]["count_one"]}')
    for n in NODES:
        exc2, _, _ = grep_log(n, 0)
        logs[n]['exceeds_during_counts'] = exc2[len(logs[n]['exceeds']):]
        note(f'{n} system.log during the counts: {len(logs[n]["exceeds_during_counts"])} "exceeds allowed maximum" lines '
             f'{[(a, b) for a, b, _ in logs[n]["exceeds_during_counts"]][:6]}')
    sh(f'cp {IMM}/A/logs/system.log {LOGS}/A-system.log; cp {IMM}/B/logs/system.log {LOGS}/B-system.log', check=False)
    json.dump({'label': label, 'rep': rep, 'limits': {'A': want['A'], 'B': want['B']}, 'base': base, 'phases': phases,
               'counts': counts, 'logs': logs}, open(f'{LOGS}/phases.json', 'w'), indent=1)

    # B3f, per lifetime (the cross-run relation is in `analyze`)
    small, mid, big = phases[1], phases[2], phases[3]
    def oks(ph):
        return (ph['write'] or {}).get('ok', -1)
    def bw(ph):
        return ph['delta']['B']['WriteLatency']
    expect(f'S=512KiB: all {NW} writes succeed and B applies {NW}', oks(small) == NW and bw(small) == NW)
    if label in ('R0', 'R1'):
        for ph in (mid, big):
            expect(f'{ph["name"]}: all {NW} writes succeed, B applies {NW}', oks(ph) == NW and bw(ph) == NW)
            expect(f'{ph["name"]}: B pool Size or direct peak at least S above baseline',
                   max(ph['peak']['pool_size'], ph['peak']['direct_used']) >= ph['size'])
        expect('no "exceeds allowed maximum" line on A or B', not logs['A']['exceeds'] and not logs['B']['exceeds'])
    if label == 'R2':
        for ph in (mid, big):
            expect(f'{ph["name"]}: no write succeeds and B applies none', oks(ph) == 0 and bw(ph) == 0)
            expect(f'{ph["name"]}: B logs "exceeds allowed maximum of 1048576 bytes" for messages of about S',
                   any(lim == MIB and ph['size'] < sz < ph['size'] + 4096 for sz, lim, _ in logs['B']['exceeds']))
        expect('A logs no "exceeds allowed maximum" line', not logs['A']['exceeds'])
        expect('B pool Size / direct increment does not scale with S (12MiB peak <= 4MiB peak + 1 MiB)',
               max(big['peak']['pool_size'], big['peak']['direct_used']) <=
               max(mid['peak']['pool_size'], mid['peak']['direct_used']) + MIB)
    if label == 'R3':
        for ph in (mid, big):
            expect(f'{ph["name"]}: no write succeeds and B applies none', oks(ph) == 0 and bw(ph) == 0)
            expect(f'{ph["name"]}: B receives less than S from A', ph['delta']['B']['ReceivedBytes'] < ph['size'])
            expect(f'{ph["name"]}: A logs "exceeds allowed maximum of 1048576 bytes" for messages of about S',
                   any(lim == MIB and ph['size'] < sz < ph['size'] + 4096 for sz, lim, _ in logs['A']['exceeds']))
    note(f'EXPECTED totals: yes={EXPECT["yes"]} no={EXPECT["no"]}')

    stop_all()
    ok = not any_daemon()
    _, ss = sh("ss -ltn | grep -E ':(7000|7199|7299|9042)\\b' || true", check=False, quiet=True)
    note(f'cleanup: CassandraDaemon left: {"none" if ok else "YES"}; listeners on 7000/7199/7299/9042: '
         f'{ss.strip() or "none"}')


def analyze():
    runs = {}
    for d in sorted(os.listdir(ROOT)):
        f = f'{ROOT}/{d}/phases.json'
        if os.path.exists(f):
            j = json.load(open(f))
            runs[(j['label'], j['rep'])] = j
    out = open(f'{ROOT}/analysis.txt', 'w')
    def say(s):
        print(s); out.write(s + '\n')
    say(f'analysis {time.strftime("%F %T %Z")}: lifetimes {sorted(runs)}')
    for (lab, rep), j in sorted(runs.items()):
        for ph in j['phases'][1:]:
            say(f'{lab}-{rep} {ph["name"]:>12}: ok {(ph["write"] or {}).get("ok")}/{NW}, B applied '
                f'{ph["delta"]["B"]["WriteLatency"]:.0f}, B received {ph["delta"]["B"]["ReceivedBytes"] / MIB:.2f} MiB, '
                f'peak pool_size {ph["peak"]["pool_size"] / MIB:+.2f} direct {ph["peak"]["direct_used"] / MIB:+.2f} '
                f'rss {ph["peak"]["rss"] / MIB:+.2f} heap {ph["peak"]["heap_used"] / MIB:+.2f} MiB')
    def peak(lab, rep, size, col):
        j = runs.get((lab, rep))
        if not j:
            return None
        for ph in j['phases'][1:]:
            if ph['size'] == size:
                return ph['peak'][col]
    for rep in ('1', '2'):
        for col in ('pool_size', 'direct_used', 'rss'):
            r1, r2 = peak('R1', rep, 12 * MIB, col), peak('R2', rep, 12 * MIB, col)
            if r1 is not None and r2 is not None:
                say(f'B3f relation rep {rep}, {col}: R2 12MiB peak {r2 / MIB:+.2f} MiB vs R1 {r1 / MIB:+.2f} MiB -> '
                    f'{"R2 <= R1/3" if r2 <= r1 / 3 else "R2 > R1/3"}')
    out.close()


if label == 'down':
    note(f'down: {"stopped" if stop_all() else "a daemon is left"}')
elif label == 'analyze':
    analyze()
else:
    try:
        lifetime(label)
    except SystemExit:
        raise
    except Exception as e:
        fail(f'{type(e).__name__}: {e}')
