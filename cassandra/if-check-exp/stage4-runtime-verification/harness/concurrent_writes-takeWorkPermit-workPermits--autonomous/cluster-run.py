#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of concurrent_writes-takeWorkPermit-workPermits--autonomous (audit amendments R1-R5,
2026-10-21). usage: cluster-run.py all | down
  all   one node (127.0.0.11, JMX 7211; environment deviation E1), run in this order, each in a fresh node lifetime (R2):
        R0   concurrent_writes 32; keyspace1 RF 1 and the stress table made by a 100-row stress write; 3 baseline
             samples; stress unthrottled 120 s (B3c with R1's no-warmup); at t = 10 s `nodetool setconcurrency
             MutationStage 0` (read back with getconcurrency); at t = 130 s back to 32 (read back); sampling until
             Pending = 0, then 60 s more (B3e step 2). Guard: if a post-GC heap sample exceeds 1.8 GiB the pool is
             restored at once (B4: restore even if stress fails) and the event is noted.
        R32, R2, R128   concurrent_writes 32 / 2 / 128 in the yaml; stress throttled 400/s for 120 s (B3e steps 3-4).
        PC0  concurrent_writes 32, in-flight limits 256 MiB (B3a); stress unthrottled 60 s (R3, the PC reference).
        PC   the same with native_transport_max_request_data_in_flight_per_ip 4MiB (B3b, B3e step 5).
        Between lifetimes (R2): TRUNCATE keyspace1.standard1 and clearsnapshot on the running node, then stop it.
  down  stop the node of this harness.
  reanalyze  re-run the analysis on phases.json and the sample files of SEP_RUN (writes reanalysis.txt, not summary.txt).
Samplers (B3d), all into ~/stage4-logs/sep/<run>/cluster/: samples-tp.csv every 5 s (nodetool tpstats: MutationStage
Active / Pending / Completed, dropped MUTATION; du -sb of data, commitlog, hints); samples-heap.csv every 15 s (jcmd
GC.run then GC.heap_info "used"; nodetool tablestats keyspace1.standard1 memtable data size and cell count);
samples-jmx.csv every 1 s from one JMX connection (RequestsSize = org.apache.cassandra.metrics:type=Client,name=
RequestsSize Value, the same gauge B3d reads with sjk; heap used without GC; MutationStage ActiveTasks / PendingTasks
gauges). phases.json holds each run's epoch-ms boundaries. summary.txt has EXPECTED lines (B3f); a NO is recorded and
the run goes on. Exit 1: a set-up check failed; the node is stopped on any exit.
Environment: SEP_RUN (default run1), CASSANDRA_HOME (default ~/cassandra-sep), SEP_R0_S (pool-0 window, default 120),
SEP_STEADY_S (default 120), SEP_PC_S (default 60), SEP_MIN_FREE_GB (default 12)."""
import json, os, re, signal, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-sep')
HARNESS = os.path.dirname(os.path.abspath(__file__))
SEPN = os.environ.get('SEPN', HOME + '/stage4-sep')
N = SEPN + '/node1'
RUN = os.environ.get('SEP_RUN', 'run1')
ADDR, JMXP = '127.0.0.11', 7211
R0_S = int(os.environ.get('SEP_R0_S', 120))
STEADY_S = int(os.environ.get('SEP_STEADY_S', 120))
PC_S = int(os.environ.get('SEP_PC_S', 60))
MIN_FREE = float(os.environ.get('SEP_MIN_FREE_GB', 12))
MIB, GIB = 1 << 20, 1 << 30
JMXCP = SEPN + '/jmx'
MODE = sys.argv[1] if len(sys.argv) > 1 else ''
if MODE not in ('all', 'down', 'reanalyze'):
    sys.exit(__doc__)
LOGS = f'{HOME}/stage4-logs/sep/{RUN}/cluster'
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
SUMMARY = open(LOGS + ('/reanalysis.txt' if MODE == 'reanalyze' else '/summary.txt'), 'a' if MODE == 'down' else 'w')
EXPECT = {'yes': 0, 'no': 0}
PHASES = []
CHILDREN = []
STATE = {'run': 'setup', 'pid': None, 'lifetime': 0}


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
    """java CassandraDaemon processes whose arguments name this harness's node directory (never another session's)."""
    _, out = sh("ps -eo pid,args | grep -E '^ *[0-9]+ [^ ]*java .*org\\.apache\\.cassandra\\.service\\.CassandraDaemon' || true",
                check=False, quiet=True)
    return [l for l in out.splitlines() if N + '/' in l or f'-Dcassandra.jmx.local.port={JMXP}' in l]


def nodetool(cmd, timeout=180, check=False, quiet=True):
    return sh(f'bin/nodetool -h 127.0.0.1 -p {JMXP} {cmd}', timeout=timeout, check=check, quiet=quiet)


def cql(stmt, timeout=120):
    return sh(f'bin/cqlsh {ADDR} -e "{stmt}"', timeout=timeout, check=False)


def stop_node(wait_s=120):
    pid0 = pid_alive()
    if pid0 is None:
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


def fail(msg):
    note('FAIL: ' + msg)
    kill_children()
    stop_node()
    save()
    sys.exit(1)


def free_gb():
    st = os.statvfs(HOME)
    return st.f_bavail * st.f_frsize / 1e9


def start_node(extra_yaml):
    if pid_alive() is not None or my_daemons():
        fail('a node of this harness is already running')
    _, y = sh(f'bash {HARNESS}/make-node-yaml.sh ' + ' '.join(extra_yaml), env=dict(os.environ, CASSANDRA_HOME=C, SEPN=SEPN))
    note(y.strip().splitlines()[-1][:1500])
    env = dict(os.environ, CASSANDRA_CONF=N + '/conf', CASSANDRA_LOG_DIR=N + '/logs', MAX_HEAP_SIZE='2G', HEAP_NEWSIZE='400M')
    env.pop('JVM_EXTRA_OPTS', None)
    STATE['lifetime'] += 1
    try:
        os.remove(N + '/cassandra.pid')
    except OSError:
        pass
    note(f'start lifetime {STATE["lifetime"]} ({STATE["run"]}): MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M, yaml {extra_yaml}')
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
    while time.time() - t0 < 300:
        if pid_alive() is None:
            fail('node died during start')
        _, st = nodetool('status')
        _, sb = nodetool('statusbinary')
        if re.search(r'^UN\s+' + re.escape(ADDR) + r'\s', st, re.M) and re.search(r'^running\s*$', sb, re.M):
            log(f'UN and serving after {time.time() - t0:.0f} s')
            _, cmdline = sh(f'tr "\\0" " " < /proc/{STATE["pid"]}/cmdline', check=False, quiet=True)
            note('jvm: ' + ' '.join(sorted(set(x for x in cmdline.split() if x.startswith(('-Xmx', '-Xms', '-Xmn', '-XX:+UseG1GC', '-XX:HeapDumpPath', '-Dcassandra.jmx.local.port'))))))
            return
        time.sleep(3)
    fail('node not UN within 300 s')


def getconcurrency():
    _, out = nodetool('getconcurrency MutationStage', quiet=False)
    m = re.search(r'^MutationStage\s+(-?\d+)\s+(-?\d+)\s*$', out, re.M)
    return int(m.group(2)) if m else None


# ---------------------------------------------------------------- samplers

class Samplers:
    def __init__(self):
        self.stop = threading.Event()
        self.tp = open(LOGS + '/samples-tp.csv', 'a')
        self.hp = open(LOGS + '/samples-heap.csv', 'a')
        if self.tp.tell() == 0:
            self.tp.write('t_ms,run,active,pending,completed,dropped_mutation,du_data,du_commitlog,du_hints\n')
        if self.hp.tell() == 0:
            self.hp.write('t_ms,run,heap_used_after_gc,heap_total,memtable_data_size,memtable_cells\n')
        self.last_tp = {}
        self.logged_tp = False
        self.threads = [threading.Thread(target=self.loop_tp, daemon=True), threading.Thread(target=self.loop_heap, daemon=True)]
        stopf = LOGS + f'/jmx.stop.{STATE["lifetime"]}'
        try:
            os.remove(stopf)
        except OSError:
            pass
        self.stopf = stopf
        beans = ['org.apache.cassandra.metrics:type=Client,name=RequestsSize', 'Value',
                 'java.lang:type=Memory', 'HeapMemoryUsage',
                 'org.apache.cassandra.metrics:type=ThreadPools,path=request,scope=MutationStage,name=ActiveTasks', 'Value',
                 'org.apache.cassandra.metrics:type=ThreadPools,path=request,scope=MutationStage,name=PendingTasks', 'Value']
        self.jout = open(LOGS + f'/samples-jmx-{STATE["lifetime"]}.csv', 'w')
        self.jout.write('t_ms,requests_size,heap_used,ms_active,ms_pending\n'); self.jout.flush()
        self.jp = subprocess.Popen(['java', '-cp', JMXCP, 'Jmx', str(JMXP), 'poll', '1000', '100000', stopf] + beans,
                                   stdout=self.jout, stderr=subprocess.DEVNULL, start_new_session=True)
        CHILDREN.append(self.jp)
        for t in self.threads:
            t.start()

    def tpstats(self):
        _, out = nodetool('tpstats', timeout=60)
        m = re.search(r'^MutationStage\s+(\d+)\s+(\d+)\s+(\d+)', out, re.M)
        d = re.search(r'^MUTATION(?:_REQ)?\s+(\d+)', out, re.M)
        if not self.logged_tp:
            self.logged_tp = True
            log('tpstats (first of this lifetime):\n' + out[-3000:])
        if not m:
            return None
        return int(m.group(1)), int(m.group(2)), int(m.group(3)), int(d.group(1)) if d else -1

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
                self.last_tp = {'t': t, 'active': r[0], 'pending': r[1], 'completed': r[2], 'dropped': r[3]}
                self.tp.write(f'{t},{STATE["run"]},{r[0]},{r[1]},{r[2]},{r[3]},{self.du("data")},{self.du("commitlog")},{self.du("hints")}\n')
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
            self.last_heap = used
            self.hp.write(f'{t},{STATE["run"]},{used},{total},{md},{mc}\n'); self.hp.flush()
            if used > 1.8 * GIB and STATE['run'] == 'R0' and STATE.get('pool0'):
                note(f'GUARD: post-GC heap {used / MIB:.0f} MiB > 1.8 GiB during R0: restoring MutationStage to 32 now')
                nodetool('setconcurrency MutationStage 32', quiet=False)
                STATE['pool0'] = False
                STATE['guard'] = t
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


# ---------------------------------------------------------------- runs

def stress(label, seconds, throttle=None, rows=None):
    cmd = (f'tools/bin/cassandra-stress write ' + (f'n={rows} ' if rows else f'duration={seconds}s ') +
           f"cl=ONE no-warmup -col 'n=FIXED(1)' 'size=FIXED(65536)' -rate threads=128" + (f' throttle={throttle}' if throttle else '') +
           f' -errors ignore retries=0 -mode native cql3 -node {ADDR} -log file={LOGS}/stress-{label}.log')
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
    return res


def baseline(sm, n=3):
    t0 = now_ms()
    time.sleep(15 * n + 2)
    return t0, now_ms()


def phase(run, **kw):
    kw['run'] = run
    PHASES.append(kw)
    save()


def save():
    json.dump(PHASES, open(LOGS + '/phases.json', 'w'), indent=1)


def reset_and_stop():
    cql('TRUNCATE keyspace1.standard1;')
    nodetool('clearsnapshot --all', quiet=False)
    stop_node()
    for f in ('system.log', 'debug.log', 'gc.log'):
        p = f'{N}/logs/{f}'
        if os.path.exists(p):
            sh(f'cp {p} {LOGS}/{f.replace(".log", "")}-{STATE["lifetime"]}.log', check=False, quiet=True)


def run_R0():
    STATE['run'] = 'R0'
    start_node(['concurrent_writes=32'])
    cql("CREATE KEYSPACE IF NOT EXISTS keyspace1 WITH replication={'class':'SimpleStrategy','replication_factor':1};")
    p, _ = stress('R0-schema', 0, rows=100)
    p.wait(timeout=300)
    note(f'R0 schema/table: 100-row stress write {stress_result("R0-schema")}')
    nodetool('flush keyspace1', quiet=False)
    expect('R0 getconcurrency MutationStage = 32 at start', getconcurrency() == 32)
    sm = Samplers()
    b0, b1 = baseline(sm)
    # SUPPLEMENTARY (not in B3d): class histograms (live objects, a full GC each) at the baseline and 5 s before the restore
    sh(f'jcmd {STATE["pid"]} GC.class_histogram > {LOGS}/histo-R0-baseline.txt', check=False, quiet=True, timeout=120)
    p, cmd = stress('R0', R0_S)
    ts = now_ms()
    note(f'R0 stress started (unthrottled, {R0_S} s): {cmd}')
    time.sleep(10)
    nodetool('setconcurrency MutationStage 0', quiet=False)
    STATE['pool0'] = True
    t_set0 = now_ms()
    g0 = getconcurrency()
    expect(f'R0 getconcurrency MutationStage = 0 after setconcurrency 0 (read {g0})', g0 == 0)
    histo_done = False
    while now_ms() < ts + (R0_S + 10) * 1000 and STATE.get('pool0'):
        if not histo_done and now_ms() >= ts + (R0_S + 5) * 1000:
            histo_done = True
            sh(f'jcmd {STATE["pid"]} GC.class_histogram > {LOGS}/histo-R0-pool0.txt', check=False, quiet=True, timeout=120)
            note(f'R0 supplementary class histogram taken at +{(now_ms() - ts) / 1000:.0f} s (Pending then {sm.last_tp.get("pending")})')
        time.sleep(1)
    if STATE.get('pool0'):
        nodetool('setconcurrency MutationStage 32', quiet=False)
        STATE['pool0'] = False
    t_set32 = now_ms()
    g32 = getconcurrency()
    expect(f'R0 getconcurrency MutationStage = 32 after restore (read {g32})', g32 == 32)
    t_end_wait = time.time() + 600
    t_zero = None
    while time.time() < t_end_wait:
        lt = sm.last_tp
        if lt.get('t', 0) > t_set32 + 1000 and lt.get('pending') == 0:
            t_zero = lt['t']
            break
        time.sleep(2)
    note(f'R0 Pending back to 0 at +{(t_zero - t_set32) / 1000 if t_zero else -1:.0f} s after the restore')
    if p.poll() is None:
        p.wait(timeout=120)
    time.sleep(60)
    t_end = now_ms()
    sm.close()
    phase('R0', base=[b0, b1], stress_start=ts, set0=t_set0, set32=t_set32, pending_zero=t_zero, end=t_end,
          guard=STATE.get('guard'), stress=stress_result('R0'), lifetime=STATE['lifetime'])
    note(f'R0 stress: {stress_result("R0")}')
    reset_and_stop()


def run_steady(label, extra, seconds, throttle):
    STATE['run'] = label
    if free_gb() < MIN_FREE:
        fail(f'{free_gb():.1f} GB free < {MIN_FREE} GB before {label}')
    start_node(extra)
    cw = int(dict(kv.split('=', 1) for kv in extra)['concurrent_writes'])
    g = getconcurrency()
    expect(f'{label} getconcurrency MutationStage = {cw} (read {g})', g == cw)
    sm = Samplers()
    b0, b1 = baseline(sm)
    p, cmd = stress(label, seconds, throttle=throttle)
    ts = now_ms()
    note(f'{label} stress started: {cmd}; free {free_gb():.1f} GB')
    while p.poll() is None:
        time.sleep(2)
        if free_gb() < MIN_FREE - 4:
            note(f'{label}: free space {free_gb():.1f} GB below {MIN_FREE - 4} GB, stress stopped early')
            os.killpg(p.pid, signal.SIGTERM)
            break
        if now_ms() > ts + (seconds + 300) * 1000:
            note(f'{label}: stress overran by 300 s, stopped')
            os.killpg(p.pid, signal.SIGTERM)
            break
    te = now_ms()
    time.sleep(20)
    sm.close()
    phase(label, base=[b0, b1], stress_start=ts, stress_end=te, end=now_ms(), extra=extra, stress=stress_result(label),
          lifetime=STATE['lifetime'])
    note(f'{label} stress: {stress_result(label)}')
    reset_and_stop()


# ---------------------------------------------------------------- analysis (EXPECTED lines)

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
            out.append({'t': int(v[0]), 'rs': float(v[1]), 'heap': float(v[2]), 'act': float(v[3]), 'pend': float(v[4])})
        except (ValueError, IndexError):
            pass
    return out


def analyze():
    tp = rows(LOGS + '/samples-tp.csv')
    hp = rows(LOGS + '/samples-heap.csv')
    P = {p['run']: p for p in PHASES}
    def win(rs, run, a, b):
        return [r for r in rs if r['run'] == run and a <= int(r['t_ms']) <= b]
    res = {}
    if 'R0' in P:
        p = P['R0']
        base_rows = win(hp, 'R0', *p['base'])
        base = [int(r['heap_used_after_gc']) for r in base_rows]
        bmean = sum(base) / len(base) if base else float('nan')
        # runbook fix D2: the queue's heap = (heap after GC - memtable data size) minus the same at the baseline
        def net(r):
            return int(r['heap_used_after_gc']) - max(0, int(r['memtable_data_size']))
        bnet = sum(net(r) for r in base_rows) / len(base_rows) if base_rows else float('nan')
        pool0_tp = win(tp, 'R0', p['set0'], p['set32'])
        pool0_hp = win(hp, 'R0', p['set0'], p['set32'])
        pend = [int(r['pending']) for r in pool0_tp]
        act = [int(r['active']) for r in pool0_tp]
        maxpend = max(pend) if pend else -1
        last_hp = pool0_hp[-1] if pool0_hp else None
        heap_last = int(last_hp['heap_used_after_gc']) if last_hp else -1
        heap_max = max(int(r['heap_used_after_gc']) for r in pool0_hp) if pool0_hp else -1
        # Pending at the time of a heap sample: the tpstats sample nearest in time (both loops run every 5 / 15 s)
        def pend_near(t):
            c = sorted(pool0_tp, key=lambda r: abs(int(r['t_ms']) - t))
            return int(c[0]['pending']) if c and abs(int(c[0]['t_ms']) - t) <= 2500 else None
        pend_at = pend_near(int(last_hp['t_ms'])) if last_hp else None
        jr = [r for r in jmx_rows(p['lifetime']) if p['set0'] <= r['t'] <= p['set32']]
        rs_max = max(r['rs'] for r in jr) if jr else -1
        rise_raw = heap_max - bmean
        net_rows = [(int(r['t_ms']), net(r)) for r in pool0_hp]
        net_max = max(v for _, v in net_rows) if net_rows else -1
        rise = (net(last_hp) - bnet) if last_hp else -1          # at the last sample of the pool-0 window
        rise_max = net_max - bnet
        slope = None
        if len(net_rows) >= 2:
            (t1, v1), (t2, v2) = net_rows[0], net_rows[-1]
            p1, p2 = pend_near(t1), pend_near(t2)
            if p1 is not None and p2 is not None and p2 > p1:
                slope = (v2 - v1) / (p2 - p1)
        note(f'R0 (D2): baseline heap - memtable {bnet / MIB:.1f} MiB; queue heap at the last pool-0 sample {rise / MIB:.1f} MiB '
             f'(max {rise_max / MIB:.1f}); raw heap rise over the baseline {rise_raw / MIB:.1f} MiB; '
             f'slope within the window {slope / 1024 if slope else float("nan"):.1f} KiB per pending mutation')
        note(f'R0: baseline heap after GC {bmean / MIB:.1f} MiB ({len(base)} samples); pool-0 window {(p["set32"] - p["set0"]) / 1000:.0f} s; '
             f'Active max {max(act) if act else -1} (samples after the first 5 s: {[a for r, a in zip(pool0_tp, act) if int(r["t_ms"]) > p["set0"] + 5000][:3]}...); '
             f'Pending max {maxpend}; heap after GC max {heap_max / MIB:.1f} MiB (raw rise {rise_raw / MIB:.1f} MiB), last {heap_last / MIB:.1f} MiB with Pending {pend_at}; RequestsSize max {rs_max / MIB:.2f} MiB')
        late_act = [a for r, a in zip(pool0_tp, act) if int(r['t_ms']) > p['set0'] + 5000]
        expect('R0: MutationStage Active = 0 at every tpstats sample of the pool-0 window after its first 5 s', late_act and max(late_act) == 0)
        expect(f'R0: Pending rises to ≈ 7700 (±30 %: 5390–10010) by the restore (max {maxpend})', 5390 <= maxpend <= 10010)
        mono = all(b >= a for a, b in zip(pend, pend[1:]))
        expect('R0: Pending never falls during the pool-0 window (no queue bound, no rejection)', mono)
        if pend_at:
            exp = pend_at * 65 * 1024
            expect(f'R0: queue heap {rise / MIB:.1f} MiB ≈ Pending × 65 KiB = {exp / MIB:.1f} MiB (±30 %)', 0.7 * exp <= rise <= 1.3 * exp)
        expect(f'R0: queue heap ≈ 480 MiB (±30 %: 336–624) (read {rise / MIB:.1f})', 336 * MIB <= rise <= 624 * MIB)
        expect(f'R0: RequestsSize ≤ 8 MiB throughout the pool-0 window (max {rs_max / MIB:.2f} MiB), below the 256 MiB cap', 0 <= rs_max <= 8 * MIB)
        expect(f'R0: queue heap {rise / MIB:.1f} MiB is above the 256 MiB native in-flight cap and > 400 MiB above the in-flight bytes counted (RequestsSize max {rs_max / MIB:.2f} MiB)',
               rise > 256 * MIB and rise - max(rs_max, 0) > 400 * MIB)
        expect(f'R5 row check: R0 queue heap ≥ 256 MiB (read {rise / MIB:.1f})', rise >= 256 * MIB)
        after = win(hp, 'R0', (p['pending_zero'] or p['set32']) + 1, p['end'])
        if after:
            h = int(after[-1]['heap_used_after_gc']); md = int(after[-1]['memtable_data_size'])
            md0 = [int(r['memtable_data_size']) for r in win(hp, 'R0', *p['base'])]
            md0 = md0[-1] if md0 else 0
            note(f'R0 drain: last heap after GC {h / MIB:.1f} MiB, memtable data size {md / MIB:.1f} MiB (baseline {md0 / MIB:.1f})')
            expect(f'R0 drain: heap back within 50 MiB of baseline plus memtable growth ({(h - bmean) / MIB:.1f} MiB above baseline, memtable +{(md - md0) / MIB:.1f} MiB)',
                   h - bmean <= 50 * MIB + max(0, md - md0))
        mt = [int(r['memtable_data_size']) for r in pool0_hp]
        if mt:
            note(f'R0 memtable data size during pool 0: min {min(mt) / MIB:.2f} max {max(mt) / MIB:.2f} MiB')
            expect('R0: memtable data size flat (within 1 MiB) during the pool-0 window (B3h)', max(mt) - min(mt) <= MIB)
        res['R0'] = dict(base=bmean, base_net=bnet, rise=rise, rise_max=rise_max, rise_raw=rise_raw, slope=slope, maxpend=maxpend,
                         pend_at=pend_at, rs_max=rs_max)
    steady = {}
    for lab in ('R2', 'R32', 'R128'):
        if lab not in P:
            continue
        p = P[lab]
        h = [int(r['heap_used_after_gc']) for r in win(hp, lab, p['stress_start'], p['stress_end'])]
        t = win(tp, lab, p['stress_start'], p['stress_end'])
        n = int(lab[1:])
        act = [int(r['active']) for r in t]
        pend = [int(r['pending']) for r in t]
        md = [int(r['memtable_data_size']) for r in win(hp, lab, p['stress_start'], p['stress_end'])]
        steady[lab] = dict(mean=sum(h) / len(h) if h else -1, max=max(h) if h else -1, pend=max(pend) if pend else -1,
                           act=max(act) if act else -1, md=max(md) if md else -1, n=len(h))
        s = steady[lab]
        note(f'{lab}: heap after GC mean {s["mean"] / MIB:.1f} MiB, max {s["max"] / MIB:.1f} MiB ({s["n"]} samples); Active max {s["act"]}; '
             f'Pending max {s["pend"]}; memtable max {s["md"] / MIB:.1f} MiB; stress {p["stress"]}')
        expect(f'{lab}: Active ≤ N = {n} at every sample (max {s["act"]})', 0 <= s['act'] <= n)
    if len(steady) == 3:
        m = {k: v['mean'] for k, v in steady.items()}
        ratio = max(m.values()) / min(m.values())
        expect(f'R2/R32/R128: heap means within 20 % (max/min {ratio:.3f}) or higher for R2 (R2 {m["R2"] / MIB:.1f}, R32 {m["R32"] / MIB:.1f}, R128 {m["R128"] / MIB:.1f})',
               ratio <= 1.20 or m['R2'] >= max(m.values()))
        rises = m['R2'] < m['R32'] < m['R128'] and m['R128'] > 1.2 * m['R2']
        expect('R2/R32/R128: heap does NOT rise with N (R4 definition: strictly increasing and R128 > 1.2 × R2)', not rises)
        expect(f'R2 Pending max ≥ R32 Pending max ({steady["R2"]["pend"]} vs {steady["R32"]["pend"]}); not lower for smaller N',
               steady['R2']['pend'] >= steady['R32']['pend'])
        res['steady'] = steady
    if 'PC' in P and 'PC0' in P:
        out = {}
        for lab in ('PC0', 'PC'):
            p = P[lab]
            jr = [r for r in jmx_rows(p['lifetime']) if p['stress_start'] <= r['t'] <= p['stress_end']]
            out[lab] = dict(rs_max=max(r['rs'] for r in jr) if jr else -1,
                            rs_mean=sum(r['rs'] for r in jr) / len(jr) if jr else -1,
                            rate=float(p['stress'].get('op_rate', 'nan')))
            note(f'{lab}: RequestsSize max {out[lab]["rs_max"] / MIB:.2f} MiB, mean {out[lab]["rs_mean"] / MIB:.2f} MiB; stress op rate {out[lab]["rate"]}')
        expect(f'PC: RequestsSize plateaus ≤ 4 MiB (max {out["PC"]["rs_max"] / MIB:.2f} MiB)', 0 <= out['PC']['rs_max'] <= 4 * MIB)
        expect(f'PC0 (R3 reference): RequestsSize above 4 MiB without the per-IP cap (max {out["PC0"]["rs_max"] / MIB:.2f} MiB)', out['PC0']['rs_max'] > 4 * MIB)
        expect(f'PC: stress op rate lower than PC0 ({out["PC"]["rate"]} vs {out["PC0"]["rate"]}) — the cap binds', out['PC']['rate'] < out['PC0']['rate'])
        res['pc'] = out
    json.dump(res, open(LOGS + '/analysis.json', 'w'), indent=1, default=str)


def main():
    note(f'cluster-run all {time.strftime("%F %T %Z")} host {os.uname().nodename} clone {C}; free {free_gb():.1f} GB')
    _, md5 = sh(f'cd {HARNESS} && md5sum cluster-run.py make-node-yaml.sh Jmx.java', check=False, quiet=True)
    note('harness md5 ' + ' '.join(f'{l.split()[1]}={l.split()[0][:12]}' for l in md5.splitlines() if l.strip()))
    if my_daemons():
        fail('a node of this harness is running before the start')
    sh(f'rm -rf {N}; mkdir -p {JMXCP}')
    sh(f'javac -d {JMXCP} {HARNESS}/Jmx.java')
    try:
        run_R0()
        run_steady('R32', ['concurrent_writes=32'], STEADY_S, '400/s')
        run_steady('R2', ['concurrent_writes=2'], STEADY_S, '400/s')
        run_steady('R128', ['concurrent_writes=128'], STEADY_S, '400/s')
        # runbook fix D1 (2026-10-21): PC and PC0 set the per-connection receive queue to 0B, so every in-flight byte is
        # charged to the per-IP / global reserves (stress's 8 connections x 1 MiB would otherwise absorb all 8 MiB)
        run_steady('PC0', ['concurrent_writes=32', 'native_transport_receive_queue_capacity=0B'], PC_S, None)
        run_steady('PC', ['concurrent_writes=32', 'native_transport_receive_queue_capacity=0B',
                          'native_transport_max_request_data_in_flight_per_ip=4MiB'], PC_S, None)
    except Exception as e:
        fail(f'exception: {e!r}')
    analyze()
    kill_children()
    stop_node()
    left = my_daemons()
    note(f'node stopped; leftover daemons of this harness: {len(left)}')
    sh(f'du -sb {N}', check=False)
    sh(f'rm -rf {N}/data {N}/commitlog {N}/hints {N}/saved_caches {N}/cdc', check=False)
    note(f'EXPECTED tally: {EXPECT["yes"]} yes, {EXPECT["no"]} NO; done {time.strftime("%F %T %Z")}')


if MODE == 'reanalyze':
    PHASES.extend(json.load(open(LOGS + '/phases.json')))
    analyze()
    note(f'EXPECTED tally (reanalysis): {EXPECT["yes"]} yes, {EXPECT["no"]} NO')
elif MODE == 'down':
    try:
        STATE['pid'] = int(open(N + '/cassandra.pid').read().strip())
    except (OSError, ValueError):
        pass
    stop_node()
else:
    main()
