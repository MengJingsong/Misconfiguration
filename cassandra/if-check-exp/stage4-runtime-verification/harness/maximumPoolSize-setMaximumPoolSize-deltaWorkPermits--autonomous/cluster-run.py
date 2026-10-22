#!/usr/bin/env python3
"""Stage 4, cluster tier (B3, amendments C1-C7) of maximumPoolSize-setMaximumPoolSize-deltaWorkPermits--autonomous (frozen sha256 d75be538...).
usage: cluster-run.py all | down | reanalyze     one node, 127.0.0.5, JMX 7205 (environment deviation E1), heap 2 GiB.
Lifetimes, each a fresh node (TRUNCATE + clearsnapshot + stop between):
  n32   concurrent_reads/writes 32/32  write n=3,000,000 -> mixed 10 min -> idle 3 min (C3)
  n4    4/4 (same)           n256   256/256 (same)       n32b   32/32 again (noise repeat, B3h)
  RS    32/32, write then mixed 6 min; both stages: t=60 s `setconcurrency <stage> 32` (same value), 120 s 8, 180 s 64, 240 s 32 (C1, C2)
  PC0   32/32, receive queue 0B, in-flight keys 256MiB; write duration=90s unthrottled     PC  same with both in-flight keys 128KiB (C7)
  M64 / M256   32/32, memtable_heap_space 64MiB / 256MiB; write n=3,000,000 only (C7)
Samplers (C4): tpstats every 5 s (ReadStage/MutationStage Active Pending Completed); memory every 30 s (jcmd GC.run, GC.heap_info used, RssAnon/VmRSS,
NMT summary total and Thread committed, ReadStage-/MutationStage-/SharedPool-Worker- thread counts from Thread.print, du of data); JMX every 1 s (RequestsSize, MemtableOnHeapSize of
keyspace1.standard1, ThreadCount, heap used, Read/Mutation ActiveTasks and PendingTasks). Output ~/stage4-logs/mps2/<MPS_RUN>/cluster/.
Env: MPS_RUN (run1), CASSANDRA_HOME (~/cassandra-mps2), MPS_ONLY (comma list of lifetimes), MPS_ROWS (3000000), MPS_READ_S (600), MPS_IDLE_S (180),
MPS_RS_S (360), MPS_PC_S (90), MPS_MIN_FREE_GB (12). Exit 1: a set-up check failed; the node is stopped on any exit."""
import json, os, re, signal, statistics, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-mps2')
HARNESS = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ.get('MPS2N', HOME + '/stage4-mps2')
N = BASE + '/node1'
RUN = os.environ.get('MPS_RUN', 'run1')
ADDR, JMXP = '127.0.0.5', 7205
ROWS = int(os.environ.get('MPS_ROWS', 3000000))
READ_S = int(os.environ.get('MPS_READ_S', 600))
IDLE_S = int(os.environ.get('MPS_IDLE_S', 180))
RS_S = int(os.environ.get('MPS_RS_S', 360))
PC_S = int(os.environ.get('MPS_PC_S', 90))
MIN_FREE = float(os.environ.get('MPS_MIN_FREE_GB', 12))
ONLY = [x for x in os.environ.get('MPS_ONLY', '').split(',') if x]
MIB, GIB = 1 << 20, 1 << 30
JMXCP = BASE + '/jmx'
MODE = sys.argv[1] if len(sys.argv) > 1 else ''
if MODE not in ('all', 'down', 'reanalyze'):
    sys.exit(__doc__)
LOGS = f'{HOME}/stage4-logs/mps2/{RUN}/cluster'
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
SUMMARY = open(LOGS + ('/reanalysis.txt' if MODE == 'reanalyze' else '/summary.txt'), 'a' if MODE == 'down' else 'w')
EXPECT = {'yes': 0, 'no': 0}
PHASES = []
CHILDREN = []
STATE = {'run': 'setup', 'pid': None, 'lifetime': 0}
GCOPTS = '-XX:G1NewSizePercent=20 -XX:G1MaxNewSizePercent=30 -XX:InitiatingHeapOccupancyPercent=30'   # runbook fix D2: appended to jvm11-server.options in every lifetime
COL = "-col 'n=FIXED(1)' 'size=FIXED(1024)'"
STRESS_OPTS = f"-rate threads=400 -errors ignore retries=0 -mode native cql3 -node {ADDR}"


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
    """java CassandraDaemon processes of this harness only: the node directory or the JMX port in the arguments (never another session's)."""
    _, out = sh("ps -eo pid,args | grep -E '^ *[0-9]+ [^ ]*java .*org\\.apache\\.cassandra\\.service\\.CassandraDaemon' || true", check=False, quiet=True)
    return [l for l in out.splitlines() if N + '/' in l or f'-Dcassandra.jmx.local.port={JMXP}' in l]


def nodetool(cmd, timeout=180, check=False, quiet=True):
    return sh(f'bin/nodetool -h 127.0.0.1 -p {JMXP} {cmd}', timeout=timeout, check=check, quiet=quiet)


def cql(stmt, timeout=300):
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
    _, y = sh(f'bash {HARNESS}/make-node-yaml.sh ' + ' '.join(extra_yaml), env=dict(os.environ, CASSANDRA_HOME=C, MPS2N=BASE, MPS_GCOPTS=os.environ.get('MPS_GCOPTS', GCOPTS)))
    note(y.strip().splitlines()[-1][:1500])
    env = dict(os.environ, CASSANDRA_CONF=N + '/conf', CASSANDRA_LOG_DIR=N + '/logs', MAX_HEAP_SIZE='2G', HEAP_NEWSIZE='400M')
    env.pop('JVM_EXTRA_OPTS', None)
    STATE['lifetime'] += 1
    sh(f'rm -f {N}/logs/gc-compact.log* {N}/logs/gc.log*', check=False, quiet=True)
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
            note('jvm: ' + ' '.join(sorted(set(x for x in cmdline.split() if x.startswith(('-Xmx', '-Xms', '-Xmn', '-XX:+UseG1GC', '-XX:HeapDumpPath', '-XX:NativeMemoryTracking', '-Dcassandra.jmx.local.port'))))))
            return
        time.sleep(3)
    fail('node not UN within 300 s')


def getconc(stage):
    _, out = nodetool(f'getconcurrency {stage}', quiet=False)
    m = re.search(rf'^{stage}\s+(-?\d+)\s+(-?\d+)\s*$', out, re.M)
    return int(m.group(2)) if m else None


# ---------------------------------------------------------------- samplers

POOLS = [('ReadStage', 'rd'), ('MutationStage', 'mu')]
MT_BEAN = 'org.apache.cassandra.metrics:type=Table,keyspace=keyspace1,scope=standard1,name=MemtableOnHeapSize'


class Samplers:
    def __init__(self):
        self.stop = threading.Event()
        self.tp = open(LOGS + '/samples-tp.csv', 'a')
        self.mem = open(LOGS + '/samples-mem.csv', 'a')
        if self.tp.tell() == 0:
            self.tp.write('t_ms,run,rd_active,rd_pending,rd_completed,mu_active,mu_pending,mu_completed\n')
        if self.mem.tell() == 0:
            self.mem.write('t_ms,run,heap_after_gc,heap_total,heap_info_used,rss_anon_kb,vmrss_kb,nmt_total_kb,nmt_thread_kb,rd_threads,mu_threads,sp_threads,du_data\n')
        self.last_tp = {}
        self.logged = False
        self.threads = [threading.Thread(target=self.loop_tp, daemon=True), threading.Thread(target=self.loop_mem, daemon=True)]
        self.stopf = LOGS + f'/jmx.stop.{STATE["lifetime"]}'
        try:
            os.remove(self.stopf)
        except OSError:
            pass
        beans = ['org.apache.cassandra.metrics:type=Client,name=RequestsSize', 'Value', MT_BEAN, 'Value',
                 'java.lang:type=Threading', 'ThreadCount', 'java.lang:type=Memory', 'HeapMemoryUsage']
        for st, _ in POOLS:
            for nm in ('ActiveTasks', 'PendingTasks'):
                beans += [f'org.apache.cassandra.metrics:type=ThreadPools,path=request,scope={st},name={nm}', 'Value']
        self.jout = open(LOGS + f'/samples-jmx-{STATE["lifetime"]}.csv', 'w')
        self.jout.write('t_ms,requests_size,memtable_onheap,thread_count,heap_used,rd_active,rd_pending,mu_active,mu_pending\n'); self.jout.flush()
        self.jp = subprocess.Popen(['java', '-cp', JMXCP, 'Jmx', str(JMXP), 'poll', '1000', '100000', self.stopf] + beans,
                                   stdout=self.jout, stderr=subprocess.DEVNULL, start_new_session=True)
        CHILDREN.append(self.jp)
        for t in self.threads:
            t.start()

    def loop_tp(self):
        while not self.stop.is_set():
            t = now_ms()
            _, out = nodetool('tpstats', timeout=60)
            if not self.logged:
                self.logged = True
                log('tpstats (first of this lifetime):\n' + out[-2500:])
            v = []
            for st, _ in POOLS:
                m = re.search(rf'^{st}\s+(\d+)\s+(\d+)\s+(\d+)', out, re.M)
                v += [int(x) for x in m.groups()] if m else [-1, -1, -1]
            self.last_tp = {'t': t, 'rd_pending': v[1], 'mu_pending': v[4]}
            self.tp.write(f'{t},{STATE["run"]},' + ','.join(map(str, v)) + '\n'); self.tp.flush()
            self.stop.wait(max(0.0, 5 - (now_ms() - t) / 1000))

    def sample_mem(self):
        pid = STATE['pid']
        t = now_ms()
        # D2: GC.run + GC.heap_info reads the live set plus the allocation after the GC (a 1 GiB eden at 100k ops/s); the class histogram runs its own
        # full GC and totals only live objects, so its Total line is the heap after GC. GC.heap_info right after it is kept as a second column.
        _, hist = sh(f'jcmd {pid} GC.class_histogram', check=False, quiet=True, timeout=180)
        mt = re.search(r'^Total\s+(\d+)\s+(\d+)\s*$', hist, re.M)
        used = int(mt.group(2)) if mt else -1
        with open(LOGS + '/histo-excerpt.txt', 'a') as hf:
            hf.write(f'--- {t} {STATE["run"]}\n' + '\n'.join(hist.splitlines()[:14]) + '\n')
        _, out = sh(f'jcmd {pid} GC.heap_info', check=False, quiet=True, timeout=60)
        m = re.search(r'garbage-first heap\s+total (\d+)K, used (\d+)K', out)
        total = int(m.group(1)) * 1024 if m else -1
        info_used = int(m.group(2)) * 1024 if m else -1
        st = open(f'/proc/{pid}/status').read() if pid_alive() else ''
        ra = re.search(r'RssAnon:\s+(\d+) kB', st); vr = re.search(r'VmRSS:\s+(\d+) kB', st)
        _, nmt = sh(f'jcmd {pid} VM.native_memory summary', check=False, quiet=True, timeout=120)
        nt = re.search(r'Total: reserved=\d+KB, committed=(\d+)KB', nmt)
        nth = re.search(r'-\s+Thread \(reserved=\d+KB, committed=(\d+)KB', nmt)
        _, tdump = sh(f'jcmd {pid} Thread.print', check=False, quiet=True, timeout=120)
        rdt = len(re.findall(r'^"ReadStage-\d+"', tdump, re.M)); mut = len(re.findall(r'^"MutationStage-\d+"', tdump, re.M))
        spt = len(re.findall(r'^"SharedPool-Worker-\d+"', tdump, re.M))
        _, du = sh(f'du -sb {N}/data', check=False, quiet=True, timeout=60)
        self.mem.write(f'{t},{STATE["run"]},{used},{total},{info_used},{ra.group(1) if ra else -1},{vr.group(1) if vr else -1},{nt.group(1) if nt else -1},'
                       f'{nth.group(1) if nth else -1},{rdt},{mut},{spt},{du.split()[0] if du.split() else -1}\n'); self.mem.flush()

    def loop_mem(self):
        while not self.stop.is_set():
            t = now_ms()
            try:
                self.sample_mem()
            except Exception as e:
                log(f'mem sample failed: {e}')
            self.stop.wait(max(0.0, 30 - (now_ms() - t) / 1000))

    def close(self):
        self.stop.set()
        for t in self.threads:
            t.join(timeout=300)
        open(self.stopf, 'w').close()
        try:
            self.jp.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.jp.kill()
        self.jout.close(); self.tp.close(); self.mem.close()


# ---------------------------------------------------------------- stress

def stress_cmd(kind, label):
    if kind == 'write_n':
        return f"tools/bin/cassandra-stress write n={ROWS} cl=ONE no-warmup {COL} {STRESS_OPTS} -log file={LOGS}/stress-{label}.log"
    if kind == 'write_t':
        return f"tools/bin/cassandra-stress write duration={PC_S}s cl=ONE no-warmup {COL} {STRESS_OPTS} -log file={LOGS}/stress-{label}.log"
    secs = RS_S if label.startswith('RS') else READ_S
    return (f"tools/bin/cassandra-stress mixed 'ratio(write=1,read=3)' duration={secs}s cl=ONE no-warmup -pop 'dist=UNIFORM(1..{ROWS})' "
            f"{COL} {STRESS_OPTS} -log file={LOGS}/stress-{label}.log")


def stress(kind, label):
    cmd = stress_cmd(kind, label)
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
    res['timeouts_logged'] = txt.count('Timeout')
    return res


def wait_stress(p, label, limit_s):
    t0 = time.time()
    while p.poll() is None:
        time.sleep(2)
        if free_gb() < MIN_FREE - 4:
            note(f'{label}: free space {free_gb():.1f} GB below {MIN_FREE - 4} GB, stress stopped early')
            os.killpg(p.pid, signal.SIGTERM); break
        if time.time() - t0 > limit_s:
            note(f'{label}: stress overran {limit_s} s, stopped')
            os.killpg(p.pid, signal.SIGTERM); break


def save():
    json.dump(PHASES, open(LOGS + '/phases.json', 'w'), indent=1)


def reset_and_stop():
    cql('TRUNCATE keyspace1.standard1;')
    nodetool('clearsnapshot --all', quiet=False)
    stop_node()
    for f in ('system.log', 'debug.log', 'gc-compact.log'):
        p = f'{N}/logs/{f}'
        if os.path.exists(p):
            sh(f'cp {p} {LOGS}/{f.replace(".log", "")}-{STATE["lifetime"]}.log', check=False, quiet=True)
            try:
                open(p, 'w').close()
            except OSError:
                pass


def run_lifetime(label, yaml, plan, n=None):
    """plan: 'full' | 'rs' | 'pc' | 'mem'."""
    STATE['run'] = label
    if free_gb() < MIN_FREE:
        fail(f'{free_gb():.1f} GB free < {MIN_FREE} GB before {label}')
    start_node(yaml)
    ph = dict(label=label, lifetime=STATE['lifetime'], yaml=yaml, plan=plan, n=n)
    for st, _ in POOLS:
        g = getconc(st)
        ph[f'conc_{st}'] = g
        if n is not None:
            expect(f'{label} getconcurrency {st} = {n} (read {g})', g == n)
    sm = Samplers()
    time.sleep(65)                       # two baseline memory samples
    ph['base'] = [now_ms() - 65000, now_ms()]
    ph['t_start'] = now_ms()
    kind = 'write_t' if plan == 'pc' else 'write_n'
    p, cmd = stress(kind, label + '-W')
    note(f'{label} write phase started: {cmd}; free {free_gb():.1f} GB')
    ph['w_start'] = now_ms()
    wait_stress(p, label + '-W', 2400)
    ph['w_end'] = now_ms()
    ph['stress_W'] = stress_result(label + '-W')
    note(f'{label} write phase: {ph["stress_W"]}')
    if plan in ('full', 'rs'):
        p, cmd = stress('mixed', label + '-R')
        note(f'{label} read phase started: {cmd}')
        ph['r_start'] = now_ms()
        if plan == 'rs':
            ph['changes'] = []
            for off, val in ((60, 32), (120, 8), (180, 64), (240, 32)):
                while now_ms() < ph['r_start'] + off * 1000:
                    time.sleep(0.5)
                for st, _ in POOLS:
                    t0 = now_ms()
                    rc, out = nodetool(f'setconcurrency {st} {val}', quiet=False)
                    ph['changes'].append(dict(t=t0, stage=st, value=val, rc=rc, out=out.strip()[-200:], read=getconc(st)))
        wait_stress(p, label + '-R', (RS_S if plan == 'rs' else READ_S) + 600)
        ph['r_end'] = now_ms()
        ph['stress_R'] = stress_result(label + '-R')
        note(f'{label} read phase: {ph["stress_R"]}')
        time.sleep(IDLE_S if plan == 'full' else 60)
    else:
        time.sleep(30)
    ph['end'] = now_ms()
    sm.close()
    PHASES.append(ph); save()
    reset_and_stop()


LIFETIMES = [
    ('n32', ['concurrent_reads=32', 'concurrent_writes=32'], 'full', 32),
    ('n4', ['concurrent_reads=4', 'concurrent_writes=4'], 'full', 4),
    ('n256', ['concurrent_reads=256', 'concurrent_writes=256'], 'full', 256),
    ('n32b', ['concurrent_reads=32', 'concurrent_writes=32'], 'full', 32),
    ('RS', ['concurrent_reads=32', 'concurrent_writes=32'], 'rs', None),
    ('PC0', ['concurrent_reads=32', 'concurrent_writes=32', 'native_transport_receive_queue_capacity=0B',
             'native_transport_max_request_data_in_flight=256MiB', 'native_transport_max_request_data_in_flight_per_ip=256MiB'], 'pc', 32),
    ('PC', ['concurrent_reads=32', 'concurrent_writes=32', 'native_transport_receive_queue_capacity=0B',
            'native_transport_max_request_data_in_flight=128KiB', 'native_transport_max_request_data_in_flight_per_ip=128KiB'], 'pc', 32),
    ('M64', ['concurrent_reads=32', 'concurrent_writes=32', 'memtable_heap_space=64MiB'], 'mem', 32),
    ('M256', ['concurrent_reads=32', 'concurrent_writes=32', 'memtable_heap_space=256MiB'], 'mem', 32),
]


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


def jmx_rows(lt):
    out = []
    try:
        lines = open(f'{LOGS}/samples-jmx-{lt}.csv').read().splitlines()[1:]
    except OSError:
        return out
    for l in lines:
        v = l.split(',')
        try:
            out.append(dict(t=int(v[0]), rs=float(v[1]), mt=float(v[2]), thr=float(v[3]), heap=float(v[4]), rda=float(v[5]), rdp=float(v[6]), mua=float(v[7]), mup=float(v[8])))
        except (ValueError, IndexError):
            pass
    return out


def med(xs):
    xs = list(xs)
    return statistics.median(xs) if xs else float('nan')


def analyze():
    mem = rows(LOGS + '/samples-mem.csv')
    tp = rows(LOGS + '/samples-tp.csv')
    P = {p['label']: p for p in PHASES}
    def win(rs, label, a, b, key='t_ms'):
        return [r for r in rs if r['run'] == label and a <= int(r[key]) <= b]
    S = {}
    for lab, ph in P.items():
        if 'w_start' not in ph:
            continue
        w = (ph['w_start'], ph['w_end'])
        r = (ph.get('r_start'), ph.get('r_end'))
        mw = win(mem, lab, *w); mr = win(mem, lab, *r) if r[0] else []
        base = win(mem, lab, ph['base'][0], ph['t_start'])
        jr = [x for x in jmx_rows(ph['lifetime']) if r[0] and r[0] <= x['t'] <= r[1]]
        jw = [x for x in jmx_rows(ph['lifetime']) if w[0] <= x['t'] <= w[1]]
        jall = jmx_rows(ph['lifetime'])
        tr = win(tp, lab, *r) if r[0] else []
        tw = win(tp, lab, *w)
        S[lab] = dict(
            heap_base=med(int(x['heap_after_gc']) for x in base) / MIB,
            heapW=med(int(x['heap_after_gc']) for x in mw) / MIB, heapR=med(int(x['heap_after_gc']) for x in mr) / MIB,
            heapRmax=max([int(x['heap_after_gc']) for x in mr] or [0]) / MIB, heapWmax=max([int(x['heap_after_gc']) for x in mw] or [0]) / MIB,
            rssR=med(int(x['rss_anon_kb']) for x in mr) / 1024, rssW=med(int(x['rss_anon_kb']) for x in mw) / 1024,
            thrR=med(x['thr'] for x in jr), thrW=med(x['thr'] for x in jw),
            rdthrR=med(int(x['rd_threads']) for x in mr), muthrR=med(int(x['mu_threads']) for x in mr), spthrR=med(int(x['sp_threads']) for x in mr),
            nmtThreadR=med(int(x['nmt_thread_kb']) for x in mr) / 1024,
            rd_pend_R=med(float(x['rd_pending']) for x in tr), mu_pend_R=med(float(x['mu_pending']) for x in tr),
            rd_pend_Rmax=max([float(x['rd_pending']) for x in tr] or [0]), mu_pend_Rmax=max([float(x['mu_pending']) for x in tr] or [0]),
            mu_pend_W=med(float(x['mu_pending']) for x in tw),
            jrd_pend_R=med(x['rdp'] for x in jr), jmu_pend_R=med(x['mup'] for x in jr), jrd_pend_Rmax=max([x['rdp'] for x in jr] or [0]),
            jmu_pend_Rmax=max([x['mup'] for x in jr] or [0]),
            act_max=max([max(x['rda'], x['mua']) for x in jall] or [0]),
            tp_act_max=max([max(float(x['rd_active']), float(x['mu_active'])) for x in tp if x['run'] == lab] or [0]),
            rs_max=max([x['rs'] for x in jw + jr] or [0]) / 1024, mt_max=max([x['mt'] for x in jall] or [0]) / MIB)
    for lab, s in S.items():
        note(f'READING {lab}: ' + ', '.join(f'{k}={v:.1f}' for k, v in s.items()))
    # gc health + OOM
    for lab, ph in P.items():
        lt = ph['lifetime']
        try:
            gc = open(f'{LOGS}/gc-compact-{lt}.log', errors='replace').read()
        except OSError:
            gc = ''
        full = [l for l in gc.splitlines() if 'Pause Full' in l and not any(c in l for c in ('System.gc()', 'Heap Inspection', 'Diagnostic Command'))]
        try:
            sl = open(f'{LOGS}/system-{lt}.log', errors='replace').read()
        except OSError:
            sl = ''
        expect(f'{lab}: no full GC other than System.gc()/Heap Inspection (C4, D1) and no OutOfMemoryError (found {len(full)} / {sl.count("OutOfMemoryError: ")})', not full and 'OutOfMemoryError: ' not in sl)
    fixed = [l for l in ('n4', 'n32', 'n256') if l in S]
    if len(fixed) == 3:
        for key, nm in (('heapR', 'HEAP(n) in R'), ('heapW', 'HEAP(n) in W'), ('rssR', 'RSS(n) in R')):
            xs = [S[l][key] for l in fixed]
            ratio = max(xs) / min(xs)
            expect(f'C5 {nm} about equal across n = 4 · 32 · 256: {[round(x, 1) for x in xs]} MiB, max/min {ratio:.3f} <= 1.15', ratio <= 1.15)
            mono = xs[0] < xs[1] < xs[2]
            expect(f'C5 {nm} does not track n (refuting needs monotone and max/min >= 1.5): monotone {mono}, ratio {ratio:.3f}', not (mono and ratio >= 1.5))
        expect(f'B3f sub: RSS(256) - RSS(4) <= 64 MiB (read {S["n256"]["rssR"] - S["n4"]["rssR"]:.1f})', S['n256']['rssR'] - S['n4']['rssR'] <= 64)
        for st in ('rd', 'mu'):
            p4 = S['n4'][f'{st}_pend_R']; p256 = S['n256'][f'{st}_pend_R']
            note(f'READING pending median in R, {st}: n=4 {p4}, n=32 {S["n32"][f"{st}_pend_R"]}, n=256 {p256}')
        reach = any(S['n4'][f'{st}_pend_R'] >= 20 for st in ('rd', 'mu'))
        expect('C5 load reached the limit at n = 4: median Pending in R >= 20 for ReadStage or MutationStage', reach)
        big = [st for st in ('rd', 'mu') if S['n4'][f'{st}_pend_R'] >= 20]
        expect(f'C5 Pending(4) >> Pending(256) for {big}: >= 5 x max(P256,1)', bool(big) and all(S['n4'][f'{st}_pend_R'] >= 5 * max(S['n256'][f'{st}_pend_R'], 1) for st in big))
        expect(f'B3f Pending not capped by n: Pending max at n = 4 exceeds 4 (rd {S["n4"]["rd_pend_Rmax"]}, mu {S["n4"]["mu_pend_Rmax"]})', max(S['n4']['rd_pend_Rmax'], S['n4']['mu_pend_Rmax']) > 4)
        for l, nn in (('n4', 4), ('n32', 32), ('n256', 256)):
            expect(f'C6b {l}: Active <= {nn} at every sample (JMX 1 s max {S[l]["act_max"]}, tpstats max {S[l]["tp_act_max"]})', S[l]['act_max'] <= nn and S[l]['tp_act_max'] <= nn)
        for l, nn in (('n4', 4), ('n32', 32), ('n256', 256)):
            note(f'READING Active reached n? {l}: JMX Active max {S[l]["act_max"]} (n = {nn})')
    if 'n32' in S and 'n32b' in S:
        r = max(S['n32']['heapR'], S['n32b']['heapR']) / min(S['n32']['heapR'], S['n32b']['heapR'])
        expect(f'C6a noise: HEAP(32) of the two n = 32 lifetimes, ratio {r:.3f} <= 1.15 ({S["n32"]["heapR"]:.1f}, {S["n32b"]["heapR"]:.1f})', r <= 1.15)
    # runtime arm: Resized lines
    if 'RS' in P:
        ph = P['RS']
        try:
            sl = open(f'{LOGS}/system-{ph["lifetime"]}.log', errors='replace').read()
        except OSError:
            sl = ''
        lines = [l for l in sl.splitlines() if 'Resized' in l]
        for st in ('ReadStage', 'MutationStage'):
            ls = [l for l in lines if f'Resized {st} ' in l]
            seq = [re.search(r'from (\d+) to (\d+)', l).groups() for l in ls]
            expect(f'C6c RS {st}: exactly 3 "Resized" lines 32->8, 8->64, 64->32 (none for the same-value call): {seq}', seq == [('32', '8'), ('8', '64'), ('64', '32')])
        for c in ph.get('changes', []):
            expect(f'RS setconcurrency {c["stage"]} {c["value"]} rc 0 and read back {c["read"]}', c['rc'] == 0 and c['read'] == c['value'])
    # controls
    if 'PC0' in P and 'PC' in P:
        rs0 = S['PC0']['rs_max']; rs1 = S['PC']['rs_max']      # KiB (rs_max is bytes / 1024)
        expect(f'C7(i) PC RequestsSize max <= 1.25 x 128 KiB (read {rs1:.1f} KiB) and PC0 >= 2 x PC (read {rs0:.1f} KiB)', rs1 <= 160 and rs0 >= 2 * rs1)
        note(f'READING stress PC0 {P["PC0"]["stress_W"]}; PC {P["PC"]["stress_W"]}')
    if all(l in S for l in ('M64', 'M256', 'n32')):
        a, b, c = S['M64']['mt_max'], S['M256']['mt_max'], S['n32']['mt_max']
        expect(f'C7(ii) peak MemtableOnHeapSize M64 {a:.1f} <= M256 {b:.1f} / 1.3 <= n32 reference {c:.1f} / 1.69', a <= b / 1.3 and b / 1.3 <= c / 1.69)
        expect(f'C7(ii) HEAP(W) ordered M64 < M256 < reference: {S["M64"]["heapW"]:.1f} < {S["M256"]["heapW"]:.1f} < {S["n32"]["heapW"]:.1f}', S['M64']['heapW'] < S['M256']['heapW'] < S['n32']['heapW'])
    note(f'SUMMARY: {EXPECT["yes"]} yes, {EXPECT["no"]} NO')


def main():
    if MODE == 'down':
        stop_node()
        note(f'down: daemons left of this harness: {len(my_daemons())}')
        return
    if MODE == 'reanalyze':
        global PHASES
        PHASES = json.load(open(LOGS + '/phases.json'))
        analyze()
        return
    try:
        for lab, yaml, plan, n in LIFETIMES:
            if ONLY and lab not in ONLY:
                continue
            run_lifetime(lab, yaml, plan, n)
        analyze()
    finally:
        kill_children()
        stop_node()
        save()
        note(f'daemons left of this harness: {len(my_daemons())}; free {free_gb():.1f} GB')


if __name__ == '__main__':
    main()
