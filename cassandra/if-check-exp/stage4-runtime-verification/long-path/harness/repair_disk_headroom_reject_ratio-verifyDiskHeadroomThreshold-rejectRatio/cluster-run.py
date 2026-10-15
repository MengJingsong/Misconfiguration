#!/usr/bin/env python3
"""Stage 4, cluster tier, repair_disk_headroom_reject_ratio-verifyDiskHeadroomThreshold-rejectRatio (case 9b-9e, amended 2026-10-15).
usage: cluster-run.py <label> [<label> ...]
  labels, in 9e order: setup | idle | sweep-p | sweep-k | types | valid | load | overshoot | down
Two nodes on this host from ~/cassandra-run1: N1 = 127.0.0.2 (JMX 7102, runs every repair), N2 = 127.0.0.3 (JMX 7103), RF 2,
one token each, cap data_disk_usage_max_disk_size = 1 GiB on both. The nodes stay up between labels; setup wipes and starts them.
Each label logs every command to $HDR_LOGS/<label>/session.log (default ~/stage4-logs/hdr/run1) and writes summary.txt
(EXPECTED lines), triggers.csv and, for overshoot, samples.csv. Exit 1: an instrument or set-up check failed (both nodes stopped).
The usage is set with a sparse pad file <N>/data/hdr-pad.bin (apparent bytes; no blocks), created only while a node runs."""
import csv, json, math, os, random, re, subprocess, sys, threading, time
from decimal import Decimal, ROUND_UP

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-run1')
HARNESS = os.path.dirname(os.path.abspath(__file__))
HDR = os.environ.get('HDR', HOME + '/stage4-hdr')
LOGROOT = os.environ.get('HDR_LOGS', HOME + '/stage4-logs/hdr/run1')
NODES = {'N1': ('127.0.0.2', 7102), 'N2': ('127.0.0.3', 7103)}
BYTEMAN = C + '/build/lib/jars/byteman-4.0.20.jar'
RS = 'org.apache.cassandra.db:type=RepairService'
GR = 'org.apache.cassandra.db:type=Guardrails'
ATTR = 'IncrementalRepairDiskHeadroomRejectRatio'
CAP = 1073741824
DELTA = 4194304
RATIOS = os.environ.get('HDR_RATIOS', '0.0,0.2,0.5,0.8').split(',')   # a subset is a shakedown, not a reading
REPAIR = 'repair -full hdr t'
# the check's own ERROR text has '(' after 'disk usage'; RepairCoordinator's 'Repair <id> failed: … disk usage above threshold' does not
NOT_STARTED = re.compile(r'merkle tree|Prepared AEService|\[Stream #|anticompact|snapshot', re.I)

SESSION = SUMMARY = TCSV = TCSV_F = None
n_exp = n_yes = 0


def open_label(label):
    global SESSION, SUMMARY, TCSV, TCSV_F
    d = f'{LOGROOT}/{label}'
    os.makedirs(d, exist_ok=True)
    SESSION = open(d + '/session.log', 'a')
    SUMMARY = open(d + '/summary.txt', 'w')
    TCSV_F = open(d + '/triggers.csv', 'w', newline='')
    TCSV = csv.writer(TCSV_F)
    TCSV.writerow(['label', 'trigger', 'knob_node', 'r', 'U0_plan', 'D', 'pad', 'u_plan', 'u_line', 'admit_lines', 'callers', 'exit',
                   'error_lines', 'nodetool_tail', 'not_started_lines', 'failure_cause', 'dir_changed'])
    return d


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
        SESSION.write(out[-6000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed rc={r.returncode}: {cmd}\n{out[-1200:]}')
    return r.returncode, out


def expect(desc, cond):
    global n_exp, n_yes
    n_exp += 1; n_yes += bool(cond)
    note(f'EXPECTED: {desc} — {"yes" if cond else "NO (recorded; the AI judges it in the results file)"}')
    return cond


# ---------------------------------------------------------------- nodes

def pid_of(node):
    f = f'{HDR}/{node}/cassandra.pid'
    try:
        pid = int(open(f).read().strip())
        return pid if 'CassandraDaemon' in open(f'/proc/{pid}/cmdline').read() else None
    except (OSError, ValueError):
        return None


def stop_node(node):
    if pid_of(node) is None:
        return
    remove_pad(node)
    sh(f'bin/nodetool -p {NODES[node][1]} stopdaemon', check=False, timeout=120)
    for _ in range(90):
        if pid_of(node) is None:
            break
        time.sleep(1)
    pid = pid_of(node)
    if pid is not None:
        log(f'{node} did not stop; kill -9 {pid}'); subprocess.run(['kill', '-9', str(pid)]); time.sleep(2)


def stop_all():
    for n in ('N2', 'N1'):
        stop_node(n)
    _, left = sh("ps -eo cmd | grep '[C]assandraDaemon' || true", check=False, quiet=True)
    if left.strip():
        log('WARNING: a CassandraDaemon is still running: ' + left[:300])


def fail(msg):
    note('FAIL: ' + msg)
    stop_all()
    sys.exit(1)


def start_node(node, extras=()):
    if pid_of(node) is not None:
        fail(f'{node} is already running')
    _, y = sh(f'{HARNESS}/make-node-yaml.sh {node} ' + ' '.join(extras))
    note(y.strip().splitlines()[-1][:700])
    N = f'{HDR}/{node}'
    env = dict(os.environ, CASSANDRA_CONF=N + '/conf', CASSANDRA_LOG_DIR=N + '/logs', MAX_HEAP_SIZE='2G',
               JVM_EXTRA_OPTS=f'-javaagent:{BYTEMAN}=script:{HARNESS}/headroom.btm -Dstage4.trace={N}/hdr.trace')
    env.pop('HEAP_NEWSIZE', None)
    sh(f'bin/cassandra -p {N}/cassandra.pid > {N}/stdout.txt 2>&1', env=env)
    time.sleep(4)
    if pid_of(node) is None:
        fail(f'{node} did not start; see {N}/stdout.txt')


def wait_up(node, want_un, timeout=300):
    port = NODES[node][1]
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pid_of(node) is None:
            fail(f'{node} died during start')
        _, st = sh(f'bin/nodetool -p {port} statusbinary', check=False, quiet=True)
        _, ns = sh(f'bin/nodetool -p {port} status', check=False, quiet=True)
        un = re.findall(r'^UN\s+(\S+)', ns, re.M)
        if re.search(r'^running\s*$', st, re.M) and len(un) >= want_un:
            note(f'{node} up: statusbinary running, UN {un} after {time.time() - t0:.0f} s')
            return
        time.sleep(3)
    fail(f'{node} not up after {timeout} s')


def jmx(port, *args):
    _, out = sh(f'java -cp {HDR}/jmxcls Jmx {port} ' + ' '.join(f"'{a}'" for a in args), check=False, timeout=60)
    return out.strip()


def get_ratio(node):
    m = re.search(ATTR + r'\|(\S+)', jmx(NODES[node][1], 'get', RS, ATTR))
    return m.group(1) if m else None


def set_ratio(node, r, expect_fail=False):
    out = jmx(NODES[node][1], 'setdouble', RS, ATTR, r)
    if expect_fail:
        return out
    back = get_ratio(node)
    note(f'KNOB {node} set {r} read back {back}')
    if back is None or float(back) != float(r):
        fail(f'{node}: ratio read back {back}, set {r} (invalid run)')
    return back


def flush(node):
    sh(f'bin/nodetool -p {NODES[node][1]} flush', timeout=180)


# ---------------------------------------------------------------- usage

def walk(path):
    """FileUtils.folderSize's rule: lstat size of every non-directory entry, no symlink followed (amendment (3))."""
    tot = 0
    try:
        it = os.scandir(path)
    except FileNotFoundError:
        return 0
    with it:
        for e in it:
            try:
                if e.is_dir(follow_symlinks=False):
                    tot += walk(e.path)
                else:
                    tot += e.stat(follow_symlinks=False).st_size
            except FileNotFoundError:
                pass
    return tot


def data_dir(node):
    return f'{HDR}/{node}/data'


def pad_path(node):
    return f'{data_dir(node)}/hdr-pad.bin'


def remove_pad(node):
    if os.path.exists(pad_path(node)):
        os.remove(pad_path(node))


def set_pad(node, U0):
    remove_pad(node)
    D = walk(data_dir(node))
    pad = U0 - D
    if pad < 0:
        fail(f'{node}: data directory already holds {D} > U0 {U0}')
    with open(pad_path(node), 'wb') as f:
        f.truncate(pad)
    after = walk(data_dir(node))
    log(f'PAD {node}: D={D} pad={pad} walk after={after} (U0 {U0})')
    return D, pad, after


def ceil5(x):
    return float(Decimal(x).quantize(Decimal('0.00001'), rounding=ROUND_UP))


def ufrac(U0):
    return ceil5(Decimal(U0) / Decimal(CAP))


def L_of(r):
    """L(r) = (1 - r) C rounded to the byte, as 9a's table (858,993,459 at 0.2; 214,748,365 at 0.8)."""
    return int(((Decimal(1) - Decimal(r)) * CAP).quantize(Decimal(1), rounding='ROUND_HALF_UP'))


# ---------------------------------------------------------------- logs

def size_of(p):
    try:
        return os.path.getsize(p)
    except OSError:
        return 0


def offsets():
    o = {}
    for n in NODES:
        for f in ('hdr.trace', 'logs/system.log', 'logs/debug.log'):
            p = f'{HDR}/{n}/{f}'
            o[(n, f)] = size_of(p)
    return o


def since(o, node, f):
    p = f'{HDR}/{node}/{f}'
    try:
        with open(p, errors='replace') as fh:
            fh.seek(o.get((node, f), 0))
            return fh.read()
    except OSError:
        return ''


def table_listing():
    out = {}
    for n in NODES:
        _, ls = sh(f'ls -l --time-style=+%s {data_dir(n)}/hdr/t-*/ 2>/dev/null | grep -v "^total" || true', check=False, quiet=True)
        out[n] = sorted(re.sub(r'\s+', ' ', l).split(' ', 4)[-1] for l in ls.splitlines() if l.strip())
    return out


def participates(node):
    _, out = sh(f'bin/cqlsh {NODES[node][0]} -e "SELECT id, preview_kind, failure_cause FROM system_views.repair_participates"', check=False, timeout=120)
    return out


# ---------------------------------------------------------------- one trigger

def trigger(label, name, knob, r, U0, cmd=REPAIR, want_admit=None, phase=''):
    """knob: the node holding the ratio and the pad ('N1' / 'N2' / None). U0: planned usage on that node, None = no pad."""
    for n in NODES:
        set_ratio(n, '0.0') if get_ratio(n) not in ('0.0',) else None
        remove_pad(n)
        flush(n)
    D = pad = after = None
    if knob:
        set_ratio(knob, r)
        if U0 is not None:
            D, pad, after = set_pad(knob, U0)
    u_plan = ufrac(U0) if U0 is not None else None
    before_dirs = table_listing()
    o = offsets()
    rc, out = sh(f'bin/nodetool -p 7102 {cmd}', check=False, timeout=900)
    time.sleep(2)
    tr = {n: since(o, n, 'hdr.trace').splitlines() for n in NODES}
    errs = {n: [l for l in since(o, n, 'logs/system.log').splitlines() if 'Rejecting incoming repair, disk usage (' in l] for n in NODES}
    dbg = {n: [l for l in since(o, n, 'logs/debug.log').splitlines() if NOT_STARTED.search(l)] for n in NODES}
    after_dirs = table_listing()
    m = re.search(r'Starting repair command #(\d+) \(([0-9a-f-]+)\)', out)
    rid = m.group(2) if m else None
    usage = {n: [(float(re.search(r'usage=(\S+)', l).group(1)), float(re.search(r'ratio=(\S+)', l).group(1))) for l in tr[n] if l.startswith('HDR usage')] for n in NODES}
    verdict = {n: [re.search(r'admit=(\w+)', l).group(1) == 'true' for l in tr[n] if l.startswith('HDR verdict')] for n in NODES}
    callers = {n: [re.search(r'caller=(\w+)', l).group(1) for l in tr[n] if l.startswith('HDR caller')] for n in NODES}
    fc = ''
    if knob == 'N2' and verdict['N2'] and not verdict['N2'][-1] and rid:
        pt = participates('N2')
        fc = ' | '.join(l.strip() for l in pt.splitlines() if rid in l)
    tail = ' / '.join(l.strip() for l in out.splitlines() if re.search(r'error|failed|finished|Rejecting|negative', l, re.I))[-600:]
    dir_changed = before_dirs != after_dirs
    rec = dict(name=name, knob=knob, r=r, U0=U0, D=D, pad=pad, u_plan=u_plan, usage=usage, verdict=verdict, callers=callers, rc=rc,
               errs=errs, dbg=dbg, tail=tail, fc=fc, rid=rid, dir_changed=dir_changed, out=out)
    TCSV.writerow([label, name, knob, r, U0, D, pad, u_plan, json.dumps(usage), json.dumps(verdict), json.dumps(callers), rc,
                   json.dumps({n: [e[e.find('[['):][:150] for e in v] for n, v in errs.items()}), tail[:300],
                   json.dumps({n: [l[:160] for l in v] for n, v in dbg.items()}), fc[:200], dir_changed])
    TCSV_F.flush()
    note(f'TRIGGER {phase}{name}: knob {knob} r={r} U0={U0} D={D} pad={pad} u_plan={u_plan} | usage {usage} verdict {verdict} callers {callers}'
         f' | nodetool rc={rc} id={rid} | ERROR lines N1 {len(errs["N1"])} N2 {len(errs["N2"])} | not-started lines N1 {len(dbg["N1"])} N2 {len(dbg["N2"])}'
         f' | dirs changed {dir_changed}' + (f' | participates: {fc}' if fc else ''))
    for n in NODES:
        for e in errs[n]:
            note(f'  ERROR {n}: {e[e.find("[["):][:200]}')
    note(f'  nodetool: {tail[:400]}')
    if knob:
        remove_pad(knob)
        set_ratio(knob, '0.0')
    return rec


def pct(x):
    return '%.2f' % (x * 100)


def judge(rec, arm, scen):
    """9a's per-trigger expectations for arms P and K."""
    r = float(rec['r']); knob = rec['knob']; other = 'N1' if knob == 'N2' else 'N2'
    tag = f'{arm} r={rec["r"]} {scen}'
    if scen == 'A':
        ok = (rec['rc'] == 0 and all(len(rec['verdict'][n]) == 1 and rec['verdict'][n][0] for n in NODES)
              and 'finished' in rec['out'] and not rec['errs']['N1'] and not rec['errs']['N2'])
        expect(f'{tag}: admitted (two HDR lines admit=true, nodetool rc 0 finished, no Rejecting line)', ok)
    else:
        u = rec['usage'][knob][0][0] if rec['usage'][knob] else None
        want_err = f'Rejecting incoming repair, disk usage ({pct(u)}%) above threshold ({pct(1 - r)}%)' if u is not None else '?'
        err_ok = len(rec['errs'][knob]) == 1 and want_err in rec['errs'][knob][0] and '[[repair #' in rec['errs'][knob][0] and not rec['errs'][other]
        started = rec['dbg']['N1'] or rec['dbg']['N2'] or rec['dir_changed']
        if knob == 'N2':
            ok = (rec['verdict']['N1'] == [True] and rec['verdict']['N2'] == [False] and rec['callers']['N2'] == ['participant']
                  and rec['rc'] != 0 and 'Got negative replies from endpoints [/127.0.0.3:7010]' in rec['out']
                  and 'Not enough disk headroom to perform repair' in rec['fc'])
        else:
            ok = (rec['verdict']['N1'] == [False] and rec['verdict']['N2'] == [] and rec['callers']['N1'] == ['coordinator']
                  and rec['rc'] != 0 and 'Rejecting incoming repair, disk usage above threshold' in rec['out'])
        expect(f'{tag}: refused by {knob} ({"participant" if knob == "N2" else "coordinator"}), verdict lines and nodetool text as 9a', ok)
        expect(f'{tag}: one ERROR line on {knob} only, "{want_err}"', err_ok)
        pe = '%.2f' % (rec['u_plan'] * 100)
        expect(f'{tag}: ERROR percentages {pe}% / {pct(1 - r)}% as planned (u within 0.0005 of plan)', u is not None and abs(u - rec['u_plan']) <= 0.0005)
        expect(f'{tag}: nothing started (no merkle/AEService/stream/snapshot/anticompaction line, table dirs unchanged)', not started)
    if rec['U0'] is not None:
        u = rec['usage'][knob][0][0] if rec['usage'][knob] else None
        expect(f'{tag}: operand u={u} within +/-0.0005 of plan {rec["u_plan"]}', u is not None and abs(u - rec['u_plan']) <= 0.0005)


# ---------------------------------------------------------------- labels

def l_setup():
    for n in NODES:
        if pid_of(n) is not None:
            fail(f'{n} already running')
    _, left = sh("ps -eo cmd | grep '[C]assandraDaemon' || true", check=False, quiet=True)
    if left.strip():
        fail('another CassandraDaemon is running: ' + left[:200])
    sh(f'rm -rf {HDR}/N1 {HDR}/N2 {HDR}/jmxcls && mkdir -p {HDR}/jmxcls && javac -d {HDR}/jmxcls {HARNESS}/Jmx.java')
    _, ts = sh(f'java -classpath {BYTEMAN}:build/classes/main:"build/lib/jars/*":"lib/*" org.jboss.byteman.check.TestScript {HARNESS}/headroom.btm', check=False)
    if 'TestScript: no errors' not in ts:
        fail('Byteman TestScript reported errors: ' + ts[-600:])
    note('INSTRUMENT Byteman TestScript: no errors')
    start_node('N1'); wait_up('N1', 1)
    start_node('N2'); wait_up('N2', 2)
    sh('bin/cqlsh 127.0.0.2 -e "CREATE KEYSPACE hdr WITH replication = {\'class\': \'SimpleStrategy\', \'replication_factor\': 2}; '
       'CREATE TABLE hdr.t (pk int PRIMARY KEY, v blob) WITH compression = {\'enabled\': \'false\'} AND '
       'compaction = {\'class\': \'SizeTieredCompactionStrategy\', \'enabled\': \'false\'};"')
    time.sleep(3)
    for n, (_, port) in NODES.items():
        g = jmx(port, 'get', RS, ATTR, GR, 'DataDiskUsageMaxDiskSize')
        note(f'INSTRUMENT jmx {n}: ' + g.replace('\n', ' ; '))
        if f'{ATTR}|0.0' not in g or 'DataDiskUsageMaxDiskSize|1073741824B' not in g:
            fail(f'{n}: ratio (0.0) or cap (1073741824B) read-back failed')
    _, df = sh(f'df -B1 --output=avail {HDR} | tail -1', check=False)
    avail = int(df.split()[-1])
    note(f'INSTRUMENT df avail {avail} B')
    if avail < 2 * 1024 ** 3:
        fail('less than 2 GiB free')
    rec = trigger('setup', 'instrument control', None, '0.0', None)
    ok = all(len(rec['usage'][n]) == 1 and rec['verdict'][n] == [True] for n in NODES) and rec['rc'] == 0
    for n in NODES:
        if rec['usage'][n]:
            D = walk(data_dir(n))
            note(f'INSTRUMENT {n}: usage line {rec["usage"][n][0][0]} vs walk D/C {D / CAP:.6f}')
            ok = ok and abs(rec['usage'][n][0][0] - D / CAP) <= 0.0005
    if not ok:
        fail('instrument control repair: expected one HDR usage line per node, admit=true, usage within 0.0005 of D/C')
    note('INSTRUMENT control repair: two HDR usage lines, admit=true, usage matches the walk')


def l_idle():
    o = offsets()
    time.sleep(30)
    lines = sum(len(since(o, n, 'hdr.trace').splitlines()) for n in NODES)
    expect('idle 30 s, ratio 0, no pad: no HDR line', lines == 0)


def l_sweep(label, knob):
    arm = 'P' if knob == 'N2' else 'K'
    for r in RATIOS:
        c = trigger(label, f'control before r={r}', None, '0.0', None, phase=f'{arm} ')
        expect(f'{arm} r={r} control: admitted', c['rc'] == 0 and all(c['verdict'][n] == [True] for n in NODES))
        L = L_of(r)
        a = trigger(label, f'A r={r}', knob, r, L - DELTA, phase=f'{arm} ')
        judge(a, arm, 'A')
        b = trigger(label, f'B r={r}', knob, r, L + DELTA, phase=f'{arm} ')
        judge(b, arm, 'B')


TYPES = [('incremental', 'repair hdr t', False), ('full -pr', 'repair -full -pr hdr t', False),
         ('preview -full', 'repair --preview -full hdr t', True), ('preview', 'repair --preview hdr t', True),
         ('validate', 'repair --validate hdr t', True), ('paxos-only', 'repair --paxos-only hdr t', False)]


def l_types():
    for knob in ('N2', 'N1'):
        U0 = L_of('0.5') + DELTA
        for name, cmd, preview in TYPES:
            rec = trigger('types', f'{name} on {knob}', knob, '0.5', U0, cmd=cmd, phase='T ')
            prefix = '[[preview repair #' if preview else '[[repair #'
            refused = (rec['verdict'][knob] == [False] and rec['rc'] != 0 and len(rec['errs'][knob]) == 1 and prefix in rec['errs'][knob][0])
            expect(f'T {name} refused by {knob}, log prefix {prefix}', refused)
            if name == 'incremental':
                expect(f'T incremental on {knob}: no anticompaction line', not any('anticompact' in l.lower() for n in NODES for l in rec['dbg'][n]))


def l_valid():
    stop_node('N2')
    start_node('N2', ['repair_disk_headroom_reject_ratio=1.5']); wait_up('N2', 2)
    v = get_ratio('N2')
    expect(f'V: node 2 started with yaml 1.5; JMX reads {v}', v == '1.5')
    o = offsets()
    rc, out = sh(f'bin/nodetool -p 7102 {REPAIR}', check=False, timeout=600)
    time.sleep(2)
    errs = [l for l in since(o, 'N2', 'logs/system.log').splitlines() if 'Rejecting incoming repair, disk usage (' in l]
    note(f'V repair: rc={rc} N2 ERROR {[e[e.find("[["):][:160] for e in errs]}')
    expect('V: repair with no pad refused by node 2, threshold printed (-50.00%)', rc != 0 and len(errs) == 1 and errs[0].endswith('above threshold (-50.00%)'))
    sf = set_ratio('N2', '1.5', expect_fail=True)
    note(f'V JMX write 1.5: {sf[:300]}')
    expect('V: JMX write of 1.5 fails with the range text', 'Value must be >= 0 and <= 1 for repair_disk_headroom_reject_ratio' in sf and get_ratio('N2') == '1.5')
    set_ratio('N2', '0.0')
    rc2, out2 = sh(f'bin/nodetool -p 7102 {REPAIR}', check=False, timeout=600)
    expect('V: after a JMX write of 0.0 the repair is admitted', rc2 == 0 and 'finished' in out2)
    stop_node('N2')
    start_node('N2'); wait_up('N2', 2)
    expect('V: node 2 restarted without the yaml line reads 0.0', get_ratio('N2') == '0.0')


def driver():
    lib = os.path.join(C, 'lib')
    import glob
    z = max(glob.glob(os.path.join(lib, 'cassandra-driver-internal-only-*.zip')))
    ver = os.path.splitext(os.path.basename(z))[0][len('cassandra-driver-internal-only-'):]
    sys.path.insert(0, os.path.join(z, 'cassandra-driver-' + ver))
    for p in ('pure_sasl-', 'wcwidth-', 'pyasyncore-'):
        zz = glob.glob(os.path.join(lib, p + '*.zip'))
        if zz:
            sys.path.insert(0, max(zz))


def table_bytes(node):
    _, out = sh(f'du -sb {data_dir(node)}/hdr/ 2>/dev/null | cut -f1', check=False, quiet=True)
    return int(out.strip() or 0)


def l_load():
    stop_node('N2')
    _, st = sh('bin/nodetool -p 7102 status', check=False)
    expect('O load: node 2 is DN on node 1', re.search(r'^DN\s+127\.0\.0\.3', st, re.M) is not None)
    driver()
    from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
    from cassandra.policies import WhiteListRoundRobinPolicy
    from cassandra.concurrent import execute_concurrent_with_args
    from cassandra import ConsistencyLevel
    prof = ExecutionProfile(load_balancing_policy=WhiteListRoundRobinPolicy(['127.0.0.2']), consistency_level=ConsistencyLevel.ONE, request_timeout=60)
    cl = Cluster(['127.0.0.2'], protocol_version=5, execution_profiles={EXEC_PROFILE_DEFAULT: prof})
    s = cl.connect()
    ps = s.prepare('INSERT INTO hdr.t (pk, v) VALUES (?, ?)')
    rnd = random.Random(42)
    rows = [(i, rnd.randbytes(65536)) for i in range(4096)]
    res = execute_concurrent_with_args(s, ps, rows, concurrency=16, raise_on_first_error=True)
    cl.shutdown()
    note(f'O load: {len(res)} rows of 65,536 random bytes written at ONE to node 1')
    sh('bin/nodetool -p 7102 flush hdr t', timeout=300)
    b1 = table_bytes('N1')
    note(f'O load: node 1 hdr directory {b1} B (du -sb)')
    expect('O load: node 1 holds 268.4 to 269.5 MB', 268.4e6 <= b1 <= 269.5e6)
    _, ls2 = sh(f'ls {data_dir("N2")}/hdr/t-*/ 2>/dev/null | grep -c Data.db || true', check=False)
    expect('O load: node 2 holds no hdr.t Data.db', ls2.strip() in ('', '0'))
    start_node('N2'); wait_up('N2', 2)
    _, ls3 = sh(f'ls {data_dir("N2")}/hdr/t-*/ 2>/dev/null | grep -c Data.db || true', check=False)
    expect('O load: node 2 still holds no hdr.t Data.db after its restart (no hints)', ls3.strip() in ('', '0'))


def accepting(text):
    return [int(m) for m in re.findall(r'Accepting incoming files newStreamTotalSSTables=\d+ newStreamTotalBytes=(\d+)', text)]


def l_overshoot(d):
    o = offsets()
    rc, out = sh(f'bin/nodetool -p 7102 repair --preview -full hdr t', check=False, timeout=900)
    time.sleep(2)
    sp = accepting(since(o, 'N2', 'logs/system.log'))
    est = re.findall(r'Total estimated streaming: (.*)', out + since(o, 'N1', 'logs/system.log'))
    note(f'O preview: rc={rc} N2 Accepting {sp} ; estimated {est[:2]}')
    S_prv = sp[0] if sp else None
    expect('O preview: out of sync, node 2 logs Accepting with S_prv in 268.4-269.5 MB', S_prv is not None and 268.4e6 <= S_prv <= 269.5e6)
    for n in NODES:
        flush(n)
    set_ratio('N2', '0.5')
    L = L_of('0.5'); U0 = L - DELTA
    D, pad, after = set_pad('N2', U0)
    note(f'O: node 2 D={D} pad={pad} walk={after} (U0 {U0})')
    n1_before = walk(data_dir('N1'))
    samples = open(d + '/samples.csv', 'w', newline='')
    sw = csv.writer(samples); sw.writerow(['ms', 'walk_N2', 'du_sb_N2_hdr', 'du_sB1_N2_hdr', 'walk_N1', 'hdr_lines_N2'])
    stop = threading.Event()
    o2 = offsets()

    def sampler():
        while not stop.is_set():
            w2 = walk(data_dir('N2'))
            r1 = subprocess.run(f'du -sb {data_dir("N2")}/hdr; du -sB1 {data_dir("N2")}/hdr', shell=True, capture_output=True, text=True).stdout.split()
            hl = len([l for l in since(o2, 'N2', 'hdr.trace').splitlines() if l.startswith('HDR usage')])
            sw.writerow([int(time.time() * 1000), w2, r1[0] if r1 else '', r1[2] if len(r1) > 2 else '', walk(data_dir('N1')), hl]); samples.flush()
            stop.wait(1.0)
    th = threading.Thread(target=sampler, daemon=True); th.start()
    rc, out = sh(f'bin/nodetool -p 7102 {REPAIR}', check=False, timeout=1800)
    time.sleep(8)
    stop.set(); th.join(5); samples.close()
    tr2 = since(o2, 'N2', 'hdr.trace').splitlines(); tr1 = since(o2, 'N1', 'hdr.trace').splitlines()
    S = accepting(since(o2, 'N2', 'logs/system.log'))
    U1 = walk(data_dir('N2')); n1_after = walk(data_dir('N1'))
    u2 = [float(re.search(r'usage=(\S+)', l).group(1)) for l in tr2 if l.startswith('HDR usage')]
    note(f'O repair: rc={rc}; N2 HDR usage {u2}; N1 HDR lines {len([l for l in tr1 if l.startswith("HDR usage")])}; N2 Accepting {S}; '
         f'U0 {U0} -> U1 {U1} (growth {U1 - U0}); u1 = {U1 / CAP:.5f}; overshoot U1 - L = {U1 - L}; node 1 walk {n1_before} -> {n1_after}')
    expect('O: admitted at u = 0.49610 +/- 0.0005 (one HDR usage line on node 2, admit=true)', rc == 0 and len(u2) == 1 and abs(u2[0] - 0.49610) <= 0.0005)
    expect('O: node 2 Accepting S = S_prv', len(S) == 1 and S_prv is not None and S[0] == S_prv)
    if S:
        expect(f'O: node 2 grew by S +/- 1 MiB (growth {U1 - U0}, S {S[0]})', abs((U1 - U0) - S[0]) <= 1048576)
        expect('O: node 2 ends above L (U1 in 801.1-802.2 MB; u1 0.7461-0.7471)', U1 > L and 801.1e6 <= U1 <= 802.2e6)
    rows = list(csv.reader(open(d + '/samples.csv')))[1:]
    crossed = [r for r in rows if int(r[1]) > L]
    expect('O: the sampler shows usage crossing L during the repair with no further HDR usage line on node 2', bool(crossed) and all(int(r[5]) <= 1 for r in rows))
    expect('O: node 1 data directory changed by < 1 MiB', abs(n1_after - n1_before) < 1048576)
    # the re-checks, pad still in place
    o3 = offsets()
    rc3, out3 = sh(f'bin/nodetool -p 7102 {REPAIR}', check=False, timeout=900)
    time.sleep(2)
    e3 = [l for l in since(o3, 'N2', 'logs/system.log').splitlines() if 'Rejecting incoming repair, disk usage (' in l]
    note(f'O re-check at 0.5: rc={rc3} ERROR {[e[e.find("[["):][:160] for e in e3]}')
    expect('O re-check at 0.5 refused: ERROR (74.6x%) above threshold (50.00%)', rc3 != 0 and len(e3) == 1 and re.search(r'disk usage \(74\.6\d%\) above threshold \(50\.00%\)', e3[0]) is not None)
    set_ratio('N2', '0.2')
    rc4, out4 = sh(f'bin/nodetool -p 7102 {REPAIR}', check=False, timeout=900)
    expect('O re-check at 0.2 admitted', rc4 == 0 and 'finished' in out4)
    set_ratio('N2', '0.0')
    remove_pad('N2')


def l_down():
    for n in NODES:
        remove_pad(n)
    stop_all()
    for n in NODES:
        sh(f'cp -r {HDR}/{n}/logs {LOGROOT}/down/{n}-logs; cp {HDR}/{n}/hdr.trace {LOGROOT}/down/{n}-hdr.trace; cp {HDR}/{n}/conf/cassandra.yaml {LOGROOT}/down/{n}-cassandra.yaml', check=False)
    _, left = sh("ps -eo cmd | grep -c '[C]assandraDaemon' || true", check=False)
    note(f'down: CassandraDaemon processes left: {left.strip()}')


def main():
    labels = sys.argv[1:]
    for label in labels:
        d = open_label(label)
        global n_exp, n_yes
        n_exp = n_yes = 0
        note(f'LABEL {label} start {time.strftime("%F %T %Z")}; harness md5 ' +
             subprocess.run(f'cd {HARNESS} && md5sum cluster-run.py headroom.btm make-node-yaml.sh Jmx.java | cut -c1-12 | tr "\\n" " "', shell=True, capture_output=True, text=True).stdout)
        try:
            {'setup': l_setup, 'idle': l_idle, 'sweep-p': lambda: l_sweep('sweep-p', 'N2'), 'sweep-k': lambda: l_sweep('sweep-k', 'N1'),
             'types': l_types, 'valid': l_valid, 'load': l_load, 'overshoot': lambda: l_overshoot(d), 'down': l_down}[label]()
        except SystemExit:
            raise
        except Exception as e:
            import traceback
            note(f'FAIL (exception) in {label}: {e!r}'); log(traceback.format_exc())
            stop_all(); sys.exit(1)
        note(f'DONE {label} expected {n_yes}/{n_exp} yes')


main()
