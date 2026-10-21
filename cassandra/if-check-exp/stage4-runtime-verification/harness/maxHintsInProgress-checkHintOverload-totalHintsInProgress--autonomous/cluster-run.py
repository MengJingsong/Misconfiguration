#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous
(audit amendments R1, R3-R6 of 2026-10-21).
usage: cluster-run.py <run> [<run> ...] | analyze | down
  <run> is one of O-1 O-128 O-MAX F-1 F-MAX (B3b); 'all' = the five in that order. Per run (B3e steps 1-8):
    1. fresh node copies ~/stage4-mhp/<RUN>/<run>/{n1,n2} of the build (O-*: ~/cassandra-mhp; F-*: ~/cassandra-mhp-patched,
       hintsInProgress-LoadingCache.diff), without .git, data/, logs/; B3a yaml edits (cluster_name, listen/rpc address,
       seeds n1, concurrent_writes 2; hinted_handoff_enabled true and max_hints_size_per_host unset = 0 as shipped);
       JMX_PORT 7221 / 7222 in cassandra-env.sh (R3). MAX_HEAP_SIZE=2G, HEAP_NEWSIZE unset (G1).
    2. start n1, wait for "Starting listening for CQL clients"; start n2; wait for two UN in n1's nodetool status.
    3. schema: the B3c stress command with n=1000 while both are up.
    4. kill n2 (its pid file), wait until n1 shows 127.0.0.22 DN.
    5. MaxHintsInProgress=L through jmx.jsh MODE=set (read back), jmx.jsh MODE=sample (200 ms) and jstat -gcutil 1000 (replaced: defect D1, G1 Old Gen CollectionUsage over JMX).
    6. the B3c stress command with n=1000000 (-errors ignore retries=0, R4).
    7. 30 s, stop the samplers; grep "Too many in flight hints" in n1's logs (R5: 0 expected everywhere), du -sb of n1's
       hints, stress's "Total errors" line, TotalHints and write Unavailables before/after (Jmx.java get).
    8. kill n1, wait for exit, check that no pid of this run is alive (R6), copy logs, remove the node copies.
  analyze: reads every <run>/readings.json of this RUN and writes analysis.txt with the B3f relations.
  down:    kill this harness's nodes (pid files under ~/stage4-mhp/<RUN>/).
Output: ~/stage4-logs/mhp/<RUN>/cluster/<run>/ (summary.txt with EXPECTED lines, session.log, samples.csv,
oldgen.csv, stress-*.log/out, readings.json, n1-logs/, n2-logs/). Env: MHP_RUN (default run1), MHP_N (default 1000000),
MHP_THREADS (default 400). A missed prediction is recorded as EXPECTED ... NO and the run goes on; a failed set-up
step stops the run (exit 1) after killing its nodes."""
import glob, json, os, re, signal, subprocess, sys, time

HOME = os.path.expanduser('~')
HARNESS = os.path.dirname(os.path.abspath(__file__))
RUN = os.environ.get('MHP_RUN', 'run1')
N = int(os.environ.get('MHP_N', 1000000))
THREADS = int(os.environ.get('MHP_THREADS', 400))
WORKROOT = f'{HOME}/stage4-mhp/{RUN}'
LOGROOT = f'{HOME}/stage4-logs/mhp/{RUN}/cluster'
BUILDS = {'O': f'{HOME}/cassandra-mhp', 'F': f'{HOME}/cassandra-mhp-patched'}
LIMITS = {'1': 1, '128': 128, 'MAX': 2147483647}
ORDER = ['O-1', 'O-128', 'O-MAX', 'F-1', 'F-MAX']
NODES = {'n1': ('127.0.0.21', 7221), 'n2': ('127.0.0.22', 7222)}
SP = 'org.apache.cassandra.db:type=StorageProxy'
UNA = 'org.apache.cassandra.metrics:type=ClientRequest,scope=Write,name=Unavailables'
MYPIDS = set()

args = sys.argv[1:]
if not args:
    sys.exit(__doc__)
if args == ['all']:
    args = ORDER


class Ctx:
    def __init__(self, run):
        self.run = run
        self.logs = f'{LOGROOT}/{run}'
        os.makedirs(self.logs, exist_ok=True)
        self.session = open(self.logs + '/session.log', 'w')
        self.summary = open(self.logs + '/summary.txt', 'w')
        self.expect = {'yes': 0, 'no': 0}


CTX = None


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, file=sys.stderr, flush=True)
    if CTX:
        CTX.session.write(line + '\n'); CTX.session.flush()


def note(s):
    log(s)
    if CTX:
        CTX.summary.write(s + '\n'); CTX.summary.flush()


def expect(desc, cond):
    CTX.expect['yes' if cond else 'no'] += 1
    note(f'EXPECTED: {desc} — {"yes" if cond else "NO (recorded; judged in the results file)"}')
    return cond


def sh(cmd, timeout=600, check=True, cwd=None, env=None, quiet=False):
    log('+ ' + cmd)
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, cwd=cwd, env=env)
    except subprocess.TimeoutExpired:
        log(f'  TIMEOUT after {timeout} s')
        if check:
            raise RuntimeError('timeout: ' + cmd)
        return 124, ''
    out = (r.stdout or '') + (r.stderr or '')
    if not quiet and CTX:
        CTX.session.write(out[-4000:] + f'\n  rc={r.returncode}\n'); CTX.session.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'rc={r.returncode}: {cmd}\n{out[-1500:]}')
    return r.returncode, out


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def node_pid(work, n):
    try:
        return int(open(f'{work}/{n}.pid').read().strip())
    except (OSError, ValueError):
        return None


def kill_node(work, n, wait_s=90):
    pid = node_pid(work, n)
    if pid is None or not alive(pid):
        return
    log(f'kill {n} pid {pid}')
    os.kill(pid, signal.SIGTERM)
    for _ in range(wait_s):
        if not alive(pid):
            return
        time.sleep(1)
    log(f'{n} pid {pid} still alive after {wait_s} s: SIGKILL')
    os.kill(pid, signal.SIGKILL)
    time.sleep(2)


def my_daemons():
    """java CassandraDaemon processes whose command line names ~/stage4-mhp (R6); never other sessions' nodes"""
    _, out = sh("ps -eo pid,args", quiet=True, check=False)
    res = []
    for l in out.splitlines()[1:]:
        pid, _, a = l.strip().partition(' ')
        if re.match(r'^\S*java\s', a) and 'org.apache.cassandra.service.CassandraDaemon' in a and '/stage4-mhp/' in a:
            res.append(int(pid))
    return res


def nodetool(work, n, cmd, timeout=120):
    return sh(f'{work}/n1/bin/nodetool -h 127.0.0.1 -p {NODES[n][1]} {cmd}', timeout=timeout, check=False, quiet=True)[1]


def jmx_get(work, n, *pairs):
    cp = f'{HOME}/stage4-mhp/jmxcls'
    _, out = sh(f'java -cp {cp} Jmx {NODES[n][1]} get ' + ' '.join(f"'{x}'" for p in pairs for x in p), check=False, quiet=True)
    res = {}
    for l in out.splitlines():
        parts = l.rsplit('|', 2)
        if len(parts) == 3:
            res[parts[1]] = parts[2]
    return res


def edit_line(text, pattern, repl, path):
    new, k = re.subn(pattern, repl, text, count=1, flags=re.M)
    if k != 1:
        raise RuntimeError(f'pattern {pattern!r} not found in {path}')
    return new


def make_node(src, work, n):
    d = f'{work}/{n}'
    sh(f'mkdir -p {d} && rsync -a --exclude=.git --exclude=/data --exclude=/logs --exclude=/build/test {src}/ {d}/', timeout=600)
    addr, jmxp = NODES[n]
    y = f'{d}/conf/cassandra.yaml'
    t = open(y).read()
    t = edit_line(t, r"^cluster_name: .*$", "cluster_name: 'stage4-mhp'", y)
    t = edit_line(t, r'^(\s*- seeds: )"127\.0\.0\.1:7000"', r'\1"127.0.0.21:7000"', y)
    t = edit_line(t, r'^listen_address: localhost$', f'listen_address: {addr}', y)
    t = edit_line(t, r'^rpc_address: localhost$', f'rpc_address: {addr}', y)
    t = edit_line(t, r'^concurrent_writes: 32$', 'concurrent_writes: 2', y)
    if not re.search(r'^hinted_handoff_enabled: true$', t, re.M) or re.search(r'^max_hints_size_per_host:', t, re.M):
        raise RuntimeError('hinted handoff / max_hints_size_per_host not as shipped')
    open(y, 'w').write(t)
    e = f'{d}/conf/cassandra-env.sh'
    et = edit_line(open(e).read(), r'^JMX_PORT="7199"$', f'JMX_PORT="{jmxp}"', e)
    open(e, 'w').write(et)
    sh(f'cd {d} && diff {src}/conf/cassandra.yaml conf/cassandra.yaml > {CTX.logs}/{n}-yaml.diff; '
       f'diff {src}/conf/cassandra-env.sh conf/cassandra-env.sh >> {CTX.logs}/{n}-yaml.diff; true', check=False)


def start_node(work, n):
    d = f'{work}/{n}'
    env = {k: v for k, v in os.environ.items() if k not in ('JVM_EXTRA_OPTS', 'CASSANDRA_CONF', 'CASSANDRA_HOME', 'HEAP_NEWSIZE', 'CASSANDRA_LOG_DIR')}
    env['MAX_HEAP_SIZE'] = '2G'
    sh(f'ulimit -n 100000; cd {d} && bin/cassandra -p {work}/{n}.pid > {d}/stdout.txt 2>&1', env=env, check=True)
    for _ in range(30):
        time.sleep(1)
        pid = node_pid(work, n)
        if pid and alive(pid):
            MYPIDS.add(pid)
            note(f'{n} started pid {pid}')
            return pid
    raise RuntimeError(f'{n} did not start')


def wait_log(work, n, text, timeout=300):
    f = f'{work}/{n}/logs/system.log'
    t0 = time.time()
    while time.time() - t0 < timeout:
        pid = node_pid(work, n)
        if pid is None or not alive(pid):
            raise RuntimeError(f'{n} died during start')
        try:
            if text in open(f, errors='replace').read():
                log(f'{n}: "{text}" after {time.time() - t0:.0f} s')
                return
        except OSError:
            pass
        time.sleep(2)
    raise RuntimeError(f'{n}: "{text}" not seen in {timeout} s')


def status(work):
    out = nodetool(work, 'n1', 'status')
    return {a: s for s, a in re.findall(r'^([UD][NLJM])\s+(\S+)\s', out, re.M)}, out


def stress(work, n_ops, tag):
    so = f'{CTX.logs}/stress-{tag}.out'
    cmd = (f'cd {work}/n1 && tools/bin/cassandra-stress write n={n_ops} cl=ONE -schema "replication(factor=2)" '
           f'-col "size=FIXED(1024)" "n=FIXED(1)" -rate threads={THREADS} -errors ignore retries=0 '
           f'-node {NODES["n1"][0]} -log file={CTX.logs}/stress-{tag}.log > {so} 2>&1')
    t0 = time.time()
    rc, _ = sh(cmd, timeout=3600, check=False)
    txt = open(so, errors='replace').read()
    m = re.search(r'Total errors\s*:\s*([\d,]+)', txt)
    errs = int(m.group(1).replace(',', '')) if m else None
    m2 = re.search(r'Total partitions\s*:\s*([\d,]+)', txt)
    parts = int(m2.group(1).replace(',', '')) if m2 else None
    msg = txt.count('Too many in flight hints')
    note(f'stress {tag}: rc={rc} {time.time() - t0:.0f} s; Total errors={errs}; Total partitions={parts}; '
         f'"Too many in flight hints" in stress output: {msg}')
    return {'rc': rc, 'errors': errs, 'partitions': parts, 'msg_count': msg, 'seconds': round(time.time() - t0, 1)}


def du_hints(work):
    d = f'{work}/n1/data/hints'
    tot, k = 0, 0
    for f in glob.glob(d + '/*.hints'):
        try:
            tot += os.path.getsize(f); k += 1
        except OSError:
            pass
    _, out = sh(f'du -sb {d}', check=False, quiet=True)
    return tot, k, int(out.split()[0]) if out.strip() and out.split()[0].isdigit() else None


def one(run):
    global CTX
    CTX = Ctx(run)
    b, l = run.split('-')
    L = LIMITS[l]
    src = BUILDS[b]
    work = f'{WORKROOT}/{run}'
    procs = []
    R = {'run': run, 'build': src, 'L': L}
    try:
        note(f'run {run} {time.strftime("%F %T %z")} host {os.uname().nodename} build {src} L={L} N={N} threads={THREADS}')
        _, f = sh(f"javap -p -cp {src}/build/apache-cassandra-5.0.9-SNAPSHOT.jar org.apache.cassandra.service.StorageProxy | grep ' hintsInProgress;'", quiet=True)
        note('build check (jar used by bin/cassandra): ' + f.strip())
        R['field'] = f.strip()
        if my_daemons():
            raise RuntimeError(f'a node of this harness is already running: {my_daemons()}')
        sh(f'rm -rf {work} && mkdir -p {work}')
        _, df = sh(f'df -B1 --output=avail {HOME} | tail -1', quiet=True)
        note(f'free on / at start: {int(df) / 2**30:.1f} GiB')
        for n in ('n1', 'n2'):
            make_node(src, work, n)
        note('yaml/env diffs: ' + open(f'{CTX.logs}/n1-yaml.diff').read().replace('\n', ' | ')[:900])
        start_node(work, 'n1')
        wait_log(work, 'n1', 'Starting listening for CQL clients')
        start_node(work, 'n2')
        t0 = time.time()
        while True:
            st, out = status(work)
            if st.get('127.0.0.21') == 'UN' and st.get('127.0.0.22') == 'UN':
                note(f'two UN after {time.time() - t0:.0f} s')
                break
            if time.time() - t0 > 400:
                raise RuntimeError('ring not UN/UN: ' + out[-800:])
            for n in ('n1', 'n2'):
                if not alive(node_pid(work, n) or -1):
                    raise RuntimeError(f'{n} died')
            time.sleep(5)
        wait_log(work, 'n2', 'Starting listening for CQL clients', timeout=200)
        R['schema'] = stress(work, 1000, 'schema')
        if R['schema']['errors'] not in (0,):
            raise RuntimeError('schema stress had errors')
        n2pid = node_pid(work, 'n2')
        os.kill(n2pid, signal.SIGTERM)
        t0 = time.time()
        while time.time() - t0 < 120:
            st, out = status(work)
            if st.get('127.0.0.22') == 'DN':
                note(f'n1 sees n2 DN after {time.time() - t0:.0f} s (n2 pid {n2pid} alive={alive(n2pid)})')
                break
            time.sleep(2)
        else:
            raise RuntimeError('n2 not DN')
        for _ in range(60):
            if not alive(n2pid):
                break
            time.sleep(1)
        R['n2_status'] = 'DN'
        env = dict(os.environ, PORT=str(NODES['n1'][1]), MODE='set', L=str(L))
        rc, out = sh(f'jshell {HARNESS}/jmx.jsh', env=env, timeout=180)
        m = re.search(r'MaxHintsInProgress=(\d+)', out)
        R['L_readback'] = int(m.group(1)) if m else None
        note(f'set MaxHintsInProgress: read back {R["L_readback"]}')
        if R['L_readback'] != L:
            raise RuntimeError('limit not set')
        before = jmx_get(work, 'n1', (SP, 'TotalHints'), (UNA, 'Count'), (SP, 'HintsInProgress'))
        R['before'] = before
        note(f'before: {before}')
        csv = f'{CTX.logs}/samples.csv'
        for f in (csv + '.stop',):
            if os.path.exists(f):
                os.remove(f)
        envs = dict(os.environ, PORT=str(NODES['n1'][1]), MODE='sample', OUT=csv)
        log(f'+ jshell {HARNESS}/jmx.jsh (sample) &')
        ps = subprocess.Popen(['jshell', f'{HARNESS}/jmx.jsh'], env=envs, stdout=open(f'{CTX.logs}/sampler.out', 'w'),
                              stderr=subprocess.STDOUT, start_new_session=True)
        procs.append(ps); MYPIDS.add(ps.pid)
        # defect D1 (shakedown1): jstat cannot attach (the node runs with -XX:+PerfDisableSharedMem, conf/jvm-server.options),
        # so B3d's post-GC old-gen reading is taken over JMX instead: G1 Old Gen CollectionUsage.used (after the last GC)
        # and Usage.used (= jstat's O column, current old-gen occupancy), every 1000 ms, the same 1 s period as the filed jstat.
        og = 'java.lang:type=MemoryPool,name=G1 Old Gen'
        pj = subprocess.Popen(['java', '-cp', f'{HOME}/stage4-mhp/jmxcls', 'Jmx', str(NODES['n1'][1]), 'poll', '1000', '100000000',
                               csv + '.stop', og, 'CollectionUsage', og, 'Usage'],
                              stdout=open(f'{CTX.logs}/oldgen.csv', 'w'), stderr=subprocess.STDOUT, start_new_session=True)
        procs.append(pj); MYPIDS.add(pj.pid)
        for _ in range(60):
            time.sleep(1)
            if os.path.exists(csv) and len(open(csv).read().splitlines()) >= 3:
                break
        else:
            raise RuntimeError('sampler wrote no rows')
        R['stress_t0_ms'] = int(time.time() * 1000)
        R['stress'] = stress(work, N, 'main')
        R['stress_t1_ms'] = int(time.time() * 1000)
        time.sleep(30)
        open(csv + '.stop', 'w').close()
        try:
            ps.wait(timeout=30)
        except subprocess.TimeoutExpired:
            ps.kill()
        pj.terminate()
        try:
            pj.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pj.kill()
        after = jmx_get(work, 'n1', (SP, 'TotalHints'), (UNA, 'Count'), (SP, 'HintsInProgress'))
        R['after'] = after
        note(f'after (+30 s): {after}')
        _, g = sh(f'grep -c "Too many in flight hints" {work}/n1/logs/system.log {work}/n1/logs/debug.log', check=False, quiet=True)
        R['log_lines'] = sum(int(x.rsplit(':', 1)[1]) for x in g.split() if ':' in x and x.rsplit(':', 1)[1].isdigit())
        note(f'"Too many in flight hints" in n1 logs: {g.strip()}')
        R['hints_bytes'], R['hints_files'], R['hints_du'] = du_hints(work)
        note(f'n1 hints: {R["hints_bytes"]} B in {R["hints_files"]} files (du -sb {R["hints_du"]})')
        st, out = status(work)
        R['n2_status_end'] = st.get('127.0.0.22')
        _, er = sh(f"grep -c '^ERROR' {work}/n1/logs/system.log", check=False, quiet=True)
        R['n1_error_lines'] = int(er.strip() or 0)
        # sampler readings
        rows = []
        for ln in open(csv).read().splitlines()[1:]:
            p = ln.split(',')
            if len(p) == 6 and p[0].isdigit():
                rows.append([int(p[0]), int(p[1]), int(p[2]), int(p[3]), int(p[4]), int(p[5])])
        R['samples'] = len(rows)
        R['limit_seen'] = sorted({r[1] for r in rows})
        R['max_hip'] = max(r[2] for r in rows)
        R['max_pending'] = max(r[3] for r in rows)
        R['max_heap'] = max(r[5] for r in rows)
        R['una_first'], R['una_last'] = rows[0][4], rows[-1][4]
        R['una_delta'] = int(after.get('Count', -1)) - int(before.get('Count', 0))
        R['hints_delta'] = int(after.get('TotalHints', -1)) - int(before.get('TotalHints', 0))
        jo, ju = [], []
        for ln in open(f'{CTX.logs}/oldgen.csv').read().splitlines():
            p = ln.split(',')
            if len(p) == 3 and p[0].isdigit() and p[1].isdigit() and p[2].isdigit():
                jo.append(int(p[1])); ju.append(int(p[2]))
        R['oldgen_samples'] = len(jo)
        R['max_old_after_gc'] = max(jo) if jo else None
        R['max_old_pct'] = round(100.0 * max(ju) / (2 << 30), 2) if ju else None   # jstat's O column = current old-gen use, of the 2 GiB heap
        R['max_old_used'] = max(ju) if ju else None
        note(f'samples={R["samples"]} limit_seen={R["limit_seen"]} max_hintsInProgress={R["max_hip"]} '
             f'max_mutationPending={R["max_pending"]} max_heapUsed={R["max_heap"] / 2**20:.0f} MiB '
             f'max_oldgen_used={(R["max_old_used"] or 0) / 2**20:.1f} MiB ({R["max_old_pct"]} % of 2 GiB; after-GC {(R["max_old_after_gc"] or 0) / 2**20:.1f} MiB; {R["oldgen_samples"]} samples) '
             f'unavailables_delta={R["una_delta"]} (sampler {R["una_first"]}->{R["una_last"]}) TotalHints_delta={R["hints_delta"]} '
             f'n1 ERROR lines={R["n1_error_lines"]}')
        # B3f per-run expectations
        s = R['stress']
        expect(f'{run}: limit in force during the run (sampler limit column = {L})', R['limit_seen'] == [L])
        expect(f'{run}: n2 DN at the end, TotalHints grew', R['n2_status_end'] == 'DN' and R['hints_delta'] > 0)
        expect(f'{run}: "Too many in flight hints" lines in n1 logs = 0 (R5: none in any run)', R['log_lines'] == 0)
        if b == 'O' or l == 'MAX':
            expect(f'{run}: write Unavailables delta = 0', R['una_delta'] == 0)
            expect(f'{run}: stress Total errors = 0', s['errors'] == 0)
            expect(f'{run}: max hintsInProgress >= 2', R['max_hip'] >= 2)
            if L < 2147483647:
                expect(f'{run}: max hintsInProgress > L = {L} (the limit was passed)', R['max_hip'] > L)
            expect(f'{run}: hints on disk 1.0-1.3 GB (~1 M hints)', 1.0e9 <= (R['hints_bytes'] or 0) <= 1.3e9)
        else:
            expect(f'{run}: write Unavailables delta > 0', R['una_delta'] > 0)
            expect(f'{run}: stress Total errors > 0', (s['errors'] or 0) > 0)
            expect(f'{run}: max hintsInProgress <= ~130 (1 + native request threads)', R['max_hip'] <= 130)
        R['expect'] = dict(CTX.expect)
        return True
    except Exception as e:
        note(f'FAIL: {e}')
        R['fail'] = str(e)
        return False
    finally:
        for p in procs:
            if p.poll() is None:
                p.kill()
        for n in ('n2', 'n1'):
            kill_node(work, n)
        for n in ('n1', 'n2'):
            sh(f'cp -r {work}/{n}/logs {CTX.logs}/{n}-logs 2>/dev/null; cp {work}/{n}/stdout.txt {CTX.logs}/{n}-stdout.txt 2>/dev/null', check=False, quiet=True)
        left = [p for p in MYPIDS if alive(p)] + my_daemons()
        note(f'processes of this run left: {sorted(set(left))}')
        R['left'] = sorted(set(left))
        json.dump(R, open(f'{CTX.logs}/readings.json', 'w'), indent=1)
        note(f'EXPECTED totals {run}: {CTX.expect}')
        if not left:
            sh(f'rm -rf {work}', check=False)


def analyze():
    global CTX
    CTX = Ctx('analysis')
    R = {}
    for f in glob.glob(f'{LOGROOT}/*/readings.json'):
        j = json.load(open(f))
        if 'fail' not in j and 'max_hip' in j:
            R[j['run']] = j
    note('runs: ' + ', '.join(sorted(R)))
    for k in ORDER:
        if k in R:
            j = R[k]
            note(f"{k}: L={j['L']} max_hip={j['max_hip']} max_pending={j['max_pending']} max_heap={j['max_heap'] / 2**20:.0f}MiB "
                 f"max_old%={j['max_old_pct']} una_delta={j['una_delta']} stress_errors={j['stress']['errors']} "
                 f"hints_bytes={j['hints_bytes']} hints_delta={j['hints_delta']} stress_s={j['stress']['seconds']}")
    O = [R[k] for k in ('O-1', 'O-128', 'O-MAX') if k in R]
    if len(O) == 3:
        for key, lab in (('max_hip', 'peak hintsInProgress'), ('max_pending', 'peak MutationStage pending'), ('max_old_used', 'peak old-gen use (bytes; jstat O equivalent)')):
            v = [o[key] for o in O]
            lo, hi = min(v), max(v)
            expect(f'X1 O-*: {lab} within ±25 % of each other ({v}; max/min = {hi / lo if lo else float("inf"):.2f}; read as max <= 1.25 x min)', hi <= 1.25 * lo)
        expect(f"X2 O-MAX: max hintsInProgress > 128 ({R['O-MAX']['max_hip']})", R['O-MAX']['max_hip'] > 128)
        a, c = R['O-1']['hints_bytes'], R['O-MAX']['hints_bytes']
        expect(f'X3 O-1 vs O-MAX hint bytes within ±5 % ({a} vs {c}, ratio {a / c:.4f})', abs(a / c - 1) <= 0.05)
        a2, c2 = R['O-1']['max_heap'], R['O-MAX']['max_heap']
        expect(f'X4 O-1 heap/hint volume not >25 % below O-MAX (heap {a2 / 2**20:.0f} vs {c2 / 2**20:.0f} MiB)', a >= 0.75 * c and a2 >= 0.75 * c2)
    if 'F-1' in R and 'O-1' in R:
        f1, o1 = R['F-1'], R['O-1']
        expect(f"X5 F-1 hints on disk well below O-1 ({f1['hints_bytes']} vs {o1['hints_bytes']}, ratio {f1['hints_bytes'] / o1['hints_bytes']:.3f}; 'well below' read as < 0.75)",
               f1['hints_bytes'] < 0.75 * o1['hints_bytes'])
        expect(f"X6 F-1 peak MutationStage pending below O-1 ({f1['max_pending']} vs {o1['max_pending']})", f1['max_pending'] < o1['max_pending'])
        expect(f"X7 F-1 Unavailables a substantial share of the writes ({f1['una_delta']} of {N}; 'substantial' read as >= 10 %)", f1['una_delta'] >= 0.10 * N)
    if 'F-MAX' in R and 'O-MAX' in R:
        fm, om = R['F-MAX'], R['O-MAX']
        expect(f"X8 F-MAX matches O-MAX: 0 Unavailables in both, hint bytes within ±5 % ({fm['hints_bytes']} vs {om['hints_bytes']})",
               fm['una_delta'] == 0 and om['una_delta'] == 0 and abs(fm['hints_bytes'] / om['hints_bytes'] - 1) <= 0.05)
    note(f'EXPECTED totals analysis: {CTX.expect}')


def down():
    for d in glob.glob(f'{WORKROOT}/*'):
        for n in ('n2', 'n1'):
            kill_node(d, n)
    print('left:', my_daemons())


if args == ['analyze']:
    analyze()
elif args == ['down']:
    down()
else:
    for a in args:
        if a not in ORDER:
            sys.exit(f'unknown run {a}')
    os.makedirs(f'{HOME}/stage4-mhp/jmxcls', exist_ok=True)
    subprocess.run(['javac', '-d', f'{HOME}/stage4-mhp/jmxcls', f'{HARNESS}/Jmx.java'], check=True)
    ok = True
    for a in args:
        ok = one(a) and ok
    sys.exit(0 if ok else 1)
