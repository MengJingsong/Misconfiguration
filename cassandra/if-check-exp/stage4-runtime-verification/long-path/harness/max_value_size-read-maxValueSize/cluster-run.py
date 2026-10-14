#!/usr/bin/env python3
"""Stage 4, cluster tier, max_value_size-read-maxValueSize (case 9b-9e, amended 2026-10-13).
usage: cluster-run.py instrument | value <1m|4m|8m|default> | compaction | replay | down
       instrument uses the 1m yaml; compaction is at 1m; replay starts at 4m, restarts at 1m, then at 4m.
One node (~/cassandra-run1), RF 1, a fresh data/ per mode (the replay arm keeps it between its starts). Logs every command to
<logroot>/<run>/session.log (logroot ~/stage4-logs/mvs, or $STAGE4_LOGROOT for shakedowns), writes summary.txt (EXPECTED
lines), readings.csv, the Byteman trace alloc.trace and a copy of system.log. Exit 1: an instrument, control or set-up check
failed (invalid run). The node is stopped and conf/cassandra.yaml restored on any exit."""
import csv, glob, json, os, re, subprocess, sys, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-run1')
HARNESS = os.path.dirname(os.path.abspath(__file__))
BM = C + '/build/lib/jars'
LOGROOT = os.environ.get('STAGE4_LOGROOT', HOME + '/stage4-logs/mvs')
MIB = 1048576
EPS = 65536                       # 9c
THRESH = 262144                   # trace threshold, 9c
VALUES = {'1m': ('1MiB', MIB), '4m': ('4MiB', 4 * MIB), '8m': ('8MiB', 8 * MIB), 'default': ('none', 268435456)}
DEFAULT_ROW = 15728640            # default arm, 9c
REPLAY_ROW = 2097152              # replay arm, 9e
SYSLOG = C + '/logs/system.log'
GUARD_RE = re.compile(r'Corrupt value length (\d+) encountered, as it exceeds the maximum of (\d+)')

mode = sys.argv[1] if len(sys.argv) > 1 else 'down'
label = sys.argv[2] if mode == 'value' else {'instrument': '1m', 'compaction': '1m', 'replay': '4m', 'down': 'default'}.get(mode, '1m')
if label not in VALUES:
    sys.exit(f'unknown label {label}')
VAL, M = VALUES[label]
RUN = label if mode == 'value' else mode
D = f'{LOGROOT}/{RUN}'
os.makedirs(D, exist_ok=True)
TRACE = D + '/alloc.trace'
SESSION = open(D + '/session.log', 'a')
SUMMARY = open(D + '/summary.txt', 'w')
RFILE = open(D + '/readings.csv', 'w')
RCSV = csv.writer(RFILE)
RCSV.writerow(['run', 'step', 'command', 'outcome', 'length', 'guard_l', 'guard_M', 'trace_new_lengths', 'log_new', 'detail'])


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


def copy_logs():
    if os.path.exists(SYSLOG):
        sh(f'cp {SYSLOG} {D}/system.log', check=False)


def stop_node(kill=False):
    if daemon_pids() and not kill:
        sh('bin/nodetool stopdaemon', check=False, timeout=120)
        for _ in range(90):
            if not daemon_pids():
                break
            time.sleep(1)
    for p in daemon_pids():
        log(f'kill -9 {p}'); subprocess.run(['kill', '-9', p]); time.sleep(2)
    if daemon_pids():
        log('WARNING: a CassandraDaemon is still running')
    copy_logs()


def finish(rc):
    stop_node()
    sh('git checkout -q conf/cassandra.yaml', check=False)
    note(f'node stopped; daemons left: {len(daemon_pids())}; yaml restored')
    RFILE.flush()
    sys.exit(rc)


def fail(msg):
    note('FAIL: ' + msg)
    finish(1)


def expect(desc, cond):
    note(f'EXPECTED: {desc} — {"yes" if cond else "NO (recorded; the AI judges it in the results file)"}')
    return cond


# ------------------------------------------------------------------ observables

def trace_lines():
    if not os.path.exists(TRACE):
        return []
    rows = []
    for l in open(TRACE, errors='replace'):
        m = re.match(r'alloc class=(\S+) length=(\d+) thread=(.*) ms=(\d+)$', l.strip())
        if m:
            rows.append({'class': m.group(1), 'length': int(m.group(2)), 'thread': m.group(3), 'ms': int(m.group(4))})
    return rows


def trace_count(length, rows=None):
    return sum(1 for r in (trace_lines() if rows is None else rows) if r['length'] == length)


def syslog_size():
    return os.path.getsize(SYSLOG) if os.path.exists(SYSLOG) else 0


def syslog_since(off):
    if not os.path.exists(SYSLOG):
        return ''
    with open(SYSLOG, errors='replace') as f:
        f.seek(off)
        return f.read()


def client(*args):
    log('+ send-value.py ' + ' '.join(args))
    r = subprocess.run([sys.executable, f'{HARNESS}/send-value.py', *args], capture_output=True, text=True, timeout=400)
    line = (r.stdout.strip().splitlines() or ['ERR ClientFailure {}'])[-1]
    SESSION.write(line[:3000] + '\n' + r.stderr[-600:] + '\n'); SESSION.flush()
    ok = line.startswith('OK ')
    parts = line.split(' ', 2)
    try:
        body = json.loads(line[3:] if ok else parts[2])
    except Exception:
        body = {'raw': line[:1500]}
    body['ok'] = ok
    body['class'] = None if ok else parts[1]
    return body


def op(step, *args, settle=1.0):
    """one client call; returns the result, the new system.log text and the trace lines it added"""
    off, n0 = syslog_size(), len(trace_lines())
    res = client(*args)
    time.sleep(settle)
    newlog = syslog_since(off)
    added = trace_lines()[n0:]
    g = GUARD_RE.search(res.get('message') or '') or GUARD_RE.search(newlog)
    gl, gm = (int(g.group(1)), int(g.group(2))) if g else (None, None)
    outcome = 'OK' if res['ok'] else f"ERR {res['class']}"
    flags = [k for k, pat in (('guard', 'Corrupt value length'), ('CorruptSSTableException', 'CorruptSSTableException'),
                              ('UnexpectedDuringRequest', 'Unexpected exception during request')) if pat in newlog]
    lens = sorted({a['length'] for a in added})
    RCSV.writerow([RUN, step, ' '.join(args), outcome, res.get('length'), gl, gm, ' '.join(map(str, lens)), ' '.join(flags),
                   (res.get('message') or '')[:400]])
    RFILE.flush()
    note(f'{step}: {" ".join(args)} -> {outcome}' + (f' length={res.get("length")}' if res['ok'] and 'length' in res else '')
         + f'  guard l/M={gl}/{gm}  new trace lengths={lens}  new log: {flags or "-"}'
         + ('' if res['ok'] else f'  msg: {(res.get("message") or "")[:260]}'))
    return res, newlog, added, gl, gm


def table_dir(table):
    d = glob.glob(f'{C}/data/data/ks1/{table}-*')
    return d[0] if d else None


def listing(table):
    d = table_dir(table)
    return sorted(os.listdir(d)) if d else []


def data_files(table):
    d = table_dir(table)
    out = []
    for f in sorted(glob.glob(f'{d}/*-Data.db')) if d else []:
        m = re.search(r'-(\d+)-big-Data\.db$', f)
        out.append((int(m.group(1)) if m else -1, os.path.basename(f), os.path.getsize(f)))
    return sorted(out)


def memtable_data_size(table='t'):
    _, out = sh(f'bin/nodetool tablestats ks1.{table}', check=False)
    m = re.search(r'Memtable data size:\s*(\d+)', out)
    return int(m.group(1)) if m else None


# ------------------------------------------------------------------ node

def wait_start(pid_file, timeout, expect_up=True):
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


def start(tag, val, trace=True, wipe=True, expect_up=True, timeout=240):
    if daemon_pids():
        fail('a CassandraDaemon is already running before the start')
    note(sh(f'{HARNESS}/make-node-yaml.sh {tag} {val}')[1].strip().replace('\n', ' | '))
    sh(f'cp conf/cassandra.yaml {D}/cassandra.{tag}.yaml')
    _, y = sh('grep -E "^(commitlog_sync|commitlog_sync_period|write_request_timeout|read_request_timeout|disk_failure_policy|'
              'commit_failure_policy|max_value_size|commitlog_segment_size|memtable_allocation_type)\\b" conf/cassandra.yaml', check=False)
    note('yaml in force: ' + ' ; '.join(y.strip().splitlines()))
    if wipe:
        if C != HOME + '/cassandra-run1':
            fail(f'unexpected clone path {C}')
        sh('rm -rf data logs saved_caches')
    env = dict(os.environ, MAX_HEAP_SIZE='4G')
    env.pop('HEAP_NEWSIZE', None)
    env.pop('JVM_EXTRA_OPTS', None)
    if trace:
        env['JVM_EXTRA_OPTS'] = f'-javaagent:{BM}/byteman-4.0.20.jar=script:{HARNESS}/value-alloc.btm,listener:true -Dstage4.byteman.out={TRACE}'
        note('JVM_EXTRA_OPTS=' + env['JVM_EXTRA_OPTS'])
    pid_file = f'{D}/cassandra.{tag}.pid'
    if os.path.exists(pid_file):
        os.remove(pid_file)
    sh(f'bin/cassandra -p {pid_file} > {D}/startup.{tag}.log 2>&1', env=env)
    state, secs = wait_start(pid_file, timeout, expect_up)
    note(f'start {tag}: {state} after {secs:.0f} s')
    if not expect_up:
        return state
    if state != 'up':
        fail(f'node did not come up ({state}); see startup.{tag}.log and system.log')
    pid = open(pid_file).read().strip()
    args = open(f'/proc/{pid}/cmdline').read().split('\0')
    open(f'{D}/jvm-args.{tag}.txt', 'w').write('\n'.join(args))
    if '-Xmx4G' not in args:
        fail('JVM lacks -Xmx4G')
    if trace and not any('byteman-4.0.20.jar' in a for a in args):
        fail('JVM lacks the Byteman agent')
    return state


def schema(extra_ok=False):
    tdef = ("(pk int PRIMARY KEY, v blob) WITH compression = {'enabled': false} AND "
            "compaction = {'class': 'SizeTieredCompactionStrategy', 'enabled': 'false'}")
    stmts = ["CREATE KEYSPACE ks1 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};",
             f'CREATE TABLE ks1.t {tdef};']
    if extra_ok:
        stmts.append(f'CREATE TABLE ks1.ok {tdef};')
    sh('bin/cqlsh -e "' + ' '.join(stmts).replace('"', '\\"') + '"')
    p = client('probe')
    if not p['ok'] or p.get('protocol') != 4:
        fail('probe failed or not protocol 4: ' + str(p))
    note(f'probe: release {p.get("release_version")} protocol {p.get("protocol")}')


def idle(seconds=10):
    n0 = len(trace_lines())
    time.sleep(seconds)
    rows = trace_lines()
    note(f'idle {seconds} s: trace lines {n0} -> {len(rows)} (total {len(rows)})')
    return len(rows)


def control(fail_hard=True):
    """9e Phase 1 step 1 / instrument (iii): 1,024 B and 307,200 B rows, flushed and read back"""
    r0, *_ = op('control insert 0', 'insert', '0', '1024')
    r1, *_ = op('control insert 99', 'insert', '99', '307200')
    sh('bin/nodetool flush ks1 t')
    a, *_ = op('control readback 0', 'readback', '0')
    b, *_ = op('control readback 99', 'readback', '99')
    rows = trace_lines()
    ok = (r0['ok'] and r1['ok'] and a.get('length') == 1024 and b.get('length') == 307200
          and trace_count(307200, rows) >= 1 and trace_count(1024, rows) == 0)
    expect(f'control: rows read back at 1024 / 307200 ({a.get("length")} / {b.get("length")}); trace has '
           f'{trace_count(307200, rows)} line(s) of 307,200 (>= 1) and {trace_count(1024, rows)} of 1,024 (0)', ok)
    if not ok and fail_hard:
        fail('control failed: invalid run (9a)')
    return ok


def head():
    note(f'run {RUN} on {os.uname().nodename}; {time.strftime("%F %T %Z")}; epoch ms {int(time.time() * 1000)}')
    note('clone: ' + sh('git rev-parse HEAD')[1].strip() + ' ' + sh('git describe --tags')[1].strip())
    note('harness md5: ' + sh(f'cd {HARNESS} && md5sum *.java *.btm *.py *.sh | tr "\\n" ";"')[1].strip())
    if os.path.exists(TRACE):
        os.remove(TRACE)


try:
    if mode == 'down':
        stop_node()
        sh('git checkout -q conf/cassandra.yaml', check=False)
        note(f'down: daemons left {len(daemon_pids())}')
        sys.exit(0)

    head()

    # ---------------------------------------------------------------- instrument check (9e, before the cluster tier)
    if mode == 'instrument':
        sh(f'java -classpath {BM}/byteman-4.0.20.jar:build/classes/main:"build/lib/jars/*" org.jboss.byteman.check.TestScript '
           f'{HARNESS}/value-alloc.btm > {D}/testscript.txt 2>&1', check=False)
        ts = open(D + '/testscript.txt').read()
        note('Byteman TestScript: ' + ' | '.join(l for l in ts.splitlines() if re.search(r'^Type checked|ERROR|TestScript:', l)))
        if 'TestScript: no errors' not in ts:
            fail('(ii) Byteman TestScript reports errors (testscript.txt)')
        start('instrument', VAL)
        schema()
        p = client('probe')
        if not expect(f'(i) probe over protocol 4: {p.get("release_version")} protocol {p.get("protocol")}', p['ok'] and p.get('protocol') == 4):
            fail('(i)')
        _, sl = sh(f'java -cp {BM}/byteman-submit-4.0.20.jar org.jboss.byteman.agent.submit.Submit -l', check=False)
        open(D + '/submit-l.txt', 'w').write(sl)
        note('Submit -l: ' + ' | '.join(l.strip() for l in sl.splitlines() if 'RULE' in l or 'trigger method' in l)[:600])
        n = idle(10)
        if not expect(f'(ii) idle 10 s leaves no alloc line: {n}', n == 0):
            fail('(ii) idle trace not empty')
        control()
        st = client('settings')
        expect(f'(iv) system_views.settings max_value_size: {st.get("rows")} (secondary, not a failure)', bool(st.get('rows')))
        note('instrument check passed')
        finish(0)

    # ---------------------------------------------------------------- Phase 1 (9e)
    if mode == 'value':
        start(label, VAL)
        schema()
        n = idle(10)
        expect(f'idle control: no alloc line in 10 s ({n})', n == 0)
        control()
        if label == 'default':
            r, *_ = op('write 1', 'insert', '1', str(DEFAULT_ROW))
            expect(f'default: {DEFAULT_ROW} B row acknowledged', r['ok'])
            expect(f'default C: no trace line of {DEFAULT_ROW} after the write ({trace_count(DEFAULT_ROW)})', trace_count(DEFAULT_ROW) == 0)
            r, lg, added, *_ = op('C readback 1', 'readback', '1')
            expect(f'default C: readback 1 before the flush = {DEFAULT_ROW} ({r.get("length")}); trace gains a line of it '
                   f'({sum(1 for a in added if a["length"] == DEFAULT_ROW)})',
                   r.get('length') == DEFAULT_ROW and any(a['length'] == DEFAULT_ROW for a in added))
            sh('bin/nodetool flush ks1 t')
            note(f'Data.db after the flush: {data_files("t")}')
            r, lg, added, *_ = op('A readback 1', 'readback', '1')
            expect(f'default A: readback 1 after the flush = {DEFAULT_ROW} ({r.get("length")}); trace gains a line of it',
                   r.get('length') == DEFAULT_ROW and any(a['length'] == DEFAULT_ROW for a in added))
            stop_node()
            _, g = sh(f"grep -c 'Corrupt value length' {D}/system.log", check=False)
            expect(f'default: system.log has no "Corrupt value length" ({g.strip()})', g.strip() == '0')
            _, e = sh(f"grep -c '^ERROR' {D}/system.log", check=False)
            note(f'system.log ERROR lines: {e.strip()}')
            finish(0)

        B1, B2 = M + 1, M + 65536
        # 9e step 2: write
        for pk, n in ((1, M), (2, B1), (3, B2)):
            r, *_ = op(f'write {pk}', 'insert', str(pk), str(n))
            expect(f'write pk {pk} ({n} B) acknowledged', r['ok'])
        # 9e step 3: scenario C, before the flush
        rows = trace_lines()
        expect(f'C: no trace line of M / M+1 / M+65536 after the writes ({trace_count(M, rows)} / {trace_count(B1, rows)} / '
               f'{trace_count(B2, rows)})', trace_count(M, rows) == 0 and trace_count(B1, rows) == 0 and trace_count(B2, rows) == 0)
        mds = memtable_data_size()
        lo = 3 * M + 65537
        expect(f'C: Memtable data size {mds} in [{lo}, {lo + EPS})', mds is not None and lo <= mds < lo + EPS)
        r, lg, added, gl, gm = op('C readback 1', 'readback', '1')
        expect(f'C: readback 1 (A) before the flush = M = {M} ({r.get("length")}); trace gains a line of M '
               f'({sum(1 for a in added if a["length"] == M)})', r.get('length') == M and any(a['length'] == M for a in added))
        first_M = None
        for pk, l in ((2, B1), (3, B2)):
            r, lg, added, gl, gm = op(f'C readback {pk}', 'readback', str(pk))
            if first_M is None and gm is not None:
                first_M = gm
            expect(f'C: readback {pk} before the flush fails with ServerError ({r["class"]})', (not r['ok']) and r['class'] == 'ServerError')
            expect(f'C: guard operands {gl}/{gm} = {l}/{M} in the client message and system.log',
                   gl == l and gm == M and GUARD_RE.search(r.get('message') or '') is not None
                   and f'Corrupt value length {l} encountered, as it exceeds the maximum of {M}' in lg)
            expect('C: system.log entry under "Unexpected exception during request", no CorruptSSTableException',
                   'Unexpected exception during request' in lg and 'CorruptSSTableException' not in lg)
            expect(f'C: no trace line of {l}', not any(a['length'] == l for a in added))
        if first_M != M:
            fail(f'limit read back from the first refusal ({first_M}) differs from the value set ({M}): invalid run')
        note(f'limit read back from the first refusal: {first_M} = M')
        # 9e step 4: flush
        sh('bin/nodetool flush ks1 t')
        df = data_files('t')
        note(f'Data.db after the flush: {df}')
        newest = df[-1][2] if df else None
        expect(f'flush: newer Data.db {newest} B in [{lo}, {lo + EPS})', newest is not None and lo <= newest < lo + EPS)
        # 9e step 5: scenario A
        r, lg, added, *_ = op('A readback 1', 'readback', '1')
        expect(f'A: readback 1 after the flush = M ({r.get("length")}); trace gains line(s) of M '
               f'({sum(1 for a in added if a["length"] == M)})', r.get('length') == M and any(a['length'] == M for a in added))
        expect(f'A: no other new large length ({sorted({a["length"] for a in added})})', all(a['length'] == M for a in added))
        # 9e step 6: scenario B
        for pk, l in ((2, B1), (3, B2)):
            r, lg, added, gl, gm = op(f'B readback {pk}', 'readback', str(pk))
            expect(f'B: readback {pk} after the flush fails with ReadFailure ({r["class"]})', (not r['ok']) and r['class'] == 'ReadFailure')
            expect(f'B: system.log has "Corrupt value length {l} encountered, as it exceeds the maximum of {M}" and a CorruptSSTableException',
                   f'Corrupt value length {l} encountered, as it exceeds the maximum of {M}' in lg and 'CorruptSSTableException' in lg)
            expect(f'B: no trace line of {l}', not any(a['length'] == l for a in added))
        # 9e step 7: separation
        r, *_ = op('separation readback 1', 'readback', '1')
        expect(f'separation: readback 1 = M after the refused reads ({r.get("length")})', r.get('length') == M)
        # whole run
        rows = trace_lines()
        expect(f'whole run: no trace line of M+1 or M+65536 ({trace_count(B1, rows)} / {trace_count(B2, rows)})',
               trace_count(B1, rows) == 0 and trace_count(B2, rows) == 0)
        note(f'trace lines by length: {sorted({(a["length"], trace_count(a["length"], rows)) for a in rows})}')
        stop_node()
        _, e = sh(f"grep -c '^ERROR' {D}/system.log", check=False)
        _, g = sh(f"grep -c 'Corrupt value length' {D}/system.log", check=False)
        note(f'system.log ERROR lines: {e.strip()}; lines with "Corrupt value length": {g.strip()}')
        finish(0)

    # ---------------------------------------------------------------- compaction arm (1 MiB)
    if mode == 'compaction':
        start('compaction', VAL)
        schema(extra_ok=True)
        r0, *_ = op('ok insert 0', 'insert', '--table', 'ok', '0', '1024')
        r1, *_ = op('t insert 1', 'insert', '1', str(M))
        r2, *_ = op('t insert 2', 'insert', '2', str(M + 1))
        expect('compaction arm: the three writes acknowledged', r0['ok'] and r1['ok'] and r2['ok'])
        sh('bin/nodetool flush ks1')
        lt0, lo0 = listing('t'), listing('ok')
        note(f'listing t before: {lt0}'); note(f'listing ok before: {lo0}')
        note(f'Data.db t: {data_files("t")}; ok: {data_files("ok")}')
        rc, out = sh('bin/nodetool compact ks1 ok', check=False)
        time.sleep(2)
        lo1 = listing('ok')
        note(f'compact ks1 ok: rc={rc}; listing after: {lo1}')
        old = {f for f in lo0 if f.endswith('Data.db')}
        new = {f for f in lo1 if f.endswith('Data.db')}
        if not expect(f'control: ks1.ok compacted into a new generation ({sorted(old)} -> {sorted(new)})', rc == 0 and new and not (new & old)):
            fail('compaction control on ks1.ok wrote no new generation: invalid run (9a)')
        off = syslog_size()
        rc1, out1 = sh('bin/nodetool compact ks1 t', check=False)
        time.sleep(3)
        lg1 = syslog_since(off)
        lt1 = listing('t')
        open(D + '/compact-t-1.log', 'w').write(lg1)
        note(f'compact ks1 t (1st): rc={rc1}; output: {out1.strip()[-300:]!r}')
        note(f'listing t after the 1st: {lt1}')
        expect(f'1st compact t: system.log has "Corrupt value length {M + 1} encountered, as it exceeds the maximum of {M}" in a '
               f'CorruptSSTableException with a compaction class in the stack',
               f'Corrupt value length {M + 1} encountered, as it exceeds the maximum of {M}' in lg1 and 'CorruptSSTableException' in lg1
               and re.search(r'at org\.apache\.cassandra\.db\.compaction\.', lg1) is not None)
        expect('1st compact t: listing equal to the one before, no *_txn_*.log', lt1 == lt0 and not any('_txn_' in f for f in lt1))
        note(f'1st compact t failed at the client: rc={rc1} (non-zero expected)')
        off = syslog_size()
        rc2, out2 = sh('bin/nodetool compact ks1 t', check=False)
        time.sleep(3)
        lg2 = syslog_since(off)
        lt2 = listing('t')
        open(D + '/compact-t-2.log', 'w').write(lg2)
        note(f'compact ks1 t (2nd): rc={rc2}; output: {out2.strip()[-300:]!r}; listing after: {lt2}')
        expect('2nd compact t: no new guard message, listing unchanged (the SSTable is suspect)',
               'Corrupt value length' not in lg2 and lt2 == lt0)
        r, *_ = op('readback 1', 'readback', '1')
        expect(f'readback 1 on t after the failed compaction = M ({r.get("length")})', r.get('length') == M)
        finish(0)

    # ---------------------------------------------------------------- replay arm (4 MiB, then 1 MiB, then 4 MiB)
    if mode == 'replay':
        start('replay-4m', '4MiB')
        schema()
        r, *_ = op('write 30', 'insert', '30', str(REPLAY_ROW))
        expect(f'replay: {REPLAY_ROW} B row acknowledged under 4 MiB', r['ok'])
        r, *_ = op('readback 30', 'readback', '30')
        expect(f'replay: readback 30 = {REPLAY_ROW} ({r.get("length")})', r.get('length') == REPLAY_ROW)
        _, segs = sh('ls -l data/commitlog/', check=False)
        note('commit-log files before the kill: ' + ' | '.join(segs.strip().splitlines()))
        if not expect('replay: a commit-log segment exists', 'CommitLog-' in segs):
            fail('no commit-log segment before the kill')
        sh(f'cp {SYSLOG} {D}/system.before-kill.log', check=False)
        stop_node(kill=True)
        if not expect('replay: no daemon after kill -9', not daemon_pids()):
            fail('daemon still running after kill -9')
        off = syslog_size()
        state = start('replay-1m', '1MiB', trace=False, wipe=False, expect_up=False, timeout=180)
        lg = syslog_since(off)
        open(D + '/replay-1m.log', 'w').write(lg)
        hits = [l for l in lg.splitlines() if re.search(r'Corrupt value length|Replay stopped|encountered during startup', l)]
        note('replay-1m log hits:\n  ' + '\n  '.join(h[:300] for h in hits[:12]))
        expect(f'replay under 1 MiB: the node does not start, the process exits ({state})', state == 'exited')
        expect(f'replay under 1 MiB: log has "Corrupt value length {REPLAY_ROW} encountered, as it exceeds the maximum of {MIB}"',
               f'Corrupt value length {REPLAY_ROW} encountered, as it exceeds the maximum of {MIB}' in lg)
        expect('replay under 1 MiB: log has "Replay stopped. If you wish to override this error"',
               'Replay stopped. If you wish to override this error' in lg)
        if state != 'exited':
            note('the node came up or did not settle under 1 MiB; stopping it')
            stop_node()
        _, mut = sh('ls -l /tmp/mutation*dat 2>/dev/null | tail -3', check=False)
        note('saved mutation files in /tmp (newest): ' + ' | '.join(mut.strip().splitlines()))
        off = syslog_size()
        start('replay-ctl-4m', '4MiB', trace=False, wipe=False)
        lg = syslog_since(off)
        open(D + '/replay-ctl-4m.log', 'w').write(lg)
        rp = [l for l in lg.splitlines() if 'replay' in l.lower()]
        note('replay control log lines:\n  ' + '\n  '.join(h[:300] for h in rp[:10]))
        r, *_ = op('control readback 30', 'readback', '30')
        expect(f'replay control under 4 MiB: the node starts and readback 30 = {REPLAY_ROW} ({r.get("length")})', r.get('length') == REPLAY_ROW)
        finish(0)

    fail('unknown mode ' + mode)
except SystemExit:
    raise
except Exception as e:
    note(f'FAIL: exception {type(e).__name__}: {str(e)[:800]}')
    finish(1)
