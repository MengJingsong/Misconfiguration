#!/usr/bin/env python3
"""Cluster tier (B3) of OTCP_LARGE_MESSAGE_THRESHOLD-doRun-maxSendBytes--autonomous.

usage: python3 cluster-run.py <run> <label>        one lifetime of both nodes (B3e step 2)
       python3 cluster-run.py <run> analyze        B3f/B3g over all lifetimes (amendment S4-A9's rows, in its order)
       python3 cluster-run.py <run> down           stop any node of this clone (n2 SIGCONTed first)
Labels: v16k-<r>, v64k-<r>, v128k-<r> (V = 16384 / 65536 / 131072 on both nodes; send C 1 MiB, endpoint 2 MiB (send and,
S4-A6, receive key), global 4 MiB, internode_max_message_size 1 MiB) and ctl-<r> (V 65536; C 16 MiB, endpoint 16 MiB,
global 32 MiB: the positive control), r = 1, 2.

One lifetime: wipe ~/stage4-otc/n{1,2}/data and move logs aside; both yamls (make-node-yaml.sh); start n1 with
JVM_EXTRA_OPTS="-Dcassandra.otcp_large_message_threshold=V -XX:NativeMemoryTracking=summary", MAX_HEAP_SIZE=4G,
HEAP_NEWSIZE=800M, wait UN + binary; start n2 likewise, wait 2 UN; check each daemon's command line carries V; start the
JMX poller on n1 (Jmx.java poll, 1 s, S4-A8); t0 = start of cassandra-stress (S4-A7: 90 s, fixed 30,000/s, whitelist n1);
t0+30 s SIGSTOP n2; stall+12 s GC.class_histogram of n1; stall+15 s VM.native_memory summary of n1; t0+50 s SIGCONT n2;
wait for stress; 10 s; stop the poller; copy logs; nodetool drain both; stop both (n2 SIGCONTed first on any exit);
check no java of this clone is left; remove node data.
Reading rules (S4-A9): stall window = [SIGSTOP, SIGCONT]; pending peak = max SmallMessagePendingBytes in the window;
UsedSize / direct = max in the window minus the median over [t0+10 s, t0+25 s].
Logs: ~/stage4-logs/otc/<run>/cluster/<label>/.
"""
import json, os, re, signal, statistics, subprocess, sys, time

HOME = os.path.expanduser('~')
C_HOME = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-otc')
H = os.path.dirname(os.path.abspath(__file__))
OTC = HOME + '/stage4-otc'
NODES = {'n1': ('127.0.0.1', 7199), 'n2': ('127.0.0.2', 7299)}
MIB = 1 << 20
KIB = 1 << 10
MAIN = dict(C=1, E=2, G=4)
CTL = dict(C=16, E=16, G=32)
LABELS = {}
for r in (1, 2):
    LABELS[f'v16k-{r}'] = dict(V=16384, **MAIN)
    LABELS[f'v64k-{r}'] = dict(V=65536, **MAIN)
    LABELS[f'v128k-{r}'] = dict(V=131072, **MAIN)
    LABELS[f'ctl-{r}'] = dict(V=65536, ctl=True, **CTL)
LABELS['shake'] = dict(V=65536, duration=20, nostop=True, **MAIN)
ORDER = ['v16k-1', 'v64k-1', 'v128k-1', 'ctl-1', 'v16k-2', 'v64k-2', 'v128k-2', 'ctl-2']
SCOPE = '127.0.0.2_7000'
BEANS = [(f'org.apache.cassandra.metrics:type=Connection,scope={SCOPE},name=SmallMessagePendingBytes', 'Value', 'pending'),
         (f'org.apache.cassandra.metrics:type=Connection,scope={SCOPE},name=SmallMessageDroppedBytesDueToOverload', 'Value', 'dropBytes'),
         (f'org.apache.cassandra.metrics:type=Connection,scope={SCOPE},name=SmallMessageDroppedTasksDueToTimeout', 'Value', 'dropTimeout'),
         (f'org.apache.cassandra.metrics:type=Connection,scope={SCOPE},name=UrgentMessagePendingBytes', 'Value', 'urgentPending'),
         (f'org.apache.cassandra.metrics:type=Connection,scope={SCOPE},name=LargeMessagePendingBytes', 'Value', 'largePending'),
         ('org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=UsedSize', 'Value', 'used'),
         ('org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=OverflowSize', 'Value', 'overflow'),
         ('org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=Size', 'Value', 'poolSize'),
         ('java.nio:type=BufferPool,name=direct', 'MemoryUsed', 'direct'),
         ('java.lang:type=Memory', 'HeapMemoryUsage', 'heapUsed')]
COLS = [c for _, _, c in BEANS]

RUN = sys.argv[1]
OUT = f'{HOME}/stage4-logs/otc/{RUN}/cluster'
LOGF = None


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
    """java processes of this clone running CassandraDaemon: {pid: cmd} (command lines show only bin/../)"""
    r = {}
    for l in subprocess.run(['ps', '-eo', 'pid=,args='], stdout=subprocess.PIPE, text=True).stdout.splitlines():
        pid, _, args = l.strip().partition(' ')
        if not (args.split(' ')[0].endswith('java') and 'CassandraDaemon' in args):
            continue
        try:
            cwd = os.readlink(f'/proc/{pid}/cwd')
        except OSError:
            cwd = ''
        if cwd == C_HOME or f'{OTC}/' in args:
            r[int(pid)] = args
    return r


def pid_of(node):
    try:
        return int(open(f'{OTC}/{node}/cassandra.pid').read().strip())
    except Exception:
        return None


def alive(pid):
    return pid is not None and pid in daemons()


def stop_node(node, drain=False):
    pid = pid_of(node)
    if not alive(pid):
        return
    os.kill(pid, signal.SIGCONT)
    if drain:
        sh(f'bin/nodetool -p {NODES[node][1]} drain', check=False, timeout=180)
    os.kill(pid, signal.SIGTERM)
    for _ in range(90):
        if not alive(pid):
            log(f'{node} stopped'); return
        time.sleep(1)
    log(f'{node} did not stop; kill -9 {pid}')
    os.kill(pid, signal.SIGKILL)


def stop_all(drain=False):
    for n in ('n2', 'n1'):
        stop_node(n, drain)
    time.sleep(1)
    for pid in daemons():
        log(f'leftover daemon {pid}; SIGCONT + kill -9')
        os.kill(pid, signal.SIGCONT); os.kill(pid, signal.SIGKILL)
    time.sleep(1)
    log(f'daemons of this clone left: {len(daemons())}')


def start_node(node, V, args):
    sh(f'bash {H}/make-node-yaml.sh {node} ' + ' '.join(args))
    N = f'{OTC}/{node}'
    env = dict(os.environ, CASSANDRA_CONF=N + '/conf', CASSANDRA_LOG_DIR=N + '/logs', MAX_HEAP_SIZE='4G', HEAP_NEWSIZE='800M')
    jvm = f'-Dcassandra.otcp_large_message_threshold={V} -XX:NativeMemoryTracking=summary'
    sh(f'ulimit -n 100000 && JVM_EXTRA_OPTS="{jvm}" bin/cassandra -p {N}/cassandra.pid > {N}/stdout.txt 2>&1', env=env)


def wait_up(n_up, timeout=300):
    t = time.time()
    while time.time() - t < timeout:
        for node in NODES:
            p = pid_of(node)
            if p is not None and not alive(p) and time.time() - t > 20:
                raise RuntimeError(f'{node} died during start')
        _, st = sh('bin/nodetool -p 7199 status', check=False, quiet=True)
        _, sb = sh('bin/nodetool -p 7199 statusbinary', check=False, quiet=True)
        ups = len(re.findall(r'^UN ', st, re.M))
        if ups >= n_up and 'running' in sb:
            log(f'{ups} UN after {time.time()-t:.0f} s'); return st
        time.sleep(3)
    raise RuntimeError('nodes not up')


def read_csv(path):
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


def histo_total(path):
    for l in open(path):
        m = re.match(r'Total\s+(\d+)\s+(\d+)', l)
        if m:
            return int(m.group(2))
    return None


def lifetime(label):
    global LOGF
    cfg = LABELS[label]
    D = f'{OUT}/{label}'
    os.makedirs(D, exist_ok=True)
    LOGF = open(f'{D}/session.log', 'a')
    log(f'=== lifetime {label} {cfg} clone {C_HOME} harness {H}')
    if daemons():
        raise RuntimeError(f'daemons of this clone already running: {daemons()}')
    for node in NODES:
        N = f'{OTC}/{node}'
        sh(f'rm -rf {N}/data; mkdir -p {N}', quiet=True)
        if os.path.isdir(f'{N}/logs'):
            os.rename(f'{N}/logs', f'{N}/logs.prev-{int(time.time())}')
    sh(f'df -h {HOME} | tail -1')
    knobs = [f'internode_application_send_queue_capacity={cfg["C"]}MiB',
             f'internode_application_send_queue_reserve_endpoint_capacity={cfg["E"]}MiB',
             f'internode_application_receive_queue_reserve_endpoint_capacity={cfg["E"]}MiB',   # S4-A6
             f'internode_application_send_queue_reserve_global_capacity={cfg["G"]}MiB',
             'internode_max_message_size=1MiB']
    V = cfg['V']
    stopf = f'{D}/stop'
    procs = []
    res = dict(label=label, **cfg)
    try:
        if os.path.exists(stopf):
            os.remove(stopf)
        start_node('n1', V, knobs)
        wait_up(1)
        start_node('n2', V, knobs)
        st = wait_up(2)
        open(f'{D}/status.txt', 'w').write(st)
        for node in NODES:
            pid = pid_of(node)
            cmd = open(f'/proc/{pid}/cmdline').read().replace('\0', ' ')
            ok = f'-Dcassandra.otcp_large_message_threshold={V} ' in cmd + ' '
            res[f'{node}_property_ok'] = ok
            log(f'{node} pid {pid} command line carries V={V}: {ok}')
            if not ok:
                raise RuntimeError(f'{node} does not carry the property')
            sh(f'cp {OTC}/{node}/conf/cassandra.yaml {D}/{node}-cassandra.yaml; diff {OTC}/{node}/shipped.yaml {OTC}/{node}/conf/cassandra.yaml > {D}/{node}-yaml.diff', check=False, quiet=True)
        os.makedirs(f'{OTC}/jmx-classes', exist_ok=True)
        sh(f'javac -d {OTC}/jmx-classes {H}/Jmx.java', quiet=True)
        beanargs = ' '.join(f"'{b}' {a}" for b, a, _ in BEANS)
        open(f'{D}/jmx.csv', 'w').write('ms,' + ','.join(COLS) + '\n')
        pj = subprocess.Popen(f'exec java -cp {OTC}/jmx-classes Jmx 7199 poll 1000 100000 {stopf} {beanargs} >> {D}/jmx.csv 2> {D}/jmx.err',
                              shell=True)
        procs.append(pj)
        time.sleep(3)
        dur = cfg.get('duration', 90)
        stress = (f'tools/bin/cassandra-stress write duration={dur}s cl=ONE no-warmup '
                  f'-schema "replication(factor=2)" -col "size=FIXED(1000)" "n=FIXED(1)" '
                  f'-rate threads=200 fixed=30000/s -node whitelist 127.0.0.1 -mode native cql3 -log interval=1s')
        log(f'$ {stress}')
        t0 = time.time()
        res['t0'] = int(t0 * 1000)
        ps = subprocess.Popen(stress, shell=True, cwd=C_HOME, stdout=open(f'{D}/stress.log', 'w'), stderr=subprocess.STDOUT,
                              env={k: v for k, v in os.environ.items() if k not in ('CASSANDRA_CONF', 'JVM_EXTRA_OPTS')})
        procs.append(ps)

        def at(sec):
            w = t0 + sec - time.time()
            if w > 0:
                time.sleep(w)
        p1 = pid_of('n1'); p2 = pid_of('n2')
        if not cfg.get('nostop'):
            at(30)
            os.kill(p2, signal.SIGSTOP); tp = time.time(); res['stop'] = int(tp * 1000)
            log(f'SIGSTOP n2 pid {p2}')
            time.sleep(max(0, tp + 12 - time.time()))
            sh(f'jcmd {p1} GC.class_histogram > {D}/histo-stall12.txt 2>&1', check=False, quiet=True)
            res['histo_ms'] = int(time.time() * 1000); log('histogram taken')
            time.sleep(max(0, tp + 15 - time.time()))
            sh(f'jcmd {p1} VM.native_memory summary > {D}/nmt-stall15.txt 2>&1', check=False, quiet=True)
            res['nmt_ms'] = int(time.time() * 1000); log('NMT taken')
            at(50)
            os.kill(p2, signal.SIGCONT); res['cont'] = int(time.time() * 1000)
            log(f'SIGCONT n2 pid {p2}')
        rc = ps.wait(timeout=600)
        res['stress_rc'] = rc
        log(f'stress exit {rc}')
        time.sleep(10)
        open(stopf, 'w').close()
        for p in procs:
            try:
                p.wait(timeout=20)
            except subprocess.TimeoutExpired:
                p.kill()
        res['end'] = int(time.time() * 1000)
        sh(f'bin/nodetool -p 7199 status > {D}/status-end.txt 2>&1', check=False, quiet=True)
    finally:
        open(stopf, 'w').close()
        for p in procs:
            if p.poll() is None:
                p.kill()
        try:
            stop_all(drain=True)
        finally:
            for node in NODES:
                for f in ('system.log', 'debug.log', 'gc.log'):
                    sh(f'cp {OTC}/{node}/logs/{f} {D}/{node}-{f} 2>/dev/null || true', check=False, quiet=True)
                sh(f'rm -rf {OTC}/{node}/data', check=False, quiet=True)
    json.dump(res, open(f'{D}/times.json', 'w'))
    analyse(label, D, res)
    LOGF.close()


def analyse(label, D, res):
    say_lines = []

    def say(s):
        say_lines.append(s); log(s)
    rows = read_csv(f'{D}/jmx.csv')
    t0 = res['t0']
    base = [r for r in rows if t0 + 10000 <= r['ms'] <= t0 + 25000]
    s = {'label': label, 'V': res['V'], 'ctl': bool(res.get('ctl')), 'samples': len(rows), 'base_samples': len(base)}
    if 'stop' in res:
        win = [r for r in rows if res['stop'] <= r['ms'] <= res['cont']]
        s['win_samples'] = len(win)
        for k in ('pending', 'used', 'direct', 'overflow', 'poolSize', 'urgentPending', 'largePending'):
            vals = [r[k] for r in win if r[k] is not None]
            bv = [r[k] for r in base if r[k] is not None]
            s[f'{k}_peak'] = max(vals) if vals else None
            s[f'{k}_base'] = statistics.median(bv) if bv else None
            s[f'{k}_delta'] = (s[f'{k}_peak'] - s[f'{k}_base']) if vals and bv else None
        pend = [r['pending'] for r in win]
        s['pending_first_ge_90pct_s'] = next(((r['ms'] - res['stop']) / 1000 for r in win
                                              if r['pending'] is not None and r['pending'] >= 0.9 * (res['C'] + res['E']) * MIB), None)
        db = [r['dropBytes'] for r in rows if r['dropBytes'] is not None]
        s['dropBytes_at_stop'] = next((r['dropBytes'] for r in rows if r['ms'] >= res['stop']), None)
        s['dropBytes_at_cont'] = next((r['dropBytes'] for r in rows if r['ms'] >= res['cont']), None)
        s['dropTimeout_end'] = rows[-1]['dropTimeout'] if rows else None
        s['heapUsed_peak'] = max(r['heapUsed'] for r in win if r['heapUsed'] is not None) if win else None
        s['pending_end'] = rows[-1]['pending'] if rows else None
    if os.path.exists(f'{D}/histo-stall12.txt'):
        s['histo_total'] = histo_total(f'{D}/histo-stall12.txt')
    sl = open(f'{D}/n1-system.log', errors='replace').read() if os.path.exists(f'{D}/n1-system.log') else ''
    s['n1_down_lines'] = len(re.findall(r'is now DOWN', sl))
    # C4 counts only DOWN lines inside the stall window: the shutdown at the end of every lifetime also logs one
    # (shakedown, 2026-10-22). system.log time stamps are UTC, e.g. 2026-10-22T08:26:25,479.
    s['n1_down_in_stall'] = 0
    if 'stop' in res:
        import calendar
        for m in re.finditer(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d),(\d{3}) .*is now DOWN', sl):
            ms = calendar.timegm(time.strptime(m.group(1), '%Y-%m-%dT%H:%M:%S')) * 1000 + int(m.group(2))
            if res['stop'] <= ms <= res['cont']:
                s['n1_down_in_stall'] += 1
    s['n1_frame_errors'] = len(re.findall(r'Maximum payload size', sl))
    s['n1_error_lines'] = len(re.findall(r'^ERROR', sl, re.M))
    s['n1_overload_warn'] = len(re.findall(r'overloaded', sl))
    s['n1_lmt_logged'] = None
    s['n2_down_any'] = s['n1_down_in_stall'] > 0
    st = open(f'{D}/stress.log', errors='replace').read() if os.path.exists(f'{D}/stress.log') else ''
    for k in ('Op rate', 'Total errors', 'Total partitions'):
        m = re.search(rf'^{k}\s*:\s*(.*)$', st, re.M)
        s[k.replace(' ', '_')] = m.group(1).strip() if m else None
    nmt = open(f'{D}/nmt-stall15.txt', errors='replace').read() if os.path.exists(f'{D}/nmt-stall15.txt') else ''
    m = re.search(r'-\s+Other \(reserved=(\d+)KB, committed=(\d+)KB\)', nmt)
    s['nmt_other_committed_kb'] = int(m.group(2)) if m else None
    m = re.search(r'Total: reserved=(\d+)KB, committed=(\d+)KB', nmt)
    s['nmt_total_committed_kb'] = int(m.group(2)) if m else None
    json.dump(s, open(f'{D}/summary.json', 'w'), indent=1)
    say('SUMMARY ' + json.dumps(s))


def analyze():
    global LOGF
    os.makedirs(OUT, exist_ok=True)
    LOGF = open(f'{OUT}/analyze.log', 'a')
    S = {}
    for label in ORDER:
        p = f'{OUT}/{label}/summary.json'
        if os.path.exists(p):
            S[label] = json.load(open(p))
    log(f'lifetimes found: {list(S)}')
    lines = []

    def say(x):
        lines.append(x); log(x)
    main = [s for s in S.values() if not s['ctl']]
    ctl = [s for s in S.values() if s['ctl']]
    valid = lambda s: not s.get('n2_down_any') and s.get('n1_frame_errors', 0) == 0
    for s in S.values():
        say(f"{s['label']}: V={s['V']} pending_peak={s.get('pending_peak')} used_delta={s.get('used_delta')} direct_delta={s.get('direct_delta')} "
            f"overflow_delta={s.get('overflow_delta')} histo_total={s.get('histo_total')} down={s.get('n1_down_lines')} frameErr={s.get('n1_frame_errors')} "
            f"errors={s.get('n1_error_lines')} t90={s.get('pending_first_ge_90pct_s')} rate={s.get('Op_rate')} stressErr={s.get('Total_errors')}")
    # per-V means over counting runs
    per = {}
    for V in (16384, 65536, 131072):
        rs = [s for s in main if s['V'] == V and valid(s)]
        per[V] = {k: (statistics.mean(s[k] for s in rs) if rs else None) for k in ('pending_peak', 'used_delta', 'direct_delta')}
        per[V]['n'] = len(rs)
        say(f'per-V V={V}: {per[V]}')
    cap, ccap, msg = 3 * MIB, 32 * MIB, 2 * KIB
    rows = {}
    # C4 / C5 run validity
    rows['C4'] = [s['label'] for s in S.values() if s.get('n2_down_any')]
    rows['C5'] = [s['label'] for s in S.values() if s.get('n1_frame_errors', 0) > 0]
    noV = [V for V in per if per[V]['n'] == 0]
    say(f'C4 (n2 down in a run): {rows["C4"]}; C5 (frame errors): {rows["C5"]}; V with no counting run: {noV}')
    # C2
    c2 = []
    for k in ('pending_peak', 'used_delta', 'direct_delta'):
        v = [per[V][k] for V in (16384, 65536, 131072)]
        if None not in v and v[0] < v[1] < v[2] and v[2] - v[0] > MIB:
            c2.append(k)
    say(f'C2 (monotonic increase with V by > 1 MiB): {c2}')
    cm = [s for s in main if valid(s)]
    cc = [s for s in ctl if valid(s)]
    c3 = [s['label'] for s in cm if s['pending_peak'] < 0.9 * cap] + [s['label'] for s in cc if s['pending_peak'] < 0.9 * ccap]
    c6 = [s['label'] for s in cm if s['pending_peak'] > cap + msg] + [s['label'] for s in cc if s['pending_peak'] > ccap + msg]
    say(f'C3 (cap not reached): {c3}; C6 (cap exceeded): {c6}')
    pv = [per[V]['pending_peak'] for V in per if per[V]['pending_peak'] is not None]
    uv = [per[V]['used_delta'] for V in per if per[V]['used_delta'] is not None]
    dv = [per[V]['direct_delta'] for V in per if per[V]['direct_delta'] is not None]
    bands = {
        'main pending in [0.9*3MiB, 3MiB+2KiB]': all(0.9 * cap <= s['pending_peak'] <= cap + msg for s in cm) and len(cm) > 0,
        'per-V pending span < 5% of mean': len(pv) == 3 and (max(pv) - min(pv)) < 0.05 * statistics.mean(pv),
        'per-V UsedSize span < 0.5 MiB': len(uv) == 3 and (max(uv) - min(uv)) < 0.5 * MIB,
        'per-V direct span < 1 MiB': len(dv) == 3 and (max(dv) - min(dv)) < MIB,
        'control pending in [0.9*32MiB, 32MiB+2KiB]': all(0.9 * ccap <= s['pending_peak'] <= ccap + msg for s in cc) and len(cc) > 0,
    }
    if pv:
        say(f'pending per-V span {max(pv)-min(pv):.0f} B ({(max(pv)-min(pv))/statistics.mean(pv)*100:.2f} % of mean)')
    if uv:
        say(f'UsedSize per-V span {max(uv)-min(uv):.0f} B')
    if dv:
        say(f'direct per-V span {max(dv)-min(dv):.0f} B')
    for k, v in bands.items():
        say(f'C1 band: {k}: {v}')
    if noV:
        verdict = 'C5/C4: a V has no counting run -> Not confirmed'
    elif c2:
        verdict = f'C2 Refuted ({c2})'
    elif c3:
        verdict = f'C3 Not confirmed (cap not reached: {c3})'
    elif c6:
        verdict = f'C6 Not confirmed (cap exceeded: {c6})'
    elif not all(bands.values()):
        verdict = f'C7 Not confirmed (band missed: {[k for k, v in bands.items() if not v]})'
    else:
        verdict = 'C1 Confirmed'
    # sub-prediction: heap of the control vs the V=65536 runs (S4-A8)
    h64 = [s['histo_total'] for s in main if s['V'] == 65536 and s.get('histo_total')]
    hc = [s['histo_total'] for s in ctl if s.get('histo_total')]
    if h64 and hc:
        say(f'heap sub-prediction: control histogram total mean {statistics.mean(hc):.0f} vs V=65536 mean {statistics.mean(h64):.0f}: '
            f'diff {statistics.mean(hc)-statistics.mean(h64):.0f} B (predicted >= ~29 MB)')
    say(f'VERDICT (B3g as amended by S4-A9): {verdict}')
    open(f'{OUT}/analyze-summary.txt', 'w').write('\n'.join(lines) + '\n')


if __name__ == '__main__':
    what = sys.argv[2]
    if what == 'analyze':
        analyze()
    elif what == 'down':
        stop_all()
    else:
        lifetime(what)
