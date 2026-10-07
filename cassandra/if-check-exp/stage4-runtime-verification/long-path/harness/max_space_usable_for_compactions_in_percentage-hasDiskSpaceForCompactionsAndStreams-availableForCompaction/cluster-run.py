#!/usr/bin/env python3
"""Stage 4, cluster tier, max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction
(case 9b-9e).   usage: cluster-run.py <label>   (run in the measured node; needs sudo for the loop mount)

  d95       pct left at the default 0.95                      -> scenario A, no input shed
  f15       B/total = 1.5                                     -> scenario A
  f08, f04  B/total = 0.8, 0.4                                -> scenario B (2 and 5 inputs shed)
  f01       B/total = 0.1                                     -> scenario C (abort), then H1 (hatch off + nodetool compact)
                                                                  and H2 (hatch off + nodetool enableautocompaction)
  inflight  tables t, t2, slow; B = R0 + 3.2 s                -> I1 (t alone), I2 (t2 with slow in flight)

One node (~/cassandra-run1), TWO starts per label (case 9b "Order within a run"): a first at the default builds the inputs; with the node
stopped the Data.db lengths and df are read and pct is computed; a second carries pct. The data directory is /mnt/stage4-data/data on a fresh
4 GiB loop-mounted ext4. Logs every command to ~/stage4-logs/mscp/<label>/session.log and writes summary.txt (EXPECTED lines), passes.csv,
triggers.csv, samples.csv. Exit 1: a set-up or instrument check failed; the node is stopped on any exit.
Python 3.9+ (random.randbytes)."""
import calendar, csv, glob, json, math, os, random, re, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-run1')
HARNESS = os.path.dirname(os.path.abspath(__file__))
IMG = HOME + '/stage4-data.img'
MNT = '/mnt/stage4-data'
DATA = MNT + '/data'
MIB = 1048576
FLOOR = 50 * MIB                 # min_free_space_per_drive, default
NSST, ROWS, PAYLOAD = 8, 12800, 5120
FACTOR = {'f15': 1.5, 'f08': 0.8, 'f04': 0.4, 'f01': 0.1}
PLAN_N = {'d95': 0, 'f15': 0, 'f08': 2, 'f04': 5, 'f01': -1}      # dropped inputs planned in 9a (-1 = abort)
ARM = {'d95': 'A', 'f15': 'A', 'f08': 'B', 'f04': 'B', 'f01': 'C'}
SEED = {'t': 1000, 't2': 2000, 'slow': 3000}
CM = 'org.apache.cassandra.metrics:type=Compaction,name='
CTRS = ['CompactionsReduced', 'SSTablesDroppedFromCompaction', 'CompactionsAborted']
INFLIGHT_MARGIN = 3.2            # B = R0 + 3.2 s (9a)

if len(sys.argv) != 2 or sys.argv[1] not in list(PLAN_N) + ['inflight']:
    sys.exit(__doc__)
label = sys.argv[1]
TABLES = ['t', 't2', 'slow'] if label == 'inflight' else ['t']

D = f'{HOME}/stage4-logs/mscp/{label}'
if os.path.exists(D):
    os.rename(D, D + '.' + time.strftime('%Y%m%d-%H%M%S', time.localtime(os.path.getmtime(D))))
os.makedirs(D)
SESSION = open(D + '/session.log', 'a')
SUMMARY = open(D + '/summary.txt', 'w')
PASSES = csv.writer(open(D + '/passes.csv', 'w'))
PASSES.writerow(['label', 'arm', 'idx', 'ts_epoch', 'available', 'requested', 'sim_requested'])
TRIG = csv.writer(open(D + '/triggers.csv', 'w'))
TRIG.writerow(['label', 'arm', 'cmd', 'rc', 'seconds', 'U_before', 'B_expected', 'total_inputs', 'passes', 'sim_dropped', 'reduced_delta',
               'dropped_delta', 'aborted_delta', 'reducing_warnings', 'abort_warnings', 'info_hatch', 'files_before', 'files_after',
               'datadb_after_bytes', 'peak_du', 'final_du'])
DEBUG_LOG = C + '/logs/debug.log'
SYSTEM_LOG = C + '/logs/system.log'
SAMPLER = None
EVENT = re.compile(r'^(DEBUG|INFO|WARN|ERROR)\s+\[([^\]]*)\]\s+(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d,\d{3})\s+(\S+?):(\d+)\s+-\s+(.*)$')
PASS = re.compile(r'FileStore (.*) has (\d+) bytes available, checking if we can write (\d+) bytes')


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


def daemon_up():
    return subprocess.run("pgrep -f '[o]rg.apache.cassandra.service.CassandraDaemon'", shell=True, capture_output=True).returncode == 0


def stop_node():
    if daemon_up():
        sh('bin/nodetool stopdaemon', check=False, quiet=True)
        for _ in range(90):
            if not daemon_up():
                break
            time.sleep(1)
        if daemon_up():
            subprocess.run("pkill -9 -f '[o]rg.apache.cassandra.service.CassandraDaemon'", shell=True)
            time.sleep(2)
    if daemon_up():
        log('WARNING: a CassandraDaemon is still running')
    sh('git checkout -q conf/cassandra.yaml', check=False, quiet=True)


def fail(msg):
    note('FAIL: ' + msg)
    if SAMPLER:
        SAMPLER.stop()
    stop_node()
    sys.exit(1)


def expect(desc, cond):
    note(f'EXPECTED: {desc} — {"yes" if cond else "NO (recorded; the AI judges it in the results file)"}')
    return cond


def java_round(x):
    return int(math.floor(x + 0.5))


def df_avail():
    st = os.statvfs(MNT)
    return st.f_bavail * st.f_frsize


def table_files(table, pat='*-Data.db'):
    return sorted(glob.glob(f'{DATA}/ks1/{table}-*/{pat}'))


def datadb(table):
    out = []
    for f in table_files(table):
        try:
            out.append(os.path.getsize(f))
        except FileNotFoundError:
            pass
    return out


def du_dir(table):
    total = 0
    for d in glob.glob(f'{DATA}/ks1/{table}-*'):
        for root, _dirs, files in os.walk(d):
            for fn in files:
                try:
                    total += os.lstat(os.path.join(root, fn)).st_size
                except FileNotFoundError:
                    pass
    return total


def simulate(sizes, B, extra=0):
    """The ladder of 9a/section 5: (requested per pass, dropped) with dropped = -1 for the abort."""
    keep = sorted(sizes, reverse=True)
    reqs = []
    while True:
        s = sum(keep) + extra
        reqs.append(s)
        if s <= B:
            return reqs, len(sizes) - len(keep)
        if len(keep) > 1:
            keep.pop(0)
        else:
            return reqs, -1


# ---- driver (the bundled Python driver, protocol 5), as in the other cases' clients
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
    from cassandra.concurrent import execute_concurrent_with_args
    from cassandra import ConsistencyLevel
    return Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT, execute_concurrent_with_args, ConsistencyLevel


def connect():
    Cluster, EP, DEFAULT, _, CL = DRV
    cl = Cluster(['127.0.0.1'], protocol_version=5, execution_profiles={DEFAULT: EP(request_timeout=120, consistency_level=CL.ONE)})
    return cl, cl.connect()


# ---- JMX
def jmx_get(*pairs):
    args = [x for p in pairs for x in p]
    _, out = sh(['java', '-cp', D + '/jmx-classes', 'Jmx', 'get', *args], check=False, quiet=True)
    vals = {}
    for l in out.splitlines():
        parts = l.split('|')
        if len(parts) == 3:
            vals[(parts[0], parts[1])] = parts[2]
    return vals


def counters():
    v = jmx_get(*[(CM + n, 'Count') for n in CTRS])
    return {n: int(float(v[(CM + n, 'Count')])) for n in CTRS}


# ---- node and filesystem
def prepare_fs():
    sh(f'if mountpoint -q {MNT}; then sudo umount {MNT}; fi', check=False)
    rc, _ = sh(f'mountpoint -q {MNT}', check=False, quiet=True)
    if rc == 0:
        fail(f'{MNT} is still mounted and could not be unmounted')
    sh(f'rm -f {IMG} && truncate -s 4G {IMG} && mkfs.ext4 -q -F {IMG}')
    sh(f'sudo mkdir -p {MNT} && sudo mount -o loop {IMG} {MNT} && sudo mkdir -p {DATA} && sudo chown {os.getuid()}:{os.getgid()} {DATA}')
    note('FILESYSTEM ' + sh(f'df -B1 {MNT} | tail -1')[1].strip())


def start_node(tag):
    if daemon_up():
        fail('a CassandraDaemon is already running')
    env = dict(os.environ, MAX_HEAP_SIZE='4G')
    sh(f'bin/cassandra -p {D}/cassandra.pid > {D}/startup-{tag}.log 2>&1', env=env)
    for _ in range(150):
        _, st = sh('bin/nodetool statusbinary', check=False, quiet=True)
        _, ns = sh('bin/nodetool status', check=False, quiet=True)
        if 'running' in st and re.search(r'^UN', ns, re.M):
            break
        time.sleep(2)
    else:
        fail(f'node ({tag}) did not come up')
    note(f'node up ({tag})')


# ---- log parsing
def read_since(off):
    with open(DEBUG_LOG, 'rb') as f:
        f.seek(off)
        return f.read().decode('utf-8', 'replace')


def parse_events(text):
    ev = []
    for l in text.splitlines():
        m = EVENT.match(l)
        if m:
            t = m.group(3)
            ts = calendar.timegm(time.strptime(t[:19], '%Y-%m-%dT%H:%M:%S')) + int(t[20:23]) / 1000.0
            ev.append(dict(level=m.group(1), thread=m.group(2), ts=ts, src=m.group(4) + ':' + m.group(5), msg=m.group(6)))
    return ev


def passes_of(ev, minreq):
    out = []
    for e in ev:
        if e['level'] == 'DEBUG' and e['src'].startswith('Directories.java'):
            m = PASS.search(e['msg'])
            if m and int(m.group(3)) >= minreq:
                out.append((e['ts'], int(m.group(2)), int(m.group(3))))
    return out


# ---- sampler: every 500 ms du of each table directory, df, and the rows of system_views.sstable_tasks
class Sampler(threading.Thread):
    def __init__(self, session, tables, path):
        super().__init__(daemon=True)
        self.session, self.tables = session, tables
        self.stop_ev = threading.Event()
        self.f = open(path, 'w')
        self.w = csv.writer(self.f)
        self.w.writerow(['epoch', 'avail'] + ['du_' + t for t in tables] + ['tasks'])
        self.hist = []
        self.latest = {}
        self.lock = threading.Lock()
        self.q = ('SELECT keyspace_name, table_name, kind, progress, total, total_compressed, completion_ratio '
                  'FROM system_views.sstable_tasks')

    def run(self):
        nxt = time.time()
        while not self.stop_ev.is_set():
            t = time.time()
            try:
                rows = list(self.session.execute(self.q))
            except Exception as e:                      # recorded in the row, the sampler goes on
                rows = []
                log(f'sampler query failed: {e!r}')
            tasks = {r.table_name: (r.progress, r.total, r.total_compressed, r.kind) for r in rows if r.keyspace_name == 'ks1'}
            avail = df_avail()
            dus = {x: du_dir(x) for x in self.tables}
            self.w.writerow([f'{t:.3f}', avail] + [dus[x] for x in self.tables] + [json.dumps(tasks)])
            self.f.flush()
            with self.lock:
                self.hist.append((t, avail, dus, tasks))
                self.latest = tasks
            nxt += 0.5
            time.sleep(max(0.0, nxt - time.time()))

    def stop(self):
        self.stop_ev.set()

    def window(self, t0, t1):
        with self.lock:
            return [h for h in self.hist if t0 <= h[0] <= t1]

    def remaining(self, table, epoch):
        """R = total_compressed x (1 - progress/total) of the table's task, interpolated to epoch (None if never seen)."""
        with self.lock:
            pts = [(h[0], h[3][table]) for h in self.hist if table in h[3] and h[3][table][1] > 0]
        if not pts:
            return None
        val = lambda row: row[2] * (1.0 - row[0] / row[1])
        prev = [p for p in pts if p[0] <= epoch]
        nxt = [p for p in pts if p[0] >= epoch]
        if prev and nxt:
            (ta, ra), (tb, rb) = prev[-1], nxt[0]
            if tb == ta:
                return val(ra)
            return val(ra) + (val(rb) - val(ra)) * (epoch - ta) / (tb - ta)
        return val((prev or nxt)[-1 if prev else 0][1])


# ---- one trigger and its analysis
def ladder_trigger(arm, cmd, table, pct_eff, planned_n, first=False, expect_info=False):
    """Run `cmd` (a nodetool command that starts one major compaction of `table`) and compare the window of debug.log, the counters and the
    files with the ladder simulated from the Data.db lengths and the expected B."""
    U1 = df_avail()
    sizes = datadb(table)
    B = java_round((U1 - FLOOR) * pct_eff)
    reqs, dropped = simulate(sizes, B)
    note(f'SIM {arm}: table {table} Data.db lengths {sizes} total {sum(sizes)}; U {U1}; pct {pct_eff}; B {B}; B/total {B / sum(sizes):.4f}; '
         f'simulated passes {reqs}; dropped {dropped}')
    c0 = counters()
    off = os.path.getsize(DEBUG_LOG)
    files0 = table_files(table)
    t0 = time.time()
    rc, out = sh(cmd, check=False, timeout=900)
    t1 = time.time()
    time.sleep(8)                                       # asynchronous log appender and deletion of the obsolete inputs
    ev = parse_events(read_since(off))
    c1 = counters()
    files1 = table_files(table)
    return analyze_ladder(arm, cmd, table, sizes, U1, B, reqs, dropped, planned_n, ev, c0, c1, rc, out, files0, files1, t0, t1, first, expect_info)


def analyze_ladder(arm, cmd, table, sizes, U1, B, reqs, dropped, planned_n, ev, c0, c1, rc, out, files0, files1, t0, t1, first, expect_info):
    minreq = min(sizes) // 2
    ps = passes_of(ev, minreq)
    for i, (ts, av, rq) in enumerate(ps):
        PASSES.writerow([label, arm, i, f'{ts:.3f}', av, rq, reqs[i] if i < len(reqs) else ''])
    note(f'OBSERVED {arm}: rc {rc}; pass lines (available, requested): {[(a, r) for _, a, r in ps]}')
    reducing = [e for e in ev if e['level'] == 'WARN' and e['msg'].endswith('Reducing scope.')]
    aborts = [e for e in ev if e['level'] == 'WARN' and e['msg'].startswith('Not enough space for compaction (')]
    info = [e for e in ev if 'Compaction space check is disabled' in e['msg']]
    d = {k: c1[k] - c0[k] for k in CTRS}
    outbytes = sum(datadb(table))
    win = SAMPLER.window(t0, t1 + 8) if SAMPLER else []
    peak = max([h[2][table] for h in win] or [0])
    final = du_dir(table)
    TRIG.writerow([label, arm, ' '.join(cmd) if isinstance(cmd, list) else cmd, rc, f'{t1 - t0:.1f}', U1, B, sum(sizes), len(ps), dropped,
                   d['CompactionsReduced'], d['SSTablesDroppedFromCompaction'], d['CompactionsAborted'], len(reducing), len(aborts), len(info),
                   len(files0), len(files1), outbytes, peak, final])
    note(f'OBSERVED {arm}: counters delta {d}; Reducing scope x{len(reducing)}; abort warnings x{len(aborts)}; info lines x{len(info)}; '
         f'Data.db files {len(files0)} -> {len(files1)} ({outbytes} bytes); table du peak {peak} final {final}; sampler window {len(win)} samples')
    ok_band = expect(f'{arm}: the ladder simulated from the lengths and B gives the planned outcome ({planned_n}); else INVALID RUN (band)', dropped == planned_n)
    ok_cnt = expect(f'{arm}: {len(reqs)} pass lines with requested >= {minreq} (the simulated number)', len(ps) == len(reqs))
    expect(f'{arm}: every pass has available within 1 MiB of the expected B ({B})', bool(ps) and all(abs(av - B) <= MIB for _, av, _ in ps))
    expect(f'{arm}: pass requested figures equal the simulated {reqs}', [rq for _, _, rq in ps] == reqs)
    if dropped >= 0:
        expect(f'{arm}: Reducing scope warnings = {dropped}', len(reducing) == dropped)
        expect(f'{arm}: counters Reduced +{1 if dropped else 0}, Dropped +{dropped}, Aborted +0',
               (d['CompactionsReduced'], d['SSTablesDroppedFromCompaction'], d['CompactionsAborted']) == (1 if dropped else 0, dropped, 0))
        expect(f'{arm}: nodetool returned 0', rc == 0)
        expect(f'{arm}: {1 + dropped} Data.db files afterwards (one output plus {dropped} shed inputs)', len(files1) == 1 + dropped)
        kept = sum(sorted(sizes, reverse=True)[dropped:])
        note(f'INFO {arm}: output length {outbytes - sum(sorted(sizes, reverse=True)[:dropped])} against the kept inputs {kept}')
    else:
        expect(f'{arm}: Reducing scope warnings = {len(sizes) - 1} and one abort warning', len(reducing) == len(sizes) - 1 and len(aborts) == 1)
        expect(f'{arm}: counters Reduced +0, Dropped +0, Aborted +1', (d['CompactionsReduced'], d['SSTablesDroppedFromCompaction'], d['CompactionsAborted']) == (0, 0, 1))
        expect(f'{arm}: nodetool returned non-zero (the task threw)', rc != 0)
        expect(f'{arm}: the {len(sizes)} inputs are untouched (same files, same lengths, no output)', files1 == files0 and datadb(table) == sizes)
        note(f'INFO {arm}: nodetool output tail: {out.strip()[-300:]!r}')
    if expect_info:
        expect(f'{arm}: the info line "Compaction space check is disabled" appears', len(info) >= 1)
    else:
        expect(f'{arm}: no "Compaction space check is disabled" line', len(info) == 0)
    if first:
        if not ps:
            fail(f'instrument check: no debug line at the first trigger ({arm})')
        if not (ok_band and ok_cnt) or abs(ps[0][1] - B) > MIB:
            note(f'INSTRUMENT CHECK FAILED at the first trigger ({arm}): band/pass count/available do not hold (9e "Before the cluster tier" 1)')
            fail('instrument check failed at the first trigger')
        note(f'INSTRUMENT first trigger ({arm}): first pass available {ps[0][1]} vs expected B {B} (difference {ps[0][1] - B})')
    return dict(sizes=sizes, B=B, passes=ps, dropped=dropped, d=d, files1=files1, rc=rc)


def wait_table_idle(table, want_files, timeout=180):
    """Wait until the table has `want_files` Data.db files and no task of it shows in sstable_tasks."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if len(table_files(table)) == want_files and table not in (SAMPLER.latest if SAMPLER else {}):
            return True
        time.sleep(1)
    return False


def hatch_arms(pct_eff):
    jmx = ['java', '-cp', D + '/jmx-classes', 'Jmx', 'invoke', 'org.apache.cassandra.db:type=Tables,keyspace=ks1,table=t', 'compactionDiskSpaceCheck', 'false']
    rc, out = sh(jmx, check=False)
    note(f'HATCH invoke compactionDiskSpaceCheck(false) on ks1.t: rc {rc}: {out.strip()[-200:]}')
    if rc != 0:
        fail('the JMX call for the hatch failed')
    # H1: a major compaction is still refused (the hatch tests compactionType == COMPACTION, a major compaction is MAJOR_COMPACTION)
    h1 = ladder_trigger('H1', ['bin/nodetool', 'compact', 'ks1', 't'], 't', pct_eff, -1)
    # H2: a background (COMPACTION) task ignores the budget
    sizes = datadb('t')
    c0 = counters()
    off = os.path.getsize(DEBUG_LOG)
    t0 = time.time()
    rc, out = sh(['bin/nodetool', 'enableautocompaction', 'ks1', 't'], check=False)
    done = wait_table_idle('t', 1, 180)
    t1 = time.time()
    time.sleep(8)
    ev = parse_events(read_since(off))
    c1 = counters()
    ps = passes_of(ev, min(sizes) // 2)
    info = [e for e in ev if 'Compaction space check is disabled' in e['msg']]
    comp = [e for e in ev if e['msg'].startswith('Compacting (') and '/t-' in e['msg']]
    files1 = table_files('t')
    outbytes = sum(datadb('t'))
    d = {k: c1[k] - c0[k] for k in CTRS}
    win = SAMPLER.window(t0, t1 + 8)
    peak = max([h[2]['t'] for h in win] or [0])
    TRIG.writerow([label, 'H2', 'nodetool enableautocompaction ks1 t', rc, f'{t1 - t0:.1f}', df_avail(), '', sum(sizes), len(ps), '', d['CompactionsReduced'],
                   d['SSTablesDroppedFromCompaction'], d['CompactionsAborted'], 0, 0, len(info), len(sizes), len(files1), outbytes, peak, du_dir('t')])
    note(f'OBSERVED H2: rc {rc}; finished {done}; pass lines {[(a, r) for _, a, r in ps]}; info lines x{len(info)}; Compacting lines x{len(comp)}; '
         f'Data.db files {len(sizes)} -> {len(files1)} ({outbytes} bytes against inputs {sum(sizes)}); counters delta {d}')
    expect('H2: the info line "Compaction space check is disabled" appears once for the background task', len(info) == 1)
    expect('H2: no debug pass line from that task (the check is not evaluated)', len(ps) == 0)
    expect('H2: the compaction ran: 1 Data.db file whose length is the inputs\' total within 5 %', done and len(files1) == 1 and abs(outbytes - sum(sizes)) <= 0.05 * sum(sizes))
    expect('H2: counters unchanged (no reduction, no abort)', d == {k: 0 for k in CTRS})
    return h1


def inflight_arm(pct_eff):
    # I1: ks1.t alone at the same pct
    i1 = ladder_trigger('I1', ['bin/nodetool', 'compact', 'ks1', 't'], 't', pct_eff, 0, first=True)
    # I2: ks1.slow in flight at 4 MiB/s, then ks1.t2
    sh('bin/nodetool setcompactionthroughput 4')
    sizes_t2, sizes_slow = datadb('t2'), datadb('slow')
    U_s = df_avail()
    off_slow = os.path.getsize(DEBUG_LOG)
    p_slow = subprocess.Popen(['bin/nodetool', 'compact', 'ks1', 'slow'], cwd=C, stdout=open(D + '/slow-compact.out', 'w'), stderr=subprocess.STDOUT)
    log('+ bin/nodetool compact ks1 slow (background)')
    t_s0 = time.time()
    while time.time() - t_s0 < 60:
        row = SAMPLER.latest.get('slow')
        if row and row[0] > 0:
            break
        time.sleep(0.2)
    else:
        p_slow.kill()
        fail('the slow compaction showed no progress in sstable_tasks within 60 s')
    t_seen = time.time()
    row = SAMPLER.latest.get('slow')
    note(f'I2 slow task seen {t_seen - t_s0:.1f} s after its nodetool started: kind {row[3]!r} progress {row[0]} total {row[1]} total_compressed {row[2]}')
    U2 = df_avail()
    B2 = java_round((U2 - FLOOR) * pct_eff)
    c0 = counters()
    off = os.path.getsize(DEBUG_LOG)
    t0 = time.time()
    p_t2 = subprocess.Popen(['bin/nodetool', 'compact', 'ks1', 't2'], cwd=C, stdout=open(D + '/t2-compact.out', 'w'), stderr=subprocess.STDOUT)
    log('+ bin/nodetool compact ks1 t2 (background)')
    admitted = None
    while time.time() - t0 < 90:
        ev = parse_events(read_since(off))
        admitted = [e for e in ev if e['msg'].startswith('Compacting (') and '/t2-' in e['msg']]
        if admitted:
            break
        time.sleep(0.5)
    sh('bin/nodetool setcompactionthroughput 64')
    try:
        p_t2.wait(timeout=900)
        p_slow.wait(timeout=900)
    except subprocess.TimeoutExpired:
        fail('the compactions of I2 did not finish in 900 s')
    t1 = time.time()
    time.sleep(8)
    ev_slow = parse_events(read_since(off_slow))
    ev = parse_events(read_since(off))
    c1 = counters()
    minreq = min(sizes_t2) // 2
    slow_pass = passes_of([e for e in ev_slow if e['ts'] < min([e2['ts'] for e2 in ev] or [1e18])], minreq)
    ps = passes_of(ev, minreq)
    for i, (ts, av, rq) in enumerate(ps):
        PASSES.writerow([label, 'I2', i, f'{ts:.3f}', av, rq, ''])
    note(f'OBSERVED I2 slow task own pass (available, requested): {[(a, r) for _, a, r in slow_pass]} (R0 = sum of ks1.slow Data.db {sum(sizes_slow)})')
    note(f'OBSERVED I2 t2 passes (available, requested): {[(a, r) for _, a, r in ps]}')
    d = {k: c1[k] - c0[k] for k in CTRS}
    reducing = [e for e in ev if e['level'] == 'WARN' and e['msg'].endswith('Reducing scope.')]
    n_obs = d['SSTablesDroppedFromCompaction']
    files_t2 = table_files('t2')
    note(f'OBSERVED I2: counters delta {d}; Reducing scope x{len(reducing)}; t2 Data.db files {len(files_t2)}; slow files {len(table_files("slow"))}; '
         f't files {len(table_files("t"))}; U at the slow task\'s first progress {U2} (B there {B2}), U before slow {U_s}')
    tot_t2 = sum(sizes_t2)
    TRIG.writerow([label, 'I2', 'nodetool compact ks1 t2 (ks1.slow in flight)', 0 if p_t2.returncode == 0 else p_t2.returncode, f'{t1 - t0:.1f}', U2, B2, tot_t2,
                   len(ps), n_obs, d['CompactionsReduced'], d['SSTablesDroppedFromCompaction'], d['CompactionsAborted'], len(reducing), 0, 0, len(sizes_t2),
                   len(files_t2), sum(datadb('t2')), '', du_dir('t2')])
    expect('I2: the slow task was admitted whole (its own pass: requested = R0 <= available)', bool(slow_pass) and slow_pass[0][2] == sum(sizes_slow) and slow_pass[0][2] <= slow_pass[0][1])
    expect('I2: the t2 compaction printed passes', bool(ps))
    if ps:
        a0, r0_ = ps[0][1], ps[0][2]
        R_dbg = r0_ - tot_t2
        R_smp = SAMPLER.remaining('slow', ps[0][0])
        note(f'I2 first pass: requested {r0_} - total of t2 {tot_t2} = R {R_dbg}; sampler R at the line\'s time {R_smp}; available {a0}')
        expect('I2: first pass requested - 8 s = R, within 16 MiB of the slow task\'s remaining write read from sstable_tasks at that time',
               R_smp is not None and abs(R_dbg - R_smp) <= 16 * MIB)
        expect('I2: all passes have available within 1 MiB of the first', all(abs(av - a0) <= MIB for _, av, _ in ps))
        steps = [ps[i][2] - ps[i + 1][2] for i in range(len(ps) - 1)]
        expect('I2: requested falls by the largest remaining input at each pass', steps == sorted(sizes_t2, reverse=True)[:len(steps)])
        first_ok = [i for i, (_, av, rq) in enumerate(ps) if rq <= av]
        expect('I2: the last pass is the first one with requested <= available (the check agrees with its own operands)',
               bool(first_ok) and first_ok[0] == len(ps) - 1)
        n_pass = len(ps) - 1
        expect(f'I2: the number of inputs shed ({n_obs}) equals passes - 1 ({n_pass})', n_obs == n_pass)
        expect('I2 (design): n = 5 (k = 3 kept)', n_obs == 5)
        expect('I2: the in-flight term moved the boundary: I1 shed 0, I2 shed more than 0', i1['dropped'] == 0 and n_obs > 0)
        expect(f'I2: counters Reduced +1, Dropped +{n_obs}, Aborted +0', (d['CompactionsReduced'], d['SSTablesDroppedFromCompaction'], d['CompactionsAborted']) == (1 if n_obs else 0, n_obs, 0))
        expect(f'I2: Reducing scope warnings = {n_obs}', len(reducing) == n_obs)
        expect(f'I2: t2 holds {1 + n_obs} Data.db files afterwards', len(files_t2) == 1 + n_obs)


def main():
    global DRV, SAMPLER
    DRV = load_driver()
    note(f'LABEL {label}  date {time.strftime("%F %T")}  host {os.uname().nodename}  kernel {os.uname().release}')
    note('JAVA ' + sh('java -version 2>&1 | head -1')[1].strip() + ' | ANT ' + sh('ant -version 2>&1 | head -1')[1].strip())
    note('CLONE ' + sh('git describe --tags && git rev-parse HEAD')[1].replace('\n', ' ').strip())
    if daemon_up():
        fail('a CassandraDaemon is already running')
    sh('git checkout -q conf/cassandra.yaml', check=False)
    sh(f'rm -rf {D}/jmx-classes && mkdir -p {D}/jmx-classes && javac -d {D}/jmx-classes {HARNESS}/Jmx.java')

    # ---- first start: build the inputs
    prepare_fs()
    sh('rm -rf data logs logs-build saved_caches')
    note(sh(f'{HARNESS}/make-node-yaml.sh default')[1].strip())
    start_node('build')
    cl, ses = connect()
    ses.execute("CREATE KEYSPACE ks1 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
    for t in TABLES:
        ses.execute(f"CREATE TABLE ks1.{t} (pk int PRIMARY KEY, v blob) WITH compaction = {{'class': 'SizeTieredCompactionStrategy', 'enabled': 'false'}}")
    execute_concurrent = DRV[3]
    for t in TABLES:
        ps = ses.prepare(f'INSERT INTO ks1.{t} (pk, v) VALUES (?, ?)')
        for i in range(NSST):
            rnd = random.Random(SEED[t] + i)
            args = [(i * 1_000_000 + r, rnd.randbytes(PAYLOAD)) for r in range(ROWS)]
            execute_concurrent(ses, ps, args, concurrency=64, raise_on_first_error=True)
            sh(f'bin/nodetool flush ks1 {t}')
        sizes = datadb(t)
        _, ts = sh(f'bin/nodetool tablestats ks1.{t}')
        m = re.search(r'SSTable count:\s*(\d+)', ts)
        note(f'DATASET ks1.{t}: Data.db lengths {sizes}; tablestats SSTable count {m.group(1) if m else None}; du -sb {du_dir(t)}')
        if len(sizes) != NSST or max(sizes) > 1.10 * min(sizes) or any(abs(x - 64 * MIB) > 0.10 * 64 * MIB for x in sizes):
            fail(f'dataset check failed for ks1.{t}: need {NSST} Data.db files, largest <= 1.10 x smallest, each within 10 % of 64 MiB')
    cl.shutdown()
    sh('bin/nodetool drain', timeout=300, check=False)
    stop_node()
    time.sleep(3)

    # ---- plan (node stopped)
    U_plan = df_avail()
    tot = {t: sum(datadb(t)) for t in TABLES}
    s_mean = tot['t'] / NSST
    if label == 'd95':
        pct_str, pct_eff = 'default', 0.95
    else:
        if label == 'inflight':
            pct = (tot['slow'] + INFLIGHT_MARGIN * s_mean) / (U_plan - FLOOR)
        else:
            pct = FACTOR[label] * tot['t'] / (U_plan - FLOOR)
        if not 0 < pct < 1:
            fail(f'pct {pct} is outside (0, 1)')
        pct_str = f'{pct:.12f}'
        pct_eff = float(pct_str)
    note(f'PLAN U {U_plan} (node stopped); totals {tot}; s = {s_mean:.0f}; pct {pct_str}; planned B {java_round((U_plan - FLOOR) * pct_eff)} '
         f'= {java_round((U_plan - FLOOR) * pct_eff) / tot["t"]:.4f} x total of ks1.t' + (f' = R0 + {INFLIGHT_MARGIN} s' if label == 'inflight' else ''))

    # ---- second start: the knob
    sh('mv logs logs-build', check=False)
    sh('rm -rf saved_caches')
    note(sh(f'{HARNESS}/make-node-yaml.sh {pct_str}')[1].strip())
    start_node('run')
    sh('bin/nodetool setlogginglevel org.apache.cassandra.db.Directories DEBUG')
    note('LOGGING ' + ' | '.join(l for l in sh('bin/nodetool getlogginglevels')[1].splitlines() if 'Directories' in l or l.strip().startswith('org.apache.cassandra ')))
    note('COUNTERS at start ' + json.dumps(counters()))
    cl, ses = connect()
    SAMPLER = Sampler(ses, TABLES, D + '/samples.csv')
    SAMPLER.start()
    time.sleep(20)                                       # settle: start-up flushes of the system tables
    off = os.path.getsize(DEBUG_LOG)
    t0 = time.time()
    time.sleep(30)                                       # idle control
    ev = parse_events(read_since(off))
    idle = passes_of(ev, min(datadb('t')) // 2)
    idle_win = SAMPLER.window(t0, time.time())
    note(f'IDLE 30 s: {len(idle_win)} samples; df {idle_win[0][1] if idle_win else None} -> {idle_win[-1][1] if idle_win else None}; du t {idle_win[0][2]["t"] if idle_win else None} -> '
         f'{idle_win[-1][2]["t"] if idle_win else None}; pass lines of a table-size compaction {len(idle)}')
    expect('IDLE: no compaction pass line of a table-size compaction in 30 s, df and du unchanged',
           not idle and bool(idle_win) and idle_win[0][1] == idle_win[-1][1] and idle_win[0][2] == idle_win[-1][2])

    if label == 'inflight':
        inflight_arm(pct_eff)
    else:
        r = ladder_trigger(ARM[label], ['bin/nodetool', 'compact', 'ks1', 't'], 't', pct_eff, PLAN_N[label], first=True)
        if label == 'f01':
            hatch_arms(pct_eff)
    SAMPLER.stop()
    time.sleep(1)
    note('DONE')


try:
    main()
except SystemExit:
    raise
except Exception as e:
    import traceback
    note(f'FAIL (exception): {e!r}')
    SESSION.write(traceback.format_exc()); SESSION.flush()
    if SAMPLER:
        SAMPLER.stop()
    stop_node()
    sys.exit(1)
finally:
    stop_node()
    for src, dst in ((DEBUG_LOG, 'debug.log'), (SYSTEM_LOG, 'system.log')):
        subprocess.run(f'cp {src} {D}/{dst} 2>/dev/null', shell=True)
    subprocess.run(f'cp -r {C}/logs-build {D}/logs-build 2>/dev/null', shell=True)
