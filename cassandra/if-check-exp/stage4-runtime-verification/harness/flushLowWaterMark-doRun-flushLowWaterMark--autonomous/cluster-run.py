#!/usr/bin/env python3
"""Cluster tier (B3) of flushLowWaterMark-doRun-flushLowWaterMark--autonomous (frozen sha256 f754e36f...).

usage: python3 cluster-run.py <run> <variant> <rep>     one lifetime of both nodes (B3e steps 1-8), variant V0..V4, rep 1|2
       python3 cluster-run.py <run> analyze             cross-lifetime relations (B3f, A9; the B3g/A10 rows are judged by hand)
       python3 cluster-run.py <run> reanalyse <V> <rep> re-run one lifetime's analysis from its files
       python3 cluster-run.py <run> down                stop any node of any variant tree (B is SIGCONTed first)
       python3 cluster-run.py <run> shake               shakedown: V0, 20 s stress, no freeze; instruments only

One lifetime (amendments A5-A8): wipe the tmpfs node dirs; both yamls (make-node-yaml.sh); start A (Byteman script
flw.btm, trace to the lifetime's dir) and wait UN + binary; start B; wait 2 UN; start the JMX poller (500 ms), the
internode_outbound sampler (2 s) and an ss sampler (2 s); start cassandra-stress (A6) = t0; t0+15 s SIGSTOP B (= pause);
t0+40 s SIGCONT B; wait for stress; 10 s; stop the samplers; final vt read; copy logs and trace; stop both nodes (B SIGCONTed
first, on any exit); check no daemon of any variant tree is left.
Reading rules (fixed in the case file before run 1, A7/A9): pre window [pause-11 s, pause-1 s]; plateau window
[pause+10 s, pause+22 s]; D = median(UsedSize, plateau) - median(UsedSize, pre); D_direct likewise for direct MemoryUsed.
Logs: ~/stage4-logs/flw/<run>/cluster/<variant>-r<rep>/.
"""
import json, os, re, signal, statistics, subprocess, sys, time

HOME = os.path.expanduser('~')
H = os.path.dirname(os.path.abspath(__file__))
FLW = HOME + '/stage4-flw'
DATA = FLW + '/nodes'
NODES = {'A': ('127.0.0.1', 7199), 'B': ('127.0.0.2', 7299)}
MIB = 1 << 20
TREES = {'V0': HOME + '/cassandra-flw', 'V1': HOME + '/cassandra-flw-p1', 'V2': HOME + '/cassandra-flw-p2',
         'V3': HOME + '/cassandra-flw-p3', 'V4': HOME + '/cassandra-flw-p4'}
HL = {'V0': (65536, 32768), 'V1': (1 << 26, 1 << 10), 'V2': (1 << 26, 1 << 25), 'V3': (1 << 26, (1 << 26) - (1 << 20)),
      'V4': (1 << 22, 1 << 21)}
SCOPE = '127.0.0.2_7000'
BEANS = [("org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=UsedSize", 'Value', 'used'),
         ("java.nio:type=BufferPool,name=direct", 'MemoryUsed', 'direct'),
         (f"org.apache.cassandra.metrics:type=Connection,scope={SCOPE},name=SmallMessagePendingBytes", 'Value', 'smallPending'),
         (f"org.apache.cassandra.metrics:type=Connection,scope={SCOPE},name=UrgentMessagePendingBytes", 'Value', 'urgentPending'),
         (f"org.apache.cassandra.metrics:type=Connection,scope={SCOPE},name=SmallMessageDroppedTasksDueToOverload", 'Value', 'smallOverload'),
         ("java.lang:type=Memory", 'HeapMemoryUsage', 'heap')]
COLS = [b[2] for b in BEANS]
BYTEMAN = 'build/lib/jars/byteman-4.0.20.jar'

RUN = sys.argv[1]
OUT = f'{HOME}/stage4-logs/flw/{RUN}/cluster'
LOGF = None
C_HOME = TREES['V0']


def log(s):
    line = f'{time.strftime("%H:%M:%S")} {int(time.time()*1000)} {s}'
    print(line, flush=True)
    if LOGF:
        LOGF.write(line + '\n'); LOGF.flush()


def sh(cmd, timeout=600, check=True, env=None, quiet=False):
    if not quiet:
        log(f'$ {cmd}')
    p = subprocess.run(cmd, shell=True, cwd=C_HOME, env=env, timeout=timeout, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, text=True)
    if not quiet:
        for l in p.stdout.strip().splitlines()[-15:]:
            log(f'  | {l}')
    if check and p.returncode != 0:
        raise RuntimeError(f'command failed rc={p.returncode}: {cmd}')
    return p.returncode, p.stdout


def daemons():
    """java processes running CassandraDaemon whose cwd is a variant tree or whose args name this run's conf: {pid: args}"""
    r = {}
    for l in subprocess.run(['ps', '-eo', 'pid=,args='], stdout=subprocess.PIPE, text=True).stdout.splitlines():
        pid, _, args = l.strip().partition(' ')
        if not (args.split(' ')[0].endswith('java') and 'CassandraDaemon' in args):
            continue
        try:
            cwd = os.readlink(f'/proc/{pid}/cwd')
        except OSError:
            cwd = ''
        if cwd in TREES.values() or f'{FLW}/' in args:
            r[int(pid)] = args
    return r


def pid_of(node):
    try:
        return int(open(f'{FLW}/{node}/cassandra.pid').read().strip())
    except Exception:
        return None


def alive(pid):
    return pid is not None and pid in daemons()


def stop_node(node):
    pid = pid_of(node)
    if not alive(pid):
        return
    os.kill(pid, signal.SIGCONT)
    sh(f'bin/nodetool -p {NODES[node][1]} stopdaemon', check=False, timeout=180)
    for _ in range(60):
        if not alive(pid):
            log(f'{node} stopped'); return
        time.sleep(1)
    log(f'{node} did not stop; kill -9 {pid}')
    os.kill(pid, signal.SIGKILL)


def stop_all():
    for n in ('B', 'A'):
        try:
            stop_node(n)
        except Exception as e:
            log(f'stop {n}: {e!r}')
    for pid in daemons():
        log(f'leftover daemon {pid}; SIGCONT + kill -9')
        try:
            os.kill(pid, signal.SIGCONT); os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    time.sleep(1)
    log(f'daemons of the variant trees left: {len(daemons())}')


def start_node(node, extra=None):
    sh(f'CASSANDRA_HOME={C_HOME} bash {H}/make-node-yaml.sh {node}')
    N = f'{FLW}/{node}'
    env = dict(os.environ, CASSANDRA_CONF=N + '/conf', CASSANDRA_LOG_DIR=N + '/logs', MAX_HEAP_SIZE='4G', HEAP_NEWSIZE='800M')
    env.pop('JVM_EXTRA_OPTS', None)
    if extra:
        env['JVM_EXTRA_OPTS'] = extra
    sh(f'ulimit -n 100000 && bin/cassandra -p {N}/cassandra.pid > {N}/stdout.txt 2>&1', env=env)


def wait_up(n_up, timeout=300):
    t = time.time()
    while time.time() - t < timeout:
        for node in NODES:
            p = pid_of(node)
            if p is not None and not alive(p) and time.time() - t > 15:
                raise RuntimeError(f'{node} died during start')
        _, st = sh('bin/nodetool -p 7199 status', check=False, quiet=True)
        _, sb = sh('bin/nodetool -p 7199 statusbinary', check=False, quiet=True)
        ups = len(re.findall(r'^UN ', st, re.M))
        if ups >= n_up and 'running' in sb:
            log(f'{ups} UN after {time.time()-t:.0f} s'); return st
        time.sleep(3)
    raise RuntimeError('nodes not up')


def lifetime(variant, rep, shake=False):
    global LOGF, C_HOME
    C_HOME = TREES[variant]
    D = f'{OUT}/{variant}-r{rep}'
    os.makedirs(D, exist_ok=True)
    LOGF = open(f'{D}/session.log', 'a')
    log(f'=== lifetime {variant} rep {rep} tree {C_HOME} harness {H} expected (H,L)={HL[variant]} shake={shake}')
    if daemons():
        raise RuntimeError(f'daemons already running: {daemons()}')
    if subprocess.run(['mountpoint', '-q', DATA]).returncode != 0:
        raise RuntimeError(f'{DATA} not mounted')
    sh(f'rm -rf {DATA}/A {DATA}/B; mkdir -p {FLW}/A {FLW}/B; df -h {DATA} / | tail -2')
    for node in ('A', 'B'):
        lg = f'{FLW}/{node}/logs'
        if os.path.isdir(lg):
            sh(f'rm -rf {lg}', quiet=True)
    sh("sed -n 104p src/java/org/apache/cassandra/net/OutboundConnectionSettings.java")
    trace = f'{D}/flw.trace'
    if os.path.exists(trace):
        os.rename(trace, trace + f'.prev-{int(time.time())}')
    btm = f'{D}/flw.btm'
    open(btm, 'w').write(open(f'{H}/flw.btm.in').read().replace('@TRACE@', trace))
    stopf = f'{D}/stop'
    procs = []
    res = {'variant': variant, 'rep': rep, 'H': HL[variant][0], 'L': HL[variant][1], 'tree': C_HOME}
    try:
        if os.path.exists(stopf):
            os.remove(stopf)
        start_node('A', f'-javaagent:{C_HOME}/{BYTEMAN}=script:{btm}')
        wait_up(1)
        start_node('B')
        st = wait_up(2)
        open(f'{D}/status.txt', 'w').write(st)
        for node in ('A', 'B'):
            sh(f'cp {FLW}/{node}/conf/cassandra.yaml {D}/{node}-cassandra.yaml; diff {FLW}/{node}/shipped.yaml {FLW}/{node}/conf/cassandra.yaml > {D}/{node}-yaml.diff', check=False, quiet=True)
        os.makedirs(f'{FLW}/jmx-classes', exist_ok=True)
        sh(f'javac -d {FLW}/jmx-classes {H}/Jmx.java', quiet=True)
        beanargs = ' '.join(f"'{b}' {a}" for b, a, _ in BEANS)
        open(f'{D}/jmx.csv', 'w').write('ms,' + ','.join(COLS) + '\n')
        procs.append(subprocess.Popen(f'exec java -cp {FLW}/jmx-classes Jmx 7199 poll 500 100000 {stopf} {beanargs} >> {D}/jmx.csv 2> {D}/jmx.err', shell=True))
        procs.append(subprocess.Popen(['python3', f'{H}/sample-vt.py', '127.0.0.1', 'outbound', '2.0', stopf, f'{D}/vt-out.csv'],
                                      stdout=open(f'{D}/vt.out', 'w'), stderr=subprocess.STDOUT, env=dict(os.environ, CASSANDRA_HOME=C_HOME)))
        procs.append(subprocess.Popen(f'while [ ! -e {stopf} ]; do echo "T $(date +%s%3N)"; ss -tmn dst 127.0.0.2:7000; sleep 2; done > {D}/ss.txt 2>&1', shell=True))
        time.sleep(3)
        dur = 20 if shake else 60
        stress = (f'tools/bin/cassandra-stress write duration={dur}s cl=ONE no-warmup '
                  f'-schema "replication(strategy=SimpleStrategy,factor=2)" keyspace=fwm -col "size=FIXED(2048)" "n=FIXED(1)" '
                  f'-rate threads=64 fixed=20000/s -node whitelist 127.0.0.1 -mode native cql3 -log interval=1s')
        log(f'$ {stress}')
        t0 = time.time(); res['t0'] = int(t0 * 1000)
        ps = subprocess.Popen(stress, shell=True, cwd=C_HOME, stdout=open(f'{D}/stress.log', 'w'), stderr=subprocess.STDOUT,
                              env={k: v for k, v in os.environ.items() if k not in ('CASSANDRA_CONF', 'JVM_EXTRA_OPTS')})
        procs.append(ps)

        def at(sec):
            w = t0 + sec - time.time()
            if w > 0:
                time.sleep(w)
        pB = pid_of('B')
        if not shake:
            at(15)
            os.kill(pB, signal.SIGSTOP); res['pause'] = int(time.time() * 1000)
            log(f'SIGSTOP B pid {pB}')
            at(40)
            os.kill(pB, signal.SIGCONT); res['cont'] = int(time.time() * 1000)
            log(f'SIGCONT B pid {pB}')
        else:
            at(15); res['pause'] = int(time.time() * 1000); res['cont'] = res['pause']
        rc = ps.wait(timeout=400)
        log(f'stress exit {rc}')
        time.sleep(10)
        open(stopf, 'w').close()
        for p in procs:
            try:
                p.wait(timeout=20)
            except subprocess.TimeoutExpired:
                p.kill()
        res['end'] = int(time.time() * 1000)
        sh(f'python3 {H}/sample-vt.py 127.0.0.1 outbound 1 {stopf} {D}/vt-final.csv once', check=False, env=dict(os.environ, CASSANDRA_HOME=C_HOME))
        for node in ('A', 'B'):
            for f in ('system.log', 'debug.log'):
                sh(f'cp {FLW}/{node}/logs/{f} {D}/{node}-{f} 2>/dev/null || true', check=False, quiet=True)
            sh(f'cp {FLW}/{node}/stdout.txt {D}/{node}-stdout.txt 2>/dev/null || true', check=False, quiet=True)
    finally:
        open(stopf, 'w').close()
        for p in procs:
            if p.poll() is None:
                p.kill()
        stop_all()
    json.dump(res, open(f'{D}/times.json', 'w'))
    analyse(D, res)
    LOGF.close()


def read_jmx(path):
    rows = []
    for l in open(path):
        f = l.strip().split(',')
        if len(f) != len(COLS) + 1 or not f[0].isdigit():
            continue
        r = {'ms': int(f[0])}
        for k, v in zip(COLS, f[1:]):
            try:
                r[k] = int(v)
            except ValueError:
                r[k] = None
        rows.append(r)
    return rows


def read_vt(path):
    rows = []
    keys = ['using_bytes', 'using_reserve_bytes', 'pending_count', 'pending_bytes', 'sent_count', 'sent_bytes', 'expired_count',
            'error_count', 'overload_count', 'overload_bytes', 'active_connections', 'connection_attempts',
            'successful_connection_attempts']
    if not os.path.exists(path):
        return rows
    for l in open(path):
        f = l.strip().split(',')
        if len(f) < 3 + len(keys) or not f[0].isdigit() or f[1] != '127.0.0.2':
            continue
        rows.append(dict(ms=int(f[0]), **{k: int(v) for k, v in zip(keys, f[3:3 + len(keys)])}))
    return rows


def read_trace(path):
    st, rs = [], []
    if not os.path.exists(path):
        return st, rs
    for l in open(path):
        f = l.split()
        if len(f) >= 8 and f[0] == 'STALL':
            st.append(dict(ms=int(f[1]), type=f[2], to=f[3], id=f[4], f=int(f[5]), H=int(f[6]), L=int(f[7])))
        elif len(f) >= 7 and f[0] == 'RESUME':
            rs.append(dict(ms=int(f[1]), type=f[2], to=f[3], id=f[4], f=int(f[5]), L=int(f[6])))
    return st, rs


def med(v):
    return statistics.median(v) if v else None


def analyse(D, res):
    S = []
    def say(s):
        S.append(s); log(s)
    Hh, Ll = res['H'], res['L']
    p0, pc = res['pause'], res['cont']
    rows = read_jmx(f'{D}/jmx.csv')
    vt = read_vt(f'{D}/vt-out.csv')
    say(f'{res["variant"]} rep {res["rep"]}: H={Hh} L={Ll}; jmx samples {len(rows)}, vt samples {len(vt)}; freeze {p0}..{pc} ({(pc-p0)/1000:.1f} s)')
    pre = [r for r in rows if p0 - 11000 <= r['ms'] <= p0 - 1000]
    pla = [r for r in rows if p0 + 10000 <= r['ms'] <= p0 + 22000]
    def mv(rr, k):
        return med([r[k] for r in rr if r.get(k) is not None])
    out = {}
    for k in ('used', 'direct', 'smallPending', 'heap'):
        a, b = mv(pre, k), mv(pla, k)
        out[k] = (a, b, None if a is None or b is None else b - a)
        say(f'  {k}: pre median {a} (n={len(pre)}), plateau median {b} (n={len(pla)}), delta {out[k][2]}'
            + ('' if out[k][2] is None else f' = {out[k][2]/MIB:.3f} MiB'))
    pla_used = [r['used'] for r in pla if r.get('used') is not None]
    say(f'  UsedSize in plateau window min/max {min(pla_used) if pla_used else None}/{max(pla_used) if pla_used else None}')
    fr = [r for r in rows if p0 <= r['ms'] <= pc]
    sp = [r['smallPending'] for r in fr if r.get('smallPending') is not None]
    say(f'  Small PendingBytes during freeze: max {max(sp) if sp else None}; median in plateau {mv(pla, "smallPending")}')
    vfr = [r for r in vt if p0 <= r['ms'] <= pc]
    if vfr:
        say(f'  vt during freeze: pending_bytes max {max(r["pending_bytes"] for r in vfr)}, active_connections min/max '
            f'{min(r["active_connections"] for r in vfr)}/{max(r["active_connections"] for r in vfr)}, connection_attempts '
            f'{vfr[0]["connection_attempts"]}->{vfr[-1]["connection_attempts"]}, overload_count {vfr[0]["overload_count"]}->{vfr[-1]["overload_count"]}, '
            f'expired_count {vfr[0]["expired_count"]}->{vfr[-1]["expired_count"]}')
    st, rs = read_trace(f'{D}/flw.trace')
    hl = sorted({(s['H'], s['L']) for s in st})
    say(f'  trace: STALL {len(st)}, RESUME {len(rs)}; (H,L) seen {hl}; expected {(Hh, Ll)}')
    bad_hl = [s for s in st if (s['H'], s['L']) != (Hh, Ll)]
    out_rng = [s for s in st if not (Hh <= s['f'] < Hh + 65536)]
    bad_res = [r for r in rs if r['f'] > Ll]
    say(f'  STALL with (H,L) != variant: {len(bad_hl)}; STALL level outside [H, H+65536): {len(out_rng)}'
        + (f' e.g. {out_rng[:3]}' if out_rng else '') + f'; RESUME level > L: {len(bad_res)}' + (f' e.g. {bad_res[:3]}' if bad_res else ''))
    if st:
        say(f'  STALL level min/max over all: {min(s["f"] for s in st)}/{max(s["f"] for s in st)}; types {sorted({s["type"] for s in st})}')
    if rs:
        say(f'  RESUME level min/median/max: {min(r["f"] for r in rs)}/{med([r["f"] for r in rs])}/{max(r["f"] for r in rs)}')
    sf = [s for s in st if p0 <= s['ms'] <= pc and s['type'] == 'SMALL_MESSAGES' and '127.0.0.2' in s['to']]
    say(f'  small-link STALLs to 127.0.0.2 inside the freeze: {len(sf)}; max level {max((s["f"] for s in sf), default=None)}'
        f'; first at pause+{(sf[0]["ms"]-p0)/1000 if sf else None} s')
    sb = [s for s in st if s['ms'] < p0]
    say(f'  STALLs before the freeze: {len(sb)}; RESUMEs before the freeze: {len([r for r in rs if r["ms"] < p0])}')
    logs = {}
    for node in ('A', 'B'):
        f = f'{D}/{node}-system.log'
        if os.path.exists(f):
            t = open(f).read()
            logs[node] = t
            say(f'  {node} system.log: ERROR {len(re.findall(r"^ERROR", t, re.M))}, WARN {len(re.findall(r"^WARN", t, re.M))}, '
                f'"Interrupted outbound connections to /127.0.0.2" {t.count("Interrupted outbound connections to /127.0.0.2")}, '
                f'"is now DOWN" {t.count("is now DOWN")}, OutOfMemoryError {t.count("java.lang.OutOfMemoryError")}')
    for l in logs.get('A', '').splitlines():
        if 'is now DOWN' in l or 'Interrupted outbound' in l or 'is now UP' in l or 'overloaded; dropping' in l:
            say('    A log: ' + l.strip()[:250])
    sto = open(f'{D}/stress.log').read() if os.path.exists(f'{D}/stress.log') else ''
    for k in ('Op rate', 'Total errors', 'Total partitions', 'Total operation time'):
        m = re.search(r'^' + k + r'.*$', sto, re.M)
        say(f'  stress {m.group(0) if m else k + ": missing"}')
    rec = dict(res, D=out['used'][2], D_direct=out['direct'][2], pre_used=out['used'][0], pla_used=out['used'][1],
               heap_delta=out['heap'][2], small_pending_freeze_max=max(sp) if sp else None,
               vt_pending_freeze_max=max((r['pending_bytes'] for r in vfr), default=None),
               vt_active_min=min((r['active_connections'] for r in vfr), default=None),
               stalls=len(st), resumes=len(rs), hl_seen=hl, stall_bad_hl=len(bad_hl), stall_out_of_range=len(out_rng),
               resume_gt_L=len(bad_res), small_freeze_stalls=len(sf), small_freeze_stall_max=max((s['f'] for s in sf), default=None),
               stall_max=max((s['f'] for s in st), default=None), stall_min=min((s['f'] for s in st), default=None),
               resume_max=max((r['f'] for r in rs), default=None),
               interrupted=logs.get('A', '').count('Interrupted outbound connections to /127.0.0.2'),
               down=logs.get('A', '').count('is now DOWN'))
    json.dump(rec, open(f'{D}/readings.json', 'w'), indent=1)
    open(f'{D}/summary.txt', 'w').write('\n'.join(S) + '\n')


def analyze():
    S = []
    def say(s):
        S.append(s); print(s)
    R = {}
    for v in ('V0', 'V1', 'V2', 'V3', 'V4'):
        for rep in (1, 2):
            f = f'{OUT}/{v}-r{rep}/readings.json'
            if os.path.exists(f):
                R[(v, rep)] = json.load(open(f))
    say('lifetime: D (MiB), D_direct (MiB), small-link freeze stall max, stall levels min..max, resume max, (H,L) seen, '
        'bad (H,L), out-of-range stalls, resume>L, vt pending max (MiB), active min, interrupted, down')
    for (v, rep), r in sorted(R.items()):
        f = lambda x: None if x is None else round(x / MIB, 3)
        say(f'  {v}-r{rep}: D {f(r["D"])}, D_direct {f(r["D_direct"])}, smallFreezeStallMax {r["small_freeze_stall_max"]}, '
            f'stalls {r["stall_min"]}..{r["stall_max"]} (n={r["stalls"]}), resumeMax {r["resume_max"]} (n={r["resumes"]}), '
            f'HL {r["hl_seen"]}, badHL {r["stall_bad_hl"]}, outOfRange {r["stall_out_of_range"]}, resume>L {r["resume_gt_L"]}, '
            f'vtPendingMax {f(r["vt_pending_freeze_max"])}, activeMin {r["vt_active_min"]}, interrupted {r["interrupted"]}, down {r["down"]}')
    mean = {}
    for v in ('V0', 'V1', 'V2', 'V3', 'V4'):
        ds = [R[(v, rep)]['D'] for rep in (1, 2) if (v, rep) in R and R[(v, rep)]['D'] is not None]
        if ds:
            mean[v] = statistics.mean(ds)
            say(f'{v}: mean D = {mean[v]/MIB:.3f} MiB over {len(ds)} lifetimes')
    if all(v in mean for v in ('V1', 'V2', 'V3')):
        m = [mean['V1'], mean['V2'], mean['V3']]
        pair = max(abs(a - b) for a in m for b in m)
        mono = (m[0] <= m[1] <= m[2]) or (m[0] >= m[1] >= m[2])
        say(f'V1-V3 means (L ascending 1 KiB, 32 MiB, 63 MiB): {[round(x/MIB,3) for x in m]}; max pairwise |diff| = {pair/MIB:.3f} MiB '
            f'(<= 4 MiB: {pair <= 4*MIB}); monotone in L: {mono}; ordered by L (monotone and spread > 4 MiB): {mono and pair > 4*MIB}')
        inr = {f'{v}-r{rep}': (64 * MIB <= R[(v, rep)]['D'] <= 70 * MIB) for v in ('V1', 'V2', 'V3') for rep in (1, 2) if (v, rep) in R}
        say(f'each V1-V3 lifetime D in [64, 70] MiB: {inr}')
    if 'V4' in mean:
        inr4 = {f'V4-r{rep}': (4 * MIB <= R[("V4", rep)]['D'] <= 8 * MIB) for rep in (1, 2) if ('V4', rep) in R}
        say(f'each V4 lifetime D in [4, 8] MiB: {inr4}')
        if 'V2' in mean:
            say(f'D(V2) - D(V4) = {(mean["V2"]-mean["V4"])/MIB:.3f} MiB (>= 56 MiB: {mean["V2"]-mean["V4"] >= 56*MIB})')
    if 'V0' in mean:
        say(f'D(V0) mean {mean["V0"]/MIB:.3f} MiB (< 1 MiB: {mean["V0"] < MIB})')
    os.makedirs(f'{OUT}/analyze', exist_ok=True)
    open(f'{OUT}/analyze/summary.txt', 'w').write('\n'.join(S) + '\n')


if __name__ == '__main__':
    what = sys.argv[2]
    if what == 'analyze':
        analyze()
    elif what == 'down':
        stop_all()
    elif what == 'reanalyse':
        Dd = f'{OUT}/{sys.argv[3]}-r{sys.argv[4]}'
        LOGF = open(f'{Dd}/session.log', 'a')
        analyse(Dd, json.load(open(f'{Dd}/times.json')))
    elif what == 'shake':
        lifetime('V0', 0, shake=True)
    else:
        lifetime(what, int(sys.argv[3]))
