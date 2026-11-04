#!/usr/bin/env python3
"""Stage 4, cluster tier, min-threshold-getEstimatedCompactionsByTasks-bucketSize--autonomous (B3 as amended, 2026-10-27).
usage: cluster-run.py [run-name]        output: ~/s4-b11-m71-logs/<run-name, default run1>/cluster/
One node on 127.0.1.1 (port slot 1: JMX 7110, native 9042), tree ~/s4-b11-m71-n (ant jar), conf ~/s4-b11-m71-node, data on tmpfs
/dev/shm/s4-b11-m71, -Xms2G -Xmx2G, concurrent_compactors=1, compaction_throughput=8MiB/s.
Arms (B3b, B3h): estimate arms min in {2,4,16} x MT_REPS (3) repetitions, max_threshold 32; control arms min 4 with max 4 and max 32.
Each arm: a fresh keyspace; ten cassandra-stress 'write n=20000' invocations (1 KiB value, disjoint -pop ranges), a flush after each;
the table is created with min=max=32 and autocompaction is disabled after the first invocation, so nothing compacts during ingest;
'setcompactionthreshold ks standard1 <min> <max>'; BASELINE sample (gauge, tablestats, du, RssAnon, live heap); 'enableautocompaction'
(the estimate refresh); POLL every ~2 s (gauge + du + the 'Compacted' lines of system.log) until the compaction ends or MT_OBS seconds.
Every command is logged to session.log; ARM/EXPECTED lines go to summary.txt, then analyze-cluster.py. The node is stopped on any exit.
Env overrides for plumbing shakedowns only: MT_REPS (3), MT_OBS (150), MT_FLUSHES (10), MT_ROWS (20000), MT_ARMS (comma list of arm names)."""
import glob, json, os, re, subprocess, sys, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/s4-b11-m71-n')
HARNESS = os.path.dirname(os.path.abspath(__file__))
MTN = HOME + '/s4-b11-m71-node'
DD = '/dev/shm/s4-b11-m71'
RUN = sys.argv[1] if len(sys.argv) > 1 else 'run1'
D = f'{HOME}/s4-b11-m71-logs/{RUN}/cluster'
os.makedirs(D, exist_ok=True)
SESSION = open(D + '/session.log', 'a')
SUMMARY = open(D + '/summary.txt', 'w')
ADDR, JMX = '127.0.1.1', 7110
REPS = int(os.environ.get('MT_REPS', '3'))
OBS = int(os.environ.get('MT_OBS', '150'))
FLUSHES = int(os.environ.get('MT_FLUSHES', '10'))
ROWS = int(os.environ.get('MT_ROWS', '20000'))


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, file=sys.stderr); SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush(); SESSION.write(s + '\n'); SESSION.flush()


def sh(cmd, timeout=600, check=True, env=None, quiet=False):
    if not quiet:
        log('+ ' + cmd[:400])
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env, cwd=C)
    out = (r.stdout or '') + (r.stderr or '')
    if not quiet:
        SESSION.write(out[-2000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed rc={r.returncode}: {cmd[:200]}\n{out[-800:]}')
    return r.returncode, out


def java_daemons():
    r = subprocess.run(['ps', '-eo', 'pid,comm,args'], capture_output=True, text=True)
    out = []
    for l in r.stdout.splitlines()[1:]:
        p = l.split(None, 2)
        if len(p) == 3 and p[1] == 'java' and 'org.apache.cassandra.service.CassandraDaemon' in p[2]:
            out.append(p[0] + ' ' + p[2])
    return out


def pid_of():
    for l in java_daemons():
        if MTN in l:
            return int(l.split()[0])
    return None


def stop_node():
    p = pid_of()
    if p:
        sh(f'bin/nodetool -h 127.0.0.1 -p {JMX} stopdaemon', check=False, timeout=120)
        for _ in range(60):
            if pid_of() is None:
                break
            time.sleep(1)
        if pid_of():
            sh(f'kill -9 {pid_of()}', check=False)
            time.sleep(2)
    if pid_of():
        log('WARNING: my CassandraDaemon is still running')


def fail(msg):
    note('FAIL: ' + msg)
    stop_node()
    sys.exit(1)


def expect(desc, cond):
    note(f'EXPECTED: {desc} — {"yes" if cond else "NO (recorded; the AI judges it in the results file)"}')
    return cond


def nt(args, **kw):
    return sh(f'bin/nodetool -h 127.0.0.1 -p {JMX} {args}', **kw)


def start_node():
    stop_node()
    if pid_of():
        fail('my CassandraDaemon is still running')
    sh(f'rm -rf {DD} {MTN}/logs', check=False)
    _, y = sh(f'{HARNESS}/make-node-yaml.sh concurrent_compactors=1 compaction_throughput=8MiB/s')
    note('yaml: ' + y.strip().splitlines()[-1][:1500])
    env = dict(os.environ, CASSANDRA_CONF=MTN + '/conf', CASSANDRA_LOG_DIR=MTN + '/logs', MAX_HEAP_SIZE='2G')
    env.pop('HEAP_NEWSIZE', None)
    env['JVM_EXTRA_OPTS'] = f'-Xlog:gc:file={D}/gc.log:utc'
    sh(f'ulimit -n 100000 && bin/cassandra -p {MTN}/cassandra.pid > {D}/stdout.txt 2>&1', env=env)
    time.sleep(5)
    if pid_of() is None:
        fail(f'node did not start; see {D}/stdout.txt')
    t0 = time.time()
    while time.time() - t0 < 300:
        if pid_of() is None:
            fail('node died during start-up')
        _, st = nt('status', check=False, quiet=True)
        _, sb = nt('statusbinary', check=False, quiet=True)
        if re.search(rf'^UN\s+{re.escape(ADDR)}\s', st, re.M) and re.search(r'^running\s*$', sb, re.M):
            log(f'node UN and native transport running after {time.time() - t0:.0f} s')
            break
        time.sleep(2)
    else:
        fail('node not UN / native transport not running in 300 s')
    jvm = open(f'/proc/{pid_of()}/cmdline').read().replace('\0', ' ')
    flags = [t for t in jvm.split() if t.startswith(('-Xm', '-XX:+Use', '-Xlog'))]
    note('jvm: ' + ' '.join(flags))
    if not expect('heap -Xms2G -Xmx2G (B3a)', '-Xms2G' in jvm.split() and '-Xmx2G' in jvm.split()):
        fail('heap is not 2G')


def tdir(ks):
    d = glob.glob(f'{DD}/data/data/{ks}/standard1-*')
    return d[0] if d else None


def du(ks):
    d = tdir(ks)
    if not d:
        return -1
    _, o = sh(f'du -sb {d}', check=False, quiet=True)
    return int(o.split()[0]) if o.strip() else -1


def gauge(ks):
    _, o = nt(f"sjk mx -mg -b 'org.apache.cassandra.metrics:type=Table,keyspace={ks},scope=standard1,name=PendingCompactions' -f Value", check=False, quiet=True)
    m = re.search(r'-?\d+', o.strip().splitlines()[-1]) if o.strip() else None
    return int(m.group()) if m else None


def tablestats(ks):
    _, o = nt(f'tablestats {ks}.standard1', check=False, quiet=True)
    g = lambda pat: (re.search(pat + r':\s*(\d+)', o) or [None, None])[1]
    return dict(sstables=int(g(r'SSTable count') or -1), live=int(g(r'Space used \(live\)') or -1), total=int(g(r'Space used \(total\)') or -1))


def rss_anon():
    for l in open(f'/proc/{pid_of()}/status'):
        if l.startswith('RssAnon'):
            return int(l.split()[1]) * 1024
    return -1


def live_heap():
    _, o = sh(f'jcmd {pid_of()} GC.class_histogram', check=False, quiet=True)
    m = re.search(r'^Total\s+\d+\s+(\d+)', o, re.M)
    return int(m.group(1)) if m else -1


def compacted_lines(ks):
    out = []
    try:
        for l in open(f'{MTN}/logs/system.log'):
            if 'Compacted (' in l and f'/{ks}/standard1-' in l:
                out.append(l.strip())
    except FileNotFoundError:
        pass
    return out


def data_sizes(ks):
    d = tdir(ks)
    return sorted(os.path.getsize(f) for f in glob.glob(d + '/*-Data.db')) if d else []


def stress(ks, i):
    lo, hi = i * ROWS + 1, (i + 1) * ROWS
    cmd = (f'tools/bin/cassandra-stress write n={ROWS} no-warmup -pop seq={lo}..{hi} -col size=FIXED\\(1024\\) n=FIXED\\(1\\) '
           f'-rate threads=8 -node {ADDR} -schema keyspace={ks} "replication(factor=1)" '
           f'"compaction(strategy=SizeTieredCompactionStrategy,min_threshold=32,max_threshold=32)" '
           f'> {D}/stress-{ks}-{i}.out 2>&1')
    rc, _ = sh(cmd, check=False, timeout=600)
    txt = open(f'{D}/stress-{ks}-{i}.out').read()
    errs = re.search(r'Total errors\s*:\s*(\d+)', txt)
    return rc, int(errs.group(1)) if errs else -1


def arm(name, kind, rep, mn, mx):
    ks = name
    note(f'--- arm {name} kind={kind} rep={rep} min={mn} max={mx}')
    for i in range(FLUSHES):
        rc, errs = stress(ks, i)
        if rc != 0 or errs != 0:
            fail(f'stress {ks} #{i} rc={rc} errors={errs}; see {D}/stress-{ks}-{i}.out')
        if i == 0:
            nt(f'disableautocompaction {ks} standard1')
        nt(f'flush {ks} standard1')
    ts = tablestats(ks)
    sizes = data_sizes(ks)
    ok = expect(f'{name}: {FLUSHES} sstables, sizes within 1.3x, all < 50 MB (one bucket); no compaction during ingest',
                ts['sstables'] == FLUSHES and len(sizes) == FLUSHES and sizes[-1] <= 1.3 * sizes[0] and sizes[-1] < 50e6 and not compacted_lines(ks))
    note(f'sizes {name}: {sizes}')
    if not ok:
        fail(f'{name}: ingest check failed')
    nt(f'setcompactionthreshold {ks} standard1 {mn} {mx}')
    _, o = nt(f'getcompactionthreshold {ks} standard1', quiet=True)
    thr = re.findall(r'(\d+)', o)
    expect(f'{name}: thresholds read back as {mn}/{mx}', thr[-2:] == [str(mn), str(mx)])
    _, o = nt('compactionstats', quiet=True)
    # BASELINE: min set, autocompaction still disabled
    b = dict(gauge=gauge(ks), du=du(ks), rss=rss_anon(), heap=live_heap(), **tablestats(ks))
    note(f'BASELINE {name} ' + json.dumps(b))
    t_en = time.time()
    nt(f'enableautocompaction {ks} standard1')
    series, seen_done = [], None
    t0 = time.time()
    while time.time() - t0 < OBS:
        g = gauge(ks)
        d = du(ks)
        cl = len(compacted_lines(ks))
        series.append((round(time.time() - t_en, 1), g, d, cl))
        if kind == 'control' and cl >= 1 and seen_done is None:
            seen_done = len(series)
        # estimate arms: stop when compaction work is over (min<=10: all merged; min 16: after 20 s of observation)
        if kind == 'est' and mn > FLUSHES and time.time() - t0 > 20:
            break
        if kind == 'est' and mn <= FLUSHES and cl >= 1 and (g == 0) and time.time() - t0 > 10:
            break
        if kind == 'control' and cl >= 1 and len(series) - seen_done >= 3:
            break
    with open(f'{D}/series-{name}.csv', 'w') as f:
        f.write('t_since_enable,gauge,du,compacted_lines\n')
        for r in series:
            f.write(','.join(str(x) for x in r) + '\n')
    cl = compacted_lines(ks)
    ts2 = tablestats(ks)
    gmax = max([r[1] for r in series if r[1] is not None] or [-1])
    dmax = max(r[2] for r in series)
    first = next((r[0] for r in series if r[1]), None)
    ndone = [int(m.group(1)) for l in cl for m in [re.search(r'Compacted \([^)]*\) (\d+) sstables', l)] if m]
    note('ARM ' + json.dumps(dict(name=name, kind=kind, rep=rep, min=mn, max=mx, base=b, gauge_max=gmax, gauge_first_pos_s=first,
                                  gauge_last=series[-1][1], du_max=dmax, compacted=len(cl), compacted_inputs=ndone,
                                  after=ts2, polls=len(series))))
    for l in cl[:3]:
        note('  log: ' + l[-260:])
    # settle before the next arm
    for _ in range(60):
        _, o = nt('compactionstats', check=False, quiet=True)
        if 'pending tasks: 0' in o:
            break
        time.sleep(2)


def main():
    start_node()
    arms = []
    for rep in range(1, REPS + 1):
        for mn in (2, 4, 16):
            arms.append((f'e{rep}m{mn}', 'est', rep, mn, 32))
    arms += [('c4', 'control', 1, 4, 4), ('c32', 'control', 1, 4, 32)]
    sel = os.environ.get('MT_ARMS')
    if sel:
        arms = [a for a in arms if a[0] in sel.split(',')]
    for a in arms:
        arm(*a)
    _, o = sh(f"grep -c '^ERROR' {MTN}/logs/system.log", check=False)
    note(f'node log ERROR lines: {o.strip()}')
    stop_node()
    expect('node stopped, no CassandraDaemon of mine left', pid_of() is None)
    sh(f'python3 -I {HARNESS}/analyze-cluster.py {D}/summary.txt | tee {D}/analysis.txt', check=False)


try:
    main()
except SystemExit:
    raise
except BaseException as e:
    note(f'FAIL: exception {e!r}')
    stop_node()
    raise
finally:
    stop_node()
