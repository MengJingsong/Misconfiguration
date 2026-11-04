#!/usr/bin/env python3
"""Stage 4, cluster tier, concurrent_compactors-submitBackground-getMaximumPoolSize (case 9b-9e).   (run on the measured node; sudo for the loop mount)

  cluster-run.py prepare            once: 40 GiB loop-mounted ext4, one node, 8 tables x 4 SSTables x 256 MiB (compression off, compaction off),
                                    then the data directory is saved as a backup on the same filesystem
  cluster-run.py run <label>        restore the backup, start the node, set the knob, enable autocompaction on all 8 tables at once, sample
                                    until no compaction is active; labels: idle n1 n2a n2b n2c n4 n8 ctl8
  idle   no compaction, 60 s (baseline of disk and heap)           n1 n2a n4 n8   concurrent_compactors = 1, 2, 4, 8 (n2a/n2b/n2c = the default, three repeats = the noise band)
  ctl8   n = 8 with max_space_usable_for_compactions_in_percentage set so the byte budget fits two 1 GiB compactions (case 9e step 4)

The node is ~/cassandra-run4 at cassandra-5.0.9; logs: ~/stage4-logs/cc/<label>/ (session.log, summary.txt, samples.csv, ...). Exit 1 on a failed check;
the node is stopped on any exit. Python 3.9+."""
import csv, glob, json, os, random, re, shutil, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-run4')
HARNESS = os.path.dirname(os.path.abspath(__file__))
IMG = HOME + '/stage4-cc.img'
MNT = '/mnt/stage4-cc'
DATA = MNT + '/data'
BACKUP = MNT + '/backup'
MIB = 1048576
GIB = 1024 * MIB
TABLES = [f'c{i}' for i in range(8)]
SST_PER_TABLE, SST_MIB, ROW_KIB = 4, 256, 64
ROWS_PER_SST = SST_MIB * 1024 // ROW_KIB            # 4096
FLOOR = 50 * MIB                                     # min_free_space_per_drive default
KNOB = {'n1': 1, 'n2a': 2, 'n2b': 2, 'n2c': 2, 'n4': 4, 'n8': 8, 'ctl8': 8, 'ctl8r': 8, 'ctl8a': 8, 'idle': 2}
BUDGET_GIB = 2.25                                    # control: budget fits two 1 GiB compactions but not a third nor a reduced 2-SSTable one
CAP_S = 25 * 60

mode = sys.argv[1] if len(sys.argv) > 1 else ''
if mode == 'prepare' and len(sys.argv) == 2:
    label = 'prepare'
elif mode == 'run' and len(sys.argv) == 3 and sys.argv[2] in KNOB:
    label = sys.argv[2]
else:
    sys.exit(__doc__)

D = f'{HOME}/stage4-logs/cc/{label}'
if os.path.exists(D):
    os.rename(D, D + '.' + time.strftime('%Y%m%d-%H%M%S', time.localtime(os.path.getmtime(D))))
os.makedirs(D)
SESSION = open(D + '/session.log', 'a')
SUMMARY = open(D + '/summary.txt', 'w')
SAMPLER = None


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, file=sys.stderr)
    SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush(); log(s)


def sh(cmd, timeout=900, check=True, env=None, cwd=C, quiet=False):
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
        for _ in range(120):
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


def df_avail():
    st = os.statvfs(MNT)
    return st.f_bavail * st.f_frsize


def dir_bytes(path):
    total = 0
    for root, _d, files in os.walk(path):
        for fn in files:
            try:
                total += os.lstat(os.path.join(root, fn)).st_size
            except FileNotFoundError:
                pass
    return total


def ks_dir_bytes():
    return sum(dir_bytes(d) for d in glob.glob(f'{DATA}/ks1/*'))


def datadb(table):
    out = []
    for f in sorted(glob.glob(f'{DATA}/ks1/{table}-*/*-Data.db')):
        try:
            out.append(os.path.getsize(f))
        except FileNotFoundError:
            pass
    return out


# ---- driver and JMX
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


DRV = load_driver()


def connect():
    Cluster, EP, DEFAULT, _, CL = DRV
    for attempt in range(30):                      # the native port can lag the nodetool 'running' answer
        cl = Cluster(['127.0.0.1'], protocol_version=5, execution_profiles={DEFAULT: EP(request_timeout=180, consistency_level=CL.ONE)})
        try:
            return cl, cl.connect()
        except Exception as e:
            log(f'connect attempt {attempt} failed: {e!r}'[:200])
            cl.shutdown(); time.sleep(4)
    raise RuntimeError('could not connect to 127.0.0.1:9042')


def compile_jmx():
    os.makedirs(D + '/jmx-classes', exist_ok=True)
    sh(f'javac -d {D}/jmx-classes {HARNESS}/Jmx.java')


def jmx_get(*pairs):
    args = [x for p in pairs for x in p]
    _, out = sh(['java', '-cp', D + '/jmx-classes', 'Jmx', 'get', *args], check=False, quiet=True)
    vals = {}
    for l in out.splitlines():
        parts = l.split('|')
        if len(parts) == 3:
            vals[(parts[0], parts[1])] = parts[2]
    return vals


TP = 'org.apache.cassandra.metrics:type=ThreadPools,path=internal,scope=CompactionExecutor,name='
CM = 'org.apache.cassandra.metrics:type=Compaction,name='
CTRS = ['CompactionsReduced', 'SSTablesDroppedFromCompaction', 'CompactionsAborted']


def counters():
    v = jmx_get(*[(CM + n, 'Count') for n in CTRS])
    return {n: int(float(v.get((CM + n, 'Count'), 'nan'))) if (CM + n, 'Count') in v else -1 for n in CTRS}


# ---- filesystem and node
def prepare_fs():
    sh(f'if mountpoint -q {MNT}; then sudo umount {MNT}; fi', check=False)
    sh(f'rm -f {IMG} && truncate -s 40G {IMG} && mkfs.ext4 -q -F {IMG}')
    sh(f'sudo mkdir -p {MNT} && sudo mount -o loop {IMG} {MNT} && sudo mkdir -p {DATA} {BACKUP} && sudo chown {os.getuid()}:{os.getgid()} {DATA} {BACKUP}')
    note('FILESYSTEM ' + sh(f'df -B1 {MNT} | tail -1')[1].strip())


def make_yaml(n, pct=None):
    sh('git checkout -q conf/cassandra.yaml', quiet=True)
    extra = [f'data_file_directories:', f'    - {DATA}', f'concurrent_compactors: {n}', 'autocompaction_on_startup_enabled: false']   # the disable done at load time is not persistent
    if pct is not None:
        extra.append(f'max_space_usable_for_compactions_in_percentage: {pct}')
    with open(C + '/conf/cassandra.yaml', 'a') as f:
        f.write('\n' + '\n'.join(extra) + '\n')
    note('YAML tail: ' + ' | '.join(extra))


def clean_node_state():
    for d in ('commitlog', 'saved_caches', 'hints', 'cdc_raw'):
        shutil.rmtree(f'{C}/data/{d}', ignore_errors=True)


def start_node(tag):
    if daemon_up():
        fail('a CassandraDaemon is already running')
    env = dict(os.environ, MAX_HEAP_SIZE='8G', HEAP_NEWSIZE='800M')
    sh(f'bin/cassandra -p {D}/cassandra.pid > {D}/startup-{tag}.log 2>&1', env=env)
    for _ in range(180):
        _, st = sh('bin/nodetool statusbinary', check=False, quiet=True)
        _, ns = sh('bin/nodetool status', check=False, quiet=True)
        if 'running' in st and re.search(r'^UN', ns, re.M):
            break
        time.sleep(2)
    else:
        fail(f'node ({tag}) did not come up')
    note(f'node up ({tag}); pid {open(D + "/cassandra.pid").read().strip()}')


def pid():
    return int(open(D + '/cassandra.pid').read().strip())


def heap_used():
    r, out = sh(f'jcmd {pid()} GC.heap_info', check=False, quiet=True, timeout=60)
    m = re.search(r'garbage-first heap\s+total\s+(\d+)K, used\s+(\d+)K', out)
    return int(m.group(2)) * 1024 if m else None


# ---- sampler
class Sampler(threading.Thread):
    def __init__(self, session, path):
        super().__init__(daemon=True)
        self.session = session
        self.stop_ev = threading.Event()
        self.f = open(path, 'w'); self.w = csv.writer(self.f)
        self.w.writerow(['epoch', 'ks1_bytes', 'avail', 'tasks_running', 'tasks_json'])
        self.base = None
        self.rows = []
        self.q = 'SELECT keyspace_name, table_name, kind, progress, total, total_compressed FROM system_views.sstable_tasks'

    def run(self):
        nxt = time.time()
        while not self.stop_ev.is_set():
            t = time.time()
            try:
                rows = [r for r in self.session.execute(self.q) if r.keyspace_name == 'ks1']
            except Exception as e:
                rows = []
                log(f'sampler query failed: {e!r}')
            tasks = {r.table_name: (r.kind, r.progress, r.total) for r in rows}
            running = sum(1 for v in tasks.values() if v[0] == 'compaction')
            b = ks_dir_bytes()
            self.w.writerow([f'{t:.3f}', b, df_avail(), running, json.dumps(tasks)]); self.f.flush()
            self.rows.append((t, b, running))
            nxt += 2.0
            time.sleep(max(0.0, nxt - time.time()))

    def stop(self):
        self.stop_ev.set()


# ---- prepare
def do_prepare():
    prepare_fs()
    stop_node()
    clean_node_state()
    make_yaml(2)
    start_node('prepare')
    compile_jmx()
    cl, session = connect()
    session.execute("CREATE KEYSPACE IF NOT EXISTS ks1 WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    for t in TABLES:
        session.execute(f"CREATE TABLE IF NOT EXISTS ks1.{t} (k int PRIMARY KEY, v blob) WITH compression = {{'enabled': 'false'}} "
                        f"AND compaction = {{'class':'SizeTieredCompactionStrategy','min_threshold':4,'max_threshold':4}}")
    sh('bin/nodetool disableautocompaction ks1')
    _, _, _, execute_concurrent_with_args, _ = DRV
    pool = random.Random(7).randbytes(8 * MIB)
    ins = session.prepare('INSERT INTO ks1.%s (k, v) VALUES (?, ?)' % '{t}') if False else None
    t0 = time.time()
    for t in TABLES:
        ins = session.prepare(f'INSERT INTO ks1.{t} (k, v) VALUES (?, ?)')
        for s in range(SST_PER_TABLE):
            args = []
            for i in range(ROWS_PER_SST):
                off = ((s * ROWS_PER_SST + i) * 4099) % (len(pool) - ROW_KIB * 1024)
                args.append((s * ROWS_PER_SST + i, pool[off:off + ROW_KIB * 1024]))
            res = execute_concurrent_with_args(session, ins, args, concurrency=32, raise_on_first_error=True)
            sh(f'bin/nodetool flush ks1 {t}', quiet=True)
            log(f'loaded {t} sstable {s} ({time.time() - t0:.0f} s)')
    cl.shutdown()
    sizes = {t: datadb(t) for t in TABLES}
    for t in TABLES:
        note(f'DATA {t}: Data.db lengths {sizes[t]} (sum {sum(sizes[t])})')
    expect('every table has 4 Data.db files of 256-262 MiB', all(len(v) == 4 and all(256 * MIB <= x <= 262 * MIB for x in v) for v in sizes.values()))
    note(f'ks1 bytes {ks_dir_bytes()}; avail {df_avail()}')
    sh('bin/nodetool drain', check=False)
    stop_node()
    sh(f'rm -rf {BACKUP}/* && cp -a {DATA}/. {BACKUP}/', timeout=1800)
    note('backup bytes ' + str(dir_bytes(BACKUP)) + '; avail ' + str(df_avail()))
    note('prepare done')


# ---- run
def do_run():
    global SAMPLER
    n = KNOB[label]
    if not os.path.ismount(MNT) or not os.path.isdir(BACKUP):
        fail('run `prepare` first')
    stop_node()
    clean_node_state()
    sh(f'rm -rf {DATA}/* && cp -a {BACKUP}/. {DATA}/', timeout=1800)
    sizes = {t: datadb(t) for t in TABLES}
    in_bytes = sum(sum(v) for v in sizes.values())
    per_table = in_bytes // len(TABLES)
    note(f'INPUT per-table Data.db bytes {[sum(v) for v in sizes.values()]}; total {in_bytes}; avail before start {df_avail()}')
    pct = None
    if label in ('ctl8', 'ctl8r', 'ctl8a'):
        U = df_avail() - 30 * MIB                       # the node's own start-up writes
        # ctl8: the filed control, B = 2.25 GiB (fits two compactions). ctl8r / ctl8a: the amended control (9f R6): the budget is checked per task,
        # all eight tasks check in the same millisecond, so B must be below ONE compaction: ctl8r B = 0.8 x one compaction (3 of 4 inputs fit,
        # the task is reduced), ctl8a B = 0.45 x one compaction (fewer than 2 inputs fit, the task aborts).
        B_target = {'ctl8': BUDGET_GIB * GIB, 'ctl8r': 0.8 * per_table, 'ctl8a': 0.45 * per_table}[label]
        pct = round(B_target / (U - FLOOR), 5)
        note(f'CONTROL target B {round(B_target)}: U {U}; pct {pct}; B = (U - 50 MiB) x pct = {round((U - FLOOR) * pct)}; one compaction = {per_table} bytes; one input = {per_table // 4}')
    make_yaml(n, pct)
    start_node('run')
    compile_jmx()
    sh('bin/nodetool setcompactionthroughput 16')
    _, thr = sh('bin/nodetool getcompactionthroughput', quiet=True)
    _, cc = sh('bin/nodetool getconcurrentcompactors', quiet=True)
    note('READBACK ' + thr.strip().replace('\n', ' ') + ' | ' + cc.strip().replace('\n', ' '))
    expect(f'getconcurrentcompactors = {n}', str(n) in cc)
    v = jmx_get((TP + 'MaxPoolSize', 'Value'))
    note(f'READBACK CompactionExecutor MaxPoolSize {v}')
    expect(f'CompactionExecutor MaxPoolSize = {n}', any(float(x) == n for x in v.values()))
    cl, session = connect()
    c0 = counters()
    note(f'COUNTERS before {c0}')
    h0 = heap_used()
    SAMPLER = Sampler(session, D + '/samples.csv')
    SAMPLER.start()
    heaps = []
    time.sleep(10)
    base = ks_dir_bytes()
    note(f'BASELINE ks1 bytes {base}; heap used {h0}')
    if label == 'idle':
        for _ in range(5):
            time.sleep(10); heaps.append(heap_used())
        peak = max(r[1] for r in SAMPLER.rows)
        SAMPLER.stop()
        note(f'IDLE peak ks1 bytes {peak}; max running {max(r[2] for r in SAMPLER.rows)}; heap used samples {heaps}')
        cl.shutdown(); stop_node(); return
    dl_off = os.path.getsize(C + '/logs/debug.log')   # budget-check lines of THIS run only (the log accumulates across runs)
    t_enable = time.time()
    sh('bin/nodetool enableautocompaction ks1')
    note(f'ENABLED at epoch {t_enable:.3f}')
    seen = False
    idle_since = None
    last_heap = 0
    while time.time() - t_enable < CAP_S:
        time.sleep(2)
        if time.time() - last_heap > 10:
            heaps.append((round(time.time(), 1), heap_used())); last_heap = time.time()
        running = SAMPLER.rows[-1][2] if SAMPLER.rows else 0
        if running > 0:
            seen = True; idle_since = None
        elif seen:
            idle_since = idle_since or time.time()
            single = all(len(datadb(t)) == 1 for t in TABLES)
            if single or time.time() - idle_since > 40:
                break
    else:
        note('TIMEOUT: compactions still running at the cap')
    time.sleep(6)
    c1 = counters()
    # the JMX active-task gauge at the end and the pool size
    SAMPLER.stop(); time.sleep(2.5)
    rows = [r for r in SAMPLER.rows if r[0] >= t_enable]
    peak_extra = max(r[1] for r in rows) - base
    peak_tasks = max(r[2] for r in rows)
    t_peak_tasks = next(r[0] for r in rows if r[2] == peak_tasks) - t_enable
    t_end = max((r[0] for r in rows if r[2] > 0), default=t_enable) - t_enable
    left = {t: len(datadb(t)) for t in TABLES}
    final = ks_dir_bytes()
    note(f'RESULT label {label} n {n} peak_running_tasks {peak_tasks} (first at +{t_peak_tasks:.0f} s) peak_extra_bytes {peak_extra} '
         f'peak_extra/per_table {peak_extra / per_table:.2f} compactions_active_until +{t_end:.0f} s base {base} final_ks1 {final} per_table_input {per_table}')
    note(f'RESULT sstables per table at end {left}; counters after {c1} (delta { {k: c1[k] - c0[k] for k in c0} }); heap samples {heaps}')
    # the debug.log lines of the budget check, for the control and as a record
    with open(C + '/logs/debug.log', 'rb') as f:
        f.seek(dl_off); dl = f.read().decode('utf-8', 'replace')
    chk = re.findall(r'FileStore (.*?) has (\d+) bytes available, checking if we can write (\d+) bytes', dl)
    note(f'BUDGET-CHECK lines in debug.log since the enable: {len(chk)}; (available, requested) of the first 24: {[(c[1], c[2]) for c in chk[:24]]}')
    for pat in ('Not enough space', 'insufficient', 'aborting compaction', 'Reducing', 'reduc'):
        mm = [l for l in dl.splitlines() if pat.lower() in l.lower()][:4]
        if mm:
            note(f'LOG[{pat}] ' + ' || '.join(m[:220] for m in mm))
    shutil.copy(C + '/logs/system.log', D + '/system.log'); shutil.copy(C + '/logs/debug.log', D + '/debug.log')
    expect('every compaction ended (no task running at the end)', rows[-1][2] == 0)
    cl.shutdown()
    stop_node()
    note('run done')


try:
    if mode == 'prepare':
        do_prepare()
    else:
        do_run()
except SystemExit:
    raise
except Exception as e:
    import traceback
    note('FAIL: exception ' + repr(e) + '\n' + traceback.format_exc())
    if SAMPLER:
        SAMPLER.stop()
    stop_node()
    sys.exit(1)
