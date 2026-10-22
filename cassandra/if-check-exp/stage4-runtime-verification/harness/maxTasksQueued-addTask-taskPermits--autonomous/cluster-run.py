#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of maxTasksQueued-addTask-taskPermits--autonomous (audit amendments C1-C7, 2026-10-22).
usage: cluster-run.py all | down | reanalyze
  all   one node (127.0.0.4, JMX 7204; environment deviation E2), four fresh node lifetimes (C4), each after TRUNCATE +
        clearsnapshot of the previous: A = in-flight 256 MiB, concurrent_writes 1; B = 32 MiB, 1; C = 256 MiB, 8; D = 32 MiB, 8
        (per-IP limit = global limit, receive queue 0B: C2). cassandra-stress write, 6000 threads, 64 KiB values, CL ONE,
        no-warmup, connectionsPerHost=16 maxPending=1024 (C3), MTA_STRESS_S seconds (default 150); window t = 30 s .. end.
  down  stop the node of this harness.
  reanalyze  re-run the analysis on phases.json and the sample files of MTA_RUN (writes reanalysis.txt).
Samplers (B3d, C5), into ~/stage4-logs/mta/<run>/cluster/: samples-tp.csv every 5 s (nodetool tpstats MutationStage
Active / Pending / Completed, dropped MUTATION; du of data / commitlog / hints), samples-heap.csv every 15 s (jcmd
GC.run, GC.heap_info used, tablestats memtable data size), samples-jmx-<lifetime>.csv every 1 s (RequestsSize, heap
used, MutationStage ActiveTasks / PendingTasks / MaxTasksQueued gauges). EXPECTED lines carry the C5/C6/C7 definitions;
a NO is recorded and the run goes on. Guard: post-GC heap > 1.8 GiB stops the stress (noted). Exit 1: a check failed;
the node is stopped on any exit."""
import json, os, re, signal, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-mta')
HARNESS = os.path.dirname(os.path.abspath(__file__))
MTAN = os.environ.get('MTAN', HOME + '/stage4-mta')
N = MTAN + '/node1'
RUN = os.environ.get('MTA_RUN', 'run1')
ADDR, JMXP = '127.0.0.4', 7204
R0_S = int(os.environ.get('MTA_R0_S', 120))
STEADY_S = int(os.environ.get('MTA_STEADY_S', 120))
PC_S = int(os.environ.get('MTA_PC_S', 60))
MIN_FREE = float(os.environ.get('MTA_MIN_FREE_GB', 12))
MIB, GIB = 1 << 20, 1 << 30
JMXCP = MTAN + '/jmx'
MODE = sys.argv[1] if len(sys.argv) > 1 else ''
if MODE not in ('all', 'down', 'reanalyze'):
    sys.exit(__doc__)
LOGS = f'{HOME}/stage4-logs/mta/{RUN}/cluster'
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
    _, y = sh(f'bash {HARNESS}/make-node-yaml.sh ' + ' '.join(extra_yaml), env=dict(os.environ, CASSANDRA_HOME=C, MTAN=MTAN))
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
                 'org.apache.cassandra.metrics:type=ThreadPools,path=request,scope=MutationStage,name=PendingTasks', 'Value',
                 'org.apache.cassandra.metrics:type=ThreadPools,path=request,scope=MutationStage,name=MaxTasksQueued', 'Value']
        self.jout = open(LOGS + f'/samples-jmx-{STATE["lifetime"]}.csv', 'w')
        self.jout.write('t_ms,requests_size,heap_used,ms_active,ms_pending,ms_maxqueued\n'); self.jout.flush()
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
            if used > 1.8 * GIB and STATE.get('stress_pg') and not STATE.get('guard'):
                note(f'GUARD: post-GC heap {used / MIB:.0f} MiB > 1.8 GiB in {STATE["run"]}: stress stopped now (heap, not the stage, is the stop)')
                STATE['guard'] = t
                try:
                    os.killpg(STATE['stress_pg'], signal.SIGTERM)
                except OSError:
                    pass
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

STRESS_S = int(os.environ.get('MTA_STRESS_S', 150))
WINDOW_START_S = 30
THREADS = int(os.environ.get('MTA_THREADS', 6000))
ARMS = [('A', 256, 1), ('B', 32, 1), ('C', 256, 8), ('D', 32, 8)]


def stress(label, seconds, rows=None, threads=None):
    th = threads or THREADS
    cmd = (f'tools/bin/cassandra-stress write ' + (f'n={rows} ' if rows else f'duration={seconds}s ') +
           f"cl=ONE no-warmup -col 'n=FIXED(1)' 'size=FIXED(65536)' -rate threads={th}" +
           f' -errors ignore retries=0 -mode native cql3 connectionsPerHost=16 maxPending=1024 -node {ADDR} -log file={LOGS}/stress-{label}.log')
    log('+ (background) ' + cmd)
    out = open(f'{LOGS}/stress-{label}.out', 'w')
    p = subprocess.Popen(cmd, shell=True, cwd=C, stdout=out, stderr=subprocess.STDOUT, start_new_session=True,
                         env=dict(os.environ, JVM_OPTS='-Xmx6g'))
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


def jmx_get(bean, attr='Value'):
    _, out = sh(f'java -cp {JMXCP} Jmx {JMXP} get {bean} {attr}', check=False, quiet=True, timeout=60)
    m = re.search(r'\|' + attr + r'\|(\S+)', out)
    return m.group(1) if m else None


MTQ_BEAN = 'org.apache.cassandra.metrics:type=ThreadPools,path=request,scope=MutationStage,name=MaxTasksQueued'


def getconcurrency():
    _, out = nodetool('getconcurrency MutationStage', quiet=False)
    m = re.search(r'^MutationStage\s+(-?\d+)\s+(-?\d+)\s*$', out, re.M)
    return int(m.group(2)) if m else None


def run_arm(label, cap_mib, w):
    STATE['run'] = label
    STATE['guard'] = None
    if free_gb() < MIN_FREE:
        fail(f'{free_gb():.1f} GB free < {MIN_FREE} GB before {label}')
    extra = [f'concurrent_writes={max(w, 2)}', f'native_transport_max_request_data_in_flight={cap_mib}MiB',
             f'native_transport_max_request_data_in_flight_per_ip={cap_mib}MiB']
    start_node(extra)
    if w < 2:   # runbook fix D1: the yaml minimum is 2; the pool is set to 1 live (B3b)
        nodetool('setconcurrency MutationStage 1', quiet=False)
    g = getconcurrency()
    expect(f'{label} getconcurrency MutationStage = {w} (read {g})', g == w)
    cql("CREATE KEYSPACE IF NOT EXISTS keyspace1 WITH replication={'class':'SimpleStrategy','replication_factor':1};")
    p, _ = stress(f'{label}-schema', 0, rows=100, threads=16)
    p.wait(timeout=300)
    note(f'{label} schema/table: 100-row stress write {stress_result(label + "-schema")}')
    nodetool('flush keyspace1', quiet=False)
    mtq0 = jmx_get(MTQ_BEAN)
    sm = Samplers()
    t0 = now_ms(); time.sleep(47); b1 = now_ms()
    p, cmd = stress(label, STRESS_S)
    STATE['stress_pg'] = p.pid
    ts = now_ms()
    note(f'{label} stress started ({cap_mib} MiB in flight, concurrent_writes {w}): {cmd}; free {free_gb():.1f} GB')
    while p.poll() is None:
        time.sleep(2)
        if free_gb() < MIN_FREE - 4:
            note(f'{label}: free space {free_gb():.1f} GB below {MIN_FREE - 4} GB, stress stopped early')
            os.killpg(p.pid, signal.SIGTERM)
            break
        if now_ms() > ts + (STRESS_S + 150) * 1000:
            note(f'{label}: stress overran by 150 s, stopped')
            os.killpg(p.pid, signal.SIGTERM)
            break
    te = now_ms()
    STATE['stress_pg'] = None
    mtq1 = jmx_get(MTQ_BEAN)
    time.sleep(20)
    sm.close()
    phase(label, base=[t0, b1], stress_start=ts, stress_end=te, end=now_ms(), extra=extra, cap_mib=cap_mib, w=w,
          mtq=[mtq0, mtq1], guard=STATE.get('guard'), stress=stress_result(label), lifetime=STATE['lifetime'])
    note(f'{label} stress: {stress_result(label)}; MaxTasksQueued gauge {mtq0} -> {mtq1}')
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
            out.append({'t': int(v[0]), 'rs': float(v[1]), 'heap': float(v[2]), 'act': float(v[3]), 'pend': float(v[4]), 'mtq': float(v[5])})
        except (ValueError, IndexError):
            pass
    return out


def median(x):
    x = sorted(x)
    return x[len(x) // 2] if x else float('nan')


def analyze():
    hp = rows(LOGS + '/samples-heap.csv')
    stat = {}
    for p in PHASES:
        a = p['stress_start'] + WINDOW_START_S * 1000
        b = p['stress_end']
        jr = [r for r in jmx_rows(p['lifetime']) if a <= r['t'] <= b]
        hw = [r for r in hp if r['run'] == p['run'] and a <= int(r['t_ms']) <= b]
        Pk = max((r['pend'] for r in jr), default=-1)
        RS = max((r['rs'] for r in jr), default=-1)
        HQ = median([int(r['heap_used_after_gc']) - max(0, int(r['memtable_data_size'])) for r in hw])
        allj = [r for r in jmx_rows(p['lifetime'])]
        mtq_all = {r['mtq'] for r in allj}
        stat[p['run']] = dict(P=Pk, RS=RS, HQ=HQ, cap=p['cap_mib'] * MIB, w=p['w'], mtq=mtq_all, n_jmx=len(jr), n_hp=len(hw),
                              act_max=max((r['act'] for r in jr), default=-1), heap_max=max((r['heap'] for r in jr), default=-1))
        s = stat[p['run']]
        note(f'{p["run"]} (cap {p["cap_mib"]} MiB, concurrent_writes {p["w"]}): window {len(jr)} JMX samples, {len(hw)} heap samples; '
             f'P (peak Pending) {Pk:.0f}; Active max {s["act_max"]:.0f}; RS (peak RequestsSize) {RS / MIB:.2f} MiB; '
             f'HQ (median post-GC heap - memtable) {HQ / MIB:.1f} MiB; heap used max {s["heap_max"] / MIB:.0f} MiB; MaxTasksQueued gauge values {sorted(mtq_all)}; guard {p.get("guard")}')
    ex = expect
    for k, s in stat.items():
        ex(f'{k}: MaxTasksQueued gauge = 2147483647 at every sample ({sorted(s["mtq"])})', s['mtq'] == {2147483647.0})
        ex(f'{k}: RS reaches >= 80 % of the cap and stays <= cap + 1 MiB (RS {s["RS"] / MIB:.2f} MiB, cap {s["cap"] / MIB:.0f} MiB)',
           0.8 * s['cap'] <= s['RS'] <= s['cap'] + MIB)
    if all(k in stat for k in 'ABCD'):
        A, B, C_, D = (stat[k] for k in 'ABCD')
        rAB = A['P'] / B['P'] if B['P'] > 0 else float('inf')
        rCD = C_['P'] / D['P'] if D['P'] > 0 else float('inf')
        note(f'ratios: P(A)/P(B) {rAB:.2f}, P(C)/P(D) {rCD:.2f}, HQ(C)/HQ(A) {C_["HQ"] / A["HQ"]:.2f}, HQ(D)/HQ(B) {D["HQ"] / B["HQ"]:.2f}')
        ex(f'B3g row 1: 4 <= P(A)/P(B) <= 12 ({rAB:.2f}) and 4 <= P(C)/P(D) <= 12 ({rCD:.2f}) [C6]', 4 <= rAB <= 12 and 4 <= rCD <= 12)
        ex('B3g row 3 (never grows): P < 20 in all four arms [C6]', all(s['P'] < 20 for s in stat.values()))
        ex(f'B3g row 2 (same plateau regardless of cap): P(A)/P(B) < 2 and P(C)/P(D) < 2 [C6] ({rAB:.2f}, {rCD:.2f})', rAB < 2 and rCD < 2)
        ex(f'B3g row 4 (heap follows concurrent_writes): HQ(w=8) >= 1.3 x HQ(w=1) at both caps [C6] '
           f'(C/A {C_["HQ"] / A["HQ"]:.2f}, D/B {D["HQ"] / B["HQ"]:.2f})', C_['HQ'] >= 1.3 * A['HQ'] and D['HQ'] >= 1.3 * B['HQ'])
        over = {k: s['P'] * 65536 / s['cap'] for k, s in stat.items()}
        note('P x 64 KiB / cap per arm: ' + ', '.join(f'{k} {v:.2f}' for k, v in over.items()))
        ex('C7 row (C-a): P x 65536 > 1.25 x cap in at least one arm while RS <= cap + 1 MiB',
           any(v > 1.25 for v in over.values()) and all(s['RS'] <= s['cap'] + MIB for s in stat.values()))
    note(f'analysis: {EXPECT["yes"]} yes, {EXPECT["no"]} NO')


# ---------------------------------------------------------------- main

def main():
    if MODE == 'down':
        stop_node()
        note(f'down: daemons left {my_daemons()}')
        return
    if MODE == 'reanalyze':
        PHASES.extend(json.load(open(LOGS + '/phases.json')))
        analyze()
        return
    sh(f'mkdir -p {JMXCP} && javac -d {JMXCP} {HARNESS}/Jmx.java', check=True, quiet=True)
    note(f'cluster-run {time.strftime("%F %T")} host {os.uname().nodename.split(".")[0]} clone {sh("git describe --tags; git rev-parse --short HEAD", quiet=True)[1].split()} '
         f'cores {os.cpu_count()} load {open("/proc/loadavg").read().split()[:3]} stress threads {THREADS} duration {STRESS_S}s')
    note('harness md5: ' + sh(f'cd {HARNESS} && md5sum cluster-run.py make-node-yaml.sh Jmx.java', quiet=True)[1].replace('\n', ' '))
    for label, cap, w in ARMS:
        if label in os.environ.get('MTA_ARMS', 'ABCD'):
            run_arm(label, cap, w)
    analyze()
    note(f'daemons left: {my_daemons()}')


def cleanup(*_):
    kill_children()
    stop_node()
    save()


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *a: (cleanup(), sys.exit(143)))
    try:
        main()
    except SystemExit:
        raise
    except BaseException as e:
        note(f'EXCEPTION {type(e).__name__}: {e}')
        cleanup()
        raise
    finally:
        if MODE == 'all':
            kill_children()
            stop_node()
