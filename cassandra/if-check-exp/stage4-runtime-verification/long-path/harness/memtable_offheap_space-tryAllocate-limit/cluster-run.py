#!/usr/bin/env python3
"""Stage 4, memtable_offheap_space-tryAllocate-limit (case 9b-9e, amended 2026-10-13).
usage: cluster-run.py instrument
       cluster-run.py value <label> <arm>
           label: 128 | 256 | 512 | default | cleanup256 | floor256
                  cleanup256 = 256 MiB with the default memtable_cleanup_threshold, no C (9b control)
                  floor256   = load-floor control: unslabbed_heap_buffers, memtable_heap_space 256MiB, no C
           arm:   small (5 x 1 KiB cells) | oversize (one 192 KiB cell)
       cluster-run.py down
One node (~/cassandra-run1). Logs every command to ~/stage4-logs/mos/<run>/session.log and writes summary.txt
(EXPECTED lines), readings.csv, rss.csv, the Byteman escape-hatch trace and region ledger. Exit 1: a set-up or
instrument check failed; exit 3: writers never waited in B (9c: repeat with threads=512). The node and stress are
stopped and conf/cassandra.yaml restored on any exit."""
import csv, os, re, signal, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-run1')
HARNESS = os.path.dirname(os.path.abspath(__file__))
BM = C + '/build/lib/jars'
LOGROOT = os.environ.get('STAGE4_LOGROOT', HOME + '/stage4-logs/mos')   # shakedowns: ~/stage4-logs/mos-shakedown
MIB = 1048576
BEAN = 'org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation'
SYSLOG = C + '/logs/system.log'
DEBUGLOG = C + '/logs/debug.log'
LABELS = {  # label: (offheap knob MiB or None, cleanup threshold or None, run C, allocation type, heap space MiB)
    '128': (128, '0.99', True, 'offheap_objects', 2048),
    '256': (256, '0.99', True, 'offheap_objects', 2048),
    '512': (512, '0.99', True, 'offheap_objects', 2048),
    'default': (None, '0.99', True, 'offheap_objects', 2048),
    'cleanup256': (256, None, False, 'offheap_objects', 2048),
    'floor256': (None, '0.99', False, 'unslabbed_heap_buffers', 256),
}
ARMS = {  # arm: (rows, -col arguments, client threads)   9c
    'small': (int(os.environ.get('ROWS', 2000000)), ['size=FIXED(1024)'], int(os.environ.get('THREADS', 256))),
    'oversize': (int(os.environ.get('ROWS', 60000)), ['n=FIXED(1)', 'size=FIXED(196608)'], int(os.environ.get('THREADS', 64))),
}
STASH = 8 * sum(8192 << i for i in range(8))   # 8 regions per size class, 8 KiB .. 1 MiB = 15.94 MiB (9a)

D = None
SESSION = SUMMARY = None
RCSV = None
STRESS = None
SAMPLER_STOP = threading.Event()


def now():
    return int(time.time() * 1000)


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, file=sys.stderr)
    if SESSION:
        SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    print(s)
    if SUMMARY:
        SUMMARY.write(s + '\n'); SUMMARY.flush()
    log(s)


def reading(step, name, value, detail=''):
    if RCSV:
        RCSV.writerow([step, name, value, detail])


def sh(cmd, timeout=600, check=True, env=None, out=None):
    log('+ ' + cmd + (f' > {out}' if out else ''))
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env, cwd=C)
    text = (r.stdout or '') + (r.stderr or '')
    if out:
        with open(out, 'w') as f:
            f.write(text)
    if SESSION:
        SESSION.write(text[-3000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed rc={r.returncode}: {cmd}\n{text[-800:]}')
    return r.returncode, text


def daemon_pids():
    r = subprocess.run("ps -eo pid,args | grep '[o]rg.apache.cassandra.service.CassandraDaemon' | awk '{print $1}'",
                       shell=True, capture_output=True, text=True)
    return [p for p in r.stdout.split() if p.isdigit()]


def stop_all():
    global STRESS
    SAMPLER_STOP.set()
    if STRESS and STRESS.poll() is None:
        log('stopping stress'); os.killpg(STRESS.pid, signal.SIGTERM)
        try:
            STRESS.wait(30)
        except subprocess.TimeoutExpired:
            os.killpg(STRESS.pid, signal.SIGKILL)
    STRESS = None
    subprocess.run("pkill -f '[o]rg.apache.cassandra.stress.Stress'", shell=True)
    if daemon_pids():
        sh('bin/nodetool stopdaemon', check=False, timeout=120)
        for _ in range(90):
            if not daemon_pids():
                break
            time.sleep(1)
    for p in daemon_pids():
        log(f'kill -9 {p}'); subprocess.run(['kill', '-9', p]); time.sleep(2)


def finish(rc):
    stop_all()
    if D and os.path.exists(SYSLOG):
        sh(f'cp {SYSLOG} {D}/system.log', check=False)
        sh(f'cp {DEBUGLOG} {D}/debug.log', check=False)
    sh('git checkout -q conf/cassandra.yaml', check=False)
    left = len(daemon_pids())
    note(f"node stopped; ps -eo cmd | grep '[C]assandraDaemon' finds {left}")
    sys.exit(rc if left == 0 else 1)


def fail(msg, rc=1):
    note('FAIL: ' + msg)
    finish(rc)


def expect(desc, cond):
    note(f'EXPECTED: {desc} — {"yes" if cond else "NO (recorded; judged in the results file)"}')
    return cond


def open_run(name):
    global D, SESSION, SUMMARY, RCSV
    D = f'{LOGROOT}/{name}'
    if os.path.isdir(D) and os.listdir(D):
        os.rename(D, f'{D}.attempt-{int(time.time())}')
    os.makedirs(D)
    SESSION = open(D + '/session.log', 'a')
    SUMMARY = open(D + '/summary.txt', 'w')
    RCSV = csv.writer(open(D + '/readings.csv', 'w', newline=''))
    RCSV.writerow(['step', 'name', 'value', 'detail'])
    log(f'script: {" ".join(sys.argv)}; host: {os.uname().nodename}; clone: {C}; harness: {HARNESS}')
    note('clone HEAD: ' + sh('git rev-parse HEAD')[1].strip() + ' ' + sh('git describe --tags')[1].strip())
    note('harness md5: ' + sh(f'cd {HARNESS} && md5sum *.java *.btm *.py *.sh | tr "\\n" ";"')[1].strip())


# ------------------------------------------------------------------ instrument check (9e, before the cluster tier)
def instrument():
    open_run('instrument')
    esc, led, out = D + '/instrument-escape.txt', D + '/instrument-ledger.txt', D + '/instrument-stage4.out'
    for f in (esc, led, out):
        if os.path.exists(f):
            os.remove(f)
    sh(f'cp {HARNESS}/NativePoolTest.java test/unit/org/apache/cassandra/utils/memory/')
    sh(f'java -classpath {BM}/byteman-4.0.20.jar:build/classes/main:"build/lib/jars/*" org.jboss.byteman.check.TestScript '
       f'{HARNESS}/escape-hatch.btm {HARNESS}/region-ledger.btm', out=D + '/testscript.txt', check=False)
    ts = open(D + '/testscript.txt').read()
    note('Byteman TestScript: ' + ' | '.join(l for l in ts.splitlines() if re.search(r'^Type checked|ERROR|TestScript:', l)))
    if 'TestScript: no errors' not in ts:
        fail('Byteman TestScript reports errors (testscript.txt)')
    rc, _ = sh('ant testsome -Dtest.name=org.apache.cassandra.utils.memory.NativePoolTest '
               f'"-Dtest.jvm.args=-javaagent:{BM}/byteman-4.0.20.jar=script:{HARNESS}/escape-hatch.btm,script:{HARNESS}/region-ledger.btm '
               f'-Dstage4.byteman.out={esc} -Dstage4.ledger.out={led} -Dstage4.out={out}"',
               out=D + '/ant.txt', check=False, timeout=1200)
    ant = open(D + '/ant.txt').read()
    note('ant: ' + ' | '.join(re.findall(r'Tests run:[^\n]*|BUILD \w+', ant)))
    ok = 'Tests run: 1, Failures: 0, Errors: 0' in ant and rc == 0
    note('STAGE4 lines:\n  ' + open(out).read().strip().replace('\n', '\n  ') if os.path.exists(out) else 'no STAGE4 output')
    if not ok:
        fail('NativePoolTest did not pass with the rules attached')
    e = open(esc).read().splitlines() if os.path.exists(esc) else []
    note(f'escape-hatch trace: {e}')
    if not (len(e) == 1 and re.match(r'^forced=10 limit=100 ', e[0])):
        fail('escape-hatch trace is not exactly one line forced=10 limit=100')
    lines = open(led).read().splitlines() if os.path.exists(led) else []
    note('ledger:\n  ' + '\n  '.join(lines))
    mallocs = [l for l in lines if l.startswith('malloc ')]
    frees = [l for l in lines if l.startswith('free ')]
    disc = [l for l in lines if l.startswith('discard ')]
    peer = re.search(r'peer=(\d+)', mallocs[0]).group(1) if mallocs else None
    good = (len(mallocs) == 1 and ' cap=8192 ' in mallocs[0] and len(disc) == 1 and ' owns=110 ' in disc[0]
            and len(frees) == 1 and f'peer={peer} ' in frees[0] and ' cap=8192 ' in frees[0] and 'site=discard' in frees[0]
            and sum(l.startswith('discarded ') for l in lines) == 1)
    if not good:
        fail('ledger is not one malloc cap=8192, one discard owns=110, one free of the same peer cap=8192 site=discard')
    sh(f'python3 {HARNESS}/ledger.py {led}', out=D + '/instrument-ledger-read.txt')
    note(open(D + '/instrument-ledger-read.txt').read().strip())
    note('INSTRUMENT CHECK PASSED')
    finish(0)


# ------------------------------------------------------------------ readings
def blocked(attr='Count'):
    _, out = sh(f"bin/nodetool sjk mx -mg -b '{BEAN}' -f {attr}", check=False, timeout=60)
    toks = re.findall(r'-?\d+(?:\.\d+)?', (out.strip().splitlines() or [''])[-1])
    return float(toks[-1]) if toks else None


def count():
    v = blocked('Count')
    if v is None:
        fail('BlockedOnAllocation Count unreadable')
    return int(v)


def syslog_lines(pattern):
    if not os.path.exists(SYSLOG):
        return []
    with open(SYSLOG, errors='replace') as f:
        return [l.rstrip('\n') for l in f if re.search(pattern, l)]


def limit_flushes():
    return syslog_lines(r'Enqueuing flush of .*Reason: MEMTABLE_LIMIT')


def wait_limit_flushes(n, timeout):
    t0 = time.time()
    while len(limit_flushes()) < n:
        if STRESS.poll() is not None:
            fail(f'stress exited before limit-driven flush #{n}')
        if time.time() - t0 > timeout:
            fail(f'timeout {timeout}s waiting for limit-driven flush #{n}')
        time.sleep(0.5)
    log(f'limit-driven flush #{n} seen after {time.time() - t0:.1f}s')


def rss_sampler(pid, path):
    with open(path, 'w') as f:
        f.write('ms,RssAnon_kB,VmRSS_kB\n')
        while not SAMPLER_STOP.is_set():
            try:
                st = open(f'/proc/{pid}/status').read()
            except OSError:
                break
            anon = re.search(r'RssAnon:\s+(\d+)', st).group(1)
            rss = re.search(r'VmRSS:\s+(\d+)', st).group(1)
            f.write(f'{now()},{anon},{rss}\n'); f.flush()
            SAMPLER_STOP.wait(1.0)


def rss_rows(path):
    with open(path) as f:
        next(f)
        return [tuple(int(x) for x in l.split(',')) for l in f if l.strip()]


def nmt(pid, tag):
    out = f'{D}/nmt-{tag}.txt'
    sh(f'jcmd {pid} VM.native_memory summary', out=out, check=False)
    txt = open(out).read()
    tot = re.search(r'Total: reserved=(\d+)KB, committed=(\d+)KB', txt)
    oth = re.search(r'-\s+Other \(reserved=(\d+)KB, committed=(\d+)KB', txt)
    note(f'NMT {tag}: total committed {tot.group(2) if tot else "?"} KB; Other committed {oth.group(2) if oth else "?"} KB')
    reading(tag, 'nmt_total_committed_kB', tot.group(2) if tot else '')
    reading(tag, 'nmt_other_committed_kB', oth.group(2) if oth else '')


def offheap_used_totals(lines):
    return [float(m.group(1)) for l in lines for m in [re.search(r'Used total: [0-9.]+/([0-9.]+)', l)] if m]


def trace_sum(path, limit_bytes, t0=None, t1=None):
    n = s = other = 0
    if os.path.exists(path):
        for l in open(path):
            m = re.match(r'forced=(\d+) limit=(\d+) ms=(\d+)', l)
            if not m:
                continue
            size, lim, ms = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if (t0 is not None and ms < t0) or (t1 is not None and ms >= t1):
                continue
            if lim == limit_bytes:
                n += 1; s += size
            else:
                other += 1
    return n, s, other


# ------------------------------------------------------------------ one capacity value, one arm
def value(label, arm):
    global STRESS
    knob, clean, run_c, atype, heap_mib = LABELS[label]
    rows, cols, threads = ARMS[arm]
    offheap = atype == 'offheap_objects'
    open_run(f'{label}-{arm}')
    esc, led, rss = D + '/escape-hatch.txt', D + '/ledger.txt', D + '/rss.csv'
    note(f'== {label}-{arm}: type={atype} offheap knob={knob or "unset"} heap={heap_mib}MiB cleanup={clean or "default"} '
         f'C={"yes" if run_c else "no"}; stress n={rows} -col {" ".join(cols)} threads={threads}')

    # preflight
    if daemon_pids():
        fail('a CassandraDaemon is already running')
    _, ss = sh('ss -ltn', check=False)
    if re.search(r':(7000|7199|9042|9091)\b', ss):
        fail('one of ports 7000/7199/9042/9091 is in use')
    free_gb = int(sh(f"df --output=avail -BG {HOME} | tail -1 | tr -dc 0-9")[1].strip())
    if free_gb < 25:
        fail(f'only {free_gb} GB free on the local disk')

    # config (9b): the tag's yaml plus exactly these lines
    sh('git show HEAD:conf/cassandra.yaml > conf/cassandra.yaml')
    y = open(C + '/conf/cassandra.yaml').read()
    want = [f'memtable_heap_space: {heap_mib}MiB']
    y = y.replace('\n# memtable_heap_space: 2048MiB\n', f'\nmemtable_heap_space: {heap_mib}MiB\n', 1)
    if knob:
        y = y.replace('\n# memtable_offheap_space: 2048MiB\n', f'\nmemtable_offheap_space: {knob}MiB\n', 1)
        want.append(f'memtable_offheap_space: {knob}MiB')
    if clean:
        y = y.replace('\n# memtable_cleanup_threshold: 0.11\n', f'\nmemtable_cleanup_threshold: {clean}\n', 1)
        want.append(f'memtable_cleanup_threshold: {clean}')
    y = y.replace('\nmemtable_allocation_type: heap_buffers\n', f'\nmemtable_allocation_type: {atype}\n', 1)
    want.append(f'memtable_allocation_type: {atype}')
    open(C + '/conf/cassandra.yaml', 'w').write(y)
    got = re.findall(r'^(memtable_(?:heap_space|offheap_space|cleanup_threshold|allocation_type): .*)$', y, re.M)
    note(f'yaml memtable lines: {got}')
    if sorted(got) != sorted(want):
        fail(f'yaml memtable lines {got} != {want}')
    sh(f'git diff -U0 conf/cassandra.yaml', out=D + '/cassandra.diff')
    changed = [l for l in open(D + '/cassandra.diff').read().splitlines() if l.startswith('+') and not l.startswith('+++')]
    if len(changed) != len(want):
        fail(f'yaml diff has {len(changed)} added lines, expected {len(want)}')

    # reset (9b) and start (9e step 2)
    if C != HOME + '/cassandra-run1':
        fail(f'unexpected clone path {C}')
    sh('rm -rf data logs saved_caches cassandra.pid')
    env = dict(os.environ, MAX_HEAP_SIZE='4G',
               JVM_EXTRA_OPTS=f'-XX:NativeMemoryTracking=summary -javaagent:{BM}/byteman-4.0.20.jar=script:{HARNESS}/escape-hatch.btm,'
                              f'script:{HARNESS}/region-ledger.btm,listener:true -Dstage4.byteman.out={esc} -Dstage4.ledger.out={led}')
    env.pop('HEAP_NEWSIZE', None)
    note('JVM_EXTRA_OPTS=' + env['JVM_EXTRA_OPTS'])
    t_start = now()
    sh(f'bin/cassandra -p {D}/cassandra.pid > {D}/stdout.txt 2>&1', env=env)
    for _ in range(300):
        pid = open(f'{D}/cassandra.pid').read().strip() if os.path.exists(f'{D}/cassandra.pid') else ''
        if pid and not os.path.exists(f'/proc/{pid}'):
            fail('node process died during startup (stdout.txt)')
        if syslog_lines(r'Starting listening for CQL clients'):
            break
        time.sleep(1)
    else:
        fail('node did not start listening for CQL clients in 300 s')
    pid = open(f'{D}/cassandra.pid').read().strip()
    note(f'node pid {pid}, up after {(now() - t_start) / 1000:.0f} s')
    threading.Thread(target=rss_sampler, args=(pid, rss), daemon=True).start()
    args = open(f'/proc/{pid}/cmdline').read().split('\0')
    open(D + '/jvm-args.txt', 'w').write('\n'.join(args))
    for a in ('-Xms4G', '-Xmx4G', '-XX:NativeMemoryTracking=summary'):
        if a not in args:
            fail(f'JVM lacks {a}')
    if not any('byteman-4.0.20.jar' in a for a in args):
        fail('JVM lacks the Byteman agent')

    # confirmation lines (9b)
    l1 = (syslog_lines(r'Global memtable off-heap threshold is (enabled|disabled)') or [''])[0]
    l2 = (syslog_lines(r'Global memtable on-heap threshold is enabled at') or [''])[0]
    dbg = open(DEBUGLOG, errors='replace').read() if os.path.exists(DEBUGLOG) else ''
    want_dbg = 'Memtables allocating with off-heap objects' if offheap else 'Memtables allocating with on-heap buffers'
    note(f'system.log: {l1.strip()[-120:]}'); note(f'system.log: {l2.strip()[-120:]}')
    note(f'debug.log has "{want_dbg}": {want_dbg in dbg}')
    if want_dbg not in dbg:
        fail(f'debug.log lacks "{want_dbg}" (wrong pool built)')
    m = re.search(r'off-heap threshold is enabled at (\d+)MiB', l1)
    lim_mib = int(m.group(1)) if m else None
    if offheap:
        if lim_mib is None:
            fail(f'cannot read the off-heap limit from: {l1!r}')
        if knob and lim_mib != knob:
            fail(f'resolved off-heap limit {lim_mib} MiB != knob {knob} MiB')
        if not knob and not 1000 <= lim_mib <= 1024:
            fail(f'default off-heap limit {lim_mib} MiB is not about 1024 MiB')
    LIMIT = (lim_mib or 0) * MIB
    note(f'resolved off-heap limit: {lim_mib} MiB = {LIMIT} B')
    reading('config', 'offheap_limit_bytes', LIMIT)

    # instrument in place (9e step 2)
    sh(f'java -cp {BM}/byteman-submit-4.0.20.jar org.jboss.byteman.agent.submit.Submit -l', out=D + '/submit-l.txt')
    sl = open(D + '/submit-l.txt').read()
    need = ['trigger method: org.apache.cassandra.utils.memory.MemtableAllocator$SubAllocator.allocated(long) void']
    if offheap:
        need += ['NativeAllocator$Region.<init>', 'NativeAllocator.trySwapRegion', 'NativeAllocator.setDiscarded']
    for n in need:
        if n not in sl:
            fail(f'Submit -l does not list {n}')
    note('Submit -l lists: ' + '; '.join(need))

    # idle control (9e step 1): at least 60 s of uptime
    wait = 60 - (now() - t_start) / 1000
    if wait > 0:
        log(f'idle: waiting {wait:.0f} s more'); time.sleep(wait)
    t_idle = now()
    c_idle = count()
    nmt(pid, 'idle')
    rr = rss_rows(rss)
    rss_idle = [r for r in rr if r[0] <= t_idle][-1][1]
    note(f'idle at ms={t_idle}: BlockedOnAllocation Count={c_idle}; RssAnon={rss_idle} kB')
    reading('idle', 'ms', t_idle); reading('idle', 'blocked_count', c_idle); reading('idle', 'rss_anon_kB', rss_idle)

    # scenario A (9e step 2)
    sh("bin/cqlsh -e \"CREATE KEYSPACE keyspace1 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1} "
       "AND durable_writes = false;\"")
    _, ks = sh('bin/cqlsh -e "DESCRIBE KEYSPACE keyspace1"', check=False)
    if 'durable_writes = false' not in ks:
        fail('keyspace1 does not have durable_writes = false')
    senv = {k: v for k, v in os.environ.items() if k not in ('JVM_EXTRA_OPTS', 'MAX_HEAP_SIZE')}
    scmd = ['tools/bin/cassandra-stress', 'write', f'n={rows}', 'no-warmup', '-col', *cols, '-rate', f'threads={threads}']
    t_a0 = now()
    log('+ ' + ' '.join(scmd) + f' > {D}/stress.txt   (T_A0={t_a0})')
    STRESS = subprocess.Popen(scmd, cwd=C, env=senv, stdout=open(D + '/stress.txt', 'w'), stderr=subprocess.STDOUT,
                              start_new_session=True)
    wait_limit_flushes(1, 1200)
    t_a1 = now()
    c_a = count()
    first = limit_flushes()[0]
    used = (syslog_lines(r'Used total') or [''])[0]
    note(f'A: first limit flush after {t_a1 - t_a0} ms; BlockedOnAllocation Count={c_a}')
    note(f'A Enqueuing: {first[first.find("Enqueuing"):][:220]}')
    note(f'A Used total: {used[used.find("Flushing"):][:240]}')
    mu = re.search(r'([0-9.]+[KMG]i?B) \((\d+)%\) off-heap', first)
    if mu:
        reading('A', 'first_limit_flush_offheap', mu.group(1)); reading('A', 'first_limit_flush_offheap_pct', mu.group(2))
    reading('A', 'ms', t_a1); reading('A', 'blocked_count', c_a)

    # scenario B (9e step 3): three more limit-driven flushes, one thread dump at each
    for k in (2, 3, 4):
        wait_limit_flushes(k, 900)
        td = f'{D}/threaddump-B{k - 1}.txt'
        sh(f'jcmd {pid} Thread.print', out=td, check=False)
        frames = open(td).read().count('MemtableAllocator.java:195')
        note(f'B dump {k - 1}: at limit flush #{k}; frames at MemtableAllocator.java:195 = {frames}')
        reading('B', f'dump{k - 1}_frames_195', frames)
    c_b = count()
    note(f'B end ms={now()}: BlockedOnAllocation Count at A={c_a}, after B={c_b}')
    for attr in ('50thPercentile', '95thPercentile', 'Max'):
        note(f'  BlockedOnAllocation {attr} = {blocked(attr)}')
    nmt(pid, 'endB')
    sh('bin/nodetool tablestats', out=D + '/tablestats-B.txt', check=False)
    reasons = {}
    for l in syslog_lines(r'Enqueuing flush'):
        r = re.search(r'Reason: (\w+)', l)
        reasons[r.group(1) if r else '?'] = reasons.get(r.group(1) if r else '?', 0) + 1
    note(f'B Enqueuing flush reasons so far: {reasons}')
    reading('B', 'blocked_count', c_b)
    if clean and c_b <= c_idle:
        note(f'B: BlockedOnAllocation Count did not rise (idle {c_idle}, B {c_b}): no writer waited (9c: repeat with threads=512)')
        finish(3)

    # scenario C (9e step 4)
    t_c0 = now()
    if run_c:
        for i in range(60):
            c1 = count(); time.sleep(3); c2 = count()
            if c2 > c1:
                break
            if STRESS.poll() is not None:
                fail('stress exited before the wait count was rising')
        else:
            fail('BlockedOnAllocation Count never rising before C')
        note(f'C: count rising ({c1} -> {c2})')
        nlines = len(open(SYSLOG, errors='replace').read().splitlines())
        t_c0 = now()
        t = time.time()
        sh('bin/nodetool flush keyspace1 standard1', timeout=600)
        note(f'C: nodetool flush returned after {time.time() - t:.1f} s (T_C0={t_c0})')
        after = open(SYSLOG, errors='replace').read().splitlines()[nlines:]
        open(D + '/system-log-after-C0.txt', 'w').write('\n'.join(after) + '\n')
        ut = offheap_used_totals([l for l in after if 'Used total' in l])
        note(f'C Enqueuing since T_C0: {sum("Enqueuing flush" in l for l in after)}; off-heap Used total since T_C0: {ut}; above 1.00: {[u for u in ut if u > 1.0]}')

    # stop (9e step 5)
    t_stop = now()
    stop_all()
    if daemon_pids():
        fail('a CassandraDaemon is still running after stopdaemon')
    note("ps -eo cmd | grep '[C]assandraDaemon' finds nothing after stopdaemon")
    st = open(D + '/stress.txt', errors='replace').read()
    note(f'stress: {len(re.findall(r"(?i)timed? ?out|exception", st))} lines mention timeout/exception (symptom only)')
    note(f'windows (ms): T_idle={t_idle} T_A0={t_a0} T_A1={t_a1} T_C0={t_c0} T_STOP={t_stop}')

    # escape-hatch trace (bypass volume, 9d)
    n, F, other = trace_sum(esc, LIMIT)
    note(f'escape-hatch trace, lines with limit = off-heap knob ({LIMIT} B): {n} calls, {F} B; other-limit lines: {other}')
    for nm, a0, a1 in (('A', t_a0, t_a1), ('B', t_a1, t_c0), ('C' if run_c else 'after B', t_c0, t_stop + 1)):
        wn, ws, _ = trace_sum(esc, LIMIT, a0, a1)
        note(f'  window {nm}: {wn} calls, {ws} B')
    reading('trace', 'forced_calls', n); reading('trace', 'forced_bytes', F)

    # accounted counter at flush starts
    ut_all = offheap_used_totals(syslog_lines(r'Used total'))
    pcts = [int(m.group(1)) for l in limit_flushes() if 'keyspace1' in l for m in [re.search(r'\((\d+)%\) off-heap', l)] if m]
    note(f'whole run: keyspace1 MEMTABLE_LIMIT flushes {len(pcts)}, off-heap Usage % at each: {pcts}')
    note(f'whole run: max off-heap Used total = {max(ut_all) if ut_all else None}')
    reading('run', 'limit_flushes_keyspace1', len(pcts)); reading('run', 'max_used_total_offheap', max(ut_all) if ut_all else '')

    # region ledger (9a Prediction)
    sh(f'python3 {HARNESS}/ledger.py {led} --idle-ms {t_idle} --from-ms {t_a0} --to-ms {t_stop} --json {D}/ledger.json',
       out=D + '/ledger-read.txt', check=False)
    note(open(D + '/ledger-read.txt').read().strip())
    import json
    lj = json.load(open(D + '/ledger.json')) if os.path.exists(D + '/ledger.json') else None
    rr = rss_rows(rss)
    win = [r for r in rr if t_a0 <= r[0] <= t_stop]
    rss_max = max(win, key=lambda r: r[1]) if win else None
    d_rss = (rss_max[1] - rss_idle) * 1024 if rss_max else None
    note(f'RssAnon: idle {rss_idle} kB; max in [T_A0,T_STOP] {rss_max[1] if rss_max else None} kB at ms={rss_max[0] if rss_max else None}; '
         f'max dRssAnon = {"%.1f MiB" % (d_rss / MIB) if d_rss is not None else None}')
    reading('rss', 'max_d_rss_anon_bytes', d_rss)
    if not offheap:
        expect('load-floor control: the ledger has no malloc line', not os.path.exists(led) or 'malloc' not in open(led).read())
        note(f'== {label}-{arm}: COMPLETE'); finish(0)
    if not lj or lj['counts']['malloc'] == 0:
        fail('the ledger has no malloc line (instrument failed: 9a Invalid run)')
    dl = lj['max_L'] - lj['L_idle']
    lo = 0.99 * LIMIT - lj['L_idle'] - MIB
    hi = LIMIT + F + 19 * MIB + 0.002 * LIMIT
    reading('ledger', 'L_idle', lj['L_idle']); reading('ledger', 'max_L', lj['max_L']); reading('ledger', 'max_L_minus_idle', dl)
    reading('ledger', 'discards_ge_8MiB', lj['discards_ge_8MiB']); reading('ledger', 'discards_outside_bound', len(lj['discards_outside_bound']))
    expect(f'writers waited in B (BlockedOnAllocation {c_idle} -> {c_b})', c_b > c_idle)
    if clean:
        expect(f'first limit flush at about 99 % of the limit (Usage {mu.group(2) if mu else "?"} %)', bool(mu) and int(mu.group(2)) >= 97)
    expect(f'no off-heap Used total above 1.00 at any flush start (max {max(ut_all) if ut_all else None})', not ut_all or max(ut_all) <= 1.0)
    expect(f'per discard: 0 <= P_m - A_m <= 1 MiB + 0.002 A_m for all {len(lj["discards"])} discards',
           not lj['discards_outside_bound'])
    expect(f'node-wide: {lo / MIB:.2f} MiB <= max L - L_idle = {dl / MIB:.2f} MiB <= {hi / MIB:.2f} MiB '
           f'(limit + F {F} B + 19 MiB + 0.002 limit; stash max {STASH / MIB:.2f} MiB)', lo <= dl <= hi)
    expect(f'ledger consistent (unmatched frees {lj["unmatched_free"]}, mallocs of a live peer {lj["double_malloc"]}, bad lines {lj["counts"]["bad"]})',
           lj['unmatched_free'] == 0 and lj['double_malloc'] == 0 and lj['counts']['bad'] == 0)
    note(f'max L / limit = {lj["max_L"] / LIMIT:.4f}; max dRssAnon - (max L - L_idle) = {(d_rss - dl) / MIB if d_rss is not None else float("nan"):.1f} MiB '
         '(compared with the load-floor control in the results file)')
    grep = [l for l in open(SYSLOG, errors='replace') if re.search(r'Enqueuing flush|Flushing largest|Completed flushing|Global memtable|^ERROR|^WARN', l)]
    open(D + '/system-log-key-lines.txt', 'w').writelines(grep)
    note(f'== {label}-{arm}: COMPLETE')
    finish(0)


def down():
    open_run('down')
    finish(0)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    os.makedirs(LOGROOT, exist_ok=True)
    try:
        if sys.argv[1] == 'instrument':
            instrument()
        elif sys.argv[1] == 'value' and len(sys.argv) == 4 and sys.argv[2] in LABELS and sys.argv[3] in ARMS:
            value(sys.argv[2], sys.argv[3])
        elif sys.argv[1] == 'down':
            down()
        else:
            print(__doc__); sys.exit(2)
    except SystemExit:
        raise
    except BaseException as e:
        import traceback
        log('EXCEPTION: ' + traceback.format_exc())
        fail(f'exception: {e!r}')
