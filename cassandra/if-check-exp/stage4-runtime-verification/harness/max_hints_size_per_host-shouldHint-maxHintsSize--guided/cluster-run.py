#!/usr/bin/env python3
"""Stage 4, cluster tier, max_hints_size_per_host-shouldHint-maxHintsSize (case 9b-9e, amended 2026-10-14).
usage: cluster-run.py run | down
  run    one cluster lifetime: wipe, three nodes up, schema; control (all up); N3 down; each enabled value (A until the first
         refusal for N3, B after it); N2 down too; the two-host arm; the default arm (0); the loss read-back; every node
         stopped. Logs every command to <logs>/session.log and writes summary.txt (EXPECTED lines), phases.csv, du.csv,
         counters.csv, arms.csv, keys/<phase>.csv (the writer's per-row log) and readback/; N1's trace is N1/mhs.trace
         under ~/stage4-mhs (copied to <logs>/mhs.trace at the end).
  down   stop every node of this harness.
Three nodes on this host: N1 = 127.0.0.2 (JMX 7102, the coordinator, Byteman rules + listener), N2 = 127.0.0.3 (7103),
N3 = 127.0.0.4 (7104); keyspace ks, RF 3; the writer goes through N1 only.
Exit 1: an instrument or set-up check failed (knob read-back, a node not UN/DN, no trace line, writer errors, the limit
never reached); on a failure every node is stopped.
Environment (defaults are run 1's; anything else is a shakedown, not a reading): MHS_VALUES (16,64,256), MHS_TWO (64),
MHS_B (90 s), MHS_CTRL (30 s), MHS_DEFAULT_S (600 s), MHS_LOGS (~/stage4-logs/mhs/run1)."""
import csv, json, os, re, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-run1')
HARNESS = os.path.dirname(os.path.abspath(__file__))
MHS = os.environ.get('MHS', HOME + '/stage4-mhs')
LOGS = os.environ.get('MHS_LOGS', HOME + '/stage4-logs/mhs/run1')
VALUES = [int(x) for x in os.environ.get('MHS_VALUES', '16,64,256').split(',')]
TWO = int(os.environ.get('MHS_TWO', 64))
B_S = float(os.environ.get('MHS_B', 90))
CTRL_S = float(os.environ.get('MHS_CTRL', 30))
DEFAULT_S = float(os.environ.get('MHS_DEFAULT_S', 600))
RATE = 200.0
R_EST = 1.04e6            # bytes/s of hints at 200 rows/s x ~5.2 KB, only for the "never reached" timeout
MIB = 1 << 20
NODES = {'N1': ('127.0.0.2', 7102), 'N2': ('127.0.0.3', 7103), 'N3': ('127.0.0.4', 7104)}
EP = {n: f'/{a}:7010' for n, (a, _) in NODES.items()}
SP_BEAN = 'org.apache.cassandra.db:type=StorageProxy'
KNOB = 'MaxHintsSizePerHostInMiB'
BYTEMAN = C + '/build/lib/jars/byteman-4.0.20.jar'
BM_SUBMIT = C + '/build/lib/jars/byteman-submit-4.0.20.jar'
TRACE = MHS + '/N1/mhs.trace'
WRITER = HARNESS + '/write-load.py'

label = sys.argv[1] if len(sys.argv) > 1 else ''
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
SUMMARY = open(LOGS + '/summary.txt', 'a' if label == 'down' else 'w')
PHASES_F = open(LOGS + '/phases.csv', 'a', newline='')
PHASES = csv.writer(PHASES_F)
ARMS_F = open(LOGS + '/arms.csv', 'w', newline='')
ARMS = csv.writer(ARMS_F)
ARMS.writerow(['arm', 'host', 'L_bytes', 'T0', 'first_false_ms', 'checked_first_false', 'F_prime_ms', 'H', 'rows_per_s', 'r',
               'T_end', 'overshoot', 'bound', 'growth_last60', 'decide_n', 'decide_true', 'decide_false', 'true_over_limit',
               'false_at_or_below', 'true_after_first_false', 'site_true', 'created_delta', 'writes', 'failed'])
EXPECT = {'yes': 0, 'no': 0}


# ---------------------------------------------------------------- plumbing

def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, file=sys.stderr)
    SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush(); log(s)


def phase(name):
    ms = int(time.time() * 1000)
    PHASES.writerow([name, ms]); PHASES_F.flush(); log(f'PHASE {name} {ms}')
    return ms


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
    f = f'{MHS}/{node}/cassandra.pid'
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
    for n in ('N3', 'N2', 'N1'):
        stop_node(n)
    left = any_daemon()
    if left:
        log('WARNING: a CassandraDaemon is still running: ' + left[:300])


WRITER_PROC = {'p': None}


def fail(msg):
    note('FAIL: ' + msg)
    p = WRITER_PROC['p']
    if p is not None and p.poll() is None:
        p.kill()
    stop_all()
    sys.exit(1)


def start_node(node, byteman=False, extra=''):
    if pid_of(node) is not None:
        fail(f'{node} is already running')
    _, y = sh(f'{HARNESS}/make-node-yaml.sh {node}')
    note(y.strip().splitlines()[-1][:700])
    N = f'{MHS}/{node}'
    env = dict(os.environ, CASSANDRA_CONF=N + '/conf', CASSANDRA_LOG_DIR=N + '/logs', MAX_HEAP_SIZE='2G')
    env.pop('HEAP_NEWSIZE', None)
    if byteman:
        env['JVM_EXTRA_OPTS'] = (f'-javaagent:{BYTEMAN}=script:{HARNESS}/should-hint.btm,listener:true '
                                 f'-Dorg.jboss.byteman.verbose=false -Dstage4.trace={TRACE}')
    elif extra:
        env['JVM_EXTRA_OPTS'] = extra
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
    for m in re.finditer(r'^([UD][NLJM])\s+(\S+)\s+.*?\s([0-9a-f]{8}-[0-9a-f-]{27})\s', out, re.M):
        st[m.group(2)] = (m.group(1), m.group(3))
    return st, out


def wait_state(via, want, timeout=300):
    """want: {address: 'UN'|'DN'}; also requires the binary protocol running on `via`."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pid_of(via) is None:
            fail(f'{via} died')
        st, out = status(via)
        _, sb = sh(f'bin/nodetool -p {NODES[via][1]} statusbinary', check=False, quiet=True)
        if re.search(r'^running\s*$', sb, re.M) and all(st.get(a, ('?',))[0] == s for a, s in want.items()):
            note(f'{via} sees {want} after {time.time() - t0:.0f} s')
            SESSION.write(out + '\n')
            return st
        time.sleep(2)
    fail(f'{via}: state {want} not reached in {timeout} s')


def jmx(port, *args):
    _, out = sh(f'java -cp {MHS}/jmxcls Jmx {port} ' + ' '.join(f"'{a}'" for a in args), check=False, timeout=60, quiet=True)
    SESSION.write(out[-3000:] + '\n')
    return out


def set_knob(mib):
    out = jmx(NODES['N1'][1], 'setint', SP_BEAN, KNOB, str(mib))
    m = re.search(KNOB + r'\|(-?\d+)', out)
    back = int(m.group(1)) if m else None
    note(f'KNOB N1 {KNOB} set {mib} read back {back}')
    if back != mib:
        fail(f'{KNOB} read back {back}, set {mib} (invalid run, 9a)')


def counters(tag):
    """Hints_created-*, Hints_not_stored-*, TotalHints on N1; one row per bean in counters.csv."""
    port = NODES['N1'][1]
    res = {}
    for pat in ('org.apache.cassandra.metrics:type=HintsService,name=Hints_created-*',
                'org.apache.cassandra.metrics:type=HintsService,name=Hints_not_stored-*'):
        for l in jmx(port, 'query', pat, 'Count').splitlines():
            parts = l.split('|')
            if len(parts) == 3 and parts[2].lstrip('-').isdigit():
                res[parts[0].split('name=')[1]] = int(parts[2])
    for l in jmx(port, 'get', 'org.apache.cassandra.metrics:type=Storage,name=TotalHints', 'Count').splitlines():
        parts = l.split('|')
        if len(parts) == 3 and parts[2].isdigit():
            res['TotalHints'] = int(parts[2])
    ms = int(time.time() * 1000)
    with open(LOGS + '/counters.csv', 'a', newline='') as f:
        w = csv.writer(f)
        for k, v in sorted(res.items()):
            w.writerow([tag, ms, k, v])
    log(f'COUNTERS {tag} {res}')
    return res


def created(cnt, node):
    return cnt.get('Hints_created-' + EP[node].replace(':', '.'), 0)


def not_stored(cnt):
    return sum(v for k, v in cnt.items() if k.startswith('Hints_not_stored-'))


# ---------------------------------------------------------------- the trace and the du sampler

class Trace:
    """Incremental parser of N1's trace file."""
    RX = {
        'decide': re.compile(r'^decide ep=(\S+) result=(true|false) checked=(-?\d+) limit=(-?\d+) ms=(\d+)$'),
        'site': re.compile(r'^site send ep=(\S+) result=(true|false) key=([0-9a-f]+) ms=(\d+)$'),
        'flush': re.compile(r'^flush host=(\S+) size=(\d+) ms=(\d+)$'),
        'roll': re.compile(r'^roll host=(\S+) ms=(\d+)$'),
    }

    def __init__(self, path):
        self.path, self.pos, self.buf = path, 0, ''
        self.decide, self.site, self.flush, self.roll, self.other = [], [], [], [], []

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
            m = self.RX['decide'].match(l)
            if m:
                self.decide.append((int(m.group(5)), m.group(1), m.group(2) == 'true', int(m.group(3)), int(m.group(4))))
                continue
            m = self.RX['site'].match(l)
            if m:
                self.site.append((int(m.group(4)), m.group(1), m.group(2) == 'true', int(m.group(3), 16)))
                continue
            m = self.RX['flush'].match(l)
            if m:
                self.flush.append((int(m.group(3)), m.group(1), int(m.group(2))))
                continue
            m = self.RX['roll'].match(l)
            if m:
                self.roll.append((int(m.group(2)), m.group(1)))
                continue
            if l.strip():
                self.other.append(l)


TR = Trace(TRACE)


class Sampler(threading.Thread):
    """Every second: per host id, the sum of the .hints files' sizes in N1's hints directory and their count; plus the total
    .hints bytes in N2's and N3's own hints directories (they coordinate nothing, so they must stay empty)."""

    def __init__(self, hosts):
        super().__init__(daemon=True)
        self.hosts = hosts          # host id -> label
        self.hist = {h: [] for h in hosts}
        self.stop = False
        self.f = open(LOGS + '/du.csv', 'a', newline='')
        self.w = csv.writer(self.f)

    def sample(self):
        ms = int(time.time() * 1000)
        per = {h: [0, 0] for h in self.hosts}
        d = MHS + '/N1/hints'
        for name in os.listdir(d):
            if not name.endswith('.hints'):
                continue
            h = name[:36]
            try:
                sz = os.stat(os.path.join(d, name)).st_size
            except FileNotFoundError:
                continue
            if h not in per:
                per[h] = [0, 0]
                self.hosts.setdefault(h, 'unknown-' + h[:8])
                self.hist.setdefault(h, [])
            per[h][0] += sz
            per[h][1] += 1
        for h, (b, n) in per.items():
            self.hist[h].append((ms, b, n))
            self.w.writerow([ms, self.hosts[h], h, b, n])
        for node in ('N2', 'N3'):
            dd = f'{MHS}/{node}/hints'
            b = sum(os.stat(os.path.join(dd, x)).st_size for x in os.listdir(dd) if x.endswith('.hints')) if os.path.isdir(dd) else 0
            self.w.writerow([ms, node + '-own-dir', '', b, ''])
        self.f.flush()

    def run(self):
        while not self.stop:
            try:
                self.sample()
            except Exception as e:     # a file deleted mid-scan; the next second reads it again
                log(f'sampler: {e!r}')
            time.sleep(1)

    def at(self, h, ms):
        """The last sample of host h at or before ms (bytes, files)."""
        best = (0, 0)
        for t, b, n in self.hist.get(h, []):
            if t <= ms:
                best = (b, n)
            else:
                break
        return best

    def latest(self, h):
        return self.hist[h][-1][1:] if self.hist.get(h) else (0, 0)


# ---------------------------------------------------------------- the writer

STATE = {'next_pk': 1}


def run_stream(tag, max_s, until=None):
    """Starts the writer for `tag`; `until(now_ms)` returns True when the stream should stop (else it runs max_s)."""
    flag = f'{LOGS}/stop-{tag}.flag'
    if os.path.exists(flag):
        os.remove(flag)
    keylog = f'{LOGS}/keys/{tag}.csv'
    cmd = ['python3', WRITER, 'stream', NODES['N1'][0], str(STATE['next_pk']), flag, str(max_s), keylog]
    log('+ ' + ' '.join(cmd))
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=C)
    WRITER_PROC['p'] = p
    t0 = phase(f'{tag} stream start')
    while p.poll() is None:
        time.sleep(0.5)
        TR.poll()
        if until is not None and until(int(time.time() * 1000)):
            open(flag, 'w').close()
            break
    out, err = p.communicate(timeout=max_s + 300)
    WRITER_PROC['p'] = None
    t1 = phase(f'{tag} stream end')
    SESSION.write(err[-2000:] + '\n')
    try:
        res = json.loads(out.strip().splitlines()[-1])
    except (ValueError, IndexError):
        fail(f'writer {tag}: no result ({err[-500:]})')
    note(f'WRITER {tag}: written {res["written"]} ok {res["succeeded"]} failed {res["failed"]} '
         f'pk {res["first_pk"]}..{res["last_pk"]} {res["rows_per_s"]} rows/s, stopped by {res["stopped_by"]}')
    if res['written'] > 0:
        STATE['next_pk'] = res['last_pk'] + 1
    TR.poll()
    return res, t0, t1


# ---------------------------------------------------------------- arms

def decides(node, t0, t1):
    return [d for d in TR.decide if d[1] == EP[node] and t0 <= d[0] <= t1]


def sites(node, t0, t1):
    return [s for s in TR.site if s[1] == EP[node] and t0 <= s[0] <= t1]


def enabled_arm(name, mib, node, SAM, hostid, ctx):
    """One enabled value for one down host: A until the first refusal, B for B_S seconds after it (9e)."""
    L = mib * MIB
    note(f'--- arm {name}: {KNOB} = {mib} MiB, host {node} ({hostid})')
    set_knob(mib)
    c0 = counters(f'{name} before')
    T0 = SAM.latest(hostid)[0]
    note(f'{name}: T0 ({node} files) = {T0} B')
    timeout_s = 2 * max(L - T0, 0) / R_EST + 60
    first = {'ms': None, 'i': len(TR.decide)}
    a_start = int(time.time() * 1000)

    def until(now):
        if first['ms'] is None:
            for d in TR.decide[first['i']:]:
                first['i'] += 1
                if d[0] >= a_start and d[1] == EP[node] and not d[2]:
                    first['ms'] = d[0]
                    note(f'{name}: first refusal for {node} at +{(d[0] - a_start) / 1000:.1f} s, checked={d[3]} limit={d[4]}')
                    PHASES.writerow([f'{name} first false', d[0]]); PHASES_F.flush()
                    break
            if first['ms'] is None and now - a_start > timeout_s * 1000:
                return True
            return False
        return now >= first['ms'] + B_S * 1000

    res, t0, t1 = run_stream(name, timeout_s + B_S + 120, until)
    if first['ms'] is None:
        fail(f'{name}: no refusal for {node} within {timeout_s:.0f} s — the files never reached L (invalid run, 9a)')
    time.sleep(3)                     # one flush period and more, so the last accepted hints reach the file
    SAM.sample()
    c1 = counters(f'{name} after')
    t_end = int(time.time() * 1000)
    ctx[name] = dict(t0=t0, t1=t1, end=t_end, first=first['ms'], res=res, c0=c0, c1=c1)
    analyse_enabled(name, L, node, SAM, hostid, T0, ctx[name])


def analyse_enabled(name, L, node, SAM, hostid, T0, a):
    t0, ff, t_end, res = a['t0'], a['first'], a['end'], a['res']
    ds = decides(node, t0, t_end)
    dt = [d for d in ds if d[2]]
    dfl = [d for d in ds if not d[2]]
    true_over = [d for d in ds if d[2] and d[4] > 0 and d[3] > d[4]]
    false_le = [d for d in ds if not d[2] and not (d[3] > d[4] > 0)]
    true_after = [d for d in ds if d[2] and d[0] > ff]
    limits = sorted({d[4] for d in ds})
    first_d = next(d for d in ds if d[0] == ff and not d[2])
    ss = sites(node, t0, t_end)
    site_true = sum(1 for s in ss if s[2])
    fl = [f for f in TR.flush if f[1] == hostid]
    # the flush that moved the operand above L: the last flush of this host at or before the first refusal
    before = [f for f in fl if f[0] <= ff]
    cross = before[-1] if before else None
    prev = before[-2] if len(before) > 1 else None
    Fp = (cross[0] - prev[0]) if (cross and prev) else None
    a_true = [d for d in dt if d[0] <= ff]
    T_end, files_end = SAM.latest(hostid)
    # H: bytes per hint over the whole arm (every accepted hint is in the files by T_end), new file headers included
    H = (T_end - T0) / site_true if site_true else None
    T_b60 = SAM.at(hostid, max(ff + 5000, a['end'] - 3000 - 60000))[0]   # B's last 60 s (from 5 s after the refusal if B is shorter)
    growth60 = T_end - T_b60
    r = H * res['rows_per_s'] if H else None
    bound = L + r * Fp / 1000 + H if (r and Fp) else None
    created_d = created(a['c1'], node) - created(a['c0'], node)
    total_d = a['c1'].get('TotalHints', 0) - a['c0'].get('TotalHints', 0)
    ns = not_stored(a['c1'])
    note(f'{name}: decide lines {len(ds)} (true {len(dt)}, false {len(dfl)}), limits seen {limits}; first refusal checked={first_d[3]}; '
         f'flushes bracketing it {prev[2] if prev else None} -> {cross[2] if cross else None} B, F\' = {Fp} ms; H = {H and round(H, 1)} B; '
         f'r = {r and round(r)} B/s; T_end = {T_end} B ({files_end} files), overshoot {T_end - L} B, bound {bound and round(bound)}; '
         f'growth over B\'s last 60 s {growth60} B; site send true {site_true}; Hints_created +{created_d}; TotalHints +{total_d}')
    expect(f'{name}: every decide for {node} has limit = {L} B', limits == [L])
    expect(f'{name}: no decide true with checked > limit (count {len(true_over)})', len(true_over) == 0)
    expect(f'{name}: every false has checked > limit (exceptions {len(false_le)})', len(false_le) == 0)
    expect(f'{name}: no true after the first refusal (count {len(true_after)})', len(true_after) == 0)
    expect(f'{name}: the first refusal comes when checked first exceeds L (checked {first_d[3]} > {L}, previous trues all <= L)',
           first_d[3] > L and all(d[3] <= L for d in a_true))
    expect(f'{name}: T_end in (L, L + r*F\' + H] = ({L}, {bound and round(bound)}] (T_end {T_end})', bound is not None and L < T_end <= bound)
    expect(f'{name}: T_end <= L + 2 MiB ({T_end} <= {L + 2 * MIB})', T_end <= L + 2 * MIB)
    expect(f'{name}: files unchanged over B\'s last 60 s (growth {growth60} B)', growth60 == 0)
    expect(f'{name}: Hints_created for {node} (+{created_d}) = site send true lines ({site_true})', created_d == site_true)
    expect(f'{name}: TotalHints (+{total_d}) = site send true lines, all hosts ({sum(1 for s in TR.site if a["t0"] <= s[0] <= t_end and s[2])})',
           total_d == sum(1 for s in TR.site if a['t0'] <= s[0] <= t_end and s[2]))
    expect(f'{name}: 0 failed writes ({res["failed"]} of {res["written"]})', res['failed'] == 0)
    expect(f'{name}: Hints_not_stored absent or 0 ({ns})', ns == 0)
    # sub-prediction: du minus the operand the check last read stays within one flush's bytes
    gap = 0
    for t, b, n in SAM.hist[hostid]:
        if t < t0 or t > ff:
            continue
        last = [d for d in ds if d[0] <= t and d[3] >= 0]
        if last:
            gap = max(gap, b - last[-1][3])
    expect(f'{name}: (sub) files minus the last checked operand in A <= r*F\' + H (max {gap} B, {r and Fp and round(r * Fp / 1000 + H)})',
           r is not None and Fp is not None and gap <= r * Fp / 1000 + H)
    ARMS.writerow([name, node, L, T0, ff, first_d[3], Fp, H and round(H, 2), res['rows_per_s'], r and round(r), T_end, T_end - L,
                   bound and round(bound), growth60, len(ds), len(dt), len(dfl), len(true_over), len(false_le), len(true_after),
                   site_true, created_d, res['written'], res['failed']])
    ARMS_F.flush()
    return H, r


# ---------------------------------------------------------------- the run

def run():
    if any_daemon():
        fail('a CassandraDaemon is already running: ' + any_daemon()[:200])
    for p in (7010, 7102, 7103, 7104, 9042, 9091):
        _, o = sh(f"ss -ltn | grep -E ':{p}\\b' || true", check=False, quiet=True)
        if o.strip():
            fail(f'port {p} is in use: {o.strip()[:200]}')
    note(f'run {time.strftime("%F %T %Z")} values {VALUES} two-host {TWO} B {B_S} s control {CTRL_S} s default {DEFAULT_S} s logs {LOGS}')
    _, md5 = sh(f'cd {HARNESS} && md5sum *', cwd=HARNESS)
    note('harness md5: ' + ' '.join(f'{l.split()[1]}={l.split()[0][:8]}' for l in md5.strip().splitlines()))
    _, gd = sh('git describe --tags && git rev-parse --short HEAD')
    note('clone: ' + gd.replace('\n', ' ').strip())
    sh(f'rm -rf {MHS}/N1 {MHS}/N2 {MHS}/N3 && mkdir -p {MHS} {LOGS}/keys {LOGS}/readback')
    sh(f'mkdir -p {MHS}/jmxcls && javac -d {MHS}/jmxcls {HARNESS}/Jmx.java')
    _, ts = sh(f'java -cp "{BYTEMAN}:build/classes/main:$(ls build/lib/jars/*.jar lib/*.jar | tr \'\\n\' :)" '
               f'org.jboss.byteman.check.TestScript {HARNESS}/should-hint.btm', check=False)
    open(LOGS + '/testscript.txt', 'w').write(ts)
    if 'TestScript: no errors' not in ts:
        fail('should-hint.btm does not type-check (testscript.txt)')
    note('TestScript: no errors')

    # ring
    start_node('N1', byteman=True)
    wait_state('N1', {'127.0.0.2': 'UN'})
    start_node('N2')
    start_node('N3')
    st = wait_state('N1', {'127.0.0.2': 'UN', '127.0.0.3': 'UN', '127.0.0.4': 'UN'}, timeout=400)
    for n in ('N2', 'N3'):
        wait_state(n, {NODES[n][0]: 'UN'})
    hostid = {n: st[NODES[n][0]][1] for n in NODES}
    note(f'host ids: {hostid}')
    json.dump(hostid, open(LOGS + '/hostids.json', 'w'))
    _, sl = sh(f'java -cp {BM_SUBMIT} org.jboss.byteman.agent.submit.Submit -l', check=False)
    open(LOGS + '/submit-l.txt', 'w').write(sl)
    nrules = len(re.findall(r'^RULE mhs ', sl, re.M))
    note(f'Submit -l: {nrules} mhs rules loaded')
    if nrules != 6:
        fail(f'Submit -l lists {nrules} rules, expected 6 (submit-l.txt)')
    _, out = sh(f'python3 {WRITER} probe {NODES["N1"][0]}')
    _, out = sh(f'python3 {WRITER} schema {NODES["N1"][0]}')
    _, jl = sh(f"ps -o args= -p {pid_of('N1')}", check=False, quiet=True)
    open(LOGS + '/N1-cmdline.txt', 'w').write(jl)
    for n in NODES:
        sh(f'cp {MHS}/{n}/conf/cassandra.yaml {LOGS}/{n}-cassandra.yaml')
    out = jmx(NODES['N1'][1], 'get', SP_BEAN, KNOB)
    note(f'default {KNOB} on N1: {out.strip().splitlines()[0] if out.strip() else out}')
    SAM = Sampler({hostid[n]: n for n in ('N2', 'N3')})
    SAM.start()
    ctx = {}

    # control: all up
    note('--- control: all three nodes up')
    c0 = counters('control before')
    res, t0, t1 = run_stream('control', CTRL_S)
    time.sleep(3)
    TR.poll(); SAM.sample()
    c1 = counters('control after')
    hint_files = [x for x in os.listdir(MHS + '/N1/hints') if x.endswith('.hints')]
    dc = [d for d in TR.decide if t0 <= d[0] <= t1 + 3000]
    created_any = sum(v for k, v in c1.items() if k.startswith('Hints_created-'))
    expect(f'control: no .hints file on N1 ({len(hint_files)})', len(hint_files) == 0)
    expect(f'control: no decide line ({len(dc)})', len(dc) == 0)
    expect(f'control: Hints_created 0 ({created_any})', created_any == 0)
    expect(f'control: 0 failed writes ({res["failed"]} of {res["written"]})', res['failed'] == 0)
    ctx['control'] = dict(t0=t0, t1=t1, res=res)
    if hint_files or dc:
        fail('control made hints with every node up (invalid run, 9a)')

    # N3 down
    stop_node('N3')
    phase('N3 stopped')
    wait_state('N1', {'127.0.0.4': 'DN'})
    phase('N3 DN on N1')
    for mib in VALUES:
        enabled_arm(f'L{mib}', mib, 'N3', SAM, hostid['N3'], ctx)
    plateaus = [(m, ctx[f'L{m}']) for m in VALUES]

    # two-host arm
    stop_node('N2')
    phase('N2 stopped')
    wait_state('N1', {'127.0.0.3': 'DN', '127.0.0.4': 'DN'})
    phase('N2 DN on N1')
    name = f'two{TWO}'
    T3_before = SAM.latest(hostid['N3'])[0]
    enabled_arm(name, TWO, 'N2', SAM, hostid['N2'], ctx)
    a = ctx[name]
    d3 = decides('N3', a['t0'], a['end'])
    T3_after = SAM.latest(hostid['N3'])[0]
    c3 = created(a['c1'], 'N3') - created(a['c0'], 'N3')
    expect(f'{name}: every decide for N3 is false with checked > limit ({sum(1 for d in d3 if not d[2] and d[3] > d[4] > 0)} of {len(d3)})',
           len(d3) > 0 and all((not d[2]) and d[3] > d[4] > 0 for d in d3))
    expect(f'{name}: N3 files unchanged over the arm ({T3_before} -> {T3_after})', T3_before == T3_after)
    expect(f'{name}: Hints_created for N3 +0 (+{c3})', c3 == 0)
    note(f'{name}: directory total = N3 {T3_after} + N2 {SAM.latest(hostid["N2"])[0]} = {T3_after + SAM.latest(hostid["N2"])[0]} B')

    # default arm
    note(f'--- default arm: {KNOB} = 0, N2 and N3 down, {DEFAULT_S:.0f} s')
    set_knob(0)
    c0 = counters('default before')
    g0 = {n: SAM.latest(hostid[n]) for n in ('N2', 'N3')}
    rolls0 = {n: sum(1 for r in TR.roll if r[1] == hostid[n]) for n in ('N2', 'N3')}
    res, t0, t1 = run_stream('default', DEFAULT_S)
    time.sleep(3)
    TR.poll(); SAM.sample()
    c1 = counters('default after')
    ctx['default'] = dict(t0=t0, t1=t1, res=res, c0=c0, c1=c1)
    Hs = []
    for m in VALUES:
        row = [r for r in csv.reader(open(LOGS + '/arms.csv')) if r[0] == f'L{m}']
        if row and row[0][7] not in ('', 'None'):
            Hs.append(float(row[0][7]))
    H = sum(Hs) / len(Hs) if Hs else 5200.0
    pred = H * res['rows_per_s'] * (t1 - t0) / 1000
    grow = {}
    for n in ('N2', 'N3'):
        dd = decides(n, t0, t1 + 3000)
        bad = [d for d in dd if not (d[2] and d[4] == 0 and d[3] == -1)]
        g1 = SAM.latest(hostid[n])
        grow[n] = g1[0] - g0[n][0]
        last60 = g1[0] - SAM.at(hostid[n], max(t0 + 5000, t1 - 60000))[0]
        rolls = sum(1 for r in TR.roll if r[1] == hostid[n]) - rolls0[n]
        note(f'default: {n} grew {g0[n][0]} -> {g1[0]} B ({grow[n]} B, files {g0[n][1]} -> {g1[1]}, rolls {rolls}); last 60 s {last60} B; '
             f'predicted {pred:.0f} B (H {H:.1f} x {res["rows_per_s"]} rows/s x {(t1 - t0) / 1000:.0f} s)')
        expect(f'default: every decide for {n} true with limit=0 checked=-1 ({len(dd) - len(bad)} of {len(dd)})', len(dd) > 0 and not bad)
        expect(f'default: {n} growth within 0.8-1.2 x predicted ({grow[n] / pred:.3f})', 0.8 <= grow[n] / pred <= 1.2)
        expect(f'default: {n} still growing in the last 60 s ({last60} B)', last60 > 0)
        expect(f'default: {n} passed a 128 MiB roll (rolls {rolls}, files {g0[n][1]} -> {g1[1]})', rolls >= 1 and g1[1] > g0[n][1])
    expect(f'default: the two hosts grow alike (N2/N3 = {grow["N2"] / grow["N3"]:.4f}, within 5 %)', abs(grow['N2'] / grow['N3'] - 1) <= 0.05)
    expect(f'default: 0 failed writes ({res["failed"]} of {res["written"]})', res['failed'] == 0)
    expect(f'default: Hints_not_stored absent or 0 ({not_stored(c1)})', not_stored(c1) == 0)
    for n in ('N2', 'N3'):
        cd = created(c1, n) - created(c0, n)
        stt = sum(1 for s in sites(n, t0, t1 + 3000) if s[2])
        expect(f'default: Hints_created for {n} (+{cd}) = site send true lines ({stt})', cd == stt)
    own = [r for r in csv.reader(open(LOGS + '/du.csv')) if r[1].endswith('-own-dir') and r[3] not in ('', '0')]
    expect(f'N2 and N3 own hints directories stayed empty (non-zero samples {len(own)})', len(own) == 0)
    readback(hostid, SAM, ctx)
    SAM.stop = True
    stop_all()
    sh(f'cp {TRACE} {LOGS}/mhs.trace')
    for n in NODES:
        sh(f'cp {MHS}/{n}/logs/system.log {LOGS}/{n}-system.log', check=False)
        _, e = sh(f"grep -c '^ERROR' {MHS}/{n}/logs/system.log || true", check=False, quiet=True)
        note(f'{n} system.log ERROR lines: {e.strip()}')
    note(f'other trace lines: {len(TR.other)}')
    note(f'EXPECTED totals: yes {EXPECT["yes"]}, NO {EXPECT["no"]}')
    left = any_daemon()
    note('left running: ' + (left[:200] if left else 'none'))


def readback(hostid, SAM, ctx):
    note('--- loss read-back (9d): throttle 0 on N1, N2 and N3 back, drain, then each host read alone')
    TR.poll()
    sh(f'bin/nodetool -p {NODES["N1"][1]} sethintedhandoffthrottlekb 0')
    sh(f'bin/nodetool -p {NODES["N1"][1]} gethintedhandoffthrottlekb', check=False)
    start_node('N2')
    start_node('N3')
    wait_state('N1', {'127.0.0.2': 'UN', '127.0.0.3': 'UN', '127.0.0.4': 'UN'}, timeout=400)
    phase('N2 N3 back')
    t0 = time.time()
    while time.time() - t0 < 2400:
        left = [x for x in os.listdir(MHS + '/N1/hints') if x.endswith('.hints')]
        if not left:
            break
        time.sleep(5)
    else:
        fail(f'hints not drained in 2400 s: {left[:5]}')
    phase('drained')
    note(f'hints drained in {time.time() - t0:.0f} s')
    time.sleep(10)
    TR.poll()
    # key sets from the writer's logs and the site send lines
    written, phase_of = {}, {}
    for tag in ['control'] + [f'L{m}' for m in VALUES] + [f'two{TWO}', 'default']:
        for row in csv.reader(open(f'{LOGS}/keys/{tag}.csv')):
            if row[2] == 'ok':
                written[int(row[0])] = tag
    up_n2 = {'control'} | {f'L{m}' for m in VALUES}
    st = {n: {True: set(), False: set()} for n in ('N2', 'N3')}
    for ms, ep, res, key in TR.site:
        for n in ('N2', 'N3'):
            if ep == EP[n]:
                st[n][res].add(key)
    exp = {
        'N3': {k for k, t in written.items() if t == 'control'} | st['N3'][True],
        'N2': {k for k, t in written.items() if t in up_n2} | st['N2'][True],
    }
    sites_n3 = sum(1 for s in TR.site if s[1] == EP['N3'])
    down_n3 = sum(1 for t in written.values() if t != 'control')
    expect(f'read-back: one site send line for N3 per row written while it was down ({sites_n3} lines, {down_n3} rows)', sites_n3 == down_n3)
    # N3 alone
    stop_node('N1'); stop_node('N2')
    wait_state('N3', {'127.0.0.2': 'DN', '127.0.0.3': 'DN', '127.0.0.4': 'UN'})
    got = {}
    _, o = sh(f'python3 {WRITER} count {NODES["N3"][0]} {LOGS}/readback/N3-keys.txt', timeout=900)
    got['N3'] = {int(x) for x in open(f'{LOGS}/readback/N3-keys.txt') if x.strip()}
    stop_node('N3')
    # alone, a non-seed node fails its start-up shadow round (StorageService.java:870-877, 'Unable to gossip with any
    # peers'); the property skips only that collision check (shakedown 1)
    start_node('N2', extra='-Dcassandra.allow_unsafe_join=true')
    wait_state('N2', {'127.0.0.2': 'DN', '127.0.0.3': 'UN', '127.0.0.4': 'DN'})
    _, o = sh(f'python3 {WRITER} count {NODES["N2"][0]} {LOGS}/readback/N2-keys.txt', timeout=900)
    got['N2'] = {int(x) for x in open(f'{LOGS}/readback/N2-keys.txt') if x.strip()}
    stop_node('N2')
    allk = set(written)
    for n in ('N3', 'N2'):
        missing = allk - got[n]
        extra = got[n] - exp[n]
        short = exp[n] - got[n]
        note(f'read-back {n}: rows {len(got[n])}, expected {len(exp[n])}, written {len(allk)}, missing {len(missing)}, '
             f'refused for {n} {len(st[n][False])}; extra {len(extra)}, short {len(short)}')
        expect(f'read-back {n}: holds exactly the expected rows (extra {len(extra)}, short {len(short)})', not extra and not short)
        expect(f'read-back {n}: the missing rows are exactly its refused rows ({len(missing)} vs {len(st[n][False])})', missing == st[n][False])
        with open(f'{LOGS}/readback/{n}-summary.json', 'w') as f:
            json.dump({'rows': len(got[n]), 'expected': len(exp[n]), 'written': len(allk), 'missing': len(missing),
                       'refused': len(st[n][False]), 'extra': sorted(extra)[:50], 'short': sorted(short)[:50]}, f)


def main():
    if label == 'down':
        stop_all()
        note('down: ' + (any_daemon()[:200] or 'no daemon left'))
        return
    if label != 'run':
        sys.exit(__doc__)
    try:
        run()
    except SystemExit:
        raise
    except Exception as e:
        import traceback
        log(traceback.format_exc())
        fail(f'harness error: {e!r}')


main()
