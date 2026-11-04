#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of hints-EncryptedChecksummedDataInput-reusableBuffers-decryptBuffer--autonomous (audit R2, R8, R9).
usage: cluster-run.py cell <tag> <mm_KiB|default> <groups> [forged|plain] | pos <tag> <max_hints_file_size|default> | all | down
  cell  one lifetime: wipe ~/s4-ec-run; start A (seed) and B on loopback (TDE enabled, test keystore, max_mutation_size on A = <mm>);
        table ks.t created WITH ID = EcProbe.TABLE_ID, RF 2; B's host id read; A stopped; EcProbe `produce` writes the encrypted hints
        file (<groups>, kind:size:count, see EcProbe) for B's host id into A's hints dir (forged: header 512 MiB + junk; plain: same
        hints, no encryption = B3h control); A restarted with Byteman ec.btm (B up); wait until A's dispatch ends (hints dir empty, or
        'Finished hinted handoff' / 'Failed to dispatch' in system.log); snapshots at +10 s, +30 s, +150 s (live heap dump parsed for
        byte[] >= 200 kB, HintsDispatcher thread count, direct pool, Byteman trace tail); both nodes stopped.
  pos   B3h/K3 positive control: A and B, keyspace hc (RF 2), B stopped, 200 x 1 MiB values written to A (hints), hints files
        counted and sized with max_hints_file_size = default or the given value on A.
  all   the cells of the run (see CELLS), then the controls.
  down  stop both nodes of this harness.
A = 127.0.33.2 (JMX 7333, Byteman 9333, native 9355, storage 7033), B = 127.0.33.3 (JMX 7334, native 9356, storage 7034).
Environment: EC_RUN (default run1), CASSANDRA_HOME (default ~/s4-ec). Output: ~/stage4-logs/ec/<run>/cluster/<tag>/ (summary.txt has
EXPECTED lines). Both nodes are stopped on any exit. A reading that misses a prediction is recorded as EXPECTED ... NO and the run goes on."""
import glob, json, os, re, subprocess, sys, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/s4-ec')
HARNESS = os.path.dirname(os.path.abspath(__file__))
EC = os.environ.get('EC', HOME + '/s4-ec-run')
RUN = os.environ.get('EC_RUN', 'run1')
KIB, MIB = 1024, 1 << 20
NODES = {'A': ('127.0.33.2', 7333, 9355), 'B': ('127.0.33.3', 7334, 9356)}
BM = C + '/build/lib/jars/byteman-4.0.20.jar'
BM_PORT = 9333
TOOLS = EC + '/tools'
TABLE_ID = '6f1b8c2e-4d3a-4e5b-9a77-0c0ffee00033'
F1 = 'r:1024:65536'
F2 = 'r:8388608:1,r:1024:200'
F3 = 'r:15728640:1,r:1024:200'
CELLS = [('f1_mmdef', 'default', F1, ''), ('f2_mmdef', 'default', F2, ''), ('f2_mm4096', '4096', F2, ''), ('f2_mm1024', '1024', F2, ''),
         ('f3_mmdef', 'default', F3, ''), ('f3_mm1024', '1024', F3, ''), ('f3_plain', 'default', F3, 'plain'), ('f4_forged', 'default', 'r:1024:1', 'forged')]
# frozen predictions (B3f, with the 2026-10-26 amendments): retained byte[] band per file shape [lo, hi] bytes
BAND = {'f1': (254 * KIB, 262144 + 1069), 'f2': (8 * MIB, 8 * MIB + 40 * KIB), 'f3': (15 * MIB, 15 * MIB + 70 * KIB)}

args = sys.argv[1:]
if not args or args[0] not in ('cell', 'pos', 'all', 'down'):
    sys.exit(__doc__)
MODE = args[0]
TAG = args[1] if MODE in ('cell', 'pos') else MODE
LOGS = f'{HOME}/stage4-logs/ec/{RUN}/cluster/{TAG}'
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
SUMMARY = open(LOGS + '/summary.txt', 'a' if MODE in ('down', 'all') else 'w')
EXPECT = {'yes': 0, 'no': 0}
PIDS = {}
TRACE = LOGS + '/ec.trace'


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, file=sys.stderr)
    SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush(); log(s)


def sh(cmd, timeout=600, check=True, env=None, cwd=C, quiet=False):
    log('+ ' + cmd[:400])
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
    except subprocess.TimeoutExpired:
        log(f'  TIMEOUT after {timeout} s')
        if check:
            raise RuntimeError(f'command timed out: {cmd}')
        return 124, ''
    out = (r.stdout or '') + (r.stderr or '')
    if not quiet:
        SESSION.write(out[-4000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed rc={r.returncode}: {cmd}\n{out[-1200:]}')
    return r.returncode, out


def expect(desc, cond):
    EXPECT['yes' if cond else 'no'] += 1
    note(f'EXPECTED: {desc} - {"yes" if cond else "NO (recorded; the AI judges it in the results file)"}')
    return bool(cond)


def pid_of(node):
    f = f'{EC}/{node}/cassandra.pid'
    try:
        PIDS[node] = int(open(f).read().strip())
    except (ValueError, OSError):
        pass
    pid = PIDS.get(node)
    if pid is None:
        return None
    try:
        return pid if 'CassandraDaemon' in open(f'/proc/{pid}/cmdline').read() else None
    except OSError:
        return None


def mine_left():
    out = []
    for p in glob.glob('/proc/[0-9]*/cmdline'):
        try:
            c = open(p).read().replace('\0', ' ')
        except OSError:
            continue
        if 'CassandraDaemon' in c and '/s4-ec-run/' in c:
            out.append((p.split('/')[2], c[:80]))
    return out


def nodetool(node, cmd, timeout=180):
    return sh(f'bin/nodetool -h 127.0.0.1 -p {NODES[node][1]} {cmd}', timeout=timeout, check=False, quiet=True)


def stop_node(node, wait_s=120):
    if pid_of(node) is None:
        return
    nodetool(node, 'stopdaemon', timeout=wait_s)
    for _ in range(wait_s):
        if pid_of(node) is None:
            return
        time.sleep(1)
    pid = pid_of(node)
    if pid is not None:
        note(f'{node} did not stop within {wait_s} s; kill -9 {pid}')
        subprocess.run(['kill', '-9', str(pid)]); time.sleep(3)


def stop_all():
    for n in ('B', 'A'):
        stop_node(n)
    left = mine_left()
    if left:
        log('WARNING: a CassandraDaemon of this harness is still running: ' + str(left))
    return not left


def fail(msg):
    note('FAIL: ' + msg)
    stop_all()
    sys.exit(1)


def client(host_node, *a, timeout=1800):
    rc, out = sh(f'python3 {HARNESS}/client.py {a[0]} {NODES[host_node][0]} ' + ' '.join(str(x) for x in a[1:]), timeout=timeout, check=False,
                 env=dict(os.environ, CASSANDRA_HOME=C, EC_NATIVE_PORT=str(NODES[host_node][2])))
    js = [l for l in out.splitlines() if l.startswith('{')]
    return json.loads(js[-1]) if js else None


def prepare_tools():
    os.makedirs(TOOLS, exist_ok=True)
    cp = f'{C}/build/classes/main:{C}/build/lib/jars/*'
    sh(f'javac -d {TOOLS} {HARNESS}/Jmx.java')
    sh(f'mkdir -p {TOOLS}/eh && javac -d {TOOLS}/eh -cp "{cp}" {HARNESS}/EcHelper.java && cd {TOOLS}/eh && jar cf {TOOLS}/ec-helper.jar EcHelper.class')
    tcp = f'{C}/build/test/classes:{C}/build/classes/main:{C}/build/lib/jars/*:{C}/build/test/lib/jars/*:{C}/test/conf'
    sh(f'mkdir -p {TOOLS}/probe && javac -nowarn -d {TOOLS}/probe -cp "{tcp}" {HARNESS}/EcProbe.java')


def start_node(node, mm, byteman=False, extra_yaml=()):
    if pid_of(node) is not None:
        fail(f'{node} is already running')
    PIDS.pop(node, None)
    _, y = sh(f'{HARNESS}/make-node-yaml.sh {node} {mm} ' + ' '.join(extra_yaml), env=dict(os.environ, CASSANDRA_HOME=C, EC=EC))
    note(y.strip().splitlines()[-1][:1500])
    for port in (NODES[node][1], NODES[node][2]) + ((BM_PORT,) if byteman else ()):
        if sh(f'ss -ltn | grep -c ":{port} "', check=False, quiet=True)[1].strip() not in ('0', ''):
            fail(f'port {port} is not free')
    N = f'{EC}/{node}'
    env = dict(os.environ, CASSANDRA_CONF=N + '/conf', CASSANDRA_LOG_DIR=N + '/logs', MAX_HEAP_SIZE='2G', HEAP_NEWSIZE='400M')
    env.pop('JVM_EXTRA_OPTS', None)
    extra = ''
    if byteman:
        extra = (f'-javaagent:{BM}=listener:true,port:{BM_PORT},sys:{TOOLS}/ec-helper.jar,script:{HARNESS}/ec.btm '
                 f'-Dstage4.trace={TRACE} -Dorg.jboss.byteman.verbose=false')
    note(f'start {node}: MAX_HEAP_SIZE=2G JVM_EXTRA_OPTS="{extra}"')
    sh(f'ulimit -n 100000; JVM_EXTRA_OPTS="{extra}" bin/cassandra -p {N}/cassandra.pid > {N}/stdout.txt 2>&1', env=env)
    for _ in range(30):
        time.sleep(1)
        if pid_of(node) is not None:
            return
    fail(f'{node} did not start; see {N}/stdout.txt')


def status_of(via):
    _, st = nodetool(via, 'status')
    return {a: s for s, a in re.findall(r'^([UD][NLJM])\s+(\S+)\s', st, re.M)}


def wait_up(nodes, timeout=300, others=()):
    t0 = time.time()
    while time.time() - t0 < timeout:
        ok = True
        for via in nodes:
            if pid_of(via) is None:
                fail(f'{via} died during start')
            st = status_of(via)
            _, sb = nodetool(via, 'statusbinary')
            ok = ok and all(st.get(NODES[n][0]) == 'UN' for n in tuple(nodes) + tuple(others)) and re.search(r'^running\s*$', sb, re.M) is not None
        if ok:
            log(f'{nodes} UN and serving after {time.time() - t0:.0f} s')
            return
        time.sleep(3)
    fail(f'{nodes} not UN within the timeout')


def hints_files(node='A'):
    out = []
    try:
        for e in os.scandir(f'{EC}/{node}/hints'):
            out.append((e.name, e.stat().st_size))
    except OSError:
        pass
    return sorted(out)


def jmx_get(node, bean, attr):
    _, o = sh(f'java -cp {TOOLS} Jmx {NODES[node][1]} get {bean} {attr}', check=False, quiet=True, timeout=60)
    m = re.search(r'\|([-0-9.eE+]+)\s*$', o.strip().splitlines()[-1] if o.strip() else '')
    return float(m.group(1)) if m else None


def snapshot(tag, nsmall=200000):
    pid = pid_of('A')
    d = {'tag': tag, 'ms': int(time.time() * 1000)}
    if pid is None:
        d['error'] = 'A not running'; return d
    hp = f'{LOGS}/heap-{tag}.hprof'
    if os.path.exists(hp):
        os.remove(hp)
    sh(f'jcmd {pid} GC.heap_dump {hp}', timeout=600, check=False, quiet=True)
    rc, o = sh(f'python3 -I {HARNESS}/hprof_big.py {hp} {nsmall}', timeout=900, check=False, quiet=True)
    arrays = [int(l.split()[1]) for l in o.splitlines() if l.startswith('bytearray ')]
    tot = [l for l in o.splitlines() if l.startswith('total_bytearrays')]
    d['big_bytearrays'] = arrays
    d['total_bytearrays'] = tot[0] if tot else o[-200:]
    d['heap_dump_bytes'] = os.path.getsize(hp) if os.path.exists(hp) else None
    if os.path.exists(hp):
        os.remove(hp)
    _, tp = sh(f'jcmd {pid} Thread.print', timeout=120, check=False, quiet=True)
    d['hintsdispatcher_threads'] = len(re.findall(r'^"HintsDispatcher', tp, re.M))
    d['direct_used'] = jmx_get('A', 'java.nio:type=BufferPool,name=direct', 'MemoryUsed')
    _, hist = sh(f'jcmd {pid} GC.class_histogram', timeout=120, check=False, quiet=True)
    d['histogram_B'] = ' '.join(next((l for l in hist.splitlines() if l.rstrip().endswith('[B')), '').split())
    rows = trace_rows()
    d['trace_lines'] = len(rows)
    d['trace_last'] = rows[-1] if rows else None
    note('SNAPSHOT ' + json.dumps(d))
    return d


def trace_rows():
    try:
        return [l.strip() for l in open(TRACE, errors='replace') if l.strip()]
    except OSError:
        return []


def kv(line):
    return dict(re.findall(r'(\w+)=(\S+)', line))


def syslog_hits(pattern):
    try:
        return len(re.findall(pattern, open(f'{EC}/A/logs/system.log', errors='replace').read()))
    except OSError:
        return 0


def produce(host_id, groups, flag):
    cmd = (f'rm -rf {C}/build/test/cassandra; java -Xmx2g -ea -javaagent:$(ls {C}/build/lib/jars/jamm-*.jar | head -1) -Dstorage-config={C}/test/conf '
           f'-Dcassandra.config=file://{C}/test/conf/cassandra.yaml -Dio.netty.tryReflectionSetAccessible=true -Dstage4.out={LOGS}/produce.out '
           '--add-exports java.base/jdk.internal.misc=ALL-UNNAMED --add-exports java.base/jdk.internal.ref=ALL-UNNAMED --add-exports java.base/sun.nio.ch=ALL-UNNAMED '
           '--add-exports java.management.rmi/com.sun.jmx.remote.internal.rmi=ALL-UNNAMED --add-exports java.rmi/sun.rmi.registry=ALL-UNNAMED '
           '--add-exports java.rmi/sun.rmi.server=ALL-UNNAMED --add-exports java.rmi/sun.rmi.transport.tcp=ALL-UNNAMED --add-exports java.sql/java.sql=ALL-UNNAMED '
           '--add-opens java.base/java.lang.module=ALL-UNNAMED --add-opens java.base/java.net=ALL-UNNAMED --add-opens java.base/jdk.internal.loader=ALL-UNNAMED '
           '--add-opens java.base/jdk.internal.ref=ALL-UNNAMED --add-opens java.base/jdk.internal.reflect=ALL-UNNAMED --add-opens java.base/jdk.internal.math=ALL-UNNAMED '
           '--add-opens java.base/jdk.internal.module=ALL-UNNAMED --add-opens java.base/jdk.internal.util.jar=ALL-UNNAMED --add-opens jdk.management/com.sun.management.internal=ALL-UNNAMED '
           '--add-opens java.base/java.nio=ALL-UNNAMED --add-opens java.base/java.lang=ALL-UNNAMED '
           f'-cp "{TOOLS}/probe:{C}/build/test/classes:{C}/build/classes/main:{C}/build/lib/jars/*:{C}/build/test/lib/jars/*:{C}/test/conf" '
           f'org.apache.cassandra.hints.EcProbe produce {TAG} {EC}/A/hints {host_id} {groups} {flag} > {LOGS}/produce.log 2>&1 < /dev/null')
    sh(cmd, timeout=900)
    blocks = []
    for l in open(f'{LOGS}/produce.out'):
        m = re.match(r'STAGE4 block \S+ idx=\d+ enc=(\d+) plain=(\d+)', l)
        if m:
            blocks.append((int(m.group(1)), int(m.group(2))))
    return blocks


def cell(tag, mm, groups, flag):
    note(f'cluster-run cell {tag} mm={mm} groups={groups} flag={flag or "-"} {time.strftime("%F %T %Z")} host {os.uname().nodename.split(".")[0]} clone {C} run {RUN}')
    note('harness md5: ' + sh('md5sum cluster-run.py client.py make-node-yaml.sh Jmx.java EcHelper.java EcProbe.java ec.btm hprof_big.py', quiet=True, cwd=HARNESS)[1].replace('\n', ' ')[:900])
    sh(f'rm -rf {EC}/A {EC}/B', check=False)
    os.makedirs(EC, exist_ok=True)
    prepare_tools()
    start_node('A', mm); start_node('B', 'default')
    wait_up(('A', 'B'))
    r = client('A', 'schemaid', 'ks', 2, TABLE_ID)
    expect('table ks.t created WITH ID, schema agreement', bool(r and r.get('ok') and r.get('schema_agreement')))
    pr = client('B', 'probe')
    host_id = pr['host_id']
    note(f'B host id {host_id}')
    stop_node('A')
    blocks = produce(host_id, groups, flag)
    files = hints_files()
    note(f'produced {files}; raw blocks (enc,plain): count={len(blocks)} max_enc={max([b[0] for b in blocks] or [0])} first={blocks[:3]}')
    max_enc = max([b[0] for b in blocks] or [0])
    logpos = os.path.getsize(f'{EC}/A/logs/system.log') if os.path.exists(f'{EC}/A/logs/system.log') else 0
    start_node('A', mm, byteman=True)
    t_start = time.time()
    # A is up when its log says so (a failed forged dispatch stops A's transports, so UN/binary checks would race with it)
    for _ in range(240):
        time.sleep(1)
        if pid_of('A') is None:
            fail('A died during start')
        with open(f'{EC}/A/logs/system.log', errors='replace') as lf:
            lf.seek(logpos)
            if 'Startup complete' in lf.read():
                break
    else:
        fail('A: no Startup complete within 240 s')
    log(f'A startup complete after {time.time() - t_start:.0f} s')
    # wait for the dispatch to end
    t_end = None
    for _ in range(600):
        time.sleep(1)
        if pid_of('A') is None:
            fail('A died')
        done = syslog_hits(r'Finished hinted handoff of file') > 0 or syslog_hits(r'Failed to dispatch hints file') > 0
        if flag == 'forged':
            done = syslog_hits(r'Failed to dispatch hints file') > 0
        if (flag == 'forged' or not [f for f in hints_files() if f[0].endswith('.hints')]) and done:
            t_end = time.time(); break
    note(f'dispatch end {"after %.0f s from A start" % (t_end - t_start) if t_end else "NOT seen within 600 s"}; hints dir now {hints_files()}; '
         f'log: finished={syslog_hits("Finished hinted handoff of file")} failed={syslog_hits("Failed to dispatch hints file")} ignoring_encryption={syslog_hits("ignoring encryption")}')
    note('after dispatch: system.log hits: ' + ', '.join(f'{k}={syslog_hits(k)}' for k in ('Stop listening for CQL clients', 'Stopping gossiper', 'Stop listening', 'disk failure', 'FSReadError', 'markCorrupted', 'corrupt')))
    note('hints dir listing: ' + str(hints_files()))
    snaps = []
    if t_end:
        for dt in (10, 30, 150):
            while time.time() < t_end + dt:
                time.sleep(1)
            snaps.append(snapshot(f'p{dt}'))
    # B applied the hints?
    cnt = client('B', 'count', 'ks')
    note(f'rows on B after dispatch: {cnt}')
    rows = trace_rows()
    kind = tag.split('_')[0]
    outs = [kv(l) for l in rows if l.startswith('out ')]
    excs = [kv(l) for l in rows if l.startswith('exc ')]
    ins = [kv(l) for l in rows if l.startswith('in ')]
    note(f'trace: in={len(ins)} out={len(outs)} exc={len(excs)}; distinct reader threads={sorted({o["th"] for o in ins})}')
    expect('dispatch ended (file consumed or failed)', t_end is not None)
    if flag == 'plain':
        expect('plain control: the encrypted reader never ran (no trace lines)', len(rows) == 0)
        expect('plain control: no byte[] >= 2 MiB in any live heap dump (the node itself holds 1 MiB arrays)', all(max(s.get('big_bytearrays') or [0]) < 2 * MIB for s in snaps))
    elif flag == 'forged':
        expect('forged: readBuffer left by an exception', len(excs) >= 1)
        expect('forged: thread-local capacity unchanged by the failed read (tl after == tl before)', bool(excs and ins and excs[-1]['tl'] == ins[-1]['tl']))
        da = [int(e['alloc']) - int(i['alloc']) for e, i in zip(excs, ins[-len(excs):])] if excs else []
        expect('forged: >= 512 MiB allocated on the reading thread during the failed read', bool(da) and max(da) >= 512 * MIB)
        expect('forged: no byte[] >= 64 MiB retained in any live heap dump (the 512 MiB array is garbage)', all(max(s.get('big_bytearrays') or [0]) < 64 * MIB for s in snaps))
    else:
        lo, hi = BAND[kind]
        last_tl = int(outs[-1]['tl']) if outs else -1
        expect(f'retained capacity (trace, last out) {last_tl} is in the frozen band [{lo}, {hi}]', lo <= last_tl <= hi)
        expect(f'retained capacity equals the largest raw encrypted block {max_enc}', last_tl == max_enc)
        expect('every read ran on one thread', len({o["th"] for o in outs}) == 1)
        for s in snaps[:2]:
            expect(f'live heap dump {s["tag"]}: a byte[] of exactly {max_enc} bytes is retained', max_enc in s.get('big_bytearrays', []))
        if snaps:
            expect('dispatcher thread alive at +10 s', snaps[0].get('hintsdispatcher_threads', 0) >= 1)
    note(f'summary {tag}: EXPECTED yes={EXPECT["yes"]} no={EXPECT["no"]}')
    json.dump({'tag': tag, 'mm': mm, 'groups': groups, 'flag': flag, 'host_id': host_id, 'blocks': blocks, 'max_enc': max_enc, 'snapshots': snaps,
               'dispatch_end_s': (t_end - t_start) if t_end else None}, open(f'{LOGS}/cell.json', 'w'), indent=1)
    for src, dst in ((f'{EC}/A/logs/system.log', 'A-system.log'), (f'{EC}/B/logs/system.log', 'B-system.log')):
        sh(f'cp {src} {LOGS}/{dst}', check=False, quiet=True)
    stop_all()
    expect('no CassandraDaemon of this harness left', not mine_left())


def pos(tag, mhfs):
    note(f'cluster-run pos {tag} max_hints_file_size={mhfs} {time.strftime("%F %T %Z")} run {RUN}')
    sh(f'rm -rf {EC}/A {EC}/B', check=False)
    os.makedirs(EC, exist_ok=True)
    prepare_tools()
    extra = [] if mhfs == 'default' else [f'max_hints_file_size={mhfs}']
    start_node('A', 'default', extra_yaml=extra); start_node('B', 'default')
    wait_up(('A', 'B'))
    client('A', 'schema', 'hc', 2, 0)
    stop_node('B')
    for _ in range(60):
        if status_of('A').get(NODES['B'][0]) == 'DN':
            break
        time.sleep(2)
    r = client('A', 'write', 'hc', MIB, 200, 4, 0, 600, f'{LOGS}/keys.csv')
    note(f'write: {r}')
    time.sleep(8)
    sizes = []
    for _ in range(10):
        s2 = hints_files()
        if s2 == sizes:
            break
        sizes = s2; time.sleep(3)
    hs = [s for _, s in sizes if True]
    note(f'hints files: count={len(sizes)} sizes={hs} total={sum(hs)} max={max(hs or [0])}')
    json.dump({'tag': tag, 'max_hints_file_size': mhfs, 'files': sizes, 'write': r}, open(f'{LOGS}/pos.json', 'w'), indent=1)
    if mhfs == 'default':
        expect('default: few files (<= 3), total >= 190 MiB', len(sizes) <= 3 and sum(hs) >= 190 * MIB)
    else:
        expect('4 MiB cap: about 50 files (>= 40), none above 4 MiB + one hint (5.1 MiB)', len(sizes) >= 40 and max(hs) <= 4 * MIB + 1100 * KIB)
    stop_all()
    expect('no CassandraDaemon of this harness left', not mine_left())


def run_all():
    for tag, mm, groups, flag in CELLS:
        sub = [sys.executable, os.path.abspath(__file__), 'cell', tag, mm, groups] + ([flag] if flag else [])
        note(f'--- {tag}'); r = subprocess.run(sub, env=os.environ)
        note(f'--- {tag} rc={r.returncode}')
    for tag, v in (('pos_default', 'default'), ('pos_4mib', '4MiB')):
        r = subprocess.run([sys.executable, os.path.abspath(__file__), 'pos', tag, v], env=os.environ)
        note(f'--- {tag} rc={r.returncode}')


try:
    if MODE == 'cell':
        cell(args[1], args[2], args[3], args[4] if len(args) > 4 else '')
    elif MODE == 'pos':
        pos(args[1], args[2])
    elif MODE == 'all':
        run_all()
    else:
        note('stopped: ' + str(stop_all()))
except SystemExit:
    raise
except BaseException as e:
    note(f'EXCEPTION {e!r}')
    stop_all()
    raise
finally:
    if MODE in ('cell', 'pos'):
        stop_all()
