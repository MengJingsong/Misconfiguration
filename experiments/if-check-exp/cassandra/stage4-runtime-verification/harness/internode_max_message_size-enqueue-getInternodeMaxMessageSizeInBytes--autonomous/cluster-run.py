#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of internode_max_message_size-enqueue-getInternodeMaxMessageSizeInBytes--autonomous
(case file with the step-0 amendments R1-R5 of 2026-10-20).
usage: cluster-run.py <label> | analyze | down
  <label>   one lifetime of both nodes (B3e steps 1-5): wipe $IME/{A,B}, write both yaml files with the label's
            internode_max_message_size (the same on both nodes, B3b), start A (the seed) then B, wait for UN and running
            binary on both, create ks (RF 2) and ks.t, read the limit back from system_views.settings on both nodes,
            GC both and take a 10 s idle control (the baseline), then the 2 MiB workload (B3c: 16 client threads x 200
            INSERTs of 2,097,152 random bytes at CL ALL, all through A), 5 s settle; for L1MC instead the 256 KiB control
            workload (16 x 200 x 262,144 B), 5 s settle (B3e step 4 in its own lifetime: results section 3, defect 3). Both nodes are sampled every 200 ms (JMX: java.nio direct pool,
            heap, networking pool Size/UsedSize/OverflowSize (R2); on A the outbound Connection gauges toward B (R4); on B
            the inbound counters from A; /proc VmRSS); the 1 s readings of B3d are the first sample of each second, and
            both are reported. Then per-phase counter deltas, tpstats, tablestats, the "exceeds allowed maximum" and
            "Unexpected exception during request" lines of both logs, data size per node. Both nodes stopped, their data,
            commit log and hints deleted (B3e step 5, R3).
            Labels: L1M = 1MiB, L1MC = 1MiB (the 256 KiB control), L8M = 8MiB, DEF = not set (128 MiB derived
            default, amendment R1). After cluster attempt 1, A's and B's MutationStage and Native-Transport-Requests
            pending tasks and ks.t's memtable heap are sampled too (what holds the heap).
  analyze   reads every <label>/phases.json of the run and writes analysis.txt: the B3f relations across lifetimes.
  down      stop both nodes of this harness.
Two nodes on this host on loopback: A = 127.0.0.2 (JMX 7102, seed, the only coordinator), B = 127.0.0.3 (JMX 7103).
Output: ~/stage4-logs/ime/<run>/cluster/<label>/ (summary.txt with EXPECTED lines, session.log, samples-A.csv,
samples-B.csv, phases.json, keys-<phase>.csv, logs). Exit 1: a set-up check failed (a node not UN, the read-back, a
client that could not connect); then both nodes are stopped. A reading that misses a prediction is recorded as
EXPECTED ... NO and the run goes on.
Environment: IME_RUN (run folder, default run1), CASSANDRA_HOME (default ~/cassandra-run1), IME (node root, default
/mydata/stage4-ime), IME_THREADS (16), IME_PER (writes per thread, 200; a shakedown may lower it).
From the internode_max_message_size-inferMessageSize-size--autonomous harness's cluster-run.py."""
import calendar, json, os, re, shutil, statistics, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-run1')
HARNESS = os.path.dirname(os.path.abspath(__file__))
IME = os.environ.get('IME', '/mydata/stage4-ime')
RUN = os.environ.get('IME_RUN', 'run1')
NT = int(os.environ.get('IME_THREADS', 16))
PER = int(os.environ.get('IME_PER', 200))
NW = NT * PER
KIB, MIB = 1024, 1 << 20
BIG, SMALL = 2 * MIB, 256 * KIB
NODES = {'A': ('127.0.0.2', 7102), 'B': ('127.0.0.3', 7103)}
LABELS = {'L1M': '1MiB', 'L1MC': '1MiB', 'L8M': '8MiB', 'DEF': None}
LIMIT_BYTES = {'1MiB': MIB, '8MiB': 8 * MIB, None: 128 * MIB}
CLIENT = HARNESS + '/client.py'
JMXCP = IME + '/jmx'
POOL = 'org.apache.cassandra.metrics:type=BufferPool,scope=networking,name='
TABLE_W = 'org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=t,name=WriteLatency'
CLIENT_W = 'org.apache.cassandra.metrics:type=ClientRequest,scope=Write,name=Latency'
DROP = 'org.apache.cassandra.metrics:type=DroppedMessage,scope=MUTATION_REQ,name=Dropped'
MEM = [('direct_used', 'java.nio:type=BufferPool,name=direct', 'MemoryUsed'),
       ('direct_count', 'java.nio:type=BufferPool,name=direct', 'Count'),
       ('heap_used', 'java.lang:type=Memory', 'HeapMemoryUsage'),
       ('pool_size', POOL + 'Size', 'Value'), ('pool_used', POOL + 'UsedSize', 'Value'),
       ('pool_overflow', POOL + 'OverflowSize', 'Value'),
       # added after cluster attempt 1 (node A ran out of heap in L1M; results section 3, defect 3): what holds the heap
       ('mutation_pending', 'org.apache.cassandra.metrics:type=ThreadPools,path=request,scope=MutationStage,name=PendingTasks', 'Value'),
       ('mutation_active', 'org.apache.cassandra.metrics:type=ThreadPools,path=request,scope=MutationStage,name=ActiveTasks', 'Value'),
       ('ntr_pending', 'org.apache.cassandra.metrics:type=ThreadPools,path=transport,scope=Native-Transport-Requests,name=PendingTasks', 'Value'),
       ('memtable_heap', 'org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=t,name=AllMemtablesOnHeapDataSize', 'Value')]
OUT_NAMES = ['LargeMessagePendingBytes', 'LargeMessagePendingTasks', 'LargeMessageCompletedTasks',
             'LargeMessageCompletedBytes', 'LargeMessageDroppedTasksDueToOverload', 'LargeMessageDroppedTasksDueToTimeout',
             'LargeMessageDroppedTasksDueToError', 'SmallMessagePendingBytes', 'UrgentMessagePendingBytes']
IN_NAMES = ['ReceivedBytes', 'ReceivedCount', 'ProcessedBytes', 'ErrorCount']
MEM_COLS = ['direct_used', 'pool_size', 'pool_used', 'pool_overflow', 'heap_used', 'rss']
EXCEEDS = re.compile(r'Message of size (\d+) bytes exceeds allowed maximum of (\d+) bytes')

args = sys.argv[1:]
if len(args) != 1 or args[0] not in list(LABELS) + ['analyze', 'down']:
    sys.exit(__doc__)
label = args[0]
ROOT = f'{HOME}/stage4-logs/ime/{RUN}/cluster'
LOGS = f'{ROOT}/{label}'
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
    f = f'{IME}/{node}/cassandra.pid'
    try:
        pid = int(open(f).read().strip())
        return pid if 'CassandraDaemon' in open(f'/proc/{pid}/cmdline').read() else None
    except (ValueError, OSError):
        return None


def any_daemon():
    # a java process whose command line names the daemon class (not a shell that mentions it)
    out = sh("ps -eo comm,args | awk '$1==\"java\" && /CassandraDaemon/' || true", check=False, quiet=True)[1].strip()
    return out


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
              env=dict(os.environ, CASSANDRA_HOME=C, IME=IME))
    note(y.strip().splitlines()[-1][:900])
    N = f'{IME}/{node}'
    env = dict(os.environ, CASSANDRA_CONF=N + '/conf', CASSANDRA_LOG_DIR=N + '/logs', MAX_HEAP_SIZE='1G',
               HEAP_NEWSIZE='256M')
    env.pop('JVM_EXTRA_OPTS', None)
    # ulimit -n: the node's soft limit is 1024 (environment.md section 7); raise it in the shell that starts the node
    sh(f'ulimit -n 100000 && bin/cassandra -p {N}/cassandra.pid > {N}/stdout.txt 2>&1', env=env)
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
    """one node every 200 ms: one Jmx poll JVM for the JMX columns, a thread for VmRSS; merged by time at the end"""

    def __init__(self, node, pid, cols):
        self.node, self.cols = node, cols
        self.stop = f'{LOGS}/sampler-{node}.stop'
        if os.path.exists(self.stop):
            os.remove(self.stop)
        self.jf = open(f'{LOGS}/samples-jmx-{node}.csv', 'w')
        self.jf.write('ms,' + ','.join(c for c, _, _ in cols) + '\n'); self.jf.flush()
        cmd = ['java', '-cp', JMXCP, 'Jmx', str(NODES[node][1]), 'poll', '200', '100000000', self.stop]
        for _, bean, attr in cols:
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
        rows = []
        for l in open(f'{LOGS}/samples-jmx-{self.node}.csv').read().splitlines()[1:]:
            parts = l.split(',')
            if len(parts) == len(self.cols) + 1 and parts[0].isdigit():
                rows.append([int(parts[0])] + [num(x) for x in parts[1:]])
        out, j = [], 0
        for r in rows:          # nearest RSS sample in time
            while j + 1 < len(self.rss) and abs(self.rss[j + 1][0] - r[0]) <= abs(self.rss[j][0] - r[0]):
                j += 1
            kb = self.rss[j][1] if self.rss else None
            out.append(r + [None if kb is None else kb * 1024.0])
        with open(f'{LOGS}/samples-{self.node}.csv', 'w') as f:
            f.write('ms,' + ','.join(c for c, _, _ in self.cols) + ',rss\n')
            for r in out:
                f.write(','.join('' if v is None else str(int(v)) for v in r) + '\n')
        return out


def colidx(cols, name):
    names = [c for c, _, _ in cols]
    return 1 + names.index(name) if name != 'rss' else len(cols) + 1


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


def grep_log(node):
    """("exceeds", size, limit, ms) and ("unexpected", ms) events in node's system.log (UTC timestamps)"""
    f = f'{IME}/{node}/logs/system.log'
    exc, unexp = [], []
    if not os.path.exists(f):
        return exc, unexp
    cur = None
    for l in open(f, errors='replace'):
        m = re.match(r'^[A-Z]+\s+\[[^\]]*\]\s+(\d{4}-\d\d-\d\d)[ T](\d\d:\d\d:\d\d),(\d{3})', l)
        if m:
            ts = calendar.timegm(time.strptime(m.group(1) + ' ' + m.group(2), '%Y-%m-%d %H:%M:%S'))   # the log is in UTC
            cur = int(ts * 1000) + int(m.group(3))
            if 'Unexpected exception during request' in l:
                unexp.append(cur)
        e = EXCEEDS.search(l)
        if e:
            exc.append((int(e.group(1)), int(e.group(2)), cur))
    return exc, unexp


def du(path):
    _, o = sh(f'du -sb {path} 2>/dev/null | cut -f1', check=False, quiet=True, cwd=HOME)
    return int(o.strip() or 0)


# ---------------------------------------------------------------- one lifetime

def lifetime(label):
    lim = LABELS[label]
    note(f'cluster-run {label} {time.strftime("%F %T %Z")} host {os.uname().nodename.split(".")[0]} clone {C} '
         f'{sh("git describe --tags; git rev-parse --short HEAD", quiet=True)[1].split()} threads {NT} x {PER} writes')
    note('harness md5: ' + sh('md5sum cluster-run.py client.py make-node-yaml.sh Jmx.java', quiet=True,
                              cwd=HARNESS)[1].replace('\n', ' ')[:600])
    note(f'label {label}: internode_max_message_size on both nodes = {lim or "unset (derived default)"}')
    if any_daemon():
        fail('a CassandraDaemon is already running on this host: ' + any_daemon()[:200])
    os.makedirs(IME, exist_ok=True)
    for d in (IME, HOME):
        _, df = sh(f'df -k {d}', quiet=True)
        free_gb = int(df.splitlines()[-1].split()[3]) / 1048576
        note(f'free on {d}: {free_gb:.1f} GiB')
        if free_gb < (40 if d == IME else 5):
            fail(f'not enough free space on {d} (R3: up to about 15 GiB per node per accepted run)')
    os.makedirs(JMXCP, exist_ok=True)
    sh(f'javac -d {JMXCP} {HARNESS}/Jmx.java')
    sh(f'rm -rf {IME}/A {IME}/B')

    start_node('A', lim)
    time.sleep(15)
    start_node('B', lim)
    wait_up()
    sh(f'cp {IME}/A/conf/cassandra.yaml {LOGS}/A-cassandra.yaml; cp {IME}/B/conf/cassandra.yaml {LOGS}/B-cassandra.yaml')
    if client('schema', NODES['A'][0]) is None:
        fail('schema')
    want = LIMIT_BYTES[lim]
    for n, (addr, _) in NODES.items():
        vals = {}
        for name in ('internode_max_message_size', 'write_request_timeout', 'hinted_handoff_enabled',
                     'internode_application_send_queue_capacity', 'internode_application_send_queue_reserve_endpoint_capacity',
                     'internode_application_receive_queue_reserve_endpoint_capacity', 'max_mutation_size',
                     'native_transport_max_message_size', 'num_tokens'):
            r = client('setting', addr, name)
            vals[name] = r and r['value']
        note(f'read-back {n}: ' + ', '.join(f'{k}={v}' for k, v in vals.items()))
        v = (vals['internode_max_message_size'] or '').strip()
        m = re.match(r'^(\d+)(B|KiB|MiB)$', v)
        got = int(m.group(1)) * {'B': 1, 'KiB': KIB, 'MiB': MIB}[m.group(2)] if m else None
        if got != want:
            fail(f'read-back of {n}: {v!r}, expected {want} bytes')
        if (vals['hinted_handoff_enabled'] or '').lower() != 'false':
            fail(f'hinted_handoff_enabled on {n} is {vals["hinted_handoff_enabled"]!r} (R5)')

    # metric scopes (R4): A's outbound Connection gauges toward B, B's inbound from A
    def scope(node, typ, addr, name):
        # the query names one gauge: a wildcard over the type also matches meters (Timeouts), which have no Value
        _, q = sh(f"java -cp {JMXCP} Jmx {NODES[node][1]} query 'org.apache.cassandra.metrics:type={typ},name={name},*' Value",
                  check=False, quiet=True)
        for l in q.splitlines():
            mm = re.search(r'scope=([^,]+),', l)
            if mm and addr in mm.group(1):
                return mm.group(1)
        return None
    out_scope = scope('A', 'Connection', NODES['B'][0], 'LargeMessagePendingBytes')
    in_scope = scope('B', 'InboundConnection', NODES['A'][0], 'ReceivedBytes')
    note(f'metric scopes: A type=Connection scope={out_scope}; B type=InboundConnection scope={in_scope}')
    if not out_scope or not in_scope:
        fail('outbound or inbound connection metrics not found')
    OUT = [(n, f'org.apache.cassandra.metrics:type=Connection,scope={out_scope},name={n}', 'Value') for n in OUT_NAMES]
    INB = [(n, f'org.apache.cassandra.metrics:type=InboundConnection,scope={in_scope},name={n}', 'Value') for n in IN_NAMES]
    chk = jmx('A', *[(b, a) for _, b, a in OUT])
    bad = [n for n, b, a in OUT if (chk.get((b, a)) or 'ERROR').startswith('ERROR')]
    note(f'R4 name check on A: {len(OUT) - len(bad)}/{len(OUT)} outbound gauges readable; missing {bad}')
    if 'LargeMessagePendingBytes' in bad:
        fail('LargeMessagePendingBytes not readable')
    COLS = {'A': MEM + OUT, 'B': MEM + INB}
    counters = {'A': [(TABLE_W, 'Count'), (CLIENT_W, 'Count')] + [(b, a) for _, b, a in OUT],
                'B': [(TABLE_W, 'Count'), (CLIENT_W, 'Count'), (DROP, 'Count')] + [(b, a) for _, b, a in INB]}

    pids = {n: pid_of(n) for n in NODES}
    for n in NODES:
        sh(f'jcmd {pids[n]} GC.run', check=False)
    time.sleep(5)
    for n in NODES:
        _, hi = sh(f'jcmd {pids[n]} GC.heap_info', check=False, quiet=True)
        open(f'{LOGS}/{n}-heap-start.txt', 'w').write(hi)
    samplers = {n: Sampler(n, pids[n], COLS[n]) for n in NODES}
    phases = []
    time.sleep(1)
    t0 = int(time.time() * 1000); time.sleep(10); t1 = int(time.time() * 1000)
    phases.append({'name': 'control', 't0': t0, 't1': t1, 't2': t1})
    # B3e step 4's 256 KiB control runs in its own lifetime at the same setting (L1MC): in cluster attempt 1 node A ran
    # out of heap during L1M's 2 MiB workload, so the control could not run after it (results section 3, defect 3)
    plan = [('P256K', SMALL)] if label == 'L1MC' else [('P2M', BIG)]
    k = 0
    for name, size in plan:
        before = {n: jmx(n, *counters[n]) for n in NODES}
        t0 = int(time.time() * 1000)
        w = client('load', NODES['A'][0], k, NT, PER, size, f'{LOGS}/keys-{name}.csv', timeout=7200)
        t1 = int(time.time() * 1000)
        time.sleep(5)
        t2 = int(time.time() * 1000)
        after = {n: jmx(n, *counters[n]) for n in NODES}

        def short(b):
            return (b.split('scope=')[1].split(',')[0] + '.' if 'type=ClientRequest' in b else '') + \
                   (b.split('name=')[-1].split(',')[0] if 'name=' in b else b)
        d = {n: {short(b): (num(after[n].get((b, a))) or 0) - (num(before[n].get((b, a))) or 0)
                 for b, a in counters[n]} for n in NODES}
        phases.append({'name': name, 'size': size, 't0': t0, 't1': t1, 't2': t2, 'write': w, 'delta': d})
        note(f'{name} ({size} B): client {w}')
        note(f'{name}: alive after the phase: ' + ', '.join(f'{n} {"yes" if pid_of(n) == pids[n] else "NO"}' for n in NODES))
        note(f'{name}: A local writes +{d["A"]["WriteLatency"]:.0f}, A client writes +{d["A"]["Write.Latency"]:.0f}; '
             f'B local writes +{d["B"]["WriteLatency"]:.0f}, B client writes +{d["B"]["Write.Latency"]:.0f}; '
             f'B dropped MUTATION_REQ +{d["B"]["Dropped"]:.0f}')
        note(f'{name}: A outbound to B: ' + ', '.join(f'{x} +{d["A"][x]:.0f}' for x in OUT_NAMES if 'Pending' not in x))
        note(f'{name}: B inbound from A: ' + ', '.join(f'{x} +{d["B"][x]:.0f}' for x in IN_NAMES))
        k += NW
    rows = {n: samplers[n].close() for n in NODES}
    for n in NODES:
        _, hi = sh(f'jcmd {pids[n]} GC.heap_info', check=False, quiet=True)
        open(f'{LOGS}/{n}-heap-end.txt', 'w').write(hi)

    # peaks against the control window's median (B3d)
    base = {}
    for n in NODES:
        br = window(rows[n], phases[0]['t0'], phases[0]['t1'])
        base[n] = {c: statistics.median([r[colidx(COLS[n], c)] for r in br if r[colidx(COLS[n], c)] is not None] or [0])
                   for c in MEM_COLS}
        note(f'baseline {n} (median of the 10 s control): ' + ', '.join(f'{c}={base[n][c] / MIB:.2f}MiB' for c in MEM_COLS))
    pend = 'LargeMessagePendingBytes'
    for ph in phases[1:]:
        ph['peak'], ph['peak_1s'], ph['samples'] = {}, {}, {}
        for n in NODES:
            wr = window(rows[n], ph['t0'], ph['t2'])
            ws = whole_seconds(wr)
            cols = MEM_COLS + ['mutation_pending', 'ntr_pending', 'memtable_heap'] + ([pend, 'LargeMessagePendingTasks'] if n == 'A' else [])
            def pk(rs, c):
                vals = [r[colidx(COLS[n], c)] for r in rs if r[colidx(COLS[n], c)] is not None]
                return (max(vals) if vals else 0) - (base[n][c] if c in MEM_COLS else 0)
            ph['peak'][n] = {c: pk(wr, c) for c in cols}
            ph['peak_1s'][n] = {c: pk(ws, c) for c in cols}
            ph['samples'][n] = len(wr)
            if n == 'A':
                nz = [r for r in wr if (r[colidx(COLS['A'], pend)] or 0) > 0]
                ph['pending_nonzero_samples'] = len(nz)
            note(f'{ph["name"]} {n}: {len(wr)} samples; peak increment over baseline (200 ms / 1 s): ' +
                 ', '.join(f'{c} {ph["peak"][n][c] / MIB:+.2f}/{ph["peak_1s"][n][c] / MIB:+.2f}MiB' for c in cols))
        note(f'{ph["name"]} A: samples with LargeMessagePendingBytes > 0: {ph["pending_nonzero_samples"]} of '
             f'{ph["samples"]["A"]}; LargeMessagePendingTasks peak {ph["peak"]["A"]["LargeMessagePendingTasks"]:.0f}')

    # after the workload
    for n, (addr, port) in NODES.items():
        _, tp = sh(f'bin/nodetool -p {port} tpstats', check=False, quiet=True)
        open(f'{LOGS}/{n}-tpstats.txt', 'w').write(tp)
        m = re.search(r'^MUTATION_REQ\s+(\d+)', tp, re.M)
        _, ts = sh(f'bin/nodetool -p {port} tablestats ks.t', check=False, quiet=True)
        open(f'{LOGS}/{n}-tablestats.txt', 'w').write(ts)
        lw = re.search(r'Local write count: (\d+)', ts)
        note(f'{n}: tpstats dropped MUTATION_REQ {m.group(1) if m else "?"}; tablestats local write count '
             f'{lw.group(1) if lw else "?"}')
    logs = {}
    for n in NODES:
        exc, unexp = grep_log(n)
        logs[n] = {'exceeds': exc, 'unexpected': unexp}
        for ph in phases[1:]:
            e = [x for x in exc if x[2] is not None and ph['t0'] - 1000 <= x[2] <= ph['t2']]
            u = [x for x in unexp if ph['t0'] - 1000 <= x <= ph['t2']]
            by = {}
            for sz, li, _ in e:
                by[(sz, li)] = by.get((sz, li), 0) + 1
            ph.setdefault('log', {})[n] = {'exceeds': len(e), 'by': sorted(by.items()), 'unexpected': len(u)}
            note(f'{ph["name"]} {n} system.log: {len(e)} "exceeds allowed maximum" lines {sorted(by.items())[:4]}, '
                 f'{len(u)} "Unexpected exception during request" lines')
        note(f'{n} system.log whole lifetime: {len(exc)} exceeds lines, {len(unexp)} unexpected-exception lines')
        sh(f"grep -n -m 40 'exceeds allowed maximum' {IME}/{n}/logs/system.log > {LOGS}/{n}-log-excerpt.txt", check=False)
        sh(f"grep -n -m1 -A30 'exceeds allowed maximum' {IME}/{n}/logs/system.log > {LOGS}/{n}-stack-first.txt", check=False)
        sh(f"grep -c '^ERROR' {IME}/{n}/logs/system.log > {LOGS}/{n}-error-count.txt", check=False)
        sh(f"grep '^ERROR\\|^WARN' {IME}/{n}/logs/system.log | sed -E 's/ [0-9]{{4}}-[0-9-]+T[0-9:,]+ / /' | cut -c1-300 | sort | uniq -c | sort -rn | head -40 "
           f"> {LOGS}/{n}-errors-warns.txt", check=False)
    sizes = {}
    for n in NODES:
        sizes[n] = {d: du(f'{IME}/{n}/{d}') for d in ('data', 'commitlog', 'hints')}
        note(f'{n} on-disk bytes: ' + ', '.join(f'{d} {v / MIB:.1f} MiB' for d, v in sizes[n].items()))
    json.dump({'label': label, 'limit': want, 'threads': NT, 'per': PER, 'base': base, 'phases': phases,
               'logs': logs, 'sizes': sizes, 'cols': {n: [c for c, _, _ in COLS[n]] for n in NODES}},
              open(f'{LOGS}/phases.json', 'w'), indent=1)

    # B3f, per lifetime (the cross-run relation is in `analyze`)
    big = phases[1]
    ok_big = (big['write'] or {}).get('ok', -1)
    for n in NODES:
        note(f'node {n} alive at the end of the workload: {"yes" if pid_of(n) == pids[n] else "NO"}')
    expect(f'node B is not a coordinator: B client writes +0 in every phase',
           all(ph['delta']['B']['Write.Latency'] == 0 for ph in phases[1:]))
    if label == 'L1MC':
        expect(f'P256K: all {NW} writes succeed', ok_big == NW)
        expect('P256K: no "exceeds allowed maximum" line on A or B', big['log']['A']['exceeds'] == 0 and
               big['log']['B']['exceeds'] == 0)
    elif label == 'L1M':
        expect(f'P2M: client writes at CL ALL fail ({NW} of {NW} err)', ok_big == 0)
        expect('P2M: A logs "Message of size ~2.1e6 bytes exceeds allowed maximum of 1048576 bytes"',
               any(li == MIB and BIG < sz < BIG + 4096 for sz, li in [(a, b) for (a, b), _ in big['log']['A']['by']]))
        expect('P2M: peak LargeMessagePendingBytes on A toward B about 0 (= 0 in every 200 ms sample)',
               big['peak']['A'][pend] == 0)
        for n in NODES:
            expect(f'P2M: no direct-memory growth from large payloads on {n} (direct and pool Size peak increment < '
                   f'one 2 MiB message)', max(big['peak'][n]['direct_used'], big['peak'][n]['pool_size']) < BIG)
    else:
        expect(f'P2M: all {NW} writes succeed', ok_big == NW)
        expect('P2M: no "exceeds allowed maximum" line on A or B', big['log']['A']['exceeds'] == 0 and
               big['log']['B']['exceeds'] == 0)
        expect('P2M: peak LargeMessagePendingBytes on A toward B > 0', big['peak']['A'][pend] > 0)
        expect(f'P2M: peak LargeMessagePendingBytes <= about {NT} x 2 MiB (16 x (2 MiB + 4 KiB))',
               big['peak']['A'][pend] <= NT * (BIG + 4096))
    note(f'EXPECTED totals: yes={EXPECT["yes"]} no={EXPECT["no"]}')

    stop_all()
    for n in NODES:
        for f in ('system.log', 'debug.log', 'gc.log'):
            if os.path.exists(f'{IME}/{n}/logs/{f}'):
                shutil.copy(f'{IME}/{n}/logs/{f}', f'{LOGS}/{n}-{f}')
        # B3e step 5 / R3: the data of this lifetime is deleted (the logs are kept above)
        for d in ('data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw'):
            shutil.rmtree(f'{IME}/{n}/{d}', ignore_errors=True)
    ok = not any_daemon()
    _, ss = sh("ss -ltn | grep -E ':(7000|7102|7103|9042)\\b' || true", check=False, quiet=True)
    note(f'cleanup: CassandraDaemon left: {"none" if ok else "YES"}; listeners on 7000/7102/7103/9042: '
         f'{ss.strip() or "none"}; data, commit log and hints deleted')


def analyze():
    runs = {}
    for d in sorted(os.listdir(ROOT)):
        f = f'{ROOT}/{d}/phases.json'
        if os.path.exists(f):
            j = json.load(open(f))
            runs[j['label']] = j
    out = open(f'{ROOT}/analysis.txt', 'w')

    def say(s):
        print(s); out.write(s + '\n')
    say(f'analysis {time.strftime("%F %T %Z")}: lifetimes {sorted(runs)}')
    for lab, j in sorted(runs.items()):
        for ph in j['phases'][1:]:
            w = ph['write'] or {}
            say(f'{lab} {ph["name"]:>6}: ok {w.get("ok")}/{j["threads"] * j["per"]} in {w.get("seconds")} s; '
                f'A pending peak {ph["peak"]["A"]["LargeMessagePendingBytes"] / MIB:.2f} MiB '
                f'(1 s {ph["peak_1s"]["A"]["LargeMessagePendingBytes"] / MIB:.2f}); ' +
                '; '.join(f'{n} direct {ph["peak"][n]["direct_used"] / MIB:+.2f} (1 s {ph["peak_1s"][n]["direct_used"] / MIB:+.2f}) '
                          f'pool {ph["peak"][n]["pool_size"] / MIB:+.2f} rss {ph["peak"][n]["rss"] / MIB:+.2f} '
                          f'heap {ph["peak"][n]["heap_used"] / MIB:+.2f} MiB' for n in NODES))
    ok_all = 'L1M' in runs and 'L8M' in runs and 'DEF' in runs
    if not ok_all:
        say('not every lifetime (L1M, L8M, DEF) has a phases.json: the relation cannot hold')
    if 'L1M' in runs:
        r1 = runs['L1M']['phases'][1]
        for lab in ('L8M', 'DEF'):
            if lab not in runs:
                continue
            rb = runs[lab]['phases'][1]
            for n in NODES:
                for key in ('peak', 'peak_1s'):
                    dlt = rb[key][n]['direct_used'] - r1[key][n]['direct_used']
                    good = MIB <= dlt < 100 * MIB
                    ok_all &= good
                    say(f'B3f relation {lab} vs L1M, {n} direct {key}: {rb[key][n]["direct_used"] / MIB:+.2f} vs '
                        f'{r1[key][n]["direct_used"] / MIB:+.2f} MiB, difference {dlt / MIB:+.2f} MiB -> '
                        f'{"higher by MiB to tens of MiB (yes)" if good else "NOT in [1, 100) MiB"}')
                dp = rb['peak'][n]['pool_size'] - r1['peak'][n]['pool_size']
                say(f'R2 reading {lab} vs L1M, {n} pool Size peak: {rb["peak"][n]["pool_size"] / MIB:+.2f} vs '
                    f'{r1["peak"][n]["pool_size"] / MIB:+.2f} MiB (difference {dp / MIB:+.2f})')
    say(f'analysis done; B3f direct relations all hold: {ok_all}')
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
