#!/usr/bin/env python3
"""Stage 4, recheck of native_transport_receive_queue_capacity-acquireCapacity-queueCapacity--guided (case file section
"Stage-4 design for the recheck claim (2026-11-17)"). One node lifetime on pc72, all capacity knobs at their defaults.

usage: recheck-run.py            (env RECHECK_RUN = run folder name, default run1; RECHECK_SCALE multiplies durations
                                  and windows: a shakedown, not a reading)

Layout (pc72): BASE=/mydata/s4/ntq-recheck: cassandra/ (cp -a of cassandra-base), node/ (conf, data, logs, the hold
file), classes/, logs/<run>/ (session.log, summary.txt with EXPECTED lines, arms.csv, ntq.trace, stdout.txt,
system.log copy, one folder per arm: flood.out, meters-before/after.txt, jmx-poll.csv, cg-poll.csv, histo-*.txt,
handlers.csv, series.csv).
The node runs `bin/cassandra -f` inside `systemd-run --user --scope -p MemoryMax=6G -p MemorySwapMax=0`, a child of
this script, so this script's ssh session must stay open. On any exit the node is stopped and the absence of a
CassandraDaemon is checked. Readings that miss a prediction are written as EXPECTED ... NO and the run goes on.
"""
import json, os, re, signal, subprocess, sys, threading, time

BASE = os.environ.get('RECHECK_BASE', '/mydata/s4/ntq-recheck')
C = BASE + '/cassandra'
NODE = BASE + '/node'
HARNESS = os.path.dirname(os.path.abspath(__file__))
RUN = os.environ.get('RECHECK_RUN', 'run1')
SCALE = float(os.environ.get('RECHECK_SCALE', 1))
LOGS = f'{BASE}/logs/{RUN}'
TRACE = LOGS + '/ntq.trace'
HOLD = NODE + '/hold'
CLASSES = BASE + '/classes'
JMX = 7199
UNIT = 'ntq-recheck-' + RUN
MEMMAX = 6 * 1024 ** 3
BYTEMAN = C + '/build/lib/jars/byteman-4.0.20.jar'
BM_SUBMIT = C + '/build/lib/jars/byteman-submit-4.0.20.jar'
FLOOD_CP = f'{CLASSES}:{C}/build/classes/main:{C}/build/lib/jars/*'
CAP = 1 << 20
SMALL, LARGE = 65000, 262000
QM = 'org.apache.cassandra.transport.messages.QueryMessage'

B_DISC = 'org.apache.cassandra.metrics:type=Client,name=RequestDiscarded'
B_RSIZE = 'org.apache.cassandra.metrics:type=Client,name=RequestsSize'
B_PAUSED = 'org.apache.cassandra.metrics:type=Client,name=PausedConnections'
B_TOBP = 'org.apache.cassandra.metrics:type=Client,name=TimedOutBeforeProcessing'
B_PROTO = 'org.apache.cassandra.metrics:type=Client,name=ProtocolException'
B_POOLU = 'org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=UsedSize'
B_POOLO = 'org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=OverflowSize'
B_DIRECT = 'java.nio:type=BufferPool,name=direct'
B_HEAP = 'java.lang:type=Memory'
METERS = [(B_DISC, 'Count'), (B_RSIZE, 'Value'), (B_PAUSED, 'Value'), (B_TOBP, 'Count'), (B_PROTO, 'Count'),
          (B_POOLU, 'Value'), (B_POOLO, 'Value'), (B_DIRECT, 'MemoryUsed')]
POLL = [(B_HEAP, 'HeapMemoryUsage'), (B_DIRECT, 'MemoryUsed'), (B_DIRECT, 'Count'), (B_POOLU, 'Value'),
        (B_POOLO, 'Value'), (B_RSIZE, 'Value'), (B_PAUSED, 'Value')]
POLL_COLS = 'ms,heap_used,direct_used,direct_count,pool_used,pool_overflow,global_in_use,paused'


def sc(x):
    return max(1, int(round(x * SCALE)))


# (name, kind, throw, value bytes, connections, window, seconds, retry ms, histograms?)
ARMS = [('idle', 'idle', None, 0, 0, 0, sc(10), 0, True),
        ('U10', 'U', False, SMALL, 10, 80, sc(45), 100, False),
        ('D20', 'D', False, SMALL, 20, sc(240), sc(90), 100, True),
        ('D30', 'D', False, SMALL, 30, sc(240), sc(90), 100, True),
        ('D40', 'D', False, SMALL, 40, sc(240), sc(90), 100, True),
        ('T40', 'T', True, SMALL, 40, sc(240), sc(60), 1000, True),
        ('L20', 'L', False, LARGE, 20, sc(60), sc(60), 100, True)]

os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
SUMMARY = open(LOGS + ('/summary-reanalysis.txt' if os.environ.get('RECHECK_ANALYSE_ONLY') else '/summary.txt'), 'w')
EXPECT = {'yes': 0, 'no': 0}
CHILDREN = []
NODE_PROC = None


def log(s):
    line = f'[{time.strftime("%F %T")} {int(time.time() * 1000)}] {s}'
    print(line, file=sys.stderr, flush=True)
    SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    SUMMARY.write(s + '\n'); SUMMARY.flush(); log(s)


def sh(cmd, timeout=600, check=True, env=None, cwd=C, quiet=False):
    log('+ ' + cmd)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
    out = (r.stdout or '') + (r.stderr or '')
    if not quiet:
        SESSION.write(out[-6000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed rc={r.returncode}: {cmd}\n{out[-1500:]}')
    return r.returncode, out


def expect(desc, cond):
    EXPECT['yes' if cond else 'no'] += 1
    note(f'EXPECTED: {desc} — {"yes" if cond else "NO (recorded; judged in the results file)"}')
    return cond


def daemons():
    out = subprocess.run("ps -eo pid,cmd | grep '[C]assandraDaemon' || true", shell=True, capture_output=True,
                         text=True).stdout
    return out.strip()


def node_pid():
    for p in os.listdir('/proc'):
        if not p.isdigit():
            continue
        try:
            cl = open(f'/proc/{p}/cmdline').read()
        except OSError:
            continue
        if 'CassandraDaemon' in cl and NODE + '/logs' in cl:
            return int(p)
    return None


def stop_node():
    pid = node_pid()
    if pid is not None:
        sh(f'bin/nodetool -p {JMX} stopdaemon', check=False, timeout=180)
        for _ in range(90):
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
    if os.path.exists(HOLD):
        os.remove(HOLD)
    left = daemons()
    note('after stop, CassandraDaemon processes on pc72: ' + (left[:300] if left else 'none'))


def fail(msg):
    note('FAIL: ' + msg)
    for p in CHILDREN:
        if p.poll() is None:
            p.kill()
    stop_node()
    note(f'stopped; {EXPECT}')
    sys.exit(1)


def jmx(*args):
    _, out = sh(f'java -cp {CLASSES} Jmx {JMX} ' + ' '.join(f"'{a}'" for a in args), check=False, timeout=60,
                quiet=True)
    return out


def meters(path):
    out = jmx('get', *[x for p in METERS for x in p])
    open(path, 'w').write(out)
    res = {}
    for l in out.splitlines():
        parts = l.split('|')
        if len(parts) == 3:
            key = parts[0].split('name=')[-1] + '.' + parts[1]
            try:
                res[key] = int(float(parts[2]))
            except ValueError:
                res[key] = parts[2]
    return res


def cgroup_dir(pid):
    for l in open(f'/proc/{pid}/cgroup'):
        if l.startswith('0::'):
            return '/sys/fs/cgroup' + l.strip()[3:]
    return None


def client_jvm_opts():
    return ' '.join(l.strip() for l in open(C + '/conf/jvm11-clients.options') if l.strip().startswith('-'))


def start_node():
    global NODE_PROC
    if daemons():
        fail('a CassandraDaemon already runs on this host: ' + daemons()[:200])
    sh(f'rm -rf {NODE}/data {NODE}/logs', check=False)
    env = dict(os.environ, CASSANDRA_HOME=C, NTQ=NODE)
    _, y = sh(f'{HARNESS}/make-node-yaml.sh', env=env)
    note('yaml tail: ' + y.strip().splitlines()[-1][:1500])
    yaml = open(NODE + '/conf/cassandra.yaml').read()
    keys = ['native_transport_receive_queue_capacity', 'native_transport_max_request_data_in_flight',
            'native_transport_max_request_data_in_flight_per_ip', 'native_transport_max_message_size',
            'native_transport_max_threads', 'networking_cache_size', 'native_transport_receive_queue_capacity_in_bytes',
            'native_transport_max_concurrent_requests_in_bytes', 'native_transport_max_concurrent_requests_in_bytes_per_ip']
    setk = [k for k in keys if re.search(rf'^{k}:', yaml, re.M)]
    expect(f'yaml sets none of the knobs under test (set: {setk}); throw_on_overload: '
           f'{re.findall(r"^native_transport_throw_on_overload:.*$", yaml, re.M)}', not setk)
    open(HOLD, 'w').close()
    env = dict(os.environ, CASSANDRA_CONF=NODE + '/conf', CASSANDRA_LOG_DIR=NODE + '/logs', MAX_HEAP_SIZE='2G',
               MAX_DIRECT_MEMORY_SIZE='2G')
    env.pop('HEAP_NEWSIZE', None)
    env['JVM_EXTRA_OPTS'] = (f'-javaagent:{BYTEMAN}=script:{HARNESS}/ntq-trace.btm,script:{HARNESS}/hold-request.btm,'
                             f'listener:true -Dorg.jboss.byteman.verbose=false -Dstage4.trace={TRACE} '
                             f'-Dstage4.hold.file={HOLD} -Dstage4.hold.ms=250')
    cmd = ['systemd-run', '--user', '--scope', '--unit', UNIT, '-p', f'MemoryMax={MEMMAX}', '-p', 'MemorySwapMax=0',
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
    expect(f'node pid {pid} in scope {cg} with memory.max {mm} = {MEMMAX} and memory.swap.max {ms} = 0',
           mm == str(MEMMAX) and ms == '0')
    _, lst = sh(f'java -cp {BM_SUBMIT} org.jboss.byteman.agent.submit.Submit -l', check=False)
    rules = sorted({m.strip() for m in re.findall(r'^RULE (.+)$', lst, re.M)})
    open(LOGS + '/submit-l.txt', 'w').write(lst)
    if not expect(f'Submit -l lists the 9 rules ({len(rules)}: {rules})', len(rules) == 9):
        fail('Byteman rules not loaded')
    jvm = open(f'/proc/{pid}/cmdline').read().replace('\0', ' ')
    note('jvm: ' + ' '.join(t for t in jvm.split()
                            if t.startswith(('-Xm', '-XX:MaxDirect', '-javaagent', '-Dstage4', '-XX:+Use'))))
    rc, out = sh(f'bin/cqlsh 127.0.0.1 9042 -e "CREATE KEYSPACE ks WITH replication = '
                 "{'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE ks.t (pk int PRIMARY KEY, v blob);\"",
                 check=False, timeout=120)
    if rc != 0:
        fail('schema: ' + out[-400:])
    note('schema: ks (RF 1), ks.t (pk int PRIMARY KEY, v blob)')
    return pid, cg


def histogram(pid, path):
    h0 = int(time.time() * 1000)
    sh(f'jcmd {pid} GC.class_histogram > {path}', check=False, timeout=180, quiet=True)
    h1 = int(time.time() * 1000)
    qm = bb = 0
    for l in open(path, errors='replace'):
        p = l.split()
        if len(p) >= 4 and p[3] == QM:
            qm = int(p[1])
        if len(p) >= 4 and p[3] == '[B':
            bb = int(p[2])
    log(f'histogram {path}: {h0}-{h1} QueryMessage={qm} [B={bb}')
    return h0, h1, qm, bb


class Poller(threading.Thread):
    """the scope's memory.current and oom_kill every 2 s"""
    def __init__(self, cg, path):
        super().__init__(daemon=True)
        self.cg, self.f, self.stop_flag, self.max = cg, open(path, 'w'), False, 0
        self.f.write('ms,memory_current,oom_kill\n')

    def run(self):
        while not self.stop_flag:
            try:
                cur = int(open(self.cg + '/memory.current').read())
                ev = dict(l.split() for l in open(self.cg + '/memory.events'))
                self.max = max(self.max, cur)
                self.f.write(f'{int(time.time() * 1000)},{cur},{ev.get("oom_kill")}\n'); self.f.flush()
            except OSError:
                pass
            time.sleep(2)


def run_arm(pid, cg, arm):
    name, kind, throw, size, conns, window, seconds, retry, histos_wanted = arm
    D = f'{LOGS}/{name}'
    os.makedirs(D, exist_ok=True)
    note(f'--- arm {name}: kind={kind} throw={throw} value_bytes={size} N={conns} W={window} seconds={seconds} '
         f'retry_ms={retry}')
    mb = meters(D + '/meters-before.txt')
    stop = D + '/stop-poll'
    pj = subprocess.Popen(['java', '-cp', CLASSES, 'Jmx', str(JMX), 'poll', '2000', '100000', stop] +
                          [x for p in POLL for x in p], stdout=open(D + '/jmx-poll.csv', 'w'),
                          stderr=subprocess.STDOUT)
    CHILDREN.append(pj)
    cgp = Poller(cg, D + '/cg-poll.csv'); cgp.start()
    histos = []
    t_start = int(time.time() * 1000)
    if kind == 'idle':
        time.sleep(seconds / 2)
        histos.append(histogram(pid, D + '/histo-1.txt'))
        time.sleep(seconds / 2)
        fl_rc = 0
    else:
        args = (f'--host 127.0.0.1 --port 9042 --connections {conns} --window {window} --value-bytes {size} '
                f'--seconds {seconds} --throw {"true" if throw else "false"} --retry-ms {retry}')
        cmd = (f'java {client_jvm_opts()} -Dio.netty.eventLoopThreads=1 '
               f'-Dlogback.configurationFile={HARNESS}/flood-logback.xml -Xmx4g '
               f'-cp "{FLOOD_CP}" org.apache.cassandra.transport.NativeFlood {args}')
        log(f'+ ({name}) {cmd}')
        fl = subprocess.Popen(cmd, shell=True, cwd=C, stdout=open(D + '/flood.out', 'w'), stderr=subprocess.STDOUT)
        CHILDREN.append(fl)
        if histos_wanted:
            for frac in (1 / 3, 2 / 3):
                at = t_start / 1000 + 2 + frac * seconds   # ~2 s of client start-up before 'start'
                while time.time() < at and fl.poll() is None:
                    time.sleep(0.2)
                if fl.poll() is None:
                    histos.append(histogram(pid, f'{D}/histo-{len(histos) + 1}.txt'))
        try:
            fl_rc = fl.wait(timeout=seconds + 240)
        except subprocess.TimeoutExpired:
            fl.kill(); fl_rc = 'timeout'
    t_end = int(time.time() * 1000)
    # drain: the global reserve in use back to 0
    drained = None
    for _ in range(30):
        m = meters(D + '/meters-drain.txt')
        drained = m.get('RequestsSize.Value')
        if drained == 0:
            break
        time.sleep(1)
    open(stop, 'w').close()
    cgp.stop_flag = True
    time.sleep(2.5)
    if pj.poll() is None:
        pj.kill()
    ma = meters(D + '/meters-after.txt')
    note(f'{name}: client rc={fl_rc}; meters before {mb}; after {ma}; global in use after drain {drained}; '
         f'scope memory.current max {cgp.max}')
    res = dict(arm=list(arm), D=D, t_start=t_start, t_end=t_end, mb=mb, ma=ma, histos=histos, fl_rc=fl_rc,
               drained=drained, cgmax=cgp.max)
    with open(LOGS + '/arms.jsonl', 'a') as f:
        f.write(json.dumps(res) + '\n')
    return res


# ------------------------------------------------------------------ analysis (after the node is stopped)

NEW_RX = re.compile(r'^new id=(\S+) throw=(\S+) cap=(\d+) srv=(\S+) remote=/?(\S+) ms=(\d+)$')
ACQ_RX = re.compile(r'^acq id=(\S+) b=(\d+) out=(\S+) q=(-?\d+) cap=(\d+) ep=(-?\d+)/(\d+) gl=(-?\d+)/(\d+) ms=(\d+)$')
REL_RX = re.compile(r'^rel id=(\S+) b=(\d+) q=(-?\d+) ms=(\d+)$')
DEC_RX = re.compile(r'^dec id=(\S+) b=(\d+) bp=(\S+) ms=(\d+)$')
RLS_RX = re.compile(r'^rls id=(\S+) b=(\d+) ms=(\d+)$')
DISC_RX = re.compile(r'^disc id=(\S+) b=(\d+) ov=(\S+) ms=(\d+)$')
LDISC_RX = re.compile(r'^ldisc id=(\S+) b=(\d+) ms=(\d+)$')
WAKE_RX = re.compile(r'^wake id=(\S+) ns=(-?\d+) ms=(\d+)$')


def parse_trace():
    handlers, ev, other, holds = {}, [], [], 0
    for l in open(TRACE, errors='replace'):
        l = l.rstrip('\n')
        m = ACQ_RX.match(l)
        if m:
            g = m.groups()
            ev.append(('acq', g[0], int(g[1]), g[2], int(g[3]), int(g[9]), int(g[5]), int(g[7]), int(g[6]), int(g[8])))  # ms, ep/gl using, ep/gl limit
            continue
        m = REL_RX.match(l)
        if m:
            ev.append(('rel', m.group(1), int(m.group(2)), None, int(m.group(3)), int(m.group(4))))
            continue
        m = DEC_RX.match(l)
        if m:
            ev.append(('dec', m.group(1), int(m.group(2)), m.group(3), None, int(m.group(4))))
            continue
        m = RLS_RX.match(l)
        if m:
            ev.append(('rls', m.group(1), int(m.group(2)), None, None, int(m.group(3))))
            continue
        m = DISC_RX.match(l)
        if m:
            ev.append(('disc', m.group(1), int(m.group(2)), m.group(3), None, int(m.group(4))))
            continue
        m = LDISC_RX.match(l)
        if m:
            ev.append(('ldisc', m.group(1), int(m.group(2)), None, None, int(m.group(3))))
            continue
        m = WAKE_RX.match(l)
        if m:
            ev.append(('wake', m.group(1), 0, None, None, int(m.group(3))))
            continue
        if l.startswith('hold '):
            holds += 1
            continue
        m = NEW_RX.match(l)
        if m:
            handlers[m.group(1)] = dict(throw=m.group(2) == 'true', cap=int(m.group(3)), remote=m.group(5))
            continue
        if l.strip():
            other.append(l)
    return handlers, ev, other, holds


def flood_info(D):
    ports, total, start_ms, stop_ms, texts = [], {}, None, None, []
    for l in open(D + '/flood.out', errors='replace'):
        m = re.match(r'^conn \d+ local=/?(\S+) throw=', l)
        if m:
            ports.append(m.group(1))
        m = re.match(r'^start ms=(\d+)', l)
        if m:
            start_ms = int(m.group(1))
        m = re.match(r'^stop ms=(\d+)', l)
        if m:
            stop_ms = int(m.group(1))
        if l.startswith('TOTAL'):
            total = {k: int(v) for k, v in re.findall(r'(\w+)=(-?\d+)', l)}
        if l.startswith(('ovl_other_text', 'err_text')):
            texts.append(l.strip())
    return ports, total, start_ms, stop_ms, texts


def analyse_arm(r, handlers, ev):
    name, kind, throw, size, conns, window, seconds, retry, _ = r['arm']
    D = r['D']
    ports, total, s_ms, e_ms, texts = flood_info(D)
    ids = {i for i, h in handlers.items() if h['remote'] in set(ports)}
    note(f'{name}: {len(ids)} server handlers matched to {len(ports)} client connections; client TOTAL {total}; '
         f'texts {texts}')
    expect(f'{name}: every client connection has its server handler ({len(ids)} = {conns}), each with cap = {CAP} '
           f'and throw = {throw}', len(ids) == conns and all(handlers[i]['cap'] == CAP and handlers[i]['throw'] == throw
                                                             for i in ids))
    ph = {i: dict(succ=0, ref=0, dec=0, dec_bif=0, rls=0, disc=0, ldisc=0, wake=0, q=0, d=0, dmax=0) for i in ids}
    sumA = sumD = 0
    peakA = peakD = 0
    viol_DA = 0                # lines with sumD > sumA
    series = {}                # second -> (sumA, sumD) at the end of that second
    epl, gll, glmax, epmax = {}, {}, 0, 0
    Ms = {}
    for e in ev:
        i = e[1]
        if i not in ids:
            continue
        k = e[0]
        h = ph[i]
        if k == 'acq':
            if e[3] == 'SUCCESS':
                h['succ'] += 1
            else:
                h['ref'] += 1
            sumA += e[4] - h['q']; h['q'] = e[4]
            epl[e[8]] = epl.get(e[8], 0) + 1; gll[e[9]] = gll.get(e[9], 0) + 1
            epmax = max(epmax, e[6]); glmax = max(glmax, e[7])
        elif k == 'rel':
            sumA += e[4] - h['q']; h['q'] = e[4]
        elif k == 'dec':
            h['dec'] += 1
            if e[3] == 'BYTES_IN_FLIGHT':
                h['dec_bif'] += 1
            h['d'] += e[2]; sumD += e[2]; h['dmax'] = max(h['dmax'], h['d'])
            Ms[e[2]] = Ms.get(e[2], 0) + 1
        elif k == 'rls':
            h['rls'] += 1
            h['d'] -= e[2]; sumD -= e[2]
        elif k == 'disc':
            h['disc'] += 1
        elif k == 'ldisc':
            h['ldisc'] += 1
        elif k == 'wake':
            h['wake'] += 1
        peakA = max(peakA, sumA); peakD = max(peakD, sumD)
        if sumD > sumA:
            viol_DA += 1
        series[e[5] // 1000] = (sumA, sumD)
    E = max(epl, key=epl.get) if epl else None
    G = max(gll, key=gll.get) if gll else None
    K = conns * CAP + E if E is not None else None
    M = max(Ms, key=Ms.get) if Ms else None
    ref = sum(h['ref'] for h in ph.values())
    with open(D + '/handlers.csv', 'w') as f:
        f.write('id,remote,succ,ref,dec,dec_bif,rls,disc,ldisc,wake,end_q,end_d,dmax\n')
        for i in sorted(ids):
            h = ph[i]
            f.write(f'{i},{handlers[i]["remote"]},{h["succ"]},{h["ref"]},{h["dec"]},{h["dec_bif"]},{h["rls"]},'
                    f'{h["disc"]},{h["ldisc"]},{h["wake"]},{h["q"]},{h["d"]},{h["dmax"]}\n')
    with open(D + '/series.csv', 'w') as f:
        f.write('sec_ms,sumA,sumD\n')
        for s in sorted(series):
            f.write(f'{s * 1000},{series[s][0]},{series[s][1]}\n')
    # last-third mean of sumD over the client's sending window (per-second samples, carried forward)
    lt_mean = None
    if s_ms and e_ms:
        a = s_ms + (e_ms - s_ms) * 2 // 3
        vals, cur = [], None
        for s in range(min(series) if series else 0, e_ms // 1000 + 1):
            if s in series:
                cur = series[s][1]
            if s * 1000 >= a and cur is not None:
                vals.append(cur)
        lt_mean = sum(vals) / len(vals) if vals else None
    V = conns * window * M if M else None
    note(f'{name}: M={M} (dec sizes {dict(sorted(Ms.items(), key=lambda x: -x[1])[:3])}); E={E} G={G} K={K} V={V}; '
         f'refusals={ref}; peak sumA={peakA}; peak sumD={peakD}; last-third mean sumD={lt_mean}; '
         f'ep max in use={epmax}; gl max in use={glmax}; lines sumD>sumA={viol_DA}; holds n/a')
    res = dict(name=name, kind=kind, M=M, E=E, G=G, K=K, V=V, ref=ref, peakA=peakA, peakD=peakD, lt=lt_mean, ph=ph,
               total=total, viol_DA=viol_DA, series=series, s_ms=s_ms, e_ms=e_ms, glmax=glmax, epmax=epmax)
    # exact bound on sumA: recompute over the arm with the final K
    sA = 0; q = {i: 0 for i in ids}; over = 0
    for e in ev:
        if e[1] in ids and e[0] in ('acq', 'rel'):
            sA += e[4] - q[e[1]]; q[e[1]] = e[4]
            if K is not None and sA > K:
                over += 1
    res['overK'] = over
    return res


def poll_stats(D):
    rows = []
    try:
        for l in open(D + '/jmx-poll.csv'):
            p = l.strip().split(',')
            if len(p) == 8 and p[0].isdigit():
                try:
                    rows.append([int(float(x)) for x in p])
                except ValueError:
                    pass
    except OSError:
        pass
    return rows


def main():
    for f in ('ntq-trace.btm', 'hold-request.btm', 'NativeFlood.java', 'Jmx.java', 'make-node-yaml.sh',
              'recheck-run.py'):
        _, o = sh(f'md5sum {HARNESS}/{f}', quiet=True)
        note('harness md5 ' + o.split()[0] + ' ' + f)
    note(f'run={RUN} scale={SCALE} base={BASE} host={os.uname().nodename}')
    if os.environ.get('RECHECK_ANALYSE_ONLY'):
        note('analysis only, from arms.jsonl and ntq.trace of this run folder')
        results = [json.loads(l) for l in open(LOGS + '/arms.jsonl')]
        return analyse(results)
    if os.path.exists(LOGS + '/arms.jsonl'):
        os.remove(LOGS + '/arms.jsonl')
    os.makedirs(CLASSES, exist_ok=True)
    sh(f'javac -d {CLASSES} {HARNESS}/Jmx.java')
    sh(f'javac -nowarn -d {CLASSES} -cp "{C}/build/classes/main:{C}/build/lib/jars/*" {HARNESS}/NativeFlood.java')
    pid, cg = start_node()
    results = []
    try:
        for arm in ARMS:
            if node_pid() is None:
                fail(f'node gone before arm {arm[0]}')
            results.append(run_arm(pid, cg, arm))
        oomk = [l for l in open(cg + '/memory.events')] if os.path.exists(cg + '/memory.events') else []
        note('scope memory.events at end: ' + ' '.join(x.strip() for x in oomk))
        try:
            note('scope memory.peak: ' + open(cg + '/memory.peak').read().strip())
        except OSError:
            note('scope memory.peak: not available (max of the 2 s memory.current polls per arm is in each arm line)')
    except Exception as ex:   # noqa
        note('EXCEPTION ' + repr(ex))
        stop_node()
        raise
    stop_node()
    sh(f'cp {NODE}/logs/system.log {LOGS}/system.log', check=False)
    analyse(results)


def analyse(results):
    handlers, ev, other, holds = parse_trace()
    note(f'trace: {len(handlers)} handlers, {len(ev)} events, {holds} hold lines, {len(other)} other lines '
         f'(first: {other[:3]})')
    sl = open(LOGS + '/system.log', errors='replace').read() if os.path.exists(LOGS + '/system.log') else ''
    for t in ('requests/second', 'spent over', 'timed out before it could start', 'java.lang.OutOfMemoryError'):
        expect(f'system.log has no "{t}" ({sl.count(t)})', sl.count(t) == 0)
    expect('system.log has no ERROR line (' + str(len(re.findall(r'^ERROR', sl, re.M))) + ')',
           not re.search(r'^ERROR', sl, re.M))
    idle = next(r for r in results if r['arm'][0] == 'idle')
    ip = poll_stats(idle['D'])
    idle_direct = sum(r[2] for r in ip) / len(ip) if ip else 0
    idle_pool = sum(r[4] + r[5] for r in ip) / len(ip) if ip else 0
    idle_bb = idle['histos'][0][3] if idle['histos'] else 0
    note(f'idle: direct MemoryUsed mean {idle_direct:.0f}; pool used+overflow mean {idle_pool:.0f}; '
         f'idle histogram {idle["histos"]}')
    armres = {}
    csv = open(LOGS + '/arms.csv', 'w')
    csv.write('arm,N,W,M,E,G,K,V,refusals,dec_bif,disc,ldisc,wake,warned,ovl_bytes,ovl_other,err,outstanding,'
              'discarded_delta,peak_sumA,peak_sumD,lastthird_sumD,lines_sumA_over_K,end_q_sum,end_q_nonzero,'
              'direct_max_minus_idle,pool_max_minus_idle,heap_used_max,cg_max,histos\n')
    for r in results:
        name, kind, throw, size, conns, window, seconds, retry, _ = r['arm']
        if kind == 'idle':
            continue
        a = analyse_arm(r, handlers, ev)
        armres[name] = a
        ph, t = a['ph'], a['total']
        M, K, G, V = a['M'], a['K'], a['G'], a['V']
        dec_bif = sum(h['dec_bif'] for h in ph.values())
        disc = sum(h['disc'] for h in ph.values())
        ldisc = sum(h['ldisc'] for h in ph.values())
        wake = sum(h['wake'] for h in ph.values())
        endq = sum(h['q'] for h in ph.values())
        ddisc = r['ma'].get('RequestDiscarded.Count', 0) - r['mb'].get('RequestDiscarded.Count', 0)
        dtobp = r['ma'].get('TimedOutBeforeProcessing.Count', 0) - r['mb'].get('TimedOutBeforeProcessing.Count', 0)
        dproto = r['ma'].get('ProtocolException.Count', 0) - r['mb'].get('ProtocolException.Count', 0)
        rows = poll_stats(r['D'])
        dmax = max((x[2] for x in rows), default=0) - idle_direct
        pmax = max((x[4] + x[5] for x in rows), default=0) - idle_pool
        hmax = max((x[1] for x in rows), default=0)
        a.update(dmax=dmax, pmax=pmax, hmax=hmax)
        # validity (prediction 10)
        expect(f'{name}: client drained (outstanding {t.get("outstanding")}), rc {r["fl_rc"]}, ovl_other '
               f'{t.get("ovl_other")}, err {t.get("err")}; TimedOutBeforeProcessing +{dtobp}, ProtocolException +{dproto}',
               t.get('outstanding') == 0 and r['fl_rc'] == 0 and t.get('ovl_other') == 0 and t.get('err') == 0
               and dtobp == 0 and dproto == 0)
        expect(f'{name}: global reserve in use 0 after the drain ({r["drained"]})', r['drained'] == 0)
        # histogram band
        hb = []
        for (h0, h1, qm, bb) in r['histos']:
            vals = [sd for s, (sa, sd) in a['series'].items() if h0 - 1000 <= s * 1000 + 999 and s * 1000 <= h1 + 1000]
            lo = min(vals) / M if vals and M else None
            hi = max(vals) / M if vals and M else None
            hb.append((h0, h1, qm, bb, lo, hi))
            note(f'{name}: histogram {h0}-{h1} ms: QueryMessage {qm}, [B {bb}; sumD/M over the interval ±1 s '
                 f'[{lo}, {hi}]')
        a['hb'] = hb
        if kind == 'U':
            expect(f'{name} (P7): no refusal ({a["ref"]})', a['ref'] == 0)
            expect(f'{name} (P7): sumD <= sumA at every line ({a["viol_DA"]} violations) and peak sumA {a["peakA"]} '
                   f'<= {conns * window * M}', a['viol_DA'] == 0 and a['peakA'] <= conns * window * M)
            expect(f'{name} (P7): every handler ends at queueSize 0 (sum {endq}, nonzero '
                   f'{sum(1 for h in ph.values() if h["q"] != 0)})', all(h['q'] == 0 for h in ph.values()))
        if kind == 'D':
            expect(f'{name} (P1): refusals occur ({a["ref"]})', a['ref'] > 0)
            expect(f'{name} (P1): per handler dec bp=BYTES_IN_FLIGHT = refusals (total {dec_bif} = {a["ref"]}; '
                   f'handlers differing {sum(1 for h in ph.values() if h["dec_bif"] != h["ref"])})',
                   all(h['dec_bif'] == h['ref'] for h in ph.values()))
            expect(f'{name} (P1): client warned {t.get("warned")} = refusals {a["ref"]}', t.get('warned') == a['ref'])
            expect(f'{name} (P1): RequestDiscarded +{ddisc} = 0 and client overloads {t.get("ovl_bytes")} = 0',
                   ddisc == 0 and t.get('ovl_bytes') == 0)
            expect(f'{name} (P2): every handler ends at queueSize = -k_i*M (sum {endq} = {-a["ref"] * M}; handlers '
                   f'differing {sum(1 for h in ph.values() if h["q"] != -h["ref"] * M)})',
                   all(h['q'] == -h['ref'] * M for h in ph.values()))
            expect(f'{name} (P3): sumA <= K = {K} at every line ({a["overK"]} lines over; peak {a["peakA"]})',
                   a['overK'] == 0)
            lt = a['lt'] or 0
            expect(f'{name} (P3): last-third mean sumD {lt:.0f} in [0.85 V, V] = [{0.85 * V:.0f}, {V}] and > G = {G} '
                   f'(x{lt / G:.3f} of G, x{lt / K:.3f} of K)', 0.85 * V <= lt <= V and lt > G)
            expect(f'{name} (P3): every handler peak D_i > C (min {min(h["dmax"] for h in ph.values())})',
                   all(h['dmax'] > CAP for h in ph.values()))
            for k_, (h0, h1, qm, bb, lo, hi) in enumerate(hb):
                expect(f'{name} (P5): histogram {k_ + 1}: QueryMessage {qm} within sumD/M band [{lo}, {hi}] (±1)',
                       lo is not None and lo - 1 <= qm <= hi + 1)
            if len(hb) >= 2:
                h0, h1, qm, bb, lo, hi = hb[1]
                expect(f'{name} (P5): histogram 2: count*M = {qm * M} > G = {G}', qm * M > G)
                expect(f'{name} (P5): histogram 2: [B {bb} - idle {idle_bb} = {bb - idle_bb} >= 0.9*count*65000 = '
                       f'{0.9 * qm * 65000:.0f}', bb - idle_bb >= 0.9 * qm * 65000)
            expect(f'{name} (P6): direct MemoryUsed max - idle = {dmax:.0f} < 64 MiB and pool used+overflow max - '
                   f'idle = {pmax:.0f} < 64 MiB', dmax < 64 * 2 ** 20 and pmax < 64 * 2 ** 20)
        if kind == 'T':
            expect(f'{name} (P8): refusals {a["ref"]} > 0 and = disc {disc} = RequestDiscarded +{ddisc} = client '
                   f'overloads {t.get("ovl_bytes")}', a['ref'] > 0 and a['ref'] == disc == ddisc == t.get('ovl_bytes'))
            expect(f'{name} (P8): per handler dec = SUCCESS acquires (handlers differing '
                   f'{sum(1 for h in ph.values() if h["dec"] != h["succ"])})',
                   all(h['dec'] == h['succ'] for h in ph.values()))
            expect(f'{name} (P8): sumA <= K = {K} at every line ({a["overK"]} over) and peak {a["peakA"]} >= 0.9 K',
                   a['overK'] == 0 and a['peakA'] >= 0.9 * K)
            expect(f'{name} (P8): sumD <= sumA at every line ({a["viol_DA"]}) so peak sumD {a["peakD"]} < G {G}',
                   a['viol_DA'] == 0 and a['peakD'] < G)
            expect(f'{name} (P8): every handler ends at 0 (sum {endq})', all(h['q'] == 0 for h in ph.values()))
            for k_, (h0, h1, qm, bb, lo, hi) in enumerate(hb):
                expect(f'{name} (P8): histogram {k_ + 1}: QueryMessage {qm} <= K/M + 10 = {K / M + 10:.1f}',
                       qm <= K / M + 10)
        if kind == 'L':
            expect(f'{name} (P9): refusals {a["ref"]} > 0, no dec bp=BYTES_IN_FLIGHT ({dec_bif}), client warned '
                   f'{t.get("warned")} = 0', a['ref'] > 0 and dec_bif == 0 and t.get('warned') == 0)
            expect(f'{name} (P9): per handler dec = SUCCESS acquires (handlers differing '
                   f'{sum(1 for h in ph.values() if h["dec"] != h["succ"])})',
                   all(h['dec'] == h['succ'] for h in ph.values()))
            expect(f'{name} (P9): sumA <= K = {K} at every line ({a["overK"]} over); sumD <= sumA ({a["viol_DA"]})',
                   a['overK'] == 0 and a['viol_DA'] == 0)
            expect(f'{name} (P9): every handler ends at 0 (sum {endq})', all(h['q'] == 0 for h in ph.values()))
        csv.write(f'{name},{conns},{window},{M},{a["E"]},{G},{K},{V},{a["ref"]},{dec_bif},{disc},{ldisc},{wake},'
                  f'{t.get("warned")},{t.get("ovl_bytes")},{t.get("ovl_other")},{t.get("err")},{t.get("outstanding")},'
                  f'{ddisc},{a["peakA"]},{a["peakD"]},{a["lt"]},{a["overK"]},{endq},'
                  f'{sum(1 for h in ph.values() if h["q"] != 0)},{dmax:.0f},{pmax:.0f},{hmax},{r["cgmax"]},'
                  f'{";".join(f"{x[2]}/{x[3]}" for x in hb)}\n')
    csv.close()
    ds = [armres[n] for n in ('D20', 'D30', 'D40') if n in armres]
    if len(ds) == 3 and all(d['lt'] for d in ds):
        per = [d['lt'] / n for d, n in zip(ds, (20, 30, 40))]
        avg = sum(per) / 3
        expect(f'P4: last-third mean sumD per connection {[round(p) for p in per]} within ±10 % of their mean '
               f'{avg:.0f} (W*M = {ds[0]["V"] / 20:.0f})', all(abs(p - avg) <= 0.1 * avg for p in per))
    note(f'END {EXPECT}')


if __name__ == '__main__':
    try:
        main()
    finally:
        if node_pid() is not None:
            stop_node()
