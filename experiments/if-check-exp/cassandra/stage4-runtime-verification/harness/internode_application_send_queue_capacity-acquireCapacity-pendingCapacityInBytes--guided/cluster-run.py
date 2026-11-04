#!/usr/bin/env python3
"""Stage 4, cluster tier, internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes (case 9b-9e).
usage: cluster-run.py <label>      (run on the measured node, pc66; one label per call, in the background)

  c512k c1m c4m c16m   capacity 512KiB / 1MiB / 4MiB / 16MiB, all three reserves 1MiB  -> idle control, hold check, scenario A, scenario B (+ drain)
  defres               4MiB, reserves at their defaults, hold on                          -> the default-reserves arm (B only)
  nohold               1MiB, reserves 1MiB, NO hold                                        -> the no-hold control (B load without the hold)
  c1                   4MiB, only the SEND endpoint key lowered (1MiB)                     -> scenario C1
  c2                   4MiB, only the RECEIVE endpoint key lowered (1MiB)                  -> scenario C2
  peer                 4MiB, reserves 1MiB, RF = P = 1, 2, 3 (ALTER KEYSPACE, S not restarted) -> the peer sweep
  down                 stop R1 to R3 (the ring is left up between labels) and print what is left

Four processes on this machine (case 9b): S = 127.0.0.2 (JMX 7102, the Byteman agent and the hold), R1..R3 = 127.0.0.3..5 (JMX 7103..7105), each with its own
conf/ copy, log, data and token under ~/stage4-ssq/<node>/ (make-node-yaml.sh). R1..R3 are started once and left up; S is restarted per label.
Writes ~/stage4-logs/ssq/<label>/{session.log, summary.txt, scenarios.csv, readings.csv, send-trace.txt, <scenario>/...}. Every EXPECTED: line
is a prediction of 9a, computed before the readings; a NO is recorded, not tuned (the AI judges it in the results file). Exit 1: a set-up or instrument
check failed; S is stopped on any exit, and the hold file removed."""
import csv, glob, hashlib, math, os, re, statistics, subprocess, sys, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-run1')
HARNESS = os.path.dirname(os.path.abspath(__file__))
SSQ = HOME + '/stage4-ssq'
MIB = 1048576
NODES = {'S': ('127.0.0.2', 7102), 'R1': ('127.0.0.3', 7103), 'R2': ('127.0.0.4', 7104), 'R3': ('127.0.0.5', 7105)}
PEERS = ['R1', 'R2', 'R3']
SEND_CAP = 'internode_application_send_queue_capacity'
SEND_GLOB = 'internode_application_send_queue_reserve_global_capacity'
SEND_EP = 'internode_application_send_queue_reserve_endpoint_capacity'
RECV_EP = 'internode_application_receive_queue_reserve_endpoint_capacity'
DEFAULT_E, DEFAULT_G = 128 * MIB, 512 * MIB          # effective per-peer reserve by section 4 (the receive key's default) and the node-wide default
LOW = {SEND_GLOB: '1MiB', SEND_EP: '1MiB', RECV_EP: '1MiB'}
THREADS_B, THROTTLE, LOAD_B, THREADS_A, LOAD_A = 256, '2000/s', 8, 2, 4
VALSIZE = 131072

# label -> (capacity bytes, yaml extras, effective E, effective G, drops expected, first refusal, hold, scenario A, RF list)
LABELS = {
    'c512k':  (512 * 1024, LOW, MIB, MIB, True, 'INSUFFICIENT_GLOBAL', True, True, [1]),
    'c1m':    (MIB, LOW, MIB, MIB, True, 'INSUFFICIENT_GLOBAL', True, True, [1]),
    'c4m':    (4 * MIB, LOW, MIB, MIB, True, 'INSUFFICIENT_GLOBAL', True, True, [1]),
    'c16m':   (16 * MIB, LOW, MIB, MIB, True, 'INSUFFICIENT_GLOBAL', True, True, [1]),
    'defres': (4 * MIB, {}, DEFAULT_E, DEFAULT_G, False, None, True, False, [1]),
    'nohold': (MIB, LOW, MIB, MIB, False, None, False, False, [1]),
    'c1':     (4 * MIB, {SEND_EP: '1MiB'}, DEFAULT_E, DEFAULT_G, False, None, True, False, [1]),          # section 4: the receive key governs, so no drops
    'c2':     (4 * MIB, {RECV_EP: '1MiB'}, MIB, DEFAULT_G, True, 'INSUFFICIENT_ENDPOINT', True, False, [1]),
    'peer':   (4 * MIB, LOW, MIB, MIB, True, 'INSUFFICIENT_GLOBAL', True, False, [1, 2, 3]),
}
if len(sys.argv) != 2 or sys.argv[1] not in list(LABELS) + ['down']:
    sys.exit(__doc__)
label = sys.argv[1]
D = f'{HOME}/stage4-logs/ssq/{label}'
if os.path.exists(D):
    os.rename(D, D + '.' + time.strftime('%Y%m%d-%H%M%S', time.localtime(os.path.getmtime(D))))
os.makedirs(D)
SESSION = open(D + '/session.log', 'a')
SUMMARY = open(D + '/summary.txt', 'w')
SCEN = csv.writer(open(D + '/scenarios.csv', 'w'))
SCEN.writerow(['label', 'scenario', 'rf', 'peer', 'X_trace_max_pending', 'accepted', 'refused', 'M', 'first_refusal', 'jmx_pending_late', 'overload_delta',
               'timeout_delta_before_lift', 'timeout_delta_after_drain', 'completed_delta_drain', 'reserve_max_table', 'stress_errors', 'heap_delta'])
READ = csv.writer(open(D + '/readings.csv', 'w'))
READ.writerow(['ts_ms', 'tag', 'peer', 'attr', 'value'])
TRACE = D + '/send-trace.txt'
HOLD = D + '/hold'
SPID = None


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, file=sys.stderr)
    SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush(); log(s)


def sh(cmd, timeout=600, check=True, env=None, cwd=C, quiet=False):
    if not quiet:
        log('+ ' + (cmd if isinstance(cmd, str) else ' '.join(cmd)))
    r = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
    out = (r.stdout or '') + (r.stderr or '')
    if not quiet or r.returncode != 0:
        SESSION.write(out[-3000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed rc={r.returncode}: {cmd}\n{out[-800:]}')
    return r.returncode, out


def expect(desc, cond):
    note(f'EXPECTED: {desc} — {"yes" if cond else "NO (recorded; the AI judges it in the results file)"}')
    return cond


def now_ms():
    return int(time.time() * 1000)


# ---- processes
def pid_of(node):
    try:
        p = int(open(f'{SSQ}/{node}/cassandra.pid').read().strip())
        os.kill(p, 0)
        return p
    except (OSError, ValueError):
        return None


def stop_node(node, quiet=False):
    p = pid_of(node)
    if p is None:
        return
    sh(f'bin/nodetool -p {NODES[node][1]} stopdaemon', check=False, quiet=True)
    for _ in range(90):
        if pid_of(node) is None:
            return
        time.sleep(1)
    if pid_of(node) is not None:
        os.kill(p, 9)
        time.sleep(2)
        log(f'WARNING: {node} had to be killed')


def cleanup():
    try:
        if os.path.exists(HOLD):
            os.remove(HOLD)
    except OSError:
        pass
    stop_node('S')


def fail(msg):
    note('FAIL: ' + msg)
    cleanup()
    sys.exit(1)


def start_node(node, extra_env=None, extras=(), tag=''):
    if pid_of(node) is not None:
        fail(f'{node} is already running')
    sh(f'{HARNESS}/make-node-yaml.sh {node} ' + ' '.join(f'{k}={v}' for k, v in extras))
    N = f'{SSQ}/{node}'
    env = dict(os.environ, CASSANDRA_CONF=N + '/conf', CASSANDRA_LOG_DIR=N + '/logs', MAX_HEAP_SIZE='2G')
    env.update(extra_env or {})
    sh(f'bin/cassandra -p {N}/cassandra.pid > {N}/stdout{tag}.txt 2>&1', env=env)
    time.sleep(3)
    if pid_of(node) is None:
        fail(f'{node} did not start; see {N}/stdout{tag}.txt')


def wait_up(node, want_un, timeout=300):
    """node's own nodetool must show 'running' for statusbinary and `want_un` nodes UN."""
    port = NODES[node][1]
    t0 = time.time()
    while time.time() - t0 < timeout:
        _, st = sh(f'bin/nodetool -p {port} statusbinary', check=False, quiet=True)
        _, ns = sh(f'bin/nodetool -p {port} status', check=False, quiet=True)
        if 'running' in st and len(re.findall(r'^UN', ns, re.M)) >= want_un:
            note(f'{node} up: statusbinary running, {len(re.findall(r"^UN", ns, re.M))} nodes UN ({time.time() - t0:.0f} s)')
            return
        if pid_of(node) is None:
            fail(f'{node} died while starting')
        time.sleep(3)
    fail(f'{node} did not reach {want_un} UN within {timeout} s')


def wipe_ring_state():
    """Delete the data of R1..R3 and S (their conf and logs stay). Only with every node stopped."""
    for n in PEERS + ['S']:
        for sub in ('data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw'):
            sh(f'rm -rf {SSQ}/{n}/{sub}', check=False, quiet=True)
        if os.path.exists(f'{SSQ}/{n}/cassandra.pid') and pid_of(n) is None:
            os.remove(f'{SSQ}/{n}/cassandra.pid')


def ensure_ring():
    """Start R1 (seed), R2, R3 if they are not up, one at a time.
    A ring that has already seen S still lists it, and with S stopped `ALTER KEYSPACE` is refused ("endpoints are not in normal
    state"), so such a ring is stopped and wiped first and started fresh (2026-10-07 shakedown)."""
    if all(pid_of(n) is not None for n in PEERS) and pid_of('S') is None:
        _, st = sh(f'bin/nodetool -p {NODES["R1"][1]} status', check=False, quiet=True)
        if NODES['S'][0] in st:
            note('ring: R1..R3 are up but still list S; stopping and wiping them to start a fresh ring')
            for n in PEERS:
                stop_node(n)
            wipe_ring_state()
    started = 0
    for i, n in enumerate(PEERS):
        if pid_of(n) is None:
            start_node(n)
            wait_up(n, i + 1)
            started += 1
    if started:
        note(f'ring: started {started} of R1..R3 (they stay up between labels)')
    else:
        note('ring: R1..R3 were already up')


# ---- driver, JMX, heap
def load_driver():
    lib = os.path.join(C, 'lib')

    def find_zip(prefix):
        z = glob.glob(os.path.join(lib, prefix + '*.zip'))
        return max(z) if z else None
    cql = find_zip('cassandra-driver-internal-only-')
    ver = os.path.splitext(os.path.basename(cql))[0][len('cassandra-driver-internal-only-'):]
    sys.path.insert(0, os.path.join(cql, 'cassandra-driver-' + ver))
    for pre in ('pure_sasl-', 'wcwidth-', 'pyasyncore-'):
        z = find_zip(pre)
        if z:
            sys.path.insert(0, z)
    from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
    from cassandra.policies import WhiteListRoundRobinPolicy
    from cassandra import ConsistencyLevel
    return Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT, WhiteListRoundRobinPolicy, ConsistencyLevel


def cql(host, stmt):
    Cluster, EP, DEFAULT, WL, CL = load_driver()
    cl = Cluster([host], protocol_version=5, execution_profiles={DEFAULT: EP(load_balancing_policy=WL([host]), request_timeout=60, consistency_level=CL.ONE)})
    try:
        s = cl.connect()
        r = list(s.execute(stmt))
        return r
    finally:
        cl.shutdown()


def jmx_get(port, *pairs):
    _, out = sh(['java', '-cp', D + '/jmx-classes', 'Jmx', str(port), 'get'] + [x for p in pairs for x in p], check=False, quiet=True)
    vals = {}
    for l in out.splitlines():
        parts = l.split('|')
        if len(parts) == 3:
            vals[(parts[0], parts[1])] = parts[2]
    return vals


def set_rf(rf):
    """ALTER KEYSPACE keyspace1 to SimpleStrategy RF=rf unless it already is (Cassandra refuses any ALTER while a joined node is down)"""
    cur = cql(NODES['R1'][0], "SELECT replication FROM system_schema.keyspaces WHERE keyspace_name = 'keyspace1'")
    if cur and str(cur[0].replication.get('replication_factor')) == str(rf) and 'SimpleStrategy' in cur[0].replication.get('class', ''):
        return f'RF already {rf}, not altered'
    cql(NODES['R1'][0], f"ALTER KEYSPACE keyspace1 WITH replication = {{'class': 'SimpleStrategy', 'replication_factor': {rf}}}")
    return f'altered to RF {rf}'


SCOPE = {}
ATTRS = ['LargeMessagePendingBytes', 'LargeMessagePendingTasks', 'LargeMessageCompletedTasks', 'LargeMessageDroppedTasksDueToOverload',
         'LargeMessageDroppedBytesDueToOverload', 'LargeMessageDroppedTasksDueToTimeout', 'LargeMessageDroppedBytesDueToTimeout',
         'LargeMessageDroppedTasksDueToError']


def discover_scopes():
    _, out = sh(['java', '-cp', D + '/jmx-classes', 'Jmx', '7102', 'query', 'org.apache.cassandra.metrics:type=Connection,*'], check=False, quiet=True)
    for l in out.splitlines():
        m = re.search(r'scope=([^,]+),', l)
        if m:
            for n in PEERS:
                if NODES[n][0] in m.group(1):
                    SCOPE[n] = m.group(1)
    note(f'JMX scopes of S\'s connection metrics: {SCOPE}')
    if len(SCOPE) < 3:
        fail('connection metrics for R1..R3 not all registered on S')


def jmx_snapshot(tag, peers=PEERS):
    pairs = [(f'org.apache.cassandra.metrics:type=Connection,scope={SCOPE[p]},name={a}', 'Value') for p in peers for a in ATTRS]
    v = jmx_get(7102, *pairs)
    ts = now_ms()
    res = {}
    for p in peers:
        for a in ATTRS:
            x = v.get((f'org.apache.cassandra.metrics:type=Connection,scope={SCOPE[p]},name={a}', 'Value'))
            res[(p, a)] = int(float(x)) if x is not None and not x.startswith('ERROR') else None
            READ.writerow([ts, tag, p, a, x])
    return res


def s_pid():
    return pid_of('S')


def heap_used_kb():
    """GC.run then GC.heap_info: the 'used' of the heap (G1: first line; CMS/other: summed over the generation lines), in KiB."""
    sh(f'jcmd {s_pid()} GC.run', check=False, quiet=True)
    _, out = sh(f'jcmd {s_pid()} GC.heap_info', check=False, quiet=True)
    SESSION.write(out[-1500:] + '\n'); SESSION.flush()
    m = re.search(r'garbage-first heap\s+total \d+K, used (\d+)K', out)
    if m:
        return int(m.group(1))
    us = [int(x) for x in re.findall(r'(?:generation|space|heap)\s+total \d+K, used (\d+)K', out)]
    return sum(us[:2]) if us else None


def histogram(tag):
    _, out = sh(f'jcmd {s_pid()} GC.class_histogram', check=False, quiet=True, timeout=120)
    open(f'{D}/histogram-{tag}.txt', 'w').write(out)
    res = {}
    for cls in ('org.apache.cassandra.net.Message', 'org.apache.cassandra.db.Mutation'):
        m = re.search(r'^\s*\d+:\s+(\d+)\s+(\d+)\s+' + re.escape(cls) + r'\s*$', out, re.M)
        res[cls] = (int(m.group(1)), int(m.group(2))) if m else None
    return res


# ---- trace
def read_trace(t0, t1):
    """parse send-trace.txt lines with t0 <= ms <= t1 (epoch ms)"""
    cfg, acq, holds = [], [], []
    if not os.path.exists(TRACE):
        return cfg, acq, holds
    for l in open(TRACE, errors='replace'):
        ms = re.search(r' ms=(\d+)$', l.strip())
        if not ms or not (t0 <= int(ms.group(1)) <= t1):
            continue
        if l.startswith('acquire '):
            m = re.match(r'acquire type=(\S+) peer=/?(\S+) count=(\d+) bytes=(\d+) outcome=(\S+) pending=(\d+) pendingCount=(-?\d+) overloaded=(\d+) '
                         r'endpoint_using=(\d+) global_using=(\d+) ms=(\d+)', l)
            if m:
                acq.append(dict(type=m.group(1), peer=m.group(2), bytes=int(m.group(4)), outcome=m.group(5), pending=int(m.group(6)),
                                ep=int(m.group(9)), gl=int(m.group(10)), ms=int(m.group(11))))
        elif l.startswith('config '):
            m = re.match(r'config type=(\S+) peer=/?(\S+) capacity=(\S+) endpoint=(\S+) global=(\S+) ms=(\d+)', l)
            if m:
                cfg.append(dict(type=m.group(1), peer=m.group(2), capacity=m.group(3), endpoint=m.group(4), glob=m.group(5), ms=int(m.group(6))))
        elif l.startswith('hold '):
            holds.append(l.strip())
    return cfg, acq, holds


def large_lines(acq, peer):
    return [a for a in acq if a['type'] == 'LARGE_MESSAGES' and a['peer'].startswith(NODES[peer][0] + ':')]


# ---- load
def stress(tag, threads, seconds=None, n=None, rf=1, throttle=THROTTLE, node='S'):
    out = f'{D}/{tag}/stress.txt'
    os.makedirs(f'{D}/{tag}', exist_ok=True)
    dur = f'duration={seconds}s' if seconds else f'n={n}'
    cmd = (f"tools/bin/cassandra-stress write {dur} no-warmup cl=ONE -col 'n=FIXED(1)' 'size=FIXED({VALSIZE})' "
           f"-schema 'replication(strategy=SimpleStrategy,factor={rf})' -errors ignore -rate threads={threads}"
           + (f' throttle={throttle}' if throttle and threads > 1 else '') + f' -node whitelist {NODES[node][0]} > {out} 2>&1')
    log('+ ' + cmd)
    return subprocess.Popen(cmd, shell=True, cwd=C, env={k: v for k, v in os.environ.items() if k != 'JVM_EXTRA_OPTS'}, start_new_session=True), out


def stress_errors(path):
    """(failed operations, failed attempts) from a stress output. `Total errors` counts operations and prints thousands with commas
    ("10,293"); stress retries a failed operation (`Operation xN on key(s) ...: Error executing`), so the attempts are the sum of the N."""
    if not os.path.exists(path):
        return None, None
    txt = open(path, errors='replace').read()
    m = re.search(r'Total errors\s*:\s*([\d,]+)', txt)
    ops = int(m.group(1).replace(',', '')) if m else None
    attempts = sum(int(x) for x in re.findall(r'^Operation x(\d+) .*Error executing', txt, re.M))
    return ops, attempts


def wait_proc(p, timeout, what):
    t0 = time.time()
    while p.poll() is None and time.time() - t0 < timeout:
        time.sleep(0.5)
    if p.poll() is None:
        note(f'{what}: still running after {timeout} s; terminated')
        p.terminate()
        time.sleep(1)
        if p.poll() is None:
            p.kill()


def start_poller(tag):
    os.makedirs(f'{D}/{tag}', exist_ok=True)
    stopf = f'{D}/{tag}/poll.stop'
    if os.path.exists(stopf):
        os.remove(stopf)
    open(f'{D}/{tag}/poll.csv', 'w').close()
    p = subprocess.Popen([sys.executable, f'{HARNESS}/sample-outbound.py', f'{D}/{tag}/poll.csv', '--host', NODES['S'][0], '--interval', '0.25',
                          '--stop-file', stopf, '--clone', C], stdout=open(f'{D}/{tag}/poll.out', 'w'), stderr=subprocess.STDOUT, start_new_session=True)
    time.sleep(2.5)
    return p, stopf


def stop_poller(p, stopf):
    open(stopf, 'w').close()
    try:
        p.wait(timeout=15)
    except subprocess.TimeoutExpired:
        p.kill()


def poll_rows(tag):
    rows = []
    with open(f'{D}/{tag}/poll.csv') as f:
        for r in csv.DictReader(f):
            if r.get('peer') and r['peer'] != 'ERROR' and r['pending_bytes'] != '':
                rows.append(dict(ts=int(r['ts_ms']), peer=r['peer'], pend=int(r['pending_bytes']), res=int(r['using_reserve_bytes']),
                                 over=int(r['overload_count']), exp=int(r['expired_count']), sent=int(r['sent_count'])))
    return rows


def wait_settled(peers, timeout=40):
    """until the large links' pending bytes are 0 on every peer (JMX); returns seconds taken or None"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = jmx_get(7102, *[(f'org.apache.cassandra.metrics:type=Connection,scope={SCOPE[p]},name=LargeMessagePendingBytes', 'Value') for p in peers])
        if v and all(float(x) == 0 for x in v.values()):
            return time.time() - t0
        time.sleep(1)
    return None


def probe(peers_expected=('R1',)):
    """the liveness probe: one large write with the hold absent; the large link's completed count of the owner rises by one"""
    before = jmx_snapshot('probe-before', list(peers_expected))
    p, out = stress('probe-%d' % now_ms(), 1, n=1)
    wait_proc(p, 60, 'probe stress')
    time.sleep(1)
    after = jmx_snapshot('probe-after', list(peers_expected))
    return {pe: after[(pe, 'LargeMessageCompletedTasks')] - before[(pe, 'LargeMessageCompletedTasks')] for pe in peers_expected}


# ---- scenario machinery
def scenario(sc, threads, seconds, rf, hold, cap, E, G, drops, first_ref, heap_idle, record_peers):
    """One of A or B (sc in 'A', 'B', 'B-rfN', 'B-nohold'): returns a dict of the readings and writes the scenarios.csv rows."""
    peers = PEERS[:rf]
    os.makedirs(f'{D}/{sc}', exist_ok=True)
    if hold:
        open(HOLD, 'w').close()
    poller, stopf = start_poller(sc)
    pre = jmx_snapshot(f'{sc}-pre', PEERS)
    t0 = now_ms()
    p, out = stress(sc, threads, seconds=seconds, rf=rf)
    ts = time.time()
    heap5 = hist5 = None
    if sc.startswith('B'):
        time.sleep(max(0, ts + 5 - time.time()))
        heap5 = heap_used_kb()
        hist5 = histogram(sc)
        note(f'{sc}: heap used after full GC at ~5 s = {heap5} KiB; histogram {hist5}')
    wait_proc(p, 60, f'{sc} stress')
    time.sleep(max(0, ts + 12.5 - time.time()))
    late = jmx_snapshot(f'{sc}-late', PEERS)
    # thread dump while the hold is on (the parked delivery threads)
    parked = 0
    if hold:
        _, td = sh(f'jcmd {s_pid()} Thread.print', check=False, quiet=True, timeout=60)
        open(f'{D}/{sc}/threads.txt', 'w').write(td)
        parked = len(re.findall(r'stage4\.Hold\.park', td))
    time.sleep(max(0, ts + 13.0 - time.time()))
    t_lift = now_ms()
    if hold and os.path.exists(HOLD):
        os.remove(HOLD)
    settle = wait_settled(peers) if hold else 0
    t_settled = now_ms()
    drained = jmx_snapshot(f'{sc}-drained', PEERS)
    time.sleep(2)
    stop_poller(poller, stopf)
    probed = probe(('R1',)) if hold else {}
    t1 = now_ms()
    cfg, acq, holds = read_trace(t0, t1)
    rows = poll_rows(sc)
    errs, attempts = stress_errors(out)
    res = dict(sc=sc, peers=peers, parked=parked, settle=settle, probe=probed, heap5=heap5, hist5=hist5, errors=errs, attempts=attempts, X={}, acc={}, ref={}, M=None, first=None)
    allM = [a['bytes'] for p_ in peers for a in large_lines(acq, p_) if a['outcome'] == 'SUCCESS']
    M = statistics.mode(allM) if allM else None
    res['M'] = M
    for pe in PEERS:
        ll = [a for a in large_lines(acq, pe) if t0 <= a['ms'] <= t_lift]
        X = max([a['pending'] for a in ll], default=0)
        acc = sum(1 for a in ll if a['outcome'] == 'SUCCESS')
        ref = [a for a in ll if a['outcome'] != 'SUCCESS']
        first = ref[0]['outcome'] if ref else None
        res['X'][pe], res['acc'][pe], res['ref'][pe] = X, acc, len(ref)
        if pe == peers[0]:
            res['first'] = first
        prow = [r for r in rows if r['peer'].startswith(NODES[pe][0] + ':')]
        resmax = max([r['res'] for r in prow], default=0)
        d = lambda a_, b_, k: (None if a_[(pe, k)] is None or b_[(pe, k)] is None else b_[(pe, k)] - a_[(pe, k)])
        SCEN.writerow([label, sc, rf, pe, X, acc, len(ref), M, first, late[(pe, 'LargeMessagePendingBytes')], d(pre, late, 'LargeMessageDroppedTasksDueToOverload'),
                       d(pre, late, 'LargeMessageDroppedTasksDueToTimeout'), d(pre, drained, 'LargeMessageDroppedTasksDueToTimeout'),
                       d(late, drained, 'LargeMessageCompletedTasks'), resmax, errs if pe == peers[0] else '',
                       (heap5 - heap_idle) if (heap5 is not None and heap_idle is not None and pe == peers[0]) else ''])
    res.update(pre=pre, late=late, drained=drained, rows=rows, cfg=cfg, acq=acq, t0=t0, t_lift=t_lift)
    return res


def adjudicate_B(r, cap, E, G, drops, first_ref, hold, threads, heap_idle, spread):
    sc, peers, M = r['sc'], r['peers'], r['M']
    F = min(E, G)
    pe = peers[0]
    note(f'[{sc}] M = {M} B (mode of accepted bytes); X (max pending seen by acquire, large link) = {r["X"]}; accepted {r["acc"]}; refused {r["ref"]}; '
         f'first refusal {r["first"]}; stress failed operations {r["errors"]}, failed attempts {r["attempts"]}; parked delivery threads in the dump {r["parked"]}; drain settled in {r["settle"]} s; probe {r["probe"]}')
    if M is None:
        expect(f'[{sc}] at least one message was accepted on the large link', False)
        return
    if not hold:
        X = r['X'][pe]
        expect(f'[{sc}] no-hold control: X far below C + F ({X} < {(cap + F) // 2}) and overload_count = 0 ({r["ref"][pe]} refused)', X < (cap + F) // 2 and r['ref'][pe] == 0)
        return
    D_ = threads * M
    over = sum(r['ref'].values())
    # the load must exceed C + F (else the run is invalid), except in the arms where nothing is expected to drop
    if drops:
        expect(f'[{sc}] valid run: offered load D = {D_} exceeds C + F = {cap + F}', D_ > cap + F)
        for p_ in peers:
            X = r['X'][p_]
            lo, hi = cap + F - M, cap + F
            expect(f'[{sc}] {p_}: C + F - M < X <= C + F ({lo} < {X} <= {hi})', lo < X <= hi)
            expect(f'[{sc}] {p_}: overload_count rose ({r["ref"][p_]} refused lines in the trace; JMX delta {r["late"][(p_, "LargeMessageDroppedTasksDueToOverload")] - r["pre"][(p_, "LargeMessageDroppedTasksDueToOverload")]})', r['ref'][p_] > 0)
        expect(f'[{sc}] first refused acquire is {first_ref} (it was {r["first"]})', r['first'] == first_ref)
        # reserve use of the first peer from the table: > X - C - M and <= F
        prow = [x for x in r['rows'] if x['peer'].startswith(NODES[pe][0] + ':')]
        rmax = max([x['res'] for x in prow], default=0)
        if len(peers) == 1:
            expect(f'[{sc}] using_reserve_bytes ~ X - C: F - M < {rmax} <= F ({F - M} < {rmax} <= {F})', F - M < rmax <= F)
    else:
        for p_ in peers:
            X = r['X'][p_]
            expect(f'[{sc}] {p_}: nothing dropped (refused {r["ref"][p_]}) and X ~ D = {D_} (|X - D| <= 2 M: {X})', r['ref'][p_] == 0 and abs(X - D_) <= 2 * M)
    # bypass: an accepted acquire above C + F
    bad = [a for a in r['acq'] if a['type'] == 'LARGE_MESSAGES' and a['outcome'] == 'SUCCESS' and a['pending'] > cap + F and drops]
    expect(f'[{sc}] no SUCCESS acquire with pending above C + F ({len(bad)} found)', not bad)
    # plateau flat past the deadline: the late JMX reading equals the peak, nothing expired before the lift
    for p_ in peers:
        late = r['late'][(p_, 'LargeMessagePendingBytes')]
        expire = r['late'][(p_, 'LargeMessageDroppedTasksDueToTimeout')] - r['pre'][(p_, 'LargeMessageDroppedTasksDueToTimeout')]
        expect(f'[{sc}] {p_}: plateau still there at ~12.5 s, past the 10 s deadline (JMX {late} = peak {r["X"][p_]}) and nothing expired before the lift ({expire})', late == r['X'][p_] and expire == 0)
    # drain
    for p_ in peers:
        pend = r['drained'][(p_, 'LargeMessagePendingBytes')]
        tmo = r['drained'][(p_, 'LargeMessageDroppedTasksDueToTimeout')] - r['pre'][(p_, 'LargeMessageDroppedTasksDueToTimeout')]
        comp = r['drained'][(p_, 'LargeMessageCompletedTasks')] - r['late'][(p_, 'LargeMessageCompletedTasks')]
        expect(f'[{sc}] {p_}: after the lift pending bytes return to 0 ({pend}), timed-out count = accepted ({tmo} = {r["acc"][p_]}), completed count does not move ({comp})', pend == 0 and tmo == r['acc'][p_] and comp == 0)
    expect(f'[{sc}] the parked delivery threads showed in the dump (found {r["parked"]}, expected {len(peers)})', r['parked'] >= len(peers))
    expect(f'[{sc}] liveness probe delivered: R1 completed count +1 ({r["probe"]})', r['probe'].get('R1') == 1)
    # RF = 1 only: client errors ~ overload count
    if len(peers) == 1 and r['errors'] is not None and drops:
        ov = r['ref'][pe]
        expect(f'[{sc}] stress failed attempts ~ overload_count (+- threads in flight): {r["attempts"]} ({r["errors"]} operations) vs {ov}', abs(r['attempts'] - ov) <= threads)
    # heap
    if r['heap5'] is not None and heap_idle is not None:
        dh = (r['heap5'] - heap_idle) * 1024
        Xs = sum(r['X'].values())
        note(f'[{sc}] heap: used at ~5 s {r["heap5"]} KiB; idle floor {heap_idle} KiB (spread {spread} KiB); delta {dh} B; delta / X = {dh / Xs:.2f} (X = {Xs}); adjudicable (delta > 3 x spread): {dh > 3 * spread * 1024}')


def config_check(cfg, cap, E, G, tag):
    """9b 'Confirm it took effect': the effective limits per connection, all three links of each of R1..R3"""
    ok = True
    for pe in PEERS:
        ls = [c for c in cfg if c['peer'].startswith(NODES[pe][0] + ':')]
        types = {c['type'] for c in ls}
        good = (len(ls) >= 3 and all(c['capacity'] == str(cap) and c['endpoint'] == str(E) and c['glob'] == str(G) for c in ls))
        note(f'config trace {pe}: {len(ls)} connections {sorted(types)}; ' + '; '.join(sorted({f"capacity={c['capacity']} endpoint={c['endpoint']} global={c['glob']}" for c in ls})))
        ok &= good
    expect(f'[{tag}] config trace: every connection of R1..R3 has capacity={cap} endpoint={E} global={G}', ok)


# ============================================================================================================
if label == 'down':
    for n in PEERS:
        stop_node(n)
    stop_node('S')
    wipe_ring_state()
    note('down: ' + sh("ps -eo pid,cmd | grep '[C]assandraDaemon' | cut -c1-80", check=False)[1].strip() or 'no CassandraDaemon left')
    sys.exit(0)

cap, extras, E, G, drops, first_ref, hold, withA, rfs = LABELS[label]
sh(f'rm -rf {D}/jmx-classes {D}/hold-classes && mkdir -p {D}/jmx-classes {D}/hold-classes && javac -d {D}/jmx-classes {HARNESS}/Jmx.java '
   f'&& javac -d {D}/hold-classes {HARNESS}/Hold.java && jar cf {D}/stage4-hold.jar -C {D}/hold-classes .')
try:
    note(f'label {label}: capacity {cap} B; extras {extras}; predicted effective E {E}, G {G}; drops expected {drops}; hold {hold}; scenario A {withA}; RF {rfs}')
    # which rule and helper this run uses (a shakedown once ran a rule and a Hold.class older than the files on disk: results section 3, row 3)
    for f_ in ('hold-delivery.btm', 'send-config.btm', 'send-acquire.btm', 'Hold.java'):
        note(f'harness file {f_}: md5 ' + hashlib.md5(open(f'{HARNESS}/{f_}', 'rb').read()).hexdigest())
    note('Hold.class has held(): ' + str('held' in sh(f'javap -cp {D}/hold-classes stage4.Hold', check=False, quiet=True)[1]))
    ensure_ring()
    # schema (once per ring): keyspace1.standard1 via stress, against R1
    if not cql(NODES['R1'][0], "SELECT keyspace_name FROM system_schema.keyspaces WHERE keyspace_name = 'keyspace1'"):
        p, out = stress('schema', 1, n=1, node='R1')
        p.wait()
        note('schema keyspace1.standard1 created by one cassandra-stress write against R1 (S is not up yet): ' + str(bool(cql(NODES['R1'][0], "SELECT keyspace_name FROM system_schema.keyspaces WHERE keyspace_name = 'keyspace1'"))))
    note('RF -> ' + str(rfs[0]) + ': ' + set_rf(rfs[0]))
    # S: reset (9b), start with the agent
    stop_node('S')
    for sub in ('hints', 'saved_caches'):
        sh(f'rm -rf {SSQ}/S/{sub} && mkdir -p {SSQ}/S/{sub}', check=False, quiet=True)
    if os.path.exists(SSQ + '/S/logs'):
        os.rename(SSQ + '/S/logs', SSQ + '/S/logs.' + time.strftime('%Y%m%d-%H%M%S'))
    yaml_extra = [(SEND_CAP, str(cap // 1024) + 'KiB')] + list(extras.items())
    agent = (f'-javaagent:{C}/build/lib/jars/byteman-4.0.20.jar=script:{HARNESS}/send-config.btm,script:{HARNESS}/send-acquire.btm,'
             f'script:{HARNESS}/hold-delivery.btm,listener:true -Xbootclasspath/a:{D}/stage4-hold.jar -Dstage4.byteman.out={TRACE} -Dstage4.hold.file={HOLD}')
    if os.path.exists(HOLD):
        os.remove(HOLD)
    t_start = now_ms()
    start_node('S', extra_env={'JVM_EXTRA_OPTS': agent}, extras=yaml_extra, tag='-' + label)
    wait_up('S', 4)
    sh(f'java -cp {C}/build/lib/jars/byteman-submit-4.0.20.jar org.jboss.byteman.agent.submit.Submit -l > {D}/submit-l.txt 2>&1', check=False)
    import difflib
    shipped = sh(f'git -C {C} show HEAD:conf/cassandra.yaml', quiet=True)[1].splitlines()
    mine = open(f'{SSQ}/S/conf/cassandra.yaml').read().splitlines()
    open(f'{D}/S-yaml.diff', 'w').write('\n'.join(difflib.unified_diff(shipped, mine, 'shipped', 'S', lineterm='')))
    sh(f"tr '\\0' ' ' < /proc/{s_pid()}/cmdline > {D}/S-cmdline.txt", check=False, quiet=True)
    discover_scopes()
    # config trace: the connections to R1..R3 exist once S is UN and has gossiped with them
    time.sleep(5)
    cfg, _, _ = read_trace(t_start, now_ms() + 1000)
    config_check(cfg, cap, E, G, label)

    # ---- idle control: gauges, table, heap three times 5 s apart
    idle = jmx_snapshot('idle')
    note('idle: large-link pending bytes ' + str({p: idle[(p, "LargeMessagePendingBytes")] for p in PEERS}) + '; overload counts ' + str({p: idle[(p, "LargeMessageDroppedTasksDueToOverload")] for p in PEERS}))
    expect('idle: pending bytes of the large links are 0 and no overload', all(idle[(p, 'LargeMessagePendingBytes')] == 0 and idle[(p, 'LargeMessageDroppedTasksDueToOverload')] == 0 for p in PEERS))
    hs = []
    for i in range(3):
        hs.append(heap_used_kb())
        if i < 2:
            time.sleep(5)
    heap_idle = statistics.mean(hs) if all(h is not None for h in hs) else None
    spread = (max(hs) - min(hs)) if heap_idle is not None else None
    note(f'idle heap used after full GC (KiB): {hs}; mean {heap_idle}; spread {spread}')

    # ---- hold check (9e before the cluster tier, step 2): the first trigger is its own instrument check
    if hold:
        open(HOLD, 'w').close()
        t_a = now_ms()
        p, out = stress('holdcheck', 1, n=1)
        # the stress JVM takes about 6 s to send its write: wait for the write's acquire line (up to 40 s), not a fixed sleep
        for _ in range(80):
            _, acq_w, _ = read_trace(t_a, now_ms())
            if any(x['outcome'] == 'SUCCESS' for x in large_lines(acq_w, 'R1')):
                break
            time.sleep(0.5)
        time.sleep(1)
        a = jmx_snapshot('holdcheck-held', ['R1'])
        time.sleep(3)
        b = jmx_snapshot('holdcheck-held2', ['R1'])
        _, td = sh(f'jcmd {s_pid()} Thread.print', check=False, quiet=True, timeout=60)
        open(f'{D}/holdcheck-threads.txt', 'w').write(td)
        m_hold = a[('R1', 'LargeMessagePendingBytes')]
        _, acq0, _ = read_trace(t_a, now_ms())
        mm = [x['bytes'] for x in large_lines(acq0, 'R1') if x['outcome'] == 'SUCCESS']
        held_ok = (mm and m_hold == mm[0] and b[('R1', 'LargeMessagePendingBytes')] == m_hold and
                   b[('R1', 'LargeMessageCompletedTasks')] == a[('R1', 'LargeMessageCompletedTasks')] and 'stage4.Hold.park' in td)
        note(f'hold check: pending {m_hold} (trace bytes {mm}), 3 s later {b[("R1", "LargeMessagePendingBytes")]}, completed {a[("R1", "LargeMessageCompletedTasks")]} -> {b[("R1", "LargeMessageCompletedTasks")]}; Hold.park in the dump: {"stage4.Hold.park" in td}')
        if not held_ok:
            fail('the hold does not hold (hold check)')
        c0 = b[('R1', 'LargeMessageCompletedTasks')]
        os.remove(HOLD)
        time.sleep(2)
        r_ = jmx_snapshot('holdcheck-released', ['R1'])
        wait_proc(p, 30, 'holdcheck stress')
        if not (r_[('R1', 'LargeMessageCompletedTasks')] == c0 + 1 and r_[('R1', 'LargeMessagePendingBytes')] == 0):
            fail(f'the hold was not released by removing the file (completed {c0} -> {r_[("R1", "LargeMessageCompletedTasks")]}, pending {r_[("R1", "LargeMessagePendingBytes")]})')
        note('hold trace: ' + ' | '.join(read_trace(t_a, now_ms())[2]))
        note('hold check passed: the write was held (pending = M, completed unchanged, thread parked in Hold.park) and delivered by itself after the file was removed')

    # ---- scenario A
    if withA:
        rA = scenario('A', THREADS_A, LOAD_A, rfs[0], hold, cap, E, G, drops, first_ref, heap_idle, PEERS)
        M = rA['M']
        note(f'[A] M = {M}; X = {rA["X"]["R1"]}; accepted {rA["acc"]["R1"]}; refused {rA["ref"]["R1"]}; drain settled in {rA["settle"]} s; probe {rA["probe"]}')
        expect(f'[A] X = 2 M within +-1 message ({rA["X"]["R1"]} vs {2 * M if M else None})', M is not None and abs(rA['X']['R1'] - 2 * M) <= M)
        expect('[A] no reserve use and no drop', rA['ref']['R1'] == 0 and max([x['res'] for x in rA['rows'] if x['peer'].startswith(NODES['R1'][0] + ':')], default=0) == 0)
        expect(f'[A] the parked link drained after the lift and the probe was delivered ({rA["probe"]})', rA['probe'].get('R1') == 1)

    # ---- scenario B (one per RF in the peer sweep)
    results = []
    for rf in rfs:
        if rf != rfs[0] or len(rfs) > 1:
            note(f'RF -> {rf}: ' + set_rf(rf))
            time.sleep(3)
        sc = 'B' if len(rfs) == 1 else f'B-rf{rf}'
        if not hold:
            sc = 'B-nohold'
        rB = scenario(sc, THREADS_B, LOAD_B, rf, hold, cap, E, G, drops, first_ref, heap_idle, PEERS)
        adjudicate_B(rB, cap, E, G, drops, first_ref, hold, THREADS_B, heap_idle, spread)
        results.append(rB)
    # peer sweep
    if len(rfs) > 1:
        for rB in results:
            P, M = len(rB['peers']), rB['M']
            tot = sum(rB['X'][p] for p in rB['peers'])
            lo, hi = P * cap + G - (P + 1) * M, P * cap + G
            expect(f'[{rB["sc"]}] P = {P}: sum of the links\' peaks within (P*C + G - (P+1)*M, P*C + G] = ({lo}, {hi}]: {tot}', lo < tot <= hi)
            expect(f'[{rB["sc"]}] P = {P}: each link at least C - M ({cap - M}): ' + str({p: rB['X'][p] for p in rB['peers']}), all(rB['X'][p] >= cap - M for p in rB['peers']))
            gauges = {p: max([x['res'] for x in rB['rows'] if x['peer'].startswith(NODES[p][0] + ':')], default=0) for p in rB['peers']}
            expect(f'[{rB["sc"]}] P = {P}: each peer\'s reserve gauge at most {E} and their sum at most G = {G}: {gauges}', all(v <= E for v in gauges.values()) and sum(gauges.values()) <= G)
    # config trace summary for the whole run
    note('done: label ' + label)
finally:
    cleanup()
