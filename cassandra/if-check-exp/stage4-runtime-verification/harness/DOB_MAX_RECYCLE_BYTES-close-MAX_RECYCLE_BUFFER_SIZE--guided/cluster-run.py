#!/usr/bin/env python3
"""Stage 4, cluster tier, DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE (case 9b-9e, amended 2026-10-15).
usage: cluster-run.py <label> [<label> ...]
  <label> = L<262144|default|4194304|2147483647|64>-<B1|B2|B3|BA|BB|BN>[-heap]   one fresh node start, one batch
  report                                                                       the cross-label relations (staircase, xN, arm H)
One node from ~/cassandra-run1, wiped before every start. Every command is logged to $DOB_LOGS/<label>/session.log (default
~/stage4-logs/dob/run1); summary.txt holds the EXPECTED lines, result.json the readings. Exit 1: an instrument or validity
check failed (the node is stopped on any exit)."""
import json, os, re, subprocess, sys, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-run1')
H = os.path.dirname(os.path.abspath(__file__))
LOGROOT = os.environ.get('DOB_LOGS', HOME + '/stage4-logs/dob/run1')
BM = C + '/build/lib/jars/byteman-4.0.20.jar'
POOL = 'java.nio:type=BufferPool,name=direct'
TAU = 262144
SIZES = {'B1': 100000, 'B2': 450000, 'B3': 1900000, 'BN': 450000}
sys.path.insert(0, H)
import ledger  # noqa: E402

SESSION = SUMMARY = None
n_exp = n_yes = 0
pid = None


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


def sh(cmd, timeout=600, check=True, env=None, cwd=C, quiet=False):
    log('+ ' + cmd)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
    out = (r.stdout or '') + (r.stderr or '')
    if not quiet and SESSION:
        SESSION.write(out[-5000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed rc={r.returncode}: {cmd}\n{out[-800:]}')
    return r.returncode, out


def expect(desc, cond):
    global n_exp, n_yes
    n_exp += 1; n_yes += bool(cond)
    note(f'EXPECTED: {desc} — {"yes" if cond else "NO (recorded; the AI judges it in the results file)"}')
    return bool(cond)


def daemon_up():
    return subprocess.run("ps -eo cmd | grep -q '[C]assandraDaemon'", shell=True).returncode == 0


def stop_node(D=None):
    if daemon_up():
        sh('bin/nodetool stopdaemon', check=False, timeout=120)
        for _ in range(90):
            if not daemon_up():
                break
            time.sleep(1)
        if daemon_up():
            subprocess.run("pkill -9 -f '[o]rg.apache.cassandra.service.CassandraDaemon'", shell=True); time.sleep(2)
    if D:
        sh(f'cp logs/system.log {D}/system.log', check=False)
    sh('git checkout -q conf/cassandra.yaml', check=False)


def fail(msg, D=None):
    note('FAIL: ' + msg)
    stop_node(D)
    sys.exit(1)


def client(*args, timeout=300):
    r = subprocess.run([sys.executable, f'{H}/dob-writes.py', *args], capture_output=True, text=True, timeout=timeout, cwd=C,
                       env=dict(os.environ, CASSANDRA_HOME=C))
    log('+ dob-writes.py ' + ' '.join(args) + ' -> ' + (r.stdout.strip() + ' ' + r.stderr.strip()[-300:]))
    return r.stdout.strip()


def size_of(p):
    try:
        return os.path.getsize(p)
    except OSError:
        return 0


def reading(D, name, ledger_path, heap=False):
    sh(f'jcmd {pid} GC.run', check=False, timeout=120)
    time.sleep(2)
    _, out = sh(f'java -cp {D}/jmx Jmx get {POOL} MemoryUsed {POOL} Count', check=False, timeout=60)
    mu = re.search(r'MemoryUsed\|(\d+)', out); ct = re.search(r'Count\|(\d+)', out)
    _, nmt = sh(f'jcmd {pid} VM.native_memory summary', check=False, timeout=60, quiet=True)
    open(f'{D}/nmt-{name}.txt', 'w').write(nmt)
    off = size_of(ledger_path)
    R = ledger.total(ledger.replay(ledger.parse(ledger_path, 0, off)))
    rd = dict(name=name, MemoryUsed=int(mu.group(1)) if mu else None, Count=int(ct.group(1)) if ct else None, ledger_off=off, R=R,
              ms=int(time.time() * 1000))
    if heap:
        _, hist = sh(f'jcmd {pid} GC.class_histogram', check=False, timeout=180, quiet=True)
        m = re.search(r'^\s*\d+:\s+(\d+)\s+(\d+)\s+\[B(\s|$)', hist, re.M)
        rd['live_B_bytes'] = int(m.group(2)) if m else None
    note(f'READING {name}: MemoryUsed={rd["MemoryUsed"]} Count={rd["Count"]} ledger R={R} off={off}' + (f' [B={rd.get("live_B_bytes")}' if heap else ''))
    return rd


def run_label(label):
    global SESSION, SUMMARY, pid, n_exp, n_yes
    m = re.match(r'^L(262144|default|4194304|2147483647|64)-(B1|B2|B3|BA|BB|BN)(-heap)?$', label)
    if not m:
        raise SystemExit(f'bad label {label}')
    Lspec, batch, heapmode = m.group(1), m.group(2), bool(m.group(3))
    L = 1048576 if Lspec == 'default' else int(Lspec)
    N = 4 if batch == 'BN' else 16
    D = f'{LOGROOT}/{label}'
    os.makedirs(D, exist_ok=True)
    SESSION = open(D + '/session.log', 'a'); SUMMARY = open(D + '/summary.txt', 'w'); n_exp = n_yes = 0
    note(f'LABEL {label}: L={L} ({Lspec}) batch={batch} N={N} heap={heapmode} start {time.strftime("%F %T %Z")}; harness md5 ' +
         subprocess.run(f'cd {H} && md5sum cluster-run.py dob-ledger.btm hold.btm ledger.py dob-writes.py | cut -c1-12 | tr "\\n" " "',
                        shell=True, capture_output=True, text=True).stdout)
    if daemon_up():
        fail('a CassandraDaemon is already running')
    sh('git checkout -q conf/cassandra.yaml', check=False)
    note(sh(f'{H}/make-node-yaml.sh')[1].strip())
    sh('rm -rf data logs saved_caches')
    sh(f'rm -rf {D}/jmx && mkdir -p {D}/jmx && javac -d {D}/jmx {H}/Jmx.java')
    LG, HD = f'{D}/ledger.txt', f'{D}/hold.txt'
    for f in (LG, HD):
        if os.path.exists(f):
            os.remove(f)
    props = ('' if Lspec == 'default' else f'-Dcassandra.dob_max_recycle_bytes={L} ') + '-Dcassandra.cacheable_mutation_size_limit_bytes=1 ' + \
            ('-Dcassandra.dob.allocate_type=onheap ' if heapmode else '')
    env = dict(os.environ, MAX_HEAP_SIZE='4G', HEAP_NEWSIZE='800M',
               JVM_EXTRA_OPTS=props + f'-XX:NativeMemoryTracking=summary -javaagent:{BM}=script:{H}/dob-ledger.btm,script:{H}/hold.btm '
                                      f'-Dstage4.ledger.out={LG} -Dstage4.hold.out={HD} -Dstage4.hold.ms=5000')
    sh(f'bin/cassandra -p {D}/cassandra.pid > {D}/startup.log 2>&1', env=env)
    for _ in range(120):
        _, st = sh('bin/nodetool statusbinary', check=False, quiet=True)
        _, ns = sh('bin/nodetool status', check=False, quiet=True)
        if re.search(r'^running\s*$', st, re.M) and re.search(r'^UN', ns, re.M):
            break
        time.sleep(2)
    else:
        fail('node did not come up', D)
    pid = int(open(f'{D}/cassandra.pid').read().strip())
    _, sp = sh(f"jcmd {pid} VM.system_properties | grep -E 'dob_max_recycle_bytes|dob.allocate_type|cacheable_mutation'", check=False)
    note('READBACK system properties: ' + sp.strip().replace('\n', ' ; '))
    want_l = f'cassandra.dob_max_recycle_bytes={L}' if Lspec != 'default' else None
    if (want_l and want_l not in sp) or (Lspec == 'default' and 'dob_max_recycle_bytes' in sp) or 'cacheable_mutation_size_limit_bytes=1' not in sp \
            or (heapmode != ('allocate_type=onheap' in sp)):
        fail('system-property read-back does not match the label (invalid run)', D)
    sh('bin/cqlsh -e "CREATE KEYSPACE ks1 WITH replication = {\'class\': \'SimpleStrategy\', \'replication_factor\': 1}; '
       'CREATE KEYSPACE ks0 WITH replication = {\'class\': \'SimpleStrategy\', \'replication_factor\': 1} AND durable_writes = false; '
       'CREATE TABLE ks1.t (k int PRIMARY KEY, v blob); CREATE TABLE ks0.t (k int PRIMARY KEY, v blob);"')
    pr = client('--probe')
    if 'probe=ok protocol=4' not in pr:
        fail(f'probe failed: {pr}', D)
    # ---- calibration
    off_c = size_of(LG); hoff = size_of(HD)
    cal = client('--ks', 'ks1', '--n', '1', '--value', '20000', '--first', '-1')
    time.sleep(0.5)
    held = [l for l in open(HD).read()[hoff:].splitlines() if l.startswith('held')]
    ev = ledger.parse(LG, off_c, size_of(LG))
    tid = int(re.search(r'tid=(\d+)', held[0]).group(1)) if held else None
    closes = [e for e in ev if e['kind'] == 'close' and e.get('tid') == tid and e.get('limit', 0) >= 20000]
    if not held or not closes or 'acked=1' not in cal:
        fail(f'calibration write: held={held} closes={closes} client={cal}', D)
    S0 = closes[-1]['limit']; P = S0 - 20001
    Lline = closes[-1]['L']
    note(f'CALIBRATION S0={S0} P={P} (ledger close line on tid {tid}, cap {closes[-1]["cap"]}); ledger L={Lline}')
    if not (20 <= P <= 127):
        fail(f'P={P} outside [20, 127] (invalid run)', D)
    if Lline != L:
        fail(f'ledger L={Lline} differs from the label L={L} (invalid run)', D)
    V = SIZES.get(batch) if batch in SIZES else (L // 2 - P + (1 if batch == 'BB' else 0))
    Cp = 2 * (V + P)
    keep = Cp <= L
    note(f'PLAN V={V} C=2(V+P)={Cp} -> {"kept" if keep else "replaced"} at L={L}; N={N}')
    # ---- twin warm-up (ks0, no commit log)
    off_t = size_of(LG)
    tw = client('--ks', 'ks0', '--n', str(N), '--value', str(V), '--first', '0')
    time.sleep(1)
    tev = ledger.parse(LG, off_t, size_of(LG))
    grow_tw = [e for e in tev if e['kind'] in ('alloc', 'grow-free', 'replaced') and e.get('size', e.get('cap', 0)) > 128]
    note(f'TWIN ks0 n={N} V={V}: {tw}; scratch events during the twin: {len(tev)} (growth or free above 128 B: {len(grow_tw)})')
    expect('twin warm-up (ks0) grew or freed no scratch buffer above 128 B', tw.startswith(f'acked={N} ') and not grow_tw)
    # ---- idle, before
    time.sleep(20)
    before = reading(D, 'before', LG, heap=heapmode or (Lspec == 'default' and batch in ('B2', 'B3')))
    # ---- batch
    hoff = size_of(HD)
    proc = subprocess.Popen([sys.executable, f'{H}/dob-writes.py', '--ks', 'ks1', '--n', str(N), '--value', str(V), '--first', '0'],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=C, env=dict(os.environ, CASSANDRA_HOME=C))
    t0 = time.time()
    while time.time() - t0 < 120:
        hl = [l for l in open(HD).read()[hoff:].splitlines() if l.startswith('held')]
        if len(hl) >= N:
            break
        time.sleep(0.2)
    time.sleep(3)
    hold = reading(D, 'hold', LG)
    out, err = proc.communicate(timeout=300)
    log(f'batch client: {out.strip()} {err.strip()[-300:]}')
    held = [l for l in open(HD).read()[hoff:].splitlines() if l.startswith('held')]
    tids = sorted({int(re.search(r'tid=(\d+)', l).group(1)) for l in held})
    note(f'BATCH ks1 n={N} V={V}: {out.strip()}; held lines {len(held)}, distinct tids {len(tids)}: {tids}')
    if len(tids) != N or not out.startswith(f'acked={N} '):
        fail(f'expected {N} acks on {N} distinct threads (invalid run)', D)
    time.sleep(10)
    after = reading(D, 'after', LG, heap=heapmode or (Lspec == 'default' and batch in ('B2', 'B3')))
    persist = None
    if Lspec == 'default' and batch == 'B2' and not heapmode:
        time.sleep(70)
        persist = reading(D, 'persist', LG)
    # ---- the ledger for the batch window
    st0 = ledger.replay(ledger.parse(LG, 0, before['ledger_off']))
    init = {d: (b.live, b.tid) for d, b in st0.items()}
    win = ledger.parse(LG, before['ledger_off'], after['ledger_off'])
    st1 = ledger.replay(ledger.parse(LG, 0, after['ledger_off']))
    per = {}
    for t in tids:
        evs = [e for e in win if e.get('tid') == t]
        cl = [e for e in evs if e['kind'] == 'close']
        dobs = sorted({e['dob'] for e in evs})
        d = dobs[0] if len(dobs) == 1 else None
        live0 = init.get(d, (0, None))[0]
        b0 = ledger.Buf(d); b0.live = live0; b0.peak = live0
        stw = ledger.replay([e for e in win if e['dob'] == d], {d: b0}) if d is not None else {}
        branch = [e['kind'] for e in evs if e['kind'] in ('kept', 'replaced')]
        allocs = [e['size'] for e in evs if e['kind'] == 'alloc']
        per[t] = dict(dob=d, dobs=dobs, closes=[(e['cap'], e['limit']) for e in cl], branch=branch, allocs=allocs, initial=live0,
                      final=st1[d].live if d in st1 else None, peak=stw[d].peak if d in stw else None, new=any(e['kind'] == 'new' for e in evs))
    for t in tids:
        p = per[t]
        log(f'  tid {t}: {json.dumps(p)}')
    S = V + P + 1
    one_dob = all(len(per[t]['dobs']) == 1 for t in tids)
    expect(f'each of the {N} threads used one scratch instance in the window', one_dob)
    expect(f'every ks1 close line shows cap = C = {Cp} and limit = S = {S}', all((Cp, S) in per[t]['closes'] for t in tids))
    expect(f'every branch line is {"kept" if keep else "replaced"} (C {"<=" if keep else ">"} L)',
           all(per[t]['branch'] == ['kept' if keep else 'replaced'] for t in tids))
    fin = Cp if keep else 128
    expect(f'every batch thread ends at capacity {fin}', all(per[t]['final'] == fin for t in tids))
    good_alloc = all(per[t]['allocs'] == ([128] if per[t]['new'] else []) + [V + P, Cp] + ([] if keep else [128]) for t in tids)
    expect(f'each write grew its buffer by exactly two allocations, V+P = {V + P} then {Cp} (+128 at creation / replacement)', good_alloc)
    expect(f'each write\'s transient peak = 3(V+P) = {3 * (V + P)}', all(per[t]['peak'] == 3 * (V + P) for t in tids))
    dR = after['R'] - before['R']
    sum_threads = sum(per[t]['final'] - per[t]['initial'] for t in tids)
    other = {d: (b.live - init.get(d, (0, None))[0]) for d, b in st1.items() if d not in {per[t]['dob'] for t in tids} and b.live != init.get(d, (0, None))[0]}
    note(f'LEDGER R before {before["R"]} after {after["R"]} dR {dR}; sum over batch threads (final - initial) {sum_threads}; other changed instances {other}')
    expect('dR = sum over the batch threads of (final - initial capacity), and no other scratch buffer changed', dR == sum_threads and not other)
    retained = sum(per[t]['final'] for t in tids)
    note(f'RETAINED by the {N} batch threads: {retained} B ({"16C" if keep else "N x 128"} predicted {N * fin})')
    expect(f'retained = {N} x {fin} = {N * fin}', retained == N * fin)
    new_inst = sum(1 for e in win if e['kind'] == 'new')
    if not heapmode:
        dMU = after['MemoryUsed'] - before['MemoryUsed']; dCt = after['Count'] - before['Count']
        note(f'POOL dMemoryUsed {dMU} vs dR {dR} (diff {dMU - dR}); dCount {dCt} vs new instances {new_inst}')
        expect(f'|dMemoryUsed - dR| <= tau = {TAU}', abs(dMU - dR) <= TAU)
        expect('dCount = new scratch instances in the window', dCt == new_inst)
    else:
        dMU = after['MemoryUsed'] - before['MemoryUsed']
        expect('arm H: every ledger allocation direct=false', all(e.get('direct') in ('false', False) for e in win if e['kind'] == 'alloc'))
        expect(f'arm H: |dMemoryUsed| <= tau (got {dMU})', abs(dMU) <= TAU)
    if persist:
        note(f'PERSIST 70 s later: MemoryUsed {persist["MemoryUsed"]} vs after {after["MemoryUsed"]}; ledger R {persist["R"]}')
        expect('persistence: MemoryUsed within tau of the after reading 70 s later', abs(persist['MemoryUsed'] - after['MemoryUsed']) <= TAU)
    if Lspec == '64':
        idle = [e for e in ledger.parse(LG, 0, before['ledger_off']) if e['kind'] in ('kept', 'replaced')]
        note(f'L=64: branch lines before the batch: kept {sum(1 for e in idle if e["kind"] == "kept")}, replaced {sum(1 for e in idle if e["kind"] == "replaced")}')
        expect('L=64: every scratch close on the node is replaced (no kept line at all)', not any(e['kind'] == 'kept' for e in ledger.parse(LG, 0, after['ledger_off'])))
    res = dict(label=label, L=L, Lspec=Lspec, batch=batch, heap=heapmode, N=N, P=P, V=V, C=Cp, keep=keep, before=before, hold=hold, after=after,
               persist=persist, retained=retained, dR=dR, per={str(t): per[t] for t in tids}, expected=f'{n_yes}/{n_exp}')
    json.dump(res, open(D + '/result.json', 'w'), indent=1)
    note(f'DONE {label} expected {n_yes}/{n_exp} yes')
    stop_node(D)


def report():
    global SESSION, SUMMARY, n_exp, n_yes
    D = f'{LOGROOT}/report'
    os.makedirs(D, exist_ok=True)
    SESSION = open(D + '/session.log', 'a'); SUMMARY = open(D + '/summary.txt', 'w'); n_exp = n_yes = 0
    R = {}
    for d in sorted(os.listdir(LOGROOT)):
        p = f'{LOGROOT}/{d}/result.json'
        if os.path.exists(p):
            R[d] = json.load(open(p))
    note('labels with a result: ' + ' '.join(R))
    dmu = lambda r: r['after']['MemoryUsed'] - r['before']['MemoryUsed']
    for b in ('B1', 'B2', 'B3', 'BA', 'BB'):
        row = {Ls: R.get(f'L{Ls}-{b}') for Ls in ('262144', 'default', '4194304')}
        note(f'STAIRCASE {b}: ' + ' | '.join(f'L={Ls}: C={r["C"]} {"kept" if r["keep"] else "replaced"} retained={r["retained"]} dMU={dmu(r)}' if r else f'L={Ls}: missing' for Ls, r in row.items()))
    want = {('B1', '262144'): True, ('B1', 'default'): True, ('B1', '4194304'): True, ('B2', '262144'): False, ('B2', 'default'): True,
            ('B2', '4194304'): True, ('B3', '262144'): False, ('B3', 'default'): False, ('B3', '4194304'): True}
    for (b, Ls), k in want.items():
        r = R.get(f'L{Ls}-{b}')
        expect(f'staircase {b} at L={Ls}: {"kept, 16C" if k else "replaced, 2,048 B"}', r is not None and r['keep'] == k and r['retained'] == (16 * r['C'] if k else 2048))
    for Ls in ('262144', 'default', '4194304'):
        ra, rb = R.get(f'L{Ls}-BA'), R.get(f'L{Ls}-BB')
        expect(f'boundary at L={Ls}: BA C = L kept (16L retained), BB C = L + 2 replaced (2,048 B)',
               ra is not None and rb is not None and ra['C'] == ra['L'] and ra['retained'] == 16 * ra['L'] and rb['C'] == rb['L'] + 2 and rb['retained'] == 2048)
    for b in ('B1', 'B2', 'B3'):
        peaks = {Ls: sorted({v['peak'] for v in R[f'L{Ls}-{b}']['per'].values()}) for Ls in ('262144', 'default', '4194304') if f'L{Ls}-{b}' in R}
        expect(f'in-use peak of {b} identical at every L ({peaks})', len({tuple(v) for v in peaks.values()}) == 1)
    b2, bn = R.get('Ldefault-B2'), R.get('Ldefault-BN')
    if b2 and bn:
        expect(f'xN: BN retains a quarter of B2 by the ledger ({bn["retained"]} vs {b2["retained"]})', 4 * bn['retained'] == b2['retained'])
        expect(f'xN: dMU(B2) - 4 dMU(BN) within 4 tau of 0 ({dmu(b2) - 4 * dmu(bn)})', abs(dmu(b2) - 4 * dmu(bn)) <= 4 * TAU)
    c = R.get('L2147483647-B3')
    if c:
        expect(f'scenario C, L = 2^31 - 1, B3: kept, 16C retained ({c["retained"]})', c['keep'] and c['retained'] == 16 * c['C'])
    c64 = R.get('L64-B1')
    if c64:
        expect(f'scenario C, L = 64, B1: replaced, ks1 threads retain 2,048 B ({c64["retained"]})', (not c64['keep']) and c64['retained'] == 2048)
    for b in ('B2', 'B3'):
        h, dd = R.get(f'Ldefault-{b}-heap'), R.get(f'Ldefault-{b}')
        if h and dd and h['after'].get('live_B_bytes') and dd['after'].get('live_B_bytes'):
            diff = h['after']['live_B_bytes'] - dd['after']['live_B_bytes']
            want_d = 16 * h['C'] if b == 'B2' else 0
            expect(f'arm H {b}: live [B higher than direct mode by {want_d} +/- 2 MB (got {diff})', abs(diff - want_d) <= 2_000_000)
    note(f'DONE report expected {n_yes}/{n_exp} yes')


def main():
    for label in sys.argv[1:]:
        try:
            report() if label == 'report' else run_label(label)
        except SystemExit:
            raise
        except Exception as e:
            import traceback
            note(f'FAIL (exception) in {label}: {e!r}'); log(traceback.format_exc())
            stop_node(); sys.exit(1)


main()
