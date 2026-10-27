#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of group-by-row-limit-incrementRowCount-rowsCounted--autonomous (case-file sha256 in the results file
section 1; audit amendments A6-A9 = section D of the case file).
usage: cluster-run.py <run-name> [shakedown]     (a background job; every exit stops both nodes)
Output: ~/s4-b11-b78-logs/<run-name>/cluster/ (cells.jsonl, session.log, heap-n1.csv, heap-n2.csv, b78-n1.trace, b78-n2.trace, gc-n1.log,
        gc-n2.log, system-n*.log, gcrun.jsonl).
Nodes: two JVMs on loopback 127.0.8.1 / 127.0.8.2 (port slot 8): JMX 7180 / 7181, native 9042 on each, internode 7000 on each. Data on /dev/shm.
Heap 512 MB each for the measured phase (2 GiB while loading, amendment A12), PasswordAuthenticator, ordinary role `app` (superusers skip guardrails). Client: bundled Python driver, protocol 4, node 1 only.
Steps (B3e as amended): start n1, n2 -> roles, keyspace ks (RF 2), ks.t (200000 rows x 4 KiB, one partition), ks.s (200000 x 100 B), ks.k (10 rows)
 -> flush, compact -> idle baseline 30 s -> CALIBRATION + FIRST-TRIGGER CHECK (Byteman trace of a fetch-1000 GROUP BY must show rows=1000
 unfinished=true groups=0; else stop) -> per fetch size in 100, 1000, 10000, 100000, 1000000, unset: [restart a dead node], full GC on both,
 3 x GROUP BY, 3 x plain SELECT * control -> small-row control (ks.s, fetch 10000 and 100000) -> guardrail arm (n1 restarted with
 page_size_fail_threshold 20000): fetch 10000 passes, fetch 100000 fails.
Env: B78_SCALE (1; divides the row counts, shakedown knob)."""
import glob, json, os, re, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
H = os.path.dirname(os.path.abspath(__file__))
RUNNAME = sys.argv[1] if len(sys.argv) > 1 else sys.exit(__doc__)
SHAKE = len(sys.argv) > 2 and sys.argv[2] == 'shakedown'
SCALE = int(os.environ.get('B78_SCALE', 50 if SHAKE else 1))
C = os.environ.get('CASSANDRA_HOME', f'{HOME}/s4-b11-b78-c')
SLOT = 8
RUN = f'/dev/shm/s4-b11-b78-{RUNNAME}'
LOGS = f'{HOME}/s4-b11-b78-logs/{RUNNAME}/cluster'
BYTEMAN = f'{C}/build/lib/jars/byteman-4.0.20.jar'
N_T = 200000 // SCALE
N_S = 200000 // SCALE
FETCH = [100, 1000, 10000, 100000, 1000000, None]
REPS = 3
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')

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
from cassandra.auth import PlainTextAuthProvider  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, flush=True)
    SESSION.write(line + '\n'); SESSION.flush()


def sh(cmd, timeout=900, check=True, quiet=False, env=None):
    log('+ ' + cmd[:300])
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env or os.environ, cwd=C)
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


class Node:
    def __init__(self, idx):
        self.idx = idx
        self.addr = f'127.0.{SLOT}.{idx}'
        self.jmx = 7100 + SLOT * 10 + (idx - 1)
        self.dir = f'{RUN}/n{idx}'
        self.env = dict(os.environ, CASSANDRA_CONF=self.dir + '/conf', CASSANDRA_LOG_DIR=self.dir + '/logs', MAX_HEAP_SIZE='2G', CASSANDRA_HOME=C)       # 2G only for the load phase; set to 512M for the measured phase (case-file amendment A12)
        self.env.pop('HEAP_NEWSIZE', None); self.env.pop('JVM_EXTRA_OPTS', None)
        self.poller = None
        self.restarts = 0

    def pid(self):
        try:
            pid = int(open(self.dir + '/cassandra.pid').read().strip())
            return pid if 'CassandraDaemon' in open(f'/proc/{pid}/cmdline').read() else None
        except (OSError, ValueError):
            return None

    def make_conf(self, extra=None):
        conf = self.dir + '/conf'
        sh(f'rm -rf {conf} && cp -r {C}/conf {conf}', quiet=True)
        lines = {
            'cluster_name': "'b78'",
            'authenticator': 'PasswordAuthenticator',
            'data_file_directories': f'\n    - {self.dir}/data',
            'commitlog_directory': f'{self.dir}/commitlog', 'hints_directory': f'{self.dir}/hints',
            'saved_caches_directory': f'{self.dir}/saved_caches', 'cdc_raw_directory': f'{self.dir}/cdc_raw',
            'commitlog_total_space': '1024MiB',
            'listen_address': self.addr, 'rpc_address': self.addr,
            'seed_provider': f'\n  - class_name: org.apache.cassandra.locator.SimpleSeedProvider\n    parameters:\n      - seeds: "127.0.{SLOT}.1:7000"',
            'num_tokens': '16',
            'native_transport_timeout': '600s',
            'row_cache_size': '0MiB',
            'range_request_timeout': '600000ms', 'read_request_timeout': '600000ms', 'request_timeout': '600000ms',
            'write_request_timeout': '60000ms',
        }
        if extra:
            lines.update(extra)
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
        out.append('# ---- stage4 b78 (B3a as amended) ----')
        out += [f'{k}: {v}' for k, v in lines.items()]
        open(conf + '/cassandra.yaml', 'w').write('\n'.join(out) + '\n')
        env = open(conf + '/cassandra-env.sh').read()
        assert env.count('JMX_PORT="7199"') == 1
        open(conf + '/cassandra-env.sh', 'w').write(env.replace('JMX_PORT="7199"', f'JMX_PORT="{self.jmx}"'))
        with open(conf + '/jvm11-server.options', 'a') as fo:
            fo.write(f'\n# stage4 b78\n-XX:-HeapDumpOnOutOfMemoryError\n-Dcassandra.ring_delay_ms=10000\n')
            fo.write(f'-Xlog:gc*:file={self.dir}/logs/gc.log:time,uptime:filecount=20,filesize=100M\n')
            fo.write(f'-javaagent:{BYTEMAN}=script:{H}/rowlimit.btm\n-Dstage4.trace={self.dir}/logs/b78.trace\n')
        log(f'n{self.idx} conf: ' + '; '.join(f'{k}={v.strip()}' for k, v in lines.items() if '\n' not in v) + f'; JMX {self.jmx}; heap {self.env["MAX_HEAP_SIZE"]}')

    def nodetool(self, args, timeout=600):
        return sh(f'bin/nodetool -h 127.0.0.1 -p {self.jmx} {args}', timeout=timeout, check=False, quiet=True, env=self.env)

    def start(self):
        if self.pid() is not None:
            raise RuntimeError(f'n{self.idx} already running')
        sh(f'bash -c "ulimit -n 100000; bin/cassandra -p {self.dir}/cassandra.pid >> {self.dir}/logs/start.out 2>&1"', env=self.env)
        t0 = time.time()
        while time.time() - t0 < 420:
            time.sleep(3)
            if self.pid() is None and time.time() - t0 > 20:
                raise RuntimeError(f'n{self.idx} died during start: ' + open(f'{self.dir}/logs/start.out', errors='replace').read()[-800:])
            rc, out = self.nodetool('status', timeout=60)
            if re.search(r'^UN\s+' + re.escape(self.addr), out, re.M):
                rc2, out2 = self.nodetool('statusbinary', timeout=60)
                if out2.strip() == 'running':
                    log(f'n{self.idx} up after {time.time() - t0:.0f} s, pid {self.pid()}')
                    return
        raise RuntimeError(f'n{self.idx} did not come up')

    def stop(self):
        pid = self.pid()
        if pid is None:
            return
        log(f'stopping n{self.idx} pid {pid}')
        sh(f'kill {pid}', check=False)
        for _ in range(180):
            if not os.path.exists(f'/proc/{pid}'):
                log(f'n{self.idx} stopped'); return
            time.sleep(1)
        sh(f'kill -9 {pid}', check=False); time.sleep(2)

    def start_poller(self):
        self.stopfile = f'{self.dir}/heap.stop'
        if os.path.exists(self.stopfile):
            os.remove(self.stopfile)
        self.poller = subprocess.Popen(['java', '-cp', f'{RUN}/tools', 'B78Jmx', str(self.jmx), 'poll', f'{LOGS}/heap-n{self.idx}.csv', '100', self.stopfile])

    def stop_poller(self):
        try:
            open(self.stopfile, 'w').write('x')
            if self.poller:
                self.poller.wait(timeout=20)
        except Exception as e:
            log(f'poller n{self.idx}: {e}')
        self.poller = None

    def gcrun(self):
        pid = self.pid()
        t0 = int(time.time() * 1000)
        sh(f'jcmd {pid} GC.run', check=False, quiet=True)
        return dict(node=self.idx, t0=t0, t1=int(time.time() * 1000))


NODES = [Node(1), Node(2)]
N1, N2 = NODES


CL = {}


def connect(user='app', pw='app'):
    prof = ExecutionProfile(request_timeout=900, consistency_level=ConsistencyLevel.ONE, retry_policy=FallthroughRetryPolicy(),
                            load_balancing_policy=WhiteListRoundRobinPolicy([N1.addr]))
    c = Cluster([N1.addr], port=9042, protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof}, connect_timeout=30,
                auth_provider=PlainTextAuthProvider(user, pw))
    for attempt in range(30):
        try:
            s = c.connect()
            CL['cluster'], CL['session'] = c, s
            return c, s
        except Exception as e:
            log(f'connect as {user} failed ({e!r:.150}); retry')
            time.sleep(5)
            c = Cluster([N1.addr], port=9042, protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof}, connect_timeout=30,
                        auth_provider=PlainTextAuthProvider(user, pw))
    raise RuntimeError('cannot connect')


def load(session, stmt, gen, conc=48):
    sem = threading.BoundedSemaphore(conc); errors = []
    def ok(_): sem.release()
    def bad(e): errors.append(str(e)); sem.release()
    n = 0
    for args in gen:
        sem.acquire()
        session.execute_async(stmt, args).add_callbacks(ok, bad)
        n += 1
        if n % 50000 == 0:
            log(f'  loaded {n}')
    for _ in range(conc):
        sem.acquire()
    return n, errors


def trace_lines(node, since_ms=0, until_ms=None):
    out = []
    try:
        for l in open(f'{node.dir}/logs/b78.trace', errors='replace'):
            m = re.search(r'GB ms=(\d+) rows=(\d+) groups=(\d+) unfinished=(\w+) done=(\w+)', l)
            if m and int(m.group(1)) >= since_ms and (until_ms is None or int(m.group(1)) <= until_ms):
                out.append((int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4), m.group(5)))
    except OSError:
        pass
    return out


def run_query(session, cells, ds, cql, fetch, rep, label, timeout=None):
    st = SimpleStatement(cql, fetch_size=fetch)
    t0 = int(time.time() * 1000)
    err, n = None, 0
    try:
        for _ in (session.execute(st, timeout=timeout) if timeout else session.execute(st)):
            n += 1
    except Exception as e:
        err = repr(e)[:400]
    t1 = int(time.time() * 1000)
    dead = [nd.idx for nd in NODES if nd.pid() is None]       # a node killed by -XX:OnOutOfMemoryError="kill -9 %p" (cassandra-env.sh) is gone
    rec = dict(ds=ds, label=label, fetch=fetch, rep=rep, t0=t0, t1=t1, rows_returned=n, wall_ms=t1 - t0, error=err, cql=cql, dead_nodes=dead)
    cells.write(json.dumps(rec) + '\n'); cells.flush()
    log(f'  {label} {ds} fetch={fetch} rep={rep}: rows_returned={n} wall={t1 - t0} ms err={err} dead_nodes={dead}')
    return rec


def ensure_up(_):
    """B3e.3: restart a node found dead (an OutOfMemoryError may have killed it or left it unusable); reconnect the client."""
    restarted = False
    for nd in NODES:
        if nd.pid() is None:
            log(f'n{nd.idx} is DEAD: restarting')
            nd.restarts += 1
            nd.stop_poller()
            nd.start()
            nd.start_poller()
            restarted = True
    if restarted:
        try: CL['cluster'].shutdown()
        except Exception: pass
        time.sleep(5)
        connect()
    return restarted


def main():
    global SESSION
    cluster = session = None
    try:
        sh(f'rm -rf {RUN} && mkdir -p {RUN}/tools', quiet=True)
        for nd in NODES:
            sh(f'mkdir -p {nd.dir}/logs {nd.dir}/data {nd.dir}/commitlog {nd.dir}/hints {nd.dir}/saved_caches {nd.dir}/cdc_raw', quiet=True)
        log(f'cluster-run {RUNNAME}{" SHAKEDOWN" if SHAKE else ""}: scale {SCALE}, N_T {N_T}, N_S {N_S}, host {os.uname().nodename}, df {sh("df -h /dev/shm | tail -1", quiet=True)[1].strip()}')
        rc, out = sh(f"ss -ltn | grep -E '(127.0.{SLOT}.[12]:(9042|7000)|:718[01]) ' || true", check=False, quiet=True)
        assert not out.strip(), 'port busy: ' + out
        sh(f'javac -d {RUN}/tools {H}/B78Jmx.java', quiet=True)
        for nd in NODES:
            nd.make_conf()
        N1.start()
        N2.start()
        rc, out = N1.nodetool('status')
        log('nodetool status:\n' + out)
        assert len(re.findall(r'^UN\s', out, re.M)) == 2, 'ring is not 2 x UN'
        # roles: the superuser creates the ordinary role `app`
        cluster, session = connect('cassandra', 'cassandra')
        session.execute("CREATE ROLE IF NOT EXISTS app WITH PASSWORD = 'app' AND LOGIN = true")
        session.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 2}")
        for t in ('t', 's', 'k'):
            session.execute(f'CREATE TABLE IF NOT EXISTS ks.{t} (pk int, ck int, v blob, PRIMARY KEY (pk, ck))')
        cluster.control_connection.wait_for_schema_agreement(wait_time=60)
        session.execute(SimpleStatement("SELECT release_version FROM system.local", consistency_level=ConsistencyLevel.ONE))
        cluster.shutdown()
        time.sleep(5)
        cluster, session = connect()        # as the ordinary role
        ins_t = session.prepare('INSERT INTO ks.t (pk, ck, v) VALUES (0, ?, ?)'); ins_t.consistency_level = ConsistencyLevel.ALL
        ins_s = session.prepare('INSERT INTO ks.s (pk, ck, v) VALUES (0, ?, ?)'); ins_s.consistency_level = ConsistencyLevel.ALL
        ins_k = session.prepare('INSERT INTO ks.k (pk, ck, v) VALUES (1, ?, ?)'); ins_k.consistency_level = ConsistencyLevel.ALL
        t0 = time.time()
        n, errs = load(session, ins_t, ((i, os.urandom(4096)) for i in range(N_T)))
        log(f'loaded ks.t: {n} rows, {len(errs)} errors, {time.time() - t0:.0f} s {errs[:2]}')
        assert not errs, 'load errors'
        n, errs = load(session, ins_s, ((i, os.urandom(100)) for i in range(N_S)))
        log(f'loaded ks.s: {n} rows, {len(errs)} errors {errs[:2]}')
        assert not errs, 'load errors'
        n, errs = load(session, ins_k, ((i, os.urandom(100)) for i in range(10)))
        assert not errs, 'load errors'
        for nd in NODES:
            nd.nodetool('flush', 900)
        for nd in NODES:
            nd.nodetool('compact ks t', 1800); nd.nodetool('compact ks s', 600)
            _, du = sh(f'du -sb {nd.dir}/data | cut -f1', quiet=True)
            log(f'n{nd.idx} data on disk: {du.strip()} bytes; ' + ' '.join(re.findall(r'(?:Space used \(live\)|SSTable count|Number of partitions \(estimate\))[^\n]*', nd.nodetool('tablestats ks.t', 120)[1])))
        # A12: the load phase ran with a 2 GiB heap (a first attempt with 512 MB killed node 1 during the load); restart both nodes at the measured 512 MB heap
        CL['cluster'].shutdown()
        for nd in NODES:
            nd.stop()
        for nd in NODES:
            nd.env['MAX_HEAP_SIZE'] = '512M'
        N1.start(); N2.start()
        for nd in NODES:
            nd.start_poller()
        time.sleep(60)
        connect()
        cells = open(LOGS + '/cells.jsonl', 'a')
        gcl = open(LOGS + '/gcrun.jsonl', 'a')

        def gc_both(label):
            for nd in NODES:
                g = nd.gcrun(); g['label'] = label
                gcl.write(json.dumps(g) + '\n'); gcl.flush()
            time.sleep(3)

        gc_both('before-idle')
        log('idle baseline 30 s')
        ti = int(time.time() * 1000); time.sleep(30)
        cells.write(json.dumps(dict(ds='idle', label='idle', t0=ti, t1=int(time.time() * 1000))) + '\n'); cells.flush()

        GQ = 'SELECT pk, count(v) FROM ks.{t} WHERE pk = 0 GROUP BY pk'
        PQ = 'SELECT * FROM ks.t WHERE pk = 0'
        # ---- CALIBRATION (K) and FIRST-TRIGGER CHECK ----
        m0 = int(time.time() * 1000)
        rk = run_query(CL['session'], cells, 'K', 'SELECT pk, count(v) FROM ks.k WHERE pk = 1 GROUP BY pk', 100, 0, 'calibration')
        time.sleep(2)
        kl = trace_lines(N1, m0) + trace_lines(N2, m0)
        log(f'CALIBRATION trace lines for one small sub-read: {kl}')
        m1 = int(time.time() * 1000)
        rf = run_query(CL['session'], cells, 'T', GQ.format(t='t'), 1000, 0, 'first-trigger')
        time.sleep(2)
        tl = trace_lines(N1, m1) + trace_lines(N2, m1)
        full = [t for t in tl if t[1] == 1000 and t[2] == 0 and t[3] == 'true']
        log(f'FIRST-TRIGGER CHECK: {len(tl)} trace lines, {len(full)} with rows=1000 groups=0 unfinished=true, max rows {max([t[1] for t in tl] or [0])}')
        if not (rf['error'] is None and rf['rows_returned'] == 1 and full and max(t[1] for t in tl) <= 1000):
            raise RuntimeError('FIRST-TRIGGER CHECK FAILED: the fetch-1000 GROUP BY did not show sub-reads of exactly 1000 rows with the group unfinished; stop')
        log('FIRST-TRIGGER CHECK passed')

        for fs in FETCH:
            ensure_up(None)
            log(f'== fetch {fs}: GROUP BY x{REPS}')
            gc_both(f'gb-{fs}')
            for rep in range(1, REPS + 1):
                run_query(CL['session'], cells, 'T', GQ.format(t='t'), fs, rep, 'groupby')
                if ensure_up(None):
                    gc_both(f'gb-{fs}')       # fresh JVM: a new baseline for the next repetition
                time.sleep(1)
            if fs is None or fs > 100000:
                log(f'== fetch {fs}: control SELECT * not run (A11: builds an 800 MB response on a 512 MB heap)')
                continue
            ensure_up(None)
            reps_c = REPS if fs <= 10000 else 1
            log(f'== fetch {fs}: control SELECT * x{reps_c}')
            gc_both(f'ctl-{fs}')
            for rep in range(1, reps_c + 1):
                run_query(CL['session'], cells, 'T', PQ, fs, rep, 'control-select', timeout=120)
                if ensure_up(None):
                    gc_both(f'ctl-{fs}')
                time.sleep(1)
        # small-row control (B3h 2)
        for fs in (10000, 100000):
            ensure_up(None)
            log(f'== small rows (ks.s) fetch {fs}')
            gc_both(f'small-{fs}')
            for rep in range(1, REPS + 1):
                run_query(CL['session'], cells, 'S', GQ.format(t='s'), fs, rep, 'small-rows')
                if ensure_up(None):
                    gc_both(f'small-{fs}')
                time.sleep(1)
        # guardrail arm: restart n1 with page_size_fail_threshold
        log('== guardrail arm: restarting n1 with page_size_fail_threshold 20000')
        CL['cluster'].shutdown()
        N1.stop_poller(); N1.stop()
        N1.make_conf({'page_size_fail_threshold': '20000'})
        N1.start(); N1.start_poller()
        time.sleep(5)
        cluster, session = connect()
        ensure_up(None)
        gc_both('guardrail')
        for fs in (10000, 100000, 100000, 100000):
            run_query(CL['session'], cells, 'T', GQ.format(t='t'), fs, 1, 'guardrail')
            time.sleep(1)
        log('all cells done')
        return 0
    finally:
        log('cleanup: stopping pollers, client, nodes')
        for nd in NODES:
            try: nd.stop_poller()
            except Exception: pass
        if cluster:
            try: cluster.shutdown()
            except Exception: pass
        for nd in NODES:
            nd.stop()
        for nd in NODES:
            for f in ('gc.log', 'b78.trace', 'system.log', 'start.out'):
                for src in glob.glob(f'{nd.dir}/logs/{f}*'):
                    base = os.path.basename(src)
                    stem, _, rest = base.partition('.')
                    sh(f'cp {src} {LOGS}/{stem}-n{nd.idx}.{rest} 2>/dev/null', check=False, quiet=True)
        _, left = sh("ps -eo pid,args | grep -E '^ *[0-9]+ [^ ]*java .*CassandraDaemon' | grep " + RUN + " || true", check=False, quiet=True)
        log(f'leftover CassandraDaemon of this run: {left.strip()!r}; restarts n1={N1.restarts} n2={N2.restarts}')
        sh(f'rm -rf {RUN}', check=False, quiet=True)
        log(f'tmpfs dir removed: {not os.path.exists(RUN)}')


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        log(f'FAILED: {e!r}')
        sys.exit(1)
