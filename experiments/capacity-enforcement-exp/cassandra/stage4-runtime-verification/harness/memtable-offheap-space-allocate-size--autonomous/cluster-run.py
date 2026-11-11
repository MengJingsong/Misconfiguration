#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of memtable-offheap-space-allocate-size--autonomous (case file as amended 2026-10-26).
usage: cluster-run.py <arm> | analyze | down
  <arm>  one node lifetime (B3e steps 1-6): wipe /dev/shm/s4-b7-mo, write the yaml (make-node-yaml.sh), start the node
         (MAX_HEAP_SIZE=2G, the shipped -XX:+AlwaysPreTouch, JVM_EXTRA_OPTS=-XX:NativeMemoryTracking=summary -XX:MaxDirectMemorySize=256m),
         read the settings back from system_views.settings, idle 20 s, GC twice, baseline, then ONE workload with the samplers running
         (tracked gauges via Jmx.java every 200 ms; RssAnon every 200 ms; NMT summary every 5 s), then 10 s idle, nodetool flush,
         stop the node, copy system.log.
  Arms:  k128 k256 k512  offheap_objects, L MiB, cassandra-stress 3,000,000 x 1 KiB (128 threads)
         b128 b256 b512  offheap_objects, L MiB, 3000 x 256 KiB via client.py (16 threads, protocol 4)
         ctl             heap_buffers, memtable_offheap_space 256MiB, stress 1 KiB (mode-gating control)
         hp              heap_buffers, memtable_heap_space 128MiB, stress 1 KiB (binding-cap positive control)
  analyze reads every <arm>/phases.json and writes analysis.txt (the B3f/B3g relations, rules fixed in README.md).
  down    stop every process of this harness.
Ports of this agent (slot 3): 127.0.3.1 storage 7000 / native 9042, JMX 7130 (local JMX binds 127.0.0.1).
Output: ~/s4-b7-mo-logs/<MO_RUN>/cluster/<arm>/ (summary.txt with EXPECTED lines, session.log, jmx.csv, rss.csv, nmt.csv, phases.json,
system.log). Exit 1: a set-up or first-trigger check failed; the node is then stopped. Environment: MO_RUN (default run1),
CASSANDRA_HOME (default ~/s4-b7-mo), MO_N (stress row override), MO_BIG_N (large-row override) for shakedowns only."""
import json, os, re, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/s4-b7-mo')
HARNESS = os.path.dirname(os.path.abspath(__file__))
MO = '/dev/shm/s4-b7-mo'
RUN = os.environ.get('MO_RUN', 'run1')
MIB = 1 << 20
JMXPORT = 7130
ADDR = '127.0.3.1'
ARMS = {  # offheap MiB, allocation type, workload, extra yaml
    'k128': (128, 'offheap_objects', 'stress', []), 'k256': (256, 'offheap_objects', 'stress', []), 'k512': (512, 'offheap_objects', 'stress', []),
    'b128': (128, 'offheap_objects', 'big', []), 'b256': (256, 'offheap_objects', 'big', []), 'b512': (512, 'offheap_objects', 'big', []),
    'ctl': (256, 'heap_buffers', 'stress', []), 'hp': (256, 'heap_buffers', 'stress', ['memtable_heap_space=128MiB']),
}
STRESS_N = int(os.environ.get('MO_N', 3000000))
BIG_N = int(os.environ.get('MO_BIG_N', 3000))
BEANS = [('off', 'org.apache.cassandra.metrics:type=Table,name=AllMemtablesOffHeapDataSize', 'Value'),
         ('on', 'org.apache.cassandra.metrics:type=Table,name=AllMemtablesOnHeapDataSize', 'Value'),
         ('blocked', 'org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation', 'Count'),
         ('pending', 'org.apache.cassandra.metrics:type=MemtablePool,name=PendingFlushTasks', 'Value')]

args = sys.argv[1:]
if len(args) != 1 or (args[0] not in ARMS and args[0] not in ('analyze', 'down')):
    sys.exit(__doc__)
arm = args[0]
ROOT = f'{HOME}/s4-b7-mo-logs/{RUN}/cluster'
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
    return sh("ps -eo pid,args | awk '$2 ~ /java$/ && /s4-b7-mo/' | cut -c1-170 || true", check=False, quiet=True)[1].strip()


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
            res[p[0]] = p[2]
    return {k: res.get(b) for k, b, _ in BEANS}


def read_csv(path):
    rows = []
    if os.path.exists(path):
        for l in open(path).read().splitlines()[1:]:
            rows.append(l.split(','))
    return rows


def lifetime():
    L, alloc, work, extra = ARMS[arm]
    note(f'cluster-run {arm} {time.strftime("%F %T %Z")} host {os.uname().nodename.split(".")[0]} tree {C} '
         f'{sh("git describe --tags", quiet=True)[1].strip()} MO_N={STRESS_N} MO_BIG_N={BIG_N}')
    if pid_of() is not None or mine():
        fail('a process of this harness is already running: ' + mine())
    busy = sh("ss -ltn", quiet=True)[1]
    for w in (f'{ADDR}:7000', f'{ADDR}:9042', f'127.0.0.1:{JMXPORT}'):
        if re.search(r'\s' + re.escape(w) + r'\s', busy):
            fail(f'port {w} is busy')
    sh(f'rm -rf {MO}')
    sh(f'mkdir -p {LOGS}/jmxcls && javac -d {LOGS}/jmxcls {HARNESS}/Jmx.java', cwd=HOME)
    yaml = [f'memtable_allocation_type={alloc}', f'memtable_offheap_space={L}MiB'] + extra
    _, y = sh(f'bash {HARNESS}/make-node-yaml.sh ' + ' '.join(f"'{a}'" for a in yaml), env=dict(os.environ, CASSANDRA_HOME=C, MO=MO))
    note(y.strip().splitlines()[-1][:900])
    env = dict(os.environ, CASSANDRA_CONF=MO + '/conf', CASSANDRA_LOG_DIR=MO + '/logs', MAX_HEAP_SIZE='2G',
               JVM_EXTRA_OPTS='-XX:NativeMemoryTracking=summary -XX:MaxDirectMemorySize=256m')
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
    # settings read-back
    want = {'memtable_allocation_type': alloc, 'memtable_offheap_space': f'{L}MiB', 'memtable_heap_space': '128MiB' if arm == 'hp' else '1024MiB',
            'memtable_flush_writers': '1', 'memtable_cleanup_threshold': '0.99', 'commitlog_total_space': '4096MiB',
            'file_cache_size': '64MiB', 'key_cache_size': '0MiB', 'row_cache_size': '0MiB', 'concurrent_compactors': '1'}
    got = client('settings', ADDR, *want.keys())
    bad = [k for k, v in want.items() if not got or str(got['settings'].get(k)) != v]
    note('EXPECTED settings read-back equals the yaml: ' + ('yes' if not bad else 'NO ' + json.dumps({k: (want[k], got['settings'].get(k) if got else None) for k in bad})))
    if bad:
        fail('settings read-back differs')
    jvm = sh(f'tr "\\0" " " < /proc/{pid}/cmdline', quiet=True, cwd=HOME)[1]
    note('EXPECTED JVM flags -Xmx2G, AlwaysPreTouch, NativeMemoryTracking=summary, MaxDirectMemorySize=256m: ' +
         ('yes' if all(x in jvm for x in ('-Xmx2G', '-XX:+AlwaysPreTouch', '-XX:NativeMemoryTracking=summary', '-XX:MaxDirectMemorySize=256m')) else 'NO'))
    if work == 'big':
        s = client('schema', ADDR)
        if not s or not s.get('agreement'):
            fail('schema creation failed')
    time.sleep(20)
    for _ in range(2):
        sh(f'jcmd {pid} GC.run', check=False)
        time.sleep(3)
    g = jmx_get()
    note('baseline gauges: ' + json.dumps(g))
    if any(v is None or str(v).startswith('ERROR') for v in g.values()):
        fail('a JMX gauge could not be read: ' + json.dumps(g))
    base_ms = int(time.time() * 1000)
    base = proc_status(pid)
    base_nmt = nmt(pid)
    note(f'baseline RssAnon {base.get("RssAnon")} VmRSS {base.get("VmRSS")} NMT Other {base_nmt[0]} total {base_nmt[1]}')
    for t in (threading.Thread(target=sampler_rss, args=(pid,), daemon=True), threading.Thread(target=sampler_nmt, args=(pid,), daemon=True)):
        t.start()
    cols = ' '.join(f"'{b}' {a}" for _, b, a in BEANS)
    jp = subprocess.Popen(f'java -cp {LOGS}/jmxcls Jmx {JMXPORT} poll 200 1000000 {STOP} {cols} > {LOGS}/jmx.csv 2> {LOGS}/jmx.err', shell=True)
    CHILDREN.append(jp)
    time.sleep(2)
    work_ms = int(time.time() * 1000)
    res = {}
    if work == 'stress':
        cmd = (f'tools/bin/cassandra-stress write n={STRESS_N} cl=ONE -col size=FIXED\\(1024\\) n=FIXED\\(1\\) -rate threads=128 '
               f'-node {ADDR} -port native=9042 -mode native cql3 protocolVersion=4 -schema "replication(factor=1)" > {LOGS}/stress.out 2>&1')
        wenv = dict(os.environ); wenv.pop('JVM_EXTRA_OPTS', None)
        wp = subprocess.Popen(cmd, shell=True, cwd=C, env=wenv)
    else:
        wp = subprocess.Popen(f'python3 -I {HARNESS}/client.py big {ADDR} {BIG_N} 262144 16 > {LOGS}/big.out 2>&1', shell=True,
                              cwd=C, env=dict(os.environ, CASSANDRA_HOME=C))
    CHILDREN.append(wp)
    log(f'workload {work} started pid {wp.pid}')
    # first-trigger check: the tracked gauge must rise to >= 1 MiB within 90 s, else the workload does not reach the pool
    key = 1 if alloc == 'heap_buffers' else 0
    ok = False
    t0 = time.time()
    while time.time() - t0 < 90:
        rows = read_csv(LOGS + '/jmx.csv')
        vals = [num(r[1 + key]) for r in rows if len(r) == 5]
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
    wp.wait(timeout=3000)
    end_ms = int(time.time() * 1000)
    note(f'workload exit {wp.returncode} after {(end_ms-work_ms)/1000:.0f} s')
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
    end_nmt = nmt(pid)
    stop_node()
    sh(f'cp {MO}/logs/system.log {LOGS}/system.log', check=False)
    sh(f'cp {MO}/stdout.txt {LOGS}/stdout.txt', check=False)
    if work == 'big':
        res = json.load(open(LOGS + '/big.out')) if os.path.exists(LOGS + '/big.out') else {}
    json.dump({'arm': arm, 'L': L, 'alloc': alloc, 'work': work, 'pid': pid, 'base_ms': base_ms, 'work_ms': work_ms, 'work_end_ms': end_ms,
               'mark10_ms': mark10_ms, 'flush_ms': flush_ms, 'baseline': base, 'baseline_nmt': base_nmt, 'baseline_gauges': g,
               'gauges_after_flush': g_after, 'big': res, 'stress_rc': wp.returncode, 'stress_n': STRESS_N, 'big_n': BIG_N},
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


def arm_stats(a):
    ph = json.load(open(f'{ROOT}/{a}/phases.json'))
    jm = [(int(r[0]), [num(x) for x in r[1:5]]) for r in read_csv(f'{ROOT}/{a}/jmx.csv') if len(r) == 5]
    rs = [(int(r[0]), num(r[1])) for r in read_csv(f'{ROOT}/{a}/rss.csv') if len(r) == 5 and num(r[1]) is not None]
    nm = [(int(r[0]), num(r[1])) for r in read_csv(f'{ROOT}/{a}/nmt.csv') if len(r) == 3 and num(r[1]) is not None]
    w0, w1, fl = ph['work_ms'], ph['work_end_ms'], ph['flush_ms']
    d = {'ph': ph}
    d['peak_off'] = max([v[0] for t, v in jm if w0 <= t <= fl and v[0] is not None] or [0])
    d['peak_on'] = max([v[1] for t, v in jm if w0 <= t <= fl and v[1] is not None] or [0])
    bl = [v[2] for t, v in jm if t >= ph['base_ms'] and v[2] is not None]
    d['blocked_first'] = bl[0] if bl else None
    d['blocked_last'] = bl[-1] if bl else None
    d['off_after_flush'] = jm[-1][1][0] if jm else None
    d['samples'] = len(jm)
    base = ph['baseline'].get('RssAnon') or 0
    d['rss_base'] = base
    d['rss_peak_delta'] = max([v for t, v in rs if w0 <= t <= fl] or [base]) - base
    d['nmt_other_peak_delta'] = (max([v for t, v in nm if w0 <= t <= fl] or [0]) - (ph['baseline_nmt'][0] or 0))
    flushes = 0
    tbl = 'standard1' if ph['work'] == 'stress' else 'big'
    for l in open(f'{ROOT}/{a}/system.log', errors='replace'):
        if 'Enqueuing flush of' in l and tbl in l:
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
        L = ARMS[a][0] * MIB
        p(f'{a}: L={ARMS[a][0]} MiB peak_off={d["peak_off"]/MIB:.1f} MiB ({d["peak_off"]/L:.3f} L) peak_on={d["peak_on"]/MIB:.1f} MiB blocked {d["blocked_first"]}->{d["blocked_last"]} '
          f'flushes={d["flushes"]} rss_base={d["rss_base"]/MIB:.0f} MiB rss_peak_delta={d["rss_peak_delta"]/MIB:.1f} MiB nmt_other_peak_delta={d["nmt_other_peak_delta"]/MIB:.2f} MiB '
          f'off_after_flush={d["off_after_flush"]} samples={d["samples"]} stress_rc={d["ph"]["stress_rc"]}')
        if d['ph']['work'] == 'big':
            b = d['ph']['big']
            p(f'{a}: client ok={b.get("ok")} err={b.get("err")} errors={b.get("errors")} seconds={b.get("seconds")}')
    for kind, tol in (('k', 0.05 * 1.0), ('b', None)):
        for L in (128, 256, 512):
            a = f'{kind}{L}'
            if a not in st:
                continue
            d = st[a]; Lb = L * MIB
            bound = Lb * 1.05 if kind == 'k' else Lb + 4 * MIB
            p(f'EXPECTED {a} tracked peak <= {"1.05 L" if kind == "k" else "L + 4 MiB"}: ' + ('yes' if d['peak_off'] <= bound else 'NO') + f' ({d["peak_off"]/MIB:.1f} MiB vs {bound/MIB:.1f})')
            p(f'EXPECTED {a} limit reached (peak >= 0.9 L): ' + ('yes' if d['peak_off'] >= 0.9 * Lb else 'NO'))
            p(f'EXPECTED {a} writers blocked (BlockedOnAllocation count grew): ' + ('yes' if (d['blocked_last'] or 0) > (d['blocked_first'] or 0) else 'NO'))
            p(f'EXPECTED {a} flushed repeatedly (>= 2 "Enqueuing flush of" for the table): ' + ('yes' if d['flushes'] >= 2 else 'NO') + f' ({d["flushes"]})')
            p(f'EXPECTED {a} RssAnon peak delta <= 1.3 L: ' + ('yes' if d['rss_peak_delta'] <= 1.3 * Lb else 'NO') + f' ({d["rss_peak_delta"]/MIB:.1f} vs {1.3*L:.0f} MiB)')
            p(f'EXPECTED {a} tracked off-heap returns near 0 after the final flush (< 1 MiB): ' + ('yes' if (d['off_after_flush'] or 0) < MIB else 'NO'))
        if all(f'{kind}{L}' in st for L in (128, 256, 512)):
            pk = [st[f'{kind}{L}']['peak_off'] for L in (128, 256, 512)]
            rd = [st[f'{kind}{L}']['rss_peak_delta'] for L in (128, 256, 512)]
            p(f'EXPECTED {kind}: tracked peaks ordered 128 < 256 < 512: ' + ('yes' if pk[0] < pk[1] < pk[2] else 'NO') + f' ({[round(x/MIB,1) for x in pk]})')
            r2, r4 = rd[1] / rd[0] if rd[0] else None, rd[2] / rd[0] if rd[0] else None
            p(f'EXPECTED {kind}: RssAnon peak-delta ratios 256/128 in [1.5, 2.5] and 512/128 in [3.0, 5.0] (1:2:4 within 25 %): ' +
              ('yes' if r2 and r4 and 1.5 <= r2 <= 2.5 and 3.0 <= r4 <= 5.0 else 'NO') + f' ({r2 and round(r2,2)}, {r4 and round(r4,2)})')
    if 'ctl' in st:
        d = st['ctl']
        p('EXPECTED ctl (heap_buffers, L=256): tracked off-heap stays < 1 MiB: ' + ('yes' if d['peak_off'] < MIB else 'NO') + f' ({d["peak_off"]/MIB:.2f} MiB)')
        p('EXPECTED ctl: RssAnon peak delta <= 0.3 x 256 MiB (other consumers only, not L-sized): ' + ('yes' if d['rss_peak_delta'] <= 0.3 * 256 * MIB else 'NO') + f' ({d["rss_peak_delta"]/MIB:.1f} MiB)')
    if 'hp' in st:
        d = st['hp']
        p('EXPECTED hp (heap_buffers, memtable_heap_space 128MiB): tracked on-heap plateaus <= 1.05 x 128 MiB + 4 MiB: ' + ('yes' if d['peak_on'] <= 1.05 * 128 * MIB + 4 * MIB else 'NO') + f' ({d["peak_on"]/MIB:.1f} MiB)')
        p('EXPECTED hp: writers blocked (count grew): ' + ('yes' if (d['blocked_last'] or 0) > (d['blocked_first'] or 0) else 'NO'))
        p('EXPECTED hp: limit reached (on-heap peak >= 0.9 x 128 MiB): ' + ('yes' if d['peak_on'] >= 0.9 * 128 * MIB else 'NO'))
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
