#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of default_page_size-cqlgroupbylimits_onclose-rowlimit--autonomous (case-file sha256 in the results file section 1;
audit amendments C1-C4, R1-R5 are in the case file next to B3f and before B4). Adapted from cluster-run.py of
group-by-row-limit-incrementRowCount-rowsCounted--autonomous.
usage: cluster-run.py <run-name> [shakedown]     (a background job; every exit stops the node)
Output: ~/s4-dps-logs/<run-name>/cluster/ : cells.jsonl, session.log, gcrun.jsonl, sstables-before.txt, sstables-after.txt, and per variant
        <variant>/{heap.csv, dps.trace, gc.log*, system.log*, start.out}.
One node (127.0.9.1, JMX 7190, native 9042), data under ~/s4-dps-run on local disk, PasswordAuthenticator, role `app`.
Builds (made by mkvar.sh): ~/s4-dps-v10000 (stock), ~/s4-dps-v500, ~/s4-dps-v200000 (DEFAULT_PAGE_SIZE edited, ant jar).
Steps: load with the stock build and a 2 GiB heap (2,000,000 rows x 1 KiB, one partition, 10 groups) -> flush, compact -> record sstables ->
  per variant [stock, 500, 200000]: start at 512 MB heap, idle baseline, calibration (K), first-trigger check (client fetch 1000 GROUP BY must show
  reads of exactly 1000 rows, group unfinished), warm-up (fetch 1000), 3 x [full GC, GROUP BY unset], 3 x [full GC, plain count(payload)];
  stock only: 3 x GROUP BY fetch 500, 3 x GROUP BY fetch 200000, then a guardrail arm (page_size_fail_threshold 10000).
Env: DPS_SCALE (1; divides the row count; shakedown knob)."""
import glob, json, os, re, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
H = os.path.dirname(os.path.abspath(__file__))
RUNNAME = sys.argv[1] if len(sys.argv) > 1 else sys.exit(__doc__)
SHAKE = len(sys.argv) > 2 and sys.argv[2] == 'shakedown'
SCALE = int(os.environ.get('DPS_SCALE', 100 if SHAKE else 1))
N = 2000000 // SCALE
GROUP = N // 10
SLOT = 9
RUN = f'{HOME}/s4-dps-run'
LOGS = f'{HOME}/s4-dps-logs/{RUNNAME}/cluster'
BUILDS = {'stock': f'{HOME}/s4-dps-v10000', '500': f'{HOME}/s4-dps-v500', '200000': f'{HOME}/s4-dps-v200000'}
CONSTANT = {'stock': 10000, '500': 500, '200000': 200000}
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
C = BUILDS['stock']          # current CASSANDRA_HOME (changes per variant)

LIB = os.path.join(BUILDS['stock'], 'lib')
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


def sh(cmd, timeout=900, check=True, quiet=False, env=None, cwd=None):
    log('+ ' + cmd[:300])
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env or os.environ, cwd=cwd or C)
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
    def __init__(self):
        self.addr = f'127.0.{SLOT}.1'
        self.jmx = 7190
        self.dir = f'{RUN}/n1'
        self.variant = 'stock'
        self.heap = '2G'
        self.poller = None
        self.restarts = 0
        self.extra = None

    @property
    def home(self):
        return BUILDS[self.variant]

    @property
    def vlogs(self):
        return f'{self.dir}/logs-{self.variant}'

    def env(self):
        e = dict(os.environ, CASSANDRA_CONF=self.dir + '/conf', CASSANDRA_LOG_DIR=self.vlogs, MAX_HEAP_SIZE=self.heap, CASSANDRA_HOME=self.home)
        e.pop('HEAP_NEWSIZE', None); e.pop('JVM_EXTRA_OPTS', None)
        return e

    def pid(self):
        try:
            pid = int(open(self.dir + '/cassandra.pid').read().strip())
            return pid if 'CassandraDaemon' in open(f'/proc/{pid}/cmdline').read() else None
        except (OSError, ValueError):
            return None

    def make_conf(self):
        conf = self.dir + '/conf'
        sh(f'mkdir -p {self.vlogs} && rm -rf {conf} && cp -r {self.home}/conf {conf}', quiet=True)
        lines = {
            'cluster_name': "'dps'",
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
        if self.extra:
            lines.update(self.extra)
        out, skip = [], False
        for l in open(self.home + '/conf/cassandra.yaml').read().splitlines():
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
        out.append('# ---- stage4 dps (R1) ----')
        out += [f'{k}: {v}' for k, v in lines.items()]
        open(conf + '/cassandra.yaml', 'w').write('\n'.join(out) + '\n')
        env = open(conf + '/cassandra-env.sh').read()
        assert env.count('JMX_PORT="7199"') == 1
        open(conf + '/cassandra-env.sh', 'w').write(env.replace('JMX_PORT="7199"', f'JMX_PORT="{self.jmx}"'))
        byteman = f'{self.home}/build/lib/jars/byteman-4.0.20.jar'
        with open(conf + '/jvm11-server.options', 'a') as fo:
            fo.write('\n# stage4 dps\n-XX:-HeapDumpOnOutOfMemoryError\n-Dcassandra.ring_delay_ms=10000\n')
            fo.write(f'-Xlog:gc*:file={self.vlogs}/gc.log:time,uptime:filecount=20,filesize=100M\n')
            fo.write(f'-javaagent:{byteman}=script:{H}/rowlimit.btm\n-Dstage4.trace={self.vlogs}/dps.trace\n')
        log(f'conf variant={self.variant} constant={CONSTANT[self.variant]} heap={self.heap} home={self.home}: ' + '; '.join(f'{k}={v.strip()}' for k, v in lines.items() if '\n' not in v) + f'; JMX {self.jmx}')

    def nodetool(self, args, timeout=600):
        return sh(f'bin/nodetool -h 127.0.0.1 -p {self.jmx} {args}', timeout=timeout, check=False, quiet=True, env=self.env(), cwd=self.home)

    def start(self):
        if self.pid() is not None:
            raise RuntimeError('node already running')
        sh(f'bash -c "ulimit -n 100000; bin/cassandra -p {self.dir}/cassandra.pid >> {self.vlogs}/start.out 2>&1"', env=self.env(), cwd=self.home)
        t0 = time.time()
        while time.time() - t0 < 420:
            time.sleep(3)
            if self.pid() is None and time.time() - t0 > 20:
                raise RuntimeError('node died during start: ' + open(f'{self.vlogs}/start.out', errors='replace').read()[-800:])
            rc, out = self.nodetool('status', timeout=60)
            if re.search(r'^UN\s+' + re.escape(self.addr), out, re.M):
                rc2, out2 = self.nodetool('statusbinary', timeout=60)
                if out2.strip() == 'running':
                    log(f'node up after {time.time() - t0:.0f} s, pid {self.pid()}')
                    return
        raise RuntimeError('node did not come up')

    def stop(self):
        pid = self.pid()
        if pid is None:
            return
        log(f'stopping node pid {pid}')
        sh(f'kill {pid}', check=False)
        for _ in range(180):
            if not os.path.exists(f'/proc/{pid}'):
                log('node stopped'); return
            time.sleep(1)
        sh(f'kill -9 {pid}', check=False); time.sleep(2)

    def start_poller(self):
        self.stopfile = f'{self.dir}/heap.stop'
        if os.path.exists(self.stopfile):
            os.remove(self.stopfile)
        self.poller = subprocess.Popen(['java', '-cp', f'{RUN}/tools', 'DpsJmx', str(self.jmx), 'poll', f'{self.vlogs}/heap.csv', '100', self.stopfile])

    def stop_poller(self):
        try:
            open(self.stopfile, 'w').write('x')
            if self.poller:
                self.poller.wait(timeout=20)
        except Exception as e:
            log(f'poller: {e}')
        self.poller = None

    def gcrun(self, label):
        pid = self.pid()
        t0 = int(time.time() * 1000)
        sh(f'jcmd {pid} GC.run', check=False, quiet=True)
        rec = dict(variant=self.variant, label=label, t0=t0, t1=int(time.time() * 1000))
        GCL.write(json.dumps(rec) + '\n'); GCL.flush()
        time.sleep(3)


ND = Node()
CL = {}
GCL = None


def connect(user='app', pw='app'):
    prof = ExecutionProfile(request_timeout=1800, consistency_level=ConsistencyLevel.ONE, retry_policy=FallthroughRetryPolicy(),
                            load_balancing_policy=WhiteListRoundRobinPolicy([ND.addr]))
    for attempt in range(30):
        c = Cluster([ND.addr], port=9042, protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof}, connect_timeout=30,
                    auth_provider=PlainTextAuthProvider(user, pw))
        try:
            s = c.connect()
            CL['cluster'], CL['session'] = c, s
            return c, s
        except Exception as e:
            log(f'connect as {user} failed ({e!r:.150}); retry')
            time.sleep(5)
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
        if n % 200000 == 0:
            log(f'  loaded {n}')
    for _ in range(conc):
        sem.acquire()
    return n, errors


def datasize():
    return int(sh(f'du -sb {ND.dir}/data/ks | cut -f1', quiet=True)[1].strip() or 0)


def sstables(fn):
    sh(f'(cd {ND.dir}/data/ks && find . -name "*Data.db" -o -name "*Index.db" | sort | xargs ls -l) > {LOGS}/{fn} 2>&1', check=False, quiet=True)


def trace_lines(since_ms=0, until_ms=None):
    out = []
    try:
        for l in open(f'{ND.vlogs}/dps.trace', errors='replace'):
            m = re.search(r'GB ms=(\d+) rows=(\d+) groups=(\d+) unfinished=(\w+) done=(\w+)', l)
            if m and int(m.group(1)) >= since_ms and (until_ms is None or int(m.group(1)) <= until_ms):
                out.append((int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4), m.group(5)))
    except OSError:
        pass
    return out


def run_query(cells, cql, fetch, rep, label, timeout=None):
    st = SimpleStatement(cql, fetch_size=fetch)
    ds0 = datasize()
    t0 = int(time.time() * 1000)
    err, n = None, 0
    try:
        for _ in (CL['session'].execute(st, timeout=timeout) if timeout else CL['session'].execute(st)):
            n += 1
    except Exception as e:
        err = repr(e)[:400]
    t1 = int(time.time() * 1000)
    dead = ND.pid() is None
    ds1 = datasize()
    rec = dict(variant=ND.variant, constant=CONSTANT[ND.variant], label=label, fetch=fetch, rep=rep, t0=t0, t1=t1, rows_returned=n, wall_ms=t1 - t0, error=err, cql=cql,
               dead=dead, data_bytes_before=ds0, data_bytes_after=ds1)
    cells.write(json.dumps(rec) + '\n'); cells.flush()
    log(f'  [{ND.variant}] {label} fetch={fetch} rep={rep}: rows_returned={n} wall={t1 - t0} ms err={err} dead={dead} data {ds0}->{ds1}')
    return rec


def ensure_up():
    """B3e: restart the node when found dead (an OutOfMemoryError ends the JVM through -XX:OnOutOfMemoryError kill -9); reconnect the client."""
    if ND.pid() is not None:
        return False
    log('node is DEAD: restarting')
    ND.restarts += 1
    ND.stop_poller()
    ND.start()
    ND.start_poller()
    try: CL['cluster'].shutdown()
    except Exception: pass
    time.sleep(5)
    connect()
    time.sleep(30)
    return True


def start_variant(variant, extra=None):
    ND.stop_poller() if ND.poller else None
    ND.stop()
    ND.variant, ND.heap, ND.extra = variant, '512M', extra
    ND.make_conf()
    ND.start()
    ND.start_poller()
    time.sleep(40)
    connect()


def main():
    global SESSION, GCL
    cluster = None
    try:
        sh(f'rm -rf {RUN} && mkdir -p {RUN}/tools', quiet=True)
        GCL = open(LOGS + '/gcrun.jsonl', 'a')
        sh(f'mkdir -p {ND.dir}/data {ND.dir}/commitlog {ND.dir}/hints {ND.dir}/saved_caches {ND.dir}/cdc_raw', quiet=True)
        log(f'cluster-run {RUNNAME}{" SHAKEDOWN" if SHAKE else ""}: scale {SCALE}, N {N}, host {os.uname().nodename}, df {sh("df -h " + RUN + " | tail -1", quiet=True)[1].strip()}')
        rc, out = sh(f"ss -ltn | grep -E '(127.0.{SLOT}.1:(9042|7000)|:7190) ' || true", check=False, quiet=True)
        assert not out.strip(), 'port busy: ' + out
        for v, d in BUILDS.items():
            line = [l for l in open(f'{d}/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java') if 'int DEFAULT_PAGE_SIZE' in l][0].strip()
            log(f'build {v}: {line}; jar {glob.glob(d + "/build/apache-cassandra-*.jar")}')
            assert str(CONSTANT[v]) in line
        sh(f'javac -d {RUN}/tools {H}/DpsJmx.java', quiet=True)
        # ---- load: stock build, 2 GiB heap (R2) ----
        ND.variant, ND.heap = 'stock', '2G'
        ND.make_conf(); ND.start()
        cluster, session = connect('cassandra', 'cassandra')
        session.execute("CREATE ROLE IF NOT EXISTS app WITH PASSWORD = 'app' AND LOGIN = true")
        session.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
        session.execute("CREATE TABLE IF NOT EXISTS ks.t (pk int, c1 int, c2 int, payload blob, PRIMARY KEY (pk, c1, c2)) WITH compression = {'enabled': 'false'}")
        session.execute("CREATE TABLE IF NOT EXISTS ks.k (pk int, c1 int, c2 int, payload blob, PRIMARY KEY (pk, c1, c2)) WITH compression = {'enabled': 'false'}")
        time.sleep(5)
        cluster.shutdown(); time.sleep(5)
        cluster, session = connect()        # ordinary role
        ins_t = session.prepare('INSERT INTO ks.t (pk, c1, c2, payload) VALUES (1, ?, ?, ?)')
        ins_k = session.prepare('INSERT INTO ks.k (pk, c1, c2, payload) VALUES (1, ?, ?, ?)')
        t0 = time.time()
        n, errs = load(session, ins_t, ((i // GROUP, i % GROUP, os.urandom(1024)) for i in range(N)))
        log(f'loaded ks.t: {n} rows, {len(errs)} errors, {time.time() - t0:.0f} s {errs[:2]}')
        assert not errs, 'load errors'
        n, errs = load(session, ins_k, ((0, i, os.urandom(1024)) for i in range(10)))
        assert not errs, 'load errors'
        ND.nodetool('flush', 1800)
        ND.nodetool('compact ks t', 3600)
        log('tablestats: ' + ' '.join(re.findall(r'(?:Space used \(live\)|SSTable count|Number of partitions \(estimate\))[^\n]*', ND.nodetool('tablestats ks.t', 120)[1])))
        CL['cluster'].shutdown()
        ND.stop()
        sstables('sstables-before.txt')
        log(f'data on disk: {datasize()} bytes; df {sh("df -h " + RUN + " | tail -1", quiet=True)[1].strip()}')
        cells = open(LOGS + '/cells.jsonl', 'a')

        GQ = 'SELECT pk, c1, count(payload) FROM ks.t WHERE pk = 1 GROUP BY pk, c1'
        PQ = 'SELECT count(payload) FROM ks.t WHERE pk = 1'
        for variant in ('stock', '500', '200000'):
            log(f'======== variant {variant} (DEFAULT_PAGE_SIZE {CONSTANT[variant]}) ========')
            start_variant(variant)
            ND.gcrun('before-idle')
            log('idle baseline 30 s')
            ti = int(time.time() * 1000); time.sleep(30)
            cells.write(json.dumps(dict(variant=variant, label='idle', t0=ti, t1=int(time.time() * 1000))) + '\n'); cells.flush()
            # calibration (K) and first-trigger check
            m0 = int(time.time() * 1000)
            run_query(cells, 'SELECT pk, c1, count(payload) FROM ks.k WHERE pk = 1 GROUP BY pk, c1', 100, 0, 'calibration')
            time.sleep(2)
            kl = trace_lines(m0)
            log(f'CALIBRATION trace lines for one small read: {kl}')
            m1 = int(time.time() * 1000)
            rf = run_query(cells, GQ, 1000, 0, 'first-trigger')
            time.sleep(2)
            tl = trace_lines(m1)
            full = [t for t in tl if t[1] == 1000 and t[2] == 0 and t[3] == 'true']
            log(f'FIRST-TRIGGER CHECK: {len(tl)} trace lines, {len(full)} with rows=1000 groups=0 unfinished=true, max rows {max([t[1] for t in tl] or [0])}')
            if not (rf['error'] is None and rf['rows_returned'] == 10 and full and max(t[1] for t in tl) <= 1000):
                raise RuntimeError('FIRST-TRIGGER CHECK FAILED')
            log('FIRST-TRIGGER CHECK passed (the warm-up is this fetch-1000 query)')
            ND.gcrun(f'{variant}-gb-unset')
            for rep in range(1, 4):
                run_query(cells, GQ, None, rep, 'groupby-unset')
                if ensure_up():
                    ND.gcrun(f'{variant}-gb-unset')
                else:
                    ND.gcrun(f'{variant}-gb-unset')
                time.sleep(1)
            ensure_up()
            ND.gcrun(f'{variant}-plain')
            for rep in range(1, 4):
                run_query(cells, PQ, None, rep, 'plain-count')
                if ensure_up():
                    ND.gcrun(f'{variant}-plain')
                else:
                    ND.gcrun(f'{variant}-plain')
                time.sleep(1)
            if variant == 'stock':
                for fs in (500, 200000):
                    ensure_up()
                    ND.gcrun(f'{variant}-gb-{fs}')
                    for rep in range(1, 4):
                        run_query(cells, GQ, fs, rep, f'groupby-fetch')
                        ensure_up()
                        ND.gcrun(f'{variant}-gb-{fs}')
                        time.sleep(1)
        # ---- guardrail arm (stock build, page_size_fail_threshold 10000) ----
        log('======== guardrail arm: stock build with page_size_fail_threshold 10000 ========')
        CL['cluster'].shutdown()
        start_variant('stock', {'page_size_fail_threshold': '10000'})
        for fs in (500, 200000, 200000, 200000):
            run_query(cells, GQ, fs, 1, 'guardrail')
            time.sleep(1)
        sstables('sstables-after.txt')
        log('all cells done')
        return 0
    finally:
        log('cleanup: stopping poller, client, node')
        try: ND.stop_poller()
        except Exception: pass
        try: CL['cluster'].shutdown()
        except Exception: pass
        try: cluster and cluster.shutdown()
        except Exception: pass
        ND.stop()
        for v in BUILDS:
            vd = f'{ND.dir}/logs-{v}'
            if os.path.isdir(vd):
                sh(f'mkdir -p {LOGS}/{v} && cp {vd}/heap.csv {vd}/dps.trace {vd}/gc.log* {vd}/system.log {vd}/start.out {LOGS}/{v}/ 2>/dev/null', check=False, quiet=True)
        sstables('sstables-final.txt')
        _, left = sh("ps -eo pid,args | grep -E '^ *[0-9]+ [^ ]*java .*CassandraDaemon' | grep " + RUN + " || true", check=False, quiet=True)
        log(f'leftover CassandraDaemon of this run: {left.strip()!r}; restarts={ND.restarts}')
        sh(f'rm -rf {RUN}', check=False, quiet=True)
        log(f'run dir removed: {not os.path.exists(RUN)}')


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        log(f'FAILED: {e!r}')
        sys.exit(1)
