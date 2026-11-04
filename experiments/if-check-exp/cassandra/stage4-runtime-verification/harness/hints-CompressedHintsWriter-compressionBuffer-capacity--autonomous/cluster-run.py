#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of hints-CompressedHintsWriter-compressionBuffer-capacity--autonomous (case file amended
2026-10-25, B3 amendment items 1-6).
usage: cluster-run.py <arm> | analyze | down
  <arm>   one node lifetime (B3e steps 1-7, one workload per lifetime): wipe ~/s4-hw-data, write the yaml of A, B (and C in P2)
          with the arm's lines, start A (Byteman hw.btm attached, listener port 9114) then B (C), wait for UN and the client port,
          create ks (RF 2; RF 3 in P2), read the settings back, stop the peers (drain + stopdaemon) and wait until A sees them DN,
          GC A twice and take the baseline, then ONE workload through A at CL ONE, protocol 4:
            S  200,000 INSERTs of 1,024 random bytes into ks.small, 64 in flight
            L  200 INSERTs of 8 MiB (8,388,608 B) incompressible values into ks.big, 4 in flight
          then 25 s idle (two hints_flush_period of 10 s), a sample (pre-GC mark), GC A twice, 10 s, a sample (post-GC mark, the
          reading). A is sampled every 1 s (java.nio direct pool MemoryUsed/Count, heap, TotalHints; /proc VmRSS; hints dir bytes).
          Arms (B3 amendment 1): S LZ4 + S workload · US no compression + S workload (control of S) · D1, D2 LZ4 + L · F1 LZ4,
          max_hints_file_size 1MiB + L · H1 LZ4, max_hints_size_per_host 1MiB + L · U no compression + L (control of the L arms) ·
          P2 LZ4 + L with B and C down and RF 3 · M128 LZ4, commitlog_segment_size 128MiB + L (slab positive control).
  analyze reads every <arm>/phases.json and writes analysis.txt: the B3f relations across arms, with the frozen reading rules
          (B3 amendment 4: marks, slab correction, 2 MiB band; positive control item 5).
  down    stop every node of this harness (by pid file).
Three loopback nodes: A 127.0.14.1 (JMX 7814, Byteman 9114, native 9146, storage 7014; seed, coordinator, measured), B 127.0.14.2
(JMX 7815), C 127.0.14.3 (JMX 7816). Output: ~/s4-hw-logs/<HW_RUN>/cluster/<arm>/ (summary.txt with EXPECTED lines, session.log,
samples.csv, phases.json, hw.trace, A-log-excerpt.txt). Exit 1: a set-up check failed; the nodes are then stopped. A reading
that misses a prediction is recorded as EXPECTED ... NO. Environment: HW_RUN (default run1), CASSANDRA_HOME (default ~/s4-hw),
HW_N (workload count override for a shakedown). From the max_mutation_size harness's cluster-run.py."""
import json, os, re, statistics, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/s4-hw')
HARNESS = os.path.dirname(os.path.abspath(__file__))
HW = os.environ.get('HW', HOME + '/s4-hw-data')
RUN = os.environ.get('HW_RUN', 'run1')
KIB, MIB = 1024, 1 << 20
BAND = 2 * MIB
SMALL, NSMALL, NCONC_S = 1024, int(os.environ.get('HW_N', 200000)), 64
BIG, NBIG, NCONC_L = 8 * MIB, int(os.environ.get('HW_N', 200)), 4
NODES = {'A': ('127.0.14.1', 7814), 'B': ('127.0.14.2', 7815), 'C': ('127.0.14.3', 7816)}
LZ4 = 'hints_compression=LZ4Compressor'
ARMS = {   # yaml lines, workload, peers down, compressed
    'S': ([LZ4], 'S', 1, True), 'US': ([], 'S', 1, False),
    'D1': ([LZ4], 'L', 1, True), 'D2': ([LZ4], 'L', 1, True),
    'F1': ([LZ4, 'max_hints_file_size=1MiB'], 'L', 1, True),
    'H1': ([LZ4, 'max_hints_size_per_host=1MiB'], 'L', 1, True),
    'U': ([], 'L', 1, False),
    'P2': ([LZ4], 'L', 2, True),
    'M128': ([LZ4, 'commitlog_segment_size=128MiB'], 'L', 1, True),
}
CLIENT = HARNESS + '/client.py'
BTM = HARNESS + '/hw.btm'
BYTEMAN = C + '/build/lib/jars/byteman-4.0.20.jar'
JMXCP = HW + '/jmx'
COLS = [('direct_used', 'java.nio:type=BufferPool,name=direct', 'MemoryUsed'),
        ('direct_count', 'java.nio:type=BufferPool,name=direct', 'Count'),
        ('heap_used', 'java.lang:type=Memory', 'HeapMemoryUsage'),
        ('total_hints', 'org.apache.cassandra.metrics:type=Storage,name=TotalHints', 'Count')]
SETTINGS = ['hinted_handoff_enabled', 'hints_compression', 'max_hints_file_size', 'max_hints_size_per_host',
            'max_mutation_size', 'commitlog_segment_size', 'hints_flush_period', 'write_request_timeout',
            'native_transport_timeout', 'storage_port', 'native_transport_port']
NAMES = [c for c, _, _ in COLS] + ['rss', 'hints_dir_bytes']

args = sys.argv[1:]
if not args or (args[0] in ARMS and len(args) != 1) or (args[0] not in ARMS and args[0] not in ('analyze', 'down')):
    sys.exit(__doc__)
arm = args[0]
ROOT = f'{HOME}/s4-hw-logs/{RUN}/cluster'
LOGS = f'{ROOT}/{arm}'
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
SUMMARY = open(LOGS + '/summary.txt', 'a' if arm in ('down', 'analyze') else 'w')
EXPECT = {'yes': 0, 'no': 0}
TRACE = LOGS + '/hw.trace'


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
    want = ['127.0.14.1:7014', '127.0.14.1:9146', '127.0.14.1:7814', '127.0.0.1:7814', '127.0.0.1:9114', '127.0.0.1:7815',
            '127.0.0.1:7816', '127.0.14.2:7014', '127.0.14.3:7014', '*:9114', '*:7814']
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


def start_node(node, yaml):
    if pid_of(node) is not None:
        fail(f'{node} is already running')
    _, y = sh(f'bash {HARNESS}/make-node-yaml.sh {node} ' + ' '.join(f"'{a}'" for a in yaml),
              env=dict(os.environ, CASSANDRA_HOME=C, HW=HW))
    note(y.strip().splitlines()[-1][:900])
    N = f'{HW}/{node}'
    env = dict(os.environ, CASSANDRA_CONF=N + '/conf', CASSANDRA_LOG_DIR=N + '/logs',
               MAX_HEAP_SIZE='2G' if node == 'A' else '1G')
    env.pop('HEAP_NEWSIZE', None); env.pop('JVM_EXTRA_OPTS', None)
    if node == 'A':
        extra = (f'-javaagent:{BYTEMAN}=boot:{BYTEMAN},script:{BTM},listener:true,port:9114 '
                 f'-Dorg.jboss.byteman.verbose=false -Dstage4.trace={TRACE}')
        env['JVM_EXTRA_OPTS'] = extra
        note(f'A JVM_EXTRA_OPTS: {extra}')
    sh(f"bash -c 'ulimit -n 100000 && exec bin/cassandra -p {N}/cassandra.pid' > {N}/stdout.txt 2>&1", env=env)
    for _ in range(30):
        time.sleep(1)
        if pid_of(node) is not None:
            return
    fail(f'{node} did not start; see {N}/stdout.txt')


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


def read_trace():
    tr = {'opened': [], 'cbuf': [], 'closed': [], 'created': [], 'direct': []}
    if not os.path.exists(TRACE):
        return tr
    for l in open(TRACE, errors='replace'):
        l = l.strip()
        kind = l.split(' ', 1)[0]
        if kind not in tr:
            continue
        kv = dict(re.findall(r'(\w+)=(\S+)', l))
        tr[kind].append(kv | {'line': l[:300]})
    return tr


def exp_cap(n):
    return 4 + (n + n // 255 + 16) + 8


def writers(tr):
    """per writer identity: opened ms, closed ms, calls, max in, last cap, max cap"""
    w = {}
    for o in tr['opened']:
        w.setdefault(o['w'], {'opened': int(o['ms']), 'closed': None, 'calls': 0, 'max_in': 0, 'last_cap': None, 'max_cap': 0,
                              'exp_ok': True, 'grow_only': True})
    for c in tr['cbuf']:
        d = w.setdefault(c['w'], {'opened': None, 'closed': None, 'calls': 0, 'max_in': 0, 'last_cap': None, 'max_cap': 0,
                                  'exp_ok': True, 'grow_only': True})
        cap, n = int(c['cap']), int(c['in'])
        d['calls'] += 1
        d['max_in'] = max(d['max_in'], n)
        if d['last_cap'] is not None and cap < d['last_cap']:
            d['grow_only'] = False
        d['last_cap'] = cap
        d['max_cap'] = max(d['max_cap'], cap)
        d['direct'] = c['direct']
    for d in w.values():
        d['exp_ok'] = d['last_cap'] == exp_cap(d['max_in']) if d['calls'] else True
    for c in tr['closed']:
        if c['w'] in w:
            w[c['w']]['closed'] = int(c['ms'])
    return w


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


def lifetime():
    yaml, phase, peers, compressed = ARMS[arm]
    peer_nodes = ['B', 'C'][:peers]
    note(f'cluster-run {arm} {time.strftime("%F %T %Z")} host {os.uname().nodename.split(".")[0]} tree {C} '
         f'{sh("git describe --tags; git rev-parse --short HEAD", quiet=True)[1].split()} HW_N={os.environ.get("HW_N", "(default)")}')
    note('harness md5: ' + sh('md5sum cluster-run.py client.py make-node-yaml.sh Jmx.java hw.btm', quiet=True,
                              cwd=HARNESS)[1].replace('\n', ' ')[:700])
    note(f'arm {arm}: yaml {yaml or "(none: defaults)"}; workload {phase}; peers down {peer_nodes}; compression {"LZ4" if compressed else "absent"}')
    bp = busy_ports()
    if bp or mine():
        fail(f'ports in use or processes of this harness running: {bp} {mine()[:200]}')
    _, df = sh(f'df -k {HOME}', quiet=True)
    free_gb = int(df.splitlines()[-1].split()[3]) / 1048576
    note(f'free on {HOME}: {free_gb:.1f} GiB')
    if free_gb < 12:
        fail('less than 12 GiB free')
    sh(f'rm -rf {HW}/A {HW}/B {HW}/C')
    if os.path.exists(TRACE):
        os.remove(TRACE)
    os.makedirs(JMXCP, exist_ok=True)
    sh(f'javac -d {JMXCP} {HARNESS}/Jmx.java')
    sh(f'java -cp {C}/build/lib/jars/byteman-4.0.20.jar:{C}/build/apache-cassandra-5.0.9-SNAPSHOT.jar:{C}/build/classes/main:'
       f'$(ls {C}/lib/*.jar | tr "\\n" ":") org.jboss.byteman.check.TestScript {BTM} 2>&1 | tail -2', check=False)

    start_node('A', yaml)
    wait_up(['A'])
    joined = ['A']
    for p in peer_nodes:        # one at a time: a node cannot bootstrap while another is joining (shakedown 2: C died)
        start_node(p, yaml)
        joined.append(p)
        wait_up(joined)
    sch = client('schema', NODES['A'][0], 1 + peers)
    if not sch or not sch.get('agreement'):
        fail(f'schema: {sch}')
    note(f'schema: {sch}')
    st = client('settings', NODES['A'][0], *SETTINGS)
    if not st:
        fail('settings read-back failed')
    note(f'A settings: {st["settings"]}')
    args_a = open(f'/proc/{pid_of("A")}/cmdline').read().replace('\0', ' ')
    mdm, xmx, bmp = (re.findall(p, args_a) for p in (r'-XX:MaxDirectMemorySize=\S+', r'-Xmx\S+', r'port:\d+'))
    note(f'A command line: MaxDirectMemorySize {mdm}; Xmx {xmx}; byteman port {bmp}')
    comp = str(st['settings'].get('hints_compression'))
    note(f'read-back: hints_compression shows {comp} in system_views.settings (the view does not render this key, shakedown 1); '
         f'compression is read from the writer trace instead')
    expect(f'read-back: hinted_handoff_enabled true ({st["settings"].get("hinted_handoff_enabled")})',
           str(st['settings'].get('hinted_handoff_enabled')).lower() == 'true')
    expect(f'read-back: ports storage 7014 native 9146 ({st["settings"].get("storage_port")}, {st["settings"].get("native_transport_port")})',
           str(st['settings'].get('storage_port')) == '7014' and str(st['settings'].get('native_transport_port')) == '9146')

    t_bstop = int(time.time() * 1000)
    for p in peer_nodes:
        sh(f'bin/nodetool -p {NODES[p][1]} drain', check=False, timeout=300)
        stop_node(p)
        if pid_of(p) is not None:
            fail(f'{p} did not stop')
    for _ in range(90):
        stt = status('A')
        if all(stt.get(NODES[p][0]) == 'DN' for p in peer_nodes):
            break
        time.sleep(1)
    else:
        fail('A does not see the peers down')
    note(f'{peer_nodes} stopped and seen DN by A after {(time.time() * 1000 - t_bstop) / 1000:.1f} s')
    if client('probe', NODES['A'][0]) is None:
        fail('probe through A failed')

    pidA = pid_of('A')
    smp = Sampler(pidA)
    time.sleep(3)
    gc(pidA)
    time.sleep(10)
    ph = {'arm': arm, 'phase': phase, 'peers': peers, 'compressed': compressed, 'settings': st['settings'], 'ms_bstop': t_bstop}
    ph['ms_base'] = int(time.time() * 1000)
    time.sleep(2)
    tr0 = read_trace()
    note(f'trace before the workload: { {k: len(v) for k, v in tr0.items()} }')

    if phase == 'S':
        note(f'S: {NSMALL} INSERTs of {SMALL} B at CL ONE, {NCONC_S} in flight')
        res = client('bulk', NODES['A'][0], NSMALL, SMALL, NCONC_S)
        n_expected, per = NSMALL, SMALL
    else:
        note(f'L: {NBIG} INSERTs of {BIG} B at CL ONE, {NCONC_L} in flight')
        res = client('big', NODES['A'][0], NBIG, BIG, NCONC_L)
        n_expected, per = NBIG, BIG
    if res is None:
        smp.close(); fail('workload client failed')
    note(f'workload result: {res}')
    ph['workload'] = res
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
    _, lph = sh(f'bin/nodetool -p {NODES["A"][1]} listpendinghints', check=False)
    ph['listpendinghints'] = lph.strip()[-800:]
    stA = status('A')
    ph['peer_status_end'] = {p: stA.get(NODES[p][0]) for p in peer_nodes}
    ph['hints_dir_end'] = dir_bytes(f'{HW}/A/hints')
    _, ls = sh(f'ls -l {HW}/A/hints', check=False, quiet=True)
    open(f'{LOGS}/hints-ls.txt', 'w').write(ls)
    pats = [r'[Mm]utation of .* is too large', r'too large', r'Hint of', r'[Hh]inted handoff', r'OutOfMemory',
            r'[Dd]irect buffer memory']
    lg, nerr, nwarn = grep_log('A', pats)
    ph['log'] = {p: v[-5:] for p, v in lg.items()}
    ph['log_counts'] = {p: len(v) for p, v in lg.items()} | {'ERROR': nerr, 'WARN': nwarn}
    with open(f'{LOGS}/A-log-excerpt.txt', 'w') as f:
        for p, v in lg.items():
            f.write(f'## {p}: {len(v)} lines\n' + '\n'.join(v[-10:]) + '\n')
        f.write(f'## ERROR lines {nerr}, WARN lines {nwarn}\n')
        for l in open(f'{HW}/A/logs/system.log', errors='replace'):
            if l.startswith('ERROR') or l.startswith('WARN'):
                f.write(l[:400])
    rss_end = rss_kb(pidA)
    tr = read_trace()     # before the shutdown: HintsService.shutdownBlocking closes the open writers (found in shakedown 1)
    stop_node('A')
    clean = stop_all()
    if not clean:
        note('WARNING: a process of this harness is left')
    ph['clean_stop'] = clean
    sh(f'rm -rf {HW}/A/data {HW}/A/commitlog {HW}/A/hints {HW}/A/saved_caches {HW}/A/cdc_raw {HW}/B {HW}/C', check=False)

    def val(r, name):
        return col(r, name) if r else None

    base = at(rows, ph['ms_base'] + 1500)
    pre = at(rows, ph['ms_pre_gc'] + 1500)
    post = at(rows, ph['ms_end'] + 1500)
    ph['rows'] = {k: ({n: val(r, n) for n in NAMES} | {'ms': r[0]}) if r else None for k, r in (('base', base), ('pre_gc', pre), ('post_gc', post))}
    after = [r for r in rows if r[0] > ph['ms_base'] and col(r, 'direct_used') is not None]
    peak = max(after, key=lambda r: col(r, 'direct_used')) if after else None
    ph['peak'] = {'ms': peak[0], 'direct_used_delta': col(peak, 'direct_used') - val(base, 'direct_used')} if peak and base else None
    d = lambda r, n: val(r, n) - val(base, n) if r and base and val(r, n) is not None and val(base, n) is not None else None
    ph['delta_pre_gc'] = {n: d(pre, n) for n in ('direct_used', 'direct_count', 'rss', 'total_hints', 'hints_dir_bytes')}
    ph['delta_post_gc'] = {n: d(post, n) for n in ('direct_used', 'direct_count', 'rss', 'total_hints', 'hints_dir_bytes')}
    created_after = [c for c in tr['created'] if int(c['ms']) >= ph['ms_base']]
    ph['created'] = [c['line'] for c in tr['created']]
    ph['created_after_base'] = len(created_after)
    ph['corr'] = sum(int(c['size']) for c in created_after)
    ph['trace_counts'] = {k: len(v) for k, v in tr.items()}
    w = writers(tr)
    ph['writers'] = w
    live = [x for x in w.values() if x['closed'] is None and x['calls']]
    ph['live_writers'] = len(live)
    ph['live_cap_sum'] = sum(x['last_cap'] for x in live)
    ph['max_cap'] = max((x['max_cap'] for x in w.values()), default=0)
    ph['max_in'] = max((x['max_in'] for x in w.values()), default=0)
    ph['direct_ge_1mib_nonslab'] = sorted({int(x['size']) for x in tr['direct']})[:12]
    json.dump(ph, open(f'{LOGS}/phases.json', 'w'), indent=1, default=str)

    # ---------------------------------------------------------------- summary and per-lifetime EXPECTED lines
    note(f'baseline sample: {ph["rows"]["base"]}')
    note(f'delta pre-GC : {ph["delta_pre_gc"]}')
    note(f'delta post-GC: {ph["delta_post_gc"]}')
    note(f'peak direct delta {ph["peak"]}; trace {ph["trace_counts"]}; slabs created after the baseline {ph["created_after_base"]} '
         f'(Corr {ph["corr"]} B); writers {len(w)} (live {ph["live_writers"]}, sum of last capacities {ph["live_cap_sum"]} B); '
         f'max capacity {ph["max_cap"]} B for max in {ph["max_in"]} B (exp {exp_cap(ph["max_in"])})')
    note(f'hints dir at end {ph["hints_dir_end"]} B; peers at end {ph["peer_status_end"]}; TotalHints {ph["total_hints"]}; '
         f'RSS end {rss_end} kB; log counts {ph["log_counts"]}')
    dh = ph['delta_post_gc']['total_hints']
    expect(f'validity: peers down for the whole workload ({ph["peer_status_end"]})', all(v == 'DN' for v in ph['peer_status_end'].values()))
    expect(f'workload: {res["ok"]} of {n_expected} acknowledged, {res["err"]} errors', res['ok'] == n_expected and res['err'] == 0)
    if arm == 'H1':
        expect(f'H1: TotalHints +{dh} (the host-size knob stops hints; any number is a reading)', dh is not None)
    else:
        expect(f'validity: TotalHints +{dh} >= {n_expected * peers} (a hint per write per down peer)',
               dh is not None and dh >= n_expected * peers)
        expect(f'validity: hints directory {ph["hints_dir_end"]} B >= 0.9 x {n_expected * peers * per} B',
               ph['hints_dir_end'] >= 0.9 * n_expected * peers * per)
    if compressed:
        expect(f'trace: compressed writers present ({len(w)} writers, {len(tr["cbuf"])} writeBuffer lines)', len(w) >= 1 and len(tr['cbuf']) > 0)
        expect(f'trace: every writer\'s last capacity == 4 + (max in + max in/255 + 16) + 8 and never shrank',
               all(x['exp_ok'] and x['grow_only'] for x in w.values()))
        expect(f'trace: capacity buffers are direct', all(x.get('direct') == 'true' for x in w.values() if x['calls']))
        if phase == 'S':
            expect(f'S: largest capacity {ph["max_cap"]} <= exp(256 KiB) = {exp_cap(256 * KIB)}', 0 < ph['max_cap'] <= exp_cap(256 * KIB))
        elif arm != 'H1':
            expect(f'L: largest capacity {ph["max_cap"]} == exp(max in {ph["max_in"]}) and max in >= {BIG}',
                   ph['max_cap'] == exp_cap(ph['max_in']) and ph['max_in'] >= BIG)
            expect(f'L: live writers {ph["live_writers"]} >= peers {peers}', ph['live_writers'] >= peers)
        if arm == 'F1':
            expect(f'F1: more than one writer ({len(w)}) and at most one live per peer ({ph["live_writers"]} <= {peers})',
                   len(w) > 1 and ph['live_writers'] <= peers)
        if arm == 'M128':
            expect(f'M128: slabs created are 128 MiB ({sorted({c.split("size=")[1].split()[0] for c in ph["created"]})})',
                   ph['created'] and all(int(c.split('size=')[1].split()[0]) == 128 * MIB for c in ph['created']))
    else:
        expect(f'control: no CompressedHintsWriter opened or used (opened {len(tr["opened"])}, cbuf {len(tr["cbuf"])})',
               not tr['opened'] and not tr['cbuf'])
    note(f'EXPECTED yes {EXPECT["yes"]} no {EXPECT["no"]}')
    note(f'end {time.strftime("%F %T %Z")}')


def analyze():
    ph = {}
    for dd in sorted(os.listdir(ROOT)):
        f = f'{ROOT}/{dd}/phases.json'
        if os.path.exists(f):
            ph[dd] = json.load(open(f))
    note(f'analyze {time.strftime("%F %T %Z")}: lifetimes {sorted(ph)}')

    def X(a, ctrl):
        pa, pc = ph[a], ph[ctrl]
        return (pa['delta_post_gc']['direct_used'] - pa['corr']) - (pc['delta_post_gc']['direct_used'] - pc['corr'])

    def mib(x):
        return f'{x / MIB:.2f} MiB'
    res = {}
    if 'S' in ph and 'US' in ph:
        x = X('S', 'US'); res['S'] = x
        note(f'S: X = (dPool_S - Corr_S) - (dPool_US - Corr_US) = {mib(x)}; trace max capacity {ph["S"]["max_cap"]} B')
        expect(f'S: X {mib(x)} <= 0.3 MiB + band ({mib(0.3 * MIB + BAND)}) (B3f: no more than about 0.3 MiB)', x <= 0.3 * MIB + BAND)
    for a in ('D1', 'D2', 'F1', 'H1', 'M128', 'P2'):
        if a in ph and 'U' in ph:
            x = X(a, 'U'); res[a] = x
            note(f'{a}: X vs U = {mib(x)} (dPool {mib(ph[a]["delta_post_gc"]["direct_used"])}, Corr {mib(ph[a]["corr"])}; U dPool '
                 f'{mib(ph["U"]["delta_post_gc"]["direct_used"])}, Corr {mib(ph["U"]["corr"])}); trace live sum {mib(ph[a]["live_cap_sum"])}, '
                 f'live writers {ph[a]["live_writers"]}, writers {len(ph[a]["writers"])}')
    for a in ('D1', 'D2'):
        if a in res:
            expect(f'{a}: X {mib(res[a])} in 8.03 MiB +/- {mib(BAND)} (B3f: about 8.0-8.1 MiB per down peer)', abs(res[a] - 8.0314 * MIB) <= BAND)
    if 'D1' in res and 'D2' in res:
        expect(f'noise: D1 and D2 differ by {mib(abs(res["D1"] - res["D2"]))} <= band', abs(res['D1'] - res['D2']) <= BAND)
    ds = [res[a] for a in ('D1', 'D2') if a in res]
    if ds:
        dm = statistics.mean(ds)
        for a in ('F1', 'H1'):
            if a in res:
                expect(f'{a}: same increment as the default: X {mib(res[a])} within {mib(BAND)} of D mean {mib(dm)}', abs(res[a] - dm) <= BAND)
    if 'P2' in res:
        expect(f'P2: X {mib(res["P2"])} in 16.06 MiB +/- {mib(BAND)} (B3f: 2 peers about 16 MiB)', abs(res['P2'] - 2 * 8.0314 * MIB) <= BAND)
    if 'M128' in ph and 'D1' in ph:
        diff_pool = ph['M128']['delta_post_gc']['direct_used'] - ph['D1']['delta_post_gc']['direct_used']
        diff_corr = ph['M128']['corr'] - ph['D1']['corr']
        note(f'positive control: dPool(M128) - dPool(D1) = {mib(diff_pool)}; Corr(M128) - Corr(D1) = {mib(diff_corr)}')
        expect(f'positive control: pool difference {mib(diff_pool)} = slab-created difference {mib(diff_corr)} within 8 MiB',
               abs(diff_pool - diff_corr) <= 8 * MIB)
        expect(f'positive control: slab-created difference {mib(diff_corr)} >= 64 MiB', diff_corr >= 64 * MIB)
    json.dump(res, open(f'{ROOT}/analysis.json', 'w'), indent=1)
    note(f'EXPECTED yes {EXPECT["yes"]} no {EXPECT["no"]}')


if arm == 'down':
    stop_all()
elif arm == 'analyze':
    analyze()
else:
    try:
        lifetime()
    except SystemExit:
        raise
    except Exception as e:
        import traceback
        log(traceback.format_exc())
        fail(f'{type(e).__name__}: {e}')
    finally:
        stop_all()
