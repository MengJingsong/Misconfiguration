#!/usr/bin/env python3
"""Stage 4, cluster tier, internode_application_receive_queue_capacity-acquireCapacity-queueCapacity (case 9b-9e,
amended 2026-10-14).
usage: cluster-run.py ring | <label> | down
  ring     wipe ~/stage4-rqc, start R (the Byteman agent with both rules) and S1-S4, create ks (RF 5) and ks.t.
  <label>  one lifetime of R: restart R with the label's capacity and reserves (the senders stay up), check the read-back
           (the first acq trace line names the label's capacity and reserve limits), then run the label's arms. Each arm:
           control (10 s, no writes), A (S1, one write in flight, 200 rows, no hold), B (the hold file created unless the
           arm is unheld; P writers with W writes in flight each for 30 s), drain (hold file removed, every peer's
           using_bytes back to 0), counters, TRUNCATE. Labels:
             c512k   512KiB, reserves 1MiB: B (P=1)
             c1m     1MiB, reserves 1MiB: B (P=1), nohold (P=1, no hold file); run it last (the unheld arm's
                     timed-out writes leave hints that a later arm would receive)
             c4m     4MiB, reserves 1MiB: B (P=1), p2 (S1, S2), p4 (S1-S4), small (P=1, 32,768-byte values, W=256)
             c16m    16MiB, reserves 1MiB: B (P=1)
             defres  4MiB, reserves at their defaults: B (P=1)
  down     stop every node of this harness.
Five nodes on this host: R = 127.0.0.2 (JMX 7102, the seed, the agent), S1-S4 = 127.0.0.3-.6 (JMX 7103-7106).
Writes and summary: ~/stage4-logs/rqc/<run>/<label>/ (summary.txt with EXPECTED lines, session.log, arms.csv, rqc.trace
written by R, one folder per arm). Exit 1: a set-up or instrument check failed (a node not UN, the read-back, no trace
line, a writer that could not connect); on such a failure every node is stopped. Readings that miss a prediction are
recorded as EXPECTED ... NO and the run goes on.
Environment: RQC_RUN (run folder name, default run1), RQC_B (B seconds, 30), RQC_CTRL (control seconds, 10),
RQC_ARMS (comma list to run only some arms of a label; a shakedown, not a reading)."""
import csv, json, os, re, statistics, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-run1')
HARNESS = os.path.dirname(os.path.abspath(__file__))
RQC = os.environ.get('RQC', HOME + '/stage4-rqc')
RQC_DATA = os.environ.get('RQC_DATA', '/mnt/stage4-rqc')     # node data, commit log, hints: a tmpfs (9b, corrected 2026-10-15)
RUN = os.environ.get('RQC_RUN', 'run1')
B_S = float(os.environ.get('RQC_B', 30))
CTRL_S = float(os.environ.get('RQC_CTRL', 10))
ONLY_ARMS = [a for a in os.environ.get('RQC_ARMS', '').split(',') if a]
MIB = 1 << 20
NODES = {'R': ('127.0.0.2', 7102), 'S1': ('127.0.0.3', 7103), 'S2': ('127.0.0.4', 7104), 'S3': ('127.0.0.5', 7105),
         'S4': ('127.0.0.6', 7106)}
SENDERS = ['S1', 'S2', 'S3', 'S4']
PEER = {n: f'/{a}:7010' for n, (a, _) in NODES.items()}
BYTEMAN = C + '/build/lib/jars/byteman-4.0.20.jar'
BM_SUBMIT = C + '/build/lib/jars/byteman-submit-4.0.20.jar'
HOLD = RQC + '/hold'
WRITER = HARNESS + '/write-load.py'
SAMPLER = HARNESS + '/sample-inbound.py'
LARGE, SMALL = 262144, 32768
LOW = ['internode_application_receive_queue_reserve_endpoint_capacity=1MiB',
       'internode_application_receive_queue_reserve_global_capacity=1MiB']
LABELS = {
    'c512k': (['internode_application_receive_queue_capacity=512KiB'] + LOW, 524288, MIB, MIB,
              [('B', 1, 128, LARGE, True)]),
    'c1m': (['internode_application_receive_queue_capacity=1MiB'] + LOW, MIB, MIB, MIB,
            [('B', 1, 128, LARGE, True), ('nohold', 1, 128, LARGE, False)]),
    'c4m': (['internode_application_receive_queue_capacity=4MiB'] + LOW, 4 * MIB, MIB, MIB,
            [('B', 1, 128, LARGE, True), ('p2', 2, 128, LARGE, True), ('p4', 4, 128, LARGE, True),
             ('small', 1, 256, SMALL, True)]),
    'c16m': (['internode_application_receive_queue_capacity=16MiB'] + LOW, 16 * MIB, MIB, MIB,
             [('B', 1, 128, LARGE, True)]),
    'defres': ([], 4 * MIB, 128 * MIB, 512 * MIB, [('B', 1, 128, LARGE, True)]),
}
B_TABLE = 'org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=t,name=WriteLatency'
B_DROP = 'org.apache.cassandra.metrics:type=DroppedMessage,scope=MUTATION,name=Dropped'
B_POOL = 'org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=UsedSize'
B_HEAP = 'java.lang:type=Memory'
B_DIRECT = 'java.nio:type=BufferPool,name=direct'
B_HINTS = 'org.apache.cassandra.metrics:type=Storage,name=TotalHints'

label = sys.argv[1] if len(sys.argv) > 1 else ''
if label not in LABELS and label not in ('ring', 'down'):
    sys.exit(__doc__)
LOGS = f'{HOME}/stage4-logs/rqc/{RUN}/{label}'
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
    f = f'{RQC}/{node}/cassandra.pid'
    if not os.path.exists(f):
        return None
    try:
        pid = int(open(f).read().strip())
        cmd = open(f'/proc/{pid}/cmdline').read()
        return pid if 'CassandraDaemon' in cmd else None
    except (ValueError, OSError):
        return None


def any_daemon():
    _, out = sh("ps -eo cmd | grep '[C]assandraDaemon' || true", check=False, quiet=True)
    return out.strip()


def stop_node(node):
    port = NODES[node][1]
    if pid_of(node) is None:
        return
    sh(f'bin/nodetool -p {port} stopdaemon', check=False, timeout=180)
    for _ in range(120):
        if pid_of(node) is None:
            break
        time.sleep(1)
    pid = pid_of(node)
    if pid is not None:
        log(f'{node} did not stop; kill -9 {pid}')
        subprocess.run(['kill', '-9', str(pid)])
        time.sleep(2)


def stop_all():
    for n in ('S4', 'S3', 'S2', 'S1', 'R'):
        stop_node(n)
    if os.path.exists(HOLD):
        os.remove(HOLD)
    left = any_daemon()
    if left:
        log('WARNING: a CassandraDaemon is still running: ' + left[:300])


CHILDREN = []


def fail(msg):
    note('FAIL: ' + msg)
    for p in CHILDREN:
        if p.poll() is None:
            p.kill()
    stop_all()
    sys.exit(1)


def start_node(node, yaml_args=(), trace=None):
    if pid_of(node) is not None:
        fail(f'{node} is already running')
    _, y = sh(f'{HARNESS}/make-node-yaml.sh {node} ' + ' '.join(f"'{a}'" for a in yaml_args))
    note(y.strip().splitlines()[-1][:900])
    N = f'{RQC}/{node}'
    env = dict(os.environ, CASSANDRA_CONF=N + '/conf', CASSANDRA_LOG_DIR=N + '/logs', MAX_HEAP_SIZE='2G')
    env.pop('HEAP_NEWSIZE', None)
    if node == 'R':
        env['JVM_EXTRA_OPTS'] = (f'-javaagent:{BYTEMAN}=script:{HARNESS}/receive-trace.btm,script:{HARNESS}/hold-handler.btm,'
                                 f'listener:true -Dorg.jboss.byteman.verbose=false -Dstage4.trace={trace} '
                                 f'-Dstage4.hold.file={HOLD} -Dstage4.hold.ms=200')
    else:
        env.pop('JVM_EXTRA_OPTS', None)
    n = len([f for f in os.listdir(N) if f.startswith('stdout')])
    sh(f'bin/cassandra -p {N}/cassandra.pid > {N}/stdout{n}.txt 2>&1', env=env)
    time.sleep(4)
    if pid_of(node) is None:
        fail(f'{node} did not start; see {N}/stdout{n}.txt')


def status(via):
    _, out = sh(f'bin/nodetool -p {NODES[via][1]} status', check=False, quiet=True)
    st = {}
    for m in re.finditer(r'^([UD][NLJM])\s+(\S+)\s', out, re.M):
        st[m.group(2)] = m.group(1)
    return st, out


def wait_up(via, nodes, timeout=300):
    want = {NODES[n][0]: 'UN' for n in nodes}
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pid_of(via) is None:
            fail(f'{via} died')
        st, out = status(via)
        _, sb = sh(f'bin/nodetool -p {NODES[via][1]} statusbinary', check=False, quiet=True)
        if re.search(r'^running\s*$', sb, re.M) and all(st.get(a) == s for a, s in want.items()):
            log(f'{via} sees {sorted(nodes)} UN after {time.time() - t0:.0f} s')
            SESSION.write(out + '\n')
            return
        time.sleep(2)
    fail(f'{via}: {sorted(nodes)} not all UN in {timeout} s')


def compile_jmx():
    d = RQC + '/jmxcls'
    os.makedirs(d, exist_ok=True)
    sh(f'javac -d {d} {HARNESS}/Jmx.java')


def jmx(port, *args):
    _, out = sh(f'java -cp {RQC}/jmxcls Jmx {port} ' + ' '.join(f"'{a}'" for a in args), check=False, timeout=60, quiet=True)
    SESSION.write(out[-3000:] + '\n')
    return out


def jget(port, pairs):
    out = jmx(port, 'get', *[x for p in pairs for x in p])
    res = {}
    for l in out.splitlines():
        parts = l.split('|')
        if len(parts) == 3:
            try:
                res[(parts[0], parts[1])] = int(parts[2])
            except ValueError:
                res[(parts[0], parts[1])] = parts[2]
    return res


def writer(*args, timeout=900):
    rc, out = sh(f'python3 {WRITER} ' + ' '.join(str(a) for a in args), check=False, timeout=timeout)
    js = None
    for l in out.splitlines():
        if l.startswith('{'):
            try:
                js = json.loads(l)
            except ValueError:
                pass
    return rc, js


def vt_once(path):
    sh(f'python3 {SAMPLER} {NODES["R"][0]} 1 /nonexistent {path} once', check=False, timeout=60, quiet=True)


def read_vt(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path) as f:
        for r in csv.DictReader(f):
            if r.get('address') in (None, 'ERROR'):
                continue
            try:
                rows.append({k: (int(v) if k not in ('address',) else v) for k, v in r.items()})
            except (ValueError, TypeError):
                continue
    return rows


def vt_by_peer(rows):
    """last sample's row per peer address"""
    if not rows:
        return {}
    last = max(r['ms'] for r in rows)
    return {r['address']: r for r in rows if r['ms'] == last}


def histogram(path):
    pid = pid_of('R')
    sh(f'jcmd {pid} GC.class_histogram > {path}', check=False, timeout=120, quiet=True)
    cnt, bb = None, None
    try:
        txt = open(path).read()
        m = re.search(r'^\s*\d+:\s+(\d+)\s+(\d+)\s+org\.apache\.cassandra\.db\.Mutation\s*(\(|$)', txt, re.M)
        cnt = int(m.group(1)) if m else 0
        m = re.search(r'^\s*\d+:\s+(\d+)\s+(\d+)\s+\[B\s', txt, re.M)
        bb = int(m.group(2)) if m else None
    except OSError:
        pass
    return cnt, bb


def thread_dump(path):
    pid = pid_of('R')
    sh(f'jcmd {pid} Thread.print > {path}', check=False, timeout=120, quiet=True)
    held = 0
    try:
        for block in open(path).read().split('\n\n'):
            if block.startswith('"MutationStage') and 'MutationVerbHandler.doVerb' in block and 'Thread.sleep' in block:
                held += 1
    except OSError:
        pass
    return held


# ---------------------------------------------------------------- the trace

ID_RX = re.compile(r'^(/[\d.]+:\d+)->(/[\d.]+:\d+)-([A-Z_]+)-(\S+)$')
ACQ_RX = re.compile(r'^acq id=(\S+) b=(\d+) out=(\S+) q=(-?\d+) cap=(\d+) ep=(-?\d+)/(\d+) gl=(-?\d+)/(\d+) ms=(\d+)$')
REL_RX = re.compile(r'^rel id=(\S+) b=(\d+) q=(-?\d+) ms=(\d+)$')
HOLD_RX = re.compile(r'^hold thread=(\S+) ms=(\d+)$')


class Trace:
    def __init__(self, path):
        self.path, self.pos, self.buf = path, 0, ''
        self.ev = []        # (ms, kind, id, b, out, q, cap, epu, epl, glu, gll) in file order
        self.hold = []
        self.other = []

    def poll(self):
        if not os.path.exists(self.path):
            return
        with open(self.path) as f:
            f.seek(self.pos)
            data = f.read()
            self.pos = f.tell()
        data = self.buf + data
        lines = data.split('\n')
        self.buf = lines.pop()
        for l in lines:
            m = ACQ_RX.match(l)
            if m:
                g = m.groups()
                self.ev.append((int(g[9]), 'acq', g[0], int(g[1]), g[2], int(g[3]), int(g[4]), int(g[5]), int(g[6]),
                                int(g[7]), int(g[8])))
                continue
            m = REL_RX.match(l)
            if m:
                self.ev.append((int(m.group(4)), 'rel', m.group(1), int(m.group(2)), None, int(m.group(3)),
                                None, None, None, None, None))
                continue
            m = HOLD_RX.match(l)
            if m:
                self.hold.append((int(m.group(2)), m.group(1)))
                continue
            if l.strip():
                self.other.append(l)

    def window(self, t0, t1):
        self.poll()
        return [e for e in self.ev if t0 <= e[0] <= t1]


def hid(i):
    m = ID_RX.match(i)
    return (m.group(1), m.group(3)) if m else (i, '?')


# ---------------------------------------------------------------- ring / down

def ring():
    stop_all()
    if subprocess.run(['mountpoint', '-q', RQC_DATA]).returncode != 0:
        fail(f'{RQC_DATA} is not mounted (sudo mount -t tmpfs -o size=48g,mode=1777 tmpfs {RQC_DATA})')
    sh(f'rm -rf {RQC}/R {RQC}/S1 {RQC}/S2 {RQC}/S3 {RQC}/S4 {RQC_DATA}/R {RQC_DATA}/S1 {RQC_DATA}/S2 {RQC_DATA}/S3 '
       f'{RQC_DATA}/S4', check=False)
    compile_jmx()
    start_node('R', trace=LOGS + '/rqc.trace')
    wait_up('R', ['R'])
    for s in SENDERS:
        start_node(s)
        wait_up(s, ['R', s])
    wait_up('R', list(NODES))
    for s in SENDERS:
        wait_up(s, list(NODES))
    rc, js = writer('schema', NODES['S1'][0], 5)
    if rc != 0:
        fail(f'schema failed: {js}')
    for s in SENDERS:
        rc, js = writer('probe', NODES[s][0])
        if rc != 0:
            fail(f'probe of {s} failed: {js}')
    _, st = sh(f'bin/nodetool -p {NODES["R"][1]} status', check=False)
    note('RING up: ' + ' '.join(l.split()[0] + ' ' + l.split()[1] for l in st.splitlines() if re.match(r'^[UD][NLJM]\s', l)))
    note(f'ring: schema ks RF 5; probes ok; {EXPECT}')


# ---------------------------------------------------------------- one arm

def arm(name, P, W, payload, hold, cap, E, G, tr, arm_index, rows):
    D = f'{LOGS}/{name}'
    os.makedirs(D, exist_ok=True)
    note(f'==== arm {label}/{name}: P={P} W={W} payload={payload} hold={hold} C={cap} E={E} G={G}')
    if os.path.exists(HOLD):
        os.remove(HOLD)
    peers = SENDERS[:P]
    base_pk = arm_index * 100_000_000
    rport = NODES['R'][1]
    pending = None
    for _ in range(60):
        pending = {}
        for n in NODES:
            _, ph = sh(f'bin/nodetool -p {NODES[n][1]} listpendinghints', check=False, timeout=60, quiet=True)
            rows_ph = [l for l in ph.splitlines() if re.match(r'^[0-9a-f]{8}-', l)]
            if rows_ph:
                pending[n] = rows_ph
        if not pending:
            break
        log(f'pending hints before {name}: {pending}; truncating')
        for n in pending:
            sh(f'bin/nodetool -p {NODES[n][1]} truncatehints', check=False, timeout=120)
        time.sleep(5)
    expect(f'{name}: no node holds a pending hint at the arm\'s start ({pending or "none"})', not pending)
    counters0 = jget(rport, [(B_TABLE, 'Count'), (B_DROP, 'Count')])
    snd0 = {s: jget(NODES[s][1], [(B_DROP, 'Count'), (B_HINTS, 'Count')]) for s in SENDERS}
    vt_once(D + '/vt-before.csv')
    vt0 = vt_by_peer(read_vt(D + '/vt-before.csv'))

    # control: no writes
    stop = D + '/stop-ctrl'
    t_c0 = int(time.time() * 1000)
    ps = subprocess.Popen(['python3', SAMPLER, NODES['R'][0], '0.5', stop, D + '/vt-ctrl.csv'], stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL)
    pj = subprocess.Popen(['java', '-cp', RQC + '/jmxcls', 'Jmx', str(rport), 'poll', '1000', str(int(CTRL_S) + 2), stop,
                           B_POOL, 'Value', B_HEAP, 'HeapMemoryUsage', B_DIRECT, 'MemoryUsed'],
                          stdout=open(D + '/jmx-ctrl.csv', 'w'), stderr=subprocess.DEVNULL)
    CHILDREN.extend([ps, pj])
    time.sleep(CTRL_S)
    open(stop, 'w').close()
    ps.wait(30); pj.wait(30)
    t_c1 = int(time.time() * 1000)
    idle_mut, idle_b = histogram(D + '/histo-idle.txt')
    note(f'{name} control: {t_c1 - t_c0} ms; idle Mutation instances {idle_mut}, [B bytes {idle_b}')

    # A: S1, one write in flight, 200 rows, no hold
    vt_once(D + '/vt-preA.csv')
    t_a0 = int(time.time() * 1000)
    rc, ja = writer('inflight', NODES['S1'][0], base_pk, 1, 120, payload, D + '/keys-A.csv', 200)
    t_a1 = int(time.time() * 1000)
    vt_once(D + '/vt-postA.csv')
    if ja is None:
        fail(f'writer A did not report: rc={rc}')
    note(f'{name} A: {json.dumps(ja)[:400]}')
    rows['A'] = ja.get('written', 0)
    rows['A_failed'] = ja.get('failed', 0)

    # B
    if hold:
        open(HOLD, 'w').close()
    stop = D + '/stop-B'
    ps = subprocess.Popen(['python3', SAMPLER, NODES['R'][0], '0.5', stop, D + '/vt-B.csv'], stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL)
    pj = subprocess.Popen(['java', '-cp', RQC + '/jmxcls', 'Jmx', str(rport), 'poll', '1000', '400', stop,
                           B_POOL, 'Value', B_HEAP, 'HeapMemoryUsage', B_DIRECT, 'MemoryUsed'],
                          stdout=open(D + '/jmx-B.csv', 'w'), stderr=subprocess.DEVNULL)
    CHILDREN.extend([ps, pj])
    time.sleep(1)
    t_b0 = int(time.time() * 1000)
    procs = []
    for i, s in enumerate(peers):
        p = subprocess.Popen(['python3', WRITER, 'inflight', NODES[s][0], str(base_pk + (i + 1) * 10_000_000), str(W),
                              str(B_S), str(payload), f'{D}/keys-{s}.csv'], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True)
        procs.append((s, p))
        CHILDREN.append(p)
    log(f'B writers started at {t_b0}: {peers}')
    time.sleep(B_S / 3)
    h1 = histogram(D + '/histo-b1.txt')
    held1 = thread_dump(D + '/threads-b1.txt')
    t_h1 = int(time.time() * 1000)
    time.sleep(max(0.0, t_b0 / 1000 + 2 * B_S / 3 - time.time()))
    h2 = histogram(D + '/histo-b2.txt')
    held2 = thread_dump(D + '/threads-b2.txt')
    t_h2 = int(time.time() * 1000)
    jb = {}
    for s, p in procs:
        try:
            out, _ = p.communicate(timeout=600)
        except subprocess.TimeoutExpired:
            p.kill()
            out = ''
        for l in (out or '').splitlines():
            if l.startswith('{'):
                jb[s] = json.loads(l)
        if s not in jb:
            fail(f'writer {s} did not report (rc={p.returncode})')
    t_b1 = int(time.time() * 1000)
    send_stop = max(j.get('stop_ms', t_b1) for j in jb.values())
    if os.path.exists(HOLD):
        os.remove(HOLD)
    # drain: every peer's using_bytes back to 0
    drained = None
    for _ in range(120):
        vt_once(D + '/vt-drain.csv')
        last = vt_by_peer(read_vt(D + '/vt-drain.csv'))
        if last and all(r['using_bytes'] == 0 for r in last.values()):
            drained = int(time.time() * 1000)
            break
        time.sleep(1)
    open(stop, 'w').close()
    ps.wait(30); pj.wait(30)
    time.sleep(2)
    counters1 = jget(rport, [(B_TABLE, 'Count'), (B_DROP, 'Count')])
    snd1 = {s: jget(NODES[s][1], [(B_DROP, 'Count'), (B_HINTS, 'Count')]) for s in SENDERS}
    snd_drops = sum(snd1[s].get((B_DROP, 'Count'), 0) - snd0[s].get((B_DROP, 'Count'), 0) for s in SENDERS)
    snd_hints = sum(snd1[s].get((B_HINTS, 'Count'), 0) - snd0[s].get((B_HINTS, 'Count'), 0) for s in SENDERS)
    vt_once(D + '/vt-after.csv')
    vt1 = vt_by_peer(read_vt(D + '/vt-after.csv'))
    sh(f'bin/nodetool -p {rport} tpstats > {D}/tpstats-after.txt', check=False)
    for s in jb:
        note(f'{name} B writer {s}: {json.dumps(jb[s])[:400]}')
    rows['B'] = sum(j.get('written', 0) for j in jb.values())
    rows['B_failed'] = sum(j.get('failed', 0) for j in jb.values())

    # ---------------- analysis
    tr.poll()
    evB = tr.window(t_b0, drained or t_b1)
    evA = tr.window(t_a0, t_a1)
    data_type = 'LARGE_MESSAGES' if payload == LARGE else 'SMALL_MESSAGES'
    wpeers = [PEER[s] for s in peers]
    acqB = [e for e in evB if e[1] == 'acq']
    data_acq = [e for e in acqB if hid(e[2])[1] == data_type and hid(e[2])[0] in wpeers]
    msgs = sorted(e[3] for e in data_acq if e[3] > payload)
    if not msgs:
        note(f'{name}: no data-handler acq line in B')
        return
    M_med, M_min, M_max = statistics.median(msgs), msgs[0], msgs[-1]
    succ = [e for e in data_acq if e[4] == 'SUCCESS']
    refusals = [e for e in data_acq if e[4] != 'SUCCESS']
    outs = sorted({e[4] for e in refusals})
    peak = {}
    for e in succ:
        p = hid(e[2])[0]
        peak[p] = max(peak.get(p, 0), e[5])
    other = [e for e in acqB if not (hid(e[2])[1] == data_type and hid(e[2])[0] in wpeers)]
    other_max_q = max([e[5] for e in other] + [0])
    other_ref = sum(1 for e in other if e[4] != 'SUCCESS')
    viol_succ = sum(1 for e in acqB if e[4] == 'SUCCESS' and e[5] > e[6] + E)
    viol_gl = sum(1 for e in acqB if e[9] > e[10])
    gl_cfg = [e[9] for e in acqB if e[10] == G]
    gl_max = max(gl_cfg) if gl_cfg else 0
    lease_lines = sum(1 for e in acqB if e[10] != G or e[8] != E)
    # node total rebuilt line by line
    last_q, tot_max = {}, 0
    for e in tr.window(t_b0, drained or t_b1):
        last_q[e[2]] = e[5]
        tot_max = max(tot_max, sum(last_q.values()))
    # diagnostics (no 9a row): the trace's print order is not the event order for events that overlap in time, e.g. two
    # releases of one handler on two MutationStage threads; count the pairs of consecutive rel lines of one handler, with
    # no acq of it between, whose q rises (impossible in event order), and the node total as sampled from using_bytes
    prev, disorder = {}, 0
    for e in tr.window(t_b0, drained or t_b1):
        if e[1] == 'rel' and prev.get(e[2], (None,))[0] == 'rel' and e[5] > prev[e[2]][1]:
            disorder += 1
        prev[e[2]] = (e[1], e[5])
    vtB = read_vt(D + '/vt-B.csv')
    by_ms = {}
    for r in vtB:
        by_ms[r['ms']] = by_ms.get(r['ms'], 0) + r['using_bytes']
    vt_total_max = max(by_ms.values()) if by_ms else None
    holds = [h for h in tr.hold if t_b0 <= h[0] <= (drained or t_b1)]
    thr = {}
    for s in peers:
        a, b = vt0.get(NODES[s][0]), vt1.get(NODES[s][0])
        thr[s] = (b['throttled_count'] - a['throttled_count'], b['throttled_nanos'] - a['throttled_nanos']) if a and b else (None, None)
    expired = sum(vt1[k]['expired_count'] - vt0[k]['expired_count'] for k in vt1 if k in vt0)
    writes = counters1.get((B_TABLE, 'Count'), 0) - counters0.get((B_TABLE, 'Count'), 0)
    drops = counters1.get((B_DROP, 'Count'), 0) - counters0.get((B_DROP, 'Count'), 0)
    a_ref = sum(1 for e in evA if e[1] == 'acq' and e[4] != 'SUCCESS')
    a_peak = max([e[5] for e in evA if e[1] == 'acq' and hid(e[2])[1] == data_type] + [0])
    vtA0, vtA1 = vt_by_peer(read_vt(D + '/vt-preA.csv')), vt_by_peer(read_vt(D + '/vt-postA.csv'))
    a_thr = sum(vtA1[k]['throttled_count'] - vtA0[k]['throttled_count'] for k in vtA1 if k in vtA0)

    # real resource: networking pool over B, idle from the control
    def jrows(path):
        out = []
        for l in open(path):
            parts = l.strip().split(',')
            if len(parts) == 4 and all(x.lstrip('-').isdigit() for x in parts):
                out.append([int(x) for x in parts])
        return out
    jc, jbs = jrows(D + '/jmx-ctrl.csv'), jrows(D + '/jmx-B.csv')
    idle_pool = statistics.mean(r[1] for r in jc) if jc else 0
    # the pool is read while S is capped: from the arm's first refusal (S at its plateau) to the last send; an arm with
    # no refusal (default reserves, unheld) uses the whole send window (corrected 2026-10-15 after shakedown 3)
    t_cap = min([e[0] for e in refusals] + [send_stop]) if refusals else t_b0
    inB = [r for r in jbs if t_cap <= r[0] <= send_stop]
    pool_mean = statistics.mean(r[1] for r in inB) - idle_pool if inB else None
    third = max(1, len(inB) // 3)
    pool_drift = (statistics.mean(r[1] for r in inB[-third:]) - statistics.mean(r[1] for r in inB[:third])) if len(inB) >= 3 else None
    pool_max = max(r[1] for r in inB) - idle_pool if inB else None

    n_pred = int((cap + min(E, G)) // M_med)
    n_lo, n_hi = int((cap + min(E, G)) // M_max), int((cap + min(E, G)) // M_min)
    data_peak = max(peak.values()) if peak else 0
    mut1 = h1[0] - idle_mut if h1[0] is not None and idle_mut is not None else None
    mut2 = h2[0] - idle_mut if h2[0] is not None and idle_mut is not None else None
    note(f'{name} readings: M median {M_med} min {M_min} max {M_max}; data peak q {peak} (max {data_peak}, '
         f'{data_peak / M_med:.3f} M); refusals {len(refusals)} {outs}; other handlers max q {other_max_q}, refusals '
         f'{other_ref}; global in use max {gl_max} of {G}; lease lines {lease_lines}; node total max {tot_max} (trace rebuild; '
         f'rel pairs out of event order {disorder}; sampled from using_bytes {vt_total_max}); '
         f'throttled delta {thr}; hold lines {len(holds)}; MutationStage threads held {held1}/{held2}; '
         f'Mutation instances above idle {mut1}/{mut2} ([B {h1[1]}/{h2[1]}); pool above idle mean {pool_mean} '
         f'max {pool_max} drift {pool_drift}; writes on R {writes} vs rows {rows["A"] + rows["B"]}; drops {drops}; '
         f'expired {expired}; senders: dropped MUTATION {snd_drops}, hints written {snd_hints}; '
         f'drained {drained is not None} ({(drained or 0) - send_stop} ms after the last send)')

    # validity
    if hold:
        expect(f'{name}: the hold fired (hold lines {len(holds)} > 0, MutationStage threads in doVerb sleeping at b1 '
               f'{held1} > 0)', len(holds) > 0 and held1 > 0)
    expect(f'{name}: A (one in flight, no hold) took no refusal (refusal lines {a_ref}, throttled delta {a_thr}) and '
           f'its data peak {a_peak} <= M_max {M_max}', a_ref == 0 and a_thr == 0 and a_peak <= M_max)
    # rule checks on every acq line
    expect(f'{name}: every SUCCESS line has q <= cap + E (violations {viol_succ}); global in use <= its limit on every '
           f'line (violations {viol_gl})', viol_succ == 0 and viol_gl == 0)
    # no drop (for the unheld control the same reading is a CONTROL line: no 9a row rests on it)
    nodrop = (rows['A_failed'] == 0 and rows['B_failed'] == 0 and writes == rows['A'] + rows['B'] and drops == 0
              and expired == 0 and drained is not None and snd_drops == 0 and snd_hints == 0)
    desc = (f'{name}: no write lost: writer failures A {rows["A_failed"]} B {rows["B_failed"]}, R local writes {writes} = '
            f'rows sent {rows["A"] + rows["B"]}, dropped MUTATION on R {drops}, expired {expired}, senders dropped '
            f'{snd_drops} and hinted {snd_hints}, drained {drained is not None}')
    if hold:
        expect(desc, nodrop)
    else:
        note(f'CONTROL (no 9a row): {desc} — {"yes" if nodrop else "no"}')
    low = E == MIB and G == MIB
    res = {'arm': f'{label}/{name}', 'P': P, 'W': W, 'payload': payload, 'C': cap, 'E': E, 'G': G, 'M_med': M_med,
           'M_min': M_min, 'M_max': M_max, 'n_pred': n_pred, 'data_peak': data_peak, 'peak_over_M': round(data_peak / M_med, 3),
           'refusals': len(refusals), 'outcomes': '|'.join(outs), 'gl_max': gl_max, 'node_total_max': tot_max,
           'rel_disorder': disorder, 'vt_total_max': vt_total_max,
           'other_max_q': other_max_q, 'held_b1': held1, 'held_b2': held2, 'mut_b1': mut1, 'mut_b2': mut2,
           'pool_mean': pool_mean, 'pool_max': pool_max, 'pool_drift': pool_drift, 'writes_R': writes,
           'rows': rows['A'] + rows['B'], 'drops': drops, 'expired': expired, 'snd_drops': snd_drops, 'snd_hints': snd_hints,
           'throttled': ';'.join(f'{s}:{thr[s][0]}' for s in peers), 'throttled_nanos': ';'.join(f'{s}:{thr[s][1]}' for s in peers),
           't_b0': t_b0, 't_cap': t_cap, 'send_stop': send_stop, 'drained': drained, 't_h1': t_h1, 't_h2': t_h2}

    if low and P == 1 and hold:
        expect(f'{name}: n = floor((C + 1 MiB)/M) is the same for M_min and M_max ({n_lo}, {n_hi}); predicted {n_pred}',
               n_lo == n_hi == n_pred)
        expect(f'{name}: data-handler peak q {data_peak} in (C + E - M_max, C + E] = ({cap + E - M_max}, {cap + E}] and '
               f'= n·M: {data_peak / M_med:.3f} rounds to {n_pred}',
               cap + E - M_max < data_peak <= cap + E and round(data_peak / M_med) == n_pred)
        expect(f'{name}: refusals {len(refusals)} > 0, all INSUFFICIENT_GLOBAL ({outs}); throttled count and nanos rose '
               f'{thr}', len(refusals) > 0 and outs == ['INSUFFICIENT_GLOBAL']
               and all((thr[s][0] or 0) > 0 and (thr[s][1] or 0) > 0 for s in peers))
        expect(f'{name}: the other handlers stay at or below C (max q {other_max_q}) and take no refusal ({other_ref})',
               other_max_q <= cap and other_ref == 0)
        if payload == LARGE:
            exp_mut = min(n_pred, 32)
            expect(f'{name}: live Mutation instances above idle {mut1}, {mut2} within -3/+2 of min(n, 32) = {exp_mut}, '
                   f'and within 3 of each other', mut1 is not None and mut2 is not None
                   and exp_mut - 3 <= mut1 <= exp_mut + 2 and exp_mut - 3 <= mut2 <= exp_mut + 2 and abs(mut1 - mut2) <= 3)
            if n_pred > 32:
                fr = (n_pred - 32) * M_med
                expect(f'{name}: networking pool in use above idle, mean over B {pool_mean} within x2 of (n - 32)·M = {fr:.0f}',
                       pool_mean is not None and fr / 2 <= pool_mean <= 2 * fr)
            else:
                expect(f'{name}: networking pool in use above idle, mean over B {pool_mean} below 2 MiB',
                       pool_mean is not None and pool_mean < 2 * MIB)
            expect(f'{name}: networking pool flat over B (last third - first third {pool_drift} < M {M_med})',
                   pool_drift is not None and pool_drift < M_med)
        else:
            expect(f'{name}: live Mutation instances above idle {mut1}, {mut2} within -4/+2 of n_s = {n_pred}, and within 3 '
                   f'of each other', mut1 is not None and mut2 is not None and n_pred - 4 <= mut1 <= n_pred + 2
                   and n_pred - 4 <= mut2 <= n_pred + 2 and abs(mut1 - mut2) <= 3)
    if low and P > 1:
        floor_c = int(cap // M_min) * M_min
        ok_each = all(floor_c <= peak.get(PEER[s], 0) <= cap + E for s in peers)
        expect(f'{name}: each writing peer peaks in [floor(C/M)·M, C + E] = [{floor_c}, {cap + E}]: '
               f'{ {s: peak.get(PEER[s]) for s in peers} }', ok_each)
        expect(f'{name}: global reserve in use peaks in (G - M_max, G] = ({G - M_max}, {G}]: {gl_max}', G - M_max < gl_max <= G)
        expect(f'{name}: the node total never exceeds P·C + G + 64 KiB = {P * cap + G + 65536}: {tot_max}; sum of peer '
               f'peaks {sum(peak.get(PEER[s], 0) for s in peers)} >= P·floor(C/M)·M = {P * floor_c}',
               tot_max <= P * cap + G + 65536 and sum(peak.get(PEER[s], 0) for s in peers) >= P * floor_c)
        expect(f'{name}: refusals {len(refusals)} > 0 and every writing peer throttled {thr}',
               len(refusals) > 0 and all((thr[s][0] or 0) > 0 for s in peers))
    if not low:
        expect(f'{name}: default reserves: no refusal ({len(refusals)}), throttled delta 0 {thr}, data peak {data_peak} in '
               f'(C + 1 MiB, W·M_max] = ({cap + MIB}, {W * M_max}]',
               len(refusals) == 0 and all(thr[s][0] == 0 for s in peers) and cap + MIB < data_peak <= W * M_max)
    with open(LOGS + '/arms.csv', 'a', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(res))
        if f.tell() == 0:
            w.writeheader()
        w.writerow(res)
    # reset for the next arm: hints first (a hint replayed later would add writes to R), then the table
    for n in NODES:
        sh(f'bin/nodetool -p {NODES[n][1]} truncatehints', check=False, timeout=120)
    rc, jt = writer('truncate', NODES['S1'][0])
    note(f'{name}: truncate {"ok" if rc == 0 else "FAILED " + str(jt)}')


# ---------------------------------------------------------------- main

def main():
    note(f'cluster-run {label} {time.strftime("%F %T %z")} run {RUN}; harness md5 '
         + subprocess.run(f'cd {HARNESS} && md5sum *.btm *.py *.java *.sh | cut -c1-12,33-', shell=True,
                          capture_output=True, text=True).stdout.replace('\n', '; '))
    if label == 'down':
        stop_all()
        note('down: ' + (any_daemon() or 'no CassandraDaemon left'))
        _, df = sh(f'df -h {RQC_DATA} | tail -1', check=False)
        note('data tmpfs: ' + df.strip())
        return
    if label == 'ring':
        ring()
        return
    yaml_args, cap, E, G, arms = LABELS[label]
    for s in SENDERS:
        if pid_of(s) is None:
            fail(f'{s} is not running; run `cluster-run.py ring` first')
    if not os.path.isdir(RQC + '/jmxcls'):
        compile_jmx()
    trace = LOGS + '/rqc.trace'
    if os.path.exists(trace):
        os.rename(trace, trace + f'.{int(time.time())}')
    stop_node('R')
    start_node('R', yaml_args, trace=trace)
    wait_up('R', list(NODES))
    for s in SENDERS:
        wait_up(s, list(NODES))
    _, sub = sh(f'java -cp {BYTEMAN}:{BM_SUBMIT} org.jboss.byteman.agent.submit.Submit -l', check=False)
    rules = re.findall(r'^RULE (.+)$', sub, re.M)
    note(f'Submit -l: {len(rules)} rules: {rules}')
    if sorted(rules) != ['rqc acquire exit', 'rqc hold mutation verb handler', 'rqc release decrement']:
        fail('Byteman rules not loaded on R')
    tr = Trace(trace)
    first = None
    for _ in range(90):
        tr.poll()
        cfg = [e for e in tr.ev if e[1] == 'acq']
        if cfg:
            first = cfg[0]
            break
        time.sleep(1)
    if first is None:
        fail('no acq trace line within 90 s of R starting')
    note(f'READ-BACK first acq: id={first[2]} cap={first[6]} ep limit={first[8]} gl limit={first[10]}')
    if not (first[6] == cap and first[8] == E and first[10] == G):
        fail(f'read-back mismatch: expected cap={cap} E={E} G={G}')
    expect(f'read-back: queueCapacity {first[6]} = {cap}, endpoint reserve {first[8]} = {E}, global reserve {first[10]} = {G}',
           True)
    for i, (name, P, W, payload, hold) in enumerate(arms):
        if ONLY_ARMS and name not in ONLY_ARMS:
            continue
        rows = {}
        arm(name, P, W, payload, hold, cap, E, G, tr, list(LABELS).index(label) * 10 + i + 1, rows)
    tr.poll()
    note(f'trace: {len(tr.ev)} acq/rel lines, {len(tr.hold)} hold lines, {len(tr.other)} other lines '
         f'(first: {tr.other[:2]})')
    note(f'END {label}: EXPECTED yes {EXPECT["yes"]} no {EXPECT["no"]}; R left running with this label; senders up')


try:
    main()
except SystemExit:
    raise
except BaseException as e:
    import traceback
    log(traceback.format_exc())
    fail(f'exception: {e!r}')
