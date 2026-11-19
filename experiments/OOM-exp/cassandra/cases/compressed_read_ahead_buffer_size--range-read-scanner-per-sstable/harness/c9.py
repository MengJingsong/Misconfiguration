#!/usr/bin/env python3
"""C9 stage-2 harness (design §2.5-§2.7). Runs locally on pc99. Shapes from the C8 harness (c8.py).
usage:
  c9.py setup                     copy harness files to $B/h, compile C9Jmx
  c9.py golden32                  K32 data: golden with sstable generations > 32 removed, $B/golden32
  c9.py golden                    build the golden data set G (N = 2,000 sstables), $B/golden
  c9.py run <run-id> <arm>        arms: R0 T2 K2 I2 T4 T8 T16 I2b K32
  c9.py queue <run-id:arm> ...    sequential; no new run starts after NO_START_AFTER (America/New_York)
Layout: B=/mydata/s4/c9-w4 (the session's directory; the design's /mydata/c9 renamed, amendment A1),
h/, golden-build/, golden/, inst/<run>/, runs/<run>/, dumps-kept/<budget>/.
The build /mydata/s4/cassandra-base is used unchanged (default ports, JMX 7199)."""
import glob, os, random, re, shutil, signal, subprocess, sys, threading, time

B = os.environ.get('C9_BASE', '/mydata/s4/c9-w4')
CH = '/mydata/s4/cassandra-base'
H = B + '/h'
GOLD = B + '/golden'
NODE_CPUS, CLIENT_CPUS = '0-19', '20-31'
JPORT = 7199
NT = f'{CH}/bin/nodetool -h 127.0.0.1 -p {JPORT}'
N_SST = 2000
NO_START_AFTER = os.environ.get('C9_NO_START_AFTER', '17:30')
SUMMARY = B + '/runs/summary.txt'
LOGF = None
BUDGETS = {'B2': (4096, 2048), 'B4': (8192, 4096), 'B8': (15872, 7936), 'B16': (15872, 16384)}
# arm: budget, C, D (s), extra yaml, ramp
ARMS = {
    'R0': ('B2', 8, 6 * 45, [], '1,2,3,4,6,8'),
    'T2': ('B2', 40, 300, [], ''),
    'K2': ('B2', 2, 180, [], ''),
    'K1': ('B2', 1, 180, [], ''),
    'I2': ('B2', 40, 180, ['compressed_read_ahead_buffer_size: 0KiB'], ''),
    'I2b': ('B2', 40, 180, [], ''),
    'T4': ('B4', 40, 300, [], ''),
    'T8': ('B8', 40, 300, [], ''),
    'T16': ('B16', 40, 300, [], ''),
    'K32': ('B2', 40, 120, [], ''),
    'RC': ('B2', 40, 300, [], ''),
}


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, flush=True)
    if LOGF:
        LOGF.write(line + '\n'); LOGF.flush()


def sh(cmd, timeout=600, check=False, quiet=False):
    if not quiet:
        log('+ ' + cmd)
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        out = (r.stdout or '') + (r.stderr or ''); rc = r.returncode
    except subprocess.TimeoutExpired:
        out = f'TIMEOUT after {timeout}s'; rc = -999
    if not quiet and LOGF:
        LOGF.write(out[-3000:] + f'\n  rc={rc}\n'); LOGF.flush()
    if check and rc != 0:
        raise RuntimeError(f'rc={rc}: {cmd}\n{out[-800:]}')
    return rc, out


def daemons():
    out = []
    for p in glob.glob('/proc/[0-9]*/cmdline'):
        try:
            c = open(p, 'rb').read().replace(b'\0', b' ').decode(errors='replace')
        except OSError:
            continue
        if 'CassandraDaemon' in c and c.split(' ')[0].endswith('java'):
            out.append((int(p.split('/')[2]), c))
    return out


def node_pid(inst):
    for p, c in daemons():
        if inst + '/' in c:
            return p
    return None


def start(inst, unit, heap, direct, extra, rundir):
    for d in ('logs', 'dumps', 'hints', 'saved_caches', 'cdc_raw', 'data', 'commitlog'):
        os.makedirs(f'{inst}/{d}', exist_ok=True)
    shutil.rmtree(inst + '/conf', ignore_errors=True)
    shutil.copytree(CH + '/conf', inst + '/conf')
    add = [f'data_file_directories: [{inst}/data]', f'commitlog_directory: {inst}/commitlog', f'hints_directory: {inst}/hints',
           f'saved_caches_directory: {inst}/saved_caches', f'cdc_raw_directory: {inst}/cdc_raw'] + extra
    y = open(CH + '/conf/cassandra.yaml').read()
    open(inst + '/conf/cassandra.yaml', 'w').write(y + '\n# ---- C9 stage-2 lines (environment; compressed_read_ahead_buffer_size only in arm I2) ----\n' + '\n'.join(add) + '\n')
    sh(f'diff {CH}/conf/cassandra.yaml {inst}/conf/cassandra.yaml > {rundir}/yaml.diff', quiet=True)
    env = (f'CASSANDRA_CONF={inst}/conf CASSANDRA_LOG_DIR={inst}/logs CASSANDRA_HEAPDUMP_DIR={inst}/dumps '
           f'MAX_HEAP_SIZE={heap}M MAX_DIRECT_MEMORY_SIZE={direct}M JVM_EXTRA_OPTS=-Dcassandra.printHeapHistogramOnOutOfMemoryError=true')
    inner = (f'cd {inst}; ulimit -n 100000; exec systemd-run --user --scope -p MemorySwapMax=0 --unit {unit} '
             f'taskset -c {NODE_CPUS} {CH}/bin/cassandra -f')
    cmd = f"( setsid nohup env -u HEAP_NEWSIZE {env} bash -c '{inner}' < /dev/null > {inst}/logs/launch.log 2>&1 & )"
    sh(cmd, timeout=30)
    log(f'start: heap {heap} MiB, direct {direct} MiB, yaml add: {add}')


def wait_up(inst, timeout=240):
    t0 = time.time(); seen = False
    while time.time() - t0 < timeout:
        p = node_pid(inst)
        if p is None and seen:
            return None
        if p is not None:
            seen = True
            rc, st = sh(f'{NT} statusbinary', timeout=30, quiet=True)
            if re.search(r'^running\s*$', st, re.M):
                log(f'node up (pid {p}) after {time.time() - t0:.0f} s')
                return p
        time.sleep(3)
    return None


def stop_node(inst, unit, graceful=True):
    p = node_pid(inst)
    if p is not None:
        if graceful:
            sh(f'{NT} stopdaemon', timeout=70)
            for _ in range(40):
                if node_pid(inst) is None:
                    break
                time.sleep(1)
        p = node_pid(inst)
        if p is not None:
            log(f'kill -9 {p}'); os.kill(p, signal.SIGKILL); time.sleep(2)
    sh(f'systemctl --user stop {unit}.scope', timeout=30, quiet=True)
    return node_pid(inst) is None


def driver():
    sys.path.insert(0, H)
    import c9_scan
    c9_scan.driver()


class Rss(threading.Thread):
    def __init__(self, pid, path):
        super().__init__(daemon=True); self.pid = pid; self.f = open(path, 'w'); self.f.write('ms,rss_anon_kb,vmrss_kb\n'); self.ev = threading.Event()

    def run(self):
        while not self.ev.is_set():
            try:
                st = open(f'/proc/{self.pid}/status').read()
                a = re.search(r'RssAnon:\s+(\d+)', st).group(1); r = re.search(r'VmRSS:\s+(\d+)', st).group(1)
                self.f.write(f'{int(time.time() * 1000)},{a},{r}\n'); self.f.flush()
            except (OSError, AttributeError):
                pass
            self.ev.wait(1.0)


def jcount():
    rc, o = sh(f'java -Xmx64m -cp {H} C9Jmx count {JPORT}', timeout=60, quiet=True)
    m = re.search(r'live (-?\d+) pending_compactions (-?\d+) table_pending (-?\d+)', o)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else (None, None, None)


# ---------------------------------------------------------------- setup and golden
def l_setup():
    os.makedirs(H, exist_ok=True); os.makedirs(B + '/runs', exist_ok=True)
    here = os.path.dirname(os.path.abspath(__file__))
    for f in glob.glob(here + '/*'):
        if os.path.isfile(f) and os.path.abspath(f) != os.path.abspath(H + '/' + os.path.basename(f)):
            shutil.copy(f, H)
    sh(f'javac -d {H} {H}/C9Jmx.java', check=True)
    sh(f'sha256sum {CH}/build/apache-cassandra-5.0.9-SNAPSHOT.jar')


def l_golden():
    inst = B + '/golden-build'
    rundir = B + '/runs/golden'
    os.makedirs(rundir, exist_ok=True)
    if daemons():
        raise SystemExit('CassandraDaemon running: ' + str([p for p, _ in daemons()]))
    shutil.rmtree(inst, ignore_errors=True)
    heap, direct = BUDGETS['B2']
    start(inst, 'c9-golden', heap, direct, [], rundir)
    if wait_up(inst) is None:
        raise SystemExit('golden node not up')
    driver()
    from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
    from cassandra.policies import DCAwareRoundRobinPolicy
    from cassandra.concurrent import execute_concurrent_with_args
    from cassandra import ConsistencyLevel
    prof = ExecutionProfile(consistency_level=ConsistencyLevel.ONE, request_timeout=60,
                            load_balancing_policy=DCAwareRoundRobinPolicy(local_dc='datacenter1'))
    cl = Cluster(['127.0.0.1'], port=9042, protocol_version=4, token_metadata_enabled=False, execution_profiles={EXEC_PROFILE_DEFAULT: prof})
    s = cl.connect()
    s.execute("CREATE KEYSPACE IF NOT EXISTS c9 WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    s.execute("CREATE TABLE IF NOT EXISTS c9.t (pk bigint PRIMARY KEY, v blob) WITH compaction = {'class':'SizeTieredCompactionStrategy','enabled':'false'}")
    time.sleep(2)
    sh(f'{CH}/bin/cqlsh 127.0.0.1 -e "DESCRIBE TABLE c9.t" > {rundir}/describe.txt 2>&1', timeout=120)
    ps = s.prepare('INSERT INTO c9.t (pk, v) VALUES (?, ?)')
    fl = subprocess.Popen(['java', '-Xmx64m', '-cp', H, 'C9Jmx', 'flushsrv', str(JPORT)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    rnd = random.Random(9)
    t0 = time.time()
    for r in range(1, N_SST + 1):
        rows = [(rnd.getrandbits(64) - 2 ** 63, rnd.randbytes(300)) for _ in range(1000)]
        execute_concurrent_with_args(s, ps, rows, concurrency=128, raise_on_first_error=True)
        fl.stdin.write('flush\n'); fl.stdin.flush()
        ans = fl.stdout.readline().strip()
        if r % 100 == 0 or not ans.startswith('ok'):
            log(f'round {r}: {ans} ({time.time() - t0:.0f} s)')
        if not ans.startswith('ok'):
            raise SystemExit('flush failed')
    fl.stdin.write('quit\n'); fl.stdin.flush(); fl.wait(timeout=30)
    cl.shutdown()
    rc, ts = sh(f'{NT} tablestats c9.t', timeout=120)
    open(rundir + '/tablestats.txt', 'w').write(ts)
    data = sorted(glob.glob(f'{inst}/data/c9/t-*/*-Data.db'))
    log(f'Data.db files: {len(data)}')
    md = ''
    for f in (data[0], data[len(data) // 2], data[-1]):
        rc, o = sh(f'{CH}/tools/bin/sstablemetadata {f} 2>&1 | grep -iE "First token|Last token|Compressor|SSTable:|Partitions|Estimated" | head -12', timeout=120, quiet=True)
        md += f'== {f}\n{o}\n'
    open(rundir + '/sstablemetadata.txt', 'w').write(md)
    sh(f'{NT} drain', timeout=300)
    stop_node(inst, 'c9-golden')
    shutil.rmtree(GOLD, ignore_errors=True); os.makedirs(GOLD)
    sh(f'cp -a {inst}/data {inst}/commitlog {inst}/saved_caches {inst}/hints {GOLD}/', check=True, timeout=900)
    sh(f'du -sh {GOLD} > {rundir}/du.txt; (cd {GOLD} && find . -type f | sort | sha256sum) > {rundir}/filelist.sha256; '
       f'ls -l {GOLD}/data/c9/t-*/*-Data.db | head -3 >> {rundir}/du.txt; ls {GOLD}/data/c9/t-*/*-Data.db | wc -l >> {rundir}/du.txt')
    for f in glob.glob(inst + '/logs/*.log'):
        shutil.copy(f, rundir)
    shutil.rmtree(inst, ignore_errors=True)
    log('golden done')


# ---------------------------------------------------------------- runs
def l_run(name, arm):
    global LOGF
    budget, C, D, extra, ramp = ARMS[arm]
    heap, direct = BUDGETS[budget]
    if daemons():
        raise SystemExit('CassandraDaemon running: ' + str([p for p, _ in daemons()]))
    rundir = f'{B}/runs/{name}'
    if os.path.exists(rundir):
        raise SystemExit('run dir exists: ' + rundir)
    os.makedirs(rundir)
    LOGF = open(rundir + '/session.log', 'a')
    inst = f'{B}/inst/{name}'
    unit = f'c9-{name}'
    shutil.rmtree(inst, ignore_errors=True)
    os.makedirs(inst)
    src = GOLD if arm != 'K32' else B + '/golden32'
    sh(f'cp -a {src}/. {inst}/', check=True, timeout=900)
    log(f'RUN {name} arm={arm} budget={budget} heap={heap} direct={direct} C={C} D={D} extra={extra} ramp={ramp} '
        f'load={open("/proc/loadavg").read().split()[:3]}')
    t_start = time.time()
    start(inst, unit, heap, direct, extra, rundir)
    p = wait_up(inst)
    notes = [f'arm={arm} budget={budget} heap={heap} direct={direct} C={C} D={D}']
    valid = True
    if p is None:
        notes.append('node did not come up'); valid = False
    else:
        notes.append(f'up_after_s={time.time() - t_start:.0f}')
        sh(f'ps -o args= -p {p} | tr " " "\\n" | grep -E "^-Xm[sx]|MaxDirectMemorySize|^-Xlog|HeapDump|OutOfMemory|printHeap" > {rundir}/jvmargs.txt', quiet=True)
        live, pend, tpend = jcount()
        rc, cs = sh(f'{NT} compactionstats', timeout=60, quiet=True)
        open(rundir + '/compactionstats-start.txt', 'w').write(cs)
        notes.append(f'gate: LiveSSTableCount={live} pending_compactions={pend} table_pending={tpend}')
        expect = N_SST if arm != 'K32' else 32
        if live != expect:
            notes.append('VALIDITY GATE FAILED (sstable count)'); valid = False
        log(notes[-1])
        csv = rundir + '/samples.csv'
        samp = subprocess.Popen(['taskset', '-c', CLIENT_CPUS, 'java', '-Xmx64m', '-cp', H, 'C9Jmx', 'poll', str(JPORT), csv, '200'],
                                stdout=open(rundir + '/sampler.out', 'w'), stderr=subprocess.STDOUT, start_new_session=True)
        rss = Rss(p, rundir + '/rss.csv'); rss.start()
        if arm == 'R0':
            rc, tr = sh(f'{CH}/bin/cqlsh 127.0.0.1 --request-timeout=60 -e "TRACING ON; SELECT pk FROM c9.t LIMIT 10;"', timeout=120, quiet=True)
            open(rundir + '/trace.txt', 'w').write(tr)
            m = re.search(r'Executing seq scan across (\d+) sstables', tr)
            notes.append(f'trace: {m.group(0) if m else "NO seq-scan line"}')
            log(notes[-1])
        if arm == 'I2b':
            rc, o = sh(f'{NT} compact c9 t', timeout=900)
            live, _, _ = jcount()
            notes.append(f'I2b: compact rc={rc}, LiveSSTableCount after={live}')
        time.sleep(20)  # idle B0
        if arm == 'RC':
            # design §2.7 RC: compaction re-enabled right after startup, load starts at once
            rc, o = sh(f"""{CH}/bin/cqlsh 127.0.0.1 -e \"ALTER TABLE c9.t WITH compaction = {{'class':'SizeTieredCompactionStrategy'}}\" """, timeout=120)
            notes.append(f'RC: ALTER TABLE (compaction on) rc={rc} at {time.strftime("%T")}')
        t_load = time.time()
        open(rundir + '/t_load.txt', 'w').write(f'{int(t_load * 1000)}\n')
        cargs = f'--streams {C} --fetch 1000 --duration {D} --out {rundir}/client' + (f' --ramp {ramp} --step 45' if ramp else '')
        cl = subprocess.Popen(f'exec taskset -c {CLIENT_CPUS} python3 {H}/c9_scan.py {cargs}', shell=True,
                              stdout=open(rundir + '/client.out', 'w'), stderr=subprocess.STDOUT, start_new_session=True)
        log('client started: ' + cargs)
        died_at = None
        while cl.poll() is None:
            if node_pid(inst) is None:
                died_at = time.time(); break
            if time.time() - t_load > D + 150:
                notes.append('client overran D+150 s'); break
            time.sleep(0.5)
        if died_at:
            notes.append(f'NODE GONE at load+{died_at - t_load:.1f}s')
            log(notes[-1])
            time.sleep(3)
        if cl.poll() is None:
            try:
                os.killpg(cl.pid, signal.SIGTERM); time.sleep(2); os.killpg(cl.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        notes.append(f'load_end at load+{time.time() - t_load:.1f}s; node_alive={node_pid(inst) is not None}')
        rss.ev.set()
        try:
            os.killpg(samp.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    stopped = stop_node(inst, unit)
    notes.append(f'stopped_clean={stopped} valid_gate={valid}')
    time.sleep(1)
    for f in glob.glob(inst + '/logs/*'):
        if os.path.isfile(f):
            shutil.copy(f, rundir)
    dumps = glob.glob(inst + '/dumps/*.hprof') + glob.glob(inst + '/*.hprof')
    kd = f'{B}/dumps-kept/{budget}'
    for f in dumps:
        sz = os.path.getsize(f)
        if not os.path.isdir(kd) or not os.listdir(kd):
            os.makedirs(kd, exist_ok=True); shutil.move(f, kd + '/' + name + '-' + os.path.basename(f))
            notes.append(f'heap dump kept: {kd}/{name}-{os.path.basename(f)} ({sz / 2**30:.2f} GiB)')
        else:
            os.remove(f); notes.append(f'heap dump deleted (not first for {budget}): {sz / 2**30:.2f} GiB')
    for f in glob.glob(inst + '/hs_err*'):
        shutil.move(f, rundir)
    open(rundir + '/notes.txt', 'w').write('\n'.join(notes) + '\n')
    shutil.rmtree(inst, ignore_errors=True)
    rc, o = sh(f'python3 {H}/c9_sum.py {rundir}', timeout=300, quiet=True)
    open(rundir + '/summary.txt', 'w').write(o)
    line = o.strip().splitlines()[0] if o.strip() else f'{name} summary failed'
    with open(SUMMARY, 'a') as f:
        f.write(line + '\n')
    log('OUTCOME ' + line)
    left = [p for p, c in daemons() if B in c]
    log(f'left: C9 daemons {left}')


def l_queue(specs):
    for s in specs:
        hh, mm = map(int, NO_START_AFTER.split(':'))
        now = subprocess.run('TZ=America/New_York date +%H:%M', shell=True, capture_output=True, text=True).stdout.strip()
        nh, nm = map(int, now.split(':'))
        if nh * 60 + nm > hh * 60 + mm:
            with open(B + '/runs/queue.log', 'a') as f:
                f.write(f'skip {s} at {now} (past {NO_START_AFTER})\n')
            continue
        name, arm = s.split(':')
        with open(B + '/runs/queue.log', 'a') as f:
            f.write(f'start {s} at {now}\n')
        r = subprocess.run([sys.executable, os.path.abspath(__file__), 'run', name, arm])
        with open(B + '/runs/queue.log', 'a') as f:
            f.write(f'end {s} rc={r.returncode} at {time.strftime("%T")}\n')
    with open(B + '/runs/queue.log', 'a') as f:
        f.write(f'queue done at {time.strftime("%T")}\n')


if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'setup':
        l_setup()
    elif a[0] == 'golden':
        LOGF = open(B + '/runs/golden-session.log', 'a'); l_golden()
    elif a[0] == 'golden32':
        # K32 data (design §2.7): golden copy with all but the first 32 sstable generations of c9.t removed offline
        g = B + '/golden32'
        shutil.rmtree(g, ignore_errors=True)
        sh(f'cp -a {GOLD} {g}', check=True, timeout=900)
        n = 0
        for f in glob.glob(g + '/data/c9/t-*/nb-*-big-*'):
            gen = int(os.path.basename(f).split('-')[1])
            if gen > 32:
                os.remove(f); n += 1
        print('removed', n, 'files; Data.db left', len(glob.glob(g + '/data/c9/t-*/*-Data.db')))
    elif a[0] == 'run':
        l_run(a[1], a[2])
    elif a[0] == 'queue':
        l_queue(a[1:])
