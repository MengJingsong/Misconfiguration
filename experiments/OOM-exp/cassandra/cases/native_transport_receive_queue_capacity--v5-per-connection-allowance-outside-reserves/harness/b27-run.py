#!/usr/bin/env python3
"""B27 stage 2 (2026-11-24): one clean-start node lifetime on the victim node (pc82 in the
2026-11-24 afternoon attempt, pc91 from 20:10 EST), case §2.5 steps 1-10. No Byteman, no patch.
Adapted from B10's b10-run.py (histogram timeout, scope headroom variable, process check kept). Changes: BASE, W and the
direct limit are arguments; EXTRA yaml line only for I2/I2b (--extra); client JVM sizing of §2.5 (<= 500 conns/JVM,
-Xmx1g, direct 2g, -Xss512k, eventLoopThreads=1, ulimit -n 100000, --connect-threads); TIME-WAIT check; pollers add
connectedNativeClients and server-side established connections (ss); per-histogram QM / server connection;
B27's P1-P11 EXPECTED lines.

usage:
  b27-run.py dataset <R>
  b27-run.py run <run-id> <arm> <heap GiB> <direct GiB> <N> <R> [--window 7] [--extra 'key: value'] [--throw]
      [--seconds 240] [--per-jvm 500] [--connect-threads 64] [--calib]
      arm: T2 C2 I2 X2 I2b T4 T8 CAL (label; parameters come from the arguments). --calib = calibration (60-s load,
      histograms at 20/40/60).
Layout: BASE=/mydata/s4/b27: cassandra/ (cp -a cassandra-base), classes/, harness/, node/, data.pristine-<R>/,
logs/<run-id>/ (session.log, stdout.txt, system.log, gc.log*, jmx-poll.csv, cg-poll.csv, histo-*.txt, flood-*.out,
summary.txt, run.json, hprof if any).
"""
import json, os, re, signal, subprocess, sys, threading, time

BASE = os.environ.get('B27_BASE', '/mydata/s4/b27')
C = BASE + '/cassandra'
NODE = BASE + '/node'
HARNESS = os.path.dirname(os.path.abspath(__file__))
CLASSES = BASE + '/classes'
JMX = 7199
FLOOD_CP = f'{CLASSES}:{C}/build/classes/main:{C}/build/lib/jars/*'
QM = 'org.apache.cassandra.transport.messages.QueryMessage'
VALUE = 125000
M = VALUE + 74
W = 7
CONNECT_THREADS = 64
PER_JVM_DIRECT = '2g'
CAP = 1 << 20

B_HEAP = 'java.lang:type=Memory'
B_DIRECT = 'java.nio:type=BufferPool,name=direct'
B_POOLU = 'org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=UsedSize'
B_POOLO = 'org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=OverflowSize'
B_RSIZE = 'org.apache.cassandra.metrics:type=Client,name=RequestsSize'
B_PAUSED = 'org.apache.cassandra.metrics:type=Client,name=PausedConnections'
B_DISC = 'org.apache.cassandra.metrics:type=Client,name=RequestDiscarded'
B_TOBP = 'org.apache.cassandra.metrics:type=Client,name=TimedOutBeforeProcessing'
B_NTRP = 'org.apache.cassandra.metrics:type=ThreadPools,path=transport,scope=Native-Transport-Requests,name=PendingTasks'
B_NTRA = 'org.apache.cassandra.metrics:type=ThreadPools,path=transport,scope=Native-Transport-Requests,name=ActiveTasks'
B_RSP = 'org.apache.cassandra.metrics:type=ThreadPools,path=request,scope=ReadStage,name=PendingTasks'
B_CONN = 'org.apache.cassandra.metrics:type=Client,name=connectedNativeClients'
POLL = [(B_HEAP, 'HeapMemoryUsage'), (B_DIRECT, 'MemoryUsed'), (B_DIRECT, 'Count'), (B_POOLU, 'Value'),
        (B_POOLO, 'Value'), (B_RSIZE, 'Value'), (B_PAUSED, 'Value'), (B_DISC, 'Count'), (B_TOBP, 'Count'),
        (B_NTRP, 'Value'), (B_NTRA, 'Value'), (B_RSP, 'Value'), (B_CONN, 'Value')]
POLL_COLS = ['ms', 'heap_used', 'direct_used', 'direct_count', 'pool_used', 'pool_overflow', 'global_in_use', 'paused',
             'discarded', 'timedout_before', 'ntr_pending', 'ntr_active', 'read_pending', 'native_clients']

LOGS = None
SESSION = SUMMARY = None
CHILDREN = []
NODE_PROC = None


def log(s):
    line = f'[{time.strftime("%F %T")} {int(time.time() * 1000)}] {s}'
    print(line, file=sys.stderr, flush=True)
    if SESSION:
        SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    if SUMMARY:
        SUMMARY.write(s + '\n'); SUMMARY.flush()
    log(s)


def sh(cmd, timeout=600, check=True, env=None, cwd=C, quiet=False):
    log('+ ' + cmd)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
    out = (r.stdout or '') + (r.stderr or '')
    if not quiet and SESSION:
        SESSION.write(out[-4000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed rc={r.returncode}: {cmd}\n{out[-1500:]}')
    return r.returncode, out


def daemons():
    return subprocess.run("ps -eo pid,cmd | grep '[C]assandraDaemon' || true", shell=True, capture_output=True,
                          text=True).stdout.strip()


def node_pid():
    for p in os.listdir('/proc'):
        if not p.isdigit():
            continue
        try:
            cl = open(f'/proc/{p}/cmdline').read()
        except OSError:
            continue
        if 'CassandraDaemon' in cl and BASE in cl:
            return int(p)
    return None


def stop_node():
    pid = node_pid()
    if pid is not None:
        sh(f'bin/nodetool -p {JMX} stopdaemon', check=False, timeout=120)
        for _ in range(60):
            if node_pid() is None:
                break
            time.sleep(1)
        pid = node_pid()
        if pid is not None:
            log(f'node did not stop; kill -9 {pid}')
            os.kill(pid, signal.SIGKILL)
            time.sleep(2)
    if NODE_PROC is not None:
        try:
            NODE_PROC.wait(timeout=30)
        except subprocess.TimeoutExpired:
            NODE_PROC.kill()
    left = daemons()
    note(f'after stop, CassandraDaemon processes on {os.uname().nodename.split(".")[0]}: ' + (left[:300] if left else 'none'))


def kill_children():
    for p in CHILDREN:
        if p.poll() is None:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except Exception:
                p.kill()


def fail(msg):
    note('FAIL: ' + msg)
    kill_children()
    stop_node()
    sys.exit(1)


def jmx(*args):
    _, out = sh(f'java -cp {CLASSES} Jmx {JMX} ' + ' '.join(f"'{a}'" for a in args), check=False, timeout=60,
                quiet=True)
    return out


def cgroup_dir(pid):
    for l in open(f'/proc/{pid}/cgroup'):
        if l.startswith('0::'):
            return '/sys/fs/cgroup' + l.strip()[3:]
    return None


def client_jvm_opts():
    return ' '.join(l.strip() for l in open(C + '/conf/jvm11-clients.options') if l.strip().startswith('-'))


def start_node(heap, unit, memmax_gib, data_src=None, direct=2, extra=''):
    """steps 1-2"""
    global NODE_PROC
    if daemons():
        fail('a CassandraDaemon already runs on this host: ' + daemons()[:200])
    sh(f'rm -rf {NODE}/data', check=False)
    if data_src:
        sh(f'cp -a {data_src} {NODE}/data')
    env = dict(os.environ, CASSANDRA_HOME=C, NODE=NODE, EXTRA=extra)
    _, y = sh(f'bash {HARNESS}/make-node-yaml.sh', env=env)
    note('yaml check: ' + y.strip().splitlines()[-1])
    env = dict(os.environ, CASSANDRA_CONF=NODE + '/conf', CASSANDRA_LOG_DIR=LOGS, CASSANDRA_HEAPDUMP_DIR=LOGS,
               MAX_HEAP_SIZE=f'{heap}G', MAX_DIRECT_MEMORY_SIZE=f'{direct}G')
    env.pop('HEAP_NEWSIZE', None)
    env.pop('JVM_EXTRA_OPTS', None)
    memmax = memmax_gib * 1024 ** 3
    cmd = ['systemd-run', '--user', '--scope', '--unit', unit, '-p', f'MemoryMax={memmax}', '-p', 'MemorySwapMax=0',
           'bash', '-c', 'ulimit -n 100000 && exec bin/cassandra -f']
    log('+ ' + ' '.join(cmd))
    NODE_PROC = subprocess.Popen(cmd, cwd=C, env=env, stdout=open(LOGS + '/stdout.txt', 'w'),
                                 stderr=subprocess.STDOUT)
    t0 = time.time()
    pid = None
    while time.time() - t0 < 300:
        if NODE_PROC.poll() is not None:
            fail(f'node exited during start-up rc={NODE_PROC.returncode}; see stdout.txt')
        pid = pid or node_pid()
        if pid:
            _, st = sh(f'bin/nodetool -p {JMX} status', check=False, quiet=True)
            _, sb = sh(f'bin/nodetool -p {JMX} statusbinary', check=False, quiet=True)
            if re.search(r'^UN\s+127\.0\.0\.1\s', st, re.M) and re.search(r'^running\s*$', sb, re.M):
                log(f'node UN and native transport running after {time.time() - t0:.0f} s')
                break
        time.sleep(2)
    else:
        fail('node not UN / native transport not running in 300 s')
    cg = cgroup_dir(pid)
    mm = open(cg + '/memory.max').read().strip()
    ms = open(cg + '/memory.swap.max').read().strip()
    note(f'node pid {pid} scope {cg} memory.max {mm} (want {memmax}) memory.swap.max {ms}')
    jvm = open(f'/proc/{pid}/cmdline').read().split('\0')
    note('jvm readback: ' + ' '.join(t for t in jvm if t.startswith(
        ('-Xmx', '-Xms', '-XX:MaxDirect', '-XX:+UseG1GC', '-XX:+UseParallel', '-XX:+UseConcMark', '-XX:+HeapDump',
         '-XX:OnOutOfMemoryError', '-XX:+CrashOnOutOfMemory', '-XX:+ExitOnOutOfMemory', '-javaagent', '-XX:HeapDumpPath'))))
    try:
        sl = open(LOGS + '/system.log', errors='replace').read()
        for k in ['native_transport_max_message_size', 'native_transport_max_request_data_in_flight=',
                  'native_transport_max_request_data_in_flight_per_ip', 'native_transport_receive_queue_capacity',
                  'native_transport_timeout', 'read_request_timeout', 'native_transport_throw_on_overload',
                  'native_transport_max_threads', 'native_transport_queue_max_item_age_threshold',
                  'native_transport_max_concurrent_connections=', 'native_transport_max_concurrent_connections_per_ip',
                  'native_transport_idle_timeout', 'native_transport_rate_limiting_enabled', 'concurrent_reads',
                  'allow_filtering_enabled']:
            m = re.search(re.escape(k) + r'=?([^;,\]]*)', sl)
            note(f'resolved {k.rstrip("=")}: {m.group(1).strip() if m else "not in system.log"}')
    except OSError:
        pass
    return pid, cg


def histogram(pid, path):
    h0 = int(time.time() * 1000)
    try:
        sh(f'jcmd {pid} GC.class_histogram > {path}', check=False, timeout=150, quiet=True)
    except subprocess.TimeoutExpired:
        # fix 2026-11-17 (after T8-r1): a histogram that hangs in GC thrash no longer aborts the run
        log(f'histogram {path} timed out after 150 s; jcmd killed, run continues')
        subprocess.run(f"pkill -f 'jcmd {pid} GC.class_histogram'", shell=True)
    h1 = int(time.time() * 1000)
    sc = server_conns()
    qm = bb = 0
    top = []
    try:
        for l in open(path, errors='replace'):
            p = l.split()
            if len(p) >= 4 and p[0].endswith(':'):
                if len(top) < 6:
                    top.append((p[3], int(p[2])))
                if p[3] == QM:
                    qm = int(p[1])
                if p[3] == '[B':
                    bb = int(p[2])
    except OSError:
        pass
    log(f'histogram {path}: {h0}-{h1} QueryMessage={qm} [B={bb} server_conns={sc} top={top[:4]}')
    return dict(h0=h0, h1=h1, qm=qm, bb=bb, top=top, sc=sc)


def server_conns():
    r = subprocess.run("ss -Htn state established '( sport = :9042 )' | wc -l", shell=True, capture_output=True,
                       text=True)
    try:
        return int(r.stdout.strip())
    except ValueError:
        return -1


def time_wait():
    r = subprocess.run("ss -Htan state time-wait | wc -l", shell=True, capture_output=True, text=True)
    return int(r.stdout.strip() or 0)


class CgPoller(threading.Thread):
    def __init__(self, cg, path):
        super().__init__(daemon=True)
        self.cg, self.f, self.stop_flag, self.max, self.events = cg, open(path, 'w'), False, 0, {}
        self.sc_max = 0
        self.f.write('ms,memory_current,oom_kill,max_events,server_conns\n')

    def run(self):
        while not self.stop_flag:
            try:
                cur = int(open(self.cg + '/memory.current').read())
                ev = dict(l.split() for l in open(self.cg + '/memory.events'))
                self.max = max(self.max, cur)
                self.events = ev
                sc = server_conns()
                self.sc_max = max(self.sc_max, sc)
                self.f.write(f'{int(time.time() * 1000)},{cur},{ev.get("oom_kill")},{ev.get("max")},{sc}\n'); self.f.flush()
            except (OSError, ValueError):
                pass
            time.sleep(2)


def flood(tag, conns, window, seconds, throw, out):
    args = (f'--host 127.0.0.1 --port 9042 --connections {conns} --window {window} --value-bytes {VALUE} '
            f'--seconds {seconds} --throw {"true" if throw else "false"} --retry-ms 100 --connect-threads {CONNECT_THREADS}')
    cmd = (f'ulimit -n 100000 && exec java -Xmx1g -XX:MaxDirectMemorySize={PER_JVM_DIRECT} -Xss512k '
           f'-Dio.netty.eventLoopThreads=1 {client_jvm_opts()} '
           f'-Dlogback.configurationFile={HARNESS}/flood-logback.xml '
           f'-cp "{FLOOD_CP}" org.apache.cassandra.transport.NativeFlood {args}')
    log(f'+ ({tag}) {cmd}')
    p = subprocess.Popen(cmd, shell=True, cwd=C, stdout=open(out, 'w'), stderr=subprocess.STDOUT,
                         start_new_session=True)
    CHILDREN.append(p)
    return p


def flood_total(path):
    total, start_ms, last = {}, None, {}
    for l in open(path, errors='replace'):
        m = re.match(r'^start ms=(\d+)', l)
        if m:
            start_ms = int(m.group(1))
        if l.startswith(('sec ', 'drain ', 'TOTAL')):
            d = {k: int(v) for k, v in re.findall(r'(\w+)=(-?\d+)', l)}
            last = d
            if l.startswith('TOTAL'):
                total = d
    return total or last, start_ms


def gc_pauses(path_glob_dir):
    """(epoch_ms, pause_ms, line) for every stop-the-world pause line of gc.log*"""
    import glob, datetime
    out = []
    for f in sorted(glob.glob(path_glob_dir + '/gc.log*')):
        for l in open(f, errors='replace'):
            if 'Pause' not in l or not re.search(r'\d+\.\d+ms\s*$', l):
                continue
            m = re.match(r'^\[(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3})([+-]\d{4})\]', l)
            if not m:
                continue
            ts = datetime.datetime.strptime(m.group(1) + m.group(2), '%Y-%m-%dT%H:%M:%S.%f%z').timestamp() * 1000
            out.append((int(ts), float(re.search(r'(\d+\.\d+)ms\s*$', l).group(1)), l.strip()))
    return sorted(out)


def dataset(R):
    global LOGS, SESSION, SUMMARY
    LOGS = f'{BASE}/logs/dataset-{R}'
    os.makedirs(LOGS, exist_ok=True)
    SESSION = open(LOGS + '/session.log', 'a'); SUMMARY = open(LOGS + '/summary.txt', 'w')
    pid, cg = start_node(2, f'oom-b27-dataset-{R}', 8)
    sh(f'bin/cqlsh 127.0.0.1 9042 -e "CREATE KEYSPACE ks WITH replication = '
       "{'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE ks.t (pk int, ck int, v blob, "
       'PRIMARY KEY (pk, ck));"', timeout=120)
    csv = f'{BASE}/rows-{R}.csv'
    with open(csv, 'w') as f:
        for i in range(R):
            f.write(f'0,{i},0x{os.urandom(16).hex()}\n')
    t0 = time.time()
    rc, out = sh(f"bin/cqlsh 127.0.0.1 9042 --request-timeout=120 -e \"COPY ks.t (pk, ck, v) FROM '{csv}' "
                 f"WITH MAXBATCHSIZE=50 AND NUMPROCESSES=8\"", timeout=1200, check=False)
    note(f'COPY rc={rc} in {time.time() - t0:.0f} s: ' + ' | '.join(out.strip().splitlines()[-3:]))
    sh(f'bin/nodetool -p {JMX} flush ks t', timeout=300)
    _, cnt = sh('bin/cqlsh 127.0.0.1 9042 --request-timeout=120 -e "SELECT count(*) FROM ks.t WHERE pk = 0"',
                timeout=300, check=False)
    note('count: ' + ' '.join(cnt.split()))
    sh(f'bin/nodetool -p {JMX} drain', timeout=300, check=False)
    stop_node()
    sh(f'rm -rf {BASE}/data.pristine-{R} && cp -a {NODE}/data {BASE}/data.pristine-{R}')
    note(f'data.pristine-{R} written; du: ' + sh(f'du -sh {BASE}/data.pristine-{R}', quiet=True)[1].strip())


def run(run_id, arm, heap, direct, n, R, throw, seconds, per_jvm, calib, extra):
    global LOGS, SESSION, SUMMARY
    LOGS = f'{BASE}/logs/{run_id}'
    os.makedirs(LOGS, exist_ok=True)
    SESSION = open(LOGS + '/session.log', 'a'); SUMMARY = open(LOGS + '/summary.txt', 'w')
    note(f'run {run_id} arm={arm} heap={heap}G direct={direct}G N={n} W={W} value={VALUE} M={M} R={R} throw={throw} '
         f'seconds={seconds} per_jvm={per_jvm} connect_threads={CONNECT_THREADS} calib={calib} extra={extra!r}')
    if extra and arm not in ('I2', 'I2b'):
        fail('EXTRA yaml line allowed only in I2 / I2b')
    if daemons() or subprocess.run("ps -eo pid,cmd | grep '[N]ativeFlood'", shell=True, capture_output=True,
                                   text=True).stdout.strip():
        fail('CassandraDaemon or NativeFlood already running')
    tw = time_wait()
    t_w = time.time()
    while tw + n > 26000 and time.time() - t_w < 120:
        time.sleep(5); tw = time_wait()
    note(f'TIME-WAIT check: {tw} + N {n} = {tw + n} (limit 26000) ' + ('ok' if tw + n <= 26000 else 'FAILED (recorded)'))
    note('harness md5: ' + sh(f'md5sum {HARNESS}/*', quiet=True)[1].replace('\n', '; '))
    src = f'{BASE}/data.pristine-{R}'
    if not os.path.isdir(src):
        fail('no ' + src)
    # design §2.3: MemoryMax = H + direct + 6 GiB; an invalid run (scope oom_kill / max > 0) is repeated once with
    # B27_MEMMAX_ADD=10.
    memmax = heap + direct + int(os.environ.get('B27_MEMMAX_ADD', '6'))
    pid, cg = start_node(heap, f'oom-b27-{run_id}', memmax, src, direct, extra)
    # step 3
    wp = flood('warmup', 1, 7, 10, False, LOGS + '/flood-warmup.out')
    try:
        wp.wait(timeout=200)
    except subprocess.TimeoutExpired:
        os.killpg(wp.pid, signal.SIGKILL)
    time.sleep(20)
    # step 4
    hidle = histogram(pid, LOGS + '/histo-idle.txt')
    open(LOGS + '/meters-idle.txt', 'w').write(jmx('get', *[x for p in POLL for x in p]))
    # step 5
    stopf = LOGS + '/stop-poll'
    pj = subprocess.Popen(['java', '-cp', CLASSES, 'Jmx', str(JMX), 'poll', '2000', '100000', stopf] +
                          [x for p in POLL for x in p], stdout=open(LOGS + '/jmx-poll.csv', 'w'),
                          stderr=subprocess.STDOUT, start_new_session=True)
    CHILDREN.append(pj)
    cgp = CgPoller(cg, LOGS + '/cg-poll.csv'); cgp.start()
    # step 6
    jvms = []
    left, j = n, 0
    while left > 0:
        k = min(per_jvm, left)
        jvms.append(flood(f'flood-{j}', k, W, seconds, throw, f'{LOGS}/flood-{j}.out'))
        left -= k; j += 1
    t0 = None
    for _ in range(6000):
        for jj in range(len(jvms)):
            try:
                for l in open(f'{LOGS}/flood-{jj}.out', errors='replace'):
                    m = re.match(r'^start ms=(\d+)', l)
                    if m:
                        t0 = int(m.group(1)) if t0 is None else min(t0, int(m.group(1)))
            except OSError:
                pass
        if t0 is not None or any(p.poll() is not None for p in jvms):
            break
        time.sleep(0.1)
    if t0 is None:
        t0 = int(time.time() * 1000)
        note('WARNING: no client start line; t0 = now')
    note(f't0 = {t0}')
    # steps 7-8
    step = 20 if heap <= 2 else 30
    marks = [20, 40, 60] if calib else list(range(20, seconds + 1, step))
    histos = []
    end_ms, death_ms = t0 + seconds * 1000, None
    while True:
        now = int(time.time() * 1000)
        if node_pid() is None:
            death_ms = now
            note(f'NODE GONE at t={(now - t0)/1000:.1f} s')
            break
        if now >= end_ms:
            break
        if marks and now >= t0 + marks[0] * 1000:
            marks.pop(0)
            h = histogram(pid, f'{LOGS}/histo-{len(histos) + 1}.txt')
            h['t'] = (h['h0'] - t0) / 1000
            histos.append(h)
            continue
        time.sleep(1)
    # step 9
    if death_ms is not None:
        time.sleep(30)
        kill_children()
    else:
        dl = time.time() + 150
        while time.time() < dl and any(p.poll() is None for p in jvms):
            if node_pid() is None:
                death_ms = death_ms or int(time.time() * 1000)
                note('NODE GONE during client drain')
                time.sleep(20); break
            time.sleep(1)
        for p in jvms:
            if p.poll() is None:
                os.killpg(p.pid, signal.SIGKILL)
    open(stopf, 'w').close()
    time.sleep(3)
    meters_end = jmx('get', *[x for p in POLL for x in p]) if node_pid() else 'node gone'
    open(LOGS + '/meters-end.txt', 'w').write(meters_end)
    cgp.stop_flag = True
    kill_children()
    stop_node()
    left = subprocess.run("ps -eo pid,cmd | grep '[N]ativeFlood' || true", shell=True, capture_output=True,
                          text=True).stdout.strip()
    note('NativeFlood left: ' + (left[:200] or 'none'))
    # step 10
    try:
        sh(f'cp {NODE}/../logs/{run_id}/system.log {LOGS}/ 2>/dev/null || true', check=False, quiet=True)
    except Exception:
        pass
    stdout = open(LOGS + '/stdout.txt', errors='replace').read()
    oom = re.search(r'java\.lang\.OutOfMemoryError[^\n]*', stdout)
    dump = re.search(r'Dumping heap to ([^\s]+)', stdout)
    sl = ''
    try:
        sl = open(LOGS + '/system.log', errors='replace').read()
    except OSError:
        pass
    sl_oom = re.search(r'^.*java\.lang\.OutOfMemoryError.*$', sl, re.M)
    first_err = re.search(r'^ERROR \[[^\]]+\].*$', sl, re.M)
    polls = []
    for l in open(LOGS + '/jmx-poll.csv', errors='replace'):
        p = l.strip().split(',')
        if len(p) == len(POLL_COLS) and p[0].isdigit():
            row = {}
            for k, v in zip(POLL_COLS, p):
                try:
                    row[k] = float(v)
                except ValueError:
                    row[k] = None
            polls.append(row)

    def mx(k):
        v = [r[k] for r in polls if r.get(k) is not None]
        return max(v) if v else None

    totals = {}
    for jj in range(len(jvms)):
        t, _ = flood_total(f'{LOGS}/flood-{jj}.out')
        for k, v in t.items():
            if k in ('sent', 'ok', 'warned', 'ovl_bytes', 'ovl_other', 'err', 'outstanding', 'refused', 'connected'):
                totals[k] = totals.get(k, 0) + v
    endpoint_ms = death_ms
    m_oom = re.search(r'^\S+\s+\[[^\]]+\] (\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d,\d{3}) .*\n(?:.*\n)?java\.lang\.OutOfMemoryError', sl, re.M)
    if m_oom and death_ms:
        import datetime
        ts = datetime.datetime.strptime(m_oom.group(1), '%Y-%m-%dT%H:%M:%S,%f').replace(tzinfo=datetime.timezone.utc).timestamp() * 1000
        note(f'first OOM line in system.log at t={(ts - t0) / 1000:.1f} s (node gone at t={(death_ms - t0) / 1000:.1f} s)')
    load_s = ((endpoint_ms or end_ms) - t0) / 1000
    pauses = gc_pauses(LOGS)
    ref = endpoint_ms or end_ms
    win = [p for p in pauses if ref - 60000 <= p[0] <= ref]
    frac = sum(p[1] for p in win) / 60000
    heap_b = heap * 1024 ** 3
    G = heap_b // 10
    E = heap_b // 40
    qmax = max([h['qm'] for h in histos] or [0])
    bbmax = max([h['bb'] for h in histos] or [0])
    bb_idle = hidle['bb']
    per_conn = [round(h['qm'] / h['sc'], 3) for h in histos if h.get('sc', 0) > 0]
    breached = len(re.findall(r'breached limit', sl))
    exceeded = len(re.findall(r'Exceeded maximum native connection limit', sl))
    import glob
    used_hist = []
    for g in [LOGS + '/gc.log'] + sorted(glob.glob(LOGS + '/gc.log.*')):
        try:
            for l in open(g, errors='replace'):
                m = re.search(r'Pause (?:Young|Full|Remark)[^\n]*?(\d+)M->(\d+)M\((\d+)M\)', l)
                if m:
                    used_hist.append(int(m.group(2)))
        except OSError:
            pass
    res = dict(run_id=run_id, arm=arm, heap_gib=heap, direct_gib=direct, N=n, W=W, M=M, R=R, throw=throw, extra=extra,
               t0=t0, endpoint='OOM' if oom else ('node died, no OOM line' if death_ms else 'none'),
               oom_line=oom.group(0) if oom else None, endpoint_t_s=(endpoint_ms - t0) / 1000 if endpoint_ms else None,
               dump=dump.group(1) if dump else None, syslog_oom=sl_oom.group(0)[:300] if sl_oom else None,
               first_error=first_err.group(0)[:300] if first_err else None,
               histos=[dict(t=h['t'], qm=h['qm'], bb=h['bb'], sc=h.get('sc'), top=h['top'][:4], dur_ms=h['h1'] - h['h0'])
                       for h in histos],
               qm_idle=hidle['qm'], bb_idle=bb_idle, qm_max=qmax, U_D1=qmax * M, bb_max_minus_idle=bbmax - bb_idle,
               qm_per_server_conn=per_conn, qm_per_conn_max=max(per_conn) if per_conn else None,
               K_max_global_in_use=mx('global_in_use'), G=G, E=E, breached_lines=breached,
               exceeded_conn_limit_lines=exceeded, server_conns_max=cgp.sc_max, native_clients_max=mx('native_clients'),
               ntr_pending_max=mx('ntr_pending'), read_pending_max=mx('read_pending'), heap_used_max=mx('heap_used'),
               direct_used_max=mx('direct_used'), pool_used_max=mx('pool_used'), discarded_max=mx('discarded'),
               timedout_before_max=mx('timedout_before'), paused_max=mx('paused'),
               client=totals, ok_per_s=totals.get('ok', 0) / max(load_s, 1), load_s=load_s,
               gc_pause_frac_last60=frac, gc_pauses_n=len(pauses), gc_last5=[p[2][-110:] for p in pauses[-5:]],
               post_gc_last5_MB=used_hist[-5:], scope_mem_max=cgp.max, scope_events=cgp.events)
    if dump and os.path.exists(dump.group(1)):
        res['dump_bytes'] = os.path.getsize(dump.group(1))
    json.dump(res, open(LOGS + '/run.json', 'w'), indent=1)
    for k, v in res.items():
        note(f'{k}: {v}')
    nw = n * W
    if not calib:
        note(f'EXPECTED P1: K=0 (max RequestsSize {res["K_max_global_in_use"]} <= M {M}); breached lines 0 ({breached}); '
             f'warned 0 ({totals.get("warned")}); ovl_bytes 0 ({totals.get("ovl_bytes")}); discarded +0 '
             f'({res["discarded_max"]}); refused 0 ({totals.get("refused")})')
        if arm in ('T2', 'C2', 'T4', 'T8'):
            note(f'EXPECTED P2: QM/server conn <= 8 at every histogram ({res["qm_per_conn_max"]}; {per_conn})')
        if arm == 'T2':
            note(f'EXPECTED P3: NTR pending >= 0.5NW ({res["ntr_pending_max"]} vs {nw/2}); QM >= 14000 ({qmax}); '
                 f'U(D1)/G >= 8 ({qmax*M/G:.2f})')
            note(f'EXPECTED P4: heap OOM within 180 s ({res["endpoint"]} at {res["endpoint_t_s"]}); scope oom_kill 0 '
                 f'({cgp.events.get("oom_kill")}) max 0 ({cgp.events.get("max")})')
        if arm == 'C2':
            note(f'EXPECTED P6: QM plateau ~{nw} ({qmax}); post-GC <= 1.35 GB ({used_hist[-5:]} MB); no OOM '
                 f'({res["endpoint"]}); gc frac < 0.9 ({frac:.2f})')
        if arm == 'I2':
            note(f'EXPECTED P7: server conns <= 1000 ({cgp.sc_max}); refused >= 2400 ({totals.get("refused")}); '
                 f'QM <= 7128 ({qmax}); no OOM ({res["endpoint"]}); ok/s {res["ok_per_s"]:.1f} (>= 0.5 x C2)')
        if arm == 'X2':
            note(f'EXPECTED P8: heap above idle <= 0.2 GB ([B above idle {bbmax - bb_idle}); no OOM ({res["endpoint"]})')
        if arm == 'I2b':
            note(f'EXPECTED P9: QM <= {E // M + 128} ({qmax}); ovl_bytes > 0 ({totals.get("ovl_bytes")}); no OOM ({res["endpoint"]})')
        if arm in ('T4', 'T8'):
            note(f'EXPECTED P10: OOM if QM >= {(heap_b - 0.3e9) / M:.0f} ({qmax}; endpoint {res["endpoint"]})')
        note(f'EXPECTED P11: direct max <= N*136KiB+0.1GB and < 0.5 U ({res["direct_used_max"]} vs '
             f'{n * 136 * 1024 + 1e8:.0f}, {qmax * M / 2:.0f})')
    note('DONE')


if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'dataset':
        dataset(int(a[1]))
    else:
        def opt(k, d):
            return a[a.index(k) + 1] if k in a else d
        throw = '--throw' in a
        calib = '--calib' in a
        seconds = int(opt('--seconds', '240'))
        per_jvm = int(opt('--per-jvm', '500'))
        W = int(opt('--window', '7'))
        CONNECT_THREADS = int(opt('--connect-threads', '64'))
        extra = opt('--extra', '')
        try:
            run(a[1], a[2], int(a[3]), int(a[4]), int(a[5]), int(a[6]), throw, seconds, per_jvm, calib, extra)
        except SystemExit:
            raise
        except BaseException as e:
            import traceback
            note('EXCEPTION ' + traceback.format_exc()[-1500:])
            kill_children()
            stop_node()
            sys.exit(2)
