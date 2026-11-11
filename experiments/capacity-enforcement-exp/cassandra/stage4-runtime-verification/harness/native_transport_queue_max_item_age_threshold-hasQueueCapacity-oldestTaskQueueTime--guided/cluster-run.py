#!/usr/bin/env python3
"""Stage 4, cluster tier, native_transport_queue_max_item_age_threshold-hasQueueCapacity-oldestTaskQueueTime--guided
(case 9b-9e, amended 9f R1-R4, 2026-10-20).
usage: cluster-run.py <run-name> <label> [<label> ...]        output: ~/stage4-logs/nqa/<run-name>/cluster/
labels (one node lifetime each; 9b "reset between runs: stop the node, restart"):
  off1 off2 off3   threshold off (Double.MAX_VALUE, the default: key absent), throwing mode   (9e A; R4's three repeats)
  t0.5 t0.1 t0.02  threshold 0.5 / 0.1 / 0.02 x the 12 s native_transport_timeout, throwing mode   (9e B)
  d0.1             threshold 0.1, default (non-throwing) mode                                       (9e B, the repeat)
  ctl              threshold off, native_transport_max_request_data_in_flight 8 MiB, throwing mode  (9e C, the control)
Hold fixed in every lifetime (9b): native_transport_timeout 12 s, native_transport_max_threads 4, in-flight limits
1 GiB (global and per IP; the control's global 8 MiB), native_transport_throw_on_overload per label in the yaml (R3).
One node on 127.0.0.1 from ~/cassandra-run1 (conf and data under ~/stage4-nqa, local disk), Byteman nqa.btm (the R2 stall
and the chk observation), stage4.NqaHold on the boot class path. Per lifetime: start, Submit -l (2 rules), JMX read-back
of every hold-fixed value, schema ks.t (pk int PRIMARY KEY, v blob), 10 s idle control, then the arm: the release file
is removed (the stall holds every EXECUTE), a 2 s JMX poll (R1: Client RequestsSize, the networking pool Size, UsedSize,
OverflowSize, the request pool's PendingTasks/ActiveTasks, heap, RequestDiscarded, ConnectionPaused, direct buffers) runs while
QueueAgeWriter sends 100 EXECUTEs/s of a 64 KiB blob for 60 s; at "sendend" + 2 s a final JMX sample and a class
histogram (live byte[] bytes against the idle control's histogram: the decoded request values, the real resource); then the release file is created and the client waits for every response (120 s budget, 9b). The node is
stopped on any exit. Every command is logged to session.log; summary.txt carries the EXPECTED lines; arms.csv one row per
label. NQA_SECONDS shortens the send phase (shakedowns only). Exit 1: a set-up or instrument check failed."""
import csv, json, os, re, subprocess, sys, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-run1')
HARNESS = os.path.dirname(os.path.abspath(__file__))
NQA = HOME + '/stage4-nqa'
RUN = sys.argv[1]
LABELS = sys.argv[2:]
D = f'{HOME}/stage4-logs/nqa/{RUN}/cluster'
os.makedirs(D, exist_ok=True)
SESSION = open(D + '/session.log', 'a')
SUMMARY = open(D + '/summary.txt', 'a')
BYTEMAN = C + '/build/lib/jars/byteman-4.0.20.jar'
BM_SUBMIT = C + '/build/lib/jars/byteman-submit-4.0.20.jar'
JMX = 7199
SS = 'org.apache.cassandra.db:type=StorageService'
CLIENT = 'org.apache.cassandra.metrics:type=Client,name='
POOL = 'org.apache.cassandra.metrics:type=BufferPool,scope=networking,name='
TP = 'org.apache.cassandra.metrics:type=ThreadPools,path=transport,scope=Native-Transport-Requests,name='
BYTES_RECEIVED = 'org.apache.cassandra.metrics:type=ClientMessageSize,name=BytesReceived'
KiB, MiB, GiB = 1024, 1 << 20, 1 << 30
RATE, VALUE = 100, 65536
SECONDS = float(os.environ.get('NQA_SECONDS', '60'))
POLL_MS = 2000
CLS = D + '/classes'
FIXED = ['native_transport_timeout=12s', 'native_transport_max_threads=4', 'native_transport_rate_limiting_enabled=false',
         'native_transport_max_request_data_in_flight_per_ip=1GiB']
ARMS = {
    'off1': dict(throw=True, thr=None, glob='1GiB'), 'off2': dict(throw=True, thr=None, glob='1GiB'),
    'off3': dict(throw=True, thr=None, glob='1GiB'),
    't0.5': dict(throw=True, thr=0.5, glob='1GiB'), 't0.1': dict(throw=True, thr=0.1, glob='1GiB'),
    't0.02': dict(throw=True, thr=0.02, glob='1GiB'),
    'd0.1': dict(throw=False, thr=0.1, glob='1GiB'),
    'ctl': dict(throw=True, thr=None, glob='8MiB'),
}
GLOB_BYTES = {'1GiB': GiB, '8MiB': 8 * MiB}
# the poll's columns (after the epoch ms)
POLL = [('requests_size', CLIENT + 'RequestsSize', 'Value'), ('pending', TP + 'PendingTasks', 'Value'),
        ('active', TP + 'ActiveTasks', 'Value'), ('pool_size', POOL + 'Size', 'Value'), ('pool_used', POOL + 'UsedSize', 'Value'),
        ('pool_overflow', POOL + 'OverflowSize', 'Value'), ('heap_used', 'java.lang:type=Memory', 'HeapMemoryUsage'),
        ('discarded', CLIENT + 'RequestDiscarded', 'Count'), ('paused', CLIENT + 'ConnectionPaused', 'Count'),
        ('bytes_received', BYTES_RECEIVED, 'Count'), ('direct_used', 'java.nio:type=BufferPool,name=direct', 'MemoryUsed')]
HIST_RE = (r'transport\.messages\.ExecuteMessage$|Dispatcher\$RequestProcessor$|concurrent\.FutureTask$|transport\.Envelope$|'
           r'^\s*\d+:\s+\d+\s+\d+\s+\[B( |$)|^Total ')
ARMS_CSV = D + '/arms.csv'
LAST_M = None
ARM_COLS = ['label', 'throw', 'thr', 'limit_ms', 'global', 'sent', 'M', 'peak_requests_size', 'final_requests_size',
            'final_pending', 'final_active', 'queued_bytes_count', 'peak_pool_size', 'peak_pool_overflow', 'heap_rise',
            'hist_execute', 'hist_processor', 'bytearray_bytes_idle', 'bytearray_bytes_peak', 'bytearray_rise', 'live_rise', 'peak_direct_used', 'ok', 'warned', 'ovl_queue', 'ovl_late', 'ovl_bytes', 'ovl_other', 'err',
            'discarded', 'paused', 'chk_false', 'first_false_after_first_queued_ms', 'hold_in', 'all_answered']


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, file=sys.stderr); SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush(); SESSION.write(s + '\n'); SESSION.flush()


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
    """java processes running CassandraDaemon only (not a shell whose command line holds the word: bsf run 1 defect)"""
    r = subprocess.run(['ps', '-eo', 'pid,comm,args'], capture_output=True, text=True)
    out = []
    for l in r.stdout.splitlines()[1:]:
        p = l.split(None, 2)
        if len(p) == 3 and p[1] == 'java' and 'org.apache.cassandra.service.CassandraDaemon' in p[2]:
            out.append(p[0] + ' ' + p[2])
    return out


def pid_of():
    lines = [l for l in java_daemons() if NQA in l]
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
    stop_node()
    sys.exit(1)


def expect(desc, cond):
    note(f'EXPECTED: {desc} — {"yes" if cond else "NO (recorded; the AI judges it in the results file)"}')
    return cond


def client_jvm_opts():
    return ' '.join(l.strip() for l in open(C + '/conf/jvm11-clients.options') if l.strip().startswith('-'))


def jmx(*args, timeout=60):
    _, out = sh(f'java -cp {CLS} Jmx {JMX} ' + ' '.join(f"'{a}'" for a in args), check=False, timeout=timeout, quiet=True)
    SESSION.write('jmx ' + ' '.join(args) + ' -> ' + out[-1500:] + '\n'); SESSION.flush()
    return out


def jmx_values(pairs):
    """pairs: [(bean, attr)] -> list of str values (None on error)"""
    args = []
    for b, a in pairs:
        args += [b, a]
    vals = {}
    for l in jmx('get', *args).splitlines():
        p = l.split('|')
        if len(p) == 3:
            vals[(p[0], p[1])] = None if p[2].startswith('ERROR') else p[2]
    return [vals.get(pa) for pa in pairs]


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def trace_lines(path):
    return open(path).read().splitlines() if os.path.exists(path) else []


def start_node(label, keys, ad):
    stop_node()
    if java_daemons():
        fail('another CassandraDaemon runs on this host: ' + java_daemons()[0][:200])
    sh(f'rm -rf {NQA}/data {NQA}/logs', check=False)
    _, y = sh(f'{HARNESS}/make-node-yaml.sh ' + ' '.join(f"'{a}'" for a in keys))
    note(f'[{label}] yaml: ' + y.strip().splitlines()[-1][:1500])
    env = dict(os.environ, CASSANDRA_CONF=NQA + '/conf', CASSANDRA_LOG_DIR=NQA + '/logs')
    env['JVM_EXTRA_OPTS'] = (f'-javaagent:{BYTEMAN}=script:{HARNESS}/nqa.btm,listener:true -Xbootclasspath/a:{D}/stage4-nqa-hold.jar '
                             f'-Dorg.jboss.byteman.verbose=false -Dstage4.trace={ad}/nqa.trace -Dstage4.release.file={ad}/release.flag')
    sh(f'ulimit -n 100000 && bin/cassandra -p {NQA}/cassandra.pid > {ad}/stdout.txt 2>&1', env=env)
    time.sleep(5)
    if pid_of() is None:
        fail(f'node did not start; see {ad}/stdout.txt')
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
    open(f'{ad}/submit-l.txt', 'w').write(lst)
    rules = sorted({m.strip() for m in re.findall(r'^RULE (.+)$', lst, re.M)})
    if not expect(f'[{label}] Submit -l lists the 2 rules of nqa.btm ({rules})', len(rules) == 2):
        fail('Byteman rules not loaded')
    pid = pid_of()
    jvm = open(f'/proc/{pid}/cmdline').read().replace('\0', ' ')
    flags = [t for t in jvm.split() if t.startswith(('-Xm', '-javaagent', '-Dstage4', '-Xbootclasspath', '-XX:+Use'))]
    note(f'[{label}] jvm: ' + ' '.join(flags))
    lim = open(f'/proc/{pid}/limits').read()
    m = re.search(r'Max open files\s+(\d+)', lim)
    expect(f'[{label}] node open-file limit >= 100000 ({m.group(1) if m else "?"})', bool(m) and int(m.group(1)) >= 100000)


def setup_checks(label, a):
    pairs = [(SS, 'NativeTransportQueueMaxItemAgeThreshold'), (SS, 'NativeTransportThrowOnOverload'),
             (SS, 'NativeTransportTimeoutMillis'), (SS, 'NativeTransportMaxConcurrentRequestsInBytes'),
             (SS, 'NativeTransportMaxConcurrentRequestsInBytesPerIp'), (TP + 'MaxPoolSize', 'Value')]
    thr, throw, tmo, glob, ip, maxp = jmx_values(pairs)
    note(f'[{label}] JMX read-back: threshold={thr} throw_on_overload={throw} timeout_ms={tmo} in_flight={glob} '
         f'in_flight_per_ip={ip} request_pool_max={maxp}')
    want_thr = a['thr'] if a['thr'] is not None else sys.float_info.max
    ok = [expect(f'[{label}] threshold {want_thr} (9b)', num(thr) is not None and abs(num(thr) - want_thr) <= 1e-12 * max(1.0, want_thr)),
          expect(f'[{label}] native_transport_throw_on_overload {str(a["throw"]).lower()} (R3)', str(throw).lower() == str(a['throw']).lower()),
          expect(f'[{label}] native_transport_timeout 12000 ms (9b)', num(tmo) == 12000),
          expect(f'[{label}] in-flight limit {GLOB_BYTES[a["glob"]]} B (9b/9e C)', num(glob) == GLOB_BYTES[a['glob']]),
          expect(f'[{label}] in-flight per-IP limit {GiB} B (9b)', num(ip) == GiB),
          expect(f'[{label}] native request pool MaxPoolSize 4 (9b native_transport_max_threads)', num(maxp) == 4)]
    if not all(ok):
        fail('a hold-fixed setting did not take')


def poll_rows(path):
    rows = []
    for l in open(path):
        p = l.strip().split(',')
        if len(p) == 1 + len(POLL) and 'ERR' not in p:
            try:
                rows.append([float(x) for x in p])
            except ValueError:
                pass
    return rows


def run_label(label):
    a = ARMS[label]
    ad = f'{D}/{label}'
    sh(f'rm -rf {ad} && mkdir -p {ad}')
    open(f'{ad}/release.flag', 'w').close()                     # present: nothing is held during set-up
    keys = FIXED + [f'native_transport_throw_on_overload={"true" if a["throw"] else "false"}',
                    f'native_transport_max_request_data_in_flight={a["glob"]}']
    if a['thr'] is not None:
        keys.append(f'native_transport_queue_max_item_age_threshold={a["thr"]}')
    start_node(label, keys, ad)
    setup_checks(label, a)
    rc, out = sh('bin/cqlsh 127.0.0.1 9042 -e "CREATE KEYSPACE ks WITH replication = '
                 "{'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE ks.t (pk int PRIMARY KEY, v blob);\"",
                 check=False, timeout=120)
    if rc != 0:
        fail('schema: ' + out[-400:])
    trace = f'{ad}/nqa.trace'
    # idle control (9e step 1)
    idle = f'{ad}/poll-idle.csv'
    sh(f'java -cp {CLS} Jmx {JMX} poll {POLL_MS} 5 {ad}/none.stop ' + ' '.join(f"'{b}' '{t}'" for _, b, t in POLL) + f' > {idle} 2>&1', timeout=60)
    ir = poll_rows(idle)
    holds0 = sum(1 for l in trace_lines(trace) if l.startswith('hold in'))
    expect(f'[{label}] idle control: {len(ir)} samples, RequestsSize {sorted({int(r[1]) for r in ir})}, PendingTasks '
           f'{sorted({int(r[2]) for r in ir})}, no hold line ({holds0})',
           len(ir) >= 3 and all(r[1] == 0 and r[2] == 0 for r in ir) and holds0 == 0)
    base = ir[-1] if ir else None
    _, hist0 = sh(f'jcmd {pid_of()} GC.class_histogram', check=False, quiet=True, timeout=120)
    hl0 = [l for l in hist0.splitlines() if re.search(HIST_RE, l)]
    open(f'{ad}/histogram-idle.txt', 'w').write('\n'.join(hl0) + '\n')
    # the arm
    os.remove(f'{ad}/release.flag')                              # the stall holds every EXECUTE from now on
    stop = f'{ad}/poll.stop'
    pf = open(f'{ad}/poll.csv', 'w')
    poll = subprocess.Popen(['java', '-cp', CLS, 'Jmx', str(JMX), 'poll', str(POLL_MS), '100000', stop] +
                            [x for _, b, t in POLL for x in (b, t)], stdout=pf, stderr=subprocess.STDOUT)
    time.sleep(1)
    cf = open(f'{ad}/client.txt', 'w')
    cmd = (f'java {client_jvm_opts()} -Dlogback.configurationFile={HARNESS}/client-logback.xml -Xmx3g '
           f'-cp "{CLS}:{C}/build/classes/main:{C}/build/lib/jars/*:{C}/lib/*" org.apache.cassandra.transport.QueueAgeWriter '
           f'--host 127.0.0.1 --port 9042 --keyspace ks --table t --rate {RATE} --value-bytes {VALUE} --seconds {SECONDS} --wait-s 180')
    log('+ ' + cmd)
    client = subprocess.Popen(cmd, shell=True, stdout=cf, stderr=subprocess.STDOUT, cwd=C)
    t0 = time.time()
    while True:
        txt = open(f'{ad}/client.txt').read()
        if 'sendend' in txt:
            break
        if client.poll() is not None or time.time() - t0 > SECONDS + 120:
            open(f'{ad}/release.flag', 'w').close()
            fail(f'client ended or stalled before sendend (rc={client.poll()}): {txt[-600:]}')
        time.sleep(0.2)
    time.sleep(2)
    fin = jmx_values([(b, t) for _, b, t in POLL])
    final = dict(zip([n for n, _, _ in POLL], [num(v) for v in fin]))
    final['ms'] = int(time.time() * 1000)
    _, hist = sh(f'jcmd {pid_of()} GC.class_histogram', check=False, quiet=True, timeout=120)
    hl = [l for l in hist.splitlines() if re.search(HIST_RE, l)]
    open(f'{ad}/histogram-at-peak.txt', 'w').write('\n'.join(hl) + '\n')
    holds = [l for l in trace_lines(trace) if l.startswith('hold in')]
    note(f'[{label}] at sendend+2 s: ' + json.dumps(final) + f'; hold in lines {len(holds)}; histogram: ' + ' | '.join(' '.join(l.split()) for l in hl))
    open(f'{ad}/final.json', 'w').write(json.dumps(final) + '\n')
    open(f'{ad}/release.flag', 'w').close()                     # release the stall
    log('release flag created')
    try:
        crc = client.wait(timeout=300)
    except subprocess.TimeoutExpired:
        client.kill(); crc = 'killed'
    cf.close()
    time.sleep(2)
    open(stop, 'w').close()
    try:
        poll.wait(timeout=30)
    except subprocess.TimeoutExpired:
        poll.kill()
    pf.close()
    sh(f'cp {NQA}/logs/system.log {ad}/system.log', check=False)
    stop_node()
    return analyse(label, a, ad, final, base, hl, crc, hl0)


def bytearray_bytes(lines, total=False):
    """live bytes of byte[] (JDK 11 prints "[B (java.base@...)"), or the histogram's Total line"""
    for l in lines:
        p = l.split()
        if total and len(p) == 3 and p[0] == 'Total':
            return int(p[2])
        if not total and len(p) >= 4 and p[3] == '[B':
            return int(p[2])
    return None


def analyse(label, a, ad, final, base, hl, crc, hl0):
    txt = open(f'{ad}/client.txt').read().splitlines()
    reqs = []
    for l in txt:
        m = re.match(r'r k=(\d+) sent_ms=(\d+) resp_ms=(-?\d+) outcome=(\S+)', l)
        if m:
            reqs.append((int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)))
    tot = next((l for l in txt if l.startswith('TOTAL')), '')
    cnt = {k: int(v) for k, v in re.findall(r' (\w+)=(\d+)', tot)}
    rows = poll_rows(f'{ad}/poll.csv')
    trace = trace_lines(f'{ad}/nqa.trace')
    holds = [l for l in trace if l.startswith('hold in')]
    chk = [l for l in trace if l.startswith('chk ')]
    falses = [int(re.search(r'ms=(\d+)', l).group(1)) for l in chk if ' ret=false' in l]
    sent = len(reqs)
    # M from the BytesReceived counter (body + 9-byte header per request) over the arm
    br0 = base[10] if base else None
    global LAST_M
    M = (final['bytes_received'] - br0) / max(1, cnt.get('sent', sent)) - 9 if br0 is not None else None
    if a['throw'] and M:
        LAST_M = M
    Mq = M if a['throw'] else LAST_M          # default mode: the server stops reading, so BytesReceived/sent is not M
    # first queued request: the 5th sent (k = 4: k = 0..3 run held)
    first_q = reqs[4][1] if len(reqs) > 4 else None
    first_false = (min(falses) - first_q) if (falses and first_q) else None
    peak_rs = max([r[1] for r in rows] + [final['requests_size'] or 0])
    peak_ps = max([r[4] for r in rows] + [final['pool_size'] or 0])
    peak_po = max([r[6] for r in rows] + [final['pool_overflow'] or 0])
    heap_rise = (final['heap_used'] - base[7]) if base else None

    def hist(pat):
        for l in hl:
            if re.search(pat, l):
                return int(l.split()[1])
        return None
    qcount = (final['pending'] or 0) + (final['active'] or 0)
    disc = (final['discarded'] - base[8]) if base else None
    paused = (final['paused'] - base[9]) if base else None
    limit_ms = a['thr'] * 12000 if a['thr'] is not None else None
    row = dict(label=label, throw=a['throw'], thr=a['thr'] if a['thr'] is not None else 'off', limit_ms=limit_ms,
               glob=None, sent=sent, M=round(M, 1) if M is not None else None, peak_requests_size=int(peak_rs),
               final_requests_size=int(final['requests_size'] or 0), final_pending=int(final['pending'] or 0),
               final_active=int(final['active'] or 0), queued_bytes_count=int(qcount * Mq) if Mq else None,
               peak_pool_size=int(peak_ps), peak_pool_overflow=int(peak_po), heap_rise=int(heap_rise) if heap_rise is not None else None,
               hist_execute=hist(r'ExecuteMessage$'), hist_processor=hist(r'RequestProcessor$'),
               discarded=int(disc) if disc is not None else None, paused=int(paused) if paused is not None else None,
               bytearray_bytes_idle=bytearray_bytes(hl0), bytearray_bytes_peak=bytearray_bytes(hl),
               bytearray_rise=(bytearray_bytes(hl) - bytearray_bytes(hl0)) if bytearray_bytes(hl) and bytearray_bytes(hl0) else None,
               live_rise=(bytearray_bytes(hl, True) - bytearray_bytes(hl0, True)) if bytearray_bytes(hl, True) and bytearray_bytes(hl0, True) else None,
               peak_direct_used=int(max([r[11] for r in rows] + [final['direct_used'] or 0])),
               chk_false=len(falses), first_false_after_first_queued_ms=first_false, hold_in=len(holds),
               all_answered='all_answered=true' in tot)
    row['global'] = GLOB_BYTES[a['glob']]
    for k in ('ok', 'warned', 'ovl_queue', 'ovl_late', 'ovl_bytes', 'ovl_other', 'err'):
        row[k] = cnt.get(k)
    del row['glob']
    new = not os.path.exists(ARMS_CSV)
    with open(ARMS_CSV, 'a') as f:
        w = csv.DictWriter(f, fieldnames=ARM_COLS)
        if new:
            w.writeheader()
        w.writerow(row)
    note(f'ARM {label}: ' + json.dumps(row))
    # per-arm EXPECTED lines (validity and instruments; the prediction is judged across arms below)
    expect(f'[{label}] client sent {sent} = {int(RATE * SECONDS)} and every request was answered (rc={crc})',
           sent == int(RATE * SECONDS) and row['all_answered'])
    expect(f'[{label}] the stall held 4 running requests (hold in lines {len(holds)}, ActiveTasks at the peak {row["final_active"]})',
           len(holds) == 4 and row['final_active'] == 4)
    series = [r[1] for r in rows if r[0] <= final['ms']]
    if a['thr'] is None and a['glob'] == '1GiB':
        mono = all(y >= x for x, y in zip(series, series[1:]))
        expect(f'[{label}] check off: queued bytes grow for the whole run (RequestsSize series nondecreasing, {len(series)} '
               f'samples, last poll {int(series[-1]) if series else None}, final {row["final_requests_size"]}; refusals '
               f'{row["ovl_queue"]}+{row["ovl_bytes"]})',
               mono and len(series) >= 10 and row['final_requests_size'] > series[len(series) // 2] and row['ovl_queue'] == 0 and row['ovl_bytes'] == 0)
    if a['thr'] is not None and a['throw']:
        expect(f'[{label}] disallow evidence: queue-age refusals at the client {row["ovl_queue"]} = RequestDiscarded '
               f'{row["discarded"]}, chk ret=false {row["chk_false"]}', row['ovl_queue'] > 0 and row['ovl_queue'] == row['discarded']
               and row['chk_false'] >= row['ovl_queue'])
    if not a['throw']:
        expect(f'[{label}] default mode: nothing refused (ovl_queue {row["ovl_queue"]}), connection paused {row["paused"]} times, '
               f'chk ret=false {row["chk_false"]}', row['ovl_queue'] == 0 and (row['paused'] or 0) > 0)
    if a['glob'] == '8MiB':
        expect(f'[{label}] positive control: RequestsSize peak {row["peak_requests_size"]} <= 8 MiB and refusals "bytes in flight" '
               f'{row["ovl_bytes"]} > 0', row['peak_requests_size'] <= 8 * MiB and (row['ovl_bytes'] or 0) > 0)
    return row


def judge():
    """the frozen §9a prediction with R4's numeric edges, over every row of arms.csv"""
    if not os.path.exists(ARMS_CSV):
        return
    rows = {r['label']: r for r in csv.DictReader(open(ARMS_CSV))}
    for obs in ('peak_requests_size', 'queued_bytes_count', 'bytearray_rise', 'live_rise'):
        offs = [float(rows[l][obs]) for l in ('off1', 'off2', 'off3') if l in rows and rows[l][obs] not in ('', 'None')]
        if len(offs) < 3:
            note(f'JUDGE {obs}: only {len(offs)} check-off arms; no judgement')
            continue
        band = max(offs) - min(offs)
        off = sum(offs) / 3
        note(f'JUDGE {obs}: check-off peaks {[int(x) for x in offs]}, mean {off:.0f}, band (range) {band:.0f}')
        same = True
        for l in ('t0.5', 't0.1', 't0.02', 'd0.1'):
            if l not in rows or rows[l][obs] in ('', 'None'):
                continue
            v = float(rows[l][obs])
            within = abs(v - off) <= band
            if l != 'd0.1':
                same = same and within
            note(f'JUDGE {obs} {l}: {v:.0f} = {100 * v / off:.2f} % of the check-off mean; within the band: {within}; '
                 f'below by {off - v:.0f} = {(off - v) / band if band else float("inf"):.1f} bands')
        if 't0.02' in rows:
            v = float(rows['t0.02'][obs])
            falls = v < 0.5 * off and (off - v) > 3 * band
            expect(f'[{obs}] Confirmed edge (R4): peaks at 0.5, 0.1, 0.02 within the band of the check-off peak', same)
            expect(f'[{obs}] Refuted edge (R4): the peak at 0.02 more than 50 % below the check-off peak and more than 3 bands below', falls)
        if 'ctl' in rows:
            expect(f'[{obs}] the control moved queued bytes: {rows["ctl"][obs]} vs the check-off mean {off:.0f}', float(rows['ctl'][obs]) < 0.5 * off)


def main():
    if java_daemons():
        fail('a CassandraDaemon is already running: ' + java_daemons()[0][:200])
    bad = [l for l in LABELS if l not in ARMS]
    if bad:
        fail(f'unknown labels {bad}')
    _, desc = sh('git describe --tags && git rev-parse HEAD')
    md5 = sh(f'cd {HARNESS} && md5sum NqaHold.java nqa.btm QueueAgeWriter.java Jmx.java cluster-run.py make-node-yaml.sh client-logback.xml')[1]
    note(f'cluster-run {RUN} {" ".join(LABELS)} {time.strftime("%F %T %Z")} host {os.uname().nodename} clone {" ".join(desc.split())} '
         f'rate {RATE}/s value {VALUE} B seconds {SECONDS} poll {POLL_MS} ms')
    note('harness md5 ' + ' '.join(f'{p[1]}={p[0][:12]}' for p in (l.split() for l in md5.splitlines()) if len(p) == 2))
    sh(f'rm -rf {CLS} {D}/hold-classes && mkdir -p {CLS} {D}/hold-classes')
    sh(f'javac -d {D}/hold-classes {HARNESS}/NqaHold.java && jar cf {D}/stage4-nqa-hold.jar -C {D}/hold-classes .')
    sh(f'javac -d {CLS} {HARNESS}/Jmx.java')
    sh(f'javac -nowarn -d {CLS} -cp "{C}/build/classes/main:{C}/build/lib/jars/*:{C}/lib/*" {HARNESS}/QueueAgeWriter.java')
    for label in LABELS:
        note(f'==== {label} {time.strftime("%F %T")}')
        run_label(label)
    if java_daemons():
        note('WARNING: a CassandraDaemon is still running after the run')
    else:
        note('no CassandraDaemon left running')
    judge()


if __name__ == '__main__':
    try:
        main()
    except SystemExit:
        raise
    except BaseException as e:
        fail(f'{type(e).__name__}: {e}')
