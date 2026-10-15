#!/usr/bin/env python3
"""Stage 4, cluster tier, coordinator_read_size_fail_threshold-shouldReject-thresholdBytes (case 9b-9e, amended 2026-10-15).
usage: cluster-run.py <label>          label: shakedownN | run1 (any name; the log folder is ~/stage4-logs/crs/<label>)
One node (~/cassandra-run1), one lifetime for every value, RF 1. One driver Session (protocol 5) held by this script for the
whole lifetime, opened before any limit is set (amendment (2)). Logs every command to <dir>/session.log, writes summary.txt
(EXPECTED lines) and readings.csv. Exit 1: an instrument/set-up check failed; the node is stopped on any exit."""
import csv, glob, json, os, re, subprocess, sys, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-run1')
HARNESS = os.path.dirname(os.path.abspath(__file__))
N, PAYLOAD, S = 8000, 1000, 1008
VALUES = [262144, 1048576, 4194304, 16777216]
label = sys.argv[1]
D = f'{HOME}/stage4-logs/crs/{label}'
os.makedirs(D, exist_ok=True)
SESSION = open(D + '/session.log', 'a')
SUMMARY = open(D + '/summary.txt', 'w')
RF = open(D + '/readings.csv', 'w'); RCSV = csv.writer(RF)
RCSV.writerow(['F', 'arm', 'cql', 'fetch', 'outcome', 'rows', 'pages', 'codes', 'guard_fail', 'result', 'frame', 'coord_alloc', 'read_alloc',
               't_meter_before', 't_meter_after', 'c_meter_before', 'c_meter_after', 'warn_lines', 'client_warning'])
TRACE = D + '/crs.trace'
SYSLOG = C + '/logs/system.log'
BM = C + '/build/lib/jars'
SS = 'org.apache.cassandra.db:type=StorageService'
TMETER = 'org.apache.cassandra.metrics:type=Table,keyspace=ks1,scope=t,name=CoordinatorReadSizeAborts'
CMETER = 'org.apache.cassandra.metrics:type=ClientRequest,scope=Read,name=ReadSizeAborts'
SEL = 'SELECT * FROM ks1.t WHERE pk = 1'


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, file=sys.stderr); SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush(); log(s)


def sh(cmd, timeout=300, check=True, env=None, cwd=C):
    log('+ ' + cmd)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
    out = (r.stdout or '') + (r.stderr or '')
    SESSION.write(out[-4000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed rc={r.returncode}: {cmd}\n{out[-800:]}')
    return r.returncode, out


def daemon_up():
    return subprocess.run("ps -eo cmd | grep -q '[C]assandraDaemon'", shell=True).returncode == 0


def stop_node():
    global cluster
    try:
        if cluster is not None:
            cluster.shutdown()
    except Exception:
        pass
    cluster = None
    if daemon_up():
        sh('bin/nodetool stopdaemon', check=False)
        for _ in range(90):
            if not daemon_up():
                break
            time.sleep(1)
        if daemon_up():
            subprocess.run("pkill -9 -f '[o]rg.apache.cassandra.service.CassandraDaemon'", shell=True)
            time.sleep(2)
    if daemon_up():
        log('WARNING: a CassandraDaemon is still running')
    sh(f'cp {SYSLOG} {D}/system.log', check=False)
    sh('git checkout -q conf/cassandra.yaml', check=False)


def fail(msg):
    note('FAIL: ' + msg)
    stop_node()
    sys.exit(1)


n_expected = n_yes = 0
def expect(desc, cond):
    global n_expected, n_yes
    n_expected += 1; n_yes += bool(cond)
    note(f'EXPECTED: {desc} — {"yes" if cond else "NO (recorded; the AI judges it in the results file)"}')
    return cond


def jmx(*args):
    _, out = sh(f'java -cp {D}/jmx Jmx ' + ' '.join(args), check=False, timeout=60)
    return out.strip()


def meters():
    out = jmx('get', TMETER, 'Count', CMETER, 'Count')
    vals = {}
    for l in out.splitlines():
        p = l.split('|')
        if len(p) == 3:
            vals[p[0]] = int(p[2])
    return vals.get(TMETER), vals.get(CMETER)


def set_limit(v):
    out = jmx('set', SS, 'CoordinatorLargeReadAbortThreshold', f'str:{v}')
    rb = out.splitlines()[-1].split('|')[-1] if out else None
    note(f'SET CoordinatorLargeReadAbortThreshold {v} -> read back {rb}')
    return rb


# ---- trace and log readers
trace_seen = 0
def new_trace():
    global trace_seen
    time.sleep(0.6)
    if not os.path.exists(TRACE):
        return []
    lines = open(TRACE, errors='replace').read().splitlines()
    new = lines[trace_seen:]
    trace_seen = len(lines)
    return new


def warn_lines():
    try:
        return [l for l in open(SYSLOG, errors='replace') if 'size failure threshold' in l]
    except FileNotFoundError:
        return []


def field(lines, kind, key):
    return [int(re.search(rf'\b{key}=(-?\d+)', l).group(1)) for l in lines if l.startswith(kind + ' ')]


# ---- the driver, loaded from the clone's bundled zip
def load_driver():
    lib = os.path.join(C, 'lib')
    z = max(glob.glob(os.path.join(lib, 'cassandra-driver-internal-only-*.zip')))
    ver = os.path.splitext(os.path.basename(z))[0][len('cassandra-driver-internal-only-'):]
    sys.path.insert(0, os.path.join(z, 'cassandra-driver-' + ver))
    for p in ('pure_sasl-', 'wcwidth-', 'pyasyncore-'):
        zz = glob.glob(os.path.join(lib, p + '*.zip'))
        if zz:
            sys.path.insert(0, max(zz))


cluster = None
session = None


def connect():
    global cluster, session
    load_driver()
    from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
    from cassandra import ConsistencyLevel
    prof = ExecutionProfile(request_timeout=120, consistency_level=ConsistencyLevel.ONE)
    cluster = Cluster(['127.0.0.1'], protocol_version=5, execution_profiles={EXEC_PROFILE_DEFAULT: prof})
    session = cluster.connect()
    return cluster.protocol_version


def query(cql, fetch=None):
    from cassandra.query import SimpleStatement
    st = SimpleStatement(cql, fetch_size=fetch)
    fut = session.execute_async(st)
    out = {'ok': True}
    try:
        rs = fut.result()
        n, pages, first = 0, 1, None
        while True:
            if n == 0 and rs.current_rows:
                first = rs.current_rows[0][0]
            n += len(rs.current_rows)
            if rs.has_more_pages:
                rs.fetch_next_page(); pages += 1
            else:
                break
        out.update(rows=n, pages=pages, first=first if isinstance(first, int) else None)
    except Exception as e:
        out.update(ok=False, error=type(e).__name__, message=str(e)[:300],
                   codes={str(k): v for k, v in (getattr(e, 'error_code_map', None) or {}).items()})
    try:
        out['warnings'] = list(fut.warnings or [])
    except Exception:
        out['warnings'] = []
    return out


aborts_caused = 0
def read(F, arm, cql, fetch=None):
    global aborts_caused
    tb, cb = meters(); wb = len(warn_lines())
    r = query(cql, fetch)
    tr = new_trace()
    ta, ca = meters(); wl = warn_lines()
    res = dict(F=F, arm=arm, ok=r['ok'], rows=r.get('rows'), pages=r.get('pages'), first=r.get('first'), codes=r.get('codes'),
               gf=[l for l in tr if l.startswith('guard-fail ')], result=field(tr, 'result', 'size'), result_rows=field(tr, 'result', 'rows'),
               frame=field(tr, 'frame', 'bytes'), frame_rows=field(tr, 'frame', 'rows'), coord=field(tr, 'coord-alloc', 'bytes'),
               readalloc=field(tr, 'read-alloc', 'bytes'), tb=tb, ta=ta, cb=cb, ca=ca, warn_new=wl[wb:], warnings=r.get('warnings', []),
               error=r.get('error'), trace=tr)
    if not r['ok']:
        aborts_caused += 1
    gf_size = field(res['gf'], 'guard-fail', 'size'); gf_lim = field(res['gf'], 'guard-fail', 'limit')
    res['gf_size'], res['gf_limit'] = gf_size, gf_lim
    RCSV.writerow([F, arm, cql[:100], fetch, 'OK' if r['ok'] else 'ERR:' + str(r.get('error')), res['rows'], res['pages'], res['codes'],
                   ' '.join(f'{a}/{b}' for a, b in zip(gf_size, gf_lim)), res['result'], res['frame'], res['coord'], res['readalloc'],
                   tb, ta, cb, ca, len(res['warn_new']), (res['warnings'][0][:160] if res['warnings'] else '')])
    RF.flush()
    note(f'READ F={F} {arm}: {"OK rows=" + str(res["rows"]) + " pages=" + str(res["pages"]) if r["ok"] else "ERR " + str(r.get("error")) + " codes=" + str(r.get("codes"))}'
         f' guard-fail={list(zip(gf_size, gf_lim))} result={list(zip(res["result"], res["result_rows"]))} frame={list(zip(res["frame"], res["frame_rows"]))}'
         f' coord-alloc={res["coord"]} read-alloc={res["readalloc"]} tmeter {tb}->{ta} cmeter {cb}->{ca} warn+{len(res["warn_new"])}'
         + (f' first={res["first"]}' if res['first'] is not None else ''))
    return res


def is_abort(r, X, F):
    return ((not r['ok']) and list((r['codes'] or {}).values()) == [4] and r['gf_size'] == [X] and r['gf_limit'] == [F]
            and r['ta'] == r['tb'] + 1 and r['ca'] == r['cb'] + 1 and not r['frame'] and len(r['warn_new']) == 1
            and any(f'size failure threshold of {F:,} bytes' in w for w in r['warnings']))


def main():
    if daemon_up():
        fail('a CassandraDaemon is already running')
    sh('git checkout -q conf/cassandra.yaml', check=False)
    note(sh(f'{HARNESS}/make-node-yaml.sh')[1].strip())
    sh('rm -rf data logs saved_caches')
    sh(f'rm -rf {D}/helper-classes {D}/jmx && mkdir -p {D}/helper-classes {D}/jmx && javac -d {D}/helper-classes {HARNESS}/Alloc.java {HARNESS}/CoordAlloc.java '
       f'&& jar cf {D}/stage4-helpers.jar -C {D}/helper-classes . && javac -d {D}/jmx {HARNESS}/Jmx.java')
    _, ts = sh(f'java -classpath {BM}/byteman-4.0.20.jar:{D}/stage4-helpers.jar:build/classes/main:"build/lib/jars/*":"lib/*" '
               f'org.jboss.byteman.check.TestScript {HARNESS}/coord-read.btm {HARNESS}/read-alloc.btm', check=False)
    open(D + '/testscript.txt', 'w').write(ts)
    if 'TestScript: no errors' not in ts:
        fail('Byteman TestScript reported errors (testscript.txt)')
    note('INSTRUMENT Byteman TestScript: no errors')
    if os.path.exists(TRACE):
        os.remove(TRACE)
    env = dict(os.environ, MAX_HEAP_SIZE='4G',
               JVM_EXTRA_OPTS=f'-Xbootclasspath/a:{D}/stage4-helpers.jar -javaagent:{BM}/byteman-4.0.20.jar=script:{HARNESS}/coord-read.btm,'
                              f'script:{HARNESS}/read-alloc.btm,listener:true -Dstage4.byteman.out={TRACE}')
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
    note('node up; JVM options: ' + sh("ps -eo args | grep '[C]assandraDaemon' | tr ' ' '\\n' | grep -E 'byteman|Xmx|Xms|bootclasspath'", check=False)[1].replace('\n', ' '))

    # ---- instrument checks (stop on failure)
    p = json.loads(subprocess.run([sys.executable, f'{HARNESS}/send-read.py', 'probe'], capture_output=True, text=True, timeout=120).stdout.strip().splitlines()[-1])
    if not p.get('ok') or p.get('protocol') != 5:
        fail(f'probe failed or protocol is not 5: {p}')
    note(f'INSTRUMENT probe: release {p["release_version"]} protocol {p["protocol"]}')
    g = jmx('get', SS, 'CoordinatorLargeReadAbortThreshold', SS, 'ReadThresholdsEnabled')
    note('INSTRUMENT jmx: ' + g.replace('\n', ' ; '))
    if 'CoordinatorLargeReadAbortThreshold|null' not in g or 'ReadThresholdsEnabled|true' not in g:
        fail('JMX read-back of the limit (null) or the switch (true) failed')
    sh('bin/cqlsh -e "CREATE KEYSPACE ks1 WITH replication = {\'class\': \'SimpleStrategy\', \'replication_factor\': 1}; '
       'CREATE TABLE ks1.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck)) WITH compression = {\'enabled\': false} AND '
       'compaction = {\'class\': \'SizeTieredCompactionStrategy\', \'enabled\': \'false\'};"')
    ld = json.loads(subprocess.run([sys.executable, f'{HARNESS}/send-read.py', 'load', str(N), str(PAYLOAD)], capture_output=True, text=True, timeout=600).stdout.strip().splitlines()[-1])
    if not ld.get('ok') or ld.get('loaded') != N:
        fail(f'load failed: {ld}')
    sh('bin/nodetool flush ks1 t')
    _, ls = sh('ls data/data/ks1/t-*/*-Data.db')
    note(f'DATASET rows loaded {ld["loaded"]}, Data.db files {len(ls.split())}')
    if len(ls.split()) != 1:
        fail('expected one Data.db file')
    proto = connect()
    note(f'SESSION one driver session, protocol {proto} (held for the lifetime)')
    tm = meters()
    if None in tm:
        fail(f'cannot read the meters over JMX: {tm}')
    new_trace()
    q1 = query(SEL + ' AND ck < 10'); t1 = new_trace()
    kinds = sorted(l.split(' ')[0] for l in t1)
    note(f'INSTRUMENT ks1 read ck<10: ok={q1["ok"]} rows={q1.get("rows")} lines {kinds}')
    if kinds != ['coord-alloc', 'frame', 'read-alloc', 'result']:
        fail('a ks1 read must write exactly one coord-alloc, frame, read-alloc and result line')
    q2 = query('SELECT release_version FROM system.local'); t2 = new_trace()
    note(f'INSTRUMENT system.local read: ok={q2["ok"]} lines {len(t2)}')
    if t2:
        fail('a system.local read wrote a trace line')
    time.sleep(10)
    if new_trace():
        fail('idle control: a trace line appeared in 10 s with no reads')
    note('INSTRUMENT idle control: no trace line in 10 s')

    # ---- 0. warm-up (runbook fix after shakedown 1, 2026-10-15): the first abort of a node lifetime carries one-off costs
    # (shakedown 1: 807,656 B for the first abort vs 406,680 B for the next one at the same F), so one abort is made and
    # discarded before any reading; then the limit is written back to null over JMX (read back 'null').
    global aborts_caused
    set_limit('262144B')
    w = query(SEL + ' AND ck < 300'); wt = new_trace()
    aborts_caused += 0 if w['ok'] else 1
    note(f'WARMUP (not a reading): ck<300 at 262144 ok={w["ok"]} codes={w.get("codes")} lines {[l.split(" ")[0] for l in wt]}')
    out = jmx('set', SS, 'CoordinatorLargeReadAbortThreshold', 'null:')
    rbn = out.splitlines()[-1].split('|')[-1] if out else None
    note(f'SET CoordinatorLargeReadAbortThreshold null -> read back {rbn}')
    if w['ok'] or rbn != 'null':
        fail('warm-up abort did not abort, or the limit could not be restored to null')

    # ---- 1. control (unset)
    ctl = {}
    for n in (1000, 2000, N):
        ctl[n] = read('unset', f'control ck<{n}' if n < N else 'control whole', SEL + (f' AND ck < {n}' if n < N else ''))
    if not all(ctl[n]['ok'] and ctl[n]['result'] == [S * n] for n in ctl):
        fail(f'INVALID: a control read did not complete with result size = 1008*n (whole must be 8,064,000)')
    expect('control: no guard-fail, meters unchanged', all(not ctl[n]['gf'] and ctl[n]['ta'] == ctl[n]['tb'] and ctl[n]['ca'] == ctl[n]['cb'] for n in ctl))
    B0 = ctl[1000]['frame'][0] - 1020 * 1000
    expect(f'frame bytes = B0 + 1020*rows exactly for the controls (B0={B0})', all(ctl[n]['frame'] == [B0 + 1020 * n] for n in ctl))
    a = (ctl[N]['coord'][0] - ctl[1000]['coord'][0]) / (N - 1000); d0 = ctl[1000]['coord'][0] - 1000 * a
    RA0 = ctl[N]['readalloc'][0]
    note(f'CALIBRATION B0={B0} a={a:.1f} B/row delta0={d0:.0f} read-alloc(whole, unset)={RA0}')

    # ---- 2. each value
    ab_whole, ab_n1, ra = {}, {}, {'unset': RA0}
    for F in VALUES:
        rb = set_limit(f'{F}B')
        time.sleep(0.5)
        logged = any(f'updating  coordinator_read_size_fail_threshold to {F}B' in l for l in open(SYSLOG, errors='replace'))
        if not expect(f'F={F}: read-back {F}B and the INFO line logged', rb == f'{F}B' and logged):
            fail('limit read-back failed')
        ns = F // S + 1; X = ns * S
        if F < S * N:
            A = read(F, 'A ck<n*', SEL + f' AND ck < {ns}')
            expect(f'F={F} A: completes with n*={ns} rows, result size X={X}, frame = B0+1020*n*', A['ok'] and A['rows'] == ns and A['result'] == [X] and A['result_rows'] == [ns] and A['frame'] == [B0 + 1020 * ns] and not A['gf'])
            B1 = read(F, 'B ck<n*+1', SEL + f' AND ck < {ns + 1}')
            expect(f'F={F} B ck<n*+1: abort, code 4, guard-fail size={X} limit={F}, meters +1, one WARN, client warning, no frame', is_abort(B1, X, F))
            B2 = read(F, 'B whole', SEL)
            expect(f'F={F} B whole: abort, code 4, guard-fail size={X} limit={F}, meters +1, one WARN, client warning, no frame', is_abort(B2, X, F))
            ab_n1[F] = B1['coord'][0] if B1['coord'] else None
            ab_whole[F] = B2['coord'][0] if B2['coord'] else None
            ra[F] = B2['readalloc'][0] if B2['readalloc'] else None
            if ab_n1[F] and ab_whole[F]:
                expect(f'F={F}: coord-alloc(whole abort) = coord-alloc(n*+1 abort) within 5% ({ab_whole[F]} vs {ab_n1[F]})', abs(ab_whole[F] - ab_n1[F]) / ab_n1[F] <= 0.05)
        else:
            W = read(F, 'whole above the data', SEL)
            expect(f'F={F}: whole partition completes, result size 8,064,000, no guard-fail', W['ok'] and W['rows'] == N and W['result'] == [S * N] and not W['gf'])
            ra[F] = W['readalloc'][0] if W['readalloc'] else None
    r1 = (ab_whole[1048576] - ab_whole[262144]) / (ab_whole[4194304] - ab_whole[1048576])
    expect(f'coord-alloc increments (1M-256K):(4M-1M) = 0.25 +/- 0.03 (got {r1:.4f})', abs(r1 - 0.25) <= 0.03)
    expect(f'abort at 262,144 allocates < 10% of the unset whole read ({ab_whole[262144]} vs {ctl[N]["coord"][0]})', ab_whole[262144] < 0.10 * ctl[N]['coord'][0])
    expect(f'read-alloc(whole) within 5% of unset at every F ({ra})', all(v is not None and abs(v - RA0) / RA0 <= 0.05 for v in ra.values()))

    # ---- 3. scenario C at 262,144
    F = 262144; X = (F // S + 1) * S
    set_limit(f'{F}B')
    c1a = read(F, 'C1 fetch 100', SEL, fetch=100)
    expect('C1 fetch 100: all 8,000 rows (pages recorded), no guard-fail', c1a['ok'] and c1a['rows'] == N and not c1a['gf'])
    c1b = read(F, 'C1 fetch 1000', SEL, fetch=1000)
    expect(f'C1 fetch 1000: aborts on page 1 (code 4, guard-fail size={X})', (not c1b['ok']) and list((c1b['codes'] or {}).values()) == [4] and c1b['gf_size'] == [X])
    c2 = read(F, 'C2 count(*)', 'SELECT count(*) FROM ks1.t WHERE pk = 1')
    expect('C2 count(*) returns 8,000, no guard-fail', c2['ok'] and c2['first'] == N and not c2['gf'])
    note('SET ReadThresholdsEnabled false -> ' + jmx('set', SS, 'ReadThresholdsEnabled', 'bool:false').splitlines()[-1])
    c3 = read(F, 'C3 switch off whole', SEL)
    expect('C3 switch off: whole completes, no guard-fail, meters unchanged', c3['ok'] and c3['rows'] == N and not c3['gf'] and c3['ta'] == c3['tb'] and c3['ca'] == c3['cb'])
    note('SET ReadThresholdsEnabled true -> ' + jmx('set', SS, 'ReadThresholdsEnabled', 'bool:true').splitlines()[-1])
    c5 = read(F, 'C5 scan', 'SELECT * FROM ks1.t')
    expect(f'C5 scan: aborts with guard-fail size={X} (as the whole-partition read)', (not c5['ok']) and c5['gf_size'] == [X] and list((c5['codes'] or {}).values()) == [4])
    # C4: the 1 B window, one read, then 16 MiB at once (amendment (4))
    wl0 = len(warn_lines())
    set_limit('1B')
    c4 = read(1, 'C4 system_schema.keyspaces', 'SELECT keyspace_name FROM system_schema.keyspaces')
    set_limit('16777216B')
    time.sleep(1)
    window = warn_lines()[wl0:]
    other = [l.strip() for l in window if 'system_schema.keyspaces' not in l]
    expect('C4 system_schema read aborts with code 4 and guard-fail ks=system_schema', (not c4['ok']) and list((c4['codes'] or {}).values()) == [4]
           and any('ks=system_schema' in l for l in c4['gf']))
    note(f'C4 window: WARN lines {len(window)}, of other tables {len(other)}' + ('' if not other else ' — ' + ' | '.join(o[:160] for o in other)))

    # ---- 4. stop
    note(f'SUMMARY aborts caused by this script {aborts_caused}, WARN lines in system.log {len(warn_lines())}')
    expect('WARN lines = aborts caused (+ other tables in the 1 B window)', len(warn_lines()) == aborts_caused + len(other))
    note(f'DONE expected {n_yes}/{n_expected} yes')
    stop_node()


try:
    main()
except SystemExit:
    raise
except Exception as e:
    import traceback
    note(f'FAIL (exception): {e!r}')
    log(traceback.format_exc())
    stop_node()
    sys.exit(1)
