#!/usr/bin/env python3
"""Stage 4, cluster tier, CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT (case 9b-9e, amended 2026-10-14).
usage: cluster-run.py instrument | value <4000000|1000000|100000|1|0> | compare | down
  instrument  9e "Instrument check" at L = 1,000,000: TestScript, histo.sh, idle pair, the control write, 24 x 90,000 held, kill, replay.
  value <L>   Phase 1 (live writes: control, 8 x 90,000 + 8 x 500,000 + 8 x 2,000,000 held, release), kill -9, Phase 2 (replay held, release).
  compare     the cross-value readings of 9a ("Heap", dose-response, S_B) from each value's histo.csv.
One node (~/cassandra-run1), RF 1, a fresh data/ per value (kept between a value's two phases). Logs every command to
<logroot>/<run>/session.log (logroot ~/stage4-logs/cms, or $STAGE4_LOGROOT for shakedowns); writes summary.txt (EXPECTED lines),
histo.csv, writers-p1.txt, hold-p<n>.txt, trace-p<n>.txt (Byteman), histo-*.txt (raw jcmd output) and a copy of system.log.
Exit 1: an instrument, control or set-up check failed (invalid run). The node is stopped and conf/cassandra.yaml restored on any exit."""
import csv, json, os, re, subprocess, sys, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-run1')
HARNESS = os.path.dirname(os.path.abspath(__file__))
BM = C + '/build/lib/jars'
LOGROOT = os.environ.get('STAGE4_LOGROOT', HOME + '/stage4-logs/cms')
HOLD_MS = 45000                                     # 9b
SIZES = [(100, 8, 90000), (108, 8, 500000), (116, 8, 2000000)]   # 9c: first pk, n, payload
VALUES = [4000000, 1000000, 100000, 1, 0]           # 9e order
SYSLOG = C + '/logs/system.log'
SER_RE = re.compile(r'serialize T=(\d+) cached=(\w+) ks=(\w+) pk=(-?\d+) v=(\d+) thread=(.*) ms=(\d+)$')
DES_RE = re.compile(r'deserialize cached=(true|false) teeLen=(\d+) ks=(\w+) pk=(-?\d+) v=(\d+) thread=(.*) ms=(\d+)$')
HOLD_RE = re.compile(r'held ks=(\w+) pk=(-?\d+) delay=(\d+) thread=(.*) ms=(\d+)$')
HISTO_RE = re.compile(r'epoch_ms=(\d+) jcmd_ms=(\d+) B_inst=(\d+) B_bytes=(\d+) cached_inst=(\d+) cached_bytes=(\d+) '
                      r'sizeonly_inst=(\d+) sizeonly_bytes=(\d+) mutation_inst=(\d+)')

mode = sys.argv[1] if len(sys.argv) > 1 else 'down'
if mode == 'value':
    L = int(sys.argv[2])
    if L not in VALUES:
        sys.exit(f'unknown value {L}')
    RUN = str(L)
elif mode == 'instrument':
    L, RUN = 1000000, 'instrument'
elif mode in ('compare', 'down'):
    L, RUN = None, mode
else:
    sys.exit('usage: cluster-run.py instrument | value <L> | compare | down')
D = f'{LOGROOT}/{RUN}'
os.makedirs(D, exist_ok=True)
SESSION = open(D + '/session.log', 'a')
SUMMARY = open(D + '/summary.txt', 'w')
HFILE = None
HCSV = None


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, file=sys.stderr); SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush(); log(s)


def sh(cmd, timeout=600, check=True, env=None):
    log('+ ' + cmd)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env, cwd=C)
    out = (r.stdout or '') + (r.stderr or '')
    SESSION.write(out[-6000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed rc={r.returncode}: {cmd}\n{out[-800:]}')
    return r.returncode, out


def daemon_pids():
    r = subprocess.run("ps -eo pid,args | grep '[o]rg.apache.cassandra.service.CassandraDaemon' | awk '{print $1}'",
                       shell=True, capture_output=True, text=True)
    return [p for p in r.stdout.split() if p.isdigit()]


def copy_logs(tag):
    if os.path.exists(SYSLOG):
        sh(f'cp {SYSLOG} {D}/system.{tag}.log', check=False)


def stop_node(kill=False, tag='end'):
    if daemon_pids() and not kill:
        sh('bin/nodetool stopdaemon', check=False, timeout=120)
        for _ in range(90):
            if not daemon_pids():
                break
            time.sleep(1)
    for p in daemon_pids():
        log(f'kill -9 {p}'); subprocess.run(['kill', '-9', p])
    for _ in range(30):
        if not daemon_pids():
            break
        time.sleep(1)
    if daemon_pids():
        log('WARNING: a CassandraDaemon is still running')
    copy_logs(tag)


def finish(rc):
    stop_node()
    sh('git checkout -q conf/cassandra.yaml', check=False)
    note(f'node stopped; daemons left: {len(daemon_pids())}; yaml restored')
    if HFILE:
        HFILE.flush()
    sys.exit(rc)


def fail(msg):
    note('FAIL: ' + msg)
    finish(1)


def expect(desc, cond):
    note(f'EXPECTED: {desc} — {"yes" if cond else "NO (recorded; the AI judges it in the results file)"}')
    return cond


# ------------------------------------------------------------------ observables

def parse(path, rx):
    if not os.path.exists(path):
        return []
    out = []
    for l in open(path, errors='replace'):
        m = rx.match(l.strip())
        if m:
            out.append(m.groups())
    return out


def ser_lines(p, ks='ks1'):
    return [{'T': int(g[0]), 'cached': g[1], 'ks': g[2], 'pk': int(g[3]), 'v': int(g[4]), 'ms': int(g[6])}
            for g in parse(f'{D}/trace-p{p}.txt', SER_RE) if g[2] == ks]


def des_lines(p, ks='ks1'):
    return [{'cached': g[0] == 'true', 'teeLen': int(g[1]), 'ks': g[2], 'pk': int(g[3]), 'v': int(g[4]), 'ms': int(g[6])}
            for g in parse(f'{D}/trace-p{p}.txt', DES_RE) if g[2] == ks]


def held_lines(p):
    return [{'pk': int(g[1]), 'ms': int(g[4])} for g in parse(f'{D}/hold-p{p}.txt', HOLD_RE) if g[0] == 'ks1']


def wait_held(p, n, timeout, t0):
    while time.time() - t0 < timeout:
        h = held_lines(p)
        if len(h) >= n:
            return h
        time.sleep(0.5)
    return held_lines(p)


def histo(pid, phase, label):
    rc, out = sh(f'{HARNESS}/histo.sh {pid} {D}/histo-p{phase}-{label}.txt', check=False, timeout=180)
    m = HISTO_RE.search(out)
    if rc != 0 or not m:
        fail(f'histo.sh failed or unparsable ({label}): {out[-300:]}')
    v = dict(zip(['epoch_ms', 'jcmd_ms', 'B_inst', 'B_bytes', 'cached_inst', 'cached_bytes', 'sizeonly_inst', 'sizeonly_bytes',
                  'mutation_inst'], map(int, m.groups())))
    HCSV.writerow([RUN, L, phase, label] + [v[k] for k in ('epoch_ms', 'jcmd_ms', 'B_inst', 'B_bytes', 'cached_inst', 'cached_bytes',
                                                          'sizeonly_inst', 'sizeonly_bytes', 'mutation_inst')])
    HFILE.flush()
    note(f'histo p{phase} {label}: [B {v["B_inst"]} / {v["B_bytes"]} B; CachedSerialization {v["cached_inst"]} ({v["cached_bytes"]} B); '
         f'SizeOnly {v["sizeonly_inst"]}; Mutation {v["mutation_inst"]}; jcmd {v["jcmd_ms"]} ms')
    return v


def sleep_until(epoch_s):
    d = epoch_s - time.time()
    if d > 0:
        time.sleep(d)


def client(*args, timeout=400):
    log('+ send-mutation.py ' + ' '.join(args))
    r = subprocess.run([sys.executable, f'{HARNESS}/send-mutation.py', *args], capture_output=True, text=True, timeout=timeout)
    line = (r.stdout.strip().splitlines() or ['ERR ClientFailure {}'])[-1]
    SESSION.write(line[:3000] + '\n' + r.stderr[-600:] + '\n'); SESSION.flush()
    return parse_client(line)


def parse_client(line):
    ok = line.startswith('OK ')
    parts = line.split(' ', 2)
    try:
        body = json.loads(line[3:] if ok else parts[2])
    except Exception:
        body = {'raw': line[:1500]}
    body['ok'] = ok
    body['class'] = None if ok else parts[1]
    return body


def writers(specs, tag):
    """start one `many` client per spec at once; returns the Popen list"""
    procs = []
    for first, n, size in specs:
        args = ['many', str(first), str(n), str(size)]
        log('+ send-mutation.py ' + ' '.join(args) + ' &')
        procs.append((args, subprocess.Popen([sys.executable, f'{HARNESS}/send-mutation.py', *args],
                                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)))
    return procs


def join_writers(procs, tag):
    results, last = [], 0.0
    with open(f'{D}/writers-{tag}.txt', 'w') as f:
        for args, p in procs:
            o, e = p.communicate(timeout=400)
            line = (o.strip().splitlines() or ['ERR ClientFailure {}'])[-1]
            f.write(' '.join(args) + '\n' + line + '\n')
            SESSION.write(line[:3000] + '\n' + e[-600:] + '\n'); SESSION.flush()
            r = parse_client(line)
            results.append((args, r))
    last = time.time()
    return results, last


def writers_ok(results):
    oks = sum(1 for _, r in results for x in r.get('results', []) if x.get('ok'))
    total = sum(int(a[2]) for a, _ in results)
    secs = [x.get('secs') for _, r in results for x in r.get('results', [])]
    return oks, total, (min(secs) if secs else None), (max(secs) if secs else None)


# ------------------------------------------------------------------ node

def wait_up(pid_file, timeout):
    """'up' (UN and binary running), 'exited' (the process is gone) or 'timeout'"""
    t0 = time.time()
    pid = None
    while time.time() - t0 < timeout:
        if pid is None and os.path.exists(pid_file):
            pid = open(pid_file).read().strip() or None
        if pid and not os.path.exists(f'/proc/{pid}'):
            return 'exited', time.time() - t0
        _, st = sh('bin/nodetool statusbinary', check=False, timeout=60)
        if 'running' in st:
            _, ns = sh('bin/nodetool status', check=False, timeout=60)
            if re.search(r'^UN', ns, re.M):
                return 'up', time.time() - t0
        time.sleep(5)
    return 'timeout', time.time() - t0


def start(phase, limit, wipe):
    """starts the node with the knob, the hold and the agent; returns (pid, t_start). Does not wait for UN."""
    if daemon_pids():
        fail('a CassandraDaemon is already running before the start')
    note(sh(f'{HARNESS}/make-node-yaml.sh {RUN}-p{phase}')[1].strip().replace('\n', ' | '))
    sh(f'cp conf/cassandra.yaml {D}/cassandra.p{phase}.yaml')
    _, y = sh('grep -E "^(commitlog_sync|commitlog_sync_period|write_request_timeout|native_transport_timeout|concurrent_writes|'
              'memtable_allocation_type|commitlog_segment_size|storage_compatibility_mode)\\b" conf/cassandra.yaml', check=False)
    note('yaml in force: ' + ' ; '.join(y.strip().splitlines()))
    if wipe:
        if C != HOME + '/cassandra-run1':
            fail(f'unexpected clone path {C}')
        sh('rm -rf data logs saved_caches')
    env = dict(os.environ, MAX_HEAP_SIZE='4G')
    env.pop('HEAP_NEWSIZE', None)
    env['JVM_EXTRA_OPTS'] = (f'-Dcassandra.cacheable_mutation_size_limit_bytes={limit} -Dstage4.hold.ms={HOLD_MS} '
                             f'-Dstage4.hold.out={D}/hold-p{phase}.txt -Dstage4.byteman.out={D}/trace-p{phase}.txt '
                             f'-javaagent:{BM}/byteman-4.0.20.jar=script:{HARNESS}/cache-trace.btm,script:{HARNESS}/hold.btm,listener:true')
    note('JVM_EXTRA_OPTS=' + env['JVM_EXTRA_OPTS'])
    pid_file = f'{D}/cassandra.p{phase}.pid'
    if os.path.exists(pid_file):
        os.remove(pid_file)
    t0 = time.time()
    sh(f'bin/cassandra -p {pid_file} > {D}/startup.p{phase}.log 2>&1', env=env)
    for _ in range(60):
        if os.path.exists(pid_file) and open(pid_file).read().strip():
            break
        time.sleep(0.5)
    pid = open(pid_file).read().strip()
    for _ in range(20):
        if os.path.exists(f'/proc/{pid}/cmdline'):
            break
        time.sleep(0.5)
    args = open(f'/proc/{pid}/cmdline').read().split('\0')
    open(f'{D}/jvm-args.p{phase}.txt', 'w').write('\n'.join(args))
    if '-Xmx4G' not in args:
        fail('JVM lacks -Xmx4G')
    if not any('byteman-4.0.20.jar' in a for a in args):
        fail('JVM lacks the Byteman agent')
    if f'-Dcassandra.cacheable_mutation_size_limit_bytes={limit}' not in args:
        fail('JVM lacks the property')
    return pid, pid_file, t0


def sysprop(pid, limit):
    _, out = sh(f'jcmd {pid} VM.system_properties', check=False, timeout=60)
    m = re.search(r'cassandra\.cacheable_mutation_size_limit_bytes=(\S+)', out)
    got = m.group(1) if m else None
    ok = got == str(limit)
    note(f'VM.system_properties: cassandra.cacheable_mutation_size_limit_bytes={got} (set {limit})')
    if not ok:
        fail('the property read back differs from the value set: invalid run (9a)')


def schema():
    tdef = "(pk int PRIMARY KEY, v blob) WITH compression = {'enabled': false}"
    stmts = ["CREATE KEYSPACE ks1 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};",
             f'CREATE TABLE ks1.t {tdef};',
             "CREATE KEYSPACE ks0 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};",
             f'CREATE TABLE ks0.ctl {tdef};']
    sh('bin/cqlsh -e "' + ' '.join(stmts).replace('"', '\\"') + '"')
    p = client('probe')
    if not p['ok'] or p.get('protocol') != 4:
        fail('probe failed or not protocol 4: ' + str(p))
    note(f'probe: release {p.get("release_version")} protocol {p.get("protocol")}')


def head():
    note(f'run {RUN} on {os.uname().nodename}; {time.strftime("%F %T %Z")}; epoch ms {int(time.time() * 1000)}')
    note('clone: ' + sh('git rev-parse HEAD')[1].strip() + ' ' + sh('git describe --tags')[1].strip())
    note('harness md5: ' + sh(f'cd {HARNESS} && md5sum *.java *.btm *.py *.sh | tr "\\n" ";"')[1].strip())
    for f in os.listdir(D):
        if re.match(r'(hold|trace)-p\d\.txt$|histo-p.*\.txt$', f):
            os.remove(f'{D}/{f}')


def control_write(pid):
    """9b Controls, amended: one unheld 1,024 B write to ks0.ctl"""
    n0 = len(held_lines(1))
    r = client('insert', '--ks', 'ks0', '0', '1024', timeout=60)
    time.sleep(1)
    ctl = ser_lines(1, 'ks0')
    nh = len(held_lines(1)) - n0
    want = 'CachedSerialization' if 1024 < (L if L is not None else 0) else 'SizeOnlyCacheableSerialization'
    note(f'control write ks0.ctl pk 0, 1,024 B: {"OK" if r["ok"] else "ERR " + str(r["class"])} in {r.get("secs")} s; new held lines {nh}; '
         f'serialize lines for ks0: {[(x["T"], x["cached"]) for x in ctl]}')
    if not r['ok'] or (r.get('secs') or 99) > 10 or nh != 0 or len(ctl) != 1:
        fail('control write: not OK within 10 s, held, or no serialize line: invalid run (9e Phase 1 step 1)')
    expect(f'control write: serialize T={ctl[0]["T"]} (just above 1,024) cached={ctl[0]["cached"]} (predicted {want})',
           ctl[0]['cached'] == want and 1024 < ctl[0]['T'] < 1200)
    return ctl[0]


def c_of(limit, Ts):
    return sum(1 for t in Ts if t < limit)


def within(delta, pred, d_lo, d_hi):
    """delta measured against both idle histograms: pred must lie between the two differences (the idle spread)"""
    lo, hi = min(d_lo, d_hi), max(d_lo, d_hi)
    return lo <= pred <= hi


def counts_vs_idle(v, idle, key):
    return v[key] - idle[0][key], v[key] - idle[1][key]


# ------------------------------------------------------------------ modes

def instrument():
    global HFILE, HCSV
    HFILE = open(D + '/histo.csv', 'w'); HCSV = csv.writer(HFILE)
    HCSV.writerow(['run', 'L', 'phase', 'label', 'epoch_ms', 'jcmd_ms', 'B_inst', 'B_bytes', 'cached_inst', 'cached_bytes',
                   'sizeonly_inst', 'sizeonly_bytes', 'mutation_inst'])
    # (i) TestScript
    sh(f'java -classpath {BM}/byteman-4.0.20.jar:build/classes/main:"build/lib/jars/*" org.jboss.byteman.check.TestScript '
       f'{HARNESS}/cache-trace.btm {HARNESS}/hold.btm > {D}/testscript.txt 2>&1', check=False)
    ts = open(D + '/testscript.txt').read()
    note('Byteman TestScript: ' + ' | '.join(l for l in ts.splitlines() if re.search(r'^Type checked|ERROR|TestScript:|WARN', l)))
    if 'TestScript: no errors' not in ts:
        fail('(i) Byteman TestScript reports errors (testscript.txt)')
    pid, pid_file, t0 = start(1, L, wipe=True)
    st, secs = wait_up(pid_file, 240)
    note(f'start p1: {st} after {secs:.0f} s')
    if st != 'up':
        fail(f'node did not come up ({st})')
    sysprop(pid, L)
    schema()
    _, sl = sh(f'java -cp {BM}/byteman-submit-4.0.20.jar org.jboss.byteman.agent.submit.Submit -l', check=False)
    open(D + '/submit-l.txt', 'w').write(sl)
    note('Submit -l: ' + ' | '.join(l.strip() for l in sl.splitlines() if 'RULE' in l or 'trigger method' in l)[:900])
    # (ii), (iii)
    i1 = histo(pid, 1, 'idle-1'); time.sleep(10); i2 = histo(pid, 1, 'idle-2')
    note(f'(iii) idle pair: CachedSerialization {i1["cached_inst"]} -> {i2["cached_inst"]}, SizeOnly {i1["sizeonly_inst"]} -> {i2["sizeonly_inst"]}, '
         f'[B bytes {i1["B_bytes"]} -> {i2["B_bytes"]}')
    # (iv)
    control_write(pid)
    # (v) 24 x 90,000
    procs = writers([(100, 24, 90000)], 'p1')
    h = wait_held(1, 24, 60, time.time())
    if len(h) < 24:
        join_writers(procs, 'p1')
        fail(f'(v) {len(h)} held lines in 60 s, 24 expected')
    t24 = max(x['ms'] for x in h) / 1000
    sleep_until(t24 + 5)
    hv = histo(pid, 1, 'held-1')
    d = counts_vs_idle(hv, (i1, i2), 'cached_inst')
    ok_v = within(None, 24, *d)
    note(f'(v) CachedSerialization held - idle = {d} (24 predicted)')
    results, _ = join_writers(procs, 'p1')
    oks, total, smin, smax = writers_ok(results)
    note(f'(v) writers: {oks}/{total} OK, completed after {smin} .. {smax} s')
    sers = ser_lines(1)
    note(f'(v) serialize lines ks1: {len(sers)}; cached: {sorted(set(x["cached"] for x in sers))}; T: {sorted(set(x["T"] for x in sers))}')
    if not (ok_v and oks == 24 and len(sers) == 24):
        fail('(v) the held histogram, the writers or the trace do not show 24 held, cached, acknowledged writes')
    time.sleep(10)
    histo(pid, 1, 'release')
    # (vi)
    stop_node(kill=True, tag='p1')
    if daemon_pids():
        fail('(vi) a daemon is left after kill -9')
    pid, pid_file, t0 = start(2, L, wipe=False)
    h = wait_held(2, 24, 120, t0)
    des = des_lines(2)
    note(f'(vi) replay: {len(h)} held lines, {len(des)} deserialize lines (ks1) within {time.time() - t0:.0f} s; '
         f'cached: {sorted(set(x["cached"] for x in des))}; teeLen: {sorted(set(x["teeLen"] for x in des))}')
    if len(h) < 24 or len(des) < 24:
        fail('(vi) fewer than 24 held or deserialize lines in 120 s')
    t24 = max(x['ms'] for x in h) / 1000
    sleep_until(t24 + 5)
    histo(pid, 2, 'held-1')
    st, secs = wait_up(pid_file, 300)
    note(f'(vi) start p2: {st} after {time.time() - t0:.0f} s')
    histo(pid, 2, 'release')
    note('INSTRUMENT CHECK PASSED')
    finish(0)


def value():
    global HFILE, HCSV
    HFILE = open(D + '/histo.csv', 'w'); HCSV = csv.writer(HFILE)
    HCSV.writerow(['run', 'L', 'phase', 'label', 'epoch_ms', 'jcmd_ms', 'B_inst', 'B_bytes', 'cached_inst', 'cached_bytes',
                   'sizeonly_inst', 'sizeonly_bytes', 'mutation_inst'])
    # ---------------- Phase 1 (9e steps 1-4)
    pid, pid_file, t0 = start(1, L, wipe=True)
    st, secs = wait_up(pid_file, 240)
    note(f'start p1: {st} after {secs:.0f} s')
    if st != 'up':
        fail(f'node did not come up ({st})')
    sysprop(pid, L)
    schema()
    i1 = histo(pid, 1, 'idle-1'); time.sleep(10); i2 = histo(pid, 1, 'idle-2')
    idle = (i1, i2)
    note(f'idle pair: CachedSerialization {i1["cached_inst"]} / {i2["cached_inst"]}; SizeOnly {i1["sizeonly_inst"]} / {i2["sizeonly_inst"]}; '
         f'[B bytes {i1["B_bytes"]} / {i2["B_bytes"]} (spread {abs(i1["B_bytes"] - i2["B_bytes"])})')
    expect(f'idle control: the two idle histograms have equal live counts (Cached {i1["cached_inst"]}/{i2["cached_inst"]}, '
           f'SizeOnly {i1["sizeonly_inst"]}/{i2["sizeonly_inst"]})',
           i1['cached_inst'] == i2['cached_inst'] and i1['sizeonly_inst'] == i2['sizeonly_inst'])
    control_write(pid)
    tw = time.time()
    procs = writers(SIZES, 'p1')
    h = wait_held(1, 24, 60, tw)
    note(f'held lines p1: {len(h)} within {time.time() - tw:.1f} s')
    if len(h) < 24:
        join_writers(procs, 'p1')
        fail(f'{len(h)} held lines in 60 s, 24 expected: invalid run (9a)')
    t24 = max(x['ms'] for x in h) / 1000
    sleep_until(t24 + 5); h1 = histo(pid, 1, 'held-1')
    sleep_until(t24 + 15); h2 = histo(pid, 1, 'held-2')
    results, tlast = join_writers(procs, 'p1')
    oks, total, smin, smax = writers_ok(results)
    sleep_until(tlast + 10); rel = histo(pid, 1, 'release')
    # Phase 1 readings
    sers = ser_lines(1)
    by_pk = {x['pk']: x for x in sers}
    Ts = []
    for first, n, size in SIZES:
        group = [by_pk[p] for p in range(first, first + n) if p in by_pk]
        tset = sorted(set(x['T'] for x in group))
        cset = sorted(set(x['cached'] for x in group))
        Ts.append(tset[0] if len(tset) == 1 else None)
        note(f'p1 size {size}: {len(group)} serialize lines, T {tset}, cached {cset}')
    if None in Ts or len(sers) != 24:
        expect(f'24 serialize lines, one T per size ({len(sers)} lines, T {Ts})', False)
        Ts = [t if t is not None else s + 40 for t, (_, _, s) in zip(Ts, SIZES)]
    c = c_of(L, Ts)
    note(f'T1, T2, T3 = {Ts}; c(L={L}) = {c}')
    wrong = [x for x in sers if (x['cached'] == 'CachedSerialization') != (x['T'] < L)]
    expect(f'p1 trace: every serialize line has cached=CachedSerialization iff T < L ({len(sers)} lines, {len(wrong)} wrong)',
           len(sers) == 24 and not wrong)
    expect(f'p1 versions: every serialize line v= {sorted(set(x["v"] for x in sers))} (one version)', len(set(x['v'] for x in sers)) == 1)
    for lab, hv in (('held-1', h1), ('held-2', h2)):
        dc = counts_vs_idle(hv, idle, 'cached_inst')
        ds = counts_vs_idle(hv, idle, 'sizeonly_inst')
        expect(f'p1 {lab}: CachedSerialization held - idle = {dc}, predicted +{8 * c}', within(None, 8 * c, *dc))
        expect(f'p1 {lab}: SizeOnlyCacheableSerialization held - idle = {ds}, predicted +{8 * (3 - c)}', within(None, 8 * (3 - c), *ds))
    cached_T = [t for t in Ts if t < L]
    if cached_T:
        expect(f'largest copy: longest cached serialize T = {max(cached_T)} < L = {L}', max(cached_T) < L)
    expect(f'p1 writers: {oks}/{total} OK (all), completed {smin} .. {smax} s after the start (hold {HOLD_MS / 1000:.0f} s)',
           oks == 24 and total == 24)
    dcr = counts_vs_idle(rel, idle, 'cached_inst'); dsr = counts_vs_idle(rel, idle, 'sizeonly_inst')
    expect(f'p1 release: Cached - idle = {dcr}, SizeOnly - idle = {dsr} (0 within the idle spread)',
           within(None, 0, *dcr) and within(None, 0, *dsr))
    # ---------------- kill (9e step 4)
    stop_node(kill=True, tag='p1')
    if daemon_pids():
        fail('a daemon is left after kill -9')
    note('killed -9; data/ and commitlog/ kept')
    # ---------------- Phase 2 (9e steps 5-6)
    pid, pid_file, t0 = start(2, L, wipe=False)
    h = wait_held(2, 24, 120, t0)
    note(f'held lines p2: {len(h)} within {time.time() - t0:.1f} s of the start command')
    if len(h) < 24:
        fail(f'{len(h)} held lines in 120 s (Phase 2), 24 expected: invalid run (9a)')
    t24 = max(x['ms'] for x in h) / 1000
    sleep_until(t24 + 5); g1 = histo(pid, 2, 'held-1')
    sleep_until(t24 + 15); g2 = histo(pid, 2, 'held-2')
    st, secs = wait_up(pid_file, 400)
    note(f'start p2: {st} after {time.time() - t0:.0f} s')
    if st != 'up':
        fail(f'node did not come up after the replay ({st})')
    time.sleep(5)
    after = histo(pid, 2, 'release')
    _, rp = sh(f'grep -n -i replay {SYSLOG}', check=False)
    rplines = [l for l in rp.splitlines() if l.strip()]
    open(f'{D}/replay-lines.txt', 'w').write(rp)
    note('replay lines in system.log: ' + ' | '.join(l[:200] for l in rplines[:6]))
    expect('a replayed segment in system.log (a "Replaying" / "replayed" line)', any(re.search(r'[Rr]eplay', l) for l in rplines))
    des = des_lines(2)
    dby = {x['pk']: x for x in des}
    cprime = c if L >= 1 else 3
    for (first, n, size), t in zip(SIZES, Ts):
        group = [dby[p] for p in range(first, first + n) if p in dby]
        note(f'p2 size {size}: {len(group)} deserialize lines, cached {sorted(set(x["cached"] for x in group))}, teeLen {sorted(set(x["teeLen"] for x in group))} (T = {t})')
    wrong = []
    for (first, n, size), t in zip(SIZES, Ts):
        want = (L <= 0) or t < L
        for p in range(first, first + n):
            x = dby.get(p)
            if x is None or x['cached'] != want or (want and x['teeLen'] != t) or (not want and x['teeLen'] >= L):
                wrong.append(p)
    expect(f'p2 trace: 24 deserialize lines (ks1: {len(des)}), cached=true with teeLen = T on {8 * cprime}, cached=false (teeLen < L) on the rest; wrong pks {wrong}',
           len(des) == 24 and not wrong)
    ctl = des_lines(2, 'ks0')
    note(f'p2 control (ks0, recorded, not counted): {[(x["cached"], x["teeLen"]) for x in ctl]}')
    # Phase 2 counts: held less the after-replay histogram (9a Phase 2), release against Phase 1's idle pair (amended)
    for lab, gv in (('held-1', g1), ('held-2', g2)):
        dc = gv['cached_inst'] - after['cached_inst']
        ds = gv['sizeonly_inst'] - after['sizeonly_inst']
        tol = abs(i1['cached_inst'] - i2['cached_inst'])
        expect(f'p2 {lab}: CachedSerialization held - after = {dc}, predicted +{8 * cprime} (tolerance: the p1 idle spread, {tol})',
               abs(dc - 8 * cprime) <= tol)
        note(f'p2 {lab}: SizeOnlyCacheableSerialization held - after = {ds} (recorded; predicted unchanged: 0)')
    dcr = counts_vs_idle(after, idle, 'cached_inst'); dsr = counts_vs_idle(after, idle, 'sizeonly_inst')
    expect(f'p2 release: after-replay Cached - p1 idle = {dcr}, SizeOnly - p1 idle = {dsr} (0 within the p1 idle spread)',
           within(None, 0, *dcr) and within(None, 0, *dsr))
    if L == 0:
        big = [x for x in des if x['teeLen'] > 1000000 and x['cached']]
        expect(f'scenario C (L = 0): {len(big)} replayed copies above 1,000,000 B (8 predicted), bypass volume 8 x (T3 + 16) = {8 * (Ts[2] + 16)} B',
               len(big) == 8)
    json.dump({'L': L, 'T': Ts, 'c': c, 'c_prime': cprime}, open(f'{D}/sizes.json', 'w'))
    # ---------------- stop (9e step 7)
    finish(0)


def compare():
    rows = {}
    for v in VALUES:
        f = f'{LOGROOT}/{v}/histo.csv'
        if not os.path.exists(f):
            note(f'compare: {f} missing'); continue
        for r in csv.DictReader(open(f)):
            rows[(v, int(r['phase']), r['label'])] = {k: int(r[k]) for k in ('B_bytes', 'cached_inst', 'sizeonly_inst')}
    sizes = {}
    for v in VALUES:
        f = f'{LOGROOT}/{v}/sizes.json'
        if os.path.exists(f):
            sizes[v] = json.load(open(f))
    Ts = next((s['T'] for s in sizes.values()), None)
    note(f'compare: values with histograms {sorted({k[0] for k in rows})}; T = {Ts}')
    for lab in ('held-1', 'held-2'):
        b0, b1 = rows.get((0, 1, lab)), rows.get((1, 1, lab))
        if not (b0 and b1 and Ts):
            note(f'compare {lab}: missing the L = 0 / L = 1 Phase 1 runs'); continue
        SB = abs(b0['B_bytes'] - b1['B_bytes'])
        note(f'compare {lab}: S_B = |[B(L=0) - [B(L=1)| Phase 1 = {SB} B (3 S_B = {3 * SB})')
        exc = {}
        for v in (100000, 1000000, 4000000):
            pred = 8 * sum(((t + 16 + 7) // 8) * 8 for t in Ts if t < v)
            for ph in (1, 2):
                a, ref = rows.get((v, ph, lab)), rows.get((1, ph, lab))
                if not (a and ref):
                    continue
                e = a['B_bytes'] - ref['B_bytes']
                exc[(v, ph)] = e
                tol = max(0.10 * pred, 3 * SB)
                readable = pred > 3 * SB
                if readable:
                    expect(f'compare {lab} p{ph} L={v}: [B excess over L=1 = {e} B, predicted {pred} B, tolerance {tol:.0f} B', abs(e - pred) <= tol)
                else:
                    note(f'compare {lab} p{ph} L={v}: [B excess over L=1 = {e} B, predicted {pred} B < 3 S_B = {3 * SB}: recorded, not read')
        for ph in (1, 2):
            if (4000000, ph) in exc and (1000000, ph) in exc and exc[(1000000, ph)] > 0:
                note(f'compare {lab} p{ph}: dose-response excess(4,000,000) / excess(1,000,000) = {exc[(4000000, ph)] / exc[(1000000, ph)]:.2f} (about 4.4 predicted)')
        z2, r2 = rows.get((0, 2, lab)), rows.get((1, 2, lab))
        if z2 and r2:
            note(f'compare {lab} p2: [B(L=0) - [B(L=1) = {z2["B_bytes"] - r2["B_bytes"]} B (scenario C bypass volume, predicted '
                 f'{8 * sum(((t + 16 + 7) // 8) * 8 for t in Ts)} B for all three sizes)')
    # flat-across-values check (Refuted row): counts and trace identical at every value?
    held = [(v, rows[(v, 1, 'held-1')]['cached_inst']) for v in VALUES if (v, 1, 'held-1') in rows]
    note(f'compare: p1 held-1 CachedSerialization by value {held}')


try:
    if mode == 'down':
        stop_node()
        sh('git checkout -q conf/cassandra.yaml', check=False)
        note(f'down: daemons left {len(daemon_pids())}')
        sys.exit(0)
    if mode == 'compare':
        compare()
        sys.exit(0)
    head()
    if mode == 'instrument':
        instrument()
    else:
        value()
except SystemExit:
    raise
except BaseException as e:
    note(f'FAIL: exception {type(e).__name__}: {str(e)[:600]}')
    finish(1)
