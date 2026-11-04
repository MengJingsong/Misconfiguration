#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of maximumPoolSize-takeTaskPermit-workPermits--autonomous (frozen sha256 c004650f…, R1-R5).
usage: cluster-run.py all | down | reanalyze      (env MPS_RUN, default run1; MPS_ONLY=bind runs only the R5 arm)
Two nodes on loopback (environment deviation E1): A = 127.0.0.21 (JMX 7221, coordinator), B = 127.0.0.22 (JMX 7222,
replica under test), 8 GiB heap each, from ~/cassandra-mps, node directories ~/stage4-mps/{A,B}.
  L1  A and B default yaml (B3a). 20 s warm-up stress, flush both, B baseline. Then for v = 32, 8, 1, 0 (B3e step 2):
      setconcurrency MutationStage v on B (read back), stress 120 s (B3c + R1 no-warmup); at t = 90 s flush B,
      jmap -histo:live B and A, GC.heap_info B; restore 32, wait Pending 0, post-drain histogram, TRUNCATE, clearsnapshot.
  L2-L4  B restarted with internode_application_receive_queue_reserve_endpoint_capacity 16MiB / 128MiB / 512MiB (+ global
      1GiB for 512MiB); baseline; the v = 0 phase only (B3e step 3).
  L5  B restarted with the default yaml; baseline; v = 32 and v = 0 again (R3 drift repeat).
  R5  bind arm: A restarted with write_request_timeout 300000ms; for each of S (32 KiB, 400/s) and L (256 KiB, 100/s) and
      v = 1, 8, 32, 128: B in a fresh lifetime with commitlog_sync group, window 5000ms, write_request_timeout 300000ms;
      setconcurrency v; flush; baseline sample; stress 90 s; t = 60 s sample; then setconcurrency 512, wait Pending 0 at
      3 samples in a row, TRUNCATE, clearsnapshot, stop B.
Samplers: samples-tp.csv (B tpstats every 5 s), samples-jmx-B<lifetime>.csv (1 s: heap used, direct MemoryUsed, networking
pool UsedSize / OverflowSize, MutationStage Active / Pending gauges), samples-heap.csv (one row per heap sample:
GC.heap_info used after the histogram's full GC, histogram totals and counts, direct, networking pool, internode_inbound
using bytes). phases.json, summary.txt with EXPECTED lines; a NO is recorded and the run goes on. Nodes stopped on any exit."""
import json, os, re, signal, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-mps')
HARNESS = os.path.dirname(os.path.abspath(__file__))
MPSN = HOME + '/stage4-mps'
RUN = os.environ.get('MPS_RUN', 'run1')
ONLY = os.environ.get('MPS_ONLY', '')
NODES = {'A': ('127.0.0.21', 7221), 'B': ('127.0.0.22', 7222)}
MIB = 1 << 20
JMXCP = MPSN + '/jmx'
FILED_S = int(os.environ.get('MPS_FILED_S', 120))
BIND_S = int(os.environ.get('MPS_BIND_S', 90))
BIND_T = int(os.environ.get('MPS_BIND_T', 60))
BIND_SET = [x for x in os.environ.get('MPS_BIND_SET', '').split(',') if x]
MODE = sys.argv[1] if len(sys.argv) > 1 else ''
if MODE not in ('all', 'down', 'reanalyze'):
    sys.exit(__doc__)
LOGS = f'{HOME}/stage4-logs/mps/{RUN}/cluster'
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
SUMMARY = open(LOGS + ('/reanalysis.txt' if MODE == 'reanalyze' else '/summary.txt'), 'a' if MODE == 'down' else 'w')
EXPECT = {'yes': 0, 'no': 0}
PHASES = []
CHILDREN = []
STATE = {'phase': 'setup', 'pid': {'A': None, 'B': None}, 'life': {'A': 0, 'B': 0}, 'jmx': None}
lock = threading.Lock()


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, file=sys.stderr)
    with lock:
        SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush(); log(s)


def now_ms():
    return int(time.time() * 1000)


def sh(cmd, timeout=600, check=True, env=None, quiet=False):
    log('+ ' + cmd)
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env, cwd=C)
    except subprocess.TimeoutExpired:
        log(f'  TIMEOUT after {timeout} s')
        if check:
            raise RuntimeError(f'command timed out: {cmd}')
        return 124, ''
    out = (r.stdout or '') + (r.stderr or '')
    if not quiet:
        with lock:
            SESSION.write(out[-3000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed rc={r.returncode}: {cmd}\n{out[-1200:]}')
    return r.returncode, out


def expect(desc, cond):
    EXPECT['yes' if cond else 'no'] += 1
    note(f'EXPECTED: {desc} — {"yes" if cond else "NO (recorded; judged in the results file)"}')
    return cond


def alive(n):
    pid = STATE['pid'][n]
    if pid is None:
        return None
    try:
        return pid if 'CassandraDaemon' in open(f'/proc/{pid}/cmdline').read() else None
    except OSError:
        return None


def my_daemons():
    _, out = sh("ps -eo pid,args | grep -E '^ *[0-9]+ [^ ]*java .*org\\.apache\\.cassandra\\.service\\.CassandraDaemon' || true",
                check=False, quiet=True)
    return [l for l in out.splitlines() if MPSN + '/' in l]


def nodetool(n, cmd, timeout=180, check=False, quiet=True):
    return sh(f'bin/nodetool -h 127.0.0.1 -p {NODES[n][1]} {cmd}', timeout=timeout, check=check, quiet=quiet)


def cql(n, stmt, timeout=180):
    return sh(f'bin/cqlsh {NODES[n][0]} --request-timeout=170 -e "{stmt}"', timeout=timeout, check=False)


def stop_node(n, wait_s=120):
    if alive(n) is None:
        return
    nodetool(n, 'stopdaemon', timeout=wait_s, quiet=False)
    for _ in range(wait_s):
        if alive(n) is None:
            break
        time.sleep(1)
    pid = alive(n)
    if pid is not None:
        note(f'{n} did not stop within {wait_s} s; kill -9 {pid}')
        os.kill(pid, signal.SIGKILL)
        time.sleep(3)
    for f in ('system.log', 'debug.log', 'gc.log'):
        p = f'{MPSN}/{n}/logs/{f}'
        if os.path.exists(p):
            sh(f'cp {p} {LOGS}/{n}{STATE["life"][n]}-{f}', check=False, quiet=True)
    if n == 'B' and STATE['jmx'] is not None:
        open(STATE['jmx'][1], 'w').close()
        try:
            STATE['jmx'][0].wait(timeout=10)
        except subprocess.TimeoutExpired:
            STATE['jmx'][0].kill()
        STATE['jmx'] = None


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
    stop_node('B'); stop_node('A')
    save()
    sys.exit(1)


def free_gb():
    st = os.statvfs(HOME)
    return st.f_bavail * st.f_frsize / 1e9


def wait_up(n, t_max=300):
    addr = NODES[n][0]
    t0 = time.time()
    while time.time() - t0 < t_max:
        if alive(n) is None:
            fail(f'{n} died during start')
        _, st = nodetool('A' if alive('A') else n, 'status')
        _, sb = nodetool(n, 'statusbinary')
        if re.search(r'^UN\s+' + re.escape(addr) + r'\s', st, re.M) and re.search(r'^running\s*$', sb, re.M):
            log(f'{n} UN and serving after {time.time() - t0:.0f} s')
            return
        time.sleep(3)
    fail(f'{n} not UN within {t_max} s')


def start_node(n, extra, jvm_extra=None):
    if alive(n) is not None:
        fail(f'{n} already running')
    if free_gb() < 20:
        fail(f'free space {free_gb():.1f} GB < 20 GB (B4)')
    _, y = sh(f'bash {HARNESS}/make-node-yaml.sh {n} ' + ' '.join(extra), env=dict(os.environ, CASSANDRA_HOME=C))
    note(y.strip().splitlines()[-1][:600])
    N = f'{MPSN}/{n}'
    env = dict(os.environ, CASSANDRA_CONF=N + '/conf', CASSANDRA_LOG_DIR=N + '/logs', MAX_HEAP_SIZE='8G')
    env.pop('JVM_EXTRA_OPTS', None); env.pop('HEAP_NEWSIZE', None)
    if jvm_extra:
        env['JVM_EXTRA_OPTS'] = jvm_extra   # scoped to this bin/cassandra command only
    STATE['life'][n] += 1
    for f in ('system.log', 'debug.log'):
        try:
            os.remove(f'{N}/logs/{f}')
        except OSError:
            pass
    try:
        os.remove(N + '/cassandra.pid')
    except OSError:
        pass
    note(f'start {n} lifetime {STATE["life"][n]} ({STATE["phase"]}): MAX_HEAP_SIZE=8G, yaml extra {extra}, JVM_EXTRA_OPTS {jvm_extra!r}')
    sh(f'ulimit -n 100000; bin/cassandra -p {N}/cassandra.pid > {N}/stdout-{STATE["life"][n]}.txt 2>&1', env=env)
    for _ in range(30):
        time.sleep(1)
        try:
            STATE['pid'][n] = int(open(N + '/cassandra.pid').read().strip())
        except (OSError, ValueError):
            continue
        if alive(n):
            break
    if not alive(n):
        fail(f'{n} did not start')
    wait_up(n)
    _, cmdline = sh(f'tr "\\0" " " < /proc/{STATE["pid"][n]}/cmdline', check=False, quiet=True)
    note(f'{n} jvm: ' + ' '.join(sorted(set(x for x in cmdline.split() if x.startswith(('-Xmx', '-Xms', '-XX:+UseG1GC', '-Dcassandra.jmx.local.port', '-javaagent'))))))
    if n == 'B':
        stopf = f'{LOGS}/jmx.stop.B{STATE["life"]["B"]}'
        out = open(f'{LOGS}/samples-jmx-B{STATE["life"]["B"]}.csv', 'w')
        out.write('t_ms,heap_used,direct_used,net_used,net_overflow,ms_active,ms_pending\n'); out.flush()
        beans = ['java.lang:type=Memory', 'HeapMemoryUsage',
                 'java.nio:type=BufferPool,name=direct', 'MemoryUsed',
                 'org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=UsedSize', 'Value',
                 'org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=OverflowSize', 'Value',
                 'org.apache.cassandra.metrics:type=ThreadPools,path=request,scope=MutationStage,name=ActiveTasks', 'Value',
                 'org.apache.cassandra.metrics:type=ThreadPools,path=request,scope=MutationStage,name=PendingTasks', 'Value']
        p = subprocess.Popen(['java', '-cp', JMXCP, 'Jmx', str(NODES['B'][1]), 'poll', '1000', '1000000', stopf] + beans,
                             stdout=out, stderr=subprocess.DEVNULL, start_new_session=True)
        CHILDREN.append(p)
        STATE['jmx'] = (p, stopf)


def getconcurrency():
    _, out = nodetool('B', 'getconcurrency MutationStage', quiet=False)
    m = re.search(r'^MutationStage\s+(-?\d+)\s+(-?\d+)\s*$', out, re.M)
    return int(m.group(2)) if m else None


def setconcurrency(v):
    nodetool('B', f'setconcurrency MutationStage {v}', quiet=False)
    g = getconcurrency()
    note(f'{STATE["phase"]}: setconcurrency MutationStage {v} on B, getconcurrency reads {g}')
    return g


# ---------------------------------------------------------------- samplers

class TpSampler:
    def __init__(self):
        self.stop = threading.Event()
        self.f = open(LOGS + '/samples-tp.csv', 'a')
        if self.f.tell() == 0:
            self.f.write('t_ms,phase,active,pending,completed,dropped_mutation\n')
        self.last = {}
        self.t = threading.Thread(target=self.loop, daemon=True)
        self.t.start()

    def loop(self):
        while not self.stop.is_set():
            t = now_ms()
            _, out = nodetool('B', 'tpstats', timeout=60)
            m = re.search(r'^MutationStage\s+(\d+)\s+(\d+)\s+(\d+)', out, re.M)
            d = re.search(r'^MUTATION_REQ\s+(\d+)', out, re.M)
            if m:
                self.last = {'t': t, 'active': int(m.group(1)), 'pending': int(m.group(2))}
                with lock:
                    self.f.write(f'{t},{STATE["phase"]},{m.group(1)},{m.group(2)},{m.group(3)},{d.group(1) if d else -1}\n'); self.f.flush()
            self.stop.wait(max(0.0, 5 - (now_ms() - t) / 1000))

    def close(self):
        self.stop.set(); self.t.join(timeout=120); self.f.close()


def histo(n, label):
    path = f'{LOGS}/histo-{label}-{n}.txt'
    sh(f'jmap -histo:live {STATE["pid"][n]} > {path}', check=False, quiet=True, timeout=300)
    res = {'total': -1, 'mutation': 0, 'pu': 0, 'cached': 0, 'bytearr': 0}
    try:
        for l in open(path):
            f = l.split()
            if len(f) >= 3 and f[0] == 'Total':
                res['total'] = int(f[2])
            elif len(f) >= 4:
                cls = f[3]
                if cls == 'org.apache.cassandra.db.Mutation':
                    res['mutation'] = int(f[1])
                elif cls == 'org.apache.cassandra.db.partitions.PartitionUpdate':
                    res['pu'] = int(f[1])
                elif cls == 'org.apache.cassandra.db.Mutation$CachedSerialization':
                    res['cached'] = int(f[1])
                elif cls == '[B':
                    res['bytearr'] = int(f[2])
    except OSError:
        pass
    return res


def heap_info(n):
    _, out = sh(f'jcmd {STATE["pid"][n]} GC.heap_info', check=False, quiet=True, timeout=60)
    m = re.search(r'garbage-first heap\s+total (\d+)K, used (\d+)K', out)
    return int(m.group(2)) * 1024 if m else -1


def jmx_now():
    _, out = sh(f'java -cp {JMXCP} Jmx {NODES["B"][1]} get java.nio:type=BufferPool,name=direct MemoryUsed '
                f'org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=UsedSize Value '
                f'org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=OverflowSize Value', check=False, quiet=True)
    vals = [l.split('|')[-1] for l in out.splitlines() if '|' in l]
    try:
        return [int(float(v)) for v in vals[:3]]
    except ValueError:
        return [-1, -1, -1]


def inbound():
    _, out = cql('B', 'SELECT address, using_bytes, using_reserve_bytes FROM system_views.internode_inbound;', timeout=60)
    ub = ur = 0
    for l in out.splitlines():
        f = [x.strip() for x in l.split('|')]
        if len(f) == 3 and f[0] == NODES['A'][0]:
            ub += int(f[1]); ur += int(f[2])
    return ub, ur


def sample(label, with_a=False, flush=True):
    t = now_ms()
    if flush:
        nodetool('B', 'flush keyspace1', timeout=300, quiet=False)
    ub, ur = inbound()
    d, nu, no = jmx_now()
    h = histo('B', label)
    used = heap_info('B')
    row = dict(t=t, phase=STATE['phase'], label=label, heap_used=used, histo_total=h['total'], mutation=h['mutation'],
               pu=h['pu'], cached=h['cached'], bytearr=h['bytearr'], direct=d, net_used=nu, net_overflow=no,
               inbound_using=ub, inbound_reserve=ur)
    if with_a:
        ha = histo('A', label)
        row['a_histo_total'] = ha['total']; row['a_mutation'] = ha['mutation']
    newf = not os.path.exists(LOGS + '/samples-heap.json')
    with open(LOGS + '/samples-heap.jsonl', 'a') as f:
        f.write(json.dumps(row) + '\n')
    log(f'sample {label}: {row}')
    return row


# ---------------------------------------------------------------- stress

def stress(label, seconds, ncol, size, rate, rows=None):
    a = NODES['A']
    cmd = (f'tools/bin/cassandra-stress write ' + (f'n={rows}' if rows else f'duration={seconds}s') + ' cl=ONE no-warmup -schema "replication(factor=2)" '
           f'-col "n=FIXED({ncol})" "size=FIXED({size})" -rate threads=64 fixed={rate}/s '
           f'-node whitelist {a[0]} -port jmx={a[1]} -log file={LOGS}/stress-{label}.log')
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
                   ('total_errors', r'^Total errors\s*:\s*([\d,]+)')):
        m = re.search(pat, txt, re.M)
        if m:
            res[k] = m.group(1).replace(',', '')
    return res


def wait_stress(p, seconds):
    t_end = time.time() + seconds + 300
    while p.poll() is None and time.time() < t_end:
        time.sleep(2)
    if p.poll() is None:
        note('stress overran by 300 s; stopped')
        os.killpg(p.pid, signal.SIGTERM)


def wait_pending_zero(tp, consecutive=1, t_max=900):
    t0 = now_ms(); seen = 0; last_t = 0
    while now_ms() - t0 < t_max * 1000:
        lt = tp.last
        if lt.get('t', 0) > max(t0, last_t):
            last_t = lt['t']
            seen = seen + 1 if lt['pending'] == 0 else 0
            if seen >= consecutive:
                return (lt['t'] - t0) / 1000
        time.sleep(1)
    return None


def phase(**kw):
    kw['phase'] = STATE['phase']
    PHASES.append(kw)
    save()


def save():
    json.dump(PHASES, open(LOGS + '/phases.json', 'w'), indent=1)


def truncate():
    rc, out = cql('A', 'TRUNCATE keyspace1.standard1;')
    note(f'{STATE["phase"]}: TRUNCATE rc={rc} {out.strip()[-200:]}')
    nodetool('A', 'clearsnapshot --all', quiet=False); nodetool('B', 'clearsnapshot --all', quiet=False)
    _, du = sh(f'du -sh {MPSN}/A/data {MPSN}/B/data {MPSN}/A/commitlog {MPSN}/B/commitlog', check=False, quiet=True)
    note(f'{STATE["phase"]}: du ' + ' ; '.join(du.split('\n')).replace('\t', ' ') + f' free {free_gb():.1f} GB')


# ---------------------------------------------------------------- filed phases (B3e)

def filed_phase(v, tp, tag=''):
    STATE['phase'] = f'v{v}{tag}'
    g = setconcurrency(v)
    expect(f'{STATE["phase"]}: getconcurrency = {v} (read {g})', g == v)
    p, cmd = stress(STATE['phase'], FILED_S, 5, 200, 20000)
    ts = now_ms()
    note(f'{STATE["phase"]}: stress started: {cmd}')
    while now_ms() < ts + 90000:
        time.sleep(1)
    s90 = sample(STATE['phase'] + '-t90', with_a=True)
    wait_stress(p, FILED_S)
    te = now_ms()
    STATE['phase'] = f'v{v}{tag}-drain'
    setconcurrency(32)
    dz = wait_pending_zero(tp)
    note(f'v{v}{tag}: Pending back to 0 {dz} s after the restore')
    time.sleep(5)
    sd = sample(f'v{v}{tag}-postdrain', flush=True)
    STATE['phase'] = f'v{v}{tag}'
    truncate()
    phase(v=v, tag=tag, stress_start=ts, stress_end=te, t90=s90['t'], stress=stress_result(f'v{v}{tag}'),
          lifeB=STATE['life']['B'], kind='filed')
    note(f'v{v}{tag}: stress {stress_result(f"v{v}{tag}")}')


def run_filed():
    STATE['phase'] = 'L1-start'
    start_node('A', []); start_node('B', [])
    tp = TpSampler()
    STATE['phase'] = 'warmup'
    p, _ = stress('warmup', 20, 5, 200, 20000)
    wait_stress(p, 20)
    note(f'warm-up: {stress_result("warmup")}')
    nodetool('A', 'flush', timeout=300, quiet=False); nodetool('B', 'flush', timeout=300, quiet=False)
    STATE['phase'] = 'L1-base'
    b = sample('L1-baseline', flush=False)
    phase(kind='baseline', t=b['t'], lifeB=STATE['life']['B'])
    for v in (32, 8, 1, 0):
        filed_phase(v, tp)
    for R in ('16MiB', '128MiB', '512MiB'):
        STATE['phase'] = f'ctl{R}-start'
        stop_node('B')
        extra = [f'internode_application_receive_queue_reserve_endpoint_capacity={R}']
        if R == '512MiB':
            extra.append('internode_application_receive_queue_reserve_global_capacity=1GiB')
        start_node('B', extra)
        STATE['phase'] = f'ctl{R}-base'
        b = sample(f'ctl{R}-baseline')
        phase(kind='baseline', t=b['t'], lifeB=STATE['life']['B'])
        filed_phase(0, tp, tag=f'-ctl{R}')
    STATE['phase'] = 'drift-start'
    stop_node('B'); start_node('B', [])
    STATE['phase'] = 'drift-base'
    b = sample('drift-baseline')
    phase(kind='baseline', t=b['t'], lifeB=STATE['life']['B'])
    filed_phase(32, tp, tag='-rep')
    filed_phase(0, tp, tag='-rep')
    tp.close()
    stop_node('B'); stop_node('A')


# ---------------------------------------------------------------- R5 bind arm

BIND_B = ['write_request_timeout=300000ms']
BYTEMAN = f'-javaagent:{C}/build/lib/jars/byteman-4.0.20.jar=script:{HARNESS}/hold-mutation.btm'


def run_bind():
    # R5 as amended by runbook fix D2 (2026-10-21): group commit replaced by a Byteman 2 s hold at the entry of
    # MutationVerbHandler.doVerb on B (hold-mutation.btm): a B restart under group commit hung in SystemKeyspaceMigrator41,
    # group commit delayed schema propagation so every small message was dropped as "incompatible schema", and its waits were
    # far shorter than the 5 s window, so the pool would not bind at v >= 32. B in a fresh lifetime per phase (R5).
    STATE['phase'] = 'bind-start'
    start_node('A', ['write_request_timeout=300000ms'])
    tp = None
    for sz, size, rate in (('S', 32768, 400), ('L', 262144, 100)):
        for v in (1, 8, 32, 128):
            lab = f'{sz}{v}'
            if BIND_SET and lab not in BIND_SET:
                continue
            STATE['phase'] = f'{lab}-start'
            start_node('B', BIND_B, jvm_extra=BYTEMAN)
            if tp is None:
                tp = TpSampler()
            _, d = cql('B', 'DESCRIBE TABLE keyspace1.standard1;', timeout=60)
            if 'CREATE TABLE keyspace1.standard1' not in d:      # only after MPS_ONLY=bind wiped the nodes
                p, _ = stress('bind-schema', 0, 1, size, rate, rows=100)
                p.wait(timeout=300)
                note(f'bind schema: 100-row stress write {stress_result("bind-schema")}')
                time.sleep(10)
                truncate()
                _, d = cql('B', 'DESCRIBE TABLE keyspace1.standard1;', timeout=60)
                if 'CREATE TABLE keyspace1.standard1' not in d:
                    fail(f'{lab}: B has no keyspace1.standard1')
            STATE['phase'] = lab
            g = setconcurrency(v)
            expect(f'{lab}: getconcurrency = {v} (read {g})', g == v)
            b = sample(f'{lab}-baseline')
            p, cmd = stress(lab, BIND_S, 1, size, rate)
            ts = now_ms()
            note(f'{lab}: stress started: {cmd}')
            while now_ms() < ts + BIND_T * 1000:
                time.sleep(1)
            s60 = sample(f'{lab}-t60')
            wait_stress(p, BIND_S)
            te = now_ms()
            STATE['phase'] = f'{lab}-drain'
            setconcurrency(512)
            dz = wait_pending_zero(tp, consecutive=3)
            note(f'{lab}: Pending 0 at 3 samples {dz} s after setconcurrency 512')
            truncate()
            STATE['phase'] = lab
            phase(kind='bind', size=sz, v=v, stress_start=ts, stress_end=te, base=b['t'], t60=s60['t'],
                  stress=stress_result(lab), lifeB=STATE['life']['B'])
            note(f'{lab}: stress {stress_result(lab)}')
            stop_node('B')
    if tp is not None:
        tp.close()
    stop_node('A')


# ---------------------------------------------------------------- analysis

def load_samples():
    out = []
    try:
        for l in open(LOGS + '/samples-heap.jsonl'):
            out.append(json.loads(l))
    except OSError:
        pass
    return {r['label']: r for r in out}


def tp_rows():
    out = []
    try:
        lines = open(LOGS + '/samples-tp.csv').read().splitlines()
    except OSError:
        return out
    for l in lines[1:]:
        v = l.split(',')
        if len(v) == 6:
            out.append(dict(t=int(v[0]), phase=v[1], active=int(v[2]), pending=int(v[3]), completed=int(v[4]), dropped=int(v[5])))
    return out


def analyze():
    S = load_samples(); TP = tp_rows(); P = PHASES
    res = {}
    base_by_life = {}
    # harness defect H2 (2026-10-21): the filed lifetime-1 baseline and R5's L1 baseline share the label 'L1-baseline'
    # (and the histogram file name); baselines are therefore matched by their time stamp over all rows, not by label
    rows_all = [json.loads(l) for l in open(LOGS + '/samples-heap.jsonl')]
    for p in P:
        if p['kind'] == 'baseline':
            m = [r for r in rows_all if r['t'] == p['t']]
            if m:
                base_by_life[p['lifeB']] = m[0]
    H = {}
    for p in [p for p in P if p['kind'] == 'filed']:
        name = f'v{p["v"]}{p["tag"]}'
        r = S.get(name + '-t90'); b = base_by_life.get(p['lifeB'])
        if not r or not b:
            note(f'{name}: sample or baseline missing'); continue
        h = (r['heap_used'] - b['heap_used']) / MIB
        rows = [x for x in TP if x['phase'] == name and p['stress_start'] <= x['t'] <= p['stress_end']]
        p90 = min(rows, key=lambda x: abs(x['t'] - r['t']))['pending'] if rows else -1
        late = [x for x in rows if x['t'] >= p['stress_start'] + 60000 and x['t'] <= r['t']]
        H[name] = dict(H=h, P=p90, mut=r['mutation'], act=max([x['active'] for x in rows] or [-1]),
                       act_late=[x['active'] for x in late], pend_late=[x['pending'] for x in late], rate=p['stress'].get('op_rate'))
        note(f'{name}: H = {h:.1f} MiB (heap {r["heap_used"] / MIB:.1f} − baseline {b["heap_used"] / MIB:.1f}); P(t≈90) = {p90}; '
             f'Mutation {r["mutation"]}, CachedSerialization {r["cached"]}, byte[] {r["bytearr"] / MIB:.1f} MiB; Active max {H[name]["act"]}; '
             f'inbound using {r["inbound_using"] / MIB:.1f} + reserve {r["inbound_reserve"] / MIB:.1f} MiB; A histo {r.get("a_histo_total", -1) / MIB:.1f} MiB; stress {p["stress"]}')
    res['filed'] = H
    g = lambda k: H.get(k, {}).get('H')
    if all(k in H for k in ('v32', 'v8', 'v1', 'v0')):
        for k in ('v32', 'v8'):
            expect(f'B3f {k}: P ≤ 1000 ({H[k]["P"]}), H < 100 MiB ({H[k]["H"]:.1f}), Mutation ≤ 1000 ({H[k]["mut"]})',
                   H[k]['P'] <= 1000 and H[k]['H'] < 100 and H[k]['mut'] <= 1000)
        expect(f'B3f v1: H(1) not below H(32) by more than 50 MiB ({g("v1"):.1f} vs {g("v32"):.1f})', g('v1') >= g('v32') - 50)
        v0 = H['v0']
        expect(f'B3f v0: Active 0 in the plateau samples ({v0["act_late"]})', v0['act_late'] and max(v0['act_late']) == 0)
        expect(f'B3f v0: P plateau 90,000–150,000 ({v0["P"]})', 90000 <= v0['P'] <= 150000)
        pl = v0['pend_late']
        expect(f'B3f v0: P flat over t = 60–90 s (max/min {max(pl) / max(1, min(pl)) if pl else -1:.3f} ≤ 1.05)', bool(pl) and max(pl) <= 1.05 * min(pl))
        expect(f'B3f v0: H 130–550 MiB ({g("v0"):.1f})', 130 <= g('v0') <= 550)
        expect(f'B3f v0: Mutation instances ≈ P (within 20 %: {v0["mut"]} vs {v0["P"]})', v0['P'] > 0 and abs(v0['mut'] - v0['P']) <= 0.2 * v0['P'])
        row1 = g('v32') < 100 and g('v8') < 100 and g('v0') - g('v32') >= 100
        expect(f'B3g row 1 part: H(32), H(8) < 100 and H(0) − H(32) ≥ 100 MiB ({g("v32"):.1f}, {g("v8"):.1f}, {g("v0"):.1f})', row1)
        dec = g('v0') < g('v1') < g('v8') < g('v32') and g('v32') - g('v0') > 50
        expect('B3g row 2 (Refuted) NOT met: H does not decrease with v (R2 definition)', not dec)
    c = {R: H.get(f'v0-ctl{R}') for R in ('16MiB', '128MiB', '512MiB')}
    if all(c.values()):
        expect(f'B3f control 16MiB: P ≈ 18,000 (±40 %: {c["16MiB"]["P"]}), H 20–80 MiB ({c["16MiB"]["H"]:.1f})',
               10800 <= c['16MiB']['P'] <= 25200 and 20 <= c['16MiB']['H'] <= 80)
        expect(f'B3f control 128MiB: as v0 — P 90,000–150,000 ({c["128MiB"]["P"]}), H 130–550 ({c["128MiB"]["H"]:.1f})',
               90000 <= c['128MiB']['P'] <= 150000 and 130 <= c['128MiB']['H'] <= 550)
        expect(f'B3f control 512MiB: P ≈ 480,000 (±40 %: {c["512MiB"]["P"]}), H 0.5–2 GiB ({c["512MiB"]["H"]:.1f} MiB)',
               288000 <= c['512MiB']['P'] <= 672000 and 512 <= c['512MiB']['H'] <= 2048)
        hs = [c[R]['H'] for R in ('16MiB', '128MiB', '512MiB')]
        expect(f'B3f/R2 control: H ordered 16 < 128 < 512 and H(512)/H(16) ≥ 8 ({hs[0]:.1f}, {hs[1]:.1f}, {hs[2]:.1f})',
               hs[0] < hs[1] < hs[2] and hs[0] > 0 and hs[2] / hs[0] >= 8)
    if 'v32-rep' in H and 'v0-rep' in H and 'v32' in H and 'v0' in H:
        expect(f'R3 drift: |H(32 rep) − H(32)| ≤ 50 ({g("v32-rep"):.1f} vs {g("v32"):.1f}), |H(0 rep) − H(0)| ≤ 50 ({g("v0-rep"):.1f} vs {g("v0"):.1f}), '
               f'P(0 rep) within 25 % ({H["v0-rep"]["P"]} vs {H["v0"]["P"]})',
               abs(g('v32-rep') - g('v32')) <= 50 and abs(g('v0-rep') - g('v0')) <= 50 and abs(H['v0-rep']['P'] - H['v0']['P']) <= 0.25 * H['v0']['P'])
    # R5
    B = {}
    for p in [p for p in P if p['kind'] == 'bind']:
        lab = f'{p["size"]}{p["v"]}'
        b = S.get(lab + '-baseline'); r = S.get(lab + '-t60')
        if not b or not r:
            note(f'{lab}: sample missing'); continue
        rows = [x for x in TP if x['phase'] == lab and p['stress_start'] + 20000 <= x['t'] <= r['t']]
        v = p['v']
        bind_frac = sum(1 for x in rows if x['active'] >= 0.9 * v) / len(rows) if rows else 0
        plate = [x['pending'] for x in rows if x['t'] >= p['stress_start'] + 30000]
        p60 = min(rows, key=lambda x: abs(x['t'] - r['t']))['pending'] if rows else -1
        B[lab] = dict(v=v, size=p['size'], H=(r['heap_used'] - b['heap_used']) / MIB, bind_frac=bind_frac,
                      act=[x['active'] for x in rows], P=p60, plate=plate,
                      inbound=r['inbound_using'] / MIB,
                      net=(r['net_used'] + r['net_overflow'] - b['net_used'] - b['net_overflow']) / MIB,
                      direct=(r['direct'] - b['direct']) / MIB, mut=r['mutation'], cached=r['cached'],
                      bytearr=(r['bytearr'] - b['bytearr']) / MIB, rate=p['stress'].get('op_rate'))
        x = B[lab]
        note(f'{lab}: H = {x["H"]:.1f} MiB; Active ≥ 0.9v at {x["bind_frac"] * 100:.0f} % of {len(rows)} samples (t 20–60 s: {x["act"]}); '
             f'P(t≈60) {x["P"]}; inbound using_bytes {x["inbound"]:.1f} MiB; networking pool used+overflow Δ {x["net"]:.1f} MiB; '
             f'direct Δ {x["direct"]:.1f} MiB; Mutation {x["mut"]}, CachedSerialization {x["cached"]}, byte[] Δ {x["bytearr"]:.1f} MiB; stress {p["stress"]}')
        expect(f'R5(a) {lab}: Active ≥ 0.9 v at ≥ 80 % of samples ({x["bind_frac"] * 100:.0f} %)', x['bind_frac'] >= 0.8)
        pl = x['plate']; mean = sum(pl) / len(pl) if pl else 0
        expect(f'R5(a) {lab}: Pending at a plateau over t = 30–60 s (all within ±10 % of mean {mean:.0f}: {pl})',
               bool(pl) and all(abs(q - mean) <= 0.1 * mean for q in pl))
        expect(f'R5(b) {lab}: reserve usage (internode_inbound using_bytes, which includes the reserve part) 100–140 MiB ({x["inbound"]:.1f})', 100 <= x['inbound'] <= 140)
        if p['size'] == 'S':
            expect(f'R5(b) {lab}: Pending 3,000–5,500 ({x["P"]})', 3000 <= x['P'] <= 5500)
            expect(f'R5(c) {lab}: H_S 185–345 MiB ({x["H"]:.1f})', 185 <= x['H'] <= 345)
        else:
            e = 528 - v
            expect(f'R5(b) {lab}: Pending ≈ 528 − v = {e} (±25 %: {x["P"]})', 0.75 * e <= x['P'] <= 1.25 * e)
    res['bind'] = B
    Sv = [B.get(f'S{v}') for v in (1, 8, 32, 128)]; Lv = [B.get(f'L{v}') for v in (1, 8, 32, 128)]
    if all(Sv) and all(Lv):
        hs = [x['H'] for x in Sv]; hl = [x['H'] for x in Lv]
        flat = lambda h: (min(h) > 0 and max(h) / min(h) <= 1.2) or (max(h) - min(h) <= 30)
        s_flat = flat(hs); l_flat = flat(hl)
        expect(f'R5(c) H_S flat over v = 1,8,32,128 ({", ".join(f"{h:.1f}" for h in hs)})', s_flat)
        l_inc = hl[1] < hl[2] < hl[3] and hl[3] - hl[0] >= 40
        expect(f'R5(d) H_L increasing over 8 < 32 < 128 with H_L(128) − H_L(1) ≥ 40 MiB ({", ".join(f"{h:.1f}" for h in hl)})', l_inc)
        nl = [x['net'] for x in Lv]
        expect(f'R5(d) L networking pool used+overflow larger at v = 1 than at v = 128 ({nl[0]:.1f} vs {nl[3]:.1f} MiB)', nl[0] > nl[3])
        s_inc = hs[3] - hs[0] >= 40 and hs[0] < hs[1] < hs[2] < hs[3]
        bound = all(x['bind_frac'] >= 0.8 for x in Sv + Lv)
        if not bound:
            row = 'BIND-4'
        elif s_flat and l_flat:
            row = 'BIND-1'
        elif s_flat and l_inc:
            row = 'BIND-2'
        elif s_inc and l_inc:
            row = 'BIND-3'
        else:
            row = 'BIND-5'
        note(f'R5 row by the rules: {row} (bound {bound}, S flat {s_flat}, S increasing {s_inc}, L flat {l_flat}, L increasing {l_inc})')
        res['bind_row'] = row
    json.dump(res, open(LOGS + '/analysis.json', 'w'), indent=1, default=str)


def main():
    note(f'cluster-run all {time.strftime("%F %T %Z")} host {os.uname().nodename} clone {C}; free {free_gb():.1f} GB; only={ONLY!r}')
    _, md5 = sh(f'cd {HARNESS} && md5sum cluster-run.py make-node-yaml.sh Jmx.java', check=False, quiet=True)
    note('harness md5 ' + ' '.join(f'{l.split()[1]}={l.split()[0][:12]}' for l in md5.splitlines() if l.strip()))
    if my_daemons():
        fail('a node of this harness is running before the start')
    sh(f'rm -rf {MPSN}/A {MPSN}/B; mkdir -p {JMXCP}')
    sh(f'javac -d {JMXCP} {HARNESS}/Jmx.java')
    try:
        if ONLY != 'bind':
            run_filed()
        run_bind()
    except SystemExit:
        raise
    except Exception as e:
        fail(f'exception: {e!r}')
    analyze()
    kill_children()
    stop_node('B'); stop_node('A')
    note(f'nodes stopped; leftover daemons of this harness: {len(my_daemons())}')
    sh(f'du -sb {MPSN}', check=False)
    sh(f'rm -rf {MPSN}/A/data {MPSN}/B/data {MPSN}/A/commitlog {MPSN}/B/commitlog {MPSN}/A/hints {MPSN}/B/hints', check=False)
    note(f'EXPECTED tally: {EXPECT["yes"]} yes, {EXPECT["no"]} NO; done {time.strftime("%F %T %Z")}')


if MODE == 'reanalyze':
    PHASES.extend(json.load(open(LOGS + '/phases.json')))
    analyze()
    note(f'EXPECTED tally (reanalysis): {EXPECT["yes"]} yes, {EXPECT["no"]} NO')
elif MODE == 'down':
    for n in ('B', 'A'):
        try:
            STATE['pid'][n] = int(open(f'{MPSN}/{n}/cassandra.pid').read().strip())
        except (OSError, ValueError):
            pass
        stop_node(n)
else:
    main()
