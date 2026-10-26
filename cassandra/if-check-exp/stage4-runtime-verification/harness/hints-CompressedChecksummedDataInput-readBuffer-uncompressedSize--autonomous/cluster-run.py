#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of hints-CompressedChecksummedDataInput-readBuffer-uncompressedSize--autonomous (audit amendments
R7-R10, 2026-10-25).
usage: cluster-run.py cell <fcs_MiB> <value_bytes> <rows> | control <fcs_MiB> | all | down
  cell     one lifetime (a "cell" of B3b's matrix): wipe ~/s4-hu-run, yaml (make-node-yaml.sh, file_cache_size = <fcs> MiB), start A
           (the seed; Byteman hu.btm) then B on loopback, schema hu.t RF 2, stop B, wait for A to see it DN, sampler on A, a 10 s
           baseline, <rows> random <value_bytes>-byte values to A at CL ONE (protocol 4), wait until the .hints files hold the
           values and stop growing, parse the raw hint files' block headers (ground truth: Z and C of every block), start B (the
           replay), sample every second until A's hints directory holds no .hints file, then the same for 20 s, stop B and A.
           Output: summary.txt (EXPECTED lines), cell.json, hints-blocks.json (the raw headers), hu.trace (A's Byteman trace),
           samples.csv, system logs.
  control  B3h: A alone (RF 1), file_cache_enabled true and file_cache_size <fcs> MiB, a table with LZ4 and chunk_length_in_kb 64,
           128 MiB of random 64 KiB values, flush, then 3 passes of random single-row reads (8 in flight) with the chunk-cache
           pool sampled every second: the pooled part (Size - OverflowSize) is the reading.
  inject   B3h as amended by R11/D2 (2026-10-25): A alone, file_cache_size <fcs> MiB, Byteman hu-inject.btm; 10 s baseline, then the flag
           file `inject` makes the node's own chunk-cache pool serve and hold 400 x 64 KiB (HuControl), sampled 20 s, then `release`.
  all      the 12 cells (fcs 1, 16, 512 x 1 KiB, 100 KiB, 1 MiB, 8 MiB) and the control at 16 and 512, in this order.
  down     stop both nodes of this harness.
A = 127.0.13.1 (JMX 7213, Byteman 9113, native 9145, storage 7013), B = 127.0.13.2 (JMX 7214, native 9145, storage 7013).
Environment: HU_RUN (default run1), CASSANDRA_HOME (default ~/s4-hu). Output: ~/stage4-logs/hu/<run>/cluster/<tag>/.
Both nodes are stopped on any exit. A reading that misses a prediction is recorded as EXPECTED ... NO and the run goes on."""
import glob, json, os, re, struct, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/s4-hu')
HARNESS = os.path.dirname(os.path.abspath(__file__))
HU = os.environ.get('HU', HOME + '/s4-hu-run')
RUN = os.environ.get('HU_RUN', 'run1')
KIB, MIB = 1024, 1 << 20
NODES = {'A': ('127.0.13.1', 7213), 'B': ('127.0.13.2', 7214)}
CLIENT = HARNESS + '/client.py'
TOOLS = HU + '/tools'
BM = C + '/build/lib/jars/byteman-4.0.20.jar'
BYTEMAN_PORT = 9113
MACRO, NORMAL, INITIAL = 8 * MIB, 128 * KIB, 4096
CELLS = [(f, b, n) for f in (1, 16, 512) for b, n in ((1024, 50000), (102400, 500), (MIB, 64), (8 * MIB, 8))]
COLS = [('direct_used', 'java.nio:type=BufferPool,name=direct', 'MemoryUsed'),
        ('size', 'org.apache.cassandra.metrics:type=BufferPool,scope=chunk-cache,name=Size', 'Value'),
        ('used', 'org.apache.cassandra.metrics:type=BufferPool,scope=chunk-cache,name=UsedSize', 'Value'),
        ('ovf', 'org.apache.cassandra.metrics:type=BufferPool,scope=chunk-cache,name=OverflowSize', 'Value'),
        ('thr', 'org.apache.cassandra.metrics:type=BufferPool,scope=chunk-cache,name=Capacity', 'Value')]

args = sys.argv[1:]
if not args or args[0] not in ('cell', 'control', 'inject', 'all', 'down'):
    sys.exit(__doc__)
MODE = args[0]
if MODE == 'cell':
    FCS, VB, ROWS = int(args[1]), int(args[2]), int(args[3])
    TAG = f'f{FCS}_b{VB}'
elif MODE == 'control':
    FCS = int(args[1]); TAG = f'control_f{FCS}'
elif MODE == 'inject':
    FCS = int(args[1]); TAG = f'inject_f{FCS}'
else:
    TAG = MODE
ROOT = f'{HOME}/stage4-logs/hu/{RUN}/cluster'
LOGS = f'{ROOT}/{TAG}'
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
SUMMARY = open(LOGS + '/summary.txt', 'a' if MODE in ('down', 'all') else 'w')
EXPECT = {'yes': 0, 'no': 0}
CHILDREN = []
PIDS = {}
TRACE = LOGS + '/hu.trace'


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
    except subprocess.TimeoutExpired:
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
    note(f'EXPECTED: {desc} - {"yes" if cond else "NO (recorded; the AI judges it in the results file)"}')
    return bool(cond)


def pid_of(node):
    f = f'{HU}/{node}/cassandra.pid'
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


def mine_left():
    """java daemons of this harness only (the host is shared): command line carries our directory"""
    out = []
    for p in glob.glob('/proc/[0-9]*/cmdline'):
        try:
            c = open(p).read().replace('\0', ' ')
        except OSError:
            continue
        if 'CassandraDaemon' in c and '/s4-hu-run/' in c and ' java ' in (' ' + c):
            out.append((p.split('/')[2], c[:80]))
    return out


def nodetool(node, cmd, timeout=180, check=False, quiet=True):
    return sh(f'bin/nodetool -h 127.0.0.1 -p {NODES[node][1]} {cmd}', timeout=timeout, check=check, quiet=quiet)


def stop_node(node, wait_s=120):
    if pid_of(node) is None:
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
    left = mine_left()
    if left:
        log('WARNING: a CassandraDaemon of this harness is still running: ' + str(left))
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
                 env=dict(os.environ, CASSANDRA_HOME=C, HU_NATIVE_PORT='9145'))
    js = [l for l in out.splitlines() if l.startswith('{')]
    return json.loads(js[-1]) if js else None


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def start_node(node, fcs, extra_yaml=(), byteman=True):
    if pid_of(node) is not None:
        fail(f'{node} is already running')
    PIDS.pop(node, None)
    _, y = sh(f'{HARNESS}/make-node-yaml.sh {node} {fcs} ' + ' '.join(extra_yaml), env=dict(os.environ, CASSANDRA_HOME=C, HU=HU))
    note(y.strip().splitlines()[-1][:1200])
    N = f'{HU}/{node}'
    env = dict(os.environ, CASSANDRA_CONF=N + '/conf', CASSANDRA_LOG_DIR=N + '/logs', MAX_HEAP_SIZE='2G', HEAP_NEWSIZE='400M')
    env.pop('JVM_EXTRA_OPTS', None)
    extra = ''
    if node == 'A' and byteman == 'inject':
        extra = (f'-javaagent:{BM}=listener:true,port:{BYTEMAN_PORT},sys:{TOOLS}/hu-control.jar,script:{HARNESS}/hu-inject.btm '
                 f'-Dstage4.flagdir={LOGS} -Dorg.jboss.byteman.verbose=false')
    elif node == 'A' and byteman:
        extra = (f'-javaagent:{BM}=listener:true,port:{BYTEMAN_PORT},sys:{TOOLS}/hu-helper.jar,script:{HARNESS}/hu.btm '
                 f'-Dstage4.trace={TRACE} -Dorg.jboss.byteman.verbose=false')
    note(f'start {node}: MAX_HEAP_SIZE=2G JVM_EXTRA_OPTS="{extra}"')
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
    d = f'{HU}/A/hints'
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
    return sorted(out)


def rss_anon(pid):
    try:
        for l in open(f'/proc/{pid}/status'):
            if l.startswith('RssAnon'):
                return int(l.split()[1]) * 1024
    except OSError:
        pass
    return None


class Sampler:
    """A every second: one Jmx poll JVM (direct pool, chunk-cache Size/UsedSize/OverflowSize/Capacity), RssAnon of A, the .hints files"""

    def __init__(self):
        self.stop = f'{LOGS}/sampler.stop'
        if os.path.exists(self.stop):
            os.remove(self.stop)
        self.jf = open(f'{LOGS}/samples-jmx.csv', 'w')
        cmd = ['java', '-cp', TOOLS, 'Jmx', str(NODES['A'][1]), 'poll', '1000', '100000000', self.stop]
        for _, bean, attr in COLS:
            cmd += [bean, attr]
        log('+ ' + ' '.join(cmd))
        self.p = subprocess.Popen(cmd, stdout=self.jf, stderr=subprocess.STDOUT)
        CHILDREN.append(self.p)
        self.hf = open(f'{LOGS}/samples-local.csv', 'w')
        self.hf.write('ms,rss_anon,hints_bytes,hints_files\n'); self.hf.flush()
        self.alive = True
        self.t = threading.Thread(target=self._local, daemon=True)
        self.t.start()

    def _local(self):
        nxt = time.time()
        while self.alive:
            fs = hints_files()
            self.hf.write(f'{int(time.time() * 1000)},{rss_anon(PIDS.get("A")) if pid_of("A") else ""},{sum(s for _, s in fs)},{len(fs)}\n')
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


def read_jmx_samples():
    rows = []
    for l in open(f'{LOGS}/samples-jmx.csv').read().splitlines():
        p = l.split(',')
        if len(p) == len(COLS) + 1 and p[0].isdigit():
            rows.append([int(p[0])] + [num(x) for x in p[1:]])
    return rows


def read_local_samples():
    rows = []
    for l in open(f'{LOGS}/samples-local.csv').read().splitlines()[1:]:
        p = l.split(',')
        if len(p) == 4 and p[0].isdigit():
            rows.append((int(p[0]), num(p[1]), int(p[2]), int(p[3])))
    return rows


# ------------------------------------------------------------ ground truth from the raw hint files

def parse_hints_file(path):
    """descriptor (40 + paramsLength bytes), then blocks of [Z int][C int][C bytes] (CompressedHintsWriter.writeBuffer)"""
    b = open(path, 'rb').read()
    plen = struct.unpack('>i', b[28:32])[0]
    pos = 40 + plen
    blocks = []
    while pos + 8 <= len(b):
        z, c = struct.unpack('>II', b[pos:pos + 8])
        if pos + 8 + c > len(b):
            blocks.append((z, c, 'truncated'))
            break
        blocks.append((z, c, 'ok'))
        pos += 8 + c
    return {'size': len(b), 'descriptor': 40 + plen, 'blocks': blocks, 'trailing': len(b) - pos}


def cap_of(z):
    return INITIAL if z <= INITIAL else z + z // 20


def pooled(fcs_mib, x):
    return fcs_mib * MIB >= MACRO and x <= NORMAL


# ------------------------------------------------------------ the model of the unit tier, event-driven over the trace

class Reader:
    def __init__(self):
        self.cap, self.cap_initial, self.cap_pooled = INITIAL, True, False
        self.comp, self.comp_pooled = -1, False


def simulate(events, fcs):
    """events: list of ('blk', file, Z, C) / ('cout', file). Returns list of (event, expected_overflow_delta, expected_cap) from a zero start"""
    ovf = 0
    readers = {}
    out = []
    for ev in events:
        if ev[0] == 'blk':
            _, f, z, c = ev
            r = readers.setdefault(f, Reader())
            if r.comp < 0 or c > r.comp:
                x = c + c // 20
                if r.comp >= 0 and not r.comp_pooled:
                    ovf -= r.comp
                if not pooled(fcs, x):
                    ovf += x
                r.comp_pooled, r.comp = pooled(fcs, x), x
            if r.cap < z:
                x = z + z // 20
                if r.cap_initial:
                    ovf -= INITIAL
                elif not r.cap_pooled:
                    ovf -= r.cap
                if not pooled(fcs, x):
                    ovf += x
                r.cap_pooled, r.cap, r.cap_initial = pooled(fcs, x), x, False
            out.append((ev, ovf, r.cap))
        else:
            _, f = ev
            r = readers.get(f)
            if r is not None and r.comp >= 0 and not r.comp_pooled:
                ovf -= r.comp
            out.append((ev, ovf, None))
    return out


def parse_trace(path):
    ev = []
    try:
        lines = open(path, errors='replace').read().splitlines()
    except OSError:
        return ev
    for l in lines:
        kv = dict(re.findall(r'(\w+)=(\S+)', l))
        w = l.split()[0] if l.split() else ''
        if w == 'blk':
            ev.append({'kind': 'blk', 'ms': int(kv['ms']), 'file': kv['file'], 'Z': int(kv['Z']), 'C': int(kv['C']),
                       'cap': int(kv['cap']), 'ccap': int(kv['ccap']), 'size': int(kv['size']), 'used': int(kv['used']),
                       'ovf': int(kv['ovf']), 'thr': int(kv['thr']), 'direct': int(kv['direct'])})
        elif w in ('cin', 'cout'):
            ev.append({'kind': w, 'ms': int(kv['ms']), 'file': kv['file'], 'size': int(kv['size']), 'used': int(kv['used']),
                       'ovf': int(kv['ovf']), 'direct': int(kv['direct']), 'cap': int(kv.get('cap', -1))})
    return ev


# ------------------------------------------------------------ cell

def prepare_tools():
    os.makedirs(TOOLS, exist_ok=True)
    cp = f'{C}/build/classes/main:{C}/build/lib/jars/*'
    sh(f'javac -d {TOOLS} {HARNESS}/Jmx.java')
    sh(f'mkdir -p {TOOLS}/hh && javac -d {TOOLS}/hh -cp "{cp}" {HARNESS}/HuHelper.java && cd {TOOLS}/hh && jar cf {TOOLS}/hu-helper.jar HuHelper.class')
    sh(f'mkdir -p {TOOLS}/hc && javac -d {TOOLS}/hc -cp "{cp}" {HARNESS}/HuControl.java && cd {TOOLS}/hc && jar cf {TOOLS}/hu-control.jar HuControl.class')


def header(extra=''):
    note(f'cluster-run {TAG} {time.strftime("%F %T %Z")} host {os.uname().nodename.split(".")[0]} clone {C} '
         f'{sh("git describe --tags; git rev-parse --short HEAD", quiet=True)[1].split()} run {RUN} {extra}')
    note('harness md5: ' + sh('md5sum cluster-run.py client.py make-node-yaml.sh Jmx.java HuHelper.java hu.btm', quiet=True,
                              cwd=HARNESS)[1].replace('\n', ' ')[:700])
    if mine_left():
        fail('a CassandraDaemon of this harness is already running: ' + str(mine_left()))
    _, df = sh(f'df -k {HOME}', quiet=True)
    free_gb = int(df.splitlines()[-1].split()[3]) / 1048576
    note(f'free on {HOME}: {free_gb:.1f} GiB')
    if free_gb < 15:
        fail('less than 15 GiB free')
    prepare_tools()
    sh(f'rm -rf {HU}/A {HU}/B')


def cell():
    header(f'cell fcs={FCS}MiB value={VB} rows={ROWS}')
    start_node('A', FCS)
    time.sleep(15)
    start_node('B', FCS)
    wait_up(['A', 'B'])
    sh(f'cp {HU}/A/conf/cassandra.yaml {LOGS}/A-cassandra.yaml; cp {HU}/B/conf/cassandra.yaml {LOGS}/B-cassandra.yaml')
    _, sho = nodetool('A', 'statushandoff')
    note('A statushandoff: ' + sho.strip().replace('\n', ' '))
    expect('hinted handoff running on A', 'running' in sho.lower())
    _, cmdl = sh(f'cat /proc/{pid_of("A")}/cmdline | tr "\\0" " "', quiet=True)
    for flag in ('-Xmx2G', '-XX:MaxDirectMemorySize=2g', '-XX:NativeMemoryTracking=summary', 'byteman', 'hu.btm'):
        note(f'A command line has {flag}: {flag in cmdl}')
    r = client('probe', NODES['A'][0])
    if not r or not r.get('ok'):
        fail('probe')
    r = client('schema', NODES['A'][0], 'hu', 2, 0)
    if not r or not r.get('ok'):
        fail('schema')
    note('B stops (drain, stopdaemon)')
    nodetool('B', 'drain', timeout=300, quiet=False)
    stop_node('B')
    wait_b_down()
    sm = Sampler()
    time.sleep(10)
    t_base = int(time.time() * 1000)
    base = [r for r in read_jmx_samples() if r[0] <= t_base][-3:]
    note(f'baseline (last 3 samples, JMX {[c for c, _, _ in COLS]}): {base}')
    conc = {1024: 32, 102400: 8, MIB: 4, 8 * MIB: 2}[VB]
    t_w0 = int(time.time() * 1000)
    w = client('write', NODES['A'][0], 'hu', VB, ROWS, conc, 0, 900, f'{LOGS}/keys.csv')
    t_w1 = int(time.time() * 1000)
    note(f'writes: {w}')
    expect('every write succeeded (CL ONE, B down)', bool(w) and w['failed'] == 0 and w['succeeded'] == ROWS)
    want = int(ROWS * VB * 0.99)
    last, stable = -1, 0
    t0 = time.time()
    while time.time() - t0 < 300:
        hb = sum(s for _, s in hints_files())
        stable = stable + 1 if hb == last else 0
        last = hb
        if hb >= want and stable >= 4:
            break
        time.sleep(1)
    files = hints_files()
    note(f'hints on disk before the replay: {files} (want >= {want} B of values)')
    expect('the hint files hold the values (>= 0.99 x rows x value bytes)', sum(s for _, s in files) >= want)
    truth = {}
    for name, _ in files:
        truth[name] = parse_hints_file(f'{HU}/A/hints/{name}')
    json.dump(truth, open(f'{LOGS}/hints-blocks.json', 'w'))
    nz = [(z, c) for t in truth.values() for z, c, _ in t['blocks'] if z > 0]
    zmax = max([z for z, _ in nz] or [0])
    note(f'raw hint files: {len(truth)} file(s), {sum(len(t["blocks"]) for t in truth.values())} blocks ({len(nz)} non-empty), '
         f'Zmax={zmax} -> expected capacity {cap_of(zmax)}; Cmax={max([c for _, c in nz] or [0])}; '
         f'truncated={[n for n, t in truth.items() if any(b[2] != "ok" for b in t["blocks"])]} trailing={[t["trailing"] for t in truth.values()]}')
    t_r0 = int(time.time() * 1000)
    start_node('B', FCS)
    t0 = time.time()
    gone = None
    while time.time() - t0 < 900:
        if pid_of('B') is None:
            fail('B died during the replay')
        if not hints_files():
            gone = gone or time.time()
            if time.time() - gone >= 20:
                break
        else:
            gone = None
        time.sleep(1)
    t_r1 = int(time.time() * 1000)
    note(f'replay: {(t_r1 - t_r0) / 1000:.0f} s from the start of B until the hints directory was empty for 20 s; files left {hints_files()}')
    expect('the replay completed (no .hints file left within 900 s)', not hints_files())
    sm.close()
    pidA = pid_of('A')
    _, nm = sh(f'jcmd {pidA} VM.native_memory summary', check=False, quiet=True)
    open(f'{LOGS}/nmt-end.txt', 'w').write(nm)
    _, ph = nodetool('A', 'listpendinghints')
    note('listpendinghints: ' + ph.strip().replace('\n', ' | ')[:300])
    _, ths = nodetool('A', 'tpstats')
    open(f'{LOGS}/tpstats-A.txt', 'w').write(ths)
    stop_all()
    sh(f'cp {HU}/A/logs/system.log {LOGS}/A-system.log; cp {HU}/B/logs/system.log {LOGS}/B-system.log; cp {HU}/A/stdout.txt {LOGS}/A-stdout.txt', check=False)
    expect('no daemon of this harness left', not mine_left())
    analyze_cell(truth, base, t_base, t_w0, t_w1, t_r0, t_r1)
    note(f'EXPECTED totals: yes {EXPECT["yes"]} no {EXPECT["no"]}')


def analyze_cell(truth, base, t_base, t_w0, t_w1, t_r0, t_r1):
    ev = parse_trace(TRACE)
    blk = [e for e in ev if e['kind'] == 'blk']
    couts = [e for e in ev if e['kind'] == 'cout']
    nonempty_truth = [(z, c) for t in truth.values() for z, c, _ in t['blocks'] if z > 0]
    all_truth = [(z, c) for t in truth.values() for z, c, _ in t['blocks']]
    zmax = max([z for z, _ in nonempty_truth] or [0])
    note(f'trace: {len(blk)} blk lines, {len(couts)} reader close(s) (cout), files {sorted({e["file"].split("/")[-1] for e in blk})}')
    expect('the trace holds one blk line per block of the raw files', len(blk) == len(all_truth))
    expect('the (Z, C) pairs in the trace equal the raw files\' headers', sorted((e['Z'], e['C']) for e in blk) == sorted(all_truth))
    capmax = max([e['cap'] for e in blk] or [0])
    expect(f'largest reader buffer capacity in the trace = cap(Zmax) = {cap_of(zmax)} (observed {capmax})', capmax == cap_of(zmax))
    # per-block capacity = model, in trace order per file
    bad = 0
    state = {}
    for e in blk:
        s = state.setdefault(e['file'], INITIAL)
        if e['Z'] > s:
            s = cap_of(e['Z'])
        state[e['file']] = s
        if e['cap'] != s:
            bad += 1
    expect(f'every block line: capacity = max(4096, cap(Z) of the largest Z so far in that file) ({bad} deviations)', bad == 0)
    # overflow model against the observed counter
    b_ovf = base[-1][1 + [c for c, _, _ in COLS].index('ovf')] if base else None
    b_size = base[-1][1 + [c for c, _, _ in COLS].index('size')] if base else None
    b_dir = base[-1][1 + [c for c, _, _ in COLS].index('direct_used')] if base else None
    evs = []
    for e in ev:
        evs.append(('blk', e['file'], e['Z'], e['C']) if e['kind'] == 'blk' else (('cout', e['file']) if e['kind'] == 'cout' else None))
    sel = [(e, x) for e, x in zip(ev, evs) if x is not None]
    sim = simulate([x for _, x in sel], FCS)
    dev, firstdev = 0, None
    for (e, _), (_, m_ovf, _) in zip(sel, sim):
        if b_ovf is not None and e['ovf'] - b_ovf != m_ovf:
            dev += 1
            firstdev = firstdev or (e['kind'], e['ms'], e['ovf'] - b_ovf, m_ovf)
    expect(f'chunk-cache OverflowSize minus baseline equals the model after every block and reader close '
           f'({dev} deviations of {len(sel)}; first {firstdev}; baseline {b_ovf})', dev == 0 and b_ovf is not None)
    pk_ovf = max([e['ovf'] for e in blk] or [0]) - (b_ovf or 0)
    pk_size = max([e['size'] for e in blk] or [0]) - (b_size or 0)
    pk_dir = max([e['direct'] for e in blk] or [0]) - (b_dir or 0)
    jm = [r for r in read_jmx_samples() if t_r0 <= r[0] <= t_r1 + 20000]
    ci = lambda n: 1 + [c for c, _, _ in COLS].index(n)
    jm_dir = (max([r[ci('direct_used')] for r in jm if r[ci('direct_used')] is not None] or [0]) - (b_dir or 0)) if jm else None
    loc = [r for r in read_local_samples()]
    rss_b = [r[1] for r in loc if r[0] <= t_base and r[1]]
    rss_r = [r[1] for r in loc if t_r0 <= r[0] <= t_r1 + 20000 and r[1]]
    comp_cap = max([e['ccap'] for e in blk] or [0])
    note(f'readings: peak chunk-cache OverflowSize over baseline {pk_ovf}; peak Size over baseline {pk_size}; peak JVM direct over baseline (trace) {pk_dir}, '
         f'(1 s samples) {jm_dir}; largest compressedBuffer capacity {comp_cap}; RssAnon baseline {rss_b[-1] if rss_b else None} peak in replay {max(rss_r) if rss_r else None}')
    thr = FCS * MIB
    expect(f'file_cache_size is seen by the pool: Capacity = {thr}', all(e['thr'] == thr for e in blk) and bool(blk))
    if VB >= MIB:
        expect(f'peak OverflowSize over baseline >= cap(Zmax) + compressedBuffer capacity - 4096 = {cap_of(zmax) + comp_cap - INITIAL} (blocks > 128 KiB are unpooled)',
               pk_ovf >= cap_of(zmax) + comp_cap - INITIAL)
        if FCS == 1:
            expect(f'the pool\'s Size over baseline exceeds file_cache_size ({thr}) without a refusal (peak {pk_size})', pk_size > thr)
    errs = sh(f"grep -c -E 'java.lang.OutOfMemoryError|Direct buffer memory|Failed to read a hint|Corrupt hint' {LOGS}/A-system.log {LOGS}/B-system.log || true", check=False, quiet=True)[1].strip()
    note('error-like lines in system logs (A, B): ' + errs.replace('\n', ' '))
    json.dump({'fcs': FCS, 'value_bytes': VB, 'rows': ROWS, 'zmax': zmax, 'cap_expected': cap_of(zmax), 'cap_observed': capmax,
               'peak_ovf': pk_ovf, 'peak_size': pk_size, 'peak_direct_trace': pk_dir, 'peak_direct_samples': jm_dir, 'ccap': comp_cap,
               'blocks': len(all_truth), 'nonempty': len(nonempty_truth), 'model_deviations': dev, 'baseline_ovf': b_ovf, 'baseline_size': b_size,
               'replay_s': (t_r1 - t_r0) / 1000, 'hints_files': len(truth)}, open(f'{LOGS}/cell.json', 'w'))


# ------------------------------------------------------------ control

def control():
    header(f'control fcs={FCS}MiB')
    start_node('A', FCS, ('file_cache_enabled=true',), byteman=False)
    wait_up_single()
    r = client('schema', NODES['A'][0], 'huc', 1, 64)
    if not r or not r.get('ok'):
        fail('schema')
    sm = Sampler()
    time.sleep(10)
    t_base = int(time.time() * 1000)
    rows = 2048
    w = client('write', NODES['A'][0], 'huc', 64 * KIB, rows, 8, 0, 900, f'{LOGS}/keys.csv')
    note(f'writes: {w}')
    expect('every write succeeded', bool(w) and w['failed'] == 0 and w['succeeded'] == rows)
    nodetool('A', 'flush', timeout=300, quiet=False)
    time.sleep(5)
    t_s0 = int(time.time() * 1000)
    s = client('scan', NODES['A'][0], 'huc', rows, 8, 3, 600)
    t_s1 = int(time.time() * 1000)
    note(f'scan: {s}')
    expect('every read succeeded', bool(s) and s['failed'] == 0)
    time.sleep(5)
    sm.close()
    stop_all()
    sh(f'cp {HU}/A/logs/system.log {LOGS}/A-system.log', check=False)
    rows_ = read_jmx_samples()
    ci = lambda n: 1 + [c for c, _, _ in COLS].index(n)
    base = [r for r in rows_ if r[0] <= t_base][-1]
    inscan = [r for r in rows_ if t_s0 <= r[0] <= t_s1 + 5000]
    pooled_pk = max(r[ci('size')] - r[ci('ovf')] for r in inscan)
    size_pk = max(r[ci('size')] for r in inscan)
    ovf_pk = max(r[ci('ovf')] for r in inscan)
    note(f'control readings: baseline Size {base[ci("size")]} Overflow {base[ci("ovf")]} Capacity {base[ci("thr")]}; during the scan peak Size {size_pk}, '
         f'peak OverflowSize {ovf_pk}, peak pooled part (Size - OverflowSize) {pooled_pk}; samples {len(inscan)}')
    thr = FCS * MIB
    expect(f'Capacity gauge = file_cache_size = {thr}', base[ci('thr')] == thr)
    if FCS == 16:
        expect(f'the pooled part reaches file_cache_size ({thr}) during the scan', pooled_pk >= thr)
        expect(f'the pooled part never exceeds file_cache_size ({thr})', pooled_pk <= thr)
    else:
        expect(f'the pooled part grows past 16 MiB when file_cache_size is {FCS} MiB (the control moves)', pooled_pk > 16 * MIB)
    json.dump({'fcs': FCS, 'pooled_peak': pooled_pk, 'size_peak': size_pk, 'ovf_peak': ovf_pk, 'thr': thr}, open(f'{LOGS}/cell.json', 'w'))
    note(f'EXPECTED totals: yes {EXPECT["yes"]} no {EXPECT["no"]}')


def inject():
    header(f'inject fcs={FCS}MiB')
    sh(f'rm -f {LOGS}/inject {LOGS}/release {LOGS}/inject.log')
    start_node('A', FCS, (), byteman='inject')
    wait_up_single()
    sm = Sampler()
    time.sleep(10)
    t_base = int(time.time() * 1000)
    open(f'{LOGS}/inject', 'w').close()
    t0 = time.time()
    while time.time() - t0 < 60 and not os.path.exists(f'{LOGS}/inject.log'):
        time.sleep(1)
    note('inject.log: ' + (open(f'{LOGS}/inject.log').read().strip() if os.path.exists(f'{LOGS}/inject.log') else 'MISSING'))
    time.sleep(15)
    t_held = int(time.time() * 1000)
    open(f'{LOGS}/release', 'w').close()
    t0 = time.time()
    while time.time() - t0 < 60 and 'released' not in open(f'{LOGS}/inject.log').read():
        time.sleep(1)
    time.sleep(5)
    sm.close()
    stop_all()
    sh(f'cp {HU}/A/logs/system.log {LOGS}/A-system.log', check=False)
    rows_ = read_jmx_samples()
    ci = lambda n: 1 + [c for c, _, _ in COLS].index(n)
    base = [r for r in rows_ if r[0] <= t_base][-1]
    held = [r for r in rows_ if t_base < r[0] <= t_held + 2000]
    pk_pooled = max(r[ci('size')] - r[ci('ovf')] for r in held)
    pk_ovf = max(r[ci('ovf')] for r in held)
    pk_used = max(r[ci('used')] for r in held)
    thr = FCS * MIB
    note(f'inject readings: baseline Size {base[ci("size")]} Used {base[ci("used")]} Overflow {base[ci("ovf")]} Capacity {base[ci("thr")]}; '
         f'while held: peak pooled part (Size - OverflowSize) {pk_pooled}, peak OverflowSize {pk_ovf}, peak UsedSize {pk_used}; samples {len(held)}')
    expect(f'Capacity gauge = file_cache_size = {thr}', base[ci('thr')] == thr)
    expect('the 400 x 64 KiB (26,214,400 B) are held: UsedSize rose by 26,214,400', pk_used - base[ci('used')] == 400 * 65536)
    if FCS == 1:
        expect('nothing is pooled at 1 MiB (pooled part stays 0) and all 26,214,400 B are overflow', pk_pooled == 0 and pk_ovf - base[ci('ovf')] == 400 * 65536)
    elif FCS == 16:
        expect(f'the pooled part reaches file_cache_size ({thr}) and never exceeds it', pk_pooled == thr)
        expect('the rest of the 400 buffers went to overflow (OverflowSize rose, by < 26,214,400)', 0 < pk_ovf - base[ci('ovf')] < 400 * 65536)
    else:
        expect('the pooled part grows past 16 MiB (the control moves) and nothing overflows', pk_pooled > 16 * MIB and pk_ovf - base[ci('ovf')] == 0)
    json.dump({'fcs': FCS, 'pooled_peak': pk_pooled, 'ovf_peak': pk_ovf, 'used_peak': pk_used, 'base': base}, open(f'{LOGS}/cell.json', 'w'))
    note(f'EXPECTED totals: yes {EXPECT["yes"]} no {EXPECT["no"]}')


def wait_up_single(timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pid_of('A') is None:
            fail('A died during start')
        _, sb = nodetool('A', 'statusbinary')
        if re.search(r'^running\s*$', sb, re.M):
            return
        time.sleep(3)
    fail('A not serving')


def main():
    if MODE == 'down':
        stop_all()
        note(f'down: left {mine_left()}')
    elif MODE == 'cell':
        cell()
    elif MODE == 'control':
        control()
    elif MODE == 'inject':
        inject()
    else:
        for f, b, n in CELLS:
            rc = subprocess.run([sys.executable, __file__, 'cell', str(f), str(b), str(n)], env=dict(os.environ)).returncode
            note(f'cell fcs={f} value={b}: rc={rc}')
        for f in (16, 512):
            rc = subprocess.run([sys.executable, __file__, 'control', str(f)], env=dict(os.environ)).returncode
            note(f'control fcs={f}: rc={rc}')


try:
    main()
except SystemExit:
    raise
except BaseException as e:
    note(f'EXCEPTION {e!r}')
    stop_all()
    raise
finally:
    if MODE in ('cell', 'control', 'inject'):
        stop_all()
