#!/usr/bin/env python3
"""Stage 4, cluster tier, DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace (case 9b-9e, amended 2026-10-15).
usage: cluster-run.py <run> <label>      (on the measured node; needs sudo for the loop mount)

  arm B (ByteOrderedPartitioner: disk boundaries null, the guard runs), arm A (Murmur3Partitioner: the default path)
  b_p256 b_p16 b_m16 b_m256 / a_p256 a_p16 a_m16 a_m256   U = T + 50 MiB + d, m = 50 MiB, d = +256 +16 -16 -256 MiB
  b_mm050 b_mm240 b_mm272 b_mm512                          U = T + 256 MiB, m = 50 240 272 512 MiB
  b_sib                                                    U = T + 50 MiB - 256 MiB, m = 50 MiB, the sibling check left ON

One node ($CASSANDRA_HOME, default ~/cassandra-run3, CASSANDRA_CONF ~/stage4-dds/conf), one start per label, a fresh 4 GiB loop-mounted ext4 at
/mnt/stage4-dds per label. The node runs with the Byteman observation rules of guard-trace.btm. Steps: build 8 SSTables of
12,800 rows x 5 KiB (one flush each), dataset check, T = sum of the Data.db lengths, ballast to U, JMX compactionDiskSpaceCheck(false)
(not b_sib), 30 s idle control, trigger = nodetool enableautocompaction ks1 t (a background COMPACTION task of all 8 inputs),
wait for the task to end, disableautocompaction, outcome checks. Writes summary.txt (EXPECTED lines), samples.csv, session.log,
dds.trace and the node's logs to ~/stage4-logs/dds/<run>/<label>/. Exit 1: a set-up or instrument check failed. The node is
stopped and the filesystem unmounted on any exit. Python 3.9+ (random.randbytes)."""
import csv, glob, os, random, re, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-run3')
HARNESS = os.path.dirname(os.path.abspath(__file__))
N = HOME + '/stage4-dds'
IMG = HOME + '/stage4-dds.img'
MNT = '/mnt/stage4-dds'
DATA = MNT + '/data'
BALLAST = MNT + '/ballast'
BM = C + '/build/lib/jars/byteman-4.0.20.jar'
MIB = 1048576
NSST, ROWS, PAYLOAD = 8, 12800, 5120
TBEAN = 'org.apache.cassandra.db:type=Tables,keyspace=ks1,table=t'

# label -> (arm, m in MiB, base: 'd' (U = T + 50 MiB + off) or 'mm' (U = T + 256 MiB), offset MiB, sibling check on)
LABELS = {}
for arm in 'ba':
    for name, off in (('p256', 256), ('p16', 16), ('m16', -16), ('m256', -256)):
        LABELS[f'{arm}_{name}'] = (arm.upper(), 50, 'd', off, False)
for m in (50, 240, 272, 512):
    LABELS[f'b_mm{m:03d}'] = ('B', m, 'mm', 256, False)
LABELS['b_sib'] = ('B', 50, 'd', -256, True)

if len(sys.argv) != 3 or sys.argv[2] not in LABELS:
    sys.exit(__doc__)
RUN, label = sys.argv[1], sys.argv[2]
ARM, M_MIB, BASE, OFF, SIB = LABELS[label]
M = M_MIB * MIB

D = f'{HOME}/stage4-logs/dds/{RUN}/{label}'
if os.path.exists(D):
    os.rename(D, D + '.' + time.strftime('%Y%m%d-%H%M%S', time.localtime(os.path.getmtime(D))))
os.makedirs(D)
SESSION = open(D + '/session.log', 'a')
SUMMARY = open(D + '/summary.txt', 'w')
TRACE = D + '/dds.trace'
SYSTEM_LOG = N + '/logs/system.log'
DEBUG_LOG = N + '/logs/debug.log'
SAMPLER = None
NODE_ENV = None


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, file=sys.stderr)
    SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush(); log(s)


def sh(cmd, timeout=600, check=True, env=None, cwd=C, quiet=False):
    if not quiet:
        log('+ ' + (cmd if isinstance(cmd, str) else ' '.join(cmd)))
    r = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True, timeout=timeout, env=env or NODE_ENV, cwd=cwd)
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
        sh('bin/nodetool stopdaemon', check=False, quiet=True, timeout=120)
        for _ in range(90):
            if not daemon_up():
                break
            time.sleep(1)
        if daemon_up():
            log('stopdaemon did not stop the node: kill -9')
            subprocess.run("pkill -9 -f '[o]rg.apache.cassandra.service.CassandraDaemon'", shell=True)
            time.sleep(2)
    if daemon_up():
        log('WARNING: a CassandraDaemon is still running')


def unmount():
    subprocess.run(f'sync; if mountpoint -q {MNT}; then sudo umount {MNT}; fi', shell=True)


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


def table_dirs():
    return glob.glob(f'{DATA}/ks1/t-*')


def table_files():
    out = {}
    for d in table_dirs():
        for root, _dirs, files in os.walk(d):
            for fn in files:
                p = os.path.join(root, fn)
                try:
                    out[os.path.relpath(p, d)] = os.lstat(p).st_size
                except FileNotFoundError:
                    pass
    return out


def datadb():
    return {k: v for k, v in table_files().items() if k.endswith('-Data.db') and '/' not in k}


def du_table():
    return sum(table_files().values())


def read_since(path, off):
    try:
        with open(path, 'rb') as f:
            f.seek(off)
            return f.read().decode('utf-8', 'replace')
    except FileNotFoundError:
        return ''


def size_of(path):
    try:
        return os.path.getsize(path)
    except FileNotFoundError:
        return 0


# ---- driver (the bundled Python driver, protocol 5)
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


# ---- sampler: every 500 ms df Available, du of the table directory, the Data.db count, the ballast's size
class Sampler(threading.Thread):
    def __init__(self, path):
        super().__init__(daemon=True)
        self.stop_ev = threading.Event()
        self.f = open(path, 'w')
        self.w = csv.writer(self.f)
        self.w.writerow(['epoch', 'avail', 'du_table', 'datadb_files', 'ballast'])
        self.hist = []
        self.lock = threading.Lock()

    def run(self):
        nxt = time.time()
        while not self.stop_ev.is_set():
            t = time.time()
            try:
                files = table_files()
                row = (t, df_avail(), sum(files.values()), sum(1 for k in files if k.endswith('-Data.db') and '/' not in k), size_of(BALLAST))
            except Exception as e:
                log(f'sampler failed: {e!r}')
                row = None
            if row:
                self.w.writerow([f'{row[0]:.3f}'] + list(row[1:]))
                self.f.flush()
                with self.lock:
                    self.hist.append(row)
            nxt += 0.5
            time.sleep(max(0.0, nxt - time.time()))

    def stop(self):
        self.stop_ev.set()

    def window(self, t0, t1):
        with self.lock:
            return [h for h in self.hist if t0 <= h[0] <= t1]


# ---- node and filesystem
def prepare_fs():
    unmount()
    rc = subprocess.run(f'mountpoint -q {MNT}', shell=True).returncode
    if rc == 0:
        fail(f'{MNT} is still mounted and could not be unmounted')
    sh(f'rm -f {IMG} && truncate -s 4G {IMG} && mkfs.ext4 -q -F {IMG}')
    sh(f'sudo mkdir -p {MNT} && sudo mount -o loop {IMG} {MNT} && sudo mkdir -p {DATA} && sudo chown {os.getuid()}:{os.getgid()} {DATA} '
       f'&& sudo touch {BALLAST} && sudo chown {os.getuid()}:{os.getgid()} {BALLAST}')
    note('FILESYSTEM ' + sh(f'df -B1 {MNT} | tail -1')[1].strip())


def start_node():
    global NODE_ENV
    if daemon_up():
        fail('a CassandraDaemon is already running')
    _, y = sh(f'{HARNESS}/make-node-yaml.sh {ARM} {M_MIB}MiB')
    note('YAML ' + y.strip().splitlines()[-1][:900])
    _, ts = sh(f'java -classpath {BM}:build/classes/main:"build/lib/jars/*":"lib/*" org.jboss.byteman.check.TestScript {HARNESS}/guard-trace.btm',
               check=False, env=dict(os.environ))
    open(D + '/testscript.txt', 'w').write(ts)
    note('Byteman TestScript: ' + ('no errors' if 'TestScript: no errors' in ts else 'ERRORS (testscript.txt)'))
    if 'TestScript: no errors' not in ts:
        fail('Byteman TestScript reports errors')
    jopts = f'-javaagent:{BM}=script:{HARNESS}/guard-trace.btm -Dstage4.trace={TRACE}'
    env = dict(os.environ, CASSANDRA_CONF=N + '/conf', CASSANDRA_LOG_DIR=N + '/logs', MAX_HEAP_SIZE='4G', JVM_EXTRA_OPTS=jopts)
    env.pop('HEAP_NEWSIZE', None)
    NODE_ENV = dict(os.environ, CASSANDRA_CONF=N + '/conf')
    sh(f'rm -rf {N}/logs {N}/commitlog {N}/hints {N}/saved_caches {N}/cdc_raw && mkdir -p {N}/logs')
    sh(f'bin/cassandra -p {N}/cassandra.pid > {D}/startup.log 2>&1', env=env)
    t0 = time.time()
    while time.time() - t0 < 300:
        if not daemon_up() and time.time() - t0 > 5:
            fail('the node died during start; see startup.log and system.log')
        _, st = sh('bin/nodetool statusbinary', check=False, quiet=True)
        _, ns = sh('bin/nodetool status', check=False, quiet=True)
        if re.search(r'^running\s*$', st, re.M) and re.search(r'^UN', ns, re.M):
            note(f'node up after {time.time() - t0:.0f} s')
            return
        time.sleep(2)
    fail('node did not come up in 300 s')


def jmx(*args, timeout=60):
    return sh(['java', '-cp', D + '/jmx-classes', 'Jmx', *args], check=False, timeout=timeout)


def set_ballast(U_target):
    """Resize the ballast until df Available is within 64 KiB of U_target; returns the final Available."""
    cur = size_of(BALLAST)
    for i in range(12):
        sh('sync', quiet=True)
        avail = df_avail()
        delta = avail - U_target
        if abs(delta) <= 64 * 1024:
            break
        new = cur + delta
        if new < 0:
            fail(f'cannot reach U {U_target}: Available {avail} with an empty ballast')
        if delta > 0:
            sh(f'fallocate -l {new} {BALLAST}', quiet=True)
        else:
            sh(f'truncate -s {new} {BALLAST}', quiet=True)
        cur = new
    sh('sync', quiet=True)
    avail = df_avail()
    note(f'BALLAST {size_of(BALLAST)} B; df Available {avail}; target U {U_target}; difference {avail - U_target}')
    return avail


def compaction_lines(text):
    return [l for l in text.splitlines() if re.search(r'Compact(ing|ed) \(', l) and '/ks1/t-' in l]


def main():
    global SAMPLER
    note(f'RUN {RUN} LABEL {label}: arm {ARM}, m {M_MIB} MiB, U = T + {"50 MiB + " if BASE == "d" else ""}{OFF} MiB, sibling check {"ON" if SIB else "off"}; '
         f'date {time.strftime("%F %T %Z")}; host {os.uname().nodename}; kernel {os.uname().release}')
    note('JAVA ' + sh('java -version 2>&1 | head -1', env=dict(os.environ))[1].strip() + ' | CLONE ' +
         sh('git describe --tags && git rev-parse --short HEAD', env=dict(os.environ))[1].replace('\n', ' ').strip())
    note('HARNESS md5 ' + sh(f'cd {HARNESS} && md5sum *.btm *.py *.sh *.java | md5sum', env=dict(os.environ))[1].split()[0])
    if daemon_up():
        fail('a CassandraDaemon is already running')
    sh(f'rm -rf {D}/jmx-classes && mkdir -p {D}/jmx-classes && javac -d {D}/jmx-classes {HARNESS}/Jmx.java', env=dict(os.environ))
    prepare_fs()
    start_node()
    _, dc = sh('bin/nodetool describecluster')
    part = re.search(r'Partitioner:\s*(\S+)', dc)
    note(f'PARTITIONER {part.group(1) if part else None}')
    want = 'ByteOrderedPartitioner' if ARM == 'B' else 'Murmur3Partitioner'
    if not part or not part.group(1).endswith(want):
        fail(f'partitioner is not {want}')

    Cluster, EP, DEFAULT, execute_concurrent, CL = load_driver()
    cl = Cluster(['127.0.0.1'], protocol_version=5, token_metadata_enabled=False,
                 execution_profiles={DEFAULT: EP(request_timeout=120, consistency_level=CL.ONE)})
    ses = cl.connect()
    ses.execute("CREATE KEYSPACE ks1 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
    ses.execute("CREATE TABLE ks1.t (pk int PRIMARY KEY, v blob) WITH compaction = {'class': 'SizeTieredCompactionStrategy', 'enabled': 'false'} "
                "AND compression = {'enabled': false}")
    ins = ses.prepare('INSERT INTO ks1.t (pk, v) VALUES (?, ?)')
    t_b = time.time()
    for i in range(NSST):
        rnd = random.Random(1000 + i)
        args = [(i * 1_000_000 + r, rnd.randbytes(PAYLOAD)) for r in range(ROWS)]
        execute_concurrent(ses, ins, args, concurrency=64, raise_on_first_error=True)
        sh('bin/nodetool flush ks1 t')
    cl.shutdown()
    sizes = datadb()
    _, ts = sh('bin/nodetool tablestats ks1.t')
    mm = re.search(r'SSTable count:\s*(\d+)', ts)
    T = sum(sizes.values())
    note(f'DATASET built in {time.time() - t_b:.0f} s: Data.db lengths {sorted(sizes.values())}; T {T}; tablestats SSTable count {mm.group(1) if mm else None}; '
         f'du of the table {du_table()}')
    if len(sizes) != NSST or any(abs(x - 64 * MIB) > 0.10 * 64 * MIB for x in sizes.values()):
        fail(f'dataset check failed: need {NSST} Data.db files, each within 10 % of 64 MiB (9c)')

    U_target = T + (50 * MIB if BASE == 'd' else 0) + OFF * MIB
    note(f'PLAN T {T}; U target {U_target} (U - T = {(U_target - T) / MIB:.1f} MiB); m {M}; guard planned: '
         f'{"refuse" if U_target - M < T else "admit"} (U - m - T = {(U_target - M - T) / MIB:.1f} MiB)')
    set_ballast(U_target)
    if not SIB:
        _, o = jmx('invoke', TBEAN, 'compactionDiskSpaceCheck', 'false')
        note(f'SWITCH compactionDiskSpaceCheck(false): {o.strip()[-160:]}')
    _, o = jmx('get', TBEAN, 'CompactionDiskSpaceCheckEnabled')
    en = re.search(r'CompactionDiskSpaceCheckEnabled\|(\w+)', o)
    note(f'SWITCH read back: CompactionDiskSpaceCheckEnabled = {en.group(1) if en else None}')
    if not en or en.group(1) != ('true' if SIB else 'false'):
        fail('the sibling switch did not take')

    SAMPLER = Sampler(D + '/samples.csv')
    SAMPLER.start()
    time.sleep(2)
    t0 = time.time()
    time.sleep(30)
    idle = SAMPLER.window(t0, time.time())
    note(f'IDLE 30 s: {len(idle)} samples; df {idle[0][1]} -> {idle[-1][1]}; du of the table {idle[0][2]} -> {idle[-1][2]}')
    expect('IDLE: du of the table unchanged and df within 1 MiB over 30 s', bool(idle) and idle[0][2] == idle[-1][2] and abs(idle[0][1] - idle[-1][1]) <= MIB)

    # ---- the trigger
    sh('sync', quiet=True)
    U1 = df_avail()
    if abs(U1 - U_target) > 16 * MIB:
        fail(f'df Available {U1} is more than 16 MiB from U {U_target}: drift (9a Invalid run row)')
    files0 = table_files()
    d0 = datadb()
    off_tr, off_sys, off_dbg = size_of(TRACE), size_of(SYSTEM_LOG), size_of(DEBUG_LOG)
    note(f'TRIGGER: U {U1} (U - m = {U1 - M}, U - m - T = {U1 - M - T} B); files in the table directory {len(files0)}; du {sum(files0.values())}')
    t_trig = time.time()
    sh('bin/nodetool enableautocompaction ks1 t')
    end_reason = None
    while time.time() - t_trig < 900:
        sys_new = read_since(SYSTEM_LOG, off_sys)
        if re.search(r'Compacted \(.*/ks1/t-', sys_new):
            end_reason = 'Compacted line'
        elif 'Not enough space to write' in sys_new:
            end_reason = 'guard exception'
        elif re.search(r'^ERROR', sys_new, re.M) and time.time() - t_trig > 5:
            end_reason = 'ERROR line'
        if end_reason:
            break
        time.sleep(1)
    else:
        end_reason = 'timeout (900 s)'
    time.sleep(10)                       # asynchronous appenders, deletion of the obsolete inputs, the abort
    t_end = time.time()
    rc_dis, _ = sh('bin/nodetool disableautocompaction ks1 t', check=False, timeout=120)
    time.sleep(2)
    SAMPLER.stop()
    time.sleep(1)
    note(f'TRIGGER ended after {t_end - t_trig - 10:.0f} s by: {end_reason}; disableautocompaction rc {rc_dis}')

    # ---- readings
    tr = [l for l in read_since(TRACE, off_tr).splitlines() if l.strip()]
    sys_new, dbg_new = read_since(SYSTEM_LOG, off_sys), read_since(DEBUG_LOG, off_dbg)
    open(D + '/system-window.log', 'w').write(sys_new)
    open(D + '/trace-window.txt', 'w').write('\n'.join(tr) + '\n')
    guards = []
    for l in tr:
        g = re.match(r'guard est=(\d+) avail=(\d+) refused=(\w+) dir=(\S+)', l)
        if g:
            guards.append((int(g.group(1)), int(g.group(2)), g.group(3) == 'true', g.group(4)))
    switches = [l for l in tr if l.startswith('switch ') and 'table=ks1.t ' in l]
    writeable_window = [l for l in tr if l.startswith('writeable ')]
    all_trace = [l for l in read_since(TRACE, 0).splitlines()]
    writeable_t = [l for l in all_trace if l.startswith('writeable ') and 'table=ks1.t ' in l]
    writeable_any = [l for l in all_trace if l.startswith('writeable ')]
    guard_msgs = re.findall(r'Not enough space to write (\S+) to (\S+) \((\S+) available\)', sys_new)
    sib_reduce = [l for l in sys_new.splitlines() if 'Reducing scope' in l]
    sib_abort = [l for l in sys_new.splitlines() if 'Not enough space for compaction (' in l]
    errors = [l for l in sys_new.splitlines() if l.startswith('ERROR')]
    fswrite = [l for l in sys_new.splitlines() if 'FSWriteError' in l or 'No space left on device' in l]
    stopping = [l for l in sys_new.splitlines() if 'Stopping transports as disk_failure_policy' in l]
    comp = compaction_lines(sys_new)
    compacting = [l for l in comp if 'Compacting (' in l]
    compacted = [l for l in comp if 'Compacted (' in l]
    n_inputs = [len(re.findall(r'/ks1/t-[^/]*/[^,\]\s]*-Data\.db', l)) for l in compacting]
    hatch_info = [l for l in sys_new.splitlines() if 'Compaction space check is disabled' in l]
    boundary_dbg = [l for l in read_since(DEBUG_LOG, 0).splitlines() if 'disk boundary cache for ks1.t' in l]
    files1 = table_files()
    d1 = datadb()
    win = SAMPLER.window(t_trig - 1, t_end)
    peak_du = max([h[2] for h in win] or [0])
    min_avail = min([h[1] for h in win] or [0])
    new_files_seen = sorted(set(files1) - set(files0))
    note(f'OBSERVED trace lines in the window: guard {len(guards)}, switch (ks1.t) {len(switches)}, writeable {len(writeable_window)}; '
         f'whole lifetime: writeable for ks1.t {len(writeable_t)}, writeable any {len(writeable_any)}')
    for gd in guards:
        note(f'OBSERVED guard: est {gd[0]} avail {gd[1]} refused {gd[2]} dir {gd[3]} (avail - est = {gd[1] - gd[0]} B)')
    for l in switches[:5]:
        note('OBSERVED ' + l)
    note(f'OBSERVED system.log: guard messages {guard_msgs}; Compacting lines {len(compacting)} (inputs {n_inputs}); Compacted lines {len(compacted)}; '
         f'"space check is disabled" lines {len(hatch_info)}; Reducing scope {len(sib_reduce)}; sibling abort {len(sib_abort)}; ERROR lines {len(errors)}; '
         f'FSWriteError/No space lines {len(fswrite)}; Stopping transports {len(stopping)}')
    for l in errors[:4]:
        note('OBSERVED ERROR ' + l[:300])
    for l in fswrite[:3]:
        note('OBSERVED FS ' + l[:300])
    note(f'OBSERVED files: Data.db {sorted(d0.values())} -> {sorted(d1.values())}; files {len(files0)} -> {len(files1)}; new names {new_files_seen[:12]}; '
         f'du {sum(files0.values())} -> {sum(files1.values())}; peak du {peak_du}; min df Available {min_avail}; df now {df_avail()}; '
         f'samples {len(win)}; DiskBoundaryManager debug lines for ks1.t (lifetime) {len(boundary_dbg)}')
    _, sb = sh('bin/nodetool statusbinary', check=False, timeout=120)
    _, sg = sh('bin/nodetool statusgossip', check=False, timeout=120)
    note(f'NODE STATE after the trigger: daemon {"up" if daemon_up() else "down"}; statusbinary {sb.strip()[-60:]!r}; statusgossip {sg.strip()[-60:]!r}')

    # ---- the expectations of 9a (one set per kind of label)
    plan_refuse = (U1 - M) < T
    expect(f'every task held all {NSST} inputs (one Compacting line with {NSST} Data.db) — else INVALID RUN', bool(compacting) and n_inputs[0] == NSST if not SIB else bool(compacting))
    expect('the background task was a COMPACTION with the switch off: one "space check is disabled" line' if not SIB else 'sibling control: no "space check is disabled" line',
           (len(hatch_info) >= 1) if not SIB else (len(hatch_info) == 0))
    if ARM == 'B':
        expect('arm B: no "Refreshing disk boundary cache for ks1.t" debug line in the lifetime', len(boundary_dbg) == 0)
        expect(f'arm B: one writeable trace line for ks1.t per flush (>= {NSST})', len(writeable_t) >= NSST)
        expect('arm B: exactly one guard trace line', len(guards) == 1)
        if guards:
            est, av, ref, _ = guards[0]
            expect('guard line: refused == (avail < est)', ref == (av < est))
            if not SIB:
                expect(f'guard line: est == T ({T})', est == T)
            expect(f'guard line: avail within 1 MiB of df at the trigger minus m ({U1 - M})', abs(av - max(0, U1 - M)) <= MIB)
        if SIB:
            kept = sorted(d0.values())
            expect('sibling control: at least one "Reducing scope" warning (the sibling refused first)', len(sib_reduce) >= 1)
            expect('sibling control: no guard exception (the guard admits the reduced estimate)', not guard_msgs)
            if guards:
                expect('sibling control: the guard admitted an estimate below T', (not guards[0][2]) and guards[0][0] < T)
            expect(f'sibling control: completed with {1 + len(sib_reduce)} Data.db (one output plus the shed inputs)', len(compacted) == 1 and len(d1) == 1 + len(sib_reduce))
        elif plan_refuse:
            expect('arm B refuse: the guard exception in system.log, once', len(guard_msgs) == 1)
            expect('arm B refuse: no switch line (no SSTableWriter)', len(switches) == 0)
            expect('arm B refuse: the table directory holds exactly the same files with the same lengths', files1 == files0)
            expect('arm B refuse: du never rose by more than 1 MiB during the window', peak_du <= sum(files0.values()) + MIB)
            expect('arm B refuse: no Compacted line, no sibling message', not compacted and not sib_reduce and not sib_abort)
        else:
            expect('arm B admit: no guard exception, no sibling message', not guard_msgs and not sib_reduce and not sib_abort)
            expect('arm B admit: one switch line with positions=null', len(switches) == 1 and 'positions=null' in switches[0])
            expect('arm B admit: one Compacted line and one Data.db whose length is within 1 % of T', len(compacted) == 1 and len(d1) == 1 and abs(sum(d1.values()) - T) <= T / 100)
    else:
        expect('arm A: the "Refreshing disk boundary cache for ks1.t" debug line appears (lifetime)', len(boundary_dbg) >= 1)
        expect('arm A: no writeable trace line in the whole lifetime (no flush or compaction reached the second check site)', len(writeable_any) == 0)
        expect('arm A: no guard trace line and no guard exception', not guards and not guard_msgs)
        expect('arm A: every switch line has positions=1 (the boundary path)', bool(switches) and all('positions=1 ' in l for l in switches))
        expect('arm A: no sibling message', not sib_reduce and not sib_abort)
        if OFF > -100:
            expect('arm A: completed: one Compacted line, one Data.db within 1 % of T', len(compacted) == 1 and len(d1) == 1 and abs(sum(d1.values()) - T) <= T / 100)
            if OFF < 0:
                expect(f'arm A d=-16: the minimum df Available during the compaction fell below m ({M}) and stayed above 0', 0 < min_avail < M)
            else:
                expect(f'arm A d={OFF}: the minimum df Available stayed at or above m ({M})', min_avail >= M)
        else:
            expect('arm A d=-256: a filesystem write error (FSWriteError / No space left on device)', len(fswrite) >= 1)
            expect('arm A d=-256: the filesystem was full (min df Available <= 1 MiB)', min_avail <= MIB)
            expect('arm A d=-256: no Compacted line', not compacted)
            expect('arm A d=-256: the 8 inputs are still there with their lengths', all(d1.get(k) == v for k, v in d0.items()))
            expect(f'arm A d=-256: peak du of the table within 16 MiB of du before + U ({sum(files0.values()) + U1})', abs(peak_du - (sum(files0.values()) + U1)) <= 16 * MIB)
            note(f'INFO arm A d=-256: transports stopped line {len(stopping)}; statusbinary {sb.strip()[-30:]!r}; partial output files left {[k for k in new_files_seen]}')
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
    sys.exit(1)
finally:
    stop_node()
    subprocess.run(f'cp {N}/logs/system.log {N}/logs/debug.log {D}/ 2>/dev/null; cp {N}/conf/cassandra.yaml {D}/cassandra.yaml 2>/dev/null; '
                   f'ls -la {DATA}/ks1/t-*/ > {D}/table-dir-final.txt 2>&1; df -B1 {MNT} >> {D}/table-dir-final.txt 2>&1', shell=True)
    unmount()
