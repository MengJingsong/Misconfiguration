#!/usr/bin/env python3
"""C8 stage 2 harness (design §2.5-§2.7 of the case file). Runs locally on pc96.
usage:
  c8.py setup                       copy the build, set JMX 7208 in the copied cassandra-env.sh, compile C8Sampler
  c8.py seed                        build the seed data set (8 GiB heap node; preparation, not a reading)
  c8.py run <name> <arm> <H_MiB> [sai_MiB]   arms: B, BW, W, BS, I-B, I-BW (I-* need sai_MiB)
  c8.py queue <name:arm:H[:sai]> ...         runs sequentially; no new run starts after NO_START_AFTER (HH:MM, America/New_York)
Layout: B=/mydata/s4/c8-w3 (stage-2 directory; the design's c8-w1 renamed by the session's task), cassandra/, seed/, inst/<run>/, runs/<run>/.
"""
import glob, hashlib, os, re, shutil, signal, subprocess, sys, threading, time

B = os.environ.get('C8_BASE', '/mydata/s4/c8-w3')
CH = B + '/cassandra'
H = B + '/h'
SEED = B + '/seed'
NODE_CPUS = '0-15'
STRESS_CPUS = '16-23'
ADDR, SPORT, NPORT, JPORT = '127.0.0.8', 7008, 9048, 7208
NT = f'{CH}/bin/nodetool -h 127.0.0.1 -p {JPORT}'
CQLSH = f'{CH}/bin/cqlsh {ADDR} {NPORT}'
RUN_CAP = 12 * 60
NO_START_AFTER = os.environ.get('C8_NO_START_AFTER', '10:25')
SUMMARY = B + '/runs/summary.txt'
LOGF = None


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, flush=True)
    if LOGF:
        LOGF.write(line + '\n'); LOGF.flush()


def sh(cmd, timeout=600, check=False, env=None, quiet=False):
    if not quiet:
        log('+ ' + cmd)
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env)
        out = (r.stdout or '') + (r.stderr or '')
        rc = r.returncode
    except subprocess.TimeoutExpired as e:
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


def yaml_for(inst, extra):
    y = open(f'{CH}/conf/cassandra.yaml').read()
    sub = {
        'cluster_name': "cluster_name: 'c8'",
        'listen_address': f'listen_address: {ADDR}',
        'rpc_address': f'rpc_address: {ADDR}',
        'storage_port': f'storage_port: {SPORT}',
        'native_transport_port': f'native_transport_port: {NPORT}',
    }
    lines = []
    for l in y.splitlines():
        k = l.split(':')[0]
        if k in sub and not l.startswith((' ', '#')):
            lines.append(sub[k])
        elif '- seeds: "127.0.0.1:7000"' in l:
            lines.append(l.replace('127.0.0.1:7000', f'{ADDR}:{SPORT}'))
        else:
            lines.append(l)
    add = [f'data_file_directories: [{inst}/data]', f'commitlog_directory: {inst}/commitlog', f'hints_directory: {inst}/hints',
           f'saved_caches_directory: {inst}/saved_caches', f'cdc_raw_directory: {inst}/cdc_raw'] + extra
    return '\n'.join(lines) + '\n# ---- C8 stage-2 lines (environment; sai_options only in arm I) ----\n' + '\n'.join(add) + '\n', add


def start(inst, unit, heap, extra, rundir):
    for d in ('logs', 'dumps', 'hints', 'saved_caches', 'cdc_raw', 'data', 'commitlog'):
        os.makedirs(f'{inst}/{d}', exist_ok=True)
    if os.path.exists(inst + '/conf'):
        shutil.rmtree(inst + '/conf')
    shutil.copytree(CH + '/conf', inst + '/conf')
    txt, add = yaml_for(inst, extra)
    open(inst + '/conf/cassandra.yaml', 'w').write(txt)
    sh(f'diff {CH}/conf/cassandra.yaml {inst}/conf/cassandra.yaml > {rundir}/yaml.diff', quiet=True)
    direct = heap // 2
    env = (f'CASSANDRA_CONF={inst}/conf CASSANDRA_LOG_DIR={inst}/logs CASSANDRA_HEAPDUMP_DIR={inst}/dumps '
           f'MAX_HEAP_SIZE={heap}M MAX_DIRECT_MEMORY_SIZE={direct}M')
    cmd = (f'( setsid nohup env -u HEAP_NEWSIZE {env} systemd-run --user --scope -p MemorySwapMax=0 --unit {unit} '
           f'taskset -c {NODE_CPUS} {CH}/bin/cassandra -f < /dev/null > {inst}/logs/launch.log 2>&1 & )')
    sh(cmd, timeout=30)
    log(f'start: heap {heap} MiB, direct {direct} MiB, yaml add: {add}')


def wait_up(inst, timeout=180):
    t0 = time.time()
    seen = False
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


def stop_node(inst, unit):
    p = node_pid(inst)
    if p is not None:
        sh(f'{NT} stopdaemon', timeout=70)
        for _ in range(60):
            if node_pid(inst) is None:
                break
            time.sleep(1)
        p = node_pid(inst)
        if p is not None:
            log(f'kill -9 {p}'); os.kill(p, signal.SIGKILL); time.sleep(2)
    sh(f'systemctl --user stop {unit}.scope', timeout=30, quiet=True)
    return node_pid(inst) is None


def driver():
    lib = CH + '/lib'
    z = max(glob.glob(lib + '/cassandra-driver-internal-only-*.zip'))
    ver = os.path.splitext(os.path.basename(z))[0][len('cassandra-driver-internal-only-'):]
    sys.path.insert(0, os.path.join(z, 'cassandra-driver-' + ver))
    for p in ('pure_sasl-', 'wcwidth-', 'pyasyncore-'):
        zz = glob.glob(os.path.join(lib, p + '*.zip'))
        if zz:
            sys.path.insert(0, max(zz))


def cql(stmt, timeout=600):
    return sh(f'{CQLSH} --request-timeout={timeout} -e "{stmt}"', timeout=timeout + 60)


# ---------------------------------------------------------------- setup and seed
def l_setup():
    if not os.path.isdir(CH):
        sh(f'cp -a /mydata/s4/cassandra-base {CH}', check=True, timeout=600)
    env_sh = CH + '/conf/cassandra-env.sh'
    t = open(env_sh).read()
    if 'JMX_PORT="7199"' in t:
        open(env_sh, 'w').write(t.replace('JMX_PORT="7199"', f'JMX_PORT="{JPORT}"'))
    sh(f'grep -n "^JMX_PORT" {env_sh}')
    here = os.path.dirname(os.path.abspath(__file__))
    for f in glob.glob(here + '/*'):
        if os.path.isfile(f):
            shutil.copy(f, H)
    sh(f'javac -d {H} {H}/C8Sampler.java', check=True)
    sh(f'sha256sum {CH}/build/apache-cassandra-5.0.9-SNAPSHOT.jar /mydata/s4/cassandra-base/build/apache-cassandra-5.0.9-SNAPSHOT.jar')


def l_seed():
    inst = B + '/inst/seed'
    rundir = B + '/runs/seed'
    os.makedirs(rundir, exist_ok=True)
    if daemons():
        log('WARNING: other CassandraDaemon(s) running: ' + '; '.join(str(p) for p, _ in daemons()))
    shutil.rmtree(inst, ignore_errors=True)
    start(inst, 'c8-seed', 8192, [], rundir)
    if wait_up(inst) is None:
        raise SystemExit('seed node not up')
    rc, o = cql("CREATE KEYSPACE c8 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}; "
                "CREATE TABLE c8.big (pk bigint PRIMARY KEY, v text); CREATE TABLE c8.small (pk bigint PRIMARY KEY, v text);")
    driver()
    from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
    from cassandra.concurrent import execute_concurrent_with_args
    from cassandra import ConsistencyLevel
    prof = ExecutionProfile(consistency_level=ConsistencyLevel.ONE, request_timeout=120)
    cl = Cluster([ADDR], port=NPORT, protocol_version=5, execution_profiles={EXEC_PROFILE_DEFAULT: prof})
    s = cl.connect()
    for tab, prefix, n in (('big', 'big-', 2000000), ('small', 'small-', 200000)):
        ps = s.prepare(f'INSERT INTO c8.{tab} (pk, v) VALUES (?, ?)')
        t0 = time.time(); done = 0; step = 20000
        while done < n:
            rows = [(i, hashlib.md5(f'{prefix}{i}'.encode()).hexdigest()) for i in range(done, min(n, done + step))]
            execute_concurrent_with_args(s, ps, rows, concurrency=128, raise_on_first_error=True)
            done += len(rows)
            if done % 400000 == 0:
                log(f'seed {tab}: {done} rows in {time.time() - t0:.0f} s')
        log(f'seed {tab}: loaded {done} rows in {time.time() - t0:.0f} s')
    cl.shutdown()
    sh(f"taskset -c {STRESS_CPUS} {CH}/tools/bin/cassandra-stress write n=1000 cl=ONE -schema 'replication(factor=1)' "
       f"-node {ADDR} -port native={NPORT} jmx={JPORT} -mode native cql3 > {rundir}/stress-schema.log 2>&1", timeout=300)
    sh(f'{NT} flush', timeout=600)
    sh(f'{NT} compact c8 big', timeout=1200)
    sh(f'{NT} compact c8 small', timeout=600)
    rc, ts = sh(f'{NT} tablestats c8', timeout=120)
    open(rundir + '/tablestats.txt', 'w').write(ts)
    rc, cnt = cql('SELECT count(*) FROM c8.small;', timeout=600)
    log('small count: ' + cnt.strip().replace('\n', ' | '))
    sh(f'{NT} drain', timeout=300)
    stop_node(inst, 'c8-seed')
    shutil.rmtree(SEED, ignore_errors=True)
    os.makedirs(SEED)
    sh(f'cp -a {inst}/data {inst}/commitlog {SEED}/', check=True, timeout=600)
    sh(f'ls -l {SEED}/data/c8/*/*-Data.db {SEED}/data/keyspace1/*/*-Data.db > {rundir}/sstables.txt; cat {rundir}/sstables.txt; du -sh {SEED}')
    for f in glob.glob(inst + '/logs/system.log') + glob.glob(inst + '/logs/launch.log'):
        shutil.copy(f, rundir)
    shutil.rmtree(inst, ignore_errors=True)
    log('seed done')


# ---------------------------------------------------------------- runs
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


def last_gauges(csv):
    try:
        with open(csv, 'rb') as f:
            f.seek(0, 2); n = f.tell(); f.seek(max(0, n - 4000))
            lines = f.read().decode(errors='replace').splitlines()
        for l in reversed(lines):
            p = l.split(',')
            if len(p) >= 11 and p[0].isdigit():
                return [int(x) for x in p]
    except OSError:
        pass
    return None


def hist(pid, path, why):
    t = time.time()
    rc, o = sh(f'timeout 120 jcmd {pid} GC.class_histogram > {path} 2>&1', timeout=130)
    log(f'histogram {os.path.basename(path)} ({why}) rc={rc} in {time.time() - t:.1f} s at {time.strftime("%T")}')
    return t


def build(inst, table, idx, deadline, rundir, notes):
    """CREATE INDEX (initial build), wait, then nodetool rebuild_index. Returns number of builds completed."""
    done = 0
    t0 = time.time()
    rc, o = cql(f"CREATE INDEX {idx} ON c8.{table} (v) USING 'sai';", timeout=300)
    notes.append(f'create_index rc={rc} t={time.time() - t0:.0f}s {o.strip()[-160:]!r}')
    log(notes[-1])
    if node_pid(inst) is None:
        return done
    built = False
    time.sleep(3)
    while time.time() < deadline:
        if node_pid(inst) is None:
            notes.append('node gone during initial build'); return done
        try:
            sl = open(inst + '/logs/system.log', errors='replace').read()
        except OSError:
            sl = ''
        if re.search(rf'Index \[{idx}\] became queryable after successful build', sl):
            built = True; break
        if re.search(rf'Index build of .*{idx}.* failed', sl):
            notes.append('initial build failed (log)'); break
        time.sleep(2)
    t1 = time.time()
    notes.append(f'initial_build {"complete" if built else "NOT complete"} at {t1 - t0:.0f}s')
    log(notes[-1])
    if not built:
        return done
    done += 1
    left = int(deadline - time.time())
    if left < 30 or node_pid(inst) is None:
        return done
    rc, o = sh(f'{NT} rebuild_index c8 {table} {idx}', timeout=min(left, 8 * 60))
    alive = node_pid(inst) is not None
    notes.append(f'rebuild_index rc={rc} in {time.time() - t1:.0f}s alive={alive} {o.strip()[-200:]!r}')
    log(notes[-1])
    if rc == 0 and alive:
        done += 1
    return done


def l_run(name, arm, heap, sai=None):
    global LOGF
    if daemons():
        others = [(p, c) for p, c in daemons() if B not in c]
        mine = [(p, c) for p, c in daemons() if B in c]
        if mine:
            raise SystemExit(f'a C8 node is still running: {mine[0][0]}')
        log('note: other sessions run CassandraDaemon(s): ' + ', '.join(str(p) for p, _ in others))
    rundir = f'{B}/runs/{name}'
    if os.path.exists(rundir):
        raise SystemExit('run dir exists: ' + rundir)
    os.makedirs(rundir)
    LOGF = open(rundir + '/session.log', 'a')
    inst = f'{B}/inst/{name}'
    unit = f'c8-{name}'
    shutil.rmtree(inst, ignore_errors=True)
    os.makedirs(inst)
    sh(f'cp -a {SEED}/data {SEED}/commitlog {inst}/', check=True, timeout=600)
    rc, df = sh('df -BG --output=avail /mydata | tail -1', quiet=True)
    log(f'RUN {name} arm={arm} H={heap} sai={sai} df_avail={df.strip()} load={open("/proc/loadavg").read().split()[:3]}')
    extra = ['sai_options:', f'  segment_write_buffer_size: {sai}MiB'] if sai else []
    t_start = time.time()
    deadline = t_start + RUN_CAP
    start(inst, unit, heap, extra, rundir)
    p = wait_up(inst)
    notes = []
    stress = None
    if p is None:
        notes.append('node did not come up')
    else:
        csv = rundir + '/gauges.csv'
        samp = subprocess.Popen(['java', '-Xmx64m', '-cp', H, 'C8Sampler', str(JPORT), csv, '500'], stdout=open(rundir + '/sampler.out', 'w'),
                                stderr=subprocess.STDOUT, start_new_session=True)
        rss = Rss(p, rundir + '/rss.csv'); rss.start()
        time.sleep(3)
        hist(p, rundir + '/hist-B0.txt', 'B0, forced GC before the arm')
        t_arm = time.time()
        open(rundir + '/t_arm.txt', 'w').write(f'{int(t_arm * 1000)}\n')
        base_arm = arm[2:] if arm.startswith('I-') else arm
        # survivor histogram trigger (controls and intervention only; never in the test arm BW)
        want_hist = arm in ('B', 'BS', 'W', 'I-B', 'I-BW')
        hist_done = threading.Event()

        def hist_watch():
            while not hist_done.is_set():
                g = last_gauges(csv)
                if node_pid(inst) is None:
                    return
                trig = None
                if g and arm in ('B', 'I-B', 'I-BW') and g[2] > 0 and g[1] >= 0.95 * g[2]:
                    trig = f'K_D1 {g[1]} >= 0.95 x limit {g[2]}'
                if g and arm == 'BS' and g[1] >= 400 * 2 ** 20:
                    trig = f'K_D1 {g[1]} >= 400 MiB'
                if arm == 'W' and time.time() - t_arm >= 240:
                    trig = 't = 240 s'
                if trig:
                    hist(p, rundir + '/hist-peak.txt', trig); hist_done.set(); return
                time.sleep(0.5)
        hw = None
        if want_hist:
            hw = threading.Thread(target=hist_watch, daemon=True); hw.start()
        builds = 0
        if base_arm in ('W', 'BW'):
            dur = 300 if base_arm == 'W' else 600
            scmd = (f"exec taskset -c {STRESS_CPUS} {CH}/tools/bin/cassandra-stress write duration={dur}s cl=ONE no-warmup "
                    f"-col 'size=fixed(1024)' 'n=fixed(4)' -rate threads=32 -node {ADDR} -port native={NPORT} jmx={JPORT} "
                    f"-mode native cql3 -log interval=1 file={rundir}/stress.log")
            log('+ ' + scmd)
            stress = subprocess.Popen(scmd, shell=True, stdout=open(rundir + '/stress.out', 'w'), stderr=subprocess.STDOUT, start_new_session=True)
        if base_arm == 'W':
            while stress.poll() is None and time.time() < deadline and node_pid(inst) is not None:
                time.sleep(2)
        elif base_arm == 'BW':
            t_w = time.time()
            while time.time() - t_w < 60 and node_pid(inst) is not None:
                time.sleep(1)
            if node_pid(inst) is not None:
                notes.append(f'build starts at arm+{time.time() - t_arm:.0f}s')
                builds = build(inst, 'big', 'v_idx', deadline, rundir, notes)
        elif base_arm == 'B':
            builds = build(inst, 'big', 'v_idx', deadline, rundir, notes)
        elif base_arm == 'BS':
            builds = build(inst, 'small', 'vs_idx', deadline, rundir, notes)
        notes.append(f'builds_completed={builds}')
        if node_pid(inst) is not None and builds == 2:
            key = 'big' if base_arm != 'BS' else 'small'
            pre = 'big-' if key == 'big' else 'small-'
            val = hashlib.md5(f'{pre}12345'.encode()).hexdigest()
            idx_col = 'v'
            rc, o = cql(f"SELECT count(*) FROM c8.{key} WHERE {idx_col} = '{val}';", timeout=120)
            m = re.search(r'^\s*(\d+)\s*$', o, re.M)
            notes.append(f'query_check count={m.group(1) if m else "?"}')
        if stress is not None and stress.poll() is None:
            log(f'kill stress pgid {stress.pid}')
            try:
                os.killpg(stress.pid, signal.SIGTERM); time.sleep(3); os.killpg(stress.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        hist_done.set()
        died = node_pid(inst) is None
        notes.append(f'node_died_before_stop={died} at arm+{time.time() - t_arm:.0f}s')
        rss.ev.set()
        try:
            os.killpg(samp.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    stopped = stop_node(inst, unit)
    notes.append(f'stopped_clean={stopped}')
    if stress is not None and stress.poll() is None:
        try:
            os.killpg(stress.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    time.sleep(2)
    for f in glob.glob(inst + '/logs/*'):
        if os.path.isfile(f):
            shutil.copy(f, rundir)
    for f in glob.glob(inst + '/dumps/*.hprof') + glob.glob(inst + '/logs/*.hprof'):
        shutil.move(f, rundir)
    for f in glob.glob(f'{CH}/hs_err*') + glob.glob(f'{inst}/hs_err*') + glob.glob('hs_err*'):
        shutil.move(f, rundir)
    open(rundir + '/notes.txt', 'w').write('\n'.join(notes) + '\n')
    open(rundir + '/meta.txt', 'w').write(f'name={name}\narm={arm}\nheap={heap}\nsai={sai or 1024}\nt_start_ms={int(t_start * 1000)}\n')
    shutil.rmtree(inst, ignore_errors=True)
    rc, o = sh(f'python3 {H}/selfcheck.py {rundir}', timeout=600)
    line = o.strip().splitlines()[-1] if o.strip() else f'{name} selfcheck failed'
    with open(SUMMARY, 'a') as f:
        f.write(line + '\n')
    log('OUTCOME ' + line)
    log(f'left: C8 daemons {[(p) for p, c in daemons() if B in c]}')


def l_queue(specs):
    for s in specs:
        hh, mm = map(int, NO_START_AFTER.split(':'))
        now = subprocess.run('TZ=America/New_York date +%H:%M', shell=True, capture_output=True, text=True).stdout.strip()
        nh, nm = map(int, now.split(':'))
        if nh * 60 + nm > hh * 60 + mm:
            print(f'[{time.strftime("%T")}] queue: {now} past {NO_START_AFTER}, not starting {s}', flush=True)
            with open(B + '/runs/queue.log', 'a') as f:
                f.write(f'skip {s} at {now}\n')
            continue
        p = s.split(':')
        args = [p[0], p[1], int(p[2])] + ([int(p[3])] if len(p) > 3 else [])
        with open(B + '/runs/queue.log', 'a') as f:
            f.write(f'start {s} at {now}\n')
        r = subprocess.run([sys.executable, os.path.abspath(__file__), 'run'] + [str(a) for a in args])
        with open(B + '/runs/queue.log', 'a') as f:
            f.write(f'end {s} rc={r.returncode} at {time.strftime("%T")}\n')
    with open(B + '/runs/queue.log', 'a') as f:
        f.write(f'queue done at {time.strftime("%T")}\n')


if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'setup':
        l_setup()
    elif a[0] == 'seed':
        LOGF = open(B + '/runs/seed-session.log', 'a'); l_seed()
    elif a[0] == 'run':
        l_run(a[1], a[2], int(a[3]), int(a[4]) if len(a) > 4 else None)
    elif a[0] == 'queue':
        l_queue(a[1:])
