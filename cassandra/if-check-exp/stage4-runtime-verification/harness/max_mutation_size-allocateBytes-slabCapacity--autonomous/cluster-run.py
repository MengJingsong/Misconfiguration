#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of max_mutation_size-allocateBytes-slabCapacity--autonomous (amended 2026-10-20, R1-R3).
usage: cluster-run.py <arm> <rep> | analyze | down
  <arm> <rep>  one lifetime of both nodes (B3e steps 2-7): wipe ~/stage4-mss, write both yaml files with the arm's lines,
               start A (Byteman slab.btm attached) then B, wait for UN and the client port on both, create ks (RF 2),
               read the settings back, stop B (drain + stopdaemon) and wait until A sees it DN, GC A and take the baseline,
               then the workload through A at CL ONE (B3c):
                 S  200,000 INSERTs of 2,048 random bytes into ks.small, 64 in flight            (then a 10 s settle)
                 L  4 INSERTs of 8 MiB into ks.big, one after another                             (then a 5 s settle)
                 X  1 INSERT of 17 MiB into ks.big                                                 (then a 10 s settle)
               A is sampled every 1 s (JMX direct pool MemoryUsed/Count, heap, TotalHints, TotalHintsInProgress;
               /proc VmRSS; the hints directory's bytes; whether B's process exists). Then counters, listpendinghints,
               the trace, the log lines; A is stopped.
               Arms (B3b, B3h): OFF hinted_handoff_enabled false (control 1) · D default (max_mutation_size unset = 16 MiB,
               slab 32 MiB, MAX_HINT_BUFFERS 3) · M4 max_mutation_size 4096KiB · M32 max_mutation_size 32768KiB with
               commitlog_segment_size 64MiB · B1 -Dcassandra.MAX_HINT_BUFFERS=1. <rep> 1 or 2 (D runs twice, control 3).
  analyze      reads every <arm>-<rep>/phases.json and writes analysis.txt: the B3f relations across arms, against the
               OFF control (the frozen tolerance, harness README: band B = 8 MiB, RSS within 25 %).
  down         stop both nodes of this harness.
Two nodes on this host (loopback): A = 127.0.0.2 (JMX 7102, seed, coordinator, measured), B = 127.0.0.3 (JMX 7103).
Output: ~/stage4-logs/mss/<run>/cluster/<arm>-<rep>/ (summary.txt with EXPECTED lines, session.log, samples.csv,
phases.json, mss.trace, keys.csv, log excerpts). Exit 1: a set-up check failed (a node not UN, B not seen down, a client
that could not connect, the trace missing); both nodes are then stopped. A reading that misses a prediction is recorded
as EXPECTED ... NO. Environment: MSS_RUN (default run1), CASSANDRA_HOME (default ~/cassandra-run1), MSS_N (bulk writes,
default 200000; a shakedown may lower it). From the internode_max_message_size-inferMessageSize harness's cluster-run.py."""
import calendar, json, os, re, statistics, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-run1')
HARNESS = os.path.dirname(os.path.abspath(__file__))
MSS = os.environ.get('MSS', HOME + '/stage4-mss')
RUN = os.environ.get('MSS_RUN', 'run1')
NBULK = int(os.environ.get('MSS_N', 200000))
KIB, MIB = 1024, 1 << 20
BAND = 8 * MIB
VALUE = 2048
BIG, NBIG, XSIZE = 8 * MIB, 4, 17 * MIB
NODES = {'A': ('127.0.0.2', 7102), 'B': ('127.0.0.3', 7103)}
ARMS = {  # yaml lines, MAX_HINT_BUFFERS property (None = default 3), predicted slab, max slabs, hints on
    'OFF': (['hinted_handoff_enabled=false'], None, None, 0, False),
    'D': ([], None, 32 * MIB, 3, True),
    'M4': (['max_mutation_size=4096KiB'], None, 32 * MIB, 3, True),
    'M32': (['max_mutation_size=32768KiB', 'commitlog_segment_size=64MiB'], None, 64 * MIB, 3, True),
    'B1': ([], 1, 32 * MIB, 1, True),
}
CLIENT = HARNESS + '/client.py'
BTM = HARNESS + '/slab.btm'
BYTEMAN = C + '/build/lib/jars/byteman-4.0.20.jar'
JMXCP = MSS + '/jmx'
COLS = [('direct_used', 'java.nio:type=BufferPool,name=direct', 'MemoryUsed'),
        ('direct_count', 'java.nio:type=BufferPool,name=direct', 'Count'),
        ('heap_used', 'java.lang:type=Memory', 'HeapMemoryUsage'),
        ('total_hints', 'org.apache.cassandra.metrics:type=Storage,name=TotalHints', 'Count'),
        ('hints_in_progress', 'org.apache.cassandra.metrics:type=Storage,name=TotalHintsInProgress', 'Count')]
SETTINGS = ['max_mutation_size', 'commitlog_segment_size', 'hinted_handoff_enabled', 'hints_flush_period',
            'max_hints_size_per_host', 'native_transport_max_message_size']

args = sys.argv[1:]
if not args or (args[0] in ARMS and len(args) != 2) or (args[0] not in ARMS and args[0] not in ('analyze', 'down')):
    sys.exit(__doc__)
arm = args[0]
tag = f'{arm}-{args[1]}' if arm in ARMS else arm
ROOT = f'{HOME}/stage4-logs/mss/{RUN}/cluster'
LOGS = f'{ROOT}/{tag}'
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
SUMMARY = open(LOGS + '/summary.txt', 'a' if arm == 'down' else 'w')
EXPECT = {'yes': 0, 'no': 0}
TRACE = LOGS + '/mss.trace'


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
    f = f'{MSS}/{node}/cassandra.pid'
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
    try:
        sh(f'bin/nodetool -p {NODES[node][1]} stopdaemon', check=False, timeout=180)
    except subprocess.TimeoutExpired:
        log(f'{node}: stopdaemon timed out (a hung node); falling back to kill -9')
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


def client(*a, timeout=1800):
    rc, out = sh(f'python3 {CLIENT} ' + ' '.join(str(x) for x in a), timeout=timeout, check=False,
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


def jmx_query(node, pattern, attr):
    _, out = sh(f"java -cp {JMXCP} Jmx {NODES[node][1]} query '{pattern}' {attr}", check=False, quiet=True, timeout=120)
    res = {}
    for l in out.splitlines():
        parts = l.rsplit('|', 2)
        if len(parts) == 3:
            res[parts[0]] = parts[2]
    return res


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def start_node(node, yaml, mhb=None):
    if pid_of(node) is not None:
        fail(f'{node} is already running')
    _, y = sh(f'bash {HARNESS}/make-node-yaml.sh {node} ' + ' '.join(f"'{a}'" for a in yaml),
              env=dict(os.environ, CASSANDRA_HOME=C, MSS=MSS))
    note(y.strip().splitlines()[-1][:900])
    N = f'{MSS}/{node}'
    env = dict(os.environ, CASSANDRA_CONF=N + '/conf', CASSANDRA_LOG_DIR=N + '/logs',
               MAX_HEAP_SIZE='2G' if node == 'A' else '1G')
    env.pop('HEAP_NEWSIZE', None); env.pop('JVM_EXTRA_OPTS', None)
    if node == 'A':
        extra = (f'-javaagent:{BYTEMAN}=boot:{BYTEMAN},script:{BTM},listener:true '
                 f'-Dorg.jboss.byteman.verbose=false -Dstage4.trace={TRACE}')
        if mhb is not None:
            extra += f' -Dcassandra.MAX_HINT_BUFFERS={mhb}'
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
    """A every 1 s: one Jmx poll JVM for the JMX columns; a thread for VmRSS, the hints directory and B's process"""

    def __init__(self, pid):
        self.stop = f'{LOGS}/sampler.stop'
        if os.path.exists(self.stop):
            os.remove(self.stop)
        self.jf = open(f'{LOGS}/samples-jmx.csv', 'w')
        self.jf.write('ms,' + ','.join(c for c, _, _ in COLS) + '\n'); self.jf.flush()
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
            self.side.append((int(time.time() * 1000), rss_kb(pid), dir_bytes(f'{MSS}/A/hints'),
                              1 if pid_of('B') is not None else 0))
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
        with open(f'{LOGS}/samples-side.csv', 'w') as f:
            f.write('ms,rss_kb,hints_dir_bytes,b_alive\n')
            for r in self.side:
                f.write(','.join('' if v is None else str(v) for v in r) + '\n')
        rows = []
        for l in open(f'{LOGS}/samples-jmx.csv').read().splitlines()[1:]:
            parts = l.split(',')
            if len(parts) == len(COLS) + 1 and parts[0].isdigit():
                rows.append([int(parts[0])] + [num(x) for x in parts[1:]])
        out, j = [], 0
        for r in rows:          # nearest side sample in time
            while j + 1 < len(self.side) and abs(self.side[j + 1][0] - r[0]) <= abs(self.side[j][0] - r[0]):
                j += 1
            sd = self.side[j] if self.side else (None, None, None, None)
            out.append(r + [None if sd[1] is None else sd[1] * 1024.0, sd[2], sd[3]])
        with open(f'{LOGS}/samples.csv', 'w') as f:
            f.write('ms,' + ','.join(c for c, _, _ in COLS) + ',rss,hints_dir_bytes,b_alive\n')
            for r in out:
                f.write(','.join('' if v is None else str(int(v)) for v in r) + '\n')
        return out


NAMES = [c for c, _, _ in COLS] + ['rss', 'hints_dir_bytes', 'b_alive']


def col(r, name):
    return r[1 + NAMES.index(name)]


def at(rows, ms):
    """the last sample at or before ms"""
    best = None
    for r in rows:
        if r[0] <= ms:
            best = r
    return best


def read_trace():
    tr = {'created': [], 'closed': [], 'waiting': [], 'offer': [], 'slowhint': [], 'direct': []}
    if not os.path.exists(TRACE):
        return tr
    for l in open(TRACE, errors='replace'):
        l = l.strip()
        kind = l.split(' ', 1)[0]
        if kind not in tr:
            continue
        kv = dict(re.findall(r'(\w+)=(\S+)', l))
        tr[kind].append(kv | {'line': l[:400], 'slab': 'HintsBuffer.create' in l})
    return tr


def grep_log(node, pats):
    f = f'{MSS}/{node}/logs/system.log'
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


# ---------------------------------------------------------------- one lifetime

def lifetime():
    yaml, mhb, slab, kmax, hints_on = ARMS[arm]
    note(f'cluster-run {tag} {time.strftime("%F %T %Z")} host {os.uname().nodename.split(".")[0]} clone {C} '
         f'{sh("git describe --tags; git rev-parse --short HEAD", quiet=True)[1].split()} MSS_N={NBULK}')
    note('harness md5: ' + sh('md5sum cluster-run.py client.py make-node-yaml.sh Jmx.java slab.btm', quiet=True,
                              cwd=HARNESS)[1].replace('\n', ' ')[:700])
    note(f'arm {arm}: yaml {yaml or "(none: defaults)"}; MAX_HINT_BUFFERS {mhb or "default (3)"}; '
         f'predicted slab {slab}; max slabs {kmax}; hints {"on" if hints_on else "off"}')
    if any_daemon():
        fail('a CassandraDaemon is already running on this host: ' + any_daemon()[:200])
    _, df = sh(f'df -k {HOME}', quiet=True)
    free_gb = int(df.splitlines()[-1].split()[3]) / 1048576
    note(f'free on {HOME}: {free_gb:.1f} GiB')
    if free_gb < 10:
        fail('less than 10 GiB free')
    sh(f'rm -rf {MSS}/A {MSS}/B')
    if os.path.exists(TRACE):
        os.remove(TRACE)
    os.makedirs(JMXCP, exist_ok=True)
    sh(f'javac -d {JMXCP} {HARNESS}/Jmx.java')
    sh(f'java -cp {C}/build/lib/jars/byteman-4.0.20.jar:{C}/build/apache-cassandra-5.0.9-SNAPSHOT.jar:{C}/build/classes/main '
       f'org.jboss.byteman.check.TestScript {BTM} 2>&1 | tail -3', check=False)

    start_node('A', yaml, mhb)
    wait_up(['A'])
    start_node('B', yaml)
    wait_up(['A', 'B'])
    if not os.path.exists(TRACE):
        log('trace file not created yet (no rule fired): expected before any hint')
    sch = client('schema', NODES['A'][0])
    if not sch or not sch.get('agreement'):
        fail(f'schema: {sch}')
    note(f'schema: {sch}')
    st = client('settings', NODES['A'][0], *SETTINGS)
    if not st:
        fail('settings read-back failed')
    note(f'A settings: {st["settings"]}')
    args_a = open(f'/proc/{pid_of("A")}/cmdline').read().replace('\0', ' ')
    mhb_arg = re.findall(r'-Dcassandra\.MAX_HINT_BUFFERS=(\d+)', args_a)
    mdm, xmx = re.findall(r'-XX:MaxDirectMemorySize=\S+', args_a), re.findall(r'-Xmx\S+', args_a)
    note(f'A command line MAX_HINT_BUFFERS: {mhb_arg or "absent (default 3)"}; MaxDirectMemorySize: {mdm}; Xmx: {xmx}')
    expect(f'read-back: hints_flush_period is 3600000ms ({st["settings"].get("hints_flush_period")})',
           str(st['settings'].get('hints_flush_period')) in ('3600000ms', '3600s', '60m', '1h'))
    expect(f'read-back: hinted_handoff_enabled {hints_on} ({st["settings"].get("hinted_handoff_enabled")})',
           str(st['settings'].get('hinted_handoff_enabled')).lower() == str(hints_on).lower())

    # stop B (B3e step 3) and wait until A sees it down
    t_bstop = int(time.time() * 1000)
    sh(f'bin/nodetool -p {NODES["B"][1]} drain', check=False, timeout=300)
    stop_node('B')
    if pid_of('B') is not None:
        fail('B did not stop')
    for _ in range(60):
        if status('A').get(NODES['B'][0]) == 'DN':
            break
        time.sleep(1)
    else:
        fail('A does not see B down')
    note(f'B stopped and seen DN by A after {(time.time() * 1000 - t_bstop) / 1000:.1f} s')
    tr0 = read_trace()
    note(f'trace before the workload: {len(tr0["created"])} created, {len(tr0["closed"])} closed, '
         f'{len(tr0["direct"])} direct lines')
    if client('probe', NODES['A'][0]) is None:
        fail('probe through A failed')

    pidA = pid_of('A')
    smp = Sampler(pidA)
    time.sleep(3)
    sh(f'jcmd {pidA} GC.run', check=False)
    time.sleep(7)
    ph = {'arm': arm, 'rep': args[1], 'slab_pred': slab, 'kmax': kmax, 'hints_on': hints_on, 'settings': st['settings'],
          'mhb_arg': mhb_arg, 'ms_bstop': t_bstop}
    ph['ms_base'] = int(time.time() * 1000)
    ph['counters_base'] = {f'{b}|{a}': v for (b, a), v in
                           jmx('A', ('org.apache.cassandra.metrics:type=Storage,name=TotalHints', 'Count')).items()}
    time.sleep(1)

    note(f'S: {NBULK} INSERTs of {VALUE} B at CL ONE, 64 in flight')
    bulk = client('bulk', NODES['A'][0], NBULK, VALUE, 64, timeout=3600)
    if bulk is None:
        smp.close(); fail('bulk client failed')
    note(f'S result: {bulk}')
    ph['bulk'] = bulk
    time.sleep(10)
    ph['ms_end_bulk'] = int(time.time() * 1000)

    keylog = f'{LOGS}/keys.csv'
    ph['big'] = []
    for i in range(NBIG):
        r = client('one', NODES['A'][0], i + 1, BIG, keylog)
        note(f'L write {i + 1}: {r}')
        ph['big'].append(r)
    time.sleep(5)
    ph['ms_end_big'] = int(time.time() * 1000)
    rx = client('one', NODES['A'][0], 100, XSIZE, keylog)
    note(f'X write (17 MiB): {rx}')
    ph['x'] = rx
    time.sleep(10)
    ph['ms_end'] = int(time.time() * 1000)
    rows = smp.close()

    # after the workload: counters, pending hints, B still down
    cnt = jmx_query('A', 'org.apache.cassandra.metrics:type=HintsService,name=*', 'Count')
    ph['hints_service'] = cnt
    _, lph = sh(f'bin/nodetool -p {NODES["A"][1]} listpendinghints', check=False)
    ph['listpendinghints'] = lph.strip()[-800:]
    stA = status('A')
    ph['b_status_end'] = stA.get(NODES['B'][0])
    ph['hints_dir_end'] = dir_bytes(f'{MSS}/A/hints')
    _, ls = sh(f'ls -l {MSS}/A/hints', check=False, quiet=True)
    open(f'{LOGS}/hints-ls.txt', 'w').write(ls)
    pats = [r'[Mm]utation of .* is too large', r'MutationExceededMaxSizeException', r'too large', r'exceeds',
            r'Hint of', r'[Hh]inted handoff', r'Finished hinted', r'OutOfMemory', r'[Dd]irect buffer memory']
    lg, nerr, nwarn = grep_log('A', pats)
    ph['log'] = {p: v[-5:] for p, v in lg.items()}
    ph['log_counts'] = {p: len(v) for p, v in lg.items()} | {'ERROR': nerr, 'WARN': nwarn}
    with open(f'{LOGS}/A-log-excerpt.txt', 'w') as f:
        for p, v in lg.items():
            f.write(f'## {p}: {len(v)} lines\n' + '\n'.join(v[-10:]) + '\n')
        f.write(f'## ERROR lines {nerr}, WARN lines {nwarn}\n')
        for l in open(f'{MSS}/A/logs/system.log', errors='replace'):
            if l.startswith('ERROR') or l.startswith('WARN'):
                f.write(l[:400])
    stop_node('A')
    if not stop_all():
        note('WARNING: a daemon is left')
    tr = read_trace()

    # ------------------------------------------------ readings
    def d(r, name, base):
        return col(r, name) - col(base, name) if r and base and col(r, name) is not None and col(base, name) is not None else None

    base = at(rows, ph['ms_base'])
    marks = {'end_bulk': at(rows, ph['ms_end_bulk']), 'end_big': at(rows, ph['ms_end_big']), 'end': at(rows, ph['ms_end'])}
    after = [r for r in rows if r[0] > ph['ms_base'] and col(r, 'direct_used') is not None]
    peak = max(after, key=lambda r: col(r, 'direct_used')) if after else None
    ph['base'] = {n: col(base, n) for n in NAMES} if base else None
    ph['marks'] = {k: ({n: col(r, n) for n in NAMES} | {'ms': r[0]}) if r else None for k, r in marks.items()}
    ph['delta'] = {k: {n: d(r, n, base) for n in ('direct_used', 'direct_count', 'rss', 'total_hints', 'hints_dir_bytes')}
                   for k, r in marks.items()}
    ph['peak'] = {'ms': peak[0], 'direct_used_delta': d(peak, 'direct_used', base)} if peak else None
    ph['b_alive_samples'] = sum(int(col(r, 'b_alive') or 0) for r in rows if r[0] >= ph['ms_base'])
    created, closed = tr['created'], tr['closed']
    ph['trace'] = {k: len(v) for k, v in tr.items()}
    ph['created'] = [c['line'] for c in created]
    ph['closed_first'] = [c['line'] for c in closed[:5]]
    ph['slab_bytes_trace'] = sum(int(c['size']) for c in created)
    ph['direct_lines'] = [x['line'][:300] for x in tr['direct']]
    ph['direct_nonslab_bytes'] = sum(int(x['size']) for x in tr['direct'] if not x['slab'])
    ph['direct_slab_lines'] = sum(1 for x in tr['direct'] if x['slab'])
    sl = [int(x['us']) for x in tr['slowhint']]
    ph['slowhint'] = {'n': len(sl), 'max_us': max(sl) if sl else 0, 'sum_us': sum(sl)}
    if len(closed) >= 2:
        t15 = (int(closed[0]['ms']) + int(closed[1]['ms'])) // 2
        r15 = next((r for r in rows if r[0] >= t15), None)
        ph['at_1p5_slabs'] = {'ms': r15[0], 'direct_used_delta': d(r15, 'direct_used', base),
                              'total_hints_delta': d(r15, 'total_hints', base)} if r15 else None
    else:
        ph['at_1p5_slabs'] = None
    # phase windows of the trace
    def in_win(evts, t0, t1):
        return [e for e in evts if t0 <= int(e['ms']) <= t1]
    ph['pre_baseline_slabs'] = len([c for c in created if int(c['ms']) < ph['ms_base']])
    ph['pre_baseline_created'] = [c['line'] for c in created if int(c['ms']) < ph['ms_base']]
    ph['created_in'] = {'S': len(in_win(created, ph['ms_base'], ph['ms_end_bulk'])),
                        'L': len(in_win(created, ph['ms_end_bulk'], ph['ms_end_big'])),
                        'X': len(in_win(created, ph['ms_end_big'], ph['ms_end']))}
    json.dump(ph, open(f'{LOGS}/phases.json', 'w'), indent=1, default=str)

    # ------------------------------------------------ summary and EXPECTED lines (per lifetime; cross-arm in analyze)
    dl = ph['delta']
    note(f'baseline direct_used {ph["base"]["direct_used"]:.0f} count {ph["base"]["direct_count"]:.0f} '
         f'rss {ph["base"]["rss"]:.0f} total_hints {ph["base"]["total_hints"]:.0f}')
    for k in ('end_bulk', 'end_big', 'end'):
        note(f'delta at {k}: ' + ', '.join(f'{n} {v:+.0f}' if v is not None else f'{n} -' for n, v in dl[k].items()))
    note(f'peak direct_used delta {ph["peak"]["direct_used_delta"]:+.0f} ({ph["peak"]["direct_used_delta"] / MIB:.2f} MiB); '
         f'at 1.5 slabs: {ph["at_1p5_slabs"]}')
    note(f'trace: {ph["trace"]}; created {ph["created"]}; slab bytes {ph["slab_bytes_trace"]}; created per phase '
         f'{ph["created_in"]}; direct >= 1 MiB not from HintsBuffer.create: {ph["direct_nonslab_bytes"]} B; '
         f'slowhint {ph["slowhint"]}')
    note(f'hints dir at end {ph["hints_dir_end"]} B; B status at end {ph["b_status_end"]}; B alive samples '
         f'{ph["b_alive_samples"]}; listpendinghints: {ph["listpendinghints"][-300:]!r}')
    note(f'log counts: {ph["log_counts"]}')

    expect(f'validity: B down for the whole workload (alive samples {ph["b_alive_samples"]}, A sees {ph["b_status_end"]})',
           ph['b_alive_samples'] == 0 and ph['b_status_end'] == 'DN')
    expect(f'bulk: {bulk["ok"]} of {NBULK} acknowledged, {bulk["err"]} errors', bulk['ok'] == NBULK and bulk['err'] == 0)
    th_bulk = dl['end_bulk']['total_hints']
    if hints_on:
        expect(f'validity: TotalHints +{th_bulk:.0f} over S >= {NBULK} (hints written)', th_bulk is not None and th_bulk >= NBULK)
        expect(f'validity: hints exceed one slab ({len(closed)} closed lines >= 1; hints dir {ph["hints_dir_end"]} B)',
               len(closed) >= 1)
        offered = th_bulk * VALUE
        expect(f'hints offered over S (TotalHints x {VALUE} B = {offered:.0f} B) exceed {kmax} x slab ({kmax * slab}): '
               f'ratio {offered / (kmax * slab):.2f}', offered > kmax * slab)
        expect(f'every created line: size={slab} ({sorted({c["size"] for c in created})})',
               all(int(c['size']) == slab for c in created) and created)
        expect(f'every created line: max={kmax} ({sorted({c["max"] for c in created})})',
               all(int(c['max']) == kmax for c in created) and created)
        expect(f'created lines {len(created)} <= MAX_HINT_BUFFERS {kmax}', 1 <= len(created) <= kmax)
        # a closing thread and the threads that raced past the full slab before position.set all reach line 190's true
        # branch: every closed line has prev >= 0 and prev + total > cap; the first of each fill also has prev <= cap
        bad = [c['line'] for c in closed if not (0 <= int(c['prev']) and int(c['prev']) + int(c['total']) > int(c['cap']))]
        fills = sum(1 for c in closed if int(c['prev']) <= int(c['cap']))
        ph['closed_fills'] = fills
        expect(f'every closed line has prev + total > cap and cap = slab ({len(closed)} lines, {len(bad)} not; '
               f'{fills} with prev <= cap, i.e. slab fills)', not bad and all(int(c['cap']) == slab for c in closed))
        expect(f'direct allocations >= 1 MiB from HintsBuffer.create ({ph["direct_slab_lines"]}) = created lines ({len(created)})',
               ph['direct_slab_lines'] == len(created))
        if kmax == 1:
            expect(f'MAX_HINT_BUFFERS=1: writers waited at take() ({len(tr["waiting"])} waiting lines > 0)', len(tr['waiting']) > 0)
    else:
        nafter = sum(ph['created_in'].values())
        expect(f'control: no slab created after the baseline ({nafter}; {ph["pre_baseline_slabs"]} before it, the idle '
               f'batchlog flush)', nafter == 0)
        expect(f'control: TotalHints +0 ({dl["end"]["total_hints"]})', dl['end']['total_hints'] == 0)
    big_ok = sum(1 for r in ph['big'] if r and r['result'] == 'ok')
    note(f'L: {big_ok} of {NBIG} 8 MiB writes acknowledged; errors: {[r["why"] for r in ph["big"] if r and r["result"] != "ok"][:2]}')
    if hints_on and arm != 'M4':
        expect(f'L: 4 x 8 MiB writes acknowledged ({big_ok})', big_ok == NBIG)
    if arm in ('D', 'M4', 'B1', 'OFF'):      # max_mutation_size <= 16 MiB: the 17 MiB write must fail (R2)
        xd = d(marks['end'], 'direct_used', marks['end_big'])
        xh = d(marks['end'], 'total_hints', marks['end_big'])
        expect(f'X: the 17 MiB write fails ({rx and rx["result"]}: {rx and rx["why"][:160]})', rx is not None and rx['result'] == 'err')
        expect(f'X: no hint written (TotalHints {xh:+.0f}) and no slab created ({ph["created_in"]["X"]})',
               xh == 0 and ph['created_in']['X'] == 0)
        expect(f'X: direct pool change {xd:+.0f} within the {BAND} B band', xd is not None and abs(xd) <= BAND)
    else:
        note(f'X (M32, max_mutation_size 32 MiB, no prediction): {rx}')
    note(f'EXPECTED yes {EXPECT["yes"]} no {EXPECT["no"]}')
    note(f'end {time.strftime("%F %T %Z")}')


# ---------------------------------------------------------------- analyze (cross-arm B3f relations)

def analyze():
    ph = {}
    for d in sorted(os.listdir(ROOT)):
        f = f'{ROOT}/{d}/phases.json'
        if os.path.exists(f):
            ph[d] = json.load(open(f))
    note(f'analyze {time.strftime("%F %T %Z")}: lifetimes {sorted(ph)}')
    offs = [k for k in ph if k.startswith('OFF-')]
    if not offs:
        note('no OFF control'); return
    off = ph[sorted(offs)[0]]

    def x(p, mark='end', what='direct_used'):
        return p['delta'][mark][what] - off['delta'][mark][what]

    res = {}
    for k, p in sorted(ph.items()):
        if not p['hints_on']:
            continue
        nc = len(p['created'])
        pre = p['pre_baseline_slabs'] * p['slab_pred']     # slabs made before the baseline (idle batchlog flush)
        xe, xb = x(p) + pre, x(p, 'end_bulk') + pre
        xp = p['peak']['direct_used_delta'] - off['peak']['direct_used_delta'] + pre
        xr = x(p, 'end', 'rss') + pre
        xe_lit = x(p)
        res[k] = {'k': nc, 'pre': p['pre_baseline_slabs'], 'x_end_literal': xe_lit, 'x_end': xe, 'x_end_bulk': xb, 'x_peak': xp, 'x_rss': xr, 'slab': p['slab_pred'],
                  'per_slab': xe / nc if nc else None, 'lat_mean': p['bulk']['lat_mean_ms'], 'lat_p99': p['bulk']['lat_p99_ms'],
                  'slow_n': p['slowhint']['n'], 'slow_max': p['slowhint']['max_us'], 'waiting': p['trace']['waiting']}
        note(f'{k}: slabs {nc} x {p["slab_pred"]} ({p["pre_baseline_slabs"]} before the baseline); literal (arm - OFF, '
             f'from the pre-write baseline) end {xe_lit / MIB:.2f} MiB; hint-attributable direct (arm - OFF) end_bulk {xb / MIB:.2f} MiB, '
             f'end {xe / MIB:.2f} MiB, peak {xp / MIB:.2f} MiB; RSS (arm - OFF) end {xr / MIB:.2f} MiB; '
             f'client lat mean {p["bulk"]["lat_mean_ms"]} ms p99 {p["bulk"]["lat_p99_ms"]} ms; slow hint writes '
             f'{p["slowhint"]["n"]} (max {p["slowhint"]["max_us"]} us); waiting {p["trace"]["waiting"]}')
        lo, hi = p['slab_pred'] - BAND, p['kmax'] * p['slab_pred'] + BAND
        expect(f'{k}: hint-attributable direct at end {xe / MIB:.2f} MiB in [{lo / MIB:.0f}, {hi / MIB:.0f}] MiB', lo <= xe <= hi)
        expect(f'{k}: peak {xp / MIB:.2f} MiB <= {p["kmax"]} x slab + band ({hi / MIB:.0f} MiB)', xp <= hi)
        expect(f'{k}: no growth past the created slabs: end {xe / MIB:.2f} MiB = {nc} x slab ({nc * p["slab_pred"] / MIB:.0f} MiB) '
               f'within the band', abs(xe - nc * p['slab_pred']) <= BAND)
        expect(f'{k}: RSS (arm - OFF) {xr / MIB:.2f} MiB within 25 % of the direct {xe / MIB:.2f} MiB',
               xe > 0 and abs(xr - xe) <= 0.25 * xe)
    ds = [v for k, v in res.items() if k.startswith('D-')]
    if ds:
        dmin, dmax = min(v['x_end'] for v in ds), max(v['x_end'] for v in ds)
        note(f'default repeats: x_end {[round(v["x_end"] / MIB, 2) for v in ds]} MiB, spread {(dmax - dmin) / MIB:.2f} MiB (control 3)')
        for k, v in res.items():
            if k.startswith('M4-'):
                expect(f'{k}: same as default: {v["x_end"] / MIB:.2f} MiB in [{(dmin - BAND) / MIB:.2f}, {(dmax + BAND) / MIB:.2f}] MiB',
                       dmin - BAND <= v['x_end'] <= dmax + BAND)
                expect(f'{k}: slab size from the trace 32 MiB = the default\'s', v['slab'] == 32 * MIB)
            if k.startswith('M32-'):
                dps = statistics.mean(w['per_slab'] for w in ds if w['per_slab'])
                ratio = v['per_slab'] / dps if v['per_slab'] and dps else None
                expect(f'{k}: one-slab step doubles: per-slab {v["per_slab"] / MIB:.2f} MiB / default {dps / MIB:.2f} MiB = '
                       f'{ratio:.3f} in [1.8, 2.2]', ratio is not None and 1.8 <= ratio <= 2.2)
            if k.startswith('B1-'):
                expect(f'{k}: one slab: {v["k"]} created, direct {v["x_end"] / MIB:.2f} MiB in [24, 40] MiB',
                       v['k'] == 1 and 32 * MIB - BAND <= v['x_end'] <= 32 * MIB + BAND)
                expect(f'{k}: hint write latency rises: slow hint writes {v["slow_n"]} (max {v["slow_max"]} us) > every '
                       f'default run\'s ({[w["slow_n"] for w in ds]}, max {[w["slow_max"] for w in ds]})',
                       all(v['slow_n'] > w['slow_n'] and v['slow_max'] > w['slow_max'] for w in ds))
                note(f'{k}: client latency mean {v["lat_mean"]} ms p99 {v["lat_p99"]} ms vs default '
                     f'{[(w["lat_mean"], w["lat_p99"]) for w in ds]}')
                expect(f'{k}: the count binds: B1 direct {v["x_end"] / MIB:.2f} MiB differs from every default run\'s by more '
                       f'than the band', all(abs(v['x_end'] - w['x_end']) > BAND for w in ds))
    json.dump(res, open(f'{LOGS}/analysis.json', 'w'), indent=1)
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
