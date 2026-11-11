#!/usr/bin/env python3
"""Stage 4, cluster tier, SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS-materializeKeysAndCloseSource-MAX_MATERIALIZED_KEYS (case 9b-9e,
amended 2026-10-15).
usage: cluster-run.py load | value <1000|4000|16000|64000|0|2147483647> | down
  load        wipe the node's directories, start at the default, create and load ks.t and ks.far (load.py), check counts and
              SSTables (t: 4, far: 1), stop. Once per run.
  value <L>   restart with -Dcassandra.sai.vector_search.max_materialized_keys=<L> (16000: no -D, the default) and run 9e's
              scenarios for it: control, A (single + 8 held at point b), B (traced L + 1, then 8 held at point a at min(4L, N)),
              C2 on ks.far at 1000 / 16000 / 64000 (single + 8 held at point c); at 0 and 2147483647 the C1 steps instead.
  down        stop the node.
One node from ~/cassandra-run1 with its own CASSANDRA_CONF and directories under ~/stage4-mmk (make-node-yaml.sh): pc57 is shared
with another session's node, so a start refuses to run while any CassandraDaemon is up. Every command is logged to
<logroot>/<run>/<label>/session.log (logroot ~/stage4-logs/mmk, run $MMK_RUN or run1); writes summary.txt (EXPECTED lines),
histo.csv, mat.trace (Byteman), histo-*.txt and a copy of system.log. Exit 1: an instrument, control or set-up check failed (invalid
run). The node is stopped and the hold flags removed on any exit."""
import csv, json, os, re, subprocess, sys, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-run1')
HARNESS = os.path.dirname(os.path.abspath(__file__))
BM = C + '/build/lib/jars/byteman-4.0.20.jar'
ROOT = HOME + '/stage4-mmk'
RUN = os.environ.get('MMK_RUN', 'run1')
LOGROOT = os.environ.get('STAGE4_LOGROOT', HOME + '/stage4-logs/mmk')
VALUES = [1000, 4000, 16000, 64000, 0, 2147483647]
DEFAULT = 16000
N_T, N_FAR, M_FAR, Q, K = 200000, 50000, 16001, 8, 10
C2_VALUES = (1000, 16000, 64000)
HOLD_MS = 15000
FLAGS = ['/tmp/mmk-hold-a', '/tmp/mmk-hold-b', '/tmp/mmk-hold-c']
SPK = 'org.apache.cassandra.index.sai.utils.PrimaryKey$Factory$SkinnyPrimaryKey'
HKEYS = ['epoch_ms', 'jcmd_ms', 'spk_inst', 'spk_bytes', 'bdk_inst', 'bdk_bytes', 'tok_inst', 'tok_bytes', 'hbb_inst', 'hbb_bytes',
         'B_inst', 'B_bytes', 'heap_used_kb']
HISTO_RE = re.compile(' '.join(k + r'=(\d+)' for k in HKEYS))

mode = sys.argv[1] if len(sys.argv) > 1 else 'down'
if mode == 'value':
    L = int(sys.argv[2])
    if L not in VALUES:
        sys.exit(f'unknown value {L}')
    LABEL = 'default' if L == DEFAULT else str(L)
elif mode in ('load', 'down'):
    L, LABEL = DEFAULT, mode
else:
    sys.exit(__doc__)
D = f'{LOGROOT}/{RUN}/{LABEL}'
os.makedirs(D, exist_ok=True)
SESSION = open(D + '/session.log', 'a')
SUMMARY = open(D + '/summary.txt', 'w')
TRACE = D + '/mat.trace'
HFILE = open(D + '/histo.csv', 'a', newline='')
HCSV = csv.writer(HFILE)
PID = None


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


def node_env():
    env = dict(os.environ, CASSANDRA_CONF=ROOT + '/conf', CASSANDRA_LOG_DIR=ROOT + '/logs')
    return env


def own_pid():
    """our node: a CassandraDaemon whose command line names our CASSANDRA_CONF"""
    for p in daemon_pids():
        try:
            if ROOT + '/conf' in open(f'/proc/{p}/cmdline').read():
                return p
        except OSError:
            pass
    return None


def stop_node(tag='end'):
    """stops only our own node (PID); never another session's"""
    global PID
    PID = PID or own_pid()
    if PID and os.path.exists(f'/proc/{PID}'):
        sh('bin/nodetool stopdaemon', check=False, timeout=120, env=node_env())
        for _ in range(90):
            if not os.path.exists(f'/proc/{PID}'):
                break
            time.sleep(1)
        if os.path.exists(f'/proc/{PID}'):
            log(f'kill -9 {PID}'); subprocess.run(['kill', '-9', PID])
            time.sleep(3)
    if os.path.exists(ROOT + '/logs/system.log'):
        sh(f'cp {ROOT}/logs/system.log {D}/system.{tag}.log', check=False)


def clear_flags():
    for f in FLAGS:
        if os.path.exists(f):
            os.remove(f)


def finish(rc):
    clear_flags()
    stop_node()
    note(f'node stopped; our pid {PID} alive: {bool(PID and os.path.exists(f"/proc/{PID}"))}; daemons on host: {len(daemon_pids())}')
    HFILE.flush()
    sys.exit(rc)


def fail(msg):
    note('FAIL: ' + msg)
    finish(1)


def expect(desc, cond):
    note(f'EXPECTED: {desc} — {"yes" if cond else "NO (recorded; the AI judges it in the results file)"}')
    return cond


def within(got, want):
    return abs(got - want) <= 0.01 * want + 100


# ------------------------------------------------------------------ observables

def trace_lines():
    if not os.path.exists(TRACE):
        return []
    return [l.rstrip('\n') for l in open(TRACE, errors='replace')]


def since(n0):
    return trace_lines()[n0:]


def field(line, name):
    m = re.search(r'\b' + name + r'=(-?\d+|null)', line or '')
    if not m:
        return None
    return None if m.group(1) == 'null' else int(m.group(1))


def kinds(lines):
    k = {'refuse': [], 'exit': [], 'ann': [], 'hybrid': [], 'pairs': [], 'processed': [], 'limit': [], 'hold': []}
    for l in lines:
        if l.startswith('mat refuse'):
            k['refuse'].append(l)
        elif l.startswith('mat exit'):
            k['exit'].append(l)
        elif l.startswith('ann '):
            k['ann'].append(l)
        elif l.startswith('hybrid '):
            k['hybrid'].append(l)
        elif l.startswith('pairs '):
            k['pairs'].append(l)
        elif l.startswith('processed='):
            k['processed'].append(l)
        elif l.startswith('limit='):
            k['limit'].append(l)
        elif l.startswith('hold '):
            k['hold'].append(l)
    return k


def histo(label):
    rc, out = sh(f'{HARNESS}/histo.sh {PID} {D}/histo-{label}.txt', check=False, timeout=300)
    m = HISTO_RE.search(out)
    if rc != 0 or not m:
        fail(f'histo.sh failed or unparsable ({label}): {out[-300:]}')
    v = dict(zip(HKEYS, map(int, m.groups())))
    HCSV.writerow([RUN, LABEL, L, label] + [v[k] for k in HKEYS]); HFILE.flush()
    note(f'histo {label}: SkinnyPrimaryKey {v["spk_inst"]} ({v["spk_bytes"]} B); BufferDecoratedKey {v["bdk_inst"]}; LongToken '
         f'{v["tok_inst"]}; HeapByteBuffer {v["hbb_inst"]}; [B {v["B_inst"]} / {v["B_bytes"]} B; heap used {v["heap_used_kb"]} KB; '
         f'jcmd {v["jcmd_ms"]} ms')
    return v


def client(*args, timeout=420):
    log('+ query.py ' + ' '.join(args))
    r = subprocess.run([sys.executable, f'{HARNESS}/query.py', *args], capture_output=True, text=True, timeout=timeout)
    line = (r.stdout.strip().splitlines() or ['ERR {}'])[-1]
    SESSION.write(line[:4000] + '\n' + r.stderr[-800:] + '\n'); SESSION.flush()
    return parse_client(line)


def parse_client(line):
    ok = line.startswith('OK ')
    try:
        body = json.loads(line.split(' ', 1)[1])
    except Exception:  # noqa: BLE001
        body = {'raw': line[:1500]}
    body['ok'] = ok
    return body


def jmx_partition_reads():
    rc, out = sh(f"java -cp {ROOT}/jmxcls Jmx 7199 query 'org.apache.cassandra.metrics:type=StorageAttachedIndex,keyspace=ks,"
                 f"table=far,scope=TableQueryMetrics,*' Count", check=False, timeout=60)
    for l in out.splitlines():
        if 'name=TotalPartitionReads' in l:
            try:
                return int(l.rsplit('|', 1)[1])
            except ValueError:
                return None
    return None


# ------------------------------------------------------------------ node

def wait_up(timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if not os.path.exists(f'/proc/{PID}'):
            return 'exited'
        _, st = sh('bin/nodetool statusbinary', check=False, timeout=60, env=node_env())
        if 'running' in st:
            _, ns = sh('bin/nodetool status', check=False, timeout=60, env=node_env())
            if re.search(r'^UN', ns, re.M):
                return 'up'
        time.sleep(5)
    return 'timeout'


def start(limit, wipe):
    global PID
    others = daemon_pids()
    if others:
        fail(f'a CassandraDaemon is already running on the host ({others}); pc57 is shared: wait for it to stop')
    clear_flags()
    note(sh(f'{HARNESS}/make-node-yaml.sh {RUN}-{LABEL} {ROOT}')[1].strip().replace('\n', ' | '))
    sh(f'cp {ROOT}/conf/cassandra.yaml {D}/cassandra.yaml')
    if wipe:
        sh(f'rm -rf {ROOT}/data {ROOT}/commitlog {ROOT}/hints {ROOT}/saved_caches {ROOT}/cdc_raw {ROOT}/logs')
    sh(f'mkdir -p {ROOT}/logs {ROOT}/helper/classes {ROOT}/jmxcls && javac -d {ROOT}/helper/classes {HARNESS}/Mmk.java && '
       f'jar cf {ROOT}/helper/mmk.jar -C {ROOT}/helper/classes . && javac -d {ROOT}/jmxcls {HARNESS}/Jmx.java')
    env = dict(node_env(), MAX_HEAP_SIZE='4G')
    env.pop('HEAP_NEWSIZE', None)
    prop = '' if limit == DEFAULT else f'-Dcassandra.sai.vector_search.max_materialized_keys={limit} '
    env['JVM_EXTRA_OPTS'] = (prop + f'-Dstage4.mat.out={TRACE} -Dstage4.hold.ms={HOLD_MS} -Xbootclasspath/a:{ROOT}/helper/mmk.jar '
                             f'-javaagent:{BM}=script:{HARNESS}/mat-trace.btm,script:{HARNESS}/hold.btm,listener:true')
    note('JVM_EXTRA_OPTS=' + env['JVM_EXTRA_OPTS'])
    pid_file = f'{D}/cassandra.pid'
    if os.path.exists(pid_file):
        os.remove(pid_file)
    sh(f'bin/cassandra -p {pid_file} > {D}/startup.log 2>&1', env=env)
    for _ in range(60):
        if os.path.exists(pid_file) and open(pid_file).read().strip():
            break
        time.sleep(0.5)
    PID = open(pid_file).read().strip()
    time.sleep(2)
    args = open(f'/proc/{PID}/cmdline').read().split('\0')
    open(f'{D}/jvm-args.txt', 'w').write('\n'.join(args))
    if '-Xmx4G' not in args or not any('UseG1GC' in a for a in args):
        fail('JVM lacks -Xmx4G or G1')
    if not any('byteman-4.0.20.jar' in a for a in args):
        fail('JVM lacks the Byteman agent')
    if prop and prop.strip() not in args:
        fail('JVM lacks the property')
    if not prop and any('max_materialized_keys' in a for a in args):
        fail('default run carries the property')
    st = wait_up(240)
    note(f'node {PID}: {st}')
    if st != 'up':
        fail('node did not come up')
    _, out = sh(f'jcmd {PID} VM.system_properties', check=False, timeout=60)
    m = re.search(r'cassandra\.sai\.vector_search\.max_materialized_keys=(\S+)', out)
    got = m.group(1) if m else None
    note(f'VM.system_properties: cassandra.sai.vector_search.max_materialized_keys={got} (set {prop.strip() or "none: default"})')
    if (prop and got != str(limit)) or (not prop and got is not None):
        fail('the property read back differs from the value set: invalid run (9a)')


def head():
    note(f'run {RUN} label {LABEL} (L = {L}) on {os.uname().nodename}; {time.strftime("%F %T %Z")}; epoch ms {int(time.time() * 1000)}')
    note('clone: ' + sh('git rev-parse HEAD')[1].strip() + ' ' + sh('git describe --tags')[1].strip())
    note('harness md5: ' + sh(f'cd {HARNESS} && md5sum *.java *.btm *.py *.sh | tr "\\n" ";"')[1].strip())
    if os.path.exists(TRACE):
        os.rename(TRACE, TRACE + f'.{int(time.time())}.old')


# ------------------------------------------------------------------ scenarios

def single(tag, table, m, trace=False, ann_only=False):
    n0 = len(trace_lines())
    args = ['--table', table, '--m', str(m)] + (['--trace'] if trace else []) + (['--ann-only'] if ann_only else [])
    r = client(*args)
    time.sleep(1)
    k = kinds(since(n0))
    q = r.get('queries', [{}])[0]
    note(f'{tag}: client {"OK" if r["ok"] else "ERR"} rows={q.get("rows")} bad={q.get("bad")} max_i={q.get("max_i")} '
         f'err={q.get("err")} secs={r.get("secs")}; lines: refuse={k["refuse"]} exit={k["exit"]} ann={len(k["ann"])} '
         f'hybrid={k["hybrid"]} pairs={[field(x, "cap") for x in k["pairs"]]} processed={k["processed"]}')
    if trace:
        ev = r.get('trace_events', [])
        open(f'{D}/trace-events-{tag.replace(" ", "_")}.txt', 'w').write('\n'.join(ev))
        r['trace_hit'] = [e for e in ev if 'Switching to ORDER BY' in e]
        note(f'{tag}: trace events {len(ev)}; switch events: {r["trace_hit"]}')
    return r, k


def held(tag, point, table, m, idle):
    n0 = len(trace_lines())
    open(f'/tmp/mmk-hold-{point}', 'w').close()
    log(f'+ query.py --table {table} --m {m} --q {Q} &  (hold point {point})')
    p = subprocess.Popen([sys.executable, f'{HARNESS}/query.py', '--table', table, '--m', str(m), '--q', str(Q)],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    t0 = time.time()
    starts = []
    while time.time() - t0 < 300:
        k = kinds(since(n0))
        starts = [x for x in k['hold'] if x.startswith(f'hold start {point}')]
        ends = [x for x in k['hold'] if x.startswith(f'hold end {point}')]
        if len(starts) >= Q or ends or p.poll() is not None:
            break
        time.sleep(0.2)
    ends_before = [x for x in kinds(since(n0))['hold'] if x.startswith(f'hold end {point}')]
    note(f'{tag}: {len(starts)} hold starts at point {point} after {time.time() - t0:.1f} s; hold ends before the histogram: '
         f'{len(ends_before)}')
    v = None
    if len(starts) == Q and not ends_before:
        v = histo(f'{tag.replace(" ", "_")}')
        ends_after = [x for x in kinds(since(n0))['hold'] if x.startswith(f'hold end {point}')]
        note(f'{tag}: hold ends by the end of the histogram: {len(ends_after)} (0 = all {Q} still held)')
        if ends_after:
            v = None
    os.remove(f'/tmp/mmk-hold-{point}')
    o, e = p.communicate(timeout=400)
    line = (o.strip().splitlines() or ['ERR {}'])[-1]
    SESSION.write(line[:4000] + '\n' + e[-800:] + '\n'); SESSION.flush()
    r = parse_client(line)
    time.sleep(1)
    k = kinds(since(n0))
    note(f'{tag}: client {"OK" if r["ok"] else "ERR"} rows={[q.get("rows") for q in r.get("queries", [])]} '
         f'bad={sum(q.get("bad") or 0 for q in r.get("queries", []))} errs={[q.get("err") for q in r.get("queries", []) if q.get("err")]}; '
         f'refuse sizes={[field(x, "size") for x in k["refuse"]]} exit returned={[field(x, "returned") for x in k["exit"]]} '
         f'ann={len(k["ann"])} hybrid sizes={[field(x, "size") for x in k["hybrid"]]} '
         f'processed={[field(x, "processed") for x in k["processed"]]} reads={[field(x, "reads") for x in k["processed"]]}')
    if v is None:
        fail(f'{tag}: the {Q} queries were not all held at point {point} during the histogram (instrument)')
    d = {c: v[c + '_inst'] - idle[c + '_inst'] for c in ('spk', 'bdk', 'tok', 'hbb', 'B')}
    d['bytes5'] = sum(v[c + '_bytes'] - idle[c + '_bytes'] for c in ('spk', 'bdk', 'tok', 'hbb', 'B'))
    note(f'{tag}: change from idle: SkinnyPrimaryKey {d["spk"]:+d}, BufferDecoratedKey {d["bdk"]:+d}, LongToken {d["tok"]:+d}, '
         f'HeapByteBuffer {d["hbb"]:+d}, [B {d["B"]:+d}; five-class bytes {d["bytes5"]:+d}')
    return r, k, d


def control_and_idle():
    r, k = single('control ANN-only', 't', 0, ann_only=True)
    q = r.get('queries', [{}])[0]
    if not (q.get('rows') == K and not k['refuse'] and not k['exit'] and len(k['ann']) == 1 and not k['hybrid']):
        fail('control ANN-only query: want 10 rows, no mat line, one ann line (9e step 1, rec. 3)')
    expect('control: ANN-only query returns 10 rows with no mat line and one ann line', True)


def first_limit_line():
    lim = kinds(trace_lines())['limit']
    note(f'limit lines: {lim}')
    if len(lim) != 1 or field(lim[0], 'limit') != L:
        fail(f'the trace start-up line does not read limit={L} (9b "Confirm it took effect"): invalid run')


def check_single(tag, r, k, m, want_refuse):
    q = r.get('queries', [{}])[0]
    one = len(k['exit']) == 1
    expect(f'{tag}: exactly one mat exit line (one command per query)', one)
    expect(f'{tag}: {K} rows, each with i <= {m}', q.get('rows') == K and q.get('bad') == 0)
    if want_refuse:
        want = max(L + 1, 1) if L < 2 ** 31 - 1 else None
        ok = (len(k['refuse']) == 1 and field(k['refuse'][0], 'size') == want and field(k['refuse'][0], 'count') == want
              and one and field(k['exit'][0], 'returned') is None and 'returned=null' in k['exit'][0]
              and len(k['ann']) == 1 and not k['hybrid'])
        expect(f'{tag}: refusal with size = count = {want}, returned null, one ann line, no hybrid line', ok)
    else:
        ok = (not k['refuse'] and one and field(k['exit'][0], 'returned') == m and len(k['hybrid']) == 1
              and field(k['hybrid'][0], 'size') == m and not k['ann'])
        expect(f'{tag}: no refusal, returned = hybrid size = {m}, no ann line', ok)
    return ok


def value_run():
    head()
    start(L, wipe=False)
    if L in (0, 2 ** 31 - 1):
        return c1_run()
    control_and_idle()
    # scenario A, single
    r, k = single('A single', 't', L)
    first_limit_line()
    check_single('A single M=L', r, k, L, False)
    caps = [field(x, 'cap') for x in k['pairs']]
    expect(f'A single: 4 pairs lines, each cap >= {L - 50} (derived, §6a step 4)', len(caps) == 4 and all(c >= L - 50 for c in caps))
    idle = histo('idle')
    # scenario A, held at b
    r, k, d = held('A held', 'b', 't', L, idle)
    expect(f'A held: client OK (8 x {K} rows, i <= {L})', r['ok'])
    expect(f'A held: 8 lists returned = {L}', [field(x, 'returned') for x in k['exit']] == [L] * Q)
    expect(f'A held: SkinnyPrimaryKey change {d["spk"]:+d} = Q x L = {Q * L} within 1 % + 100', within(d['spk'], Q * L))
    expect(f'A held: BufferDecoratedKey change {d["bdk"]:+d} = Q x L = {Q * L} within 1 % + 100', within(d['bdk'], Q * L))
    # scenario B, traced L + 1
    r, k = single('B traced', 't', L + 1, trace=True)
    check_single('B traced M=L+1', r, k, L + 1, True)
    expect(f'B traced: the trace event "WHERE clause generated more than {L} rows" is present', any(
        f'generated more than {L} rows' in e for e in r.get('trace_hit', [])))
    # scenario B, held at a
    mb = min(4 * L, N_T)
    r, k, d = held('B held', 'a', 't', mb, idle)
    expect(f'B held: client OK (8 x {K} rows, i <= {mb})', r['ok'])
    expect(f'B held: 8 refusals with size {L + 1}, 8 ann lines, no hybrid', [field(x, 'size') for x in k['refuse']] == [L + 1] * Q
           and len(k['ann']) == Q and not k['hybrid'])
    expect(f'B held: SkinnyPrimaryKey change {d["spk"]:+d} = Q x (L + 1) = {Q * (L + 1)} within 1 % + 100', within(d['spk'], Q * (L + 1)))
    expect(f'B held: BufferDecoratedKey change {d["bdk"]:+d} = Q x (L + 1) = {Q * (L + 1)} within 1 % + 100', within(d['bdk'], Q * (L + 1)))
    if L in C2_VALUES:
        c2_run(idle)
    finish(0)


def c2_run(idle):
    p0 = jmx_partition_reads()
    r, k = single('C2 single', 'far', M_FAR)
    p1 = jmx_partition_reads()
    note(f'C2 single: TotalPartitionReads (side reading) before {p0} after {p1}')
    pr = k['processed'][0] if len(k['processed']) == 1 else None
    reads, processed = field(pr, 'reads'), field(pr, 'processed')
    q = r.get('queries', [{}])[0]
    expect(f'C2 single: {K} rows, each with i <= {M_FAR}', q.get('rows') == K and q.get('bad') == 0)
    if L < M_FAR:
        check_single(f'C2 single L={L}', r, k, M_FAR, True)
        lo = int(0.9 * (N_FAR - M_FAR))
        expect(f'C2 single: reads={reads} between 0.9 x (N - M) = {lo} and N = {N_FAR}', reads is not None and lo <= reads <= N_FAR)
        expect(f'C2 single: processed={processed} equals reads within 10', reads is not None and processed is not None
               and abs(processed - reads) <= 10)
    else:
        check_single(f'C2 single L={L}', r, k, M_FAR, False)
        expect(f'C2 single: reads={reads} <= 20', reads is not None and reads <= 20)
    r, k, d = held('C2 held', 'c', 'far', M_FAR, idle)
    expect(f'C2 held: client OK (8 x {K} rows, i <= {M_FAR})', r['ok'])
    if L < M_FAR:
        lo = int(0.9 * Q * (N_FAR - M_FAR))
        expect(f'C2 held: SkinnyPrimaryKey change {d["spk"]:+d} >= 0.9 x Q x (N - M) = {lo}, above Q x M = {Q * M_FAR}',
               d['spk'] >= lo and d['spk'] > Q * M_FAR)
    else:
        note(f'C2 held at L={L} (list plan): SkinnyPrimaryKey change {d["spk"]:+d} (recorded; 9a predicts no refusal and '
             f'<= 20 reads only)')


def c1_run():
    control_and_idle()
    if L == 0:
        r, k = single('C1 L=0', 't', 5)
        first_limit_line()
        check_single('C1 L=0 M=5', r, k, 5, True)
        histo('idle')
    else:
        r, k = single('C1 L=MAX', 't', N_T)
        first_limit_line()
        check_single(f'C1 L=MAX M={N_T}', r, k, N_T, False)
        idle = histo('idle')
        r, k, d = held('C1 held', 'b', 't', N_T, idle)
        expect(f'C1 held: client OK', r['ok'])
        expect(f'C1 held: 8 lists returned = {N_T}', [field(x, 'returned') for x in k['exit']] == [N_T] * Q)
        expect(f'C1 held: SkinnyPrimaryKey change {d["spk"]:+d} = Q x M = {Q * N_T} within 1 % + 100', within(d['spk'], Q * N_T))
        expect(f'C1 held: BufferDecoratedKey change {d["bdk"]:+d} = Q x M = {Q * N_T} within 1 % + 100', within(d['bdk'], Q * N_T))
    finish(0)


def load_run():
    head()
    start(DEFAULT, wipe=True)
    log('+ load.py')
    r = subprocess.run([sys.executable, f'{HARNESS}/load.py'], capture_output=True, text=True, timeout=3600)
    line = (r.stdout.strip().splitlines() or ['ERR'])[-1]
    SESSION.write(line[:4000] + '\n' + r.stderr[-2000:] + '\n'); SESSION.flush()
    note('load: ' + line[:600])
    if not line.startswith('OK '):
        fail('load failed')
    body = json.loads(line[3:])
    expect(f'load: count(*) t = {N_T}, far = {N_FAR}', body['count_t'] == N_T and body['count_far'] == N_FAR)
    sh(f'bin/nodetool flush ks', env=node_env())
    for t, want in (('t', 4), ('far', 1)):
        _, out = sh(f'ls {ROOT}/data/ks/{t}-*/ | grep -c -- "-big-Data.db$"', check=False)
        n = int(out.strip().splitlines()[0]) if out.strip() else -1
        if not expect(f'load: ks.{t} has {want} SSTables (found {n})', n == want):
            fail(f'ks.{t} SSTable count {n} != {want}')
    finish(0)


try:
    if mode == 'load':
        load_run()
    elif mode == 'value':
        value_run()
    else:
        head()
        finish(0)
except SystemExit:
    raise
except Exception as e:  # noqa: BLE001
    note(f'FAIL: exception {type(e).__name__}: {e}')
    finish(1)
