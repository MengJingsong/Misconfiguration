#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous
(case file B3a-B3h with audit amendments R2-R4).
usage: cluster-run.py <label> | analyze | down
  <label>  one lifetime of both nodes (B3e steps 1-7): wipe, both yaml files (B gets the label's receive-side keys), start A
           (the seed) then B (Byteman: receive-trace.btm + hold-handler.btm), wait for UN, create ks (NTS datacenter1: 2) and
           ks.t, check the rules are loaded and read the limits back from B's first acq line, settle, GC + idle histogram +
           NMT baseline on B; create the hold file (unless the label is unheld), start the samplers, run cassandra-stress
           (user profile, ops(insert=1), n=20000, cl=ONE, 200 threads, whitelist A; its own warm-up of 5,000 first),
           sample B from 2 s after the load reaches B, then every 10 s through the drain (GC.run, GC.class_histogram, nodetool info, NMT summary, tpstats, ss -tmi); after the stress,
           wait for the drain (B's inbound using_bytes from A 0, MutationStage pending 0, A's outbound pending 0), take
           the leak-check sample, remove the hold file, stop both nodes and wipe their data (logs kept).
  analyze  reads every label's readings.json of the run and writes analysis.txt: the cross-run relations of B3f/B3g/B3h.
  down     stop both nodes of this harness.
Two nodes on this host (loopback): A = 127.0.0.2 (JMX 7102), B = 127.0.0.3 (JMX 7103, measured).
Output: ~/stage4-logs/rrc/<run>/cluster/<label>/ (summary.txt with EXPECTED lines, session.log, readings.json, rrc.trace,
jmx-B.csv, vt-in.csv, vt-out.csv, jstat-B.txt, samples/, stress.log, node logs). Exit 1: a set-up or instrument check
failed (a node not UN, rules not loaded, the read-back, no hold line); both nodes are then stopped. A reading that misses
a prediction is recorded as EXPECTED ... NO and the run goes on.
Reading rules fixed before run 1 (they implement B3f's wording and do not change its numbers):
  M          median of the data handler's acq b values above the payload (512 KiB or 1 KiB) in the loaded window
  ceiling    C = Q + E (R2: "Q + reserve"; E = G in set 1); the accounted peak (max q of the data handler's SUCCESS acq
             lines) must lie in (C - M_max, C]
  retained   GC.class_histogram (live, after GC.run) bytes of org.apache.cassandra.db.Mutation + [B, minus the idle
             histogram's; the peak over the histograms taken inside the loaded window (stress launch to drain);
             k = retained / C, B3f asks
             1.2 <= k <= 3
  throttled  InboundConnection ThrottledCount (scope = A) delta over the loaded window, and its rate per second
  near zero  (set 2, Q 4 MiB) throttled delta <= 1 % of the large messages B received from A in the window
  drained    after the drain: using_bytes and using_reserve_bytes of A's row 0, live Mutation instances <= idle + 2
Environment: RRC_RUN (run folder, default run1), CASSANDRA_HOME (default ~/cassandra-run1), RRC_DATA (default
/mnt/stage4-rrc, a tmpfs), RRC_N (stress n, default 20000; a shakedown may lower it)."""
import csv, json, os, re, statistics, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-run1')
HARNESS = os.path.dirname(os.path.abspath(__file__))
RRC = os.environ.get('RRC', HOME + '/stage4-rrc')
RRC_DATA = os.environ.get('RRC_DATA', '/mnt/stage4-rrc')
RUN = os.environ.get('RRC_RUN', 'run1')
NSTRESS = int(os.environ.get('RRC_N', 20000))
KIB, MIB = 1024, 1 << 20
NODES = {'A': ('127.0.0.2', 7102), 'B': ('127.0.0.3', 7103)}
PEER_A = '/127.0.0.2:7000'
BYTEMAN = C + '/build/lib/jars/byteman-4.0.20.jar'
BM_SUBMIT = C + '/build/lib/jars/byteman-submit-4.0.20.jar'
HOLD = RRC + '/hold'
CLIENT = HARNESS + '/client.py'
SAMPLER = HARNESS + '/sample-vt.py'
JMXCP = RRC + '/jmxcls'
RULES = ['rrc acquire exit', 'rrc hold mutation verb handler', 'rrc release decrement', 'rrc release excess']

SET1 = ['internode_application_receive_queue_reserve_endpoint_capacity=16MiB',
        'internode_application_receive_queue_reserve_global_capacity=16MiB', 'internode_max_message_size=8MiB']
CTLB = ['internode_application_receive_queue_reserve_endpoint_capacity=4MiB',
        'internode_application_receive_queue_reserve_global_capacity=4MiB', 'internode_max_message_size=2MiB']
Q64K, Q32M = ['internode_application_receive_queue_capacity=64KiB'], ['internode_application_receive_queue_capacity=32MiB']


def L(yaml, Q, E, G, hold=True, prof='big', group=''):
    return {'yaml': yaml, 'Q': Q, 'E': E, 'G': G, 'hold': hold, 'prof': prof, 'group': group}


# Q = 4 MiB is the default: no key is written, the read-back shows the default reached the handler
LABELS = {
    's1q64k': L(Q64K + SET1, 64 * KIB, 16 * MIB, 16 * MIB, group='set1'),
    's1q4m-1': L(SET1, 4 * MIB, 16 * MIB, 16 * MIB, group='set1'),
    's1q4m-2': L(SET1, 4 * MIB, 16 * MIB, 16 * MIB, group='set1'),
    's1q4m-3': L(SET1, 4 * MIB, 16 * MIB, 16 * MIB, group='set1'),
    's1q32m': L(Q32M + SET1, 32 * MIB, 16 * MIB, 16 * MIB, group='set1'),
    's2q64k': L(Q64K, 64 * KIB, 128 * MIB, 512 * MIB, group='set2'),
    's2q4m': L([], 4 * MIB, 128 * MIB, 512 * MIB, group='set2'),
    's2q32m': L(Q32M, 32 * MIB, 128 * MIB, 512 * MIB, group='set2'),
    'ctla-q64k': L(Q64K + SET1, 64 * KIB, 16 * MIB, 16 * MIB, hold=False, group='ctla'),
    'ctla-q32m': L(Q32M + SET1, 32 * MIB, 16 * MIB, 16 * MIB, hold=False, group='ctla'),
    'ctlb': L(Q64K + CTLB, 64 * KIB, 4 * MIB, 4 * MIB, group='ctlb'),
    'ctlc': L(SET1, 4 * MIB, 16 * MIB, 16 * MIB, prof='small', group='ctlc'),
}
PAYLOAD = {'big': 524288, 'small': 1024}
INB = 'org.apache.cassandra.metrics:type=InboundConnection,scope=127.0.0.2_7000,name='
POOL = 'org.apache.cassandra.metrics:type=BufferPool,scope=networking,name='
MSTAGE = 'org.apache.cassandra.metrics:type=ThreadPools,path=request,scope=MutationStage,name='
TBL = 'org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=t,name='
DROP = 'org.apache.cassandra.metrics:type=DroppedMessage,scope=MUTATION_REQ,name=Dropped'
JCOLS = [('throttled_count', INB + 'ThrottledCount', 'Value'), ('throttled_nanos', INB + 'ThrottledNanos', 'Value'),
         ('received_count', INB + 'ReceivedCount', 'Value'), ('scheduled_bytes', INB + 'ScheduledBytes', 'Value'),
         ('pool_used', POOL + 'UsedSize', 'Value'), ('pool_overflow', POOL + 'OverflowSize', 'Value'),
         ('heap_used', 'java.lang:type=Memory', 'HeapMemoryUsage'),
         ('direct_used', 'java.nio:type=BufferPool,name=direct', 'MemoryUsed'),
         ('ms_pending', MSTAGE + 'PendingTasks', 'Value'), ('ms_active', MSTAGE + 'ActiveTasks', 'Value'),
         ('mt_onheap', TBL + 'AllMemtablesOnHeapDataSize', 'Value'),
         ('mt_offheap', TBL + 'AllMemtablesOffHeapDataSize', 'Value'),
         ('writes', TBL + 'WriteLatency', 'Count'), ('dropped_mutation', DROP, 'Count')]
HCLASSES = {'mutation': 'org.apache.cassandra.db.Mutation', 'bytes': '[B',
            'pupdate': 'org.apache.cassandra.db.partitions.PartitionUpdate', 'hbb': 'java.nio.HeapByteBuffer',
            'dbb': 'java.nio.DirectByteBuffer'}

args = sys.argv[1:]
if len(args) != 1 or (args[0] not in LABELS and args[0] not in ('analyze', 'down')):
    sys.exit(__doc__)
label = args[0]
ROOT = f'{HOME}/stage4-logs/rrc/{RUN}/cluster'
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
    f = f'{RRC}/{node}/cassandra.pid'
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


CHILDREN = []


def stop_all():
    for p in CHILDREN:
        try:
            if p.poll() is None:
                p.kill()
        except Exception:
            pass
    for n in ('B', 'A'):
        stop_node(n)
    if os.path.exists(HOLD):
        os.remove(HOLD)
    left = any_daemon()
    if left:
        log('WARNING: a CassandraDaemon is still running: ' + left[:300])
    return not left


def wipe_data():
    sh(f'rm -rf {RRC_DATA}/A {RRC_DATA}/B', check=False)


def fail(msg):
    note('FAIL: ' + msg)
    stop_all()
    wipe_data()
    sys.exit(1)


def start_node(node, yaml_args=(), trace=None):
    if pid_of(node) is not None:
        fail(f'{node} is already running')
    _, y = sh(f'{HARNESS}/make-node-yaml.sh {node} ' + ' '.join(f"'{a}'" for a in yaml_args),
              env=dict(os.environ, CASSANDRA_HOME=C, RRC=RRC, RRC_DATA=RRC_DATA))
    note(y.strip().splitlines()[-1][:1200])
    N = f'{RRC}/{node}'
    env = dict(os.environ, CASSANDRA_CONF=N + '/conf', CASSANDRA_LOG_DIR=N + '/logs', MAX_HEAP_SIZE='2G')
    env.pop('HEAP_NEWSIZE', None)
    if node == 'B':
        env['JVM_EXTRA_OPTS'] = (f'-javaagent:{BYTEMAN}=script:{HARNESS}/receive-trace.btm,script:{HARNESS}/hold-handler.btm,'
                                 f'listener:true -Dorg.jboss.byteman.verbose=false -Dstage4.trace={trace} '
                                 f'-Dstage4.hold.file={HOLD} -Dstage4.hold.ms=200')
    else:
        env.pop('JVM_EXTRA_OPTS', None)
    # ulimit -n is 1024 on the run node: raise it in the shell that starts the node
    sh(f'ulimit -n 100000 && bin/cassandra -p {N}/cassandra.pid > {N}/stdout.txt 2>&1', env=env)
    for _ in range(30):
        time.sleep(1)
        if pid_of(node) is not None:
            return
    fail(f'{node} did not start; see {N}/stdout.txt')


def status(via):
    _, out = sh(f'bin/nodetool -p {NODES[via][1]} status', check=False, quiet=True)
    return {m.group(2): m.group(1) for m in re.finditer(r'^([UD][NLJM])\s+(\S+)\s', out, re.M)}, out


def wait_up(via, nodes, timeout=300):
    want = {NODES[n][0] for n in nodes}
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pid_of(via) is None:
            fail(f'{via} died')
        st, out = status(via)
        _, sb = sh(f'bin/nodetool -p {NODES[via][1]} statusbinary', check=False, quiet=True)
        if re.search(r'^running\s*$', sb, re.M) and all(st.get(a) == 'UN' for a in want):
            log(f'{via} sees {sorted(nodes)} UN after {time.time() - t0:.0f} s')
            SESSION.write(out + '\n')
            return
        time.sleep(2)
    fail(f'{via}: {sorted(nodes)} not all UN in {timeout} s')


def compile_jmx():
    os.makedirs(JMXCP, exist_ok=True)
    sh(f'javac -d {JMXCP} {HARNESS}/Jmx.java')


def client(*a, timeout=300):
    rc, out = sh(f'python3 {CLIENT} ' + ' '.join(str(x) for x in a), timeout=timeout, check=False,
                 env=dict(os.environ, CASSANDRA_HOME=C))
    js = [l for l in out.splitlines() if l.startswith('{')]
    return (json.loads(js[-1]) if js else None) if rc == 0 else None


def vt_once(host, kind, path):
    sh(f'python3 {SAMPLER} {host} {kind} 1 /nonexistent {path} once', check=False, timeout=60, quiet=True,
       env=dict(os.environ, CASSANDRA_HOME=C))


def read_vt(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path) as f:
        for r in csv.DictReader(f):
            if r.get('address') in (None, 'ERROR'):
                continue
            try:
                rows.append({k: (int(v) if k != 'address' else v) for k, v in r.items()})
            except (ValueError, TypeError):
                continue
    return rows


def histogram(path):
    pid = pid_of('B')
    sh(f'jcmd {pid} GC.run', check=False, timeout=120, quiet=True)
    sh(f'jcmd {pid} GC.class_histogram > {path}', check=False, timeout=180, quiet=True)
    res = {k: (0, 0) for k in HCLASSES}
    try:
        txt = open(path).read()
        for k, cls in HCLASSES.items():
            m = re.search(r'^\s*\d+:\s+(\d+)\s+(\d+)\s+' + re.escape(cls) + r'(\s|$)', txt, re.M)
            if m:
                res[k] = (int(m.group(1)), int(m.group(2)))
    except OSError:
        pass
    return res


def thread_dump(path):
    pid = pid_of('B')
    sh(f'jcmd {pid} Thread.print > {path}', check=False, timeout=120, quiet=True)
    held = 0
    try:
        for block in open(path).read().split('\n\n'):
            # 5.0's stage threads show as SharedPool-Worker-N in a dump (shakedown 2): match the frames only
            if 'MutationVerbHandler.doVerb' in block and 'Thread.sleep' in block:
                held += 1
    except OSError:
        pass
    return held


SAMPLES = []      # (ms, kind, histogram dict, extra)


def sample_B(tag, D):
    ms = int(time.time() * 1000)
    h = histogram(f'{D}/histo-{tag}.txt')
    pid = pid_of('B')
    sh(f'bin/nodetool -p {NODES["B"][1]} info > {D}/info-{tag}.txt 2>&1', check=False, timeout=120, quiet=True)
    sh(f'jcmd {pid} VM.native_memory summary > {D}/nmt-{tag}.txt 2>&1', check=False, timeout=120, quiet=True)
    sh(f'bin/nodetool -p {NODES["B"][1]} tpstats > {D}/tpstats-{tag}.txt 2>&1', check=False, timeout=120, quiet=True)
    sh(f"ss -tmi state established '( sport = :7000 )' > {D}/ss-{tag}.txt 2>&1", check=False, timeout=30, quiet=True)
    SAMPLES.append({'ms': ms, 'ms_end': int(time.time() * 1000), 'tag': tag, 'h': h})
    log(f'sample {tag}: ' + ' '.join(f'{k}={v[0]}/{v[1]}' for k, v in h.items()))
    return h


# ---------------------------------------------------------------- trace

ID_RX = re.compile(r'^(/[\d.]+:\d+)->(/[\d.]+:\d+)-([A-Z_]+)-(\S+)$')
ACQ_RX = re.compile(r'^acq id=(\S+) b=(\d+) out=(\S+) q=(-?\d+) cap=(\d+) ep=(-?\d+)/(\d+) gl=(-?\d+)/(\d+) ms=(\d+)$')
REL_RX = re.compile(r'^rel id=(\S+) t=(\S+) b=(\d+) old=(-?\d+) cap=(\d+) ms=(\d+)$')
RELX_RX = re.compile(r'^relx id=(\S+) t=(\S+) old=(-?\d+) excess=(-?\d+) b=(\d+) ms=(\d+)$')
HOLD_RX = re.compile(r'^hold thread=(\S+) ms=(\d+)$')


def parse_trace(path):
    acq, rel, hold, other = [], [], [], 0
    pending = {}          # thread -> rel record waiting for its relx
    viol = {'relx_missing': 0, 'relx_unexpected': 0, 'excess_wrong': 0, 'relx_orphan': 0}
    nrelx = 0
    if not os.path.exists(path):
        return acq, rel, hold, other, viol, nrelx
    for l in open(path, errors='replace'):
        l = l.rstrip('\n')
        m = ACQ_RX.match(l)
        if m:
            g = m.groups()
            acq.append({'ms': int(g[9]), 'id': g[0], 'b': int(g[1]), 'out': g[2], 'q': int(g[3]), 'cap': int(g[4]),
                        'epu': int(g[5]), 'epl': int(g[6]), 'glu': int(g[7]), 'gll': int(g[8])})
            continue
        m = REL_RX.match(l)
        if m:
            g = m.groups()
            r = {'ms': int(g[5]), 'id': g[0], 't': g[1], 'b': int(g[2]), 'old': int(g[3]), 'cap': int(g[4])}
            prev = pending.pop(r['t'], None)
            if prev is not None and prev['old'] > prev['cap']:
                viol['relx_missing'] += 1
            rel.append(r)
            if r['old'] > r['cap']:
                pending[r['t']] = r
            continue
        m = RELX_RX.match(l)
        if m:
            g = m.groups()
            nrelx += 1
            t, old, ex, b = g[1], int(g[2]), int(g[3]), int(g[4])
            prev = pending.pop(t, None)
            if prev is None or prev['id'] != g[0] or prev['old'] != old:
                viol['relx_orphan'] += 1
                continue
            if not old > prev['cap']:
                viol['relx_unexpected'] += 1
            if ex != min(old - prev['cap'], b):
                viol['excess_wrong'] += 1
            prev['excess'] = ex
            continue
        m = HOLD_RX.match(l)
        if m:
            hold.append(int(m.group(2)))
            continue
        if l.strip():
            other += 1
    viol['relx_missing'] += sum(1 for r in pending.values() if r['old'] > r['cap'])
    return acq, rel, hold, other, viol, nrelx


def hid(i):
    m = ID_RX.match(i)
    return (m.group(1), m.group(3)) if m else (i, 'CQL')


def jrows(path):
    out = []
    if not os.path.exists(path):
        return out
    for l in open(path):
        p = l.strip().split(',')
        if len(p) == len(JCOLS) + 1 and p[0].isdigit():
            row = {'ms': int(p[0])}
            for (k, _, _), v in zip(JCOLS, p[1:]):
                try:
                    row[k] = float(v)
                except ValueError:
                    row[k] = None
            out.append(row)
    return out


# ---------------------------------------------------------------- one lifetime

def lifetime():
    cfg = LABELS[label]
    Q, E, G, hold, prof = cfg['Q'], cfg['E'], cfg['G'], cfg['hold'], cfg['prof']
    payload = PAYLOAD[prof]
    D = LOGS
    os.makedirs(D + '/samples', exist_ok=True)
    note(f'==== {label}: Q={Q} E={E} G={G} hold={hold} profile={prof} ({payload} B) B yaml={cfg["yaml"]} stress n={NSTRESS}')
    if any_daemon():
        fail('a CassandraDaemon is already running: ' + any_daemon()[:200])
    if subprocess.run(['mountpoint', '-q', RRC_DATA]).returncode != 0:
        fail(f'{RRC_DATA} is not mounted (sudo mount -t tmpfs -o size=80g,mode=1777 tmpfs {RRC_DATA})')
    _, df0 = sh(f'df -B1 {RRC_DATA} | tail -1', check=False)
    note('data tmpfs before: ' + df0.strip())
    sh(f'rm -rf {RRC}/A {RRC}/B', check=False)
    wipe_data()
    compile_jmx()    # always: a stale class from an earlier harness version was used once (shakedown 2)
    trace = D + '/rrc.trace'
    if os.path.exists(trace):
        os.rename(trace, trace + f'.{int(time.time())}')
    if os.path.exists(HOLD):
        os.remove(HOLD)

    # B3e step 2: start A then B
    start_node('A')
    wait_up('A', ['A'])
    start_node('B', cfg['yaml'], trace=trace)
    wait_up('B', ['A', 'B'])
    wait_up('A', ['A', 'B'])
    # step 3: schema
    js = client('schema', NODES['A'][0])
    if not js:
        fail('schema failed')
    if not client('probe', NODES['B'][0]):
        fail('probe of B failed')
    note(f'schema: {js}')
    _, sub = sh(f'java -cp {BYTEMAN}:{BM_SUBMIT} org.jboss.byteman.agent.submit.Submit -l', check=False)
    rules = sorted(set(re.findall(r'^RULE (.+)$', sub, re.M)))
    note(f'Submit -l: {rules}')
    if rules != RULES:
        fail('Byteman rules not loaded on B')
    first = None
    for _ in range(90):
        acq, *_ = parse_trace(trace)
        a_lines = [a for a in acq if hid(a['id'])[0] == PEER_A]
        if a_lines:
            first = a_lines[0]
            break
        time.sleep(1)
    if first is None:
        fail('no acq trace line of a handler from A within 90 s')
    note(f'READ-BACK first acq from A: id={first["id"]} cap={first["cap"]} ep limit={first["epl"]} gl limit={first["gll"]}')
    if not (first['cap'] == Q and first['epl'] == E and first['gll'] == G):
        fail(f'read-back mismatch: expected cap={Q} E={E} G={G}')
    expect(f'read-back: queueCapacity {first["cap"]} = {Q}, endpoint reserve {first["epl"]} = {E}, global reserve '
           f'{first["gll"]} = {G}', True)

    # baseline (idle)
    time.sleep(10)
    vt_once(NODES['B'][0], 'inbound', D + '/vt-in-before.csv')
    h_idle = sample_B('idle', D + '/samples')
    sh(f'jcmd {pid_of("B")} VM.native_memory baseline', check=False, quiet=True)

    # step 4: samplers; then the hold and the stress (step 5)
    if hold:
        open(HOLD, 'w').close()
    stop = D + '/stop'
    if os.path.exists(stop):
        os.remove(stop)
    env = dict(os.environ, CASSANDRA_HOME=C)
    pvin = subprocess.Popen(['python3', SAMPLER, NODES['B'][0], 'inbound', '0.5', stop, D + '/vt-in.csv'], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pvout = subprocess.Popen(['python3', SAMPLER, NODES['A'][0], 'outbound', '0.5', stop, D + '/vt-out.csv'], env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pj = subprocess.Popen(['java', '-cp', JMXCP, 'Jmx', str(NODES['B'][1]), 'poll', '1000', '3600', stop]
                          + [x for _, b, a in JCOLS for x in (b, a)], stdout=open(D + '/jmx-B.csv', 'w'),
                          stderr=subprocess.DEVNULL)
    pjs = subprocess.Popen(['jstat', '-gc', '-t', str(pid_of('B')), '1000'], stdout=open(D + '/jstat-B.txt', 'w'),
                           stderr=subprocess.DEVNULL)
    CHILDREN.extend([pvin, pvout, pj, pjs])
    time.sleep(3)
    stress_cmd = (f'tools/bin/cassandra-stress user profile={HARNESS}/{prof}.yaml "ops(insert=1)" n={NSTRESS} cl=ONE '
                  f'-pop seq=1..{NSTRESS * 2} -rate threads=200 -node whitelist {NODES["A"][0]} '
                  f'-port jmx={NODES["A"][1]}')
    log('+ ' + stress_cmd)
    t_s0 = int(time.time() * 1000)
    ps = subprocess.Popen(stress_cmd, shell=True, cwd=C, stdout=open(D + '/stress.log', 'w'), stderr=subprocess.STDOUT,
                          env=dict(os.environ, JVM_OPTS=''))
    CHILDREN.append(ps)
    # Load samples (fixed 2026-10-21 after shakedowns 1-2, before run 1): the stress JVM needs about 5-8 s before its
    # first write, and the n=20000 stress then lasts about 25 s, so B3d's 30 s cadence would give at most one sample in
    # it. The samples start when B's ReceivedCount from A has risen by 20 (the load is on: first sample 2 s later) and
    # then come every 10 s, through the stress and the drain (a backlog of small messages outlives the stress). The
    # MutationStage thread dump is taken first, before the first histogram's full GC.
    rc0 = None
    st = {'k': 0, 'next': None, 'held1': None}

    def maybe_sample():
        nonlocal rc0
        now = time.time() * 1000
        if st['next'] is None:
            jr = [r for r in jrows(D + '/jmx-B.csv') if r.get('received_count') is not None]
            if not jr:
                return
            if rc0 is None:
                rc0 = jr[0]['received_count']
            if jr[-1]['received_count'] - rc0 >= 20:
                st['next'] = now + 2000
                note(f'load on at {int(now)} ({(now - t_s0) / 1000:.1f} s after the stress launch)')
            return
        if now >= st['next']:
            st['k'] += 1
            if st['held1'] is None:
                st['held1'] = thread_dump(D + '/samples/threads-load1.txt')
            sample_B(f'load{st["k"]}', D + '/samples')
            st['next'] += 10000
    while ps.poll() is None:
        time.sleep(0.5)
        maybe_sample()
        if time.time() * 1000 - t_s0 > 1800 * 1000:
            ps.kill()
            note('stress killed after 1800 s')
    t_s1 = int(time.time() * 1000)
    note(f'stress exit {ps.returncode} after {(t_s1 - t_s0) / 1000:.1f} s')
    st_tail = open(D + '/stress.log', errors='replace').read()
    for pat in (r'Op rate\s*:.*', r'Partition rate\s*:.*', r'Total partitions\s*:.*', r'Total errors\s*:.*',
                r'Total operation time\s*:.*'):
        m = re.findall(pat, st_tail)
        if m:
            note('stress: ' + m[-1].strip())

    # step 6: drain
    drained = None
    t_d = time.time()
    while time.time() - t_d < 1800:
        vt_once(NODES['B'][0], 'inbound', D + '/vt-in-drain.csv')
        vt_once(NODES['A'][0], 'outbound', D + '/vt-out-drain.csv')
        rin = [r for r in read_vt(D + '/vt-in-drain.csv') if r['address'] == NODES['A'][0]]
        rout = [r for r in read_vt(D + '/vt-out-drain.csv') if r['address'] == NODES['B'][0]]
        jr = jrows(D + '/jmx-B.csv')
        if rin and rout and rin[-1]['using_bytes'] == 0 and rout[-1]['pending_bytes'] == 0 and jr and \
                (jr[-1].get('ms_pending') or 0) == 0 and (jr[-1].get('ms_active') or 0) == 0:
            drained = int(time.time() * 1000)
            break
        maybe_sample()
        time.sleep(0.5)
    held1 = st['held1']
    note(f'drained: {drained is not None} ({((drained or int(time.time() * 1000)) - t_s1) / 1000:.1f} s after the stress)')
    time.sleep(3)
    h_after = sample_B('after', D + '/samples')
    if os.path.exists(HOLD):
        os.remove(HOLD)
    vt_once(NODES['B'][0], 'inbound', D + '/vt-in-after.csv')
    vt_once(NODES['A'][0], 'outbound', D + '/vt-out-after.csv')
    open(stop, 'w').close()
    for p in (pvin, pvout, pj):
        try:
            p.wait(30)
        except subprocess.TimeoutExpired:
            p.kill()
    pjs.kill()
    sh(f'bin/nodetool -p {NODES["B"][1]} tpstats > {D}/tpstats-B-end.txt 2>&1', check=False)
    sh(f'bin/nodetool -p {NODES["A"][1]} tpstats > {D}/tpstats-A-end.txt 2>&1', check=False)
    sh(f'jcmd {pid_of("B")} VM.native_memory summary.diff > {D}/nmt-diff-end.txt 2>&1', check=False, quiet=True)
    _, df1 = sh(f'df -B1 {RRC_DATA} | tail -1', check=False)
    note('data tmpfs after: ' + df1.strip())

    # step 7: stop both, keep logs, wipe data
    stop_all()
    for n in ('A', 'B'):
        sh(f'cp {RRC}/{n}/logs/system.log {D}/{n}-system.log; cp {RRC}/{n}/logs/debug.log {D}/{n}-debug.log; '
           f'cp {RRC}/{n}/conf/cassandra.yaml {D}/{n}-cassandra.yaml; cp {RRC}/{n}/stdout.txt {D}/{n}-stdout.txt',
           check=False)
    wipe_data()
    note('both nodes stopped, data wiped: ' + (any_daemon() or 'no CassandraDaemon left'))

    analyse(cfg, payload, t_s0, t_s1, drained, h_idle, h_after, held1, first)


def analyse(cfg, payload, t_s0, t_s1, drained, h_idle, h_after, held1, first):
    D = LOGS
    Q, E, G, hold = cfg['Q'], cfg['E'], cfg['G'], cfg['hold']
    dtype = 'LARGE_MESSAGES' if payload > 65536 else 'SMALL_MESSAGES'
    acq, rel, holds, other, viol, nrelx = parse_trace(D + '/rrc.trace')
    t_end = drained or t_s1     # the loaded window: the stress launch to the drain
    win = lambda xs: [x for x in xs if t_s0 <= x['ms'] <= t_end]
    acqW = win(acq)
    data = [a for a in acqW if hid(a['id']) == (PEER_A, dtype)]
    msgs = sorted(a['b'] for a in data if a['b'] > payload)
    M_med = statistics.median(msgs) if msgs else None
    M_min, M_max = (msgs[0], msgs[-1]) if msgs else (None, None)
    succ = [a for a in data if a['out'] == 'SUCCESS']
    refusals = [a for a in data if a['out'] != 'SUCCESS']
    outs = sorted({a['out'] for a in refusals})
    peak = max([a['q'] for a in succ] + [0])
    others = [a for a in acqW if hid(a['id'])[0] == PEER_A and hid(a['id'])[1] != dtype]
    others_peak = max([a['q'] for a in others] + [0])
    others_ref = sum(1 for a in others if a['out'] != 'SUCCESS')
    viol_succ = sum(1 for a in acq if a['out'] == 'SUCCESS' and hid(a['id'])[1] != 'CQL' and a['q'] > a['cap'] + E)
    viol_gl = sum(1 for a in acq if a['glu'] > a['gll'] or a['epu'] > a['epl'])
    relA = [r for r in rel if hid(r['id'])[0] == PEER_A]
    rel_above = sum(1 for r in rel if r['old'] > r['cap'])
    rel_le = sum(1 for r in rel if r['old'] <= r['cap'])
    rel_eq = sum(1 for r in rel if r['old'] == r['cap'])
    excess_sum = sum(r.get('excess', 0) for r in relA)
    holdsW = [h for h in holds if t_s0 <= h <= t_end]
    C_pred = Q + E if E <= G else Q + G
    n_pred = int(C_pred // M_med) if M_med else None

    # JMX samples
    jr = jrows(D + '/jmx-B.csv')
    jW = [r for r in jr if t_s0 <= r['ms'] <= t_end]
    j_before = [r for r in jr if r['ms'] < t_s0]

    def delta(key, rows):
        v = [r[key] for r in rows if r.get(key) is not None]
        return (v[-1] - v[0]) if len(v) >= 2 else None
    span = (jW[-1]['ms'] - jW[0]['ms']) / 1000 if len(jW) >= 2 else None
    thr = delta('throttled_count', jW)
    thr_ns = delta('throttled_nanos', jW)
    recv = delta('received_count', jW)
    thr_rate = thr / span if thr is not None and span else None
    pool_idle = statistics.mean(r['pool_used'] for r in j_before) if j_before else 0
    pool_max = max((r['pool_used'] for r in jW if r.get('pool_used') is not None), default=None)
    heap_max = max((r['heap_used'] for r in jW if r.get('heap_used') is not None), default=None)
    ms_pend_max = max((r['ms_pending'] for r in jW if r.get('ms_pending') is not None), default=None)
    mt_on_max = max((r['mt_onheap'] for r in jW if r.get('mt_onheap') is not None), default=None)
    mt_off_max = max((r['mt_offheap'] for r in jW if r.get('mt_offheap') is not None), default=None)
    dropped = delta('dropped_mutation', jr)
    writes_B = delta('writes', jr)

    # vtable: B inbound from A, A outbound to B
    vin = [r for r in read_vt(D + '/vt-in.csv') if r['address'] == NODES['A'][0]]
    vinW = [r for r in vin if t_s0 <= r['ms'] <= t_end]
    vt_using_max = max((r['using_bytes'] for r in vinW), default=None)
    vt_reserve_max = max((r['using_reserve_bytes'] for r in vinW), default=None)
    vt_after = [r for r in read_vt(D + '/vt-in-after.csv') if r['address'] == NODES['A'][0]]
    vt_before = [r for r in read_vt(D + '/vt-in-before.csv') if r['address'] == NODES['A'][0]]
    expired = (vt_after[-1]['expired_count'] - vt_before[-1]['expired_count']) if vt_after and vt_before else None
    vout = [r for r in read_vt(D + '/vt-out-after.csv') if r['address'] == NODES['B'][0]]
    vout0 = [r for r in read_vt(D + '/vt-out.csv') if r['address'] == NODES['B'][0]]
    a_overload = (vout[-1]['overload_count'] - vout0[0]['overload_count']) if vout and vout0 else None
    a_expired = (vout[-1]['expired_count'] - vout0[0]['expired_count']) if vout and vout0 else None
    a_sent = (vout[-1]['sent_count'] - vout0[0]['sent_count']) if vout and vout0 else None
    a_pending_max = max((r['pending_bytes'] for r in vout0 if t_s0 <= r['ms'] <= t_end), default=None)

    # histograms
    def retained(h):
        return (h['mutation'][1] + h['bytes'][1]) - (h_idle['mutation'][1] + h_idle['bytes'][1])
    loadS = [s for s in SAMPLES if s['tag'].startswith('load') and s['ms'] <= t_end]
    ret = [retained(s['h']) for s in loadS]
    ret_peak = max(ret) if ret else None
    mut_live = [s['h']['mutation'][0] - h_idle['mutation'][0] for s in loadS]
    pu_live = [s['h']['pupdate'][0] - h_idle['pupdate'][0] for s in loadS]
    k_fac = ret_peak / C_pred if ret_peak is not None else None
    ret_after = retained(h_after)
    mut_after = h_after['mutation'][0] - h_idle['mutation'][0]
    # logs
    blog = open(D + '/B-system.log', errors='replace').read() if os.path.exists(D + '/B-system.log') else ''
    alog = open(D + '/A-system.log', errors='replace').read() if os.path.exists(D + '/A-system.log') else ''
    oom_B = blog.count('java.lang.OutOfMemoryError')   # not the -XX:+HeapDumpOnOutOfMemoryError JVM flag (shakedown 1)
    oom_A = alog.count('java.lang.OutOfMemoryError')
    gcw_B = len(re.findall(r'^WARN .*GCInspector', blog, re.M))
    gcw_A = len(re.findall(r'^WARN .*GCInspector', alog, re.M))
    unrec = blog.count('UnrecoverableIllegalStateException')

    R = dict(label=label, group=cfg['group'], Q=Q, E=E, G=G, hold=hold, payload=payload, t_s0=t_s0, t_s1=t_s1,
             drained=drained, stress_s=(t_s1 - t_s0) / 1000, M_med=M_med, M_min=M_min, M_max=M_max, C_pred=C_pred,
             n_pred=n_pred, peak_q=peak, peak_over_M=(peak / M_med if M_med else None), refusals=len(refusals),
             outcomes='|'.join(outs), data_acq=len(data), others_peak=others_peak, others_ref=others_ref,
             viol_succ=viol_succ, viol_limits=viol_gl, rel_lines=len(rel), rel_A=len(relA), rel_above=rel_above,
             rel_le=rel_le, rel_eq=rel_eq, relx=nrelx, viol464=viol, excess_sum_A=excess_sum, hold_lines=len(holdsW),
             held_threads=held1, throttled=thr, throttled_nanos=thr_ns, received=recv, span_s=span,
             throttled_rate=thr_rate, vt_using_max=vt_using_max, vt_reserve_max=vt_reserve_max,
             vt_after=(vt_after[-1] if vt_after else None), expired_B=expired, dropped_B=dropped, writes_B=writes_B,
             a_overload=a_overload, a_expired=a_expired, a_sent=a_sent, a_pending_max=a_pending_max,
             pool_idle=pool_idle, pool_max_above_idle=(pool_max - pool_idle if pool_max is not None else None),
             heap_max=heap_max, ms_pending_max=ms_pend_max, mt_onheap_max=mt_on_max, mt_offheap_max=mt_off_max,
             retained=ret, retained_peak=ret_peak, k=k_fac, mutation_live=mut_live, pupdate_live=pu_live,
             retained_after=ret_after, mutation_after=mut_after, idle_hist=h_idle, after_hist=h_after,
             samples=[{'tag': s['tag'], 'ms': s['ms'], 'h': s['h']} for s in SAMPLES],
             oom_B=oom_B, oom_A=oom_A, gc_warn_B=gcw_B, gc_warn_A=gcw_A, unrecoverable_B=unrec, trace_other=other)
    json.dump(R, open(D + '/readings.json', 'w'), indent=1, default=str)
    note(f'{label} readings: M median {M_med} min {M_min} max {M_max}; C = Q + E = {C_pred} (n = {n_pred}); data peak q '
         f'{peak} ({R["peak_over_M"] and round(R["peak_over_M"], 3)} M); refusals {len(refusals)} {outs}; other A handlers '
         f'peak {others_peak} refusals {others_ref}; vt using max {vt_using_max} reserve max {vt_reserve_max}; '
         f'ThrottledCount delta {thr} over {span} s (rate {thr_rate and round(thr_rate, 2)}/s), nanos {thr_ns}, received '
         f'{recv}; retained (Mutation + [B above idle) per 30-s sample {ret} peak {ret_peak} k {k_fac and round(k_fac, 3)}; '
         f'live Mutation above idle {mut_live}, PartitionUpdate {pu_live}; networking pool above idle max '
         f'{R["pool_max_above_idle"]}; heap used max {heap_max}; MutationStage pending max {ms_pend_max}; memtable '
         f'on/off heap max {mt_on_max}/{mt_off_max}; hold lines {len(holdsW)}, held threads {held1}; after drain: '
         f'retained {ret_after}, live Mutation {mut_after}, vt {R["vt_after"]}; expired B {expired}, dropped B {dropped}, '
         f'writes on B {writes_B}; A: sent {a_sent} overload {a_overload} expired {a_expired} pending max {a_pending_max}; '
         f'rel lines {len(rel)} (old > cap {rel_above}, old <= cap {rel_le}, old == cap {rel_eq}), relx {nrelx}, '
         f'line-464 violations {viol}; OOM B/A {oom_B}/{oom_A}; GC warnings B/A {gcw_B}/{gcw_A}')

    # ---- validity and rule checks (every label)
    if hold:
        expect(f'{label}: the hold fired (hold lines {len(holdsW)} > 0, MutationStage threads in doVerb sleeping at the '
               f'first load sample {held1} > 0)', len(holdsW) > 0 and (held1 or 0) > 0)
    expect(f'{label}: line 464 on the node: every release with old > cap is followed by one excess release of '
           f'min(old - cap, b), none with old <= cap ({viol}; rel {len(rel)}, old > cap {rel_above}, relx {nrelx})',
           all(v == 0 for v in viol.values()) and rel_above == nrelx)
    expect(f'{label}: every internode SUCCESS acq has q <= cap + E (violations {viol_succ}); no reserve above its limit '
           f'({viol_gl})', viol_succ == 0 and viol_gl == 0)
    va = R['vt_after']
    expect(f'{label}: drained: A\'s using_bytes {va and va["using_bytes"]} and using_reserve_bytes '
           f'{va and va["using_reserve_bytes"]} back to 0; live Mutation instances {mut_after} <= idle + 2 '
           f'(B3g row 5)', drained is not None and va is not None and va['using_bytes'] == 0
           and va['using_reserve_bytes'] == 0 and mut_after <= 2)
    expect(f'{label}: no OutOfMemoryError on B ({oom_B}) or A ({oom_A}), no UnrecoverableIllegalStateException on B '
           f'({unrec})', oom_B == 0 and oom_A == 0 and unrec == 0)

    # ---- B3f clauses per label
    g = cfg['group']
    if g in ('set1', 'ctlb'):
        expect(f'{label}: limit reached: ThrottledCount delta {thr} > 0 and refusals {len(refusals)} > 0 (R2; B3g row 4)',
               (thr or 0) > 0 and len(refusals) > 0)
        expect(f'{label}: accounted ceiling (R2, Q + reserve): data peak q {peak} in (C - M_max, C] = '
               f'({C_pred - (M_max or 0)}, {C_pred}]', M_max is not None and C_pred - M_max < peak <= C_pred)
        expect(f'{label}: node-wide accounted bytes from A (vt using_bytes max {vt_using_max}) <= 4 x Q + E '
               f'= {4 * Q + E}', vt_using_max is not None and vt_using_max <= 4 * Q + E)
    if g == 'set1':
        expect(f'{label}: retained message heap (Mutation + [B above idle) peak {ret_peak} = k x C with 1.2 <= k <= 3 '
               f'(k = {k_fac and round(k_fac, 3)})', k_fac is not None and 1.2 <= k_fac <= 3)
    if label == 's1q64k':
        expect(f'{label}: claim-wrong test: retained peak {ret_peak} not much greater than 3 x 16 MiB (line: '
               f'2 x 48 MiB = {96 * MIB})', ret_peak is not None and ret_peak <= 96 * MIB)
    if label == 's2q4m':
        near = recv is not None and thr is not None and thr <= 0.01 * max(recv, 1)
        expect(f'{label}: set 2, Q 4 MiB: throttling near zero (delta {thr} <= 1 % of {recv} received)', near)
        expect(f'{label}: set 2, Q 4 MiB: peak queued heap bounded by the workload, about 100 MiB x k (k 1.2-3): '
               f'{ret_peak} in [{int(1.2 * 100 * MIB)}, {300 * MIB}]', ret_peak is not None
               and 1.2 * 100 * MIB <= ret_peak <= 300 * MIB)
    if g == 'ctlc':
        expect(f'{label}: 1 KiB writes do not hit the limits: no refusal ({len(refusals)}), ThrottledCount delta {thr} = 0, '
               f'data peak q {peak} <= Q {Q}', len(refusals) == 0 and (thr or 0) == 0 and peak <= Q)
    if g == 'ctla':
        note(f'CONTROL (judged in analyze against the held run at the same Q): unheld data peak q {peak}, refusals '
             f'{len(refusals)}, ThrottledCount delta {thr}, retained peak {ret_peak}')
    note(f'END {label}: EXPECTED yes {EXPECT["yes"]} no {EXPECT["no"]}')


# ---------------------------------------------------------------- analyze

def analyze():
    R = {}
    for l in LABELS:
        p = f'{ROOT}/{l}/readings.json'
        if os.path.exists(p):
            R[l] = json.load(open(p))
    out = []

    def say(s):
        out.append(s); note(s)
    say(f'analyze {time.strftime("%F %T")}: labels present {sorted(R)}')
    for l, r in R.items():
        say(f'  {l}: C {r["C_pred"]} peak_q {r["peak_q"]} retained_peak {r["retained_peak"]} k {r["k"]} '
            f'throttled {r["throttled"]} rate {r["throttled_rate"]} received {r["received"]} pool_max '
            f'{r["pool_max_above_idle"]} live Mutation {r["mutation_live"]}')
    reps = [R[l] for l in ('s1q4m-1', 's1q4m-2', 's1q4m-3') if l in R]
    if len(reps) == 3:
        rp = [r['retained_peak'] for r in reps]
        pq = [r['peak_q'] for r in reps]
        tr = [r['throttled_rate'] for r in reps]
        noise_ret, noise_q, noise_tr = max(rp) - min(rp), max(pq) - min(pq), max(tr) - min(tr)
        say(f'noise (B3h(d), range of 3 repeats of set 1 Q 4 MiB): retained {rp} -> {noise_ret}; peak q {pq} -> {noise_q}; '
            f'throttled rate {tr} -> {noise_tr:.3f}')
        mid_ret, mid_tr = statistics.mean(rp), statistics.mean(tr)
        if 's1q64k' in R and 's1q32m' in R:
            a, b = R['s1q64k'], R['s1q32m']
            expect(f'B3g row 1 / B3f: retained heap rises with Q in set 1: {a["retained_peak"]} < {mid_ret:.0f} < '
                   f'{b["retained_peak"]}, and 32 MiB - 64 KiB = {b["retained_peak"] - a["retained_peak"]} > 2 x noise '
                   f'{2 * noise_ret}', a['retained_peak'] < mid_ret < b['retained_peak']
                   and b['retained_peak'] - a['retained_peak'] > 2 * noise_ret)
            expect(f'B3f: the claim-wrong clause "does not change from 64 KiB to 32 MiB" is not met: |difference| '
                   f'{abs(b["retained_peak"] - a["retained_peak"])} > 2 x noise {2 * noise_ret}',
                   abs(b['retained_peak'] - a['retained_peak']) > 2 * noise_ret)
            expect(f'B3f / B3g row 1: ThrottledCount rate falls as Q rises: {a["throttled_rate"]:.2f} > {mid_tr:.2f} > '
                   f'{b["throttled_rate"]:.2f} /s (differences > 2 x noise {2 * noise_tr:.3f})',
                   a['throttled_rate'] - mid_tr > 2 * noise_tr and mid_tr - b['throttled_rate'] > 2 * noise_tr)
            expect(f'accounted ceiling rises with Q in set 1: peak q {a["peak_q"]} < {statistics.mean(pq):.0f} < '
                   f'{b["peak_q"]} (each step > 2 x noise {2 * noise_q})', b['peak_q'] - statistics.mean(pq) > 2 * noise_q
                   and statistics.mean(pq) - a['peak_q'] > 2 * noise_q)
    for c, h in (('ctla-q64k', 's1q64k'), ('ctla-q32m', 's1q32m')):
        if c in R and h in R:
            expect(f'B3h(a): unheld {c}: data peak q {R[c]["peak_q"]} <= 10 % of the held {h} peak {R[h]["peak_q"]}, and '
                   f'ThrottledCount delta {R[c]["throttled"]} = 0', R[c]['peak_q'] <= 0.1 * R[h]['peak_q']
                   and (R[c]['throttled'] or 0) == 0)
    if 'ctlb' in R and 's1q64k' in R:
        cb, ca = R['ctlb'], R['s1q64k']
        want = cb['C_pred'] / ca['C_pred']
        got = cb['retained_peak'] / ca['retained_peak'] if ca['retained_peak'] else None
        expect(f'B3h(b): reserves 16 -> 4 MiB at Q 64 KiB: retained ratio {got and round(got, 3)} within x2 of the ceiling '
               f'ratio {want:.3f} ("drops proportionally")', got is not None and want / 2 <= got <= want * 2)
    open(ROOT + '/analysis.txt', 'w').write('\n'.join(out) + '\n')
    note(f'END analyze: EXPECTED yes {EXPECT["yes"]} no {EXPECT["no"]}')


def main():
    md5 = subprocess.run(f'cd {HARNESS} && md5sum *.btm *.py *.java *.sh *.yaml | cut -c1-12,33-', shell=True,
                         capture_output=True, text=True).stdout.replace('\n', '; ')
    note(f'cluster-run {label} {time.strftime("%F %T %z")} run {RUN}; clone {C}; harness md5 {md5}')
    if label == 'down':
        stop_all()
        note('down: ' + (any_daemon() or 'no CassandraDaemon left'))
        return
    if label == 'analyze':
        analyze()
        return
    lifetime()


try:
    main()
except SystemExit:
    raise
except BaseException as e:
    import traceback
    log(traceback.format_exc())
    fail(f'exception: {e!r}')
