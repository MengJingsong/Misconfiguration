#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of maxTasksQueued-takeTaskPermit-taskPermits--autonomous (audit amendments of 2026-10-22).
usage: cluster-run.py all | down | reanalyze          env: MTT_RUN (default run1), MTT_ARMS (default A,B,A2), MTT_STRESS_S
One node (127.0.0.1, JMX 7199), 1 GiB heap, concurrent_writes 2, commitlog_sync batch (5.0 has no window key), native_transport_max_threads 4096,
timeouts raised, receive queue 0B. Each arm is a fresh node lifetime on wiped directories (B3e step 3):
  A   in-flight limits 512 MiB, stress 2000 threads        B   in-flight limits 16 MiB (positive control), 2000 threads
  A2  in-flight limits 512 MiB, stress 256 threads (second load level)
Stress: write, 32 KiB values, 4000 partitions overwritten (disk bound), cl=ONE, no-warmup, duration MTT_STRESS_S (default 360 s);
the statistics window is t = 60 s .. end of stress. Samplers: tpstats every 5 s (MutationStage and Native-Transport-Requests
Active/Pending/Completed, dropped MUTATION), heap after GC every 15 s (jcmd GC.run + GC.heap_info + tablestats memtable size),
JMX every 1 s (RequestsSize, heap used, MutationStage Active/Pending/MaxTasksQueued, NTR Pending), class histogram at t = 180 s.
Output ~/stage4-logs/mtt/<run>/cluster/. Every process this script starts is stopped on any exit.
"""
import atexit, json, os, re, signal, statistics, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-mtt')
HARNESS = os.path.dirname(os.path.abspath(__file__))
MTTN = os.environ.get('MTTN', HOME + '/stage4-mtt')
N = MTTN + '/node1'
RUN = os.environ.get('MTT_RUN', 'run1')
ADDR, JMXP = '127.0.0.1', 7199
STRESS_S = int(os.environ.get('MTT_STRESS_S', 360))
WARM_S = int(os.environ.get('MTT_WARM_S', 60))
HISTO_AT = int(os.environ.get('MTT_HISTO_AT', 180))
ARMS = os.environ.get('MTT_ARMS', 'A,B,A2').split(',')
MIB, KIB = 1 << 20, 1 << 10
MODE = sys.argv[1] if len(sys.argv) > 1 else ''
if MODE not in ('all', 'down', 'reanalyze'):
    sys.exit(__doc__)
LOGS = f'{HOME}/stage4-logs/mtt/{RUN}/cluster'
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
SUMMARY = open(LOGS + ('/reanalysis.txt' if MODE == 'reanalyze' else '/summary.txt'), 'a' if MODE == 'down' else 'w')
EXPECT = {'yes': 0, 'no': 0}
PHASES = []
CHILDREN = []
STATE = {'run': 'setup', 'pid': None, 'lifetime': 0}
ARM = {  # arm -> (in-flight MiB, stress threads)
    'A': (512, 2000), 'B': (16, 2000), 'A2': (512, 256)}
COMMON = ['concurrent_writes=2', 'native_transport_max_threads=4096', 'native_transport_receive_queue_capacity=0B',
          'write_request_timeout=120000ms', 'native_transport_timeout=120s',
          'commitlog_sync=batch', '-commitlog_sync_period']


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, file=sys.stderr)
    SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush(); log(s)


def now_ms():
    return int(time.time() * 1000)


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
        SESSION.write(out[-4000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed rc={r.returncode}: {cmd}\n{out[-1200:]}')
    return r.returncode, out


def expect(desc, cond):
    EXPECT['yes' if cond else 'no'] += 1
    note(f'EXPECTED: {desc} — {"yes" if cond else "NO (recorded; the AI judges it in the results file)"}')
    return cond


def pid_alive():
    pid = STATE['pid']
    if pid is None:
        return None
    try:
        return pid if 'CassandraDaemon' in open(f'/proc/{pid}/cmdline').read() else None
    except OSError:
        return None


def my_daemons():
    _, out = sh("ps -eo pid,args | grep -E '^ *[0-9]+ [^ ]*java .*org\\.apache\\.cassandra\\.service\\.CassandraDaemon' || true", check=False, quiet=True)
    return [l for l in out.splitlines() if N + '/' in l]


def nodetool(cmd, timeout=180, check=False, quiet=True):
    return sh(f'bin/nodetool -h 127.0.0.1 -p {JMXP} {cmd}', timeout=timeout, check=check, quiet=quiet)


def cql(stmt, timeout=120):
    return sh(f'bin/cqlsh {ADDR} -e "{stmt}"', timeout=timeout, check=False)


def stop_node(wait_s=180):
    if pid_alive() is None:
        return
    nodetool('stopdaemon', timeout=wait_s, quiet=False)
    for _ in range(wait_s):
        if pid_alive() is None:
            return
        time.sleep(1)
    pid = pid_alive()
    if pid is not None:
        note(f'node did not stop within {wait_s} s; kill -9 {pid}')
        os.kill(pid, signal.SIGKILL)
        time.sleep(3)


def kill_children():
    for p in CHILDREN:
        if p.poll() is None:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except OSError:
                p.kill()


def cleanup():
    kill_children()
    stop_node(60)


atexit.register(cleanup)


def fail(msg):
    note('FAIL: ' + msg)
    save()
    sys.exit(1)


def free_gb():
    st = os.statvfs(HOME)
    return st.f_bavail * st.f_frsize / 1e9


def save():
    json.dump(PHASES, open(LOGS + '/phases.json', 'w'), indent=1)


def start_node(extra_yaml):
    if pid_alive() is not None or my_daemons():
        fail('a node of this harness is already running')
    for d in ('data', 'commitlog', 'hints', 'saved_caches', 'cdc'):
        sh(f'rm -rf {N}/{d}', check=False, quiet=True)
    _, y = sh(f'bash {HARNESS}/make-node-yaml.sh ' + ' '.join(extra_yaml), env=dict(os.environ, CASSANDRA_HOME=C, MTTN=MTTN))
    note(y.strip().splitlines()[-1][:1800])
    env = dict(os.environ, CASSANDRA_CONF=N + '/conf', CASSANDRA_LOG_DIR=N + '/logs')
    for k in ('JVM_EXTRA_OPTS', 'MAX_HEAP_SIZE', 'HEAP_NEWSIZE'):
        env.pop(k, None)
    STATE['lifetime'] += 1
    try:
        os.remove(N + '/cassandra.pid')
    except OSError:
        pass
    sh(f': > {N}/logs/system.log; : > {N}/logs/debug.log', check=False, quiet=True)
    note(f'start lifetime {STATE["lifetime"]} ({STATE["run"]}): yaml {extra_yaml}')
    sh(f'ulimit -n 100000; bin/cassandra -p {N}/cassandra.pid > {N}/stdout-{STATE["lifetime"]}.txt 2>&1', env=env)
    for _ in range(30):
        time.sleep(1)
        try:
            STATE['pid'] = int(open(N + '/cassandra.pid').read().strip())
        except (OSError, ValueError):
            continue
        if pid_alive():
            break
    if not pid_alive():
        fail('node did not start; see stdout')
    t0 = time.time()
    while time.time() - t0 < 420:
        if pid_alive() is None:
            fail('node died during start')
        _, st = nodetool('status')
        _, sb = nodetool('statusbinary')
        if re.search(r'^UN\s+' + re.escape(ADDR) + r'\s', st, re.M) and re.search(r'^running\s*$', sb, re.M):
            log(f'UN and serving after {time.time() - t0:.0f} s')
            _, flags = sh(f'jcmd {STATE["pid"]} VM.flags', check=False, quiet=True)
            mh = re.search(r'-XX:MaxHeapSize=(\d+)', flags)
            note(f'jvm: MaxHeapSize {int(mh.group(1)) / MIB:.0f} MiB; G1 {"-XX:+UseG1GC" in flags}')
            return
        time.sleep(3)
    fail('node not UN within 420 s')


BEANS = {
    'req_size': ('org.apache.cassandra.metrics:type=Client,name=RequestsSize', 'Value'),
    'heap': ('java.lang:type=Memory', 'HeapMemoryUsage'),
    'ms_active': ('org.apache.cassandra.metrics:type=ThreadPools,path=request,scope=MutationStage,name=ActiveTasks', 'Value'),
    'ms_pending': ('org.apache.cassandra.metrics:type=ThreadPools,path=request,scope=MutationStage,name=PendingTasks', 'Value'),
    'ms_max': ('org.apache.cassandra.metrics:type=ThreadPools,path=request,scope=MutationStage,name=MaxTasksQueued', 'Value'),
    'ntr_pending': ('org.apache.cassandra.metrics:type=ThreadPools,path=transport,scope=Native-Transport-Requests,name=PendingTasks', 'Value'),
    'ntr_active': ('org.apache.cassandra.metrics:type=ThreadPools,path=transport,scope=Native-Transport-Requests,name=ActiveTasks', 'Value'),
}


class Samplers:
    def __init__(self):
        self.stop = threading.Event()
        self.tp = open(LOGS + '/samples-tp.csv', 'a')
        self.hp = open(LOGS + '/samples-heap.csv', 'a')
        if self.tp.tell() == 0:
            self.tp.write('t_ms,run,ms_active,ms_pending,ms_completed,ntr_active,ntr_pending,dropped_mutation,du_data,du_commitlog\n')
        if self.hp.tell() == 0:
            self.hp.write('t_ms,run,heap_used_after_gc,heap_total,memtable_data_size,memtable_cells\n')
        self.last_tp = {}
        self.logged = False
        self.threads = [threading.Thread(target=self.loop_tp, daemon=True), threading.Thread(target=self.loop_heap, daemon=True)]
        self.stopf = LOGS + f'/jmx.stop.{STATE["lifetime"]}'
        try:
            os.remove(self.stopf)
        except OSError:
            pass
        args = []
        for b, a in BEANS.values():
            args += [b, a]
        self.jout = open(LOGS + f'/samples-jmx-{STATE["lifetime"]}.csv', 'w')
        self.jout.write('t_ms,' + ','.join(BEANS) + '\n'); self.jout.flush()
        self.jp = subprocess.Popen(['java', '-cp', MTTN + '/jmx', 'Jmx', str(JMXP), 'poll', '1000', '100000', self.stopf] + args,
                                   stdout=self.jout, stderr=subprocess.DEVNULL, start_new_session=True)
        CHILDREN.append(self.jp)
        for t in self.threads:
            t.start()

    def tpstats(self):
        _, out = nodetool('tpstats', timeout=60)
        if not self.logged:
            self.logged = True
            log('tpstats (first of this lifetime):\n' + out[-3500:])
        m = re.search(r'^MutationStage\s+(\d+)\s+(\d+)\s+(\d+)', out, re.M)
        n = re.search(r'^Native-Transport-Requests\s+(\d+)\s+(\d+)\s+(\d+)', out, re.M)
        d = re.search(r'^MUTATION(?:_REQ)?\s+(\d+)', out, re.M)
        if not m:
            return None
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)), int(n.group(1)) if n else -1, int(n.group(2)) if n else -1,
                int(d.group(1)) if d else -1)

    def du(self, d):
        _, out = sh(f'du -sb {N}/{d}', check=False, quiet=True, timeout=60)
        try:
            return int(out.split()[0])
        except (IndexError, ValueError):
            return -1

    def loop_tp(self):
        while not self.stop.is_set():
            t = now_ms()
            r = self.tpstats()
            if r is not None:
                self.last_tp = {'t': t, 'pending': r[1]}
                self.tp.write(f'{t},{STATE["run"]},{r[0]},{r[1]},{r[2]},{r[3]},{r[4]},{r[5]},{self.du("data")},{self.du("commitlog")}\n')
                self.tp.flush()
            self.stop.wait(max(0.0, 5 - (now_ms() - t) / 1000))

    def heap_after_gc(self):
        pid = STATE['pid']
        sh(f'jcmd {pid} GC.run', check=False, quiet=True, timeout=120)
        _, out = sh(f'jcmd {pid} GC.heap_info', check=False, quiet=True, timeout=60)
        m = re.search(r'garbage-first heap\s+total (\d+)K, used (\d+)K', out)
        return (int(m.group(2)) * 1024, int(m.group(1)) * 1024) if m else (-1, -1)

    def memtable(self):
        _, out = nodetool('tablestats keyspace1.standard1', timeout=60)
        a = re.search(r'Memtable data size: (\d+)', out)
        b = re.search(r'Memtable cell count: (\d+)', out)
        return (int(a.group(1)) if a else -1), (int(b.group(1)) if b else -1)

    def loop_heap(self):
        while not self.stop.is_set():
            t = now_ms()
            used, total = self.heap_after_gc()
            md, mc = self.memtable()
            self.hp.write(f'{t},{STATE["run"]},{used},{total},{md},{mc}\n'); self.hp.flush()
            self.stop.wait(max(0.0, 15 - (now_ms() - t) / 1000))

    def close(self):
        self.stop.set()
        for t in self.threads:
            t.join(timeout=200)
        open(self.stopf, 'w').close()
        try:
            self.jp.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.jp.kill()
        self.jout.close(); self.tp.close(); self.hp.close()


def stress(label, seconds, threads, rows=None):
    cmd = ('tools/bin/cassandra-stress write ' + (f'n={rows} ' if rows else f'duration={seconds}s ') +
           "cl=ONE no-warmup -col 'n=FIXED(1)' 'size=FIXED(32768)' " +
           ("" if rows else "-pop 'dist=UNIFORM(1..4000)' ") +
           f'-rate threads={threads} -errors ignore retries=0 -mode native cql3 connectionsPerHost=16 -node {ADDR} -log file={LOGS}/stress-{label}.log')
    log('+ (background) ' + cmd)
    out = open(f'{LOGS}/stress-{label}.out', 'w')
    p = subprocess.Popen(cmd, shell=True, cwd=C, stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
    CHILDREN.append(p)
    return p, cmd


def stress_result(label):
    try:
        txt = open(f'{LOGS}/stress-{label}.out', errors='replace').read()
    except OSError:
        return {}
    res = {}
    for k, pat in (('op_rate', r'^Op rate\s*:\s*([\d,]+) op/s'), ('total_partitions', r'^Total partitions\s*:\s*([\d,]+)'),
                   ('total_errors', r'^Total errors\s*:\s*([\d,]+)'), ('elapsed', r'^Total operation time\s*:\s*(\S+)')):
        m = re.search(pat, txt, re.M)
        if m:
            res[k] = m.group(1).replace(',', '') if k != 'elapsed' else m.group(1)
    res['write_timeouts_logged'] = txt.count('WriteTimeout')
    res['exceptions_logged'] = len(re.findall(r'Exception', txt))
    return res


def run_arm(label):
    inflight, threads = ARM[label]
    STATE['run'] = label
    if free_gb() < 15:
        fail(f'{free_gb():.1f} GB free < 15 GB before {label}')
    extra = COMMON + [f'native_transport_max_request_data_in_flight={inflight}MiB',
                      f'native_transport_max_request_data_in_flight_per_ip={inflight}MiB']
    start_node(extra)
    cql("CREATE KEYSPACE IF NOT EXISTS keyspace1 WITH replication={'class':'SimpleStrategy','replication_factor':1};")
    p, _ = stress(label + '-schema', 0, 4, rows=100)
    p.wait(timeout=300)
    note(f'{label} schema/table: 100-row stress write {stress_result(label + "-schema")}')
    nodetool('flush keyspace1', quiet=False)
    _, gc = nodetool('getconcurrency MutationStage', quiet=False)
    expect(f'{label} concurrent_writes = 2 (getconcurrency: {gc.strip().splitlines()[-1] if gc.strip() else "?"})',
           bool(re.search(r'^MutationStage\s+\d+\s+2\s*$', gc, re.M)))
    sm = Samplers()
    b0 = now_ms()
    time.sleep(47)
    b1 = now_ms()
    sh(f'jcmd {STATE["pid"]} GC.class_histogram > {LOGS}/histo-{label}-baseline.txt', check=False, quiet=True, timeout=120)
    p, cmd = stress(label, STRESS_S, threads)
    ts = now_ms()
    note(f'{label} stress started ({threads} threads, in-flight {inflight} MiB, {STRESS_S} s): {cmd}; free {free_gb():.1f} GB')
    histo_done = False
    while p.poll() is None:
        time.sleep(2)
        if not histo_done and now_ms() >= ts + HISTO_AT * 1000:
            histo_done = True
            sh(f'jcmd {STATE["pid"]} GC.class_histogram > {LOGS}/histo-{label}-peak.txt', check=False, quiet=True, timeout=180)
            note(f'{label} class histogram taken at +{(now_ms() - ts) / 1000:.0f} s (MutationStage Pending then {sm.last_tp.get("pending")})')
        if free_gb() < 8:
            note(f'{label}: free space {free_gb():.1f} GB < 8 GB, stress stopped early')
            os.killpg(p.pid, signal.SIGTERM)
            break
        if now_ms() > ts + (STRESS_S + 240) * 1000:
            note(f'{label}: stress overran by 240 s, stopped')
            os.killpg(p.pid, signal.SIGTERM)
            break
    te = now_ms()
    time.sleep(20)
    sm.close()
    phase(label, base=[b0, b1], stress_start=ts, stress_end=te, end=now_ms(), threads=threads, inflight_mib=inflight,
          stress=stress_result(label), lifetime=STATE['lifetime'])
    note(f'{label} stress: {stress_result(label)}')
    stop_node()
    for f in ('system.log', 'debug.log', 'gc.log'):
        pth = f'{N}/logs/{f}'
        if os.path.exists(pth):
            sh(f'cp {pth} {LOGS}/{f.replace(".log", "")}-{label}.log', check=False, quiet=True)
    sh(f'du -sh {N}/data {N}/commitlog', check=False)


def phase(run, **kw):
    kw['run'] = run
    PHASES.append(kw)
    save()


# ---------------------------------------------------------------- analysis

def rows(path):
    out = []
    try:
        lines = open(path).read().splitlines()
    except OSError:
        return out
    hdr = lines[0].split(',')
    for l in lines[1:]:
        v = l.split(',')
        if len(v) == len(hdr):
            out.append(dict(zip(hdr, v)))
    return out


def jmx_rows(lifetime):
    out = []
    for l in open(f'{LOGS}/samples-jmx-{lifetime}.csv').read().splitlines()[1:]:
        v = l.split(',')
        try:
            out.append({'t': int(v[0]), **{k: float(x) for k, x in zip(BEANS, v[1:])}})
        except (ValueError, IndexError):
            pass
    return out


def histo_val(path, cls):
    try:
        for l in open(path, errors='replace'):
            p = l.split()
            if len(p) >= 4 and p[3] == cls:
                return int(p[1]), int(p[2])
    except OSError:
        pass
    return None


def analyze():
    tp = rows(LOGS + '/samples-tp.csv')
    hp = rows(LOGS + '/samples-heap.csv')
    stats = {}
    for ph in PHASES:
        r = ph['run']
        a, b = ph['stress_start'] + WARM_S * 1000, ph['stress_end']
        tpw = [x for x in tp if x['run'] == r and a <= int(x['t_ms']) <= b]
        hpw = [x for x in hp if x['run'] == r and a <= int(x['t_ms']) <= b]
        base = [x for x in hp if x['run'] == r and ph['base'][0] <= int(x['t_ms']) <= ph['base'][1] + 5000]
        jr = [x for x in jmx_rows(ph['lifetime']) if a <= x['t'] <= b]
        pend = [int(x['ms_pending']) for x in tpw]
        jp = [x['ms_pending'] for x in jr]
        hq = [int(x['heap_used_after_gc']) - int(x['memtable_data_size']) for x in hpw if int(x['heap_used_after_gc']) > 0]
        hb = [int(x['heap_used_after_gc']) - int(x['memtable_data_size']) for x in base if int(x['heap_used_after_gc']) > 0]
        s = {'n_tp': len(pend), 'n_heap': len(hq), 'n_jmx': len(jr)}
        if pend:
            s['Pn'] = statistics.median(pend); s['Pmax'] = max(pend); s['Pmin'] = min(pend)
            s['Pn_jmx'] = statistics.median(jp) if jp else None
            s['Pmax_jmx'] = max(jp) if jp else None
            s['NTRpend_median'] = statistics.median(int(x['ntr_pending']) for x in tpw)
            s['active_max'] = max(int(x['ms_active']) for x in tpw)
            s['dropped_delta'] = int(tpw[-1]['dropped_mutation']) - int(tpw[0]['dropped_mutation'])
            s['completed_delta'] = int(tpw[-1]['ms_completed']) - int(tpw[0]['ms_completed'])
            s['rate_per_s'] = s['completed_delta'] / max(1, (int(tpw[-1]['t_ms']) - int(tpw[0]['t_ms'])) / 1000)
            half = len(pend) // 2
            s['P_first_half_median'] = statistics.median(pend[:half]); s['P_second_half_median'] = statistics.median(pend[half:])
        if hq and hb:
            s['Hn_MiB'] = (statistics.median(hq) - statistics.median(hb)) / MIB
            s['H_base_MiB'] = statistics.median(hb) / MIB
            s['H_raw_median_MiB'] = statistics.median(int(x['heap_used_after_gc']) for x in hpw) / MIB
        if jr:
            s['req_size_max_MiB'] = max(x['req_size'] for x in jr) / MIB
            s['req_size_mean_MiB'] = statistics.mean(x['req_size'] for x in jr) / MIB
            s['maxq_all_const'] = all(x['ms_max'] == 2147483647 for x in jr)
            s['heap_used_max_MiB'] = max(x['heap'] for x in jr) / MIB
        stats[r] = s
        note(f'{r}: ' + json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in s.items()}))
        hv = histo_val(f'{LOGS}/histo-{r}-peak.txt', 'java.util.concurrent.ConcurrentLinkedQueue$Node')
        hb2 = histo_val(f'{LOGS}/histo-{r}-peak.txt', '[B')
        hm = histo_val(f'{LOGS}/histo-{r}-peak.txt', 'org.apache.cassandra.db.Mutation')
        bb = histo_val(f'{LOGS}/histo-{r}-baseline.txt', '[B')
        note(f'{r} histogram at peak: CLQ$Node {hv}, byte[] {hb2} (baseline {bb}), db.Mutation {hm}')
    return stats


def finish():
    stats = analyze()
    A, B, A2 = stats.get('A'), stats.get('B'), stats.get('A2')
    for r, s in stats.items():
        expect(f'{r} MaxTasksQueued = 2147483647 at every 1-s JMX sample ({s.get("n_jmx")} samples)', bool(s.get('maxq_all_const')) and s.get('n_jmx', 0) > 100)
        expect(f'{r} MutationStage Active max <= 2 (concurrent_writes 2)', s.get('active_max', 99) <= 2)
        expect(f'{r} statistics window has >= 40 tpstats samples and >= 12 heap samples', s.get('n_tp', 0) >= 40 and s.get('n_heap', 0) >= 12)
    if A and A2:
        expect(f'A Pn >= 1000 (sub-prediction; Pn(A) = {A.get("Pn")})', A.get('Pn', 0) >= 1000)
        expect(f'A Pmax <= 2200 (= 1.1 x threads; Pmax = {A.get("Pmax")})', A.get('Pmax', 1e9) <= 2200)
        expect(f'A2 Pn in [128, 282] (0.5-1.1 x 256; Pn = {A2.get("Pn")})', 128 <= A2.get('Pn', 0) <= 282)
        expect(f'Pn(A) >= 2 x Pn(A2) ({A.get("Pn")} vs {A2.get("Pn")})', A.get('Pn', 0) >= 2 * A2.get('Pn', 1e9))
    if A and B:
        expect(f'B Pmax <= 563 (1.1 x 16 MiB / 32 KiB; Pmax = {B.get("Pmax")})', B.get('Pmax', 1e9) <= 563)
        expect(f'Pn(B) <= 0.5 x Pn(A) ({B.get("Pn")} vs {A.get("Pn")})', B.get('Pn', 1e9) <= 0.5 * A.get('Pn', 0))
        expect(f'B RequestsSize max >= 14.4 MiB (90 % of 16 MiB; {B.get("req_size_max_MiB")})', B.get('req_size_max_MiB', 0) >= 14.4)
        expect(f'B RequestsSize max <= 16.5 MiB ({B.get("req_size_max_MiB")})', B.get('req_size_max_MiB', 99) <= 16.5)
        expect(f'A RequestsSize max < 512 MiB ({A.get("req_size_max_MiB")})', A.get('req_size_max_MiB', 1e9) < 512)
        if 'Hn_MiB' in A and 'Hn_MiB' in B:
            need = 0.5 * (A['Pn'] - B['Pn']) * 32 * KIB / MIB
            expect(f'Hn(A) - Hn(B) >= 0.5 x (Pn(A) - Pn(B)) x 32 KiB: {A["Hn_MiB"] - B["Hn_MiB"]:.1f} MiB vs {need:.1f} MiB', A['Hn_MiB'] - B['Hn_MiB'] >= need)
    if A and A2 and 'Hn_MiB' in A and 'Hn_MiB' in A2:
        need = 0.5 * (A['Pn'] - A2['Pn']) * 32 * KIB / MIB
        expect(f'Hn(A) - Hn(A2) >= 0.5 x (Pn(A) - Pn(A2)) x 32 KiB: {A["Hn_MiB"] - A2["Hn_MiB"]:.1f} MiB vs {need:.1f} MiB', A['Hn_MiB'] - A2['Hn_MiB'] >= need)
    for r, s in stats.items():
        if 'Hn_MiB' in s and s.get('Pn'):
            per = s['Hn_MiB'] * MIB / s['Pn'] / KIB
            expect(f'{r} heap per queued mutation >= 32 KiB, the payload (reported {per:.1f} KiB)', per >= 32)
    for r, s in stats.items():
        if s.get('P_first_half_median') is not None:
            note(f'{r} drift: Pending median first half {s["P_first_half_median"]}, second half {s["P_second_half_median"]}')
    note(f'EXPECTED summary: {EXPECT["yes"]} yes, {EXPECT["no"]} NO')


if MODE == 'down':
    stop_node(120)
    left = my_daemons()
    note(f'down: daemons of this harness left: {len(left)}')
    sys.exit(0)

if MODE == 'reanalyze':
    PHASES.extend(json.load(open(LOGS + '/phases.json')))
    finish()
    sys.exit(0)

note(f'cluster-run {time.strftime("%F %T")} host {os.uname().nodename} arms {ARMS} stress {STRESS_S} s warm {WARM_S} s clone {C}')
for arm in ARMS:
    run_arm(arm)
finish()
note('left running: ' + str(len(my_daemons())))
