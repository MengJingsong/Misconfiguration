#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of internode_application_receive_queue_reserve_global_capacity-acquireCapacity-actualExcess--autonomous
(case file B3a-B3h with audit amendments R4-R10).
usage: cluster-run.py <label> | analyze | down
  <label>  one lifetime of both nodes (B3e steps 1-4): wipe, both yaml files (A, the target, gets the label's keys), start A (the
           seed; Byteman receive-trace.btm + hold-handler.btm) then B (the sender), wait for UN, create ks (NTS datacenter1: 2) and
           ks.t, check the rules are loaded and read the limits back from A's first acq line from B, settle, GC + idle histogram + NMT
           baseline on A; create the hold file (not for `base`), start the samplers, run cassandra-stress against B
           (user profile, ops(insert=1), cl=ALL, 192 threads, no-warmup, duration=RSV_DURATION s (120)), sample A from 2 s after the
           load reaches A and then every 10 s (GC.run, GC.class_histogram, nodetool info, NMT summary, tpstats, ss -tmi); after the
           stress wait for the drain (A's inbound using_bytes from B 0, MutationStage pending 0, B's outbound pending 0), take the
           leak-check sample, remove the hold file, stop both nodes, wipe their data (logs kept). `base` runs no stress: it samples A
           every 10 s for RSV_DURATION s with the same instruments (the heap-noise baseline, B3h).
  analyze  reads every label's readings.json of the run and writes analysis.txt: the cross-run relations of B3f/B3g/B3h (R8).
  down     stop both nodes of this harness.
Two nodes on this host (loopback): A = 127.0.0.2 (JMX 7102, the target, measured), B = 127.0.0.3 (JMX 7103, the sender).
Output: ~/stage4-logs/rsv/<run>/cluster/<label>/ (summary.txt with EXPECTED lines, session.log, readings.json, rsv.trace, jmx-A.csv,
vt-in.csv, vt-out.csv, jstat-A.txt, samples/, stress.log, node logs). Exit 1: a set-up or instrument check failed; both nodes are
then stopped. A reading that misses a prediction is recorded as EXPECTED ... NO and the run goes on.
Reading rules (fixed before run 1; they implement B3f and amendment R8):
  C          ceiling Q + min(E, G) of the sender's large-message handler's accounted bytes
  acc        the largest queueSize after a SUCCESS acquire of that handler (peak in the loaded window)
  H          peak, over the histograms of the loaded window (GC.run first), of live Mutation + [B bytes above the idle histogram's
  P          peak networking BufferPool UsedSize (JMX, 1 s) in the loaded window above its mean before the load
  M          H + P
  throttled  InboundConnection ThrottledCount (scope 127.0.0.3_7000) delta over the loaded window; received = ReceivedCount delta
  never > G  every trace line with the configured limits (limit == E / G): using <= limit, and the vtable's using_reserve_bytes <= G
  drained    after the drain: vtable using_bytes and using_reserve_bytes 0 and the last trace line's ep/gl using 0
Environment: RSV_RUN (run folder, default run1), CASSANDRA_HOME (default ~/cassandra-rsv), RSV_DATA (default /mnt/stage4-rsv, a
tmpfs), RSV_DURATION (stress duration s, default 120), RSV_THREADS (default 192)."""
import csv, json, os, re, statistics, subprocess, sys, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-rsv')
HARNESS = os.path.dirname(os.path.abspath(__file__))
RSV = os.environ.get('RSV', HOME + '/stage4-rsv')
RSV_DATA = os.environ.get('RSV_DATA', '/mnt/stage4-rsv')
RUN = os.environ.get('RSV_RUN', 'run1')
DURATION = int(os.environ.get('RSV_DURATION', 120))
THREADS = int(os.environ.get('RSV_THREADS', 192))
KIB, MIB = 1024, 1 << 20
NODES = {'A': ('127.0.0.2', 7102), 'B': ('127.0.0.3', 7103)}
PEER_B = '/127.0.0.3:7000'
BYTEMAN = C + '/build/lib/jars/byteman-4.0.20.jar'
BM_SUBMIT = C + '/build/lib/jars/byteman-submit-4.0.20.jar'
HOLD = RSV + '/hold'
CLIENT = HARNESS + '/client.py'
SAMPLER = HARNESS + '/sample-vt.py'
JMXCP = RSV + '/jmxcls'
RULES = ['rsv acquire exit', 'rsv hold mutation verb handler', 'rsv release exit']
PAYLOAD = 262144


def ykeys(Q, E, G):
    k = []
    if Q != 4 * MIB:
        k.append(f'internode_application_receive_queue_capacity={Q // MIB}MiB')
    k.append(f'internode_application_receive_queue_reserve_endpoint_capacity={E // MIB}MiB')
    k.append(f'internode_application_receive_queue_reserve_global_capacity={G // MIB}MiB')
    return k


def L(Q, E, G, stress=True):
    return {'yaml': ykeys(Q, E, G), 'Q': Q, 'E': E, 'G': G, 'stress': stress}


LABELS = {
    'g4': L(1 * MIB, 4 * MIB, 4 * MIB),
    'g32': L(1 * MIB, 32 * MIB, 32 * MIB),
    'g512': L(1 * MIB, 512 * MIB, 512 * MIB),
    'ctlq16': L(16 * MIB, 4 * MIB, 4 * MIB),
    'base': L(1 * MIB, 4 * MIB, 4 * MIB, stress=False),
}
INB = 'org.apache.cassandra.metrics:type=InboundConnection,scope=127.0.0.3_7000,name='
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
ROOT = f'{HOME}/stage4-logs/rsv/{RUN}/cluster'
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
    note(f'EXPECTED: {desc} - {"yes" if cond else "NO (recorded; the AI judges it in the results file)"}')
    return cond


def pid_of(node):
    f = f'{RSV}/{node}/cassandra.pid'
    try:
        pid = int(open(f).read().strip())
        return pid if 'CassandraDaemon' in open(f'/proc/{pid}/cmdline').read() else None
    except (ValueError, OSError):
        return None


def any_daemon():
    # match only java processes whose arguments name CassandraDaemon (a shell's own grep pattern can match, HANDOFF lesson)
    return sh("ps -eo pid,comm,args | awk '$2==\"java\" && /CassandraDaemon/ {print $1\" \"substr($0,1,160)}'", check=False,
              quiet=True)[1].strip()


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
    sh(f'rm -rf {RSV_DATA}/A {RSV_DATA}/B', check=False)


def fail(msg):
    note('FAIL: ' + msg)
    stop_all()
    wipe_data()
    sys.exit(1)


def start_node(node, yaml_args=(), trace=None):
    if pid_of(node) is not None:
        fail(f'{node} is already running')
    _, y = sh(f'{HARNESS}/make-node-yaml.sh {node} ' + ' '.join(f"'{a}'" for a in yaml_args),
              env=dict(os.environ, CASSANDRA_HOME=C, RSV=RSV, RSV_DATA=RSV_DATA))
    note(y.strip().splitlines()[-1][:1200])
    N = f'{RSV}/{node}'
    env = dict(os.environ, CASSANDRA_CONF=N + '/conf', CASSANDRA_LOG_DIR=N + '/logs',
               MAX_HEAP_SIZE='1G' if node == 'A' else '2G')
    env.pop('HEAP_NEWSIZE', None)
    if node == 'A':
        env['JVM_EXTRA_OPTS'] = (f'-javaagent:{BYTEMAN}=script:{HARNESS}/receive-trace.btm,script:{HARNESS}/hold-handler.btm,'
                                 f'listener:true -Dorg.jboss.byteman.verbose=false -Dstage4.trace={trace} '
                                 f'-Dstage4.hold.file={HOLD} -Dstage4.hold.ms=20')
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
    pid = pid_of('A')
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
    pid = pid_of('A')
    sh(f'jcmd {pid} Thread.print > {path}', check=False, timeout=120, quiet=True)
    held = 0
    try:
        for block in open(path).read().split('\n\n'):
            if 'MutationVerbHandler.doVerb' in block and 'Thread.sleep' in block:
                held += 1
    except OSError:
        pass
    return held


SAMPLES = []      # (ms, histogram dict)


def sample_A(tag, D):
    ms = int(time.time() * 1000)
    h = histogram(f'{D}/histo-{tag}.txt')
    pid = pid_of('A')
    sh(f'bin/nodetool -p {NODES["A"][1]} info > {D}/info-{tag}.txt 2>&1', check=False, timeout=120, quiet=True)
    sh(f'jcmd {pid} VM.native_memory summary > {D}/nmt-{tag}.txt 2>&1', check=False, timeout=120, quiet=True)
    sh(f'bin/nodetool -p {NODES["A"][1]} tpstats > {D}/tpstats-{tag}.txt 2>&1', check=False, timeout=120, quiet=True)
    sh(f"ss -tmi state established '( sport = :7000 )' > {D}/ss-{tag}.txt 2>&1", check=False, timeout=30, quiet=True)
    SAMPLES.append({'ms': ms, 'ms_end': int(time.time() * 1000), 'tag': tag, 'h': h})
    log(f'sample {tag}: ' + ' '.join(f'{k}={v[0]}/{v[1]}' for k, v in h.items()))
    return h


# ---------------------------------------------------------------- trace

ID_RX = re.compile(r'^(/[\d.]+:\d+)->(/[\d.]+:\d+)-([A-Z_]+)-(\S+)$')
ACQ_RX = re.compile(r'^acq id=(\S+) b=(\d+) out=(\S+) q=(-?\d+) cap=(\d+) ep=(-?\d+)/(\d+) gl=(-?\d+)/(\d+) ms=(\d+)$')
REL_RX = re.compile(r'^rel id=(\S+) b=(\d+) q=(-?\d+) ep=(-?\d+)/(\d+) gl=(-?\d+)/(\d+) ms=(\d+)$')
HOLD_RX = re.compile(r'^hold thread=(\S+) ms=(\d+)$')


def parse_trace(path):
    acq, rel, hold, other = [], [], [], 0
    if not os.path.exists(path):
        return acq, rel, hold, other
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
            rel.append({'ms': int(g[7]), 'id': g[0], 'b': int(g[1]), 'q': int(g[2]), 'epu': int(g[3]), 'epl': int(g[4]),
                        'glu': int(g[5]), 'gll': int(g[6])})
            continue
        m = HOLD_RX.match(l)
        if m:
            hold.append(int(m.group(2)))
            continue
        if l.strip():
            other += 1
    return acq, rel, hold, other


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
    Q, E, G, stress = cfg['Q'], cfg['E'], cfg['G'], cfg['stress']
    D = LOGS
    os.makedirs(D + '/samples', exist_ok=True)
    note(f'==== {label}: Q={Q} E={E} G={G} stress={stress} ({PAYLOAD} B, {THREADS} threads, {DURATION} s, cl=ALL) A yaml={cfg["yaml"]}')
    if any_daemon():
        fail('a CassandraDaemon is already running: ' + any_daemon()[:200])
    if subprocess.run(['mountpoint', '-q', RSV_DATA]).returncode != 0:
        fail(f'{RSV_DATA} is not mounted (sudo mount -t tmpfs -o size=80g,mode=1777 tmpfs {RSV_DATA})')
    _, df0 = sh(f'df -B1 {RSV_DATA} | tail -1', check=False)
    note('data tmpfs before: ' + df0.strip())
    sh(f'rm -rf {RSV}/A {RSV}/B', check=False)
    wipe_data()
    compile_jmx()
    trace = D + '/rsv.trace'
    if os.path.exists(trace):
        os.rename(trace, trace + f'.{int(time.time())}')
    if os.path.exists(HOLD):
        os.remove(HOLD)

    # B3e step 2: start A (target, seed) then B (sender)
    start_node('A', cfg['yaml'], trace=trace)
    wait_up('A', ['A'])
    start_node('B')
    wait_up('A', ['A', 'B'])
    wait_up('B', ['A', 'B'])
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
        fail('Byteman rules not loaded on A')
    first = None
    for _ in range(90):
        acq, *_ = parse_trace(trace)
        a_lines = [a for a in acq if hid(a['id'])[0] == PEER_B and a['epl'] == cfg['E'] and a['gll'] == cfg['G']]
        any_lines = [a for a in acq if hid(a['id'])[0] == PEER_B]
        if any_lines:
            first = any_lines[0]
            break
        time.sleep(1)
    if first is None:
        fail('no acq trace line of a handler from B within 90 s')
    note(f'READ-BACK first acq from B: id={first["id"]} cap={first["cap"]} ep limit={first["epl"]} gl limit={first["gll"]}')
    if not (first['cap'] == Q and first['epl'] == E and first['gll'] == G):
        fail(f'read-back mismatch: expected cap={Q} E={E} G={G}')
    expect(f'read-back: queueCapacity {first["cap"]} = {Q}, endpoint reserve {first["epl"]} = {E}, global reserve {first["gll"]} = {G}', True)

    # baseline (idle)
    time.sleep(10)
    vt_once(NODES['A'][0], 'inbound', D + '/vt-in-before.csv')
    h_idle = sample_A('idle', D + '/samples')
    sh(f'jcmd {pid_of("A")} VM.native_memory baseline', check=False, quiet=True)

    # step 4: samplers; then the hold and the stress (step 5)
    if stress:
        open(HOLD, 'w').close()
    stopf = D + '/stop'
    if os.path.exists(stopf):
        os.remove(stopf)
    env = dict(os.environ, CASSANDRA_HOME=C)
    pvin = subprocess.Popen(['python3', SAMPLER, NODES['A'][0], 'inbound', '0.5', stopf, D + '/vt-in.csv'], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pvout = subprocess.Popen(['python3', SAMPLER, NODES['B'][0], 'outbound', '0.5', stopf, D + '/vt-out.csv'], env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pj = subprocess.Popen(['java', '-cp', JMXCP, 'Jmx', str(NODES['A'][1]), 'poll', '1000', '3600', stopf]
                          + [x for _, b, a in JCOLS for x in (b, a)], stdout=open(D + '/jmx-A.csv', 'w'),
                          stderr=subprocess.DEVNULL)
    pjs = subprocess.Popen(['jstat', '-gc', '-t', str(pid_of('A')), '1000'], stdout=open(D + '/jstat-A.txt', 'w'),
                           stderr=subprocess.DEVNULL)
    CHILDREN.extend([pvin, pvout, pj, pjs])
    time.sleep(3)
    t_s0 = int(time.time() * 1000)
    ps = None
    if stress:
        stress_cmd = (f'tools/bin/cassandra-stress user profile={HARNESS}/big.yaml "ops(insert=1)" duration={DURATION}s cl=ALL '
                      f'no-warmup -pop seq=1..100000000 -rate threads={THREADS} -node whitelist {NODES["B"][0]} '
                      f'-port jmx={NODES["B"][1]}')
        log('+ ' + stress_cmd)
        ps = subprocess.Popen(stress_cmd, shell=True, cwd=C, stdout=open(D + '/stress.log', 'w'), stderr=subprocess.STDOUT,
                              env=dict(os.environ, JVM_OPTS=''))
        CHILDREN.append(ps)
    # samples start when A's ReceivedCount from B has risen by 20 (the load is on; first sample 2 s later), then every 10 s
    rc0 = None
    st = {'k': 0, 'next': None, 'held1': None}

    def maybe_sample():
        nonlocal rc0
        now = time.time() * 1000
        if st['next'] is None:
            if not stress:
                st['next'] = now + 2000
                return
            jr = [r for r in jrows(D + '/jmx-A.csv') if r.get('received_count') is not None]
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
            if stress and st['held1'] is None:
                st['held1'] = thread_dump(D + '/samples/threads-load1.txt')
            sample_A(f'load{st["k"]}', D + '/samples')
            st['next'] += 10000
    if stress:
        while ps.poll() is None:
            time.sleep(0.5)
            maybe_sample()
            if time.time() * 1000 - t_s0 > (DURATION + 600) * 1000:
                ps.kill()
                note('stress killed after duration + 600 s')
    else:
        while time.time() * 1000 - t_s0 < DURATION * 1000:
            time.sleep(0.5)
            maybe_sample()
    t_s1 = int(time.time() * 1000)
    if stress:
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
    while time.time() - t_d < 900:
        vt_once(NODES['A'][0], 'inbound', D + '/vt-in-drain.csv')
        vt_once(NODES['B'][0], 'outbound', D + '/vt-out-drain.csv')
        rin = [r for r in read_vt(D + '/vt-in-drain.csv') if r['address'] == NODES['B'][0]]
        rout = [r for r in read_vt(D + '/vt-out-drain.csv') if r['address'] == NODES['A'][0]]
        jr = jrows(D + '/jmx-A.csv')
        if rin and rout and rin[-1]['using_bytes'] == 0 and rout[-1]['pending_bytes'] == 0 and jr and \
                (jr[-1].get('ms_pending') or 0) == 0 and (jr[-1].get('ms_active') or 0) == 0:
            drained = int(time.time() * 1000)
            break
        maybe_sample()
        time.sleep(0.5)
    held1 = st['held1']
    note(f'drained: {drained is not None} ({((drained or int(time.time() * 1000)) - t_s1) / 1000:.1f} s after the stress)')
    time.sleep(3)
    h_after = sample_A('after', D + '/samples')
    if os.path.exists(HOLD):
        os.remove(HOLD)
    vt_once(NODES['A'][0], 'inbound', D + '/vt-in-after.csv')
    vt_once(NODES['B'][0], 'outbound', D + '/vt-out-after.csv')
    open(stopf, 'w').close()
    for p in (pvin, pvout, pj):
        try:
            p.wait(30)
        except subprocess.TimeoutExpired:
            p.kill()
    pjs.kill()
    sh(f'bin/nodetool -p {NODES["A"][1]} tpstats > {D}/tpstats-A-end.txt 2>&1', check=False)
    sh(f'bin/nodetool -p {NODES["B"][1]} tpstats > {D}/tpstats-B-end.txt 2>&1', check=False)
    sh(f'jcmd {pid_of("A")} VM.native_memory summary.diff > {D}/nmt-diff-end.txt 2>&1', check=False, quiet=True)
    _, df1 = sh(f'df -B1 {RSV_DATA} | tail -1', check=False)
    note('data tmpfs after: ' + df1.strip())

    # step 7: stop both, keep logs, wipe data
    stop_all()
    for n in ('A', 'B'):
        sh(f'cp {RSV}/{n}/logs/system.log {D}/{n}-system.log; cp {RSV}/{n}/logs/debug.log {D}/{n}-debug.log; '
           f'cp {RSV}/{n}/conf/cassandra.yaml {D}/{n}-cassandra.yaml; cp {RSV}/{n}/stdout.txt {D}/{n}-stdout.txt', check=False)
    wipe_data()
    note('both nodes stopped, data wiped: ' + (any_daemon() or 'no CassandraDaemon left'))
    analyse(cfg, t_s0, t_s1, drained, h_idle, h_after, held1)


def analyse(cfg, t_s0, t_s1, drained, h_idle, h_after, held1):
    D = LOGS
    Q, E, G, stress = cfg['Q'], cfg['E'], cfg['G'], cfg['stress']
    acq, rel, holds, other = parse_trace(D + '/rsv.trace')
    t_end = drained or t_s1
    win = lambda xs: [x for x in xs if t_s0 <= x['ms'] <= t_end]
    acqW = win(acq)
    data = [a for a in acqW if hid(a['id']) == (PEER_B, 'LARGE_MESSAGES')]
    msgs = sorted(a['b'] for a in data if a['b'] > PAYLOAD)
    M_med = statistics.median(msgs) if msgs else None
    M_max = msgs[-1] if msgs else None
    succ = [a for a in data if a['out'] == 'SUCCESS']
    refusals = [a for a in data if a['out'] != 'SUCCESS']
    outs = {}
    for a in refusals:
        outs[a['out']] = outs.get(a['out'], 0) + 1
    acc = max([a['q'] for a in succ] + [0])
    C_pred = Q + min(E, G)
    # the configured limits only (a reactivation passes a Basic lease with another limit)
    cfgd = [x for x in acq + rel if x['epl'] == E and x['gll'] == G]
    over_ep = sum(1 for x in cfgd if x['epu'] > E)
    over_gl = sum(1 for x in cfgd if x['glu'] > G)
    max_ep = max([x['epu'] for x in cfgd] + [0])
    max_gl = max([x['glu'] for x in cfgd] + [0])
    viol_succ = sum(1 for a in acq if a['out'] == 'SUCCESS' and hid(a['id'])[1] != 'CQL' and a['q'] > a['cap'] + min(E, G))
    last_line = max(acq + rel, key=lambda x: x['ms']) if (acq or rel) else None
    last_cfg = max(cfgd, key=lambda x: x['ms']) if cfgd else None
    holdsW = [h for h in holds if t_s0 <= h <= t_end]

    jr = jrows(D + '/jmx-A.csv')
    jW = [r for r in jr if t_s0 <= r['ms'] <= t_end]
    j_before = [r for r in jr if r['ms'] < t_s0]

    def delta(key, rows):
        v = [r[key] for r in rows if r.get(key) is not None]
        return (v[-1] - v[0]) if len(v) >= 2 else None
    span = (jW[-1]['ms'] - jW[0]['ms']) / 1000 if len(jW) >= 2 else None
    thr = delta('throttled_count', jW)
    thr_ns = delta('throttled_nanos', jW)
    recv = delta('received_count', jW)
    pool_idle = statistics.mean(r['pool_used'] for r in j_before) if j_before else 0
    pool_vals = [r['pool_used'] for r in jW if r.get('pool_used') is not None]
    P_peak = (max(pool_vals) - pool_idle) if pool_vals else None
    P_range = (max(pool_vals) - min(pool_vals)) if pool_vals else None
    direct_idle = statistics.mean(r['direct_used'] for r in j_before if r.get('direct_used') is not None) if j_before else 0
    direct_max = max((r['direct_used'] for r in jW if r.get('direct_used') is not None), default=None)
    heap_max = max((r['heap_used'] for r in jW if r.get('heap_used') is not None), default=None)
    ms_pend_max = max((r['ms_pending'] for r in jW if r.get('ms_pending') is not None), default=None)
    dropped = delta('dropped_mutation', jr)

    vin = [r for r in read_vt(D + '/vt-in.csv') if r['address'] == NODES['B'][0]]
    vinW = [r for r in vin if t_s0 <= r['ms'] <= t_end]
    vt_using_max = max((r['using_bytes'] for r in vinW), default=None)
    vt_reserve_max = max((r['using_reserve_bytes'] for r in vinW), default=None)
    vt_after = [r for r in read_vt(D + '/vt-in-after.csv') if r['address'] == NODES['B'][0]]
    vt_before = [r for r in read_vt(D + '/vt-in-before.csv') if r['address'] == NODES['B'][0]]
    expired = (vt_after[-1]['expired_count'] - vt_before[-1]['expired_count']) if vt_after and vt_before else None
    vout = [r for r in read_vt(D + '/vt-out.csv') if r['address'] == NODES['A'][0]]
    b_overload = (vout[-1]['overload_count'] - vout[0]['overload_count']) if vout else None
    b_expired = (vout[-1]['expired_count'] - vout[0]['expired_count']) if vout else None

    def retained(h):
        return (h['mutation'][1] + h['bytes'][1]) - (h_idle['mutation'][1] + h_idle['bytes'][1])
    loadS = [s for s in SAMPLES if s['tag'].startswith('load') and s['ms'] <= t_end]
    ret = [retained(s['h']) for s in loadS]
    H_peak = max(ret) if ret else None
    H_range = (max(ret) - min(ret)) if ret else None
    mut_live = [s['h']['mutation'][0] - h_idle['mutation'][0] for s in loadS]
    M = (H_peak + P_peak) if (H_peak is not None and P_peak is not None) else None
    noise = ((H_range or 0) + (P_range or 0)) if stress is False else None
    ret_after = retained(h_after)
    mut_after = h_after['mutation'][0] - h_idle['mutation'][0]
    blog = open(D + '/A-system.log', errors='replace').read() if os.path.exists(D + '/A-system.log') else ''
    slog = open(D + '/B-system.log', errors='replace').read() if os.path.exists(D + '/B-system.log') else ''
    oom_A = blog.count('java.lang.OutOfMemoryError')
    oom_B = slog.count('java.lang.OutOfMemoryError')
    unrec = blog.count('UnrecoverableIllegalStateException')
    errs_A = len(re.findall(r'^ERROR ', blog, re.M))

    R = dict(label=label, Q=Q, E=E, G=G, stress=stress, t_s0=t_s0, t_s1=t_s1, drained=drained,
             stress_s=(t_s1 - t_s0) / 1000, M_med=M_med, M_max=M_max, C_pred=C_pred, acc=acc, acc_over_C=acc / C_pred,
             refusals=len(refusals), outcomes=outs, data_acq=len(data), viol_succ=viol_succ, over_ep=over_ep, over_gl=over_gl,
             max_ep_using=max_ep, max_gl_using=max_gl, cfg_lines=len(cfgd), last_line=last_line, last_cfg_line=last_cfg,
             hold_lines=len(holdsW), held_threads=held1, throttled=thr, throttled_nanos=thr_ns, received=recv, span_s=span,
             vt_using_max=vt_using_max, vt_reserve_max=vt_reserve_max, vt_after=(vt_after[-1] if vt_after else None),
             expired_A=expired, dropped_A=dropped, b_overload=b_overload, b_expired=b_expired, pool_idle=pool_idle,
             P_peak=P_peak, P_range=P_range, direct_idle=direct_idle, direct_max=direct_max, heap_max=heap_max,
             ms_pending_max=ms_pend_max, retained=ret, H_peak=H_peak, H_range=H_range, M=M, noise=noise,
             mutation_live=mut_live, retained_after=ret_after, mutation_after=mut_after, idle_hist=h_idle,
             after_hist=h_after, samples=[{'tag': s['tag'], 'ms': s['ms'], 'h': s['h']} for s in SAMPLES],
             oom_A=oom_A, oom_B=oom_B, unrecoverable_A=unrec, error_lines_A=errs_A, trace_other=other)
    json.dump(R, open(D + '/readings.json', 'w'), indent=1, default=str)
    note(f'{label} readings: M(msg) median {M_med} max {M_max}; C = Q + min(E,G) = {C_pred}; acc {acc} ({acc / C_pred:.3f} C); '
         f'refusals {len(refusals)} {outs}; trace max using ep {max_ep} gl {max_gl} (over: {over_ep}/{over_gl}); vt using max '
         f'{vt_using_max} reserve max {vt_reserve_max}; ThrottledCount delta {thr} over {span} s, received {recv}; H {H_peak} '
         f'(samples {ret}), P {P_peak}, M {M}; live Mutation above idle {mut_live}; direct max {direct_max}; heap max {heap_max}; '
         f'MutationStage pending max {ms_pend_max}; hold lines {len(holdsW)}, held threads {held1}; after drain: retained '
         f'{ret_after}, live Mutation {mut_after}, vt {R["vt_after"]}, last trace line {last_line}; expired A {expired}, '
         f'dropped A {dropped}; B overload {b_overload} expired {b_expired}; OOM A/B {oom_A}/{oom_B}')

    # ---- validity and rule checks
    if stress:
        expect(f'{label}: the hold fired (hold lines {len(holdsW)} > 0, MutationStage threads in doVerb sleeping at the first '
               f'load sample {held1} > 0)', len(holdsW) > 0 and (held1 or 0) > 0)
    expect(f'{label}: B3f "never above G": no trace line of the configured limits with endpoint using > {E} ({over_ep}) or '
           f'global using > {G} ({over_gl}); max ep {max_ep}, max gl {max_gl}; vtable using_reserve_bytes max {vt_reserve_max} <= {G}',
           over_ep == 0 and over_gl == 0 and (vt_reserve_max or 0) <= G)
    expect(f'{label}: every SUCCESS acquire of an internode handler has q <= cap + min(E, G) (violations {viol_succ}); '
           f'accounted peak {acc} <= C = {C_pred}', viol_succ == 0 and acc <= C_pred)
    va = R['vt_after']
    lc = last_cfg
    expect(f'{label}: idle: vtable using_bytes {va and va["using_bytes"]} and using_reserve_bytes {va and va["using_reserve_bytes"]} '
           f'0, last configured-limit trace line ep/gl using {lc and lc["epu"]}/{lc and lc["glu"]} 0, live Mutation {mut_after} <= 2',
           drained is not None and va is not None and va['using_bytes'] == 0 and va['using_reserve_bytes'] == 0
           and lc is not None and lc['epu'] == 0 and lc['glu'] == 0 and mut_after <= 2)
    expect(f'{label}: no OutOfMemoryError on A ({oom_A}) or B ({oom_B}), no UnrecoverableIllegalStateException on A ({unrec})',
           oom_A == 0 and oom_B == 0 and unrec == 0)
    # ---- B3f clauses per label
    if label in ('g4', 'g32', 'ctlq16'):
        expect(f'{label}: limit reached: ThrottledCount delta {thr} > 0 and refusals {len(refusals)} > 0 and accounted peak {acc} '
               f'within one message ({M_max}) of C = {C_pred}', (thr or 0) > 0 and len(refusals) > 0 and M_max is not None
               and C_pred - M_max < acc <= C_pred)
    if label == 'g512':
        near = recv is not None and thr is not None and thr <= 0.01 * max(recv, 1)
        expect(f'{label}: ~0 throttling: ThrottledCount delta {thr} <= 1 % of {recv} received; refusals {len(refusals)}',
               near and len(refusals) == 0)
    if label == 'base':
        note(f'BASELINE noise: H range {H_range}, P range {P_range}, sum {noise}')
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
        say(f'  {l}: C {r["C_pred"]} acc {r["acc"]} H {r["H_peak"]} P {r["P_peak"]} M {r["M"]} throttled {r["throttled"]} '
            f'received {r["received"]} refusals {r["refusals"]} vt reserve max {r["vt_reserve_max"]}')
    noise = R['base']['noise'] if 'base' in R else None
    if noise is not None:
        say(f'noise (B3h baseline `base`: H range + P range) = {noise}')
    if 'g4' in R and 'g32' in R and noise is not None:
        a, b = R['g4'], R['g32']
        dM = b['M'] - a['M']
        dacc = b['acc'] - a['acc']
        r = dM / dacc if dacc else None
        expect(f'B3f memory grows with G over {{4, 32}} MiB: M(g32) - M(g4) = {dM} >= 10 MiB and >= 2 x noise {2 * noise}',
               dM >= 10 * MIB and dM >= 2 * noise)
        expect(f'B3f inflation factor r = (M(g32) - M(g4)) / (acc(g32) - acc(g4)) = {dM} / {dacc} = {r and round(r, 3)} in [1, 3]',
               r is not None and 1 <= r <= 3)
    if 'g512' in R:
        g = R['g512']
        expect(f'B3f flat or load-limited at 512 MiB: M(g512) {g["M"]} <= 3 x acc(g512) {3 * g["acc"]}', g['M'] <= 3 * g['acc'])
    if 'g4' in R and 'ctlq16' in R:
        a, c = R['g4'], R['ctlq16']
        expect(f'B3h positive control: Q 1 -> 16 MiB at G = 4 MiB moves memory: M(ctlq16) - M(g4) = {c["M"] - a["M"]} >= 15 MiB '
               f'and acc {c["acc"]} > {a["acc"]}', c['M'] - a['M'] >= 15 * MIB and c['acc'] > a['acc'])
    if 'g4' in R and 'g32' in R and 'g512' in R:
        say(f'M by G: 4 MiB {R["g4"]["M"]}, 32 MiB {R["g32"]["M"]}, 512 MiB {R["g512"]["M"]}; throttled {R["g4"]["throttled"]} / '
            f'{R["g32"]["throttled"]} / {R["g512"]["throttled"]}')
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
