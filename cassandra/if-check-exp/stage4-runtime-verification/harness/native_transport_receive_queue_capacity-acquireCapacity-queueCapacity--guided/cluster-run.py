#!/usr/bin/env python3
"""Stage 4, cluster tier, native_transport_receive_queue_capacity-acquireCapacity-queueCapacity (case 9b-9e, amended
2026-10-15).
usage: cluster-run.py <label> | down
  <label>  one lifetime of the node: wipe ~/stage4-ntq/data, build the yaml (make-node-yaml.sh with the label's keys),
           start the node with the Byteman agent (ntq-trace.btm, hold-request.btm; Submit -l must list 9 rules), create
           ks (RF 1) and ks.t, then run the label's arms one after the other. Labels:
             c128k c512k c1m c4m   capacity 128 KiB / 512 KiB / 1 MiB / 4 MiB, both reserves 4 MiB, max message 2 MiB:
                                   ctrl, connidle, A_throw, A_def, Bts, Btl, Bdl, Bds
             nsweep                1 MiB, reserves 4 MiB: n1, n10, n100 (throwing small, W = 32, 30 s)
             defres                512 KiB, reserves and max message size at their defaults: defres (throwing small,
                                   N = 10, W = 128, 60 s)
  down     stop the node of this harness.
Arms: ctrl = 10 s, no client; connidle = 10 throwing + 10 default connections, no request, 10 s; A_* = small requests,
W = floor(C / M_s), 20 s; Bts/Btl = throwing small/large, W = ceil(2 (C + R/N) / M), 60 s; Bdl = default large, W = 32,
60 s; Bds = default small, W = 128, 180 s. Every arm: Client meters before and after, Jmx poll every 2 s (networking
pool, heap, global reserve in use), two class histograms at 1/3 and 2/3 of every B arm, the client's output,
the drain check (Client.RequestsSize back to 0). The hold file exists for the whole lifetime: every ks.t request sleeps
500 ms after its decode.
Writes: ~/stage4-logs/ntq/<run>/<label>/ (summary.txt with EXPECTED lines, session.log, arms.csv, ntq.trace written by
the node, one folder per arm with flood.out, meters, jmx-poll.csv, histo-*.txt, series.csv). Exit 1: a set-up or
instrument check failed (the node not up, Submit -l, the read-back, a client that could not connect); on any exit the
node is stopped. Readings that miss a prediction are recorded as EXPECTED ... NO and the run goes on.
Environment: NTQ_RUN (run folder name, default run1), NTQ_ARMS (comma list: only these arms; a shakedown, not a
reading), NTQ_SCALE (multiplies every arm's duration; a shakedown, not a reading)."""
import math, os, re, subprocess, sys, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-run1')
HARNESS = os.path.dirname(os.path.abspath(__file__))
NTQ = os.environ.get('NTQ', HOME + '/stage4-ntq')
RUN = os.environ.get('NTQ_RUN', 'run1')
ONLY_ARMS = [a for a in os.environ.get('NTQ_ARMS', '').split(',') if a]
SCALE = float(os.environ.get('NTQ_SCALE', 1))
KIB, MIB = 1024, 1 << 20
R = 4 * MIB                      # both reserves (9b)
N = 10                           # connections per arm (9b)
SMALL, LARGE = 65000, 262000     # value bytes (9b amended)
M_EST = {SMALL: 65100, LARGE: 262100}   # body estimate used only to size the throwing windows (9a amended notation)
JMX = 7199
BYTEMAN = C + '/build/lib/jars/byteman-4.0.20.jar'
BM_SUBMIT = C + '/build/lib/jars/byteman-submit-4.0.20.jar'
HOLD = NTQ + '/hold'
FLOOD_CP = f'{HOME}/stage4-harness-run/ntq/classes:{C}/build/classes/main:{C}/build/lib/jars/*'
QM_CLASS = 'org.apache.cassandra.transport.messages.QueryMessage'

B_DISC = 'org.apache.cassandra.metrics:type=Client,name=RequestDiscarded'
B_RSIZE = 'org.apache.cassandra.metrics:type=Client,name=RequestsSize'
B_PAUSED = 'org.apache.cassandra.metrics:type=Client,name=PausedConnections'
B_CPAUSE = 'org.apache.cassandra.metrics:type=Client,name=ConnectionPaused'
B_TOBP = 'org.apache.cassandra.metrics:type=Client,name=TimedOutBeforeProcessing'
B_PROTO = 'org.apache.cassandra.metrics:type=Client,name=ProtocolException'
B_POOLU = 'org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=UsedSize'
B_POOLO = 'org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=OverflowSize'
B_HEAP = 'java.lang:type=Memory'
METERS = [(B_DISC, 'Count'), (B_RSIZE, 'Value'), (B_PAUSED, 'Value'), (B_CPAUSE, 'Count'), (B_TOBP, 'Count'),
          (B_PROTO, 'Count'), (B_POOLU, 'Value'), (B_POOLO, 'Value')]


def wt(cap, size):
    """the throwing arms' window, ceil(2 (C + R/N) / M) (9a amended notation)"""
    return math.ceil(2 * (cap + R / N) / M_EST[size])


def b_arms(cap):
    return [('ctrl', 'ctrl', None, 0, 0, 10),
            ('connidle', 'connidle', None, 0, 0, 10),
            ('A_throw', 'A', True, SMALL, cap // M_EST[SMALL], 20),
            ('A_def', 'A', False, SMALL, cap // M_EST[SMALL], 20),
            ('Bts', 'Bt', True, SMALL, wt(cap, SMALL), 60),
            ('Btl', 'Bt', True, LARGE, wt(cap, LARGE), 60),
            ('Bdl', 'Bdl', False, LARGE, 32, 60),
            ('Bds', 'Bds', False, SMALL, 128, 180)]


RES = [f'native_transport_max_request_data_in_flight_per_ip={R // MIB}MiB',
       f'native_transport_max_request_data_in_flight={R // MIB}MiB', 'native_transport_max_message_size=2MiB']
# label: (yaml keys, capacity, reserves pinned?, arms as (name, kind, throw, value bytes, window, seconds[, connections]))
LABELS = {
    'c128k': (['native_transport_receive_queue_capacity=128KiB'] + RES, 128 * KIB, True, b_arms(128 * KIB)),
    'c512k': (['native_transport_receive_queue_capacity=512KiB'] + RES, 512 * KIB, True, b_arms(512 * KIB)),
    'c1m': (['native_transport_receive_queue_capacity=1MiB'] + RES, MIB, True, b_arms(MIB)),
    'c4m': (['native_transport_receive_queue_capacity=4MiB'] + RES, 4 * MIB, True, b_arms(4 * MIB)),
    'nsweep': (['native_transport_receive_queue_capacity=1MiB'] + RES, MIB, True,
               [('n1', 'n', True, SMALL, 32, 30, 1), ('n10', 'n', True, SMALL, 32, 30, 10),
                ('n100', 'n', True, SMALL, 32, 30, 100)]),
    'defres': (['native_transport_receive_queue_capacity=512KiB'], 512 * KIB, False,
               [('defres', 'defres', True, SMALL, 128, 60)]),
}

label = sys.argv[1] if len(sys.argv) > 1 else ''
if label not in LABELS and label != 'down':
    sys.exit(__doc__)
LOGS = f'{HOME}/stage4-logs/ntq/{RUN}/{label}'
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
SUMMARY = open(LOGS + '/summary.txt', 'a' if label == 'down' else 'w')
EXPECT = {'yes': 0, 'no': 0}
TRACE = LOGS + '/ntq.trace'


# ---------------------------------------------------------------- plumbing

def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, file=sys.stderr)
    SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush(); log(s)


def sh(cmd, timeout=600, check=True, env=None, cwd=C, quiet=False):
    log('+ ' + cmd)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
    out = (r.stdout or '') + (r.stderr or '')
    if not quiet:
        SESSION.write(out[-6000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed rc={r.returncode}: {cmd}\n{out[-1200:]}')
    return r.returncode, out


def expect(desc, cond):
    EXPECT['yes' if cond else 'no'] += 1
    note(f'EXPECTED: {desc} — {"yes" if cond else "NO (recorded; the AI judges it in the results file)"}')
    return cond


def pid_of():
    f = NTQ + '/cassandra.pid'
    if not os.path.exists(f):
        return None
    try:
        pid = int(open(f).read().strip())
        return pid if 'CassandraDaemon' in open(f'/proc/{pid}/cmdline').read() else None
    except (ValueError, OSError):
        return None


def any_daemon():
    _, out = sh("ps -eo pid,cmd | grep '[C]assandraDaemon' || true", check=False, quiet=True)
    return out.strip()


def stop_node():
    if pid_of() is not None:
        sh(f'bin/nodetool -p {JMX} stopdaemon', check=False, timeout=180)
        for _ in range(120):
            if pid_of() is None:
                break
            time.sleep(1)
        pid = pid_of()
        if pid is not None:
            log(f'node did not stop; kill -9 {pid}')
            subprocess.run(['kill', '-9', str(pid)])
            time.sleep(2)
    if os.path.exists(HOLD):
        os.remove(HOLD)
    left = any_daemon()
    if left:
        log('WARNING: a CassandraDaemon is still running: ' + left[:300])


CHILDREN = []


def fail(msg):
    note('FAIL: ' + msg)
    for p in CHILDREN:
        if p.poll() is None:
            p.kill()
    stop_node()
    note(f'stopped; {EXPECT}')
    sys.exit(1)


def compile_tools():
    d = NTQ + '/jmxcls'
    os.makedirs(d, exist_ok=True)
    sh(f'javac -d {d} {HARNESS}/Jmx.java')
    cls = f'{HOME}/stage4-harness-run/ntq/classes'
    os.makedirs(cls, exist_ok=True)
    sh(f'javac -nowarn -d {cls} -cp "{C}/build/classes/main:{C}/build/lib/jars/*" {HARNESS}/NativeFlood.java')


def jmx(*args):
    _, out = sh(f'java -cp {NTQ}/jmxcls Jmx {JMX} ' + ' '.join(f"'{a}'" for a in args), check=False, timeout=60, quiet=True)
    SESSION.write(out[-3000:] + '\n')
    return out


def meters():
    out = jmx('get', *[x for p in METERS for x in p])
    res = {}
    for l in out.splitlines():
        parts = l.split('|')
        if len(parts) == 3:
            try:
                res[parts[0].split('name=')[-1]] = int(float(parts[2]))
            except ValueError:
                res[parts[0].split('name=')[-1]] = parts[2]
    return res


def start_node(keys):
    stop_node()
    if any_daemon():
        fail('another CassandraDaemon runs on this host: ' + any_daemon()[:200])
    sh(f'rm -rf {NTQ}/data {NTQ}/logs', check=False)
    _, y = sh(f'{HARNESS}/make-node-yaml.sh ' + ' '.join(f"'{a}'" for a in keys))
    note('yaml: ' + y.strip().splitlines()[-1][:1200])
    open(HOLD, 'w').close()
    env = dict(os.environ, CASSANDRA_CONF=NTQ + '/conf', CASSANDRA_LOG_DIR=NTQ + '/logs', MAX_HEAP_SIZE='4G')
    env.pop('HEAP_NEWSIZE', None)
    env['JVM_EXTRA_OPTS'] = (f'-javaagent:{BYTEMAN}=script:{HARNESS}/ntq-trace.btm,script:{HARNESS}/hold-request.btm,'
                             f'listener:true -Dorg.jboss.byteman.verbose=false -Dstage4.trace={TRACE} '
                             f'-Dstage4.hold.file={HOLD} -Dstage4.hold.ms=500')
    sh(f'bin/cassandra -p {NTQ}/cassandra.pid > {LOGS}/stdout.txt 2>&1', env=env)
    time.sleep(5)
    if pid_of() is None:
        fail(f'node did not start; see {LOGS}/stdout.txt')
    t0 = time.time()
    while time.time() - t0 < 300:
        if pid_of() is None:
            fail('node died during start-up')
        _, st = sh(f'bin/nodetool -p {JMX} status', check=False, quiet=True)
        _, sb = sh(f'bin/nodetool -p {JMX} statusbinary', check=False, quiet=True)
        if re.search(r'^UN\s+127\.0\.0\.1\s', st, re.M) and re.search(r'^running\s*$', sb, re.M):
            log(f'node UN and native transport running after {time.time() - t0:.0f} s')
            break
        time.sleep(2)
    else:
        fail('node not UN / native transport not running in 300 s')
    _, lst = sh(f'java -cp {BM_SUBMIT} org.jboss.byteman.agent.submit.Submit -l', check=False)
    rules = sorted({m.strip() for m in re.findall(r'^RULE (.+)$', lst, re.M)})
    open(LOGS + '/submit-l.txt', 'w').write(lst)
    if not expect(f'Submit -l lists the 9 rules of ntq-trace.btm and hold-request.btm ({len(rules)}: {rules})', len(rules) == 9):
        fail('Byteman rules not loaded')
    jvm = open(f'/proc/{pid_of()}/cmdline').read().replace('\0', ' ')
    note('jvm: ' + ' '.join(t for t in jvm.split() if t.startswith(('-Xm', '-javaagent', '-Dstage4', '-XX:+Use'))))
    rc, out = sh(f'bin/cqlsh 127.0.0.1 9042 -e "CREATE KEYSPACE ks WITH replication = '
                 "{'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE ks.t (pk int PRIMARY KEY, v blob);\"",
                 check=False, timeout=120)
    if rc != 0:
        fail('schema: ' + out[-400:])
    note('schema: ks (RF 1), ks.t (pk int PRIMARY KEY, v blob)')


# ---------------------------------------------------------------- the trace

NEW_RX = re.compile(r'^new id=(\S+) throw=(\S+) cap=(\d+) srv=(\S+) remote=/?(\S+) ms=(\d+)$')
ACQ_RX = re.compile(r'^acq id=(\S+) b=(\d+) out=(\S+) q=(-?\d+) cap=(\d+) ep=(-?\d+)/(\d+) gl=(-?\d+)/(\d+) ms=(\d+)$')
REL_RX = re.compile(r'^rel id=(\S+) b=(\d+) q=(-?\d+) ms=(\d+)$')
DEC_RX = re.compile(r'^dec id=(\S+) b=(\d+) bp=(\S+) ms=(\d+)$')
RLS_RX = re.compile(r'^rls id=(\S+) b=(\d+) ms=(\d+)$')
DISC_RX = re.compile(r'^disc id=(\S+) b=(\d+) ov=(\S+) ms=(\d+)$')
LDISC_RX = re.compile(r'^ldisc id=(\S+) b=(\d+) ms=(\d+)$')
WAKE_RX = re.compile(r'^wake id=(\S+) ns=(-?\d+) ms=(\d+)$')
HOLD_RX = re.compile(r'^hold ms=(\d+)$')


class Trace:
    """reads the node's trace file incrementally; events keep the file order"""
    def __init__(self, path):
        self.path, self.pos, self.buf = path, 0, ''
        self.handlers = {}          # id -> dict(throw, cap, remote, ms)
        self.ev = []                # (kind, id, b, extra, q, ms, gl_using, gl_limit) in file order
        self.holds = 0
        self.other = []

    def poll(self):
        if not os.path.exists(self.path):
            return
        with open(self.path, errors='replace') as f:
            f.seek(self.pos)
            data = f.read()
            self.pos = f.tell()
        lines = (self.buf + data).split('\n')
        self.buf = lines.pop()
        for l in lines:
            m = ACQ_RX.match(l)
            if m:
                g = m.groups()
                self.ev.append(('acq', g[0], int(g[1]), g[2], int(g[3]), int(g[9]), int(g[7]), int(g[8])))
                continue
            m = REL_RX.match(l)
            if m:
                self.ev.append(('rel', m.group(1), int(m.group(2)), None, int(m.group(3)), int(m.group(4)), None, None))
                continue
            m = DEC_RX.match(l)
            if m:
                self.ev.append(('dec', m.group(1), int(m.group(2)), m.group(3), None, int(m.group(4)), None, None))
                continue
            m = RLS_RX.match(l)
            if m:
                self.ev.append(('rls', m.group(1), int(m.group(2)), None, None, int(m.group(3)), None, None))
                continue
            m = DISC_RX.match(l)
            if m:
                self.ev.append(('disc', m.group(1), int(m.group(2)), m.group(3), None, int(m.group(4)), None, None))
                continue
            m = LDISC_RX.match(l)
            if m:
                self.ev.append(('ldisc', m.group(1), int(m.group(2)), None, None, int(m.group(3)), None, None))
                continue
            m = WAKE_RX.match(l)
            if m:
                self.ev.append(('wake', m.group(1), 0, int(m.group(2)), None, int(m.group(3)), None, None))
                continue
            m = HOLD_RX.match(l)
            if m:
                self.holds += 1
                continue
            m = NEW_RX.match(l)
            if m:
                self.handlers[m.group(1)] = dict(throw=m.group(2) == 'true', cap=int(m.group(3)), srv=m.group(4),
                                                 remote=m.group(5), ms=int(m.group(6)))
                continue
            if l.strip():
                self.other.append(l)


def analyse(tr, ids, ev, K, check_le_K):
    """per handler and summed readings over the arm's events (ids = the arm's handler ids)"""
    ph = {i: dict(succ=0, ref=0, ref_g=0, ref_e=0, dec=0, dec_bif=0, rls=0, disc=0, ldisc=0, wake=0, q=0, qmin=0, d=0,
                  dmax=0, last_q=None) for i in ids}
    sumA = sumD = 0
    peakA = peakD = 0
    peakA_ms = peakD_ms = None
    viol_K = viol_DA = 0
    glmax = 0
    series = []                 # (ms, sumA, sumD) after every event
    M = None
    for kind, i, b, extra, q, ms, glu, gll in ev:
        if i not in ph:
            continue
        h = ph[i]
        if kind == 'acq':
            if extra == 'SUCCESS':
                h['succ'] += 1
            else:
                h['ref'] += 1
                h['ref_g' if extra == 'INSUFFICIENT_GLOBAL' else 'ref_e'] += 1
            sumA += q - h['q']; h['q'] = q; h['last_q'] = q
            glmax = max(glmax, glu)
        elif kind == 'rel':
            sumA += q - h['q']; h['q'] = q; h['last_q'] = q
        elif kind == 'dec':
            h['dec'] += 1
            if extra == 'BYTES_IN_FLIGHT':
                h['dec_bif'] += 1
            h['d'] += b; sumD += b
            M = M or b
        elif kind == 'rls':
            h['rls'] += 1
            h['d'] -= b; sumD -= b
        elif kind == 'disc':
            h['disc'] += 1
        elif kind == 'ldisc':
            h['ldisc'] += 1
        elif kind == 'wake':
            h['wake'] += 1
        h['qmin'] = min(h['qmin'], h['q'])
        h['dmax'] = max(h['dmax'], h['d'])
        if sumA > peakA:
            peakA, peakA_ms = sumA, ms
        if sumD > peakD:
            peakD, peakD_ms = sumD, ms
        if check_le_K and K is not None and sumA > K:
            viol_K += 1
        if check_le_K and sumD > sumA:
            viol_DA += 1
        series.append((ms, sumA, sumD))
    return dict(ph=ph, peakA=peakA, peakA_ms=peakA_ms, peakD=peakD, peakD_ms=peakD_ms, viol_K=viol_K, viol_DA=viol_DA,
                glmax=glmax, series=series, M=M, endA=sumA, endD=sumD)


def histogram(path):
    pid = pid_of()
    t0 = int(time.time() * 1000)
    sh(f'jcmd {pid} GC.class_histogram > {path}', check=False, timeout=180, quiet=True)
    t1 = int(time.time() * 1000)
    qm, bb = None, None
    try:
        txt = open(path).read()
        m = re.search(r'^\s*\d+:\s+(\d+)\s+(\d+)\s+' + re.escape(QM_CLASS) + r'\s*(\(|$)', txt, re.M)
        qm = int(m.group(1)) if m else 0
        m = re.search(r'^\s*\d+:\s+(\d+)\s+(\d+)\s+\[B\s', txt, re.M)
        bb = int(m.group(2)) if m else None
    except OSError:
        pass
    return t0, t1, qm, bb


# ---------------------------------------------------------------- one arm

def client_jvm_opts():
    """the module options a Cassandra client JVM needs on JDK 11 (conf/jvm11-clients.options; without them FileUtils
    fails to initialise and buffer frees fail, so responses are lost: shakedown 1, 2026-10-15)"""
    opts = []
    for l in open(C + '/conf/jvm11-clients.options'):
        l = l.strip()
        if l.startswith('-'):
            opts.append(l)
    return ' '.join(opts)


def flood(D, name, throw, size, window, seconds, conns):
    args = (f'--host 127.0.0.1 --port 9042 --connections {conns} --window {window} --value-bytes {size} '
            f'--seconds {seconds} --throw {"true" if throw else "false"} --retry-ms 100')
    cmd = (f'java {client_jvm_opts()} -Dio.netty.eventLoopThreads=1 -Dlogback.configurationFile={HARNESS}/flood-logback.xml -Xmx4g '
           f'-cp "{FLOOD_CP}" org.apache.cassandra.transport.NativeFlood {args}')
    log(f'+ ({name}) {cmd}')
    p = subprocess.Popen(cmd, shell=True, cwd=C, stdout=open(f'{D}/flood-{name}.out', 'w'),
                         stderr=open(f'{D}/flood-{name}.err', 'w'))
    CHILDREN.append(p)
    return p


def flood_out(path):
    res, conns, texts = {}, [], []
    for l in open(path):
        m = re.match(r'^conn \d+ local=/?(\S+) throw=', l)
        if m:
            conns.append(m.group(1))
        if l.startswith('TOTAL'):
            res = {k: int(v) for k, v in re.findall(r'(\w+)=(-?\d+)', l)}
        if l.startswith(('ovl_other_text', 'err_text')):
            texts.append(l.strip())
    return res, conns, texts


def arm(tr, cap, pinned, spec, rows):
    name, kind, throw, size, window, seconds = spec[:6]
    conns = spec[6] if len(spec) > 6 else N
    seconds = seconds * SCALE
    D = f'{LOGS}/{name}'
    os.makedirs(D, exist_ok=True)
    K = conns * cap + R if pinned else None
    note(f'==== arm {label}/{name}: kind={kind} throw={throw} value={size} N={conns} W={window} s={seconds:g} C={cap} '
         f'K={K}')
    tr.poll()
    ev0 = len(tr.ev)
    m0 = meters()
    stop = D + '/stop-poll'
    if os.path.exists(stop):
        os.remove(stop)
    pj = subprocess.Popen(['java', '-cp', NTQ + '/jmxcls', 'Jmx', str(JMX), 'poll', '2000', '100000', stop,
                           B_POOLU, 'Value', B_POOLO, 'Value', B_HEAP, 'HeapMemoryUsage', B_RSIZE, 'Value',
                           B_PAUSED, 'Value'], stdout=open(D + '/jmx-poll.csv', 'w'), stderr=subprocess.DEVNULL)
    CHILDREN.append(pj)
    t_start = int(time.time() * 1000)
    histos = []
    texts = []
    arm_conns = []
    fres = {}
    if kind == 'ctrl':
        time.sleep(seconds)
    elif kind == 'connidle':
        p1 = flood(D, 'throw', True, SMALL, 0, seconds, N)
        p2 = flood(D, 'def', False, SMALL, 0, seconds, N)
        for p in (p1, p2):
            p.wait(timeout=seconds + 300)
        for nm in ('throw', 'def'):
            r, c, t = flood_out(f'{D}/flood-{nm}.out')
            arm_conns += c; texts += t
            if len(c) != N:
                fail(f'{name}: client {nm} opened {len(c)} of {N} connections')
    else:
        p = flood(D, 'run', throw, size, window, seconds, conns)
        if kind in ('Bt', 'Bdl', 'Bds'):
            for frac in (1 / 3, 2 / 3):
                target = t_start / 1000 + seconds * frac
                while time.time() < target and p.poll() is None:
                    time.sleep(0.2)
                if p.poll() is None:
                    histos.append(histogram(f'{D}/histo-{len(histos) + 1}.txt'))
        p.wait(timeout=seconds + 400)
        fres, arm_conns, texts = flood_out(f'{D}/flood-run.out')
        if len(arm_conns) != conns:
            fail(f'{name}: client opened {len(arm_conns)} of {conns} connections (rc {p.returncode})')
        if p.returncode != 0:
            note(f'{name}: client exit {p.returncode} (outstanding {fres.get("outstanding")})')
    # drain: the global reserve in use back to 0
    rs = None
    for _ in range(30):
        rs = meters().get('RequestsSize')
        if rs == 0:
            break
        time.sleep(1)
    t_end = int(time.time() * 1000)
    open(stop, 'w').close()
    pj.wait(timeout=30)
    m1 = meters()
    time.sleep(1)
    tr.poll()
    ev = tr.ev[ev0:]
    dm = {k: (m1.get(k) - m0.get(k)) if isinstance(m1.get(k), int) and isinstance(m0.get(k), int) else None
          for k in m0}
    open(D + '/meters.txt', 'w').write(f'before {m0}\nafter {m1}\ndelta {dm}\n')
    ids = [i for i, h in tr.handlers.items() if h['remote'] in arm_conns]
    hmodes = [tr.handlers[i]['throw'] for i in ids]
    hcaps = sorted({tr.handlers[i]['cap'] for i in ids})
    a = analyse(tr, set(ids), ev, K, kind in ('Bt', 'Bdl', 'n', 'defres', 'A'))
    ph = a['ph']
    tot = {k: sum(h[k] for h in ph.values()) for k in ('succ', 'ref', 'ref_g', 'ref_e', 'dec', 'dec_bif', 'rls', 'disc',
                                                        'ldisc', 'wake')}
    M = a['M']
    with open(D + '/handlers.csv', 'w') as f:
        f.write('id,remote,throw,cap,succ,ref,ref_g,ref_e,dec,dec_bif,rls,disc,ldisc,wake,last_q,qmin,dmax\n')
        for i in ids:
            h, hh = ph[i], tr.handlers[i]
            f.write(f'{i},{hh["remote"]},{hh["throw"]},{hh["cap"]},{h["succ"]},{h["ref"]},{h["ref_g"]},{h["ref_e"]},'
                    f'{h["dec"]},{h["dec_bif"]},{h["rls"]},{h["disc"]},{h["ldisc"]},{h["wake"]},{h["last_q"]},'
                    f'{h["qmin"]},{h["dmax"]}\n')
    # per-second series (last value in each second)
    sec = {}
    for ms, sa, sd in a['series']:
        sec[ms // 1000] = (sa, sd)
    with open(D + '/series.csv', 'w') as f:
        f.write('sec,sumA,sumD\n')
        for s in sorted(sec):
            f.write(f'{s},{sec[s][0]},{sec[s][1]}\n')
    note(f'{name}: handlers {len(ids)} (throw {sum(hmodes)}, default {len(hmodes) - sum(hmodes)}) cap {hcaps}; M={M}; '
         f'acquires ok {tot["succ"]} refused {tot["ref"]} (global {tot["ref_g"]}, endpoint {tot["ref_e"]}); dec '
         f'{tot["dec"]} (bp=BYTES_IN_FLIGHT {tot["dec_bif"]}); rls {tot["rls"]}; disc {tot["disc"]}; ldisc '
         f'{tot["ldisc"]}; wake {tot["wake"]}; peak sumA {a["peakA"]} sumD {a["peakD"]}; end sumA {a["endA"]} sumD '
         f'{a["endD"]}; gl max {a["glmax"]}; client {fres}; meters delta {dm}; RequestsSize after {rs}; holds so far '
         f'{tr.holds}')
    for t in texts:
        note(f'{name}: client text: {t}')
    for k, (h0, h1, qm, bb) in enumerate(histos):
        win = [sd for ms, sa, sd in a['series'] if h0 - 1000 <= ms <= h1 + 1000]
        note(f'{name}: histogram {k + 1} {h0}-{h1} ms: QueryMessage {qm}, [B {bb} B; sumD/M over the interval ±1 s '
             f'{(min(win) / M) if win and M else None}..{(max(win) / M) if win and M else None}')

    # ---- the frozen §9a predictions for this arm
    others_ok = (fres.get('ovl_other', 0) == 0 and fres.get('err', 0) == 0 and dm.get('TimedOutBeforeProcessing') == 0
                 and dm.get('ProtocolException') == 0)
    if kind == 'connidle':
        expect(f'{name}: read-back: {2 * N} handlers, every cap = {cap} ({hcaps}), {N} throwing and {N} default',
               len(ids) == 2 * N and hcaps == [cap] and sum(hmodes) == N)
    if kind in ('ctrl', 'connidle'):
        expect(f'{name}: no refusal and no decode on the arm\'s handlers (refused {tot["ref"]}, dec {tot["dec"]}); '
               f'no refusal anywhere in the window ({sum(1 for e in ev if e[0] == "acq" and e[3] != "SUCCESS")})',
               tot['ref'] == 0 and tot['dec'] == 0 and not any(e[0] == 'acq' and e[3] != 'SUCCESS' for e in ev))
    if kind != 'ctrl' and kind != 'connidle':
        expect(f'{name}: read-back: {conns} handlers, cap {cap}, throw={throw} ({len(ids)}, {hcaps}, {set(hmodes)})',
               len(ids) == conns and hcaps == [cap] and set(hmodes) == {throw})
        expect(f'{name}: no other overload: client ovl_other {fres.get("ovl_other")}, err {fres.get("err")}, '
               f'TimedOutBeforeProcessing +{dm.get("TimedOutBeforeProcessing")}, ProtocolException '
               f'+{dm.get("ProtocolException")}', others_ok)
        expect(f'{name}: the client got every response (outstanding {fres.get("outstanding")})', fres.get('outstanding') == 0)
        expect(f'{name}: global reserve in use back to 0 after the drain (RequestsSize {rs})', rs == 0)
    final_q = {i: ph[i]['last_q'] for i in ids}
    if kind == 'A':
        bound = conns * (cap // M) * M if M else None
        expect(f'{name}: no refusal ({tot["ref"]}), no discard ({tot["disc"] + tot["ldisc"]}, RequestDiscarded '
               f'+{dm.get("RequestDiscarded")}), no warning ({fres.get("warned")})',
               tot['ref'] == 0 and tot['disc'] + tot['ldisc'] == 0 and dm.get('RequestDiscarded') == 0
               and fres.get('warned') == 0)
        expect(f'{name}: peak sumA {a["peakA"]} <= N*floor(C/M)*M = {bound}', bound is not None and a['peakA'] <= bound)
        expect(f'{name}: every handler ends at A_i = 0 ({sorted(set(final_q.values()))})', set(final_q.values()) <= {0})
    if kind in ('Bt', 'n') and not (kind == 'n' and conns == 1):
        expect(f'{name}: refusals occur ({tot["ref"]})', tot['ref'] > 0)
        expect(f'{name}: sumA <= K = {K} at every trace line (violations {a["viol_K"]}; peak {a["peakA"]})',
               a['viol_K'] == 0 and a['peakA'] <= K)
        expect(f'{name}: peak sumA {a["peakA"]} in (K - 2M, K] = ({K - 2 * M if M else None}, {K}]',
               M is not None and K - 2 * M < a['peakA'] <= K)
        expect(f'{name}: sumD <= sumA at every line (violations {a["viol_DA"]})', a['viol_DA'] == 0)
        expect(f'{name}: refusals {tot["ref"]} = RequestDiscarded delta {dm.get("RequestDiscarded")} = client ovl_bytes '
               f'{fres.get("ovl_bytes")}', tot['ref'] == dm.get('RequestDiscarded') == fres.get('ovl_bytes'))
        dk = 'disc' if size == SMALL else 'ldisc'
        expect(f'{name}: every refusal is a discard ({dk} {tot[dk]} = refusals {tot["ref"]}) and nothing refused is '
               f'decoded (dec {tot["dec"]} = successful acquires {tot["succ"]})',
               tot[dk] == tot['ref'] and tot['dec'] == tot['succ'])
        expect(f'{name}: every handler ends at A_i = 0 ({sorted(set(final_q.values()))})', set(final_q.values()) == {0})
    if kind == 'n' and conns == 1:
        expect(f'{name}: N = 1: no refusal ({tot["ref"]})', tot['ref'] == 0)
        expect(f'{name}: N = 1: peak sumA {a["peakA"]} = 32*M = {32 * M if M else None} (the window binds)',
               M is not None and a['peakA'] == 32 * M)
    if kind == 'Bdl':
        expect(f'{name}: refusals occur ({tot["ref"]})', tot['ref'] > 0)
        expect(f'{name}: no error or warning reaches the client (ovl_bytes {fres.get("ovl_bytes")}, warned '
               f'{fres.get("warned")}) and RequestDiscarded does not move (+{dm.get("RequestDiscarded")})',
               fres.get('ovl_bytes') == 0 and fres.get('warned') == 0 and dm.get('RequestDiscarded') == 0)
        bad = [i for i in ids if ph[i]['dec'] != ph[i]['succ']]
        expect(f'{name}: per handler, decodes = successful acquires (handlers that differ: {len(bad)}; dec {tot["dec"]}, '
               f'succ {tot["succ"]}, dec bp=BYTES_IN_FLIGHT {tot["dec_bif"]})', not bad and tot['dec_bif'] == 0)
        expect(f'{name}: sumA <= K = {K} at every line (violations {a["viol_K"]}; peak {a["peakA"]})',
               a['viol_K'] == 0 and a['peakA'] <= K)
        expect(f'{name}: peak sumA {a["peakA"]} in (K - 2M, K] = ({K - 2 * M if M else None}, {K}]',
               M is not None and K - 2 * M < a['peakA'] <= K)
        expect(f'{name}: sumD <= sumA at every line (violations {a["viol_DA"]})', a['viol_DA'] == 0)
        expect(f'{name}: every handler ends at A_i = 0, no drift ({sorted(set(final_q.values()))})',
               set(final_q.values()) == {0})
    if kind == 'Bds':
        expect(f'{name}: refusals occur ({tot["ref"]})', tot['ref'] > 0)
        bad = [i for i in ids if ph[i]['dec_bif'] != ph[i]['ref']]
        expect(f'{name}: every refusal is decoded with bp=BYTES_IN_FLIGHT: per handler equal (differ: {len(bad)}); '
               f'total {tot["dec_bif"]} = refusals {tot["ref"]} = client warned {fres.get("warned")}',
               not bad and tot['dec_bif'] == tot['ref'] == fres.get('warned'))
        expect(f'{name}: RequestDiscarded does not move (+{dm.get("RequestDiscarded")}), no overload error '
               f'({fres.get("ovl_bytes")})', dm.get('RequestDiscarded') == 0 and fres.get('ovl_bytes') == 0)
        badq = [(i, final_q[i], ph[i]['ref']) for i in ids if M is None or final_q[i] != -ph[i]['ref'] * M]
        expect(f'{name}: every handler ends at A_i = -k_i*M (the drift; handlers that differ: {badq[:3]}; '
               f'sum k_i {tot["ref"]}, sum A_i {sum(v or 0 for v in final_q.values())})', not badq)
        expect(f'{name}: peak sumD {a["peakD"]} > K = {K}', a['peakD'] > K)
        ser = [sd for ms, sa, sd in a['series']]
        if ser:
            ts = [ms for ms, sa, sd in a['series']]
            t_lo, t_hi = t_start + seconds * 1000 / 3, t_start + seconds * 2000 / 3
            first = [sd for ms, sa, sd in a['series'] if t_start <= ms < t_lo]
            last = [sd for ms, sa, sd in a['series'] if t_hi <= ms <= t_start + seconds * 1000]
            mf = sum(first) / len(first) if first else None
            ml = sum(last) / len(last) if last else None
            expect(f'{name}: mean sumD over the last third {ml} > over the first third {mf}',
                   mf is not None and ml is not None and ml > mf)
    if kind == 'defres':
        expect(f'{name}: no refusal ({tot["ref"]}), no discard (+{dm.get("RequestDiscarded")}, ovl_bytes '
               f'{fres.get("ovl_bytes")})', tot['ref'] == 0 and dm.get('RequestDiscarded') == 0
               and fres.get('ovl_bytes') == 0)
        expect(f'{name}: peak sumA {a["peakA"]} = the window N*W*M = {conns * window * M if M else None}',
               M is not None and a['peakA'] == conns * window * M)
    for k, (h0, h1, qm, bb) in enumerate(histos):
        win = [sd for ms, sa, sd in a['series'] if h0 - 1000 <= ms <= h1 + 1000]
        lo = min(win) / M if win and M else None
        hi = max(win) / M if win and M else None
        expect(f'{name}: histogram {k + 1}: live QueryMessage {qm} within sumD/M over its interval ±1 s [{lo}, {hi}]',
               lo is not None and qm is not None and lo <= qm <= hi)
        if kind == 'Bds' and k == 1 and cap <= MIB:
            expect(f'{name}: histogram 2: live QueryMessage {qm} > K/M = {K / M if M else None}',
                   M is not None and qm is not None and qm > K / M)
    rows.append(dict(arm=name, kind=kind, throw=throw, value=size, N=conns, W=window, s=seconds, C=cap, K=K, M=M,
                     handlers=len(ids), succ=tot['succ'], ref=tot['ref'], ref_g=tot['ref_g'], ref_e=tot['ref_e'],
                     dec=tot['dec'], dec_bif=tot['dec_bif'], rls=tot['rls'], disc=tot['disc'], ldisc=tot['ldisc'],
                     wake=tot['wake'], peakA=a['peakA'], peakD=a['peakD'], endA=a['endA'], glmax=a['glmax'],
                     c_ok=fres.get('ok'), c_warned=fres.get('warned'), c_ovl=fres.get('ovl_bytes'),
                     c_ovl_other=fres.get('ovl_other'), c_err=fres.get('err'), d_discarded=dm.get('RequestDiscarded'),
                     d_tobp=dm.get('TimedOutBeforeProcessing'), d_proto=dm.get('ProtocolException'),
                     d_cpause=dm.get('ConnectionPaused'), rs_after=rs,
                     histos=';'.join(f'{qm}/{bb}' for h0, h1, qm, bb in histos), t_start=t_start, t_end=t_end))


# ---------------------------------------------------------------- main

def main():
    if label == 'down':
        stop_node()
        note('down: node stopped')
        return
    keys, cap, pinned, arms = LABELS[label]
    md5 = subprocess.run(f'cd {HARNESS} && md5sum *', shell=True, capture_output=True, text=True).stdout
    note(f'cluster-run {label} {time.strftime("%F %T %Z")} run={RUN} scale={SCALE} arms={ONLY_ARMS or "all"}')
    note('harness md5: ' + ' '.join(f'{l.split()[1]}={l.split()[0][:12]}' for l in md5.splitlines()))
    if os.path.exists(TRACE):
        os.rename(TRACE, TRACE + f'.{int(time.time())}')
    compile_tools()
    start_node(keys)
    tr = Trace(TRACE)
    rows = []
    try:
        for spec in arms:
            if ONLY_ARMS and spec[0] not in ONLY_ARMS:
                continue
            if pid_of() is None:
                fail('node died')
            arm(tr, cap, pinned, spec, rows)
    finally:
        if rows:
            keys_ = list(rows[0].keys())
            with open(LOGS + '/arms.csv', 'w') as f:
                f.write(','.join(keys_) + '\n')
                for r in rows:
                    f.write(','.join(str(r[k]).replace(',', ';') for k in keys_) + '\n')
        tr.poll()
        if tr.other:
            note(f'unparsed trace lines: {len(tr.other)}; first: {tr.other[:3]}')
        _, cnt = sh(f"grep -c 'requests/second\\|spent over\\|timed out before it could start' {NTQ}/logs/system.log",
                    check=False)
        expect(f'system.log: no line with another overload text (requests/second, spent over, timed out before it could '
               f'start): {cnt.strip()}', cnt.strip() == '0')
        _, g = sh(f"grep -h 'requests/second\\|spent over\\|timed out before it could start\\|bytes in flight' "
                  f"{NTQ}/logs/system.log | head -5", check=False)
        note('system.log overload lines (first 5): ' + (g.strip().replace('\n', ' || ')[:1500] or 'none'))
        _, e = sh(f"grep -c '^ERROR' {NTQ}/logs/system.log", check=False)
        note(f'system.log ERROR lines: {e.strip()}')
        sh(f'cp {NTQ}/logs/system.log {LOGS}/system.log', check=False)
        sh(f'cp {NTQ}/conf/cassandra.yaml {LOGS}/cassandra.yaml', check=False)
        stop_node()
        note(f'node stopped; {EXPECT}')


if __name__ == '__main__':
    main()
