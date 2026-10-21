#!/usr/bin/env python3
"""Stage 4, cluster tier, native_transport_max_concurrent_connections-channelActive-limit--guided (case 9b-9e, 9f R1-R2;
frozen §9 hash 52393486…). Written 2026-10-20 before any reading.

usage: cluster-run.py <run-name> <label> [<label> ...]      labels: idle, C0-1g, C0-16m, C-1g, C-16m, or all
output: ~/stage4-logs/ncc/<run-name>/cluster/<label>/  (summary.txt, session.log, arms.csv, phases.csv, ncc.trace,
        client-*.txt, histo-*.txt, heap-*.txt, status-*.txt, system.log, poll-*.csv)

One node on 127.0.0.1 from ~/cassandra-run1 (conf and data under ~/stage4-ncc, local disk), -Xms2G -Xmx2G, Byteman
ncc.btm (6 rules) with stage4.Hold on the boot class path. Every lifetime holds 9b's settings fixed:
native_transport_idle_timeout 0ms, both connection limits -1 in the yaml, and native_transport_timeout /
read_request_timeout 120s (a control request is held about 25 s, beyond the 12 s default).

  idle    9e control, A, B: the limit set live over JMX (StorageProxy NativeTransportMaxConcurrentConnections, read
          back) before each burst; hold_connections.py opens 4,000 idle sockets from 127.0.0.1 and holds them; sampled
          at 30 s of the hold. Arms in order: warm (-1, not a reading), m1a (-1), L2000, m1b (-1), L1000, m1c (-1),
          L500. Three -1 arms give R1's noise band; interleaving spreads drift over the band.
  C0-1g / C0-16m   9e C exactly as frozen in 9f R2: 64 connections x one 1 MiB request held, in-flight limits (global and
          per-IP) 1 GiB / 16 MiB, native_transport_receive_queue_capacity at its default (1 MiB per connection).
          Source reading before run 1 (results §3, defect 1): the per-connection queue capacity takes each 1 MiB
          request, so neither arm's reserve binds; recorded as the as-filed arms, not as the positive control.
  C-1g / C-16m     the same with native_transport_receive_queue_capacity 0B, so every request byte is drawn from the
          in-flight reserves the 16 MiB arm caps: the positive control as R2 intends it (defect 1's fix).

Per sample: ss count of established server sockets on :9042, jcmd GC.class_histogram (a full GC; the "Total" bytes is
the live heap), GC.heap_info, /proc/<pid>/status (RssAnon, VmRSS), /proc/<pid>/fd count, JMX (connectedNativeClients,
RequestsSize, direct MemoryUsed, networking pool UsedSize/OverflowSize). The node is stopped on any exit; exit 1 means a
set-up or instrument check failed. Mismatches against a prediction are recorded as EXPECTED ... NO and the run goes on."""
import csv, os, re, statistics, subprocess, sys, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-run1')
HARNESS = os.path.dirname(os.path.abspath(__file__))
NCC = HOME + '/stage4-ncc'
RUN = sys.argv[1] if len(sys.argv) > 1 else 'run1'
LABELS = sys.argv[2:] or ['all']
if LABELS == ['all']:
    LABELS = ['idle', 'C0-1g', 'C0-16m', 'C-1g', 'C-16m']
ROOT = f'{HOME}/stage4-logs/ncc/{RUN}/cluster'
BYTEMAN = C + '/build/lib/jars/byteman-4.0.20.jar'
BM_SUBMIT = C + '/build/lib/jars/byteman-submit-4.0.20.jar'
JMX = 7199
SP = 'org.apache.cassandra.db:type=StorageProxy'
CLIENT = 'org.apache.cassandra.metrics:type=Client,name='
POOL = 'org.apache.cassandra.metrics:type=BufferPool,scope=networking,name='
DIRECT = 'java.nio:type=BufferPool,name=direct'
COUNT = int(os.environ.get('NCC_COUNT', '4000'))
HOLD_S = float(os.environ.get('NCC_HOLD_S', '30'))
# shakedowns only: smaller counts and limits (NCC_COUNT, NCC_HOLD_S, NCC_LIMITS=high,mid,low); run 1 uses the defaults
LIMITS = [int(x) for x in os.environ.get('NCC_LIMITS', '2000,1000,500').split(',')]
NCONN, VBYTES = 64, 1 << 20
MiB, GiB = 1 << 20, 1 << 30
FIXED = ['native_transport_idle_timeout=0ms', 'native_transport_max_concurrent_connections=-1',
         'native_transport_max_concurrent_connections_per_ip=-1', 'native_transport_timeout=120s',
         'read_request_timeout=120s']
CONTROL = {'C0-1g': ['native_transport_max_request_data_in_flight=1GiB', 'native_transport_max_request_data_in_flight_per_ip=1GiB'],
           'C0-16m': ['native_transport_max_request_data_in_flight=16MiB', 'native_transport_max_request_data_in_flight_per_ip=16MiB'],
           'C-1g': ['native_transport_max_request_data_in_flight=1GiB', 'native_transport_max_request_data_in_flight_per_ip=1GiB',
                    'native_transport_receive_queue_capacity=0B'],
           'C-16m': ['native_transport_max_request_data_in_flight=16MiB', 'native_transport_max_request_data_in_flight_per_ip=16MiB',
                     'native_transport_receive_queue_capacity=0B']}
HISTO_CLASSES = ['io.netty.channel.epoll.EpollSocketChannel', 'io.netty.channel.socket.nio.NioSocketChannel',
                 'io.netty.channel.DefaultChannelPipeline', 'io.netty.channel.DefaultChannelHandlerContext',
                 'org.apache.cassandra.transport.InitialConnectionHandler',
                 'org.apache.cassandra.transport.messages.QueryMessage', 'org.apache.cassandra.transport.CQLMessageHandler']
CLS = ROOT + '/classes'

D = SESSION = SUMMARY = TRACE = HOLDF = None
ARMS = PHASES = None


def open_label(label):
    global D, SESSION, SUMMARY, TRACE, HOLDF, ARMS, PHASES
    D = f'{ROOT}/{label}'
    os.makedirs(D, exist_ok=True)
    SESSION = open(D + '/session.log', 'a')
    SUMMARY = open(D + '/summary.txt', 'w')
    TRACE = D + '/ncc.trace'
    HOLDF = D + '/hold'
    ARMS = csv.writer(open(D + '/arms.csv', 'w'))
    ARMS.writerow(['label', 'arm', 'limit', 'tag', 'ms', 'ss_established', 'histo_total_bytes', 'heapinfo_used', 'rss_anon',
                   'vm_rss', 'fd', 'connectedNativeClients', 'RequestsSize', 'direct_used', 'pool_used', 'pool_overflow']
                  + [c.split('.')[-1] for c in HISTO_CLASSES])
    PHASES = open(D + '/phases.csv', 'w')
    PHASES.write('ms,label,arm,phase\n')


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, file=sys.stderr)
    SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush(); SESSION.write(s + '\n'); SESSION.flush()


def phase(label, arm, p):
    PHASES.write(f'{int(time.time() * 1000)},{label},{arm},{p}\n'); PHASES.flush()


def sh(cmd, timeout=300, check=True, env=None, quiet=False):
    if not quiet:
        log('+ ' + cmd)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env, cwd=C)
    out = (r.stdout or '') + (r.stderr or '')
    if not quiet:
        SESSION.write(out[-4000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed rc={r.returncode}: {cmd}\n{out[-800:]}')
    return r.returncode, out


def java_daemons():
    """java processes running CassandraDaemon only (a plain grep of ps also matches a shell holding the word: the
    batch_size_fail_threshold harness's defect of 2026-10-20)"""
    r = subprocess.run(['ps', '-eo', 'pid,comm,args'], capture_output=True, text=True)
    out = []
    for l in r.stdout.splitlines()[1:]:
        p = l.split(None, 2)
        if len(p) == 3 and p[1] == 'java' and 'org.apache.cassandra.service.CassandraDaemon' in p[2]:
            out.append(p[0] + ' ' + p[2])
    return out


def pid_of():
    lines = [l for l in java_daemons() if NCC in l]
    return int(lines[0].split()[0]) if lines else None


def stop_node():
    p = pid_of()
    if p:
        sh(f'bin/nodetool -p {JMX} stopdaemon', check=False, timeout=120)
        for _ in range(60):
            if pid_of() is None:
                break
            time.sleep(1)
        if pid_of():
            sh(f'kill -9 {pid_of()}', check=False)
            time.sleep(2)
    if java_daemons():
        log('WARNING: a CassandraDaemon is still running: ' + java_daemons()[0][:200])


def fail(msg):
    note('FAIL: ' + msg)
    try:
        if HOLDF and os.path.exists(HOLDF):
            os.remove(HOLDF)
    except OSError:
        pass
    stop_node()
    sys.exit(1)


def expect(desc, cond):
    note(f'EXPECTED: {desc} — {"yes" if cond else "NO (recorded; the AI judges it in the results file)"}')
    return cond


def client_jvm_opts():
    return ' '.join(l.strip() for l in open(C + '/conf/jvm11-clients.options') if l.strip().startswith('-'))


def jmx(*args, timeout=60):
    _, out = sh(f'java -cp {CLS} Jmx {JMX} ' + ' '.join(f"'{a}'" for a in args), check=False, timeout=timeout, quiet=True)
    SESSION.write('jmx ' + ' '.join(args) + ' -> ' + out[-600:] + '\n')
    return out


def jmx_values(pairs):
    args = []
    for b, a in pairs:
        args += [b, a]
    vals = {}
    for l in jmx('get', *args).splitlines():
        p = l.split('|')
        if len(p) == 3:
            try:
                vals[(p[0], p[1])] = int(float(p[2]))
            except ValueError:
                vals[(p[0], p[1])] = None
    return [vals.get(pr) for pr in pairs]


def trace_lines():
    return open(TRACE).read().splitlines() if os.path.exists(TRACE) else []


def count_kind(lines, kind):
    return sum(1 for l in lines if l.startswith(kind + ' '))


def start_node(label, keys):
    stop_node()
    if java_daemons():
        fail('another CassandraDaemon runs on this host: ' + java_daemons()[0][:200])
    sh(f'rm -rf {NCC}/data {NCC}/logs', check=False)
    _, y = sh(f'{HARNESS}/make-node-yaml.sh ' + ' '.join(f"'{a}'" for a in keys))
    note(f'[{label}] yaml: ' + y.strip().splitlines()[-1][:1500])
    if os.path.exists(TRACE):
        os.rename(TRACE, f'{TRACE}.{int(time.time())}')
    env = dict(os.environ, CASSANDRA_CONF=NCC + '/conf', CASSANDRA_LOG_DIR=NCC + '/logs', MAX_HEAP_SIZE='2G')
    env.pop('HEAP_NEWSIZE', None)
    env['JVM_EXTRA_OPTS'] = (f'-javaagent:{BYTEMAN}=script:{HARNESS}/ncc.btm,listener:true '
                             f'-Xbootclasspath/a:{ROOT}/stage4-hold.jar -Dorg.jboss.byteman.verbose=false '
                             f'-Dstage4.trace={TRACE} -Dstage4.hold.file={HOLDF}')
    sh(f'bin/cassandra -p {NCC}/cassandra.pid > {D}/stdout.txt 2>&1', env=env)
    time.sleep(5)
    if pid_of() is None:
        fail(f'node did not start; see {D}/stdout.txt')
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
    open(f'{D}/submit-l.txt', 'w').write(lst)
    rules = sorted({m.strip() for m in re.findall(r'^RULE (.+)$', lst, re.M)})
    if not expect(f'[{label}] Submit -l lists the 6 rules of ncc.btm ({len(rules)}: {rules})', len(rules) == 6):
        fail('Byteman rules not loaded')
    pid = pid_of()
    jvm = open(f'/proc/{pid}/cmdline').read().replace('\0', ' ')
    flags = [t for t in jvm.split() if t.startswith(('-Xm', '-javaagent', '-Dstage4', '-Xbootclasspath', '-XX:+Use', '-XX:+AlwaysPreTouch'))]
    note(f'[{label}] jvm: ' + ' '.join(flags))
    if not expect(f'[{label}] heap -Xms2G -Xmx2G (9b hold fixed)', '-Xms2G' in jvm.split() and '-Xmx2G' in jvm.split()):
        fail('heap is not 2G')
    lim = [l for l in open(f'/proc/{pid}/limits') if l.startswith('Max open files')]
    nofile = int(lim[0].split()[3]) if lim else 0
    if not expect(f'[{label}] node open-file limit {nofile} >= 10,000 (9b hold fixed)', nofile >= 10000):
        fail('open-file limit too low')
    import resource
    cl = resource.getrlimit(resource.RLIMIT_NOFILE)[0]
    if not expect(f'[{label}] client open-file limit {cl} >= 10,000 (9b hold fixed)', cl >= 10000):
        fail('client open-file limit too low')
    _, y = sh(f'grep -E "^(native_transport_[a-z_]*|read_request_timeout):" {NCC}/conf/cassandra.yaml')
    note(f'[{label}] yaml keys: ' + '; '.join(y.split('\n')).strip('; '))
    g, pi = jmx_values([(SP, 'NativeTransportMaxConcurrentConnections'), (SP, 'NativeTransportMaxConcurrentConnectionsPerIp')])
    if not expect(f'[{label}] JMX global limit {g}, per-IP limit {pi} (both -1 at start)', g == -1 and pi == -1):
        fail('limits not -1 at start')
    return pid


def histo(pid, path):
    _, out = sh(f'jcmd {pid} GC.class_histogram', check=False, quiet=True, timeout=180)
    open(path, 'w').write(out)
    counts = {}
    total = None
    for l in out.splitlines():
        m = re.match(r'^\s*\d+:\s+(\d+)\s+(\d+)\s+(\S+)', l)
        if m and m.group(3) in HISTO_CLASSES:
            counts[m.group(3)] = int(m.group(1))
        m = re.match(r'^Total\s+(\d+)\s+(\d+)', l)
        if m:
            total = int(m.group(2))
    return total, [counts.get(c, 0) for c in HISTO_CLASSES]


def ss_count():
    _, out = sh("ss -Htn state established '( sport = :9042 )'", check=False, quiet=True)
    return len([l for l in out.splitlines() if l.strip()])


def sample(label, arm, limit, tag):
    pid = pid_of()
    if pid is None:
        fail('node is gone')
    ms = int(time.time() * 1000)
    ssn = ss_count()
    total, cls = histo(pid, f'{D}/histo-{arm}-{tag}.txt')
    _, hi = sh(f'jcmd {pid} GC.heap_info', check=False, quiet=True)
    m = re.search(r'total (\d+)K, used (\d+)K', hi)
    used = int(m.group(2)) * 1024 if m else None
    st = open(f'/proc/{pid}/status').read()
    open(f'{D}/status-{arm}-{tag}.txt', 'w').write(st + '\n---- GC.heap_info\n' + hi)
    rss_anon = int(re.search(r'^RssAnon:\s+(\d+) kB', st, re.M).group(1)) * 1024
    vm_rss = int(re.search(r'^VmRSS:\s+(\d+) kB', st, re.M).group(1)) * 1024
    fd = len(os.listdir(f'/proc/{pid}/fd'))
    cnc, rs, du, pu, po = jmx_values([(CLIENT + 'connectedNativeClients', 'Value'), (CLIENT + 'RequestsSize', 'Value'),
                                      (DIRECT, 'MemoryUsed'), (POOL + 'UsedSize', 'Value'), (POOL + 'OverflowSize', 'Value')])
    row = [label, arm, limit, tag, ms, ssn, total, used, rss_anon, vm_rss, fd, cnc, rs, du, pu, po] + cls
    ARMS.writerow(row)
    note(f'SAMPLE [{label}] {arm} {tag}: ss {ssn}; histo total {total}; heap_info used {used}; RssAnon {rss_anon}; fd {fd}; '
         f'connectedNativeClients {cnc}; RequestsSize {rs}; direct {du}; pool used {pu} overflow {po}; '
         + ' '.join(f'{c.split(".")[-1]}={n}' for c, n in zip(HISTO_CLASSES, cls)))
    return dict(ss=ssn, total=total, used=used, rss=rss_anon, fd=fd, cnc=cnc, rs=rs, du=du, pu=pu, po=po,
                epoll=cls[0], nio=cls[1], pipeline=cls[2], qm=cls[5], cqlh=cls[6])


def system_log_count(pattern):
    p = f'{NCC}/logs/system.log'
    if not os.path.exists(p):
        return 0
    return sum(1 for l in open(p, errors='replace') if pattern in l)


def set_limit(limit):
    out = jmx('setlong', SP, 'NativeTransportMaxConcurrentConnections', str(limit))
    back, = jmx_values([(SP, 'NativeTransportMaxConcurrentConnections')])
    if not expect(f'limit set live to {limit}, read back {back}', back == limit):
        fail('limit did not take: ' + out[-300:])


def idle_arm(label, arm, limit):
    set_limit(limit)
    time.sleep(3)
    phase(label, arm, 'base')
    base = sample(label, arm, limit, 'base')
    n0 = len(trace_lines())
    e0 = system_log_count('Exceeded maximum native connection limit of')
    stop = f'{D}/stop-{arm}'
    if os.path.exists(stop):
        os.remove(stop)
    cf = open(f'{D}/client-{arm}.txt', 'w')
    phase(label, arm, 'burst')
    cl = subprocess.Popen([sys.executable, f'{HARNESS}/hold_connections.py', '--count', str(COUNT), '--hold-s', str(HOLD_S),
                           '--stop-file', stop], stdout=cf, stderr=subprocess.STDOUT)
    t0 = time.time()
    held = None
    while time.time() - t0 < HOLD_S + 120:
        txt = open(f'{D}/client-{arm}.txt').read()
        m = re.search(r'^HELD open=(\d+) closed_by_server=(\d+) errors=(\d+)', txt, re.M)
        if m:
            held = tuple(int(x) for x in m.groups())
            break
        if cl.poll() is not None:
            break
        time.sleep(0.5)
    if held is None:
        open(stop, 'w').close()
        fail(f'{arm}: the client printed no HELD line; see client-{arm}.txt')
    phase(label, arm, 'held')
    h = sample(label, arm, limit, 'held')
    open(stop, 'w').close()
    cl.wait(timeout=120)
    cf.close()
    phase(label, arm, 'closed')
    txt = open(f'{D}/client-{arm}.txt').read()
    fin = re.search(r'^FINAL open=(\d+) closed_by_server=(\d+) errors=(\d+)', txt, re.M)
    t1 = time.time()
    while time.time() - t1 < 60 and ss_count() > 0:
        time.sleep(0.5)
    time.sleep(2)
    lines = trace_lines()[n0:]
    acc, rej, ina = count_kind(lines, 'acc'), count_kind(lines, 'rej'), count_kind(lines, 'ina')
    last_ina = [l for l in lines if l.startswith('ina ')]
    counter_end = int(re.search(r'n=(-?\d+)', last_ina[-1]).group(1)) if last_ina else None
    e1 = system_log_count('Exceeded maximum native connection limit of')
    ss_after = ss_count()
    want = COUNT if limit < 0 else min(COUNT, limit)
    note(f'ARM [{label}] {arm}: limit {limit}; client HELD open {held[0]} closed_by_server {held[1]} errors {held[2]}; '
         f'FINAL {fin.groups() if fin else None}; ss held {h["ss"]}, after close {ss_after}; trace acc {acc} rej {rej} ina {ina} '
         f'counter at the end {counter_end}; "Exceeded maximum native connection limit" lines +{e1 - e0}; '
         f'EpollSocketChannel {base["epoll"]} -> {h["epoll"]}; histo total {base["total"]} -> {h["total"]}; '
         f'RssAnon {base["rss"]} -> {h["rss"]}; fd {base["fd"]} -> {h["fd"]}')
    if arm != 'warm':
        expect(f'{arm}: client connect errors 0 ({held[2]})', held[2] == 0)
        expect(f'{arm}: open connections at {HOLD_S:.0f} s = min(4000, limit) = {want} (client {held[0]}, ss {h["ss"]})',
               held[0] == want and h['ss'] == want)
        expect(f'{arm}: closed by the server = {COUNT - want} (client {held[1]})', held[1] == COUNT - want)
        if limit > 0:
            expect(f'{arm}: trace acc = {want}, rej = {COUNT - want} ({acc}, {rej})', acc == want and rej == COUNT - want)
            expect(f'{arm}: at least one "Exceeded maximum native connection limit of {limit}" line ({e1 - e0}; NoSpamLogger 1/min)',
                   e1 - e0 >= 1)
            expect(f'{arm}: the handler counter back to 0 after the close ({counter_end})', counter_end == 0)
        else:
            expect(f'{arm}: no handler installed at -1: no acc/rej/ina line ({acc}, {rej}, {ina})', acc == rej == ina == 0)
        expect(f'{arm}: live EpollSocketChannel objects held - base = {want} ({h["epoll"] - base["epoll"]})',
               h['epoll'] - base['epoll'] == want)
        expect(f'{arm}: every socket closed afterwards (ss {ss_after})', ss_after == 0)
    return dict(limit=limit, base=base, held=h, client=held)


def band_analysis(res):
    note('---- R1 analysis (held readings; band = range over the three -1 arms) ----')
    obs = [('epoll', 'live EpollSocketChannel'), ('pipeline', 'live DefaultChannelPipeline'), ('total', 'live heap (histogram Total, after full GC)'),
           ('used', 'heap used after GC (GC.heap_info)'), ('rss', 'RssAnon'), ('fd', 'process file descriptors')]
    for key, name in obs:
        m1 = [res[a]['held'][key] for a in ('m1a', 'm1b', 'm1c')]
        band = max(m1) - min(m1)
        hi, mid, lo = LIMITS
        r = {L: res[f'L{L}']['held'][key] for L in LIMITS}
        spread = max(r.values()) - min(r.values())
        s1 = (r[mid] - r[lo]) / (mid - lo)
        s2 = (r[hi] - r[mid]) / (hi - mid)
        flat = spread <= band
        consistent = s1 > 0 and s2 > 0 and max(s1, s2) / min(s1, s2) <= 1.5
        follows = (r[hi] - r[lo]) > 2 * band and consistent
        slope = (r[hi] - r[lo]) / (hi - lo)
        verdict = 'follows the limit' if follows else ('flat' if flat else 'neither')
        note(f'R1 {name}: -1 arms {m1} (band {band}); L{lo} {r[lo]} L{mid} {r[mid]} L{hi} {r[hi]} (spread {spread}); '
             f'slope {lo}->{hi} {slope:.1f} per connection, segments {s1:.1f} / {s2:.1f}; -1 mean {statistics.mean(m1):.0f}; '
             f'line at {COUNT} {r[lo] + slope * (COUNT - lo):.0f} -> {verdict}')
    note('(R1 operationalized in this harness before any reading: "flat" = spread of the three limit readings <= band; '
         '"follows" = L(high) - L(low) > 2 x band and both segment slopes > 0 within a factor 1.5 of each other.)')


def run_idle():
    label = 'idle'
    open_label(label)
    note(f'cluster-run {RUN} {label} {time.strftime("%F %T %Z")} host {os.uname().nodename} count {COUNT} hold {HOLD_S} s limits {LIMITS}')
    note('harness md5 ' + MD5)
    start_node(label, FIXED)
    res = {}
    hi, mid, lo = LIMITS
    for arm, limit in [('warm', -1), ('m1a', -1), (f'L{hi}', hi), ('m1b', -1), (f'L{mid}', mid), ('m1c', -1), (f'L{lo}', lo)]:
        res[arm] = idle_arm(label, arm, limit)
    set_limit(-1)
    band_analysis(res)
    sh(f'cp {NCC}/logs/system.log {D}/system.log', check=False)
    stop_node()


def run_control(label):
    open_label(label)
    note(f'cluster-run {RUN} {label} {time.strftime("%F %T %Z")} host {os.uname().nodename}')
    note('harness md5 ' + MD5)
    start_node(label, FIXED + CONTROL[label])
    rc, out = sh('bin/cqlsh 127.0.0.1 9042 -e "CREATE KEYSPACE ks WITH replication = '
                 "{'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE ks.t (pk int PRIMARY KEY, v blob);\"",
                 check=False, timeout=120)
    if rc != 0:
        fail('schema: ' + out[-400:])
    g, = jmx_values([(CLIENT + 'RequestsSize', 'Value')])
    time.sleep(3)
    phase(label, 'C', 'base')
    base = sample(label, 'C', -1, 'base')
    n0 = len(trace_lines())
    open(HOLDF, 'w').close()
    stop = f'{D}/poll.stop'
    pf = open(f'{D}/poll-C.csv', 'w')
    poll = subprocess.Popen(['java', '-cp', CLS, 'Jmx', str(JMX), 'poll', '500', '100000', stop, CLIENT + 'RequestsSize', 'Value',
                             'java.lang:type=Memory', 'HeapMemoryUsage', DIRECT, 'MemoryUsed', POOL + 'UsedSize', 'Value'],
                            stdout=pf, stderr=subprocess.STDOUT)
    cf = open(f'{D}/client-C.txt', 'w')
    phase(label, 'C', 'send')
    cmd = (f'java {client_jvm_opts()} -Dlogback.configurationFile={HARNESS}/client-logback.xml -Xmx2g '
           f'-cp "{CLS}:{C}/build/classes/main:{C}/build/lib/jars/*:{C}/lib/*" org.apache.cassandra.transport.HeldRequests '
           f'--host 127.0.0.1 --port 9042 --connections {NCONN} --value-bytes {VBYTES} --wait-s 180')
    log('+ ' + cmd)
    cl = subprocess.Popen(cmd, shell=True, cwd=C, stdout=cf, stderr=subprocess.STDOUT)
    t0 = time.time()
    while time.time() - t0 < 60 and not re.search(r'^sent n=', open(f'{D}/client-C.txt').read(), re.M):
        if cl.poll() is not None:
            break
        time.sleep(0.5)
    if not re.search(r'^sent n=', open(f'{D}/client-C.txt').read(), re.M):
        os.remove(HOLDF)
        fail('control client did not send; see client-C.txt')
    time.sleep(20)
    phase(label, 'C', 'held')
    lines = trace_lines()[n0:]
    hin_held = count_kind(lines, 'hin')
    hout_held = count_kind(lines, 'hout')
    h = sample(label, 'C', -1, 'held')
    os.remove(HOLDF)
    phase(label, 'C', 'release')
    cl.wait(timeout=240)
    cf.close()
    time.sleep(3)
    open(stop, 'w').close()
    poll.wait(timeout=30)
    pf.close()
    phase(label, 'C', 'after')
    a = sample(label, 'C', -1, 'after')
    lines = trace_lines()[n0:]
    acqs = [l for l in lines if l.startswith('acq ')]
    big = [l for l in acqs if int(re.search(r' b=(\d+)', l).group(1)) > VBYTES]
    outs = {}
    for l in big:
        o = re.search(r' out=(\S+)', l).group(1)
        outs[o] = outs.get(o, 0) + 1
    b = int(re.search(r' b=(\d+)', big[0]).group(1)) if big else None
    caps = sorted({re.search(r' cap=(\d+)', l).group(1) for l in lines if l.startswith('new ')})
    news = count_kind(lines, 'new')
    txt = open(f'{D}/client-C.txt').read()
    tot = re.search(r'^TOTAL ok=(\d+) err=(\d+) missing=(\d+)', txt, re.M)
    errs = sorted({m.group(1)[:120] for m in re.finditer(r'^resp i=\d+ ok=false ms=\d+ text=(.*)$', txt, re.M)})
    rows = []
    for l in open(f'{D}/poll-C.csv'):
        p = l.strip().split(',')
        if len(p) == 5 and 'ERR' not in p:
            try:
                rows.append([int(x) for x in p])
            except ValueError:
                pass
    rs_max = max(r[1] for r in rows) if rows else None
    gl_max = max((int(re.search(r' gl=(\d+)/', l).group(1)) for l in acqs), default=None)
    note(f'ARM [{label}] C: {NCONN} x {VBYTES} B; handlers {news} cap {caps}; request bytes b={b}; large acquires {len(big)} {outs}; '
         f'held at 20 s: hin {hin_held} hout {hout_held}; RequestsSize held {h["rs"]} (poll max {rs_max}, acq gl max {gl_max}); '
         f'histo total {base["total"]} -> {h["total"]} -> {a["total"]} (held - base {h["total"] - base["total"]}); '
         f'QueryMessage live held {h["qm"]}; heap_info used {base["used"]} -> {h["used"]}; RssAnon {base["rss"]} -> {h["rss"]}; '
         f'direct {base["du"]} -> {h["du"]}; pool used {base["pu"]} -> {h["pu"]}; client {tot.groups() if tot else None} errors {errs}; '
         f'RequestsSize after {a["rs"]}')
    held_bytes = hin_held * (b or 0)
    note(f'ARM [{label}] C: held request bytes (hin x b) {held_bytes}; RequestsSize held {h["rs"]}')
    expect(f'{label}: every connection answered (client TOTAL {tot.groups() if tot else None})', bool(tot) and tot.group(3) == '0')
    expect(f'{label}: {NCONN} CQL handlers, receive queue capacity read back {caps}',
           news >= NCONN and caps == (['0'] if label.startswith('C-') else ['1048576']))
    expect(f'{label}: RequestsSize back to 0 after the release ({a["rs"]})', a['rs'] == 0)
    if label.endswith('1g'):
        expect(f'{label}: all {NCONN} requests held at 20 s (hin {hin_held})', hin_held == NCONN)
    if label == 'C-1g':
        expect(f'{label}: RequestsSize held = {NCONN} x b = {NCONN * (b or 0)} ({h["rs"]})', h['rs'] == NCONN * (b or 0))
    if label == 'C-16m':
        expect(f'{label}: held requests <= 16 MiB / b = {16 * MiB // (b or 1)} (hin {hin_held}) and RequestsSize <= 16 MiB ({h["rs"]}, '
               f'poll max {rs_max})', hin_held <= 16 * MiB // (b or 1) and (rs_max or 0) <= 16 * MiB and h['rs'] <= 16 * MiB)
        expect(f'{label}: the reserve is used to within one request of 16 MiB (RequestsSize held {h["rs"]} > 16 MiB - b)',
               h['rs'] > 16 * MiB - (b or 0))
        expect(f'{label}: some large acquires found the reserve short (INSUFFICIENT_*: {outs})',
               any(k.startswith('INSUFFICIENT') for k in outs))
    if label.startswith('C0-'):
        note(f'SOURCE PREDICTION (results §3 defect 1, before run 1): {label} holds all {NCONN} requests and RequestsSize '
             f'{NCONN} x (b - 1 MiB) = {NCONN * ((b or 0) - MiB)}; observed hin {hin_held}, RequestsSize {h["rs"]}')
    sh(f'cp {NCC}/logs/system.log {D}/system.log', check=False)
    stop_node()


def main():
    global MD5
    if java_daemons():
        print('FAIL: a CassandraDaemon is already running: ' + java_daemons()[0][:200]); sys.exit(1)
    os.makedirs(ROOT, exist_ok=True)
    md5 = subprocess.run(f'cd {HARNESS} && md5sum ncc.btm Hold.java HeldRequests.java hold_connections.py Jmx.java cluster-run.py make-node-yaml.sh',
                         shell=True, capture_output=True, text=True).stdout
    MD5 = ' '.join(f'{p[1]}={p[0][:12]}' for p in (l.split() for l in md5.splitlines()) if len(p) == 2)
    subprocess.run(f'rm -rf {CLS} {ROOT}/hold-classes && mkdir -p {CLS} {ROOT}/hold-classes && '
                   f'javac -d {ROOT}/hold-classes {HARNESS}/Hold.java && jar cf {ROOT}/stage4-hold.jar -C {ROOT}/hold-classes . && '
                   f'javac -d {CLS} {HARNESS}/Jmx.java && '
                   f'javac -nowarn -d {CLS} -cp "{C}/build/classes/main:{C}/build/lib/jars/*:{C}/lib/*" {HARNESS}/HeldRequests.java',
                   shell=True, check=True, cwd=C)
    for label in LABELS:
        if label == 'idle':
            run_idle()
        elif label in CONTROL:
            run_control(label)
        else:
            raise SystemExit('unknown label ' + label)
    leftover = java_daemons()
    note('WARNING: a CassandraDaemon is still running after the run' if leftover else 'no CassandraDaemon left running')


MD5 = ''
if __name__ == '__main__':
    try:
        main()
    except SystemExit:
        raise
    except BaseException as e:
        if SUMMARY:
            fail(f'{type(e).__name__}: {e}')
        raise
    finally:
        if java_daemons() and pid_of():
            stop_node()
