#!/usr/bin/env python3
"""Stage 4, cluster tier, max_hints_file_size-HintsWriteExecutor.flushInternal-session.position--autonomous
(B3a-B3h as amended 2026-10-26).
usage: cluster-run.py arm <label> <L_MiB> [cap_MiB]     one arm = one fresh ring
       cluster-run.py down                              stop both nodes of this harness
  label: free text used for the log folder (L1, L16, L128, CTRL ...). cap_MiB is `max_hints_size_per_host` (control only).
An arm: wipe ~/s4-mh-run/{A,B}; start A (Byteman rules + NMT) and B; schema (RF 2); knob read-backs; stop B (DN on A);
sample (hints dir bytes/files every second; direct MemoryUsed and RssAnon every 5 s); the writer (400,000 rows x 2 KiB at
1,000 rows/s through A at ONE); wait 6 s; final readings (file sizes, NMT, counters); stop every node. Logs to
<MH_LOGS>/<label>/: session.log, summary.txt (EXPECTED lines), du.csv, mem.csv, files.txt, mh.trace, counters.txt,
nmt.txt, keys.csv, A/B system.log and yaml tails.
Exit 1 on a failed set-up or instrument check (every node is stopped).
Nodes: A = 127.0.23.1 (storage 7023, JMX 7323, native 9345, Byteman 9323), B = 127.0.23.2 (7024, 7324, 9346)."""
import csv, glob, json, os, re, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/s4-mh')
HARNESS = os.path.dirname(os.path.abspath(__file__))
RUN = os.environ.get('MH_RUN', HOME + '/s4-mh-run')
LOGROOT = os.environ.get('MH_LOGS', HOME + '/s4-mh-logs/run1')
ROWS = int(os.environ.get('MH_ROWS', 400000))
MIB = 1 << 20
NODES = {'A': dict(addr='127.0.23.1', jmx=7323, st=7023, nat=9345, bm=9323),
         'B': dict(addr='127.0.23.2', jmx=7324, st=7024, nat=9346, bm=None)}
PORTS = [7023, 7024, 7323, 7324, 9323, 9345, 9346]
BYTEMAN = C + '/build/lib/jars/byteman-4.0.20.jar'
WRITER = HARNESS + '/write-load.py'
JMXCLS = RUN + '/jmxcls'
SP_BEAN = 'org.apache.cassandra.db:type=StorageProxy'
DIRECT = 'java.nio:type=BufferPool,name=direct'

mode = sys.argv[1] if len(sys.argv) > 1 else ''
label = sys.argv[2] if mode == 'arm' else 'down'
LOGS = LOGROOT + '/' + label
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
SUMMARY = open(LOGS + '/summary.txt', 'a')
TRACE = RUN + '/A/mh.trace'


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


EXPECT = {'yes': 0, 'no': 0}


def expect(desc, cond):
    EXPECT['yes' if cond else 'no'] += 1
    note(f'EXPECTED: {desc} — {"yes" if cond else "NO (recorded; the AI judges it in the results file)"}')
    return cond


def pid_of(node):
    f = f'{RUN}/{node}/cassandra.pid'
    if not os.path.exists(f):
        return None
    try:
        pid = int(open(f).read().strip())
        cmd = open(f'/proc/{pid}/cmdline').read()
        return pid if 'CassandraDaemon' in cmd else None
    except (ValueError, OSError):
        return None


def stop_node(node):
    if pid_of(node) is None:
        return
    sh(f'bin/nodetool -p {NODES[node]["jmx"]} stopdaemon', check=False, timeout=180)
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
    for n in ('B', 'A'):
        stop_node(n)


WRITER_PROC = {'p': None}
SAMPLER = {'s': None}


def fail(msg):
    note('FAIL: ' + msg)
    p = WRITER_PROC['p']
    if p is not None and p.poll() is None:
        p.kill()
    if SAMPLER['s'] is not None:
        SAMPLER['s'].stop = True
    stop_all()
    sys.exit(1)


def ports_free():
    _, out = sh('ss -ltn', check=False, quiet=True)
    busy = [p for p in PORTS if re.search(r':%d\s' % p, out)]
    return busy


def start_node(node, byteman, yaml_args):
    if pid_of(node) is not None:
        fail(f'{node} is already running')
    n = NODES[node]
    _, y = sh(f'{HARNESS}/make-node-yaml.sh {node} ' + ' '.join(yaml_args))
    note(y.strip().splitlines()[-1][:900])
    N = f'{RUN}/{node}'
    env = dict(os.environ, CASSANDRA_CONF=N + '/conf', CASSANDRA_LOG_DIR=N + '/logs', MAX_HEAP_SIZE='1G')
    env.pop('HEAP_NEWSIZE', None)
    if byteman:
        env['JVM_EXTRA_OPTS'] = (f'-XX:NativeMemoryTracking=summary '
                                 f'-javaagent:{BYTEMAN}=script:{HARNESS}/mh.btm,listener:true,port:{n["bm"]} '
                                 f'-Dorg.jboss.byteman.verbose=false -Dstage4.trace={TRACE}')
    else:
        env['JVM_EXTRA_OPTS'] = '-XX:NativeMemoryTracking=summary'
    k = len([f for f in os.listdir(N) if f.startswith('stdout')])
    sh(f'bin/cassandra -p {N}/cassandra.pid > {N}/stdout{k}.txt 2>&1', env=env)
    time.sleep(4)
    if pid_of(node) is None:
        fail(f'{node} did not start; see {N}/stdout{k}.txt')


def status(via):
    _, out = sh(f'bin/nodetool -p {NODES[via]["jmx"]} status', check=False, quiet=True)
    st = {}
    for m in re.finditer(r'^([UD][NLJM])\s+(\S+)\s', out, re.M):
        st[m.group(2)] = m.group(1)
    return st, out


def wait_state(via, want, timeout=300, binary=True):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pid_of(via) is None:
            fail(f'{via} died')
        st, out = status(via)
        sb_ok = True
        if binary:
            _, sb = sh(f'bin/nodetool -p {NODES[via]["jmx"]} statusbinary', check=False, quiet=True)
            sb_ok = bool(re.search(r'^running\s*$', sb, re.M))
        if sb_ok and all(st.get(a) == s for a, s in want.items()):
            note(f'{via} sees {want} after {time.time() - t0:.0f} s')
            SESSION.write(out + '\n')
            return
        time.sleep(2)
    fail(f'{via}: state {want} not reached in {timeout} s')


def jmx(node, *args):
    _, out = sh(f'java -cp {JMXCLS} Jmx {NODES[node]["jmx"]} ' + ' '.join(f"'{a}'" for a in args), check=False, timeout=60, quiet=True)
    return out


def rss_anon(pid):
    try:
        for l in open(f'/proc/{pid}/status'):
            if l.startswith('RssAnon:'):
                return int(l.split()[1]) * 1024
    except OSError:
        pass
    return -1


class Sampler(threading.Thread):
    """1 s: bytes and count of .hints files in A's hints directory. 5 s: direct MemoryUsed (JMX), RssAnon."""

    def __init__(self):
        super().__init__(daemon=True)
        self.stop = False
        self.fd = open(LOGS + '/du.csv', 'w', newline='')
        self.wd = csv.writer(self.fd); self.wd.writerow(['ms', 'bytes', 'files'])
        self.fm = open(LOGS + '/mem.csv', 'w', newline='')
        self.wm = csv.writer(self.fm); self.wm.writerow(['ms', 'direct_used', 'rss_anon'])
        self.last_mem = 0

    def sample(self):
        ms = int(time.time() * 1000)
        d = RUN + '/A/hints'
        b = n = 0
        for name in os.listdir(d):
            if name.endswith('.hints'):
                try:
                    b += os.stat(os.path.join(d, name)).st_size; n += 1
                except FileNotFoundError:
                    pass
        self.wd.writerow([ms, b, n]); self.fd.flush()
        if time.time() - self.last_mem >= 5:
            self.last_mem = time.time()
            out = jmx('A', 'get', DIRECT, 'MemoryUsed')
            m = re.search(r'MemoryUsed\|(\d+)', out)
            self.wm.writerow([ms, m.group(1) if m else -1, rss_anon(pid_of('A') or 0)]); self.fm.flush()

    def run(self):
        while not self.stop:
            try:
                self.sample()
            except Exception as e:
                log(f'sampler: {e!r}')
            time.sleep(1)


def run_arm(L, cap):
    busy = ports_free()
    if busy:
        fail(f'ports in use before the start: {busy}')
    left = sh("ps -eo pid,cmd | grep '[C]assandraDaemon' | grep -c s4-mh-run || true", check=False, quiet=True)[1].strip()
    if left not in ('0', ''):
        fail('a CassandraDaemon from s4-mh-run is already running')
    sh(f'rm -rf {RUN}/A {RUN}/B', check=True)
    os.makedirs(RUN, exist_ok=True)
    if not os.path.isdir(JMXCLS):
        os.makedirs(JMXCLS)
        sh(f'javac -d {JMXCLS} {HARNESS}/Jmx.java')
    yaml = [f'max_hints_file_size={L}MiB'] + ([f'max_hints_size_per_host={cap}MiB'] if cap else [])
    note(f'ARM {label}: max_hints_file_size {L} MiB, max_hints_size_per_host {cap or "unset (0B)"}, rows {ROWS}')
    t_start = int(time.time() * 1000)
    start_node('A', True, yaml)
    wait_state('A', {NODES['A']['addr']: 'UN'}, timeout=240)
    start_node('B', False, yaml)
    wait_state('A', {NODES['A']['addr']: 'UN', NODES['B']['addr']: 'UN'}, timeout=300)
    # the harness mirror of the knobs
    cfg = ''
    for line in open(f'{RUN}/A/logs/system.log', errors='replace'):
        if 'max_hints_file_size' in line and 'Node configuration' in line:
            cfg = line
    m = re.search(r'max_hints_file_size=([^;,\]]+)', cfg)
    note(f'KNOB node A configuration line: max_hints_file_size={m.group(1) if m else "?"}')
    expect(f'node A configuration reports max_hints_file_size {L}MiB', bool(m) and m.group(1).strip() in (f'{L}MiB', f'{L * MIB}'))
    out = jmx('A', 'get', SP_BEAN, 'MaxHintsSizePerHostInMiB')
    mm = re.search(r'MaxHintsSizePerHostInMiB\|(-?\d+)', out)
    back = int(mm.group(1)) if mm else None
    note(f'KNOB node A MaxHintsSizePerHostInMiB read back {back}')
    expect(f'max_hints_size_per_host read back {cap or 0} MiB', back == (cap or 0))
    rc, so = sh(f'python3 {WRITER} schema {NODES["A"]["addr"]}', check=False, env=dict(os.environ, CASSANDRA_HOME=C))
    if rc != 0:
        fail('schema failed: ' + so[-300:])
    # B down
    stop_node('B')
    wait_state('A', {NODES['B']['addr']: 'DN'}, timeout=120)
    # Byteman rules loaded?
    BM = BYTEMAN.replace('byteman-4.0.20.jar', 'byteman-submit-4.0.20.jar')
    _, lst = sh(f'java -cp {BM} org.jboss.byteman.agent.submit.Submit -p {NODES["A"]["bm"]} -l', check=False, quiet=True)
    SESSION.write(lst[-2000:] + '\n')
    expect('Byteman lists the 5 rules on A', sum(1 for r in ('mh roll', 'mh session close', 'mh decide clear', 'mh decide operand', 'mh decide exit') if r in lst) == 5)
    pidA = pid_of('A')
    smp = Sampler(); SAMPLER['s'] = smp; smp.start()
    time.sleep(6)
    t_w0 = int(time.time() * 1000)
    note(f'PHASE writer start {t_w0}')
    env = dict(os.environ, CASSANDRA_HOME=C, MH_ROWS=str(ROWS))
    stopflag = LOGS + '/stopflag'
    keylog = LOGS + '/keys.csv'
    for f in (keylog, stopflag):
        if os.path.exists(f):
            os.remove(f)
    p = subprocess.Popen(['python3', WRITER, 'stream', NODES['A']['addr'], '0', stopflag, '1500', keylog], env=env,
                         stdout=open(LOGS + '/writer.out', 'w'), stderr=open(LOGS + '/writer.err', 'w'))
    WRITER_PROC['p'] = p
    while p.poll() is None:
        if pid_of('A') is None:
            fail('node A died during the writer')
        time.sleep(5)
    t_w1 = int(time.time() * 1000)
    note(f'PHASE writer end {t_w1} rc={p.returncode} ({(t_w1 - t_w0) / 1000:.0f} s)')
    wo = open(LOGS + '/writer.out').read().strip().splitlines()
    res = json.loads(wo[-1]) if wo else {}
    note('WRITER ' + json.dumps(res))
    expect('writer wrote 400,000 rows, 0 failed', res.get('written') == ROWS and res.get('failed') == 0)
    time.sleep(6)       # 6 flush periods
    t_final = int(time.time() * 1000)
    smp.stop = True
    time.sleep(2)
    note(f'PHASE final {t_final}')
    # final readings
    d = RUN + '/A/hints'
    fl = sorted((n, os.stat(os.path.join(d, n)).st_size) for n in os.listdir(d) if n.endswith('.hints'))
    with open(LOGS + '/files.txt', 'w') as f:
        for n, sz in fl:
            f.write(f'{n} {sz}\n')
    note(f'FILES {len(fl)} files, {sum(s for _, s in fl)} bytes; hints dir listing in files.txt')
    sh(f'jcmd {pidA} VM.native_memory summary > {LOGS}/nmt.txt 2>&1', check=False)
    rss_end = rss_anon(pidA)
    out = jmx('A', 'get', DIRECT, 'MemoryUsed', 'org.apache.cassandra.metrics:type=Storage,name=TotalHints', 'Count',
              'org.apache.cassandra.metrics:type=Storage,name=TotalHintsInProgress', 'Count')
    open(LOGS + '/counters.txt', 'w').write(out)
    note('FINAL ' + out.replace('\n', ' ')[:600] + f' RssAnon={rss_end}')
    sh(f'cp {TRACE} {LOGS}/mh.trace', check=False)
    for n in ('A', 'B'):
        sh(f'cp {RUN}/{n}/logs/system.log {LOGS}/{n}-system.log; tail -25 {RUN}/{n}/conf/cassandra.yaml > {LOGS}/{n}-yaml-tail.txt', check=False)
    stop_all()
    left = sh("ps -eo pid,cmd | grep '[C]assandraDaemon' | grep -c s4-mh-run || true", check=False, quiet=True)[1].strip()
    expect('no CassandraDaemon from s4-mh-run left', left in ('0', ''))
    note(f'ARM {label} done, EXPECTED yes={EXPECT["yes"]} no={EXPECT["no"]}')


if mode == 'arm':
    L = int(sys.argv[3]); cap = int(sys.argv[4]) if len(sys.argv) > 4 else 0
    try:
        run_arm(L, cap)
    except SystemExit:
        raise
    except Exception as e:
        note(f'FAIL: exception {e!r}')
        stop_all()
        sys.exit(1)
elif mode == 'down':
    stop_all()
    note('down: both nodes stopped')
else:
    print(__doc__); sys.exit(2)
