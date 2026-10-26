#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of slab-region-size-region-allocate-capacity--autonomous (case file as amended 2026-10-26).
usage: cluster-run.py <arm> | analyze | down
  <arm>  one node lifetime (B3e): wipe /dev/shm/s4-b7-sr7, write the yaml (make-node-yaml.sh), start the node (MAX_HEAP_SIZE=2G, the shipped
         -XX:+AlwaysPreTouch, JVM_EXTRA_OPTS=-XX:NativeMemoryTracking=summary -XX:MaxDirectMemorySize=2g), read the settings back from
         system_views.settings, create ks.t, disable autocompaction, idle 20 s, GC twice, baseline, then ONE workload (client.py big, protocol 4,
         16 in flight, 4000 rows) with the samplers running (gauges via Jmx.java every 200 ms; RssAnon every 200 ms; NMT summary every 5 s), then
         10 s idle, nodetool flush, 15 s, stop the node, copy system.log.
  Arms (L MiB, value bytes S): a64 (64, 116509)  a128 (128, 116509)  a64b (repeat of a64)  e64 (64, 131068 exact fit)  f64 (64, 131072)
                              all offheap_buffers; h64 heap_buffers, memtable_heap_space 64MiB, S 116509 (class histogram of [B once at 0.9 of the limit).
  analyze reads every <arm>/phases.json and writes analysis.txt (the B3f relations, rules fixed in README.md).
  down    stop every process of this harness.
Ports of this agent (slot 5): 127.0.5.1 storage 7000 / native 9042, JMX 7150 (local JMX binds 127.0.0.1).
Output: ~/s4-b7-sr7-logs/<SR_RUN>/cluster/<arm>/ (summary.txt with EXPECTED lines, session.log, jmx.csv, rss.csv, nmt.csv, phases.json, system.log).
Exit 1: a set-up or first-trigger check failed; the node is then stopped. Environment: SR_RUN (default run1), CASSANDRA_HOME (default ~/s4-b7-sr7),
SR_ROWS (row-count override) for shakedowns only."""
import json, os, re, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/s4-b7-sr7')
HARNESS = os.path.dirname(os.path.abspath(__file__))
MO = '/dev/shm/s4-b7-sr7'
RUN = os.environ.get('SR_RUN', 'run1')
MIB = 1 << 20
JMXPORT = 7150
ADDR = '127.0.5.1'
ROWS_A, ROWS_B, RATE_A = 3000, 2000, 50   # phase A throttled (clean samples), phase B unthrottled (disallow evidence)
ARMS = {  # offheap MiB, allocation type, value bytes, extra yaml
    'a64': (64, 'offheap_buffers', 116509, []), 'a128': (128, 'offheap_buffers', 116509, []), 'a64b': (64, 'offheap_buffers', 116509, []),
    'e64': (64, 'offheap_buffers', 131068, []), 'f64': (64, 'offheap_buffers', 131072, []),
    'h64': (64, 'heap_buffers', 116509, ['memtable_heap_space=64MiB']),
}
ROWS_OVERRIDE = os.environ.get('SR_ROWS')
BEANS = [('off', 'org.apache.cassandra.metrics:type=Table,name=AllMemtablesOffHeapDataSize', 'Value'),
         ('on', 'org.apache.cassandra.metrics:type=Table,name=AllMemtablesOnHeapDataSize', 'Value'),
         ('blocked', 'org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation', 'Count'),
         ('pending', 'org.apache.cassandra.metrics:type=MemtablePool,name=PendingFlushTasks', 'Value'),
         ('direct', 'java.nio:type=BufferPool,name=direct', 'MemoryUsed'),
         ('dcount', 'java.nio:type=BufferPool,name=direct', 'Count')]
NB = len(BEANS)

args = sys.argv[1:]
if len(args) != 1 or (args[0] not in ARMS and args[0] not in ('analyze', 'down')):
    sys.exit(__doc__)
arm = args[0]
ROOT = f'{HOME}/s4-b7-sr7-logs/{RUN}/cluster'
LOGS = f'{ROOT}/{arm}'
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
SUMMARY = open(LOGS + '/summary.txt', 'a' if arm in ('down', 'analyze') else 'w')
STOP = LOGS + '/stop.sampler'


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, file=sys.stderr)
    SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush(); log(s)


def sh(cmd, timeout=600, check=True, env=None, cwd=C, quiet=False):
    if not quiet:
        log('+ ' + cmd)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
    out = r.stdout + r.stderr
    if not quiet:
        SESSION.write(out[-3000:] + '\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed ({r.returncode}): {cmd}\n{out[-1500:]}')
    return r.returncode, out


def pid_of():
    try:
        pid = int(open(MO + '/cassandra.pid').read().strip())
        os.kill(pid, 0)
        return pid
    except (ValueError, OSError):
        return None


def mine():
    """java processes whose command line names this harness's tree or tmpfs directory (never another agent's node)"""
    return sh("ps -eo pid,args | awk '$2 ~ /java$/ && /s4-b7-sr7/' | cut -c1-170 || true", check=False, quiet=True)[1].strip()


def stop_node():
    pid = pid_of()
    if pid is None:
        return
    subprocess.run(['kill', str(pid)])
    for _ in range(120):
        if pid_of() is None:
            return
        time.sleep(1)
    log(f'node did not stop; kill -9 {pid}')
    subprocess.run(['kill', '-9', str(pid)])
    time.sleep(2)


CHILDREN = []


def fail(msg):
    note('FAIL: ' + msg)
    open(STOP, 'w').close()
    for p in CHILDREN:
        if p.poll() is None:
            p.kill()
    stop_node()
    sys.exit(1)


def client(*a, timeout=3600):
    rc, out = sh(f'python3 -I {HARNESS}/client.py ' + ' '.join(str(x) for x in a), timeout=timeout, check=False,
                 env=dict(os.environ, CASSANDRA_HOME=C))
    js = [l for l in out.splitlines() if l.startswith('{')]
    return json.loads(js[-1]) if rc == 0 and js else None


def proc_status(pid):
    d = {}
    try:
        for l in open(f'/proc/{pid}/status'):
            if l.startswith(('RssAnon', 'RssFile', 'RssShmem', 'VmRSS')):
                k, v = l.split(':')
                d[k] = int(v.split()[0]) * 1024
    except OSError:
        pass
    return d


def nmt(pid):
    rc, out = sh(f'jcmd {pid} VM.native_memory summary', check=False, quiet=True, timeout=60)
    m = re.search(r'Other \(reserved=\d+KB, committed=(\d+)KB\)', out)
    t = re.search(r'Total: reserved=\d+KB, committed=(\d+)KB', out)
    return (int(m.group(1)) * 1024 if m else None, int(t.group(1)) * 1024 if t else None)


def sampler_rss(pid):
    with open(LOGS + '/rss.csv', 'w') as f:
        f.write('ms,rssanon,rssfile,rssshmem,vmrss\n')
        while not os.path.exists(STOP):
            d = proc_status(pid)
            f.write(f"{int(time.time()*1000)},{d.get('RssAnon','')},{d.get('RssFile','')},{d.get('RssShmem','')},{d.get('VmRSS','')}\n"); f.flush()
            time.sleep(0.2)


def sampler_nmt(pid):
    with open(LOGS + '/nmt.csv', 'w') as f:
        f.write('ms,other_committed,total_committed\n')
        while not os.path.exists(STOP):
            o, t = nmt(pid)
            f.write(f'{int(time.time()*1000)},{o},{t}\n'); f.flush()
            for _ in range(50):
                if os.path.exists(STOP):
                    break
                time.sleep(0.1)


def jmx_get():
    cp = LOGS + '/jmxcls'
    _, out = sh(f'java -cp {cp} Jmx {JMXPORT} get ' + ' '.join(f"'{b}' {a}" for _, b, a in BEANS), check=False, quiet=True, timeout=120)
    res = {}
    for l in out.splitlines():
        p = l.rsplit('|', 2)
        if len(p) == 3:
            res[p[0] + '|' + p[1]] = p[2]
    return {k: res.get(b + '|' + a) for k, b, a in BEANS}


def read_csv(path):
    rows = []
    if os.path.exists(path):
        for l in open(path).read().splitlines()[1:]:
            rows.append(l.split(','))
    return rows


def hist_b(pid):
    """live bytes of [B (collecting class histogram) and the total"""
    rc, out = sh(f'jcmd {pid} GC.class_histogram', check=False, quiet=True, timeout=300)
    bb = tot = None
    for l in out.splitlines():
        m = re.match(r'\s*\d+:\s+(\d+)\s+(\d+)\s+(\S+)', l)
        if m and m.group(3) == '[B':
            bb = int(m.group(2))
        m = re.match(r'Total\s+(\d+)\s+(\d+)', l.strip())
        if m:
            tot = int(m.group(2))
    return bb, tot


def lifetime():
    L, alloc, V, extra = ARMS[arm]
    rowsA, rowsB = (int(ROWS_OVERRIDE), int(ROWS_OVERRIDE)) if ROWS_OVERRIDE else (ROWS_A, ROWS_B)
    rows = rowsA + rowsB
    heap = alloc == 'heap_buffers'
    note(f'cluster-run {arm} {time.strftime("%F %T %Z")} host {os.uname().nodename.split(".")[0]} tree {C} '
         f'{sh("git describe --tags", quiet=True)[1].strip()} L={L} {alloc} S={V} rows={rows}')
    if pid_of() is not None or mine():
        fail('a process of this harness is already running: ' + mine())
    busy = sh("ss -ltn", quiet=True)[1]
    for w in (f'{ADDR}:7000', f'{ADDR}:9042', f'127.0.0.1:{JMXPORT}'):
        if re.search(r'\s' + re.escape(w) + r'\s', busy):
            fail(f'port {w} is busy')
    sh(f'rm -rf {MO}')
    sh(f'mkdir -p {LOGS}/jmxcls && javac -d {LOGS}/jmxcls {HARNESS}/Jmx.java', cwd=HOME)
    yaml = [f'memtable_allocation_type={alloc}', f'memtable_offheap_space={L}MiB'] + extra
    _, y = sh(f'bash {HARNESS}/make-node-yaml.sh ' + ' '.join(f"'{a}'" for a in yaml), env=dict(os.environ, CASSANDRA_HOME=C, SR=MO))
    note(y.strip().splitlines()[-1][:900])
    env = dict(os.environ, CASSANDRA_CONF=MO + '/conf', CASSANDRA_LOG_DIR=MO + '/logs', MAX_HEAP_SIZE='2G',
               JVM_EXTRA_OPTS='-XX:NativeMemoryTracking=summary -XX:MaxDirectMemorySize=2g')
    env.pop('HEAP_NEWSIZE', None)
    t_start = time.time()
    sh(f"bash -c 'ulimit -n 100000 && exec bin/cassandra -p {MO}/cassandra.pid' > {MO}/stdout.txt 2>&1", env=env)
    up = False
    while time.time() - t_start < 300:
        time.sleep(3)
        if pid_of() is None:
            fail('node died during start; see ' + MO + '/stdout.txt')
        if client('probe', ADDR):
            up = True
            break
    if not up:
        fail('node not serving after 300 s')
    pid = pid_of()
    note(f'node up after {time.time()-t_start:.0f} s, pid {pid}')
    want = {'memtable_allocation_type': alloc, 'memtable_offheap_space': f'{L}MiB', 'memtable_heap_space': '64MiB' if heap else '256MiB',
            'memtable_flush_writers': '1', 'memtable_cleanup_threshold': '0.99', 'commitlog_total_space': '4096MiB',
            'file_cache_size': '64MiB', 'key_cache_size': '0MiB', 'row_cache_size': '0MiB', 'concurrent_compactors': '1'}
    got = client('settings', ADDR, *want.keys())
    bad = [k for k, v in want.items() if not got or str(got['settings'].get(k)) != v]
    note('EXPECTED settings read-back equals the yaml: ' + ('yes' if not bad else 'NO ' + json.dumps({k: (want[k], got['settings'].get(k) if got else None) for k in bad})))
    if bad:
        fail('settings read-back differs')
    jvm = sh(f'tr "\\0" " " < /proc/{pid}/cmdline', quiet=True, cwd=HOME)[1]
    note('EXPECTED JVM flags -Xmx2G, AlwaysPreTouch, NativeMemoryTracking=summary, MaxDirectMemorySize=2g: ' +
         ('yes' if all(x in jvm for x in ('-Xmx2G', '-XX:+AlwaysPreTouch', '-XX:NativeMemoryTracking=summary', '-XX:MaxDirectMemorySize=2g')) else 'NO'))
    s = client('schema', ADDR)
    if not s or not s.get('agreement'):
        fail('schema creation failed')
    sh(f'bin/nodetool -h 127.0.0.1 -p {JMXPORT} disableautocompaction ks t', check=False, timeout=120, env=dict(os.environ, JVM_EXTRA_OPTS=''))
    time.sleep(20)
    for _ in range(2):
        sh(f'jcmd {pid} GC.run', check=False)
        time.sleep(3)
    g = jmx_get()
    note('baseline gauges: ' + json.dumps(g))
    if any(v is None or str(v).startswith('ERROR') for v in g.values()):
        fail('a JMX gauge could not be read: ' + json.dumps(g))
    hist0 = hist_b(pid) if heap else (None, None)
    base_ms = int(time.time() * 1000)
    base = proc_status(pid)
    base_nmt = nmt(pid)
    note(f'baseline RssAnon {base.get("RssAnon")} VmRSS {base.get("VmRSS")} NMT Other {base_nmt[0]} total {base_nmt[1]} hist[B {hist0[0]}')
    for t in (threading.Thread(target=sampler_rss, args=(pid,), daemon=True), threading.Thread(target=sampler_nmt, args=(pid,), daemon=True)):
        t.start()
    cols = ' '.join(f"'{b}' {a}" for _, b, a in BEANS)
    jp = subprocess.Popen(f'java -cp {LOGS}/jmxcls Jmx {JMXPORT} poll 200 1000000 {STOP} {cols} > {LOGS}/jmx.csv 2> {LOGS}/jmx.err', shell=True)
    CHILDREN.append(jp)
    time.sleep(2)
    work_ms = int(time.time() * 1000)
    def start_client(n, rate, first, out):
        return subprocess.Popen(f'python3 -I {HARNESS}/client.py big {ADDR} {n} {V} 16 {rate} {first} > {LOGS}/{out} 2>&1', shell=True,
                                cwd=C, env=dict(os.environ, CASSANDRA_HOME=C))
    wp = start_client(rowsA, RATE_A, 1, 'bigA.out')
    CHILDREN.append(wp)
    log(f'workload phase A (throttled {RATE_A} rows/s, {rowsA} rows) started pid {wp.pid}')
    key = 1 if heap else 0
    ok = False
    t0 = time.time()
    while time.time() - t0 < 90:
        vals = [num(r[1 + key]) for r in read_csv(LOGS + '/jmx.csv') if len(r) == NB + 1]
        if any(v is not None and v >= MIB for v in vals):
            ok = True
            break
        if wp.poll() is not None:
            break
        time.sleep(2)
    note(f'EXPECTED first-trigger check: the tracked {"on" if key else "off"}-heap gauge reaches >= 1 MiB within 90 s of the workload start: ' + ('yes' if ok else 'NO'))
    if not ok:
        wp.kill()
        fail('first-trigger check failed')
    hist = None
    while wp.poll() is None:
        if heap and hist is None:
            vals = [num(r[1 + key]) for r in read_csv(LOGS + '/jmx.csv')[-3:] if len(r) == NB + 1]
            if vals and vals[-1] is not None and vals[-1] >= 0.9 * L * MIB:
                before = jmx_get()
                hb = hist_b(pid)
                after = jmx_get()
                hist = {'before_on': before['on'], 'after_on': after['on'], 'bb': hb[0], 'total': hb[1]}
                note('class histogram taken at the 0.9 mark: ' + json.dumps(hist))
        time.sleep(0.5)
    b_ms = int(time.time() * 1000)
    note(f'phase A exit {wp.returncode} after {(b_ms-work_ms)/1000:.0f} s; phase B (unthrottled, {rowsB} rows)')
    wpB = start_client(rowsB, 0, rowsA + 1, 'bigB.out')
    CHILDREN.append(wpB)
    wpB.wait(timeout=3000)
    end_ms = int(time.time() * 1000)
    note(f'workload exit A {wp.returncode} B {wpB.returncode} after {(end_ms-work_ms)/1000:.0f} s')
    time.sleep(10)
    mark10_ms = int(time.time() * 1000)
    sh(f'bin/nodetool -h 127.0.0.1 -p {JMXPORT} flush', check=False, timeout=300, env=dict(os.environ, JVM_EXTRA_OPTS=''))
    time.sleep(15)
    flush_ms = int(time.time() * 1000)
    g_after = jmx_get()
    note('gauges after flush: ' + json.dumps(g_after))
    open(STOP, 'w').close()
    time.sleep(3)
    if jp.poll() is None:
        jp.wait(timeout=30)
    stop_node()
    sh(f'cp {MO}/logs/system.log {LOGS}/system.log', check=False)
    sh(f'cp {MO}/stdout.txt {LOGS}/stdout.txt', check=False)
    res = {p: (json.load(open(f'{LOGS}/big{p}.out')) if os.path.exists(f'{LOGS}/big{p}.out') else {}) for p in 'AB'}
    json.dump({'arm': arm, 'L': L, 'alloc': alloc, 'V': V, 'rows': rows, 'pid': pid, 'base_ms': base_ms, 'work_ms': work_ms, 'phaseB_ms': b_ms, 'work_end_ms': end_ms,
               'mark10_ms': mark10_ms, 'flush_ms': flush_ms, 'baseline': base, 'baseline_nmt': base_nmt, 'baseline_gauges': g,
               'hist_base_bb': hist0[0], 'hist': hist, 'gauges_after_flush': g_after, 'big': res, 'client_rc': [wp.returncode, wpB.returncode]},
              open(LOGS + '/phases.json', 'w'), indent=1)
    for _ in range(60):
        if not mine():
            break
        time.sleep(1)
    sh(f'rm -rf {MO}', check=False)
    left = mine()
    note('EXPECTED nothing of this harness left running: ' + ('yes' if not left else 'NO ' + left[:300]))
    note(f'cluster-run {arm} end {time.strftime("%F %T %Z")}')


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    return None if n == 0 else (xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2)


def arm_stats(a):
    ph = json.load(open(f'{ROOT}/{a}/phases.json'))
    jm = [(int(r[0]), [num(x) for x in r[1:NB + 1]]) for r in read_csv(f'{ROOT}/{a}/jmx.csv') if len(r) == NB + 1]
    rs = [(int(r[0]), num(r[1])) for r in read_csv(f'{ROOT}/{a}/rss.csv') if len(r) == 5 and num(r[1]) is not None]
    w0, fl, pa = ph['work_ms'], ph['flush_ms'], ph['phaseB_ms']   # phase A = [w0, pa): throttled, no overlapping flush; phase B = [pa, fl]: unthrottled
    L = ph['L'] * MIB
    heap = ph['alloc'] == 'heap_buffers'
    d = {'ph': ph, 'L': L, 'heap': heap}
    d['peak_off'] = max([v[0] for t, v in jm if w0 <= t < pa and v[0] is not None] or [0])
    d['peak_on'] = max([v[1] for t, v in jm if w0 <= t < pa and v[1] is not None] or [0])
    d['peak_off_all'] = max([v[0] for t, v in jm if w0 <= t <= fl and v[0] is not None] or [0])
    d['peak_dir_all'] = max([v[4] for t, v in jm if w0 <= t <= fl and v[4] is not None] or [0]) - (num(ph['baseline_gauges'].get('direct')) or 0)
    d['peak_acc'] = d['peak_on'] if heap else d['peak_off']
    bl = [v[2] for t, v in jm if t >= ph['base_ms'] and v[2] is not None]
    d['blocked_first'] = bl[0] if bl else None
    d['blocked_last'] = bl[-1] if bl else None
    d['off_after_flush'] = jm[-1][1][0] if jm else None
    d['samples'] = len(jm)
    base = ph['baseline'].get('RssAnon') or 0
    d['rss_base'] = base
    d['rss_peak_delta'] = max([v for t, v in rs if w0 <= t < pa] or [base]) - base
    d['rss_peak_delta_all'] = max([v for t, v in rs if w0 <= t <= fl] or [base]) - base
    dbase = num(ph['baseline_gauges'].get('direct')) or 0
    d['direct_base'] = dbase
    d['peak_dir'] = max([v[4] for t, v in jm if w0 <= t < pa and v[4] is not None] or [dbase]) - dbase
    d['dir_end'] = (jm[-1][1][4] - dbase) if jm and jm[-1][1][4] is not None else None
    ratios = [(v[4] - dbase) / v[0] for t, v in jm if w0 <= t < pa and v[0] and v[4] is not None and v[0] >= 0.9 * L]
    d['rho'] = median(ratios)
    d['rho_n'] = len(ratios)
    flushes = 0
    for l in open(f'{ROOT}/{a}/system.log', errors='replace'):
        if 'Enqueuing flush of ks.t' in l and 'MEMTABLE_LIMIT' in l:
            flushes += 1
    d['flushes'] = flushes
    return d


def analyze():
    out = []

    def p(s):
        out.append(s); note(s)
    st = {}
    for a in ARMS:
        if os.path.exists(f'{ROOT}/{a}/phases.json'):
            st[a] = arm_stats(a)
    p(f'analysis of {RUN}: arms {sorted(st)}')
    for a, d in st.items():
        L = d['L']
        p(f'{a}: L={L/MIB:.0f} MiB S={ARMS[a][2]} {ARMS[a][1]} peak_acc={d["peak_acc"]/MIB:.1f} MiB ({d["peak_acc"]/L:.3f} L) peak_dir={d["peak_dir"]/MIB:.1f} MiB ({d["peak_dir"]/L:.3f} L) '
          f'(whole run: peak_acc {d["peak_off_all"]/MIB:.1f}, peak_dir {d["peak_dir_all"]/MIB:.1f}, rss {d["rss_peak_delta_all"]/MIB:.1f} MiB) rho={d["rho"]} (n={d["rho_n"]}) blocked {d["blocked_first"]}->{d["blocked_last"]} MEMTABLE_LIMIT flushes={d["flushes"]} rss_base={d["rss_base"]/MIB:.0f} MiB '
          f'rss_peak_delta={d["rss_peak_delta"]/MIB:.1f} MiB off_after_flush={d["off_after_flush"]} dir_end={d["dir_end"]} samples={d["samples"]} client_rc={d["ph"]["client_rc"]}')
        bA, bB = d['ph']['big']['A'], d['ph']['big']['B']
        p(f'{a}: client A ok={bA.get("ok")} err={bA.get("err")} seconds={bA.get("seconds")} rate={bA.get("rate")}; B ok={bB.get("ok")} err={bB.get("err")} seconds={bB.get("seconds")} errors={bA.get("errors")} {bB.get("errors")}')
        p(f'EXPECTED {a} client wrote every row without error (ok == rows, err == 0, both phases): ' + ('yes' if (bA.get('ok') or 0) + (bB.get('ok') or 0) == d['ph']['rows'] and not bA.get('err') and not bB.get('err') else 'NO'))
        p(f'EXPECTED {a} phase A was throttled and long enough (>= 40 s, rate within 10 % of {RATE_A}): ' + ('yes' if (bA.get('seconds') or 0) >= 40 and abs((bA.get('rate') or 0) - RATE_A) <= 0.1 * RATE_A else 'NO'))
    for a, d in st.items():
        L = d['L']
        if d['heap']:
            continue
        p(f'EXPECTED {a} limit reached and disallow evidence (blocked count grew, >= 2 MEMTABLE_LIMIT flushes): ' +
          ('yes' if (d['blocked_last'] or 0) > (d['blocked_first'] or 0) and d['flushes'] >= 2 else 'NO') + f' (blocked {d["blocked_first"]}->{d["blocked_last"]}, flushes {d["flushes"]})')
        p(f'EXPECTED {a} peak_acc in [0.90 L, 1.05 L]: ' + ('yes' if 0.90 * L <= d['peak_acc'] <= 1.05 * L else 'NO') + f' ({d["peak_acc"]/L:.3f})')
        band = {'e64': (0.97, 1.07), 'f64': (1.11, 1.20)}.get(a, (1.10, 1.20))
        p(f'EXPECTED {a} rho in [{band[0]}, {band[1]}]: ' + ('yes' if d['rho'] is not None and band[0] <= d['rho'] <= band[1] else 'NO') + f' ({d["rho"]})')
        p(f'EXPECTED {a} RssAnon peak delta in [0.9 peak_dir - 4 MiB, peak_dir + 0.25 L + 32 MiB]: ' +
          ('yes' if 0.9 * d['peak_dir'] - 4 * MIB <= d['rss_peak_delta'] <= d['peak_dir'] + 0.25 * L + 32 * MIB else 'NO') + f' (rss {d["rss_peak_delta"]/MIB:.1f}, dir {d["peak_dir"]/MIB:.1f} MiB)')
        p(f'EXPECTED {a} accounted gauge < 1 MiB and dir < 0.1 L after the final flush: ' +
          ('yes' if (d['off_after_flush'] or 0) < MIB and d['dir_end'] is not None and d['dir_end'] < 0.1 * L else 'NO') + f' (acc {d["off_after_flush"]}, dir {d["dir_end"]})')
        if a in ('a64', 'a128', 'a64b', 'f64'):
            pass
    if 'a64' in st:
        p('EXPECTED a64 peak_dir above L (the waste is visible): ' + ('yes' if st['a64']['peak_dir'] > st['a64']['L'] else 'NO') + f' ({st["a64"]["peak_dir"]/MIB:.1f} vs 64 MiB)')
    if 'a64' in st and 'a128' in st:
        r = st['a128']['peak_acc'] / st['a64']['peak_acc']
        p(f'EXPECTED peak_acc(a128)/peak_acc(a64) in [1.8, 2.2] (positive control): ' + ('yes' if 1.8 <= r <= 2.2 else 'NO') + f' ({r:.3f})')
        r = st['a128']['peak_dir'] / st['a64']['peak_dir']
        p(f'EXPECTED peak_dir(a128)/peak_dir(a64) in [1.7, 2.3]: ' + ('yes' if 1.7 <= r <= 2.3 else 'NO') + f' ({r:.3f})')
        r = st['a128']['rss_peak_delta'] / st['a64']['rss_peak_delta']
        p(f'EXPECTED RssAnon peak delta a128/a64 in [1.5, 2.5]: ' + ('yes' if 1.5 <= r <= 2.5 else 'NO') + f' ({r:.3f})')
    if 'a64' in st and 'a64b' in st:
        x, y = st['a64'], st['a64b']
        p('EXPECTED a64 vs a64b: peak_acc within 0.05 L and rho within 0.03: ' +
          ('yes' if abs(x['peak_acc'] - y['peak_acc']) <= 0.05 * x['L'] and x['rho'] is not None and y['rho'] is not None and abs(x['rho'] - y['rho']) <= 0.03 else 'NO') +
          f' ({x["peak_acc"]/MIB:.1f} vs {y["peak_acc"]/MIB:.1f} MiB; rho {x["rho"]} vs {y["rho"]})')
    if 'e64' in st and 'a64' in st and st['e64']['rho'] and st['a64']['rho']:
        p(f'EXPECTED rho(e64) < rho(a64) (the exact fit has less waste): ' + ('yes' if st['e64']['rho'] < st['a64']['rho'] else 'NO') + f' ({st["e64"]["rho"]:.4f} vs {st["a64"]["rho"]:.4f})')
    if 'h64' in st:
        d = st['h64']; L = d['L']
        ph = d['ph']
        p('EXPECTED h64 on-heap gauge peak in [0.90, 1.05] x 64 MiB with blocked growth: ' + ('yes' if 0.90 * L <= d['peak_on'] <= 1.05 * L and (d['blocked_last'] or 0) > (d['blocked_first'] or 0) else 'NO') +
          f' ({d["peak_on"]/MIB:.1f} MiB, blocked {d["blocked_first"]}->{d["blocked_last"]})')
        p('EXPECTED h64 off-heap gauge < 1 MiB and direct delta < 8 MiB: ' + ('yes' if d['peak_off'] < MIB and d['peak_dir'] < 8 * MIB else 'NO') + f' (off {d["peak_off"]/MIB:.2f}, dir {d["peak_dir"]/MIB:.2f} MiB)')
        h = ph.get('hist')
        if h and ph.get('hist_base_bb') is not None and h.get('bb') is not None:
            grow = h['bb'] - ph['hist_base_bb']
            acc = (num(h['before_on']) + num(h['after_on'])) / 2
            q = grow / acc
            p('EXPECTED h64 [B growth in [0.9, 1.3] x mean on-heap gauge around the histogram: ' + ('yes' if 0.9 <= q <= 1.3 else 'NO') + f' (growth {grow/MIB:.1f} MiB, gauge {acc/MIB:.1f} MiB, q={q:.3f})')
        else:
            p('EXPECTED h64 [B growth in [0.9, 1.3] x gauge: NO (no histogram taken)')
    open(ROOT + '/analysis.txt', 'w').write('\n'.join(out) + '\n')


if arm == 'analyze':
    analyze()
elif arm == 'down':
    stop_node()
    note('down: leftovers: ' + (mine() or 'none'))
else:
    try:
        lifetime()
    except SystemExit:
        raise
    except BaseException as e:
        log(f'EXCEPTION {type(e).__name__}: {e}')
        fail(f'exception {type(e).__name__}: {e}')
