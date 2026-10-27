#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of group-limit-isdone-groupcounted--autonomous (case-file sha256 in the results file section 1; audit
amendments A6-A10 = section D of the case file).
usage: cluster-run.py <run-name> [shakedown]     (a background job; every exit stops the node)
Output: ~/s4-b11-g72-logs/<run-name>/cluster/ (cells.jsonl, session.log, heap.csv, g72.trace, gc.log, system.log excerpts, summary.txt).
Node: one, on loopback 127.0.2.1 (port slot 2): JMX 7120, Byteman script only (no listener; agent port 19120 reserved), native 9042 on 127.0.2.1.
Data on /dev/shm (tmpfs). Heap 512 MB. Client: bundled Python driver, protocol 4, in this process (audit A10).
Steps (B3e as amended):  start node -> schema -> load ks.t (1 partition x 500000 rows x 1 KB) and ks.g (20000 partitions x 1 row x 1 KB)
 -> flush, compact -> FIRST-TRIGGER CHECK (many-groups L=1 P=100 must show groups=1 done=true rows=1 in the Byteman trace; else stop)
 -> cells: drift (S L=none P=10000), S {P=10000,100} x {L=1,100000,none}, drift again, control SELECT * LIMIT {1000,10000,50000} (paging off),
    many-groups G {P=100,10000} x {L=1,100,5000,none}. Each cell: 1 warm-up, then reps timed queries. Per timed query: JVM-wide allocated bytes
    before/after (JMX sum of thread allocated bytes), epoch-ms window (the heap poller and the Byteman trace are joined to it by analysis).
Env: G72_SCALE (1; divides the row counts, shakedown knob), G72_REPS (5)."""
import glob, json, os, re, signal, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
H = os.path.dirname(os.path.abspath(__file__))
RUNNAME = sys.argv[1] if len(sys.argv) > 1 else sys.exit(__doc__)
SHAKE = len(sys.argv) > 2 and sys.argv[2] == 'shakedown'
SCALE = int(os.environ.get('G72_SCALE', 50 if SHAKE else 1))
REPS = int(os.environ.get('G72_REPS', 2 if SHAKE else 5))
C = os.environ.get('CASSANDRA_HOME', f'{HOME}/s4-b11-g72-c')
SLOT = 2
ADDR = f'127.0.{SLOT}.1'
JMX = 7100 + SLOT * 10
BMPORT = 19100 + SLOT * 10
RUN = f'/dev/shm/s4-b11-g72-{RUNNAME}'
LOGS = f'{HOME}/s4-b11-g72-logs/{RUNNAME}/cluster'
BYTEMAN = f'{C}/build/lib/jars/byteman-4.0.20.jar'
N_S = 500000 // SCALE          # rows in the single group
N_G = 20000 // SCALE           # partitions of the many-groups table
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
ENV = dict(os.environ, CASSANDRA_CONF=RUN + '/conf', CASSANDRA_LOG_DIR=RUN + '/logs', MAX_HEAP_SIZE='512M', CASSANDRA_HOME=C)
ENV.pop('HEAP_NEWSIZE', None)
ENV.pop('JVM_EXTRA_OPTS', None)

# ---- bundled Python driver (as client.py of the range_tombstone harness) ----
LIB = os.path.join(C, 'lib')
def _zip(prefix):
    z = glob.glob(os.path.join(LIB, prefix + '*.zip'))
    return max(z) if z else None
_cql = _zip('cassandra-driver-internal-only-')
_ver = os.path.splitext(os.path.basename(_cql))[0][len('cassandra-driver-internal-only-'):]
sys.path.insert(0, os.path.join(_cql, 'cassandra-driver-' + _ver))
for _l in ('pure_sasl-', 'wcwidth-', 'pyasyncore-'):
    _z = _zip(_l)
    if _z:
        sys.path.insert(0, _z)
from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT  # noqa: E402
from cassandra.policies import WhiteListRoundRobinPolicy, FallthroughRetryPolicy  # noqa: E402
from cassandra.query import SimpleStatement  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, flush=True)
    SESSION.write(line + '\n'); SESSION.flush()


def sh(cmd, timeout=900, check=True, quiet=False):
    log('+ ' + cmd[:300])
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=ENV, cwd=C)
    except subprocess.TimeoutExpired:
        log(f'  TIMEOUT after {timeout} s')
        if check:
            raise RuntimeError('timeout: ' + cmd)
        return 124, ''
    out = (r.stdout or '') + (r.stderr or '')
    if not quiet:
        SESSION.write(out[-2000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'rc={r.returncode}: {cmd}\n{out[-1500:]}')
    return r.returncode, out


def node_pid():
    try:
        pid = int(open(RUN + '/cassandra.pid').read().strip())
        return pid if 'CassandraDaemon' in open(f'/proc/{pid}/cmdline').read() else None
    except (OSError, ValueError):
        return None


def my_daemons():
    _, out = sh("ps -eo pid,args | grep -E '^ *[0-9]+ [^ ]*java .*CassandraDaemon' || true", check=False, quiet=True)
    return [l for l in out.splitlines() if RUN + '/' in l]


def nodetool(args, timeout=600):
    return sh(f'bin/nodetool -h 127.0.0.1 -p {JMX} {args}', timeout=timeout, check=False, quiet=True)


def stop_node():
    pid = node_pid()
    if pid is None:
        return
    log(f'stopping node pid {pid}')
    sh(f'kill {pid}', check=False)
    for _ in range(180):
        if not os.path.exists(f'/proc/{pid}'):
            log('node stopped'); return
        time.sleep(1)
    sh(f'kill -9 {pid}', check=False); time.sleep(2)


def make_conf():
    conf = RUN + '/conf'
    sh(f'rm -rf {conf} && cp -r {C}/conf {conf}')
    lines = {
        'cluster_name': "'g72'",
        'data_file_directories': f'\n    - {RUN}/data',
        'commitlog_directory': f'{RUN}/commitlog', 'hints_directory': f'{RUN}/hints',
        'saved_caches_directory': f'{RUN}/saved_caches', 'cdc_raw_directory': f'{RUN}/cdc_raw',
        'commitlog_total_space': '1024MiB',
        'listen_address': ADDR, 'rpc_address': ADDR,
        'seed_provider': f'\n  - class_name: org.apache.cassandra.locator.SimpleSeedProvider\n    parameters:\n      - seeds: "{ADDR}:7000"',
        'num_tokens': '16',
        'native_transport_timeout': '600s',          # a full scan at P=100 holds one request for many seconds (HANDOFF lesson)
        'row_cache_size': '0MiB',
        'range_request_timeout': '600000ms', 'read_request_timeout': '600000ms', 'request_timeout': '600000ms',   # defect D1: the 10 s range deadline spans all sub-pages
    }
    out, skip = [], False
    for l in open(C + '/conf/cassandra.yaml').read().splitlines():
        m = re.match(r'^([A-Za-z_]+):', l)
        if m:
            skip = m.group(1) in lines
            if skip:
                continue
        elif skip and (l.startswith((' ', '\t', '-')) or l.strip() == ''):
            continue
        else:
            skip = False
        out.append(l)
    out.append('# ---- stage4 g72 (B3a as amended) ----')
    out += [f'{k}: {v}' for k, v in lines.items()]
    open(conf + '/cassandra.yaml', 'w').write('\n'.join(out) + '\n')
    env = open(conf + '/cassandra-env.sh').read()
    assert env.count('JMX_PORT="7199"') == 1
    open(conf + '/cassandra-env.sh', 'w').write(env.replace('JMX_PORT="7199"', f'JMX_PORT="{JMX}"'))
    with open(conf + '/jvm11-server.options', 'a') as fo:
        fo.write(f'\n# stage4 g72\n-XX:-HeapDumpOnOutOfMemoryError\n-Xlog:gc*:file={RUN}/logs/gc.log:time,uptime:filecount=10,filesize=100M\n')
        fo.write(f'-javaagent:{BYTEMAN}=script:{H}/groupby.btm\n-Dstage4.trace={RUN}/logs/g72.trace\n')
    log('conf: ' + '; '.join(f'{k}={v.strip()}' for k, v in lines.items() if '\n' not in v) + f'; JMX {JMX}; heap 512M; Byteman script only (agent port {BMPORT} reserved)')


def start_node():
    if node_pid() is not None or my_daemons():
        raise RuntimeError('a CassandraDaemon of this run is already running')
    sh(f'bash -c "ulimit -n 100000; bin/cassandra -p {RUN}/cassandra.pid > {RUN}/logs/start.out 2>&1"')
    t0 = time.time()
    while time.time() - t0 < 300:
        time.sleep(3)
        if node_pid() is None and time.time() - t0 > 20:
            raise RuntimeError('daemon died during start: ' + open(f'{RUN}/logs/start.out', errors='replace').read()[-800:])
        rc, out = nodetool('status', timeout=60)
        if re.search(r'^UN\s+' + re.escape(ADDR), out, re.M):
            rc2, out2 = nodetool('statusbinary', timeout=60)
            if out2.strip() == 'running':
                log(f'node up after {time.time() - t0:.0f} s, pid {node_pid()}')
                return node_pid()
    raise RuntimeError('node did not come up')


# ---- JMX helper process ----
class Jmx:
    def __init__(self):
        sh(f'mkdir -p {RUN}/tools && javac -d {RUN}/tools {H}/G72Jmx.java', quiet=True)
        self.p = subprocess.Popen(['java', '-cp', f'{RUN}/tools', 'G72Jmx', str(JMX), 'serve'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)

    def ask(self, cmd):
        self.p.stdin.write(cmd + '\n'); self.p.stdin.flush()
        return self.p.stdout.readline().split()

    def alloc(self):
        r = self.ask('alloc'); return int(r[1]), int(r[2])

    def heap(self):
        r = self.ask('heap'); return int(r[1]), int(r[2])

    def close(self):
        try:
            self.p.stdin.write('quit\n'); self.p.stdin.flush(); self.p.wait(timeout=10)
        except Exception:
            self.p.kill()


def connect():
    prof = ExecutionProfile(request_timeout=900, consistency_level=ConsistencyLevel.ONE, retry_policy=FallthroughRetryPolicy(),
                            load_balancing_policy=WhiteListRoundRobinPolicy([ADDR]))
    c = Cluster([ADDR], port=9042, protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof}, connect_timeout=30)
    return c, c.connect()


def load(session, stmt, gen, conc=64):
    sem = threading.BoundedSemaphore(conc); errors = []
    def ok(_): sem.release()
    def bad(e): errors.append(str(e)); sem.release()
    n = 0
    for args in gen:
        sem.acquire()
        session.execute_async(stmt, args).add_callbacks(ok, bad)
        n += 1
        if n % 100000 == 0:
            log(f'  loaded {n}')
    for _ in range(conc):
        sem.acquire()
    return n, errors


def trace_lines(since_ms=0, until_ms=None):
    out = []
    try:
        for l in open(RUN + '/logs/g72.trace', errors='replace'):
            m = re.search(r'GB ms=(\d+) rows=(\d+) groups=(\d+) unfinished=(\w+) done=(\w+)', l)
            if m and int(m.group(1)) >= since_ms and (until_ms is None or int(m.group(1)) <= until_ms):
                out.append((int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4), m.group(5)))
    except OSError:
        pass
    return out


def run_query(session, jmx, cells, ds, cql, p, l, rep, warm):
    st = SimpleStatement(cql, fetch_size=(p if p else None))
    a0 = jmx.alloc()
    t0 = int(time.time() * 1000)
    err, n = None, 0
    try:
        for _ in session.execute(st):
            n += 1
    except Exception as e:
        err = repr(e)[:300]
    t1 = int(time.time() * 1000)
    a1 = jmx.alloc()
    rec = dict(ds=ds, L=l, P=p, rep=rep, warm=warm, t0=t0, t1=t1, rows_returned=n, alloc_bytes=a1[1] - a0[1], wall_ms=t1 - t0, error=err, cql=cql)
    cells.write(json.dumps(rec) + '\n'); cells.flush()
    log(f'  {ds} L={l} P={p} rep={rep}{" warm" if warm else ""}: rows_returned={n} wall={t1 - t0} ms alloc={a1[1] - a0[1]} err={err}')
    return rec


def idle_baseline(jmx, cells, secs=5):
    a0 = jmx.alloc(); time.sleep(secs); a1 = jmx.alloc()
    rec = dict(ds='idle', t0=a0[0], t1=a1[0], alloc_bytes=a1[1] - a0[1], wall_ms=a1[0] - a0[0])
    cells.write(json.dumps(rec) + '\n'); cells.flush()
    log(f'  idle {secs} s: alloc={rec["alloc_bytes"]}')


def main():
    stopfile = RUN + '/heap.stop'
    poller = None
    session = cluster = jmx = None
    try:
        sh(f'rm -rf {RUN} && mkdir -p {RUN}/logs {RUN}/data {RUN}/commitlog {RUN}/hints {RUN}/saved_caches {RUN}/cdc_raw', quiet=True)
        log(f'cluster-run {RUNNAME}{" SHAKEDOWN" if SHAKE else ""}: scale {SCALE}, reps {REPS}, N_S {N_S}, N_G {N_G}, host {os.uname().nodename}, df {sh("df -h /dev/shm | tail -1", quiet=True)[1].strip()}')
        rc, out = sh(f"ss -ltn | grep -E '({ADDR}:(9042|7000)|:{JMX}|:{BMPORT}) ' || true", check=False, quiet=True)
        assert not out.strip(), 'port busy: ' + out
        make_conf()
        pid = start_node()
        jmx = Jmx()
        poller = subprocess.Popen(['java', '-cp', f'{RUN}/tools', 'G72Jmx', str(JMX), 'poll', f'{LOGS}/heap.csv', '100', stopfile])
        cluster, session = connect()
        session.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
        session.execute('CREATE TABLE IF NOT EXISTS ks.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck))')
        session.execute('CREATE TABLE IF NOT EXISTS ks.g (pk int, ck int, v blob, PRIMARY KEY (pk, ck))')
        cluster.control_connection.wait_for_schema_agreement(wait_time=60)
        ins_t = session.prepare('INSERT INTO ks.t (pk, ck, v) VALUES (1, ?, ?)')
        ins_g = session.prepare('INSERT INTO ks.g (pk, ck, v) VALUES (?, 0, ?)')
        t0 = time.time()
        n, errs = load(session, ins_t, ((i, os.urandom(1024)) for i in range(N_S)))
        log(f'loaded ks.t: {n} rows, {len(errs)} errors, {time.time() - t0:.0f} s {errs[:2]}')
        assert not errs, 'load errors'
        n, errs = load(session, ins_g, ((i, os.urandom(1024)) for i in range(N_G)))
        log(f'loaded ks.g: {n} rows, {len(errs)} errors {errs[:2]}')
        assert not errs, 'load errors'
        nodetool('flush', 900)
        nodetool('compact ks t', 1800)
        nodetool('compact ks g', 600)
        _, du = sh(f'du -sb {RUN}/data | cut -f1', quiet=True)
        log(f'data on disk after compaction: {du.strip()} bytes; tablestats: ' + ' '.join(re.findall(r'(?:Space used \(live\)|SSTable count)[^\n]*', nodetool('tablestats ks.t', 120)[1])))
        sh(f'jcmd {pid} GC.run', check=False, quiet=True)
        cells = open(LOGS + '/cells.jsonl', 'a')
        # ---- FIRST-TRIGGER CHECK: the disallow branch can fire (many-groups, L=1, P=100) ----
        m0 = int(time.time() * 1000)
        r = run_query(session, jmx, cells, 'G', 'SELECT pk, count(*) FROM ks.g GROUP BY pk LIMIT 1', 100, 1, 0, True)
        time.sleep(2)
        tl = trace_lines(m0)
        log(f'FIRST-TRIGGER CHECK trace lines since query start: {tl}')
        if not (r['error'] is None and r['rows_returned'] == 1 and any(g == 1 and d == 'true' and rw == 1 for _, rw, g, u, d in tl)):
            raise RuntimeError('FIRST-TRIGGER CHECK FAILED: many-groups L=1 P=100 did not show rows=1 groups=1 done=true in the Byteman trace; stop')
        log('FIRST-TRIGGER CHECK passed')

        def cell(ds, cql_fmt, p, l, reps, warm=True):
            cql = cql_fmt if l is None else cql_fmt.format(l=l)
            sh(f'jcmd {pid} GC.run', check=False, quiet=True)
            idle_baseline(jmx, cells)
            if warm:
                run_query(session, jmx, cells, ds, cql, p, l if l is not None else 'none', 0, True)
            for rep in range(1, reps + 1):
                run_query(session, jmx, cells, ds, cql, p, l if l is not None else 'none', rep, False)
                time.sleep(1)

        SQ = 'SELECT pk, count(*) FROM ks.t GROUP BY pk LIMIT {l}'
        SN = 'SELECT pk, count(*) FROM ks.t GROUP BY pk'
        GQ = 'SELECT pk, count(*) FROM ks.g GROUP BY pk LIMIT {l}'
        GN = 'SELECT pk, count(*) FROM ks.g GROUP BY pk'
        L_BIG = 100000 // SCALE
        log('== drift cell (start)')
        cell('S', SN, 10000, None, 3)
        for p in (10000, 100):
            for l in (1, L_BIG, None):
                log(f'== S P={p} L={l}')
                cell('S', SQ if l else SN, p, l, REPS)
        log('== drift cell (end)')
        cell('S', SN, 10000, None, 3)
        for l in (1000 // SCALE, 10000 // SCALE, 50000 // SCALE):
            log(f'== control SELECT * LIMIT {l}')
            cell('C', 'SELECT * FROM ks.t WHERE pk = 1 LIMIT {l}', 0, l, 3)
        for p in (100, 10000):
            for l in (1, 100, 5000 // SCALE, None):
                log(f'== G P={p} L={l}')
                cell('G', GQ if l else GN, p, l, 3)
        log('all cells done')
        return 0
    finally:
        log('cleanup: stopping poller, helper, node')
        try:
            open(stopfile, 'w').write('x')
            if poller:
                poller.wait(timeout=20)
        except Exception as e:
            log(f'poller: {e}')
        if jmx:
            jmx.close()
        if cluster:
            try: cluster.shutdown()
            except Exception: pass
        stop_node()
        for f in ('gc.log', 'g72.trace', 'system.log', 'debug.log', 'start.out'):
            for src in glob.glob(f'{RUN}/logs/{f}*'):
                sh(f'cp {src} {LOGS}/ 2>/dev/null', check=False, quiet=True)
        log(f'leftover CassandraDaemon of this run: {my_daemons()}')
        sh(f'rm -rf {RUN}', check=False, quiet=True)
        log(f'tmpfs dir removed: {not os.path.exists(RUN)}')


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        log(f'FAILED: {e!r}')
        sys.exit(1)
