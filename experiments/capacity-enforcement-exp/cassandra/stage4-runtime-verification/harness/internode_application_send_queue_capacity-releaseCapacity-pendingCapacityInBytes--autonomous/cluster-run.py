#!/usr/bin/env python3
"""Cluster tier (B3) of internode_application_send_queue_capacity-releaseCapacity-pendingCapacityInBytes--autonomous.

usage: python3 cluster-run.py <run> <label>        one lifetime of both nodes (B3e steps 1-7)
       python3 cluster-run.py <run> analyze        cross-run relations (B3f/B3g, amendment A7)
       python3 cluster-run.py <run> down           stop any node of this clone (B is SIGCONTed first)
Labels (B3b, B3e): c4m (C 4 MiB, default), c64m, c256m (reserves 1 MiB), pos (C 4 MiB, reserves 128 MiB: positive control),
neg (C 64 MiB, reserves 1 MiB, B never stopped: negative control). shake (C 4 MiB, 30 s stress, no stop) is a shakedown.

One lifetime: wipe the tmpfs node dirs; write both yamls (make-node-yaml.sh); start A, wait UN + binary; start B, wait 2 UN;
start the JMX poller (Jmx.java poll, 1 s, amendment A6) and the internode_outbound poller on A (sample-vt.py, 1 s);
start cassandra-stress (B3c, 90 s) = t0; t0+18 s histogram "pre" (A7); t0+20 s SIGSTOP B; pause+12 s histogram "plateau"
+ GC.heap_info; pause+30 s SIGCONT B (neg: no stop; its "plateau" histogram is taken at t0+32 s); wait for stress; 25 s
drain; stop the pollers; log greps; stop both nodes (B SIGCONTed first on any exit); check no java of this clone is left.
Reading rules (fixed before run 1): plateau = median of SmallMessagePendingBytes over [pause+5 s, pause+25 s]; "reached"
= the first sample >= C; s = PendingBytes / PendingTasks at the plateau samples (median); drain = the last vt sample after
the 25 s drain.
Logs: ~/stage4-logs/sq2/<run>/cluster/<label>/.
"""
import glob, json, os, re, signal, statistics, subprocess, sys, time

HOME = os.path.expanduser('~')
C_HOME = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-sq2')
H = os.path.dirname(os.path.abspath(__file__))
SQ2 = HOME + '/stage4-sq2'
DATA = SQ2 + '/nodes'
NODES = {'A': ('127.0.0.1', 7199), 'B': ('127.0.0.2', 7299)}
MIB = 1 << 20
LABELS = {
    'c4m':   dict(C=4, G=1, stop=True),
    'c64m':  dict(C=64, G=1, stop=True),
    'c256m': dict(C=256, G=1, stop=True),
    'pos':   dict(C=4, G=128, stop=True),
    'neg':   dict(C=64, G=1, stop=False),
    'shake': dict(C=4, G=1, stop=False, duration=30),
}
SCOPE = '127.0.0.2_7000'
BEANS = [('Small', 'PendingBytes'), ('Small', 'PendingTasks'), ('Small', 'DroppedBytesDueToOverload'),
         ('Small', 'DroppedTasksDueToOverload'), ('Small', 'DroppedTasksDueToTimeout'), ('Small', 'CompletedTasks'),
         ('Urgent', 'PendingBytes'), ('Large', 'PendingBytes'), ('Urgent', 'DroppedTasksDueToOverload'),
         ('Large', 'DroppedTasksDueToOverload')]
COLS = [f'{k}{n}' for k, n in BEANS] + ['heapUsed']

RUN = sys.argv[1]
OUT = f'{HOME}/stage4-logs/sq2/{RUN}/cluster'
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
    """java processes of this clone running CassandraDaemon: {pid: cmd}"""
    r = {}
    for l in subprocess.run(['ps', '-eo', 'pid=,args='], stdout=subprocess.PIPE, text=True).stdout.splitlines():
        pid, _, args = l.strip().partition(' ')
        if not (args.split(' ')[0].endswith('java') and 'CassandraDaemon' in args):
            continue
        try:
            cwd = os.readlink(f'/proc/{pid}/cwd')
        except OSError:
            cwd = ''
        # the daemon's command line names the clone only as bin/../ (relative); match its cwd or this run's conf path
        if cwd == C_HOME or f'{SQ2}/' in args:
            r[int(pid)] = args
    return r


def pid_of(node):
    try:
        return int(open(f'{SQ2}/{node}/cassandra.pid').read().strip())
    except Exception:
        return None


def alive(pid):
    return pid is not None and pid in daemons()


def stop_node(node):
    pid = pid_of(node)
    if not alive(pid):
        return
    if node == 'B':
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
        stop_node(n)
    left = daemons()
    for pid in left:
        log(f'leftover daemon {pid}; SIGCONT + kill -9')
        os.kill(pid, signal.SIGCONT); os.kill(pid, signal.SIGKILL)
    time.sleep(1)
    log(f'daemons of this clone left: {len(daemons())}')


def start_node(node, args):
    addr, jmx = NODES[node]
    sh(f'bash {H}/make-node-yaml.sh {node} ' + ' '.join(args))
    N = f'{SQ2}/{node}'
    env = dict(os.environ, CASSANDRA_CONF=N + '/conf', CASSANDRA_LOG_DIR=N + '/logs', MAX_HEAP_SIZE='4G', HEAP_NEWSIZE='800M')
    env.pop('JVM_EXTRA_OPTS', None)
    sh(f'ulimit -n 100000 && bin/cassandra -p {N}/cassandra.pid > {N}/stdout.txt 2>&1', env=env)


def wait_up(n_up, timeout=300):
    t = time.time()
    while time.time() - t < timeout:
        for node in NODES:
            p = pid_of(node)
            if p is not None and os.path.exists(f'{SQ2}/{node}/cassandra.pid') and not alive(p) and time.time() - t > 15:
                raise RuntimeError(f'{node} died during start')
        _, st = sh(f'bin/nodetool -p 7199 status', check=False, quiet=True)
        _, sb = sh(f'bin/nodetool -p 7199 statusbinary', check=False, quiet=True)
        ups = len(re.findall(r'^UN ', st, re.M))
        if ups >= n_up and 'running' in sb:
            log(f'{ups} UN after {time.time()-t:.0f} s'); return st
        time.sleep(3)
    raise RuntimeError('nodes not up')


def histogram(path):
    pid = pid_of('A')
    sh(f'jcmd {pid} GC.class_histogram > {path} 2>&1', check=False, quiet=True)
    sh(f'jcmd {pid} GC.heap_info >> {path} 2>&1', check=False, quiet=True)
    log(f'histogram {os.path.basename(path)} taken')


def parse_histo(path):
    tot, cls = None, {}
    for l in open(path):
        m = re.match(r'\s*\d+:\s+(\d+)\s+(\d+)\s+(\S+)', l)
        if m:
            cls[m.group(3)] = (int(m.group(1)), int(m.group(2)))
        m = re.match(r'Total\s+(\d+)\s+(\d+)', l)
        if m:
            tot = int(m.group(2))
    return tot, cls


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


def read_vt(path):
    rows = []
    for l in open(path):
        f = l.strip().split(',')
        if len(f) < 13 or not f[0].isdigit():
            continue
        if f[1] != '127.0.0.2':
            continue
        keys = ['using_bytes', 'using_reserve_bytes', 'pending_count', 'pending_bytes', 'sent_count', 'sent_bytes',
                'expired_count', 'error_count', 'overload_count', 'overload_bytes']
        rows.append(dict(ms=int(f[0]), **{k: int(v) for k, v in zip(keys, f[3:13])}))
    return rows


def lifetime(label):
    global LOGF
    cfg = LABELS[label]
    D = f'{OUT}/{label}'
    os.makedirs(D, exist_ok=True)
    LOGF = open(f'{D}/session.log', 'a')
    log(f'=== lifetime {label} {cfg} clone {C_HOME} harness {H}')
    if daemons():
        raise RuntimeError(f'daemons of this clone already running: {daemons()}')
    if subprocess.run(['mountpoint', '-q', DATA]).returncode != 0:
        raise RuntimeError(f'{DATA} not mounted')
    sh(f'rm -rf {DATA}/A {DATA}/B; df -h {DATA} /; mkdir -p {SQ2}/A {SQ2}/B')
    for node in ('A', 'B'):
        lg = f'{SQ2}/{node}/logs'
        if os.path.isdir(lg):
            os.rename(lg, f'{SQ2}/{node}/logs.prev-{int(time.time())}')
    C = cfg['C'] * MIB
    knobs = [f'internode_application_send_queue_capacity={cfg["C"]}MiB',
             f'internode_application_send_queue_reserve_endpoint_capacity={cfg["G"]}MiB',
             f'internode_application_send_queue_reserve_global_capacity={cfg["G"]}MiB',
             'internode_max_message_size=1MiB']
    stopf = f'{D}/stop'
    procs = []
    res = {'label': label, 'C': C, 'G': cfg['G'] * MIB, 'stop': cfg['stop']}
    try:
        if os.path.exists(stopf):
            os.remove(stopf)
        start_node('A', knobs)
        wait_up(1)
        start_node('B', [])
        st = wait_up(2)
        open(f'{D}/status.txt', 'w').write(st)
        for node in ('A', 'B'):
            sh(f'cp {SQ2}/{node}/conf/cassandra.yaml {D}/{node}-cassandra.yaml; diff {SQ2}/{node}/shipped.yaml {SQ2}/{node}/conf/cassandra.yaml > {D}/{node}-yaml.diff', check=False, quiet=True)
        os.makedirs(f'{SQ2}/jmx-classes', exist_ok=True)
        sh(f'javac -d {SQ2}/jmx-classes {H}/Jmx.java', quiet=True)
        beanargs = ' '.join(f"'org.apache.cassandra.metrics:type=Connection,scope={SCOPE},name={k}Message{n}' Value" for k, n in BEANS)
        beanargs += " 'java.lang:type=Memory' HeapMemoryUsage"
        open(f'{D}/jmx.csv', 'w').write('ms,' + ','.join(COLS) + '\n')
        pj = subprocess.Popen(f'exec java -cp {SQ2}/jmx-classes Jmx 7199 poll 1000 100000 {stopf} {beanargs} >> {D}/jmx.csv 2> {D}/jmx.err',
                              shell=True)
        procs.append(pj)
        pv = subprocess.Popen(['python3', f'{H}/sample-vt.py', '127.0.0.1', 'outbound', '1.0', stopf, f'{D}/vt-out.csv'],
                              stdout=open(f'{D}/vt.out', 'w'), stderr=subprocess.STDOUT, env=dict(os.environ, CASSANDRA_HOME=C_HOME))
        procs.append(pv)
        time.sleep(3)
        dur = cfg.get('duration', 90)
        stress = (f'tools/bin/cassandra-stress write duration={dur}s cl=ONE no-warmup '
                  f'-schema "replication(strategy=SimpleStrategy,factor=2)" -col "n=FIXED(1)" "size=FIXED(1000)" '
                  f'-rate threads=64 fixed=30000/s -node whitelist 127.0.0.1 -port native=9042 -log interval=1s')
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
        at(18)
        histogram(f'{D}/histo-pre.txt'); res['h_pre_ms'] = int(time.time() * 1000)
        pB = pid_of('B')
        if cfg['stop']:
            at(20)
            os.kill(pB, signal.SIGSTOP); tp = time.time(); res['pause'] = int(tp * 1000)
            log(f'SIGSTOP B pid {pB}')
            w = tp + 12 - time.time(); time.sleep(max(0, w))
            histogram(f'{D}/histo-plateau.txt'); res['h_plat_ms'] = int(time.time() * 1000)
            w = tp + 30 - time.time(); time.sleep(max(0, w))
            os.kill(pB, signal.SIGCONT); res['cont'] = int(time.time() * 1000)
            log(f'SIGCONT B pid {pB}')
        else:
            at(20); res['pause'] = int(time.time() * 1000)     # reference point only, B is not stopped
            at(32)
            histogram(f'{D}/histo-plateau.txt'); res['h_plat_ms'] = int(time.time() * 1000)
            res['cont'] = res['pause'] + 30000
        rc = ps.wait(timeout=400)
        log(f'stress exit {rc}')
        time.sleep(25)
        open(stopf, 'w').close()
        for p in procs:
            try:
                p.wait(timeout=20)
            except subprocess.TimeoutExpired:
                p.kill()
        res['end'] = int(time.time() * 1000)
        sh(f'python3 {H}/sample-vt.py 127.0.0.1 outbound 1 {stopf} {D}/vt-final.csv once', check=False,
           env=dict(os.environ, CASSANDRA_HOME=C_HOME))
        for node in ('A', 'B'):
            for f in ('system.log', 'debug.log'):
                sh(f'cp {SQ2}/{node}/logs/{f} {D}/{node}-{f} 2>/dev/null || true', check=False, quiet=True)
    finally:
        open(stopf, 'w').close()
        for p in procs:
            if p.poll() is None:
                p.kill()
        stop_all()
    json.dump(res, open(f'{D}/times.json', 'w'))
    analyse(label, D, res)
    LOGF.close()


def sec(ms):
    return 'none' if ms is None else f'{ms/1000:.1f}'


def analyse(label, D, res):
    S = []
    def say(s):
        S.append(s); log(s)
    C, G = res['C'], res['G']
    rows = read_csv(f'{D}/jmx.csv')
    vt = read_vt(f'{D}/vt-out.csv')
    vtf = read_vt(f'{D}/vt-final.csv') if os.path.exists(f'{D}/vt-final.csv') else []
    p0, pc = res['pause'], res['cont']
    say(f'label {label}: C={C} G(reserves)={G} stop={res["stop"]}; jmx samples {len(rows)}, vt samples {len(vt)}')
    win = [r for r in rows if p0 + 5000 <= r['ms'] <= p0 + 25000 and r['SmallPendingBytes'] is not None]
    pb = [r['SmallPendingBytes'] for r in win]
    plateau = statistics.median(pb) if pb else None
    allpb = [r['SmallPendingBytes'] for r in rows if r['SmallPendingBytes'] is not None]
    mx = max(allpb) if allpb else None
    s_vals = [r['SmallPendingBytes'] / r['SmallPendingTasks'] for r in win if r['SmallPendingTasks']]
    s = statistics.median(s_vals) if s_vals else None
    reached = next((r['ms'] - p0 for r in rows if r['ms'] >= p0 and (r['SmallPendingBytes'] or 0) >= C), None)
    say(f'plateau(median pause+5..25s)={plateau} max={mx} limit C+G={C+G} (C+G)-plateau={None if plateau is None else C+G-plateau} '
        f'reached>=C at pause+{sec(reached)}s s(median bytes/task)={None if s is None else round(s,1)}')
    say(f'window pending bytes min/max = {min(pb) if pb else None}/{max(pb) if pb else None}; pending tasks median '
        f'{statistics.median([r["SmallPendingTasks"] for r in win]) if win else None}')
    def at_ms(t, key, rr=rows):
        c = [r for r in rr if r.get(key) is not None]
        return min(c, key=lambda r: abs(r['ms'] - t))[key] if c else None
    ov0, ov1 = at_ms(p0, 'SmallDroppedTasksDueToOverload'), at_ms(p0 + 25000, 'SmallDroppedTasksDueToOverload')
    ovend = rows[-1]['SmallDroppedTasksDueToOverload'] if rows else None
    to25 = at_ms(p0 + 25000, 'SmallDroppedTasksDueToTimeout'); toend = rows[-1]['SmallDroppedTasksDueToTimeout'] if rows else None
    say(f'overload dropped tasks: at pause {ov0}, at pause+25s {ov1}, at end {ovend}; timeout-dropped tasks at pause+25s {to25}, at end {toend}')
    # first overload after pause, relative to reaching C
    fo = next((r['ms'] - p0 for r in rows if r['ms'] >= p0 and (r['SmallDroppedTasksDueToOverload'] or 0) > (ov0 or 0)), None)
    say(f'first overload drop at pause+{sec(fo)}s')
    ug = max((r['UrgentPendingBytes'] or 0) for r in rows) if rows else None
    lg = max((r['LargePendingBytes'] or 0) for r in rows) if rows else None
    say(f'max Urgent pending bytes {ug}, max Large pending bytes {lg}')
    # vt: reserve
    wv = [r for r in vt if p0 + 5000 <= r['ms'] <= p0 + 25000]
    if wv:
        say(f'vt window: using_reserve_bytes median {statistics.median([r["using_reserve_bytes"] for r in wv])} max '
            f'{max(r["using_reserve_bytes"] for r in wv)}; pending_bytes median {statistics.median([r["pending_bytes"] for r in wv])}; '
            f'reserve - max(0, pending - 3C) checks below')
    # reserve vs pending-C over the whole run (vt sums the 3 links; the small link carries the load)
    viol = [r for r in vt if r['using_reserve_bytes'] > max(0, r['pending_bytes'] - C) + 2 * MIB]
    say(f'vt samples with using_reserve > max(0, pending - C) + 2 MiB: {len(viol)} of {len(vt)}')
    after = [r for r in vt if r['ms'] >= pc + 15000]
    if after:
        last = after[-1]
        say(f'vt after SIGCONT+15s: {len(after)} samples; last: pending_bytes={last["pending_bytes"]} using_bytes={last["using_bytes"]} '
            f'using_reserve_bytes={last["using_reserve_bytes"]}; max reserve in these {max(r["using_reserve_bytes"] for r in after)}; '
            f'samples with pending<64KiB and reserve>0: {sum(1 for r in after if r["pending_bytes"] < 65536 and r["using_reserve_bytes"] > 0)}')
    if vtf:
        say(f'vt final (after the 25 s drain): pending_bytes={vtf[-1]["pending_bytes"]} using_reserve_bytes={vtf[-1]["using_reserve_bytes"]} '
            f'overload_count={vtf[-1]["overload_count"]} expired_count={vtf[-1]["expired_count"]}')
    # histograms
    hp, cp = parse_histo(f'{D}/histo-pre.txt')
    hq, cq = parse_histo(f'{D}/histo-plateau.txt')
    def cl(c, name):
        return c.get(name, (0, 0))
    ptasks = at_ms(res['h_plat_ms'], 'SmallPendingTasks'); pbytes = at_ms(res['h_plat_ms'], 'SmallPendingBytes')
    say(f'histogram totals: pre {hp} plateau {hq}; at plateau histogram: SmallPendingBytes {pbytes} SmallPendingTasks {ptasks}')
    for nm in ('org.apache.cassandra.db.Mutation', 'org.apache.cassandra.net.Message', 'org.apache.cassandra.net.Message$Header',
               'org.apache.cassandra.db.partitions.PartitionUpdate', '[B'):
        say(f'  class {nm}: pre {cl(cp, nm)} plateau {cl(cq, nm)}')
    # logs
    for node in ('A', 'B'):
        f = f'{D}/{node}-system.log'
        if os.path.exists(f):
            t = open(f).read()
            say(f'{node} system.log: ERROR {len(re.findall(r"^ERROR", t, re.M))}, WARN {len(re.findall(r"^WARN", t, re.M))}, '
                f'"overloaded; dropping" {t.count("overloaded; dropping")}, "is now DOWN" {t.count("is now DOWN")}, '
                f'UnrecoverableIllegalState {t.count("UnrecoverableIllegalStateException")}, OutOfMemoryError {t.count("java.lang.OutOfMemoryError")}')
    for l in open(f'{D}/A-system.log') if os.path.exists(f'{D}/A-system.log') else []:
        if 'overloaded; dropping' in l or 'is now DOWN' in l or 'is now UP' in l:
            say('  A log: ' + l.strip()[:300])
    st = open(f'{D}/stress.log').read() if os.path.exists(f'{D}/stress.log') else ''
    for k in ('Op rate', 'Total errors', 'Total partitions', 'Total operation time'):
        m = re.search(r'^' + k + r'.*$', st, re.M)
        say(f'stress {m.group(0) if m else k + ": missing"}')
    rec = dict(res, plateau=plateau, max=mx, s=s, reached_ms=reached, first_overload_ms=fo, ov_pause=ov0, ov_25=ov1, ov_end=ovend,
               timeout_25=to25, timeout_end=toend, urgent_max=ug, large_max=lg, h_pre=hp, h_plat=hq,
               mut_pre=cl(cp, 'org.apache.cassandra.db.Mutation'), mut_plat=cl(cq, 'org.apache.cassandra.db.Mutation'),
               msg_plat=cl(cq, 'org.apache.cassandra.net.Message'), ptasks_h=ptasks, pbytes_h=pbytes,
               vt_reserve_viol=len(viol), vt_final=(vtf[-1] if vtf else None),
               vt_after_max_reserve=(max(r['using_reserve_bytes'] for r in after) if after else None),
               vt_window_reserve_median=(statistics.median([r['using_reserve_bytes'] for r in wv]) if wv else None))
    json.dump(rec, open(f'{D}/readings.json', 'w'), indent=1)
    open(f'{D}/summary.txt', 'w').write('\n'.join(S) + '\n')


def analyze():
    S = []
    def say(s):
        S.append(s); print(s)
    R = {}
    for l in ('c4m', 'c64m', 'c256m', 'pos', 'neg'):
        f = f'{OUT}/{l}/readings.json'
        if os.path.exists(f):
            R[l] = json.load(open(f))
    pres = [r['h_pre'] for r in R.values() if r.get('h_pre')]
    N = max(pres) - min(pres) if len(pres) > 1 else None
    say(f'noise N = range of t=18 s histogram totals over {len(pres)} lifetimes: {N} ({pres})')
    neg = R.get('neg')
    ks = {}
    for l in ('c4m', 'c64m', 'c256m', 'pos'):
        r = R.get(l)
        if not r or not neg:
            continue
        dH = r['h_plat'] - neg['h_plat']
        k = dH / r['pbytes_h'] if r.get('pbytes_h') else None
        clears = N is not None and dH > 3 * N
        if l != 'pos' and clears:
            ks[l] = k
        say(f'{l}: plateau {r["plateau"]} (C+G {r["C"]+r["G"]}), dH = {dH} vs 3N {None if N is None else 3*N}: clears={clears}; '
            f'k = dH / pending at histogram ({r["pbytes_h"]}) = {None if k is None else round(k, 3)}; Mutation count plateau {r["mut_plat"][0]} '
            f'vs pending tasks {r["ptasks_h"]} (neg Mutation count {neg["mut_plat"][0]})')
    if len(ks) >= 2:
        kv = list(ks.values())
        say(f'k over runs that clear 3N: {ks}; spread max/min = {max(kv)/min(kv):.3f} (stable within +-25 % means max/min <= 1.667 '
            f'and every k within 25 % of the mean: {all(abs(k-statistics.mean(kv)) <= 0.25*statistics.mean(kv) for k in kv)}); '
            f'all in [1.5, 4]: {all(1.5 <= k <= 4 for k in kv)}')
    else:
        say(f'heap clause: only {len(ks)} of runs 1-3 clear 3N -> not adjudicable (A7/A8)')
    os.makedirs(f'{OUT}/analyze', exist_ok=True)
    open(f'{OUT}/analyze/summary.txt', 'w').write('\n'.join(S) + '\n')


if __name__ == '__main__':
    what = sys.argv[2]
    if what == 'analyze':
        analyze()
    elif what == 'down':
        stop_all()
    elif what == 'reanalyse':
        lab = sys.argv[3]; D = f'{OUT}/{lab}'
        analyse(lab, D, json.load(open(f'{D}/times.json')))
    else:
        lifetime(what)
