#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of hints-HintsBuffer-put-slabCapacity--autonomous (case file as amended 2026-10-26).
usage: cluster-run.py <arm> | analyze | down
  <arm>   one node lifetime (B3e steps 1-7): wipe ~/s4-hb-data, write the yaml of A and B, start A (Byteman: hb.btm observation
          + hold-flush.btm, which delays every hints-buffer flush by 10000 ms (attempt 1 used 2000 ms: too short, see results 3); -Dcassandra.MAX_HINT_BUFFERS=n), start B, wait for UN,
          create ks (RF 2), stop B (not in `ctl`) and wait until A sees it DN, GC A twice and take the baseline, then ONE workload
          through A at CL ANY, protocol 4:
            hints  500,000 INSERTs of 2,000 bytes into ks.small, 200 in flight (about 1.05 GB of hints)
            large  (arm L) the large-hint boundary: a calibration INSERT, then one INSERT per mutation size M in
                   m-100, m-23, m-22, m-15, m-12, m-11 (m = max_mutation_size) into ks.big, 3 s apart
          then 25 s idle (two hints_flush_period), a mark, GC twice, 10 s, a mark. A is sampled every 1 s (java.nio direct pool
          MemoryUsed/Count, heap, TotalHints; VmRSS; hints directory bytes).
  Arms (yaml lines; n = MAX_HINT_BUFFERS; expected slab): ctl A-config n=3, peer up (no hints) | A3 mms 4MiB seg 8MiB n=3 (32 MiB)
          | A2 (n=2) | A6 (n=6) | C3 default config (32 MiB) | D3 mms 24MiB seg 48MiB (48 MiB) | B3 mms 40MiB seg 80MiB (80 MiB)
          | L default config, native_transport_max_message_size 20MiB, large-hint boundary.
  analyze reads every <arm>/phases.json and writes analysis.txt (the B3f relations across arms; reading rules fixed in README.md).
  down    stop every node of this harness (by pid file).
Ports of this agent: JMX 7320 (A) 7321 (B), Byteman 9320 (A), native 9342, storage 7020, loopback 127.0.20.1 (A) .2 (B).
Output: ~/s4-hb-logs/<HB_RUN>/cluster/<arm>/ (summary.txt with EXPECTED lines, session.log, samples.csv, phases.json, hb.trace,
A-log-excerpt.txt). Exit 1: a set-up check failed; the nodes are then stopped. Environment: HB_RUN (default run1), CASSANDRA_HOME
(default ~/s4-hb), HB_N (row count override for a shakedown). Adapted from the hints-CompressedHintsWriter harness's cluster-run.py."""
import json, os, re, statistics, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/s4-hb')
HARNESS = os.path.dirname(os.path.abspath(__file__))
HW = os.environ.get('HB', HOME + '/s4-hb-data')
RUN = os.environ.get('HB_RUN', 'run1')
KIB, MIB = 1024, 1 << 20
BAND = 2 * MIB
NROWS, ROWB, CONC = int(os.environ.get('HB_N', 500000)), 2000, 200
HOLD_MS = 10000
NODES = {'A': ('127.0.20.1', 7320), 'B': ('127.0.20.2', 7321)}
CFG_A = ['max_mutation_size=4MiB', 'commitlog_segment_size=8MiB']
ARMS = {   # yaml lines, n, peer down, workload, expected slab MiB, max_mutation_size MiB
    'ctl': (CFG_A, 3, False, 'hints', 32, 4),
    'A3': (CFG_A, 3, True, 'hints', 32, 4), 'A2': (CFG_A, 2, True, 'hints', 32, 4), 'A6': (CFG_A, 6, True, 'hints', 32, 4),
    'C3': ([], 3, True, 'hints', 32, 16),
    'D3': (['max_mutation_size=24MiB', 'commitlog_segment_size=48MiB'], 3, True, 'hints', 48, 24),
    'B3': (['max_mutation_size=40MiB', 'commitlog_segment_size=80MiB'], 3, True, 'hints', 80, 40),
    'L': (['native_transport_max_message_size=20MiB'], 3, True, 'large', 32, 16),
}
CLIENT = HARNESS + '/client.py'
BTM = HARNESS + '/hb.btm'
HOLDBTM = HARNESS + '/hold-flush.btm'
BYTEMAN = C + '/build/lib/jars/byteman-4.0.20.jar'
JMXCP = HW + '/jmx'
COLS = [('direct_used', 'java.nio:type=BufferPool,name=direct', 'MemoryUsed'),
        ('direct_count', 'java.nio:type=BufferPool,name=direct', 'Count'),
        ('heap_used', 'java.lang:type=Memory', 'HeapMemoryUsage'),
        ('total_hints', 'org.apache.cassandra.metrics:type=Storage,name=TotalHints', 'Count')]
SETTINGS = ['hinted_handoff_enabled', 'max_mutation_size', 'commitlog_segment_size', 'hints_flush_period', 'write_request_timeout',
            'native_transport_timeout', 'native_transport_max_message_size', 'storage_port', 'native_transport_port']
NAMES = [c for c, _, _ in COLS] + ['rss', 'hints_dir_bytes']

args = sys.argv[1:]
if not args or (args[0] in ARMS and len(args) != 1) or (args[0] not in ARMS and args[0] not in ('analyze', 'down')):
    sys.exit(__doc__)
arm = args[0]
ROOT = f'{HOME}/s4-hb-logs/{RUN}/cluster'
LOGS = f'{ROOT}/{arm}'
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
SUMMARY = open(LOGS + '/summary.txt', 'a' if arm in ('down', 'analyze') else 'w')
EXPECT = {'yes': 0, 'no': 0}
TRACE = LOGS + '/hb.trace'

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
    f = f'{HW}/{node}/cassandra.pid'
    try:
        pid = int(open(f).read().strip())
        return pid if 'CassandraDaemon' in open(f'/proc/{pid}/cmdline').read() else None
    except (ValueError, OSError):
        return None


def mine():
    """processes whose command line names this harness's data directory (never another agent's node)"""
    return sh(f"ps -eo pid,cmd | grep '[{HW[0]}]{HW[1:]}/' | grep -v 'grep' | cut -c1-160 || true", check=False, quiet=True)[1].strip()


def busy_ports():
    out = sh("ss -ltn", check=False, quiet=True)[1]
    want = ['127.0.20.1:7020', '127.0.20.1:9342', '127.0.20.1:7320', '127.0.0.1:7320', '127.0.0.1:9320', '127.0.0.1:7321',
            '127.0.0.1:7322', '127.0.20.2:7020', '127.0.20.3:7020', '*:9320', '*:7320']
    return [w for w in want if re.search(r'\s' + re.escape(w) + r'\s', out)]


def stop_node(node):
    if pid_of(node) is None:
        return
    try:
        sh(f'bin/nodetool -p {NODES[node][1]} stopdaemon', check=False, timeout=180)
    except subprocess.TimeoutExpired:
        log(f'{node}: stopdaemon timed out; falling back to kill -9')
    for _ in range(120 if pid_of(node) is not None else 0):
        if pid_of(node) is None:
            return
        time.sleep(1)
    pid = pid_of(node)
    if pid is not None:
        log(f'{node} did not stop; kill -9 {pid}')
        subprocess.run(['kill', '-9', str(pid)])
        time.sleep(2)


def stop_all():
    for n in ('C', 'B', 'A'):
        stop_node(n)
    left = mine()
    if left:
        log('WARNING: processes of this harness still running: ' + left[:300])
    return not left


CHILDREN = []


def fail(msg):
    note('FAIL: ' + msg)
    for p in CHILDREN:
        if p.poll() is None:
            p.kill()
    stop_all()
    sys.exit(1)


def client(*a, timeout=3600):
    rc, out = sh(f'python3 -I {CLIENT} ' + ' '.join(str(x) for x in a), timeout=timeout, check=False,
                 env=dict(os.environ, CASSANDRA_HOME=C))
    js = [l for l in out.splitlines() if l.startswith('{')]
    if rc != 0 or not js:
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



def status(via):
    _, st = sh(f'bin/nodetool -p {NODES[via][1]} status', check=False, quiet=True)
    return {a: s for s, a in re.findall(r'^([UD][NLJM])\s+(\S+)\s', st, re.M)}


def wait_up(nodes, timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        ok = True
        for via in nodes:
            if pid_of(via) is None:
                fail(f'{via} died during start')
            st = status(via)
            _, sb = sh(f'bin/nodetool -p {NODES[via][1]} statusbinary', check=False, quiet=True)
            ok = ok and all(st.get(NODES[n][0]) == 'UN' for n in nodes) and re.search(r'^running\s*$', sb, re.M) is not None
        if ok:
            log(f'{nodes} UN and serving after {time.time() - t0:.0f} s')
            return
        time.sleep(3)
    fail(f'{nodes} not UN within the timeout')


def rss_kb(pid):
    try:
        for l in open(f'/proc/{pid}/status'):
            if l.startswith('VmRSS:'):
                return int(l.split()[1])
    except OSError:
        return None


def dir_bytes(d):
    t = 0
    for root, _, files in os.walk(d):
        for f in files:
            try:
                t += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return t


class Sampler:
    """A every 1 s: one Jmx poll JVM for the JMX columns; a thread for VmRSS and the hints directory"""

    def __init__(self, pid):
        self.stop = f'{LOGS}/sampler.stop'
        if os.path.exists(self.stop):
            os.remove(self.stop)
        self.jf = open(f'{LOGS}/samples-jmx.csv', 'w')
        cmd = ['java', '-cp', JMXCP, 'Jmx', str(NODES['A'][1]), 'poll', '1000', '100000000', self.stop]
        for _, bean, attr in COLS:
            cmd += [bean, attr]
        log('+ ' + ' '.join(cmd))
        self.p = subprocess.Popen(cmd, stdout=self.jf, stderr=subprocess.STDOUT)
        CHILDREN.append(self.p)
        self.side = []
        self.alive = True
        self.t = threading.Thread(target=self._side, args=(pid,), daemon=True)
        self.t.start()

    def _side(self, pid):
        nxt = time.time()
        while self.alive:
            self.side.append((int(time.time() * 1000), rss_kb(pid), dir_bytes(f'{HW}/A/hints')))
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
        self.jf.close()
        rows = []
        for l in open(f'{LOGS}/samples-jmx.csv').read().splitlines():
            parts = l.split(',')
            if len(parts) == len(COLS) + 1 and parts[0].isdigit():
                rows.append([int(parts[0])] + [num(x) for x in parts[1:]])
        out, j = [], 0
        for r in rows:
            while j + 1 < len(self.side) and abs(self.side[j + 1][0] - r[0]) <= abs(self.side[j][0] - r[0]):
                j += 1
            sd = self.side[j] if self.side else (None, None, None)
            out.append(r + [None if sd[1] is None else sd[1] * 1024.0, sd[2]])
        with open(f'{LOGS}/samples.csv', 'w') as f:
            f.write('ms,' + ','.join(NAMES) + '\n')
            for r in out:
                f.write(','.join('' if v is None else str(int(v)) for v in r) + '\n')
        return out


def col(r, name):
    return r[1 + NAMES.index(name)]


def at(rows, ms):
    best = None
    for r in rows:
        if r[0] <= ms:
            best = r
    return best




def start_node(node, yaml, n):
    if pid_of(node) is not None:
        fail(f'{node} is already running')
    _, y = sh(f'bash {HARNESS}/make-node-yaml.sh {node} ' + ' '.join(f"'{a}'" for a in yaml),
              env=dict(os.environ, CASSANDRA_HOME=C, HB=HW))
    note(y.strip().splitlines()[-1][:900])
    N = f'{HW}/{node}'
    env = dict(os.environ, CASSANDRA_CONF=N + '/conf', CASSANDRA_LOG_DIR=N + '/logs',
               MAX_HEAP_SIZE='2G' if node == 'A' else '1G')
    env.pop('HEAP_NEWSIZE', None); env.pop('JVM_EXTRA_OPTS', None)
    if node == 'A':
        extra = (f'-Dcassandra.MAX_HINT_BUFFERS={n} -javaagent:{BYTEMAN}=script:{BTM},script:{HOLDBTM},listener:true,port:9320 '
                 f'-Dorg.jboss.byteman.verbose=false -Dstage4.trace={TRACE} -Dstage4.hold.ms={HOLD_MS} -Dstage4.hold.out={LOGS}/hold.txt')
        env['JVM_EXTRA_OPTS'] = extra
        note(f'A JVM_EXTRA_OPTS: {extra}')
    sh(f"bash -c 'ulimit -n 100000 && exec bin/cassandra -p {N}/cassandra.pid' > {N}/stdout.txt 2>&1", env=env)
    for _ in range(30):
        time.sleep(1)
        if pid_of(node) is not None:
            return
    fail(f'{node} did not start; see {N}/stdout.txt')

def grep_log(node, pats):
    f = f'{HW}/{node}/logs/system.log'
    out = {p: [] for p in pats}
    nerr = nwarn = 0
    if os.path.exists(f):
        for l in open(f, errors='replace'):
            if l.startswith('ERROR'):
                nerr += 1
            if l.startswith('WARN'):
                nwarn += 1
            for p in pats:
                if re.search(p, l):
                    out[p].append(l.rstrip()[:500])
    return out, nerr, nwarn


def gc(pid):
    for _ in range(2):
        sh(f'jcmd {pid} GC.run', check=False)
        time.sleep(3)




def read_trace():
    tr = {'created': [], 'waiting': [], 'alloc': [], 'allocreject': [], 'flushrun': []}
    if not os.path.exists(TRACE):
        return tr
    for l in open(TRACE, errors='replace'):
        l = l.strip()
        kind = l.split(' ', 1)[0]
        if kind in tr:
            tr[kind].append(dict(re.findall(r'(\w+)=(\S+)', l)) | {'line': l[:300]})
    return tr


def stop_all_and_clean():
    ok = stop_all()
    sh(f'rm -rf {HW}/A/data {HW}/A/commitlog {HW}/A/hints {HW}/A/saved_caches {HW}/A/cdc_raw {HW}/B/data {HW}/B/commitlog {HW}/B/hints {HW}/B/saved_caches {HW}/B/cdc_raw', check=False)
    return ok


def lifetime():
    yaml, n, peer_down, phase, slab_mib, m_mib = ARMS[arm]
    S = slab_mib * MIB
    note(f'cluster-run {arm} {time.strftime("%F %T %Z")} host {os.uname().nodename.split(".")[0]} tree {C} '
         f'{sh("git describe --tags; git rev-parse --short HEAD", quiet=True)[1].split()} HB_N={os.environ.get("HB_N", "(default)")}')
    note('harness md5: ' + sh('md5sum cluster-run.py client.py make-node-yaml.sh Jmx.java hb.btm hold-flush.btm', quiet=True,
                              cwd=HARNESS)[1].replace('\n', ' ')[:800])
    note(f'arm {arm}: yaml {yaml or "(none: defaults)"}; MAX_HINT_BUFFERS {n}; peer down {peer_down}; workload {phase}; '
         f'expected slab {slab_mib} MiB, max_mutation_size {m_mib} MiB; hold {HOLD_MS} ms per flush')
    bp = busy_ports()
    if bp or mine():
        fail(f'ports in use or processes of this harness running: {bp} {mine()[:200]}')
    _, df = sh(f'df -k {HOME}', quiet=True)
    free_gb = int(df.splitlines()[-1].split()[3]) / 1048576
    note(f'free on {HOME}: {free_gb:.1f} GiB')
    if free_gb < 8:
        fail('less than 8 GiB free')
    sh(f'rm -rf {HW}/A {HW}/B')
    if os.path.exists(TRACE):
        os.remove(TRACE)
    os.makedirs(JMXCP, exist_ok=True)
    sh(f'javac -d {JMXCP} {HARNESS}/Jmx.java')
    rc, out = sh(f'java -cp {C}/build/lib/jars/byteman-4.0.20.jar:{C}/build/apache-cassandra-5.0.9-SNAPSHOT.jar:{C}/build/classes/main:'
                 f'$(ls {C}/lib/*.jar | tr "\\n" ":") org.jboss.byteman.check.TestScript {BTM} {HOLDBTM} 2>&1 | tail -3', check=False)
    note('Byteman TestScript: ' + out.strip().replace('\n', ' | ')[-400:])

    start_node('A', yaml, n)
    wait_up(['A'])
    start_node('B', yaml, n)
    wait_up(['A', 'B'])
    sch = client('schema', NODES['A'][0], 2)
    if not sch or not sch.get('agreement'):
        fail(f'schema: {sch}')
    note(f'schema: {sch}')
    st = client('settings', NODES['A'][0], *SETTINGS)
    if not st:
        fail('settings read-back failed')
    note(f'A settings: {st["settings"]}')
    args_a = open(f'/proc/{pid_of("A")}/cmdline').read().replace('\0', ' ')
    note('A command line: ' + ' '.join(re.findall(r'-XX:MaxDirectMemorySize=\S+|-Xmx\S+|-Dcassandra.MAX_HINT_BUFFERS=\S+|port:\d+|-Dstage4.hold.ms=\S+', args_a)))
    expect(f'read-back: storage 7020, native 9342 ({st["settings"].get("storage_port")}, {st["settings"].get("native_transport_port")})',
           str(st['settings'].get('storage_port')) == '7020' and str(st['settings'].get('native_transport_port')) == '9342')
    expect(f'A runs with MAX_HINT_BUFFERS={n} on its command line', f'-Dcassandra.MAX_HINT_BUFFERS={n}' in args_a)
    mms_rb = str(st['settings'].get('max_mutation_size'))
    note(f'max_mutation_size read-back: {mms_rb} (expected {m_mib} MiB)')

    t_bstop = int(time.time() * 1000)
    if peer_down:
        sh(f'bin/nodetool -p {NODES["B"][1]} drain', check=False, timeout=300)
        stop_node('B')
        if pid_of('B') is not None:
            fail('B did not stop')
        for _ in range(90):
            if status('A').get(NODES['B'][0]) == 'DN':
                break
            time.sleep(1)
        else:
            fail('A does not see B down')
        note(f'B stopped and seen DN by A after {(time.time() * 1000 - t_bstop) / 1000:.1f} s')
    else:
        note('ctl: B stays up; no hints are expected')
    if client('probe', NODES['A'][0]) is None:
        fail('probe through A failed')

    pidA = pid_of('A')
    smp = Sampler(pidA)
    time.sleep(3)
    gc(pidA)
    time.sleep(10)
    ph = {'arm': arm, 'n': n, 'slab_expected': S, 'm_mib': m_mib, 'phase': phase, 'peer_down': peer_down, 'settings': st['settings'], 'ms_bstop': t_bstop}
    ph['ms_base'] = int(time.time() * 1000)
    time.sleep(2)
    tr0 = read_trace()
    note(f'trace before the workload: { {k: len(v) for k, v in tr0.items()} }')

    if phase == 'hints':
        note(f'hints: {NROWS} INSERTs of {ROWB} B at CL ANY, {CONC} in flight')
        res = client('hints', NODES['A'][0], NROWS, ROWB, CONC)
        if res is None:
            smp.close(); fail('workload client failed')
        note(f'workload result: { {k: v for k, v in res.items() if k != "errors"} } errors={res.get("errors")}')
        ph['workload'] = res
    else:
        m = m_mib * MIB
        steps = []
        # calibration: M0 = hintSize - 11 is read from the trace; c = M0 - L0 (constant while the length vint keeps its width)
        L0 = m - 4096
        r0 = client('one', NODES['A'][0], 1, L0)
        time.sleep(3)
        trc = read_trace()
        h0 = [int(a['hint']) for a in trc['alloc'] if a.get('ms') and int(a['ms']) <= r0['ms_end'] + 1000]
        if not h0:
            smp.close(); fail('calibration: no alloc trace line')
        c = h0[-1] - 11 - L0
        note(f'calibration: blob {L0} -> hintSize {h0[-1]} -> M {h0[-1] - 11}; c = {c} bytes of mutation overhead; client {r0}')
        steps.append({'label': 'calibration', 'M': h0[-1] - 11, 'L': L0, 'client': r0})
        for k, (label, dM) in enumerate([('m-100', 100), ('m-23', 23), ('m-22', 22), ('m-15', 15), ('m-12', 12), ('m-11', 11)]):
            M = m - dM
            L = M - c
            t0 = int(time.time() * 1000)
            r = client('one', NODES['A'][0], 10 + k, L)
            time.sleep(3)
            th = jmx('A', ('org.apache.cassandra.metrics:type=Storage,name=TotalHints', 'Count'))
            tot = num(list(th.values())[0]) if th else None
            tr = read_trace()
            al = [a for a in tr['alloc'] if int(a['ms']) >= t0]
            rj = [a for a in tr['allocreject'] if int(a['ms']) >= t0]
            steps.append({'label': label, 'M_target': M, 'L': L, 'client': r, 'alloc': [a['hint'] for a in al],
                          'reject': [a['hint'] for a in rj], 'total_hints_after': tot})
            note(f'step {label}: M target {M}, blob {L}, client {r.get("outcome")} {r.get("message", "")[:120]}; alloc hint {[a["hint"] for a in al]}; '
                 f'rejected {[a["hint"] for a in rj]}; TotalHints {tot}')
        ph['steps'] = steps
        ph['c'] = c
    ph['ms_end_work'] = int(time.time() * 1000)
    time.sleep(25)
    ph['ms_pre_gc'] = int(time.time() * 1000)
    time.sleep(2)
    gc(pidA)
    time.sleep(10)
    ph['ms_end'] = int(time.time() * 1000)
    time.sleep(2)
    rows = smp.close()

    cnt = jmx('A', ('org.apache.cassandra.metrics:type=Storage,name=TotalHints', 'Count'))
    ph['total_hints'] = {f'{b}|{a}': v for (b, a), v in cnt.items()}
    ph['peer_status_end'] = status('A').get(NODES['B'][0])
    ph['hints_dir_end'] = dir_bytes(f'{HW}/A/hints')
    _, ls = sh(f'ls -l {HW}/A/hints', check=False, quiet=True)
    open(f'{LOGS}/hints-ls.txt', 'w').write(ls)
    pats = [r'too large', r'Hint of', r'[Hh]inted handoff', r'java.lang.OutOfMemoryError', r'[Dd]irect buffer memory', r'MutationExceededMaxSize']
    lg, nerr, nwarn = grep_log('A', pats)
    ph['log_counts'] = {p: len(v) for p, v in lg.items()} | {'ERROR': nerr, 'WARN': nwarn}
    with open(f'{LOGS}/A-log-excerpt.txt', 'w') as f:
        for p, v in lg.items():
            f.write(f'## {p}: {len(v)} lines\n' + '\n'.join(v[-10:]) + '\n')
        f.write(f'## ERROR lines {nerr}, WARN lines {nwarn}\n')
        for l in open(f'{HW}/A/logs/system.log', errors='replace'):
            if l.startswith('ERROR') or l.startswith('WARN'):
                f.write(l[:400])
    tr = read_trace()
    ph['trace_counts'] = {k: len(v) for k, v in tr.items()}
    stop_node('A')
    clean = stop_all_and_clean()
    if not clean:
        note('WARNING: a process of this harness is left')
    ph['clean_stop'] = clean

    base = at(rows, ph['ms_base'] + 1500)
    post = at(rows, ph['ms_end'] + 1500)
    k0 = sum(1 for a in tr['created'] if int(a['ms']) <= ph['ms_base'] + 1500)
    created_total = len(tr['created'])
    sizes = sorted({int(a['size']) for a in tr['created']})
    ph.update({'k0': k0, 'created_total': created_total, 'created_sizes': sizes, 'waiting': len(tr['waiting']),
               'base': {nm: col(base, nm) for nm in NAMES} if base else None, 'post': {nm: col(post, nm) for nm in NAMES} if post else None})
    after = [r for r in rows if r[0] > ph['ms_base'] and col(r, 'direct_used') is not None]
    d0 = col(base, 'direct_used') if base else None
    if after and d0 is not None:
        peak = max(after, key=lambda r: col(r, 'direct_used'))
        ph['peak_delta'] = col(peak, 'direct_used') - d0
        ph['peak_pool'] = ph['peak_delta'] + k0 * (sizes[0] if sizes else S)       # pool bytes = delta over baseline + slabs created before it
        ph['peak_ms'] = peak[0]
        work = [r for r in after if ph['ms_base'] < r[0] <= ph['ms_end_work']]
        if work:
            tail = work[len(work) // 2:]
            ph['plateau_range_second_half'] = max(col(r, 'direct_used') for r in tail) - min(col(r, 'direct_used') for r in tail)
            ph['hints_dir_first_to_last'] = [col(work[0], 'hints_dir_bytes'), col(work[-1], 'hints_dir_bytes')]
    json.dump(ph, open(f'{LOGS}/phases.json', 'w'), indent=1, default=str)

    # ---- EXPECTED lines (the B3f relations for this arm; the AI judges them in the results file) ----
    mb = lambda x: None if x is None else round(x / MIB, 2)
    note(f'readings: created slabs {created_total} (before baseline {k0}) sizes {sizes}; writers waited {len(tr["waiting"])} times; flushes {len(tr["flushrun"])}; '
         f'peak direct delta {mb(ph.get("peak_delta"))} MiB, peak pool bytes {mb(ph.get("peak_pool"))} MiB, plateau range {mb(ph.get("plateau_range_second_half"))} MiB; '
         f'hints dir {mb(ph["hints_dir_end"])} MiB; TotalHints {ph["total_hints"]}; log {ph["log_counts"]}')
    expect(f'all slabs are {slab_mib} MiB (sizes {sizes})', sizes == [S] or (arm == 'ctl' and sizes in ([S], [])))
    if phase == 'hints' and peer_down:
        expect(f'slabs created == n ({created_total} == {n}) (the cap binds)', created_total == n)
        expect(f'a writer waited at take() (disallow branch fired): {len(tr["waiting"])} lines', len(tr['waiting']) >= 1)
        expect(f'peak pool bytes {mb(ph.get("peak_pool"))} MiB within n x slab = {n * slab_mib} MiB + 2 MiB',
               ph.get('peak_pool') is not None and ph['peak_pool'] <= n * S + BAND)
        expect(f'peak pool bytes reached n x slab - 2 MiB (the ceiling was reached)', ph.get('peak_pool') is not None and ph['peak_pool'] >= n * S - BAND)
        expect(f'hints on disk ({mb(ph["hints_dir_end"])} MiB) exceed 4 x n x slab ({4 * n * slab_mib} MiB)', ph['hints_dir_end'] > 4 * n * S)
        expect(f'every row accepted (client ok {ph["workload"]["ok"]} of {NROWS})', ph['workload']['ok'] == NROWS)
    elif phase == 'hints':
        expect(f'ctl: no waiting writers and at most one slab created ({created_total}, waiting {len(tr["waiting"])})', created_total <= 1 and not tr['waiting'])
        expect(f'ctl: direct delta within +-2 MiB of baseline (peak delta {mb(ph.get("peak_delta"))} MiB)', abs(ph.get('peak_delta') or 0) <= BAND)
    else:
        for s_ in steps[1:]:
            lab = s_['label']
            hinted = lab in ('m-100', 'm-23')
            rej = lab in ('m-22', 'm-15', 'm-12')
            if hinted:
                expect(f'{lab}: hinted (no allocreject; alloc {s_["alloc"]}, reject {s_["reject"]})', not s_['reject'] and bool(s_['alloc']))
            elif rej:
                expect(f'{lab}: rejected at HintsBuffer.java:152 (alloc {s_["alloc"]}, reject {s_["reject"]})', bool(s_['reject']))
            else:
                note(f'{lab}: commit-log side, informational: client {s_["client"].get("outcome")}, alloc {s_["alloc"]}, reject {s_["reject"]}')
        th = [s_['total_hints_after'] for s_ in steps[1:]]
        note(f'TotalHints after each step: {th}')
    note(f'EXPECTED lines: {EXPECT["yes"]} yes, {EXPECT["no"]} no')
    return 0


def analyze():
    out = []
    ph = {}
    for a in ARMS:
        f = f'{ROOT}/{a}/phases.json'
        if os.path.exists(f):
            ph[a] = json.load(open(f))
    mb = lambda x: None if x is None else round(x / MIB, 2)
    for a, p in ph.items():
        out.append(f'{a}: n={p["n"]} slab={mb(p["slab_expected"])} created={p.get("created_total")} waiting={p.get("waiting")} '
                   f'peak_pool={mb(p.get("peak_pool"))} peak_delta={mb(p.get("peak_delta"))} plateau_range={mb(p.get("plateau_range_second_half"))} '
                   f'hints_dir={mb(p.get("hints_dir_end"))}')
    def rel(desc, cond):
        out.append(f'EXPECTED: {desc} — {"yes" if cond else "NO"}')
    P = lambda a: ph.get(a, {}).get('peak_pool')
    if all(P(a) is not None for a in ('A2', 'A3', 'A6')):
        rel(f'buffer-count series follows n: peak pool {mb(P("A2"))} / {mb(P("A3"))} / {mb(P("A6"))} MiB = 2/3/6 x 32 MiB within 2 MiB',
            all(abs(P(a) - n * 32 * MIB) <= BAND for a, n in (('A2', 2), ('A3', 3), ('A6', 6))))
    if all(P(a) is not None for a in ('A3', 'C3', 'D3', 'B3')):
        rel(f'slab series follows max_mutation_size: peak pool A3 {mb(P("A3"))} = C3 {mb(P("C3"))} (32 MiB floor), D3 {mb(P("D3"))} = 144, B3 {mb(P("B3"))} = 240 MiB within 2 MiB',
            abs(P('A3') - 96 * MIB) <= BAND and abs(P('C3') - 96 * MIB) <= BAND and abs(P('D3') - 144 * MIB) <= BAND and abs(P('B3') - 240 * MIB) <= BAND)
    open(f'{ROOT}/analysis.txt', 'w').write('\n'.join(out) + '\n')
    print('\n'.join(out))


if arm == 'down':
    stop_all()
    note('down: ' + (mine() or 'nothing left'))
elif arm == 'analyze':
    analyze()
else:
    try:
        sys.exit(lifetime())
    except SystemExit:
        raise
    except BaseException as e:
        note(f'EXCEPTION {type(e).__name__}: {e}')
        for p in CHILDREN:
            if p.poll() is None:
                p.kill()
        stop_all_and_clean()
        raise
