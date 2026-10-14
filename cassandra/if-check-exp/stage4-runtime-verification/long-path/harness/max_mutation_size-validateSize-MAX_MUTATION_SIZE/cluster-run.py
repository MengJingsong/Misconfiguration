#!/usr/bin/env python3
"""Stage 4, cluster tier, max_mutation_size-validateSize-MAX_MUTATION_SIZE (case 9b-9e).
usage: cluster-run.py instrument | value <label> | batch <label> | derived | replay | down
       label: 1m | 4m | default        (instrument uses the 1m yaml; derived and replay use the default value)
One node (~/cassandra-run1), RF 1, a fresh start per mode. Logs every command to ~/stage4-logs/mms/<run>/session.log, writes
summary.txt (EXPECTED lines) and readings.csv. Exit 1: an instrument or set-up check failed. The node is stopped on any exit."""
import csv, json, os, re, subprocess, sys, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-run1')
HARNESS = os.path.dirname(os.path.abspath(__file__))
VALUES = {'1m': ('1MiB', 1048576), '4m': ('4MiB', 4194304), 'default': ('none', 16777216)}
CL_BEAN = 'org.apache.cassandra.db:type=Commitlog'
OV_BEAN = 'org.apache.cassandra.metrics:type=CommitLog,name=OverSizedMutations'
BG = 65536            # background bound, 9c
SEG = 32 * 1048576    # commitlog_segment_size, 9b
GUARD_RE = re.compile(r'Rejected an oversized mutation \((\d+)/(\d+)\)')

mode = sys.argv[1]
label = sys.argv[2] if len(sys.argv) > 2 else {'instrument': '1m', 'derived': 'default', 'replay': 'default', 'down': 'default'}[mode]
VAL, M = VALUES[label]
RUN = {'value': label, 'batch': f'{label}-batch'}.get(mode, mode)
D = f'{HOME}/stage4-logs/mms/{RUN}'
os.makedirs(D, exist_ok=True)
SESSION = open(D + '/session.log', 'a')
SUMMARY = open(D + '/summary.txt', 'w')
RCSV = csv.writer(open(D + '/readings.csv', 'w'))
RCSV.writerow(['run', 'step', 'command', 'outcome', 'T', 'M', 'cs_before', 'cs_after', 'cs_delta', 'ov_before', 'ov_after', 'detail'])
SYSLOG = C + '/logs/system.log'


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, file=sys.stderr); SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush(); log(s)


def sh(cmd, timeout=300, check=True, env=None):
    log('+ ' + cmd)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env, cwd=C)
    out = (r.stdout or '') + (r.stderr or '')
    SESSION.write(out[-4000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed rc={r.returncode}: {cmd}\n{out[-800:]}')
    return r.returncode, out


def daemon_pids():
    r = subprocess.run("ps -eo pid,args | grep '[o]rg.apache.cassandra.service.CassandraDaemon' | awk '{print $1}'",
                       shell=True, capture_output=True, text=True)
    return [p for p in r.stdout.split() if p.isdigit()]


def stop_node(kill=False):
    if daemon_pids() and not kill:
        sh('bin/nodetool stopdaemon', check=False)
        for _ in range(90):
            if not daemon_pids():
                break
            time.sleep(1)
    for p in daemon_pids():
        log(f'kill -9 {p}'); subprocess.run(['kill', '-9', p]); time.sleep(2)
    if daemon_pids():
        log('WARNING: a CassandraDaemon is still running')
    if os.path.exists(SYSLOG):
        sh(f'cp {SYSLOG} {D}/system.log', check=False)


def finish(rc):
    stop_node()
    sh('git checkout -q conf/cassandra.yaml', check=False)
    note(f'node stopped; daemons left: {len(daemon_pids())}')
    sys.exit(rc)


def fail(msg):
    note('FAIL: ' + msg)
    finish(1)


def expect(desc, cond):
    note(f'EXPECTED: {desc} — {"yes" if cond else "NO (recorded; the AI judges it in the results file)"}')
    return cond


def jmx(bean, attr):
    _, out = sh(f'{HARNESS}/jmx.sh "{bean}" {attr}', check=False)
    last = out.strip().splitlines()[-1] if out.strip() else ''
    m = re.findall(r'-?\d+', last)
    return int(m[-1]) if m else None


def cs():
    return jmx(CL_BEAN, 'ActiveContentSize')


def ov():
    return jmx(OV_BEAN, 'Count')


def client(*args):
    log('+ send-mutation.py ' + ' '.join(args))
    r = subprocess.run([sys.executable, f'{HARNESS}/send-mutation.py', *args], capture_output=True, text=True, timeout=400)
    line = (r.stdout.strip().splitlines() or ['ERR ClientFailure {}'])[-1]
    SESSION.write(line[:1500] + '\n' + r.stderr[-600:] + '\n'); SESSION.flush()
    ok = line.startswith('OK ')
    parts = line.split(' ', 2)
    try:
        body = json.loads(line[3:] if ok else parts[2])
    except Exception:
        body = {'raw': line[:600]}
    body['ok'] = ok
    body['class'] = None if ok else parts[1]
    return body


def guard_operands(res):
    m = GUARD_RE.search(res.get('message', '') or '')
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def write(step, *args):
    """one client call with ActiveContentSize and OverSizedMutations read before and after"""
    c0, o0 = cs(), ov()
    res = client(*args)
    c1, o1 = cs(), ov()
    T, Mr = guard_operands(res)
    d = None if c0 is None or c1 is None else c1 - c0
    outcome = 'OK' if res['ok'] else f"ERR {res['class']}"
    RCSV.writerow([RUN, step, ' '.join(args), outcome, T, Mr, c0, c1, d, o0, o1, (res.get('message') or json.dumps(res))[:300]])
    note(f'{step}: {" ".join(args)} -> {outcome}  T/M={T}/{Mr}  content {c0}->{c1} (delta {d})  OverSized {o0}->{o1}'
         + ('' if res['ok'] else f'  msg: {(res.get("message") or "")[:200]}'))
    return res, T, Mr, d, (None if o0 is None or o1 is None else o1 - o0)


def readback(pk):
    r = client('readback', str(pk))
    note(f'readback {pk}: {"exists len=" + str(r.get("length")) if r.get("exists") else "no row" if r["ok"] else "ERR " + str(r.get("message"))[:200]}')
    RCSV.writerow([RUN, f'readback {pk}', f'readback {pk}', 'OK' if r['ok'] else 'ERR', None, None, None, None, None, None, None,
                   json.dumps({'exists': r.get('exists'), 'length': r.get('length')})])
    return r


def vint_size(v):
    """bytes of Cassandra's unsigned vint for v >= 0 (VIntCoding.computeUnsignedVIntSize)"""
    n = 1
    while v >= (1 << (7 * n)) and n < 9:
        n += 1
    return n


def start(yaml_args, wipe=True):
    if daemon_pids():
        fail('a CassandraDaemon is already running before the start')
    note(sh(f'{HARNESS}/make-node-yaml.sh {yaml_args}')[1].strip())
    sh(f'cp conf/cassandra.yaml {D}/cassandra.yaml')
    if wipe:
        sh('rm -rf data logs saved_caches')
    env = dict(os.environ, MAX_HEAP_SIZE='4G')
    env.pop('HEAP_NEWSIZE', None)
    sh(f'bin/cassandra -p {D}/cassandra.pid > {D}/startup.log 2>&1', env=env)
    for _ in range(120):
        _, st = sh('bin/nodetool statusbinary', check=False)
        _, ns = sh('bin/nodetool status', check=False)
        if 'running' in st and re.search(r'^UN', ns, re.M):
            break
        time.sleep(2)
    else:
        fail('node did not come up')
    note('node up')


def schema():
    sh('bin/cqlsh -e "CREATE KEYSPACE ks1 WITH replication = {\'class\': \'SimpleStrategy\', \'replication_factor\': 1}; '
       'CREATE TABLE ks1.t (pk int PRIMARY KEY, v blob) WITH compression = {\'enabled\': false} AND '
       'compaction = {\'class\': \'SizeTieredCompactionStrategy\', \'enabled\': \'false\'};"')
    p = client('probe')
    if not p['ok']:
        fail('probe failed: ' + str(p))


def idle(seconds):
    rows = []
    for t in range(0, seconds + 1, 10):
        if t:
            time.sleep(10 - 2)  # the two JMX reads take about 2 s
        rows.append((t, cs(), ov()))
    for t, c, o in rows:
        RCSV.writerow([RUN, f'idle t={t}', '', '', None, None, c, None, None, o, None, ''])
    move = max(r[1] for r in rows) - min(r[1] for r in rows) if all(r[1] is not None for r in rows) else None
    note(f'idle over {seconds} s: content {[r[1] for r in rows]} (moved {move}); OverSized {[r[2] for r in rows]}')
    return move


def calibrate(pkey=1):
    res, T, Mr, d, dov = write('calibration', 'insert', str(pkey), str(M + 8192))
    if T is None:
        fail('calibration write was not refused by the guard: ' + str(res.get('message'))[:300])
    if Mr != M:
        fail(f'limit read back {Mr} differs from the value set {M} (invalid run)')
    k = T - (M + 8192)
    same = vint_size(M + 8192) == vint_size(M - k)
    note(f'calibration: T={T} M={Mr} k={k}; payload classes {vint_size(M + 8192)} / {vint_size(M - k)}')
    if not same:
        fail('calibration and exact-boundary payloads are in different vint classes; recalibrate (9c)')
    return k


try:
    if mode == 'down':
        stop_node()
        sh('git checkout -q conf/cassandra.yaml', check=False)
        note(f'down: daemons left {len(daemon_pids())}')
        sys.exit(0)

    if mode == 'instrument':
        start(f'{label} {VAL}')
        schema()
        p = client('probe')
        if not expect(f'(i) probe over protocol 4: {p.get("release_version")} protocol {p.get("protocol")}', p['ok'] and p.get('protocol') == 4):
            fail('(i)')
        c0, o0 = cs(), ov()
        if not expect(f'(ii) jmx reads ActiveContentSize={c0} OverSizedMutations={o0}', c0 is not None and o0 is not None):
            fail('(ii)')
        res, T, Mr, d, dov = write('instr 1KiB', 'insert', '0', '1024')
        if not expect(f'(iii) 1,024 B insert raises content by 1,044..1,536: {d}', res['ok'] and d is not None and 1044 <= d <= 1536):
            fail('(iii)')
        res, *_ = write('instr logged batch', 'batch', 'logged', '40', '41', '1024')
        if not expect('(iv) logged batch of two 1,024 B rows succeeds', res['ok']):
            fail('(iv)')
        res, T, Mr, d, dov = write('instr over', 'insert', '1', str(M + 8192))
        if not expect(f'(v) M+8192 refused by the guard, (T/M) parses: {T}/{Mr}', T is not None and Mr == M):
            fail('(v)')
        mv = idle(30)
        if not expect(f'(vi) idle 30 s moves content < 64 KiB: {mv}', mv is not None and mv < BG):
            fail('(vi)')
        st = client('settings')
        expect(f'(vii) system_views.settings max_mutation_size: {st.get("rows")} (secondary, not a failure)', bool(st.get('rows')))
        note('instrument check passed')
        finish(0)

    if mode == 'value':
        start(f'{label} {VAL}')
        schema()
        mv = idle(30)
        expect(f'idle control: content moved {mv} < {BG}', mv is not None and mv < BG)
        res, T, Mr, d, dov = write('control 1KiB', 'insert', '0', '1024')
        expect(f'control: 1 KiB write raises content by 1,044..1,536: {d}', res['ok'] and d is not None and 1044 <= d <= 1536)
        k = calibrate(1)
        json.dump({'label': label, 'M': M, 'k': k}, open(D + '/calibration.json', 'w'))
        # scenario A
        res, T, Mr, d, dov = write('A exact', 'insert', '2', str(M - k))
        if not res['ok']:
            note('exact-boundary write refused or failed: ' + str(res.get('message'))[:300])
        expect(f'A: T=M write accepted', res['ok'])
        expect(f'A: content rise {d} = M+8 = {M + 8} (to within +{BG})', d is not None and M + 8 <= d <= M + 8 + BG)
        expect(f'A: OverSized delta 0: {dov}', dov == 0)
        # scenario B
        for pk, n, exact in ((3, M - k + 1, True), (4, M + 8192, False), (5, M + 1048576, False)):
            res, T, Mr, d, dov = write(f'B pk{pk}', 'insert', str(pk), str(n))
            expect(f'B pk{pk}: refused with InvalidRequest and the guard message: {res["class"]} T/M={T}/{Mr}',
                   (not res['ok']) and res['class'] == 'InvalidRequest' and Mr == M)
            if T is not None:
                extra = T - n - k
                expect(f'B pk{pk}: T - payload - k = {extra} ' + ('= 0' if exact else 'in 0..4'),
                       extra == 0 if exact else 0 <= extra <= 4)
            expect(f'B pk{pk}: OverSized +1: {dov}', dov == 1)
            expect(f'B pk{pk}: content within {BG}: {d}', d is not None and abs(d) < BG)
        # flush and read back
        sh('bin/nodetool flush ks1 t')
        _, ls = sh('ls -l data/data/ks1/t-*/*-Data.db', check=False)
        sizes = [int(x.split()[4]) for x in ls.splitlines() if x.endswith('Data.db')]
        note(f'Data.db sizes: {sizes}')
        expect(f'Data.db total {sum(sizes)} in [M-k+1024, M-k+1024+8192] = [{M - k + 1024}, {M - k + 1024 + 8192}]',
               M - k + 1024 <= sum(sizes) <= M - k + 1024 + 8192)
        r0, r2 = readback(0), readback(2)
        expect('readback 0 = 1024', r0.get('length') == 1024)
        expect(f'readback 2 = M-k = {M - k}', r2.get('length') == M - k)
        for pk in (1, 3, 4, 5):
            expect(f'readback {pk}: no row', readback(pk).get('exists') is False)
        stop_node()
        _, e = sh(f"grep -c '^ERROR' {D}/system.log", check=False)
        note(f'system.log ERROR lines: {e.strip()}')
        finish(0)

    if mode == 'batch':
        start(f'{label} {VAL}')
        schema()
        mv = idle(10)
        expect(f'idle 10 s: content moved {mv} < {BG}', mv is not None and mv < BG)
        n = int(0.55 * M)
        res, T, Mr, d, dov = write('unlogged', 'batch', 'unlogged', '10', '11', str(n))
        expect('unlogged batch accepted', res['ok'])
        expect(f'unlogged: content rise {d} > M = {M} (about 1.1 M = {int(1.1 * M)})', d is not None and d > M)
        expect('unlogged: readback 10 and 11 = payload', readback(10).get('length') == n and readback(11).get('length') == n)
        res, T, Mr, d, dov = write('logged', 'batch', 'logged', '12', '13', str(n))
        expect(f'logged batch refused with WriteFailure: {res["class"]}', (not res['ok']) and res['class'] == 'WriteFailure')
        expect(f'logged: OverSized +1: {dov}', dov == 1)
        expect(f'logged: content within {BG}: {d}', d is not None and abs(d) < BG)
        expect('logged: readback 12 and 13: no row', readback(12).get('exists') is False and readback(13).get('exists') is False)
        _, g = sh(f"grep -n -A 3 'Failed to apply mutation locally' {SYSLOG}", check=False)
        open(D + '/failed-locally.txt', 'w').write(g)
        expect('system.log: Failed to apply mutation locally with MutationExceededMaxSizeException naming keyspace system, batches',
               'MutationExceededMaxSizeException' in g and 'keyspace: system' in g and 'batches' in g)
        m = GUARD_RE.search(g)
        note(f'logged batch guard operands in system.log: {m.group(1) + "/" + m.group(2) if m else None}')
        finish(0)

    if mode == 'derived':
        start(f'derived none default-transport')
        schema()
        idle(10)
        res, T, Mr, d, dov = write('derived over', 'insert', '20', str(M + 8192))
        msg = res.get('message') or ''
        expect('derived: refused with "Request is too big ... maximum allowed length 16777216."',
               (not res['ok']) and 'Request is too big' in msg and 'maximum allowed length 16777216' in msg)
        expect(f'derived: OverSized unchanged: {dov}', dov == 0)
        expect(f'derived: content within {BG}: {d}', d is not None and abs(d) < BG)
        res, *_ = write('derived 1KiB', 'insert', '21', '1024')
        expect('derived: insert 21 1024 OK (the node still serves)', res['ok'])
        finish(0)

    if mode == 'replay':
        start(f'default none')
        schema()
        k = calibrate(29)
        res, T, Mr, d, dov = write('C write under 16 MiB', 'insert', '30', str(M - k))
        expect('C: 16 MiB row accepted', res['ok'])
        _, segs = sh('ls -l data/commitlog/', check=False)
        note('commit-log segments before kill:\n' + segs.strip())
        sh(f'cp {SYSLOG} {D}/system.before-kill.log', check=False)
        stop_node(kill=True)
        expect('C: no daemon after kill -9', not daemon_pids())
        start('replay 1MiB', wipe=False)
        _, rp = sh(f"grep -i 'replay' {SYSLOG}", check=False)
        open(D + '/replay-lines.txt', 'w').write(rp)
        note('replay lines: ' + str(len(rp.splitlines())) + '\n' + '\n'.join(rp.splitlines()[:8]))
        expect('C: system.log shows a commit-log replay', 'replay' in rp.lower())
        r = readback(30)
        expect(f'C: readback 30 = M16-k = {M - k} although the limit is now 1 MiB (bypass volume)', r.get('length') == M - k)
        res, T, Mr, d, dov = write('C new write under 1 MiB', 'insert', '31', str(M - k))
        expect(f'C: new write of the same size refused with (T/1048576): {T}/{Mr}', Mr == 1048576)
        finish(0)

    fail('unknown mode ' + mode)
except SystemExit:
    raise
except Exception as e:
    note(f'FAIL: exception {type(e).__name__}: {str(e)[:800]}')
    finish(1)
