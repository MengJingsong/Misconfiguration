#!/usr/bin/env python3
"""Stage 4, cluster tier, native_transport_max_message_size-processFirstFrameOfLargeMessage-maxMessageSize--guided
(case 9b-9e, amended 9f R1, R2; frozen 9 hash 14c3b5fd...).
usage: cluster-run.py [run-name] [label ...]     output: ~/stage4-logs/nms/<run-name, default run1>/cluster/<label>/
One node on 127.0.0.1 (~/cassandra-run1, conf and data under ~/stage4-nms), -Xms4G -Xmx4G, NMT summary, Byteman nms.btm.
One node lifetime per label (restart-only knob), in this order unless labels are given:
  k16   knob 16 MiB, in-flight limits 256 MiB, receive-queue capacity 128 MiB (9b): control (one 64 KiB request, idle
        baseline), then scenario A: one 8 MiB request (blob 8,388,608 B), every frame but the last sent, held 30 s
  k4    scenario B at 4 MiB          k1    scenario B at 1 MiB
  kdef  knob unset (derived default, min(max_mutation_size, in-flight limits) = 16 MiB); supplementary, not a 9a row
  ref   9f R1 reference arm: knob 12 MiB, in-flight 256 MiB, queue capacity 128 MiB, two connections, each 8 MiB held
  ctl   9f R1 control arm:   knob 12 MiB, in-flight 12 MiB (both), queue capacity 1 MiB, two connections, each 8 MiB held
Per label: a 200 ms JMX poll (networking BufferPool Size, UsedSize, OverflowSize; java.nio direct MemoryUsed, Count; Client
RequestDiscarded Count) for the whole client run; at 5 s of the hold RssAnon and NMT summary. Readings (R2): retained =
pool Size at 5 s of the hold minus the median Size with the connection(s) open and idle. Writes session.log, client.txt,
poll.csv, nms.trace, nmt-*.txt, system.log, summary.txt per label and the run's summary.txt (EXPECTED and ROW lines).
The node is stopped on any exit. Exit 1: a set-up or instrument check failed."""
import os, re, statistics, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-run1')
HARNESS = os.path.dirname(os.path.abspath(__file__))
NMS = HOME + '/stage4-nms'
RUN = sys.argv[1] if len(sys.argv) > 1 else 'run1'
ROOT = f'{HOME}/stage4-logs/nms/{RUN}/cluster'
os.makedirs(ROOT, exist_ok=True)
SESSION = open(ROOT + '/session.log', 'a')
SUMMARY = open(ROOT + '/summary.txt', 'a')
BYTEMAN = C + '/build/lib/jars/byteman-4.0.20.jar'
BM_SUBMIT = C + '/build/lib/jars/byteman-submit-4.0.20.jar'
JMX = 7199
POOL = 'org.apache.cassandra.metrics:type=BufferPool,scope=networking,name='
DIRECT = 'java.nio:type=BufferPool,name=direct'
DISC = 'org.apache.cassandra.metrics:type=Client,name=RequestDiscarded'
KiB, MiB = 1024, 1 << 20
BLOB = 8 * MiB
HOLD_S = 30
CLS = ROOT + '/classes'
WIDE = ['native_transport_max_request_data_in_flight=256MiB', 'native_transport_max_request_data_in_flight_per_ip=256MiB',
        'native_transport_receive_queue_capacity=128MiB']
LABELS = {
    'k16': (WIDE + ['native_transport_max_message_size=16MiB'], 1, 16 * MiB),
    'k4': (WIDE + ['native_transport_max_message_size=4MiB'], 1, 4 * MiB),
    'k1': (WIDE + ['native_transport_max_message_size=1MiB'], 1, 1 * MiB),
    'kdef': (WIDE, 1, None),
    'ref': (WIDE + ['native_transport_max_message_size=12MiB'], 2, 12 * MiB),
    'ctl': (['native_transport_max_request_data_in_flight=12MiB', 'native_transport_max_request_data_in_flight_per_ip=12MiB',
             'native_transport_receive_queue_capacity=1MiB', 'native_transport_max_message_size=12MiB'], 2, 12 * MiB),
    # shakedown only (instrument check of the three paths with a 2 MiB request and a 5 s hold; values of no 9a arm)
    'shake-allow': (WIDE + ['native_transport_max_message_size=4MiB'], 1, 4 * MiB, 2 * MiB, 5),
    'shake-refuse': (WIDE + ['native_transport_max_message_size=1MiB'], 1, 1 * MiB, 2 * MiB, 5),
    'shake-pause': (['native_transport_max_request_data_in_flight=2560KiB', 'native_transport_max_request_data_in_flight_per_ip=2560KiB',
                     'native_transport_receive_queue_capacity=512KiB', 'native_transport_max_message_size=2560KiB'], 2, 2560 * KiB, 2 * MiB, 5),
}
ORDER = ['k16', 'k4', 'k1', 'kdef', 'ref', 'ctl']
D = ROOT          # the current label's folder, set per label


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
    """java processes running CassandraDaemon only (a grep of ps can match a shell: batch_size_fail_threshold run 1)"""
    r = subprocess.run(['ps', '-eo', 'pid,comm,args'], capture_output=True, text=True)
    out = []
    for l in r.stdout.splitlines()[1:]:
        p = l.split(None, 2)
        if len(p) == 3 and p[1] == 'java' and 'org.apache.cassandra.service.CassandraDaemon' in p[2]:
            out.append(p[0] + ' ' + p[2])
    return out


def pid_of():
    lines = [l for l in java_daemons() if NMS in l]
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


def jmx_get(*pairs):
    _, out = sh(f'java -cp {CLS} Jmx {JMX} get ' + ' '.join(f"'{a}'" for a in pairs), check=False, timeout=60, quiet=True)
    v = {}
    for l in out.splitlines():
        p = l.split('|')
        if len(p) == 3:
            v[(p[0], p[1])] = p[2]
    return v


def start_node(label, keys):
    stop_node()
    if java_daemons():
        fail('another CassandraDaemon runs on this host: ' + java_daemons()[0][:200])
    sh(f'rm -rf {NMS}/data {NMS}/logs', check=False)
    _, y = sh(f'{HARNESS}/make-node-yaml.sh ' + ' '.join(f"'{a}'" for a in keys))
    note(f'[{label}] yaml: ' + y.strip().splitlines()[-1][:1500])
    env = dict(os.environ, CASSANDRA_CONF=NMS + '/conf', CASSANDRA_LOG_DIR=NMS + '/logs', MAX_HEAP_SIZE='4G')
    env.pop('HEAP_NEWSIZE', None)
    env['JVM_EXTRA_OPTS'] = (f'-javaagent:{BYTEMAN}=script:{HARNESS}/nms.btm,listener:true -Dorg.jboss.byteman.verbose=false '
                             f'-Dstage4.byteman.out={D}/nms.trace -XX:NativeMemoryTracking=summary')
    sh(f'ulimit -n 100000 && bin/cassandra -p {NMS}/cassandra.pid > {D}/stdout.txt 2>&1', env=env)
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
    if not expect(f'[{label}] Submit -l lists the 6 rules of nms.btm ({len(rules)})', len(rules) == 6):
        fail('Byteman rules not loaded')
    pid = pid_of()
    jvm = open(f'/proc/{pid}/cmdline').read().replace('\0', ' ').split()
    lim = open(f'/proc/{pid}/limits').read()
    m = re.search(r'Max open files\s+(\d+)', lim)
    note(f'[{label}] jvm: ' + ' '.join(t for t in jvm if t.startswith(('-Xm', '-javaagent', '-Dstage4', '-XX:NativeMemory'))) +
         f'; max open files {m.group(1) if m else "?"}')
    if not expect(f'[{label}] heap -Xms4G -Xmx4G', '-Xms4G' in jvm and '-Xmx4G' in jvm):
        fail('heap is not 4G')
    rc, out = sh('bin/cqlsh 127.0.0.1 9042 -e "CREATE KEYSPACE ks WITH replication = '
                 "{'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE ks.t (pk int PRIMARY KEY, v blob);\"",
                 check=False, timeout=120)
    if rc != 0:
        fail('schema: ' + out[-400:])
    note(f'[{label}] schema: ks (RF 1), ks.t (pk int PRIMARY KEY, v blob)')


def config_dump(label):
    """the startup config dump's values for the 9b keys (Config.java:1371)"""
    txt = open(f'{NMS}/logs/system.log').read()
    m = re.search(r'Node configuration:\[(.*?)\]\n', txt, re.S)
    got = {}
    if m:
        for k in ('native_transport_max_message_size', 'native_transport_max_request_data_in_flight',
                  'native_transport_max_request_data_in_flight_per_ip', 'native_transport_receive_queue_capacity',
                  'native_transport_throw_on_overload', 'max_mutation_size', 'native_transport_max_frame_size'):
            mm = re.search(r'(?:^|; )' + k + r'=([^;]*)', m.group(1))
            got[k] = mm.group(1) if mm else None
    note(f'[{label}] config dump: ' + '; '.join(f'{k}={v}' for k, v in got.items()))
    return got


def poll_thread(stop, rows):
    p = subprocess.Popen(['java', '-cp', CLS, 'Jmx', str(JMX), 'poll', '200', '100000', stop,
                          POOL + 'Size', 'Value', POOL + 'UsedSize', 'Value', POOL + 'OverflowSize', 'Value',
                          DIRECT, 'MemoryUsed', DIRECT, 'Count', DISC, 'Count'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    with open(f'{D}/poll.csv', 'w') as f:
        f.write('ms,size,used,overflow,direct_used,direct_count,discarded\n')
        for l in p.stdout:
            f.write(l); f.flush()
            q = l.strip().split(',')
            if len(q) == 7 and 'ERR' not in q:
                try:
                    rows.append([int(float(x)) for x in q])
                except ValueError:
                    pass
    p.wait()


def rss_anon(pid):
    for l in open(f'/proc/{pid}/status'):
        if l.startswith('RssAnon:'):
            return int(l.split()[1]) * 1024
    return None


def nmt(tag):
    _, out = sh(f'jcmd {pid_of()} VM.native_memory summary', check=False, quiet=True)
    open(f'{D}/nmt-{tag}.txt', 'w').write(out)
    m = re.search(r'-\s+Other \(reserved=\d+KB, committed=(\d+)KB\)', out)
    return int(m.group(1)) * 1024 if m else None


def at_or_before(rows, t):
    c = [r for r in rows if r[0] <= t]
    return c[-1] if c else None


def run_label(label):
    global D
    keys, nconn, knob = LABELS[label][:3]
    blob, hold_s = LABELS[label][3:5] if len(LABELS[label]) > 3 else (BLOB, HOLD_S)
    D = f'{ROOT}/{label}'
    os.makedirs(D, exist_ok=True)
    for f in ('nms.trace', 'poll.csv', 'client.txt'):
        if os.path.exists(f'{D}/{f}'):
            os.rename(f'{D}/{f}', f'{D}/{f}.{int(time.time())}')
    note(f'==== {label}: knob {knob if knob else "unset"}, {nconn} connection(s), blob {blob} B, hold {hold_s} s')
    start_node(label, keys)
    cfg = config_dump(label)
    pid = pid_of()
    time.sleep(5)
    n_trace0 = len(open(f'{D}/nms.trace').read().splitlines()) if os.path.exists(f'{D}/nms.trace') else 0
    stop = f'{D}/poll.stop'
    if os.path.exists(stop):
        os.remove(stop)
    rows = []
    pt = threading.Thread(target=poll_thread, args=(stop, rows), daemon=True)
    pt.start()
    time.sleep(2)
    nmt('idle')
    rss_idle = rss_anon(pid)
    cmd = ['python3', f'{HARNESS}/hold-client.py', '--conns', str(nconn), '--blob', str(blob), '--hold-s', str(hold_s)]
    log('+ ' + ' '.join(cmd))
    cl = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=HARNESS,
                          env=dict(os.environ, CASSANDRA_HOME=C))
    ev = {}
    lines = []
    at5 = {}
    for l in cl.stdout:
        lines.append(l.rstrip('\n'))
        open(f'{D}/client.txt', 'a').write(l)
        k = l.split()[0] if l.strip() else ''
        msm = re.search(r' ms=(\d+)', l)
        if msm:
            ev.setdefault(k, []).append((int(msm.group(1)), l.strip()))
        if k == 'HELD':
            th = int(msm.group(1))
            while time.time() * 1000 < th + 5000:
                time.sleep(0.05)
            at5['ms'] = int(time.time() * 1000)
            at5['rss'] = rss_anon(pid)
            at5['nmt_other'] = nmt('hold5s')
            log(f'5 s into the hold: RssAnon {at5["rss"]}, NMT Other committed {at5["nmt_other"]}')
    rc = cl.wait(timeout=600)
    time.sleep(2)
    nmt('after')
    open(stop, 'w').close()
    pt.join(timeout=30)
    sh(f'cp {NMS}/logs/system.log {D}/system.log', check=False)
    if rc != 0 or 'DONE' not in ev or 'HELD' not in ev:
        fail(f'[{label}] client rc={rc}; last output: ' + ' | '.join(lines[-6:]))
    if len(rows) < 20:
        fail(f'[{label}] only {len(rows)} poll rows')

    t_idle = ev['IDLE'][0][0]; t_send = ev['SEND'][0][0]; t_held = ev['HELD'][0][0]; t_last = ev['LAST'][0][0] if 'LAST' in ev else t_held
    base = [r for r in rows if t_idle + 2000 <= r[0] <= t_send]
    if not expect(f'[{label}] baseline samples with the connection(s) open and idle: {len(base)} (>= 10)', len(base) >= 10):
        fail('no idle baseline')
    b = [statistics.median(r[i] for r in base) for i in range(1, 7)]
    s5 = at_or_before(rows, t_held + 5000)
    hold = [r for r in rows if t_held <= r[0] <= t_last]
    ret = s5[1] - b[0]
    note(f'[{label}] baseline (median of {len(base)}): Size {b[0]:.0f} UsedSize {b[1]:.0f} OverflowSize {b[2]:.0f} direct {b[3]:.0f} '
         f'direct count {b[4]:.0f} RequestDiscarded {b[5]:.0f}')
    note(f'[{label}] at 5 s of the hold (sample ms {s5[0]}, HELD+{s5[0] - t_held} ms): Size {s5[1]} UsedSize {s5[2]} OverflowSize {s5[3]} '
         f'direct {s5[4]} count {s5[5]} RequestDiscarded {s5[6]}')
    note(f'READING [{label}] retained (Size at 5 s - baseline) = {ret:.0f} B = {ret / MiB:.3f} MiB; OverflowSize +{s5[3] - b[2]:.0f}; '
         f'UsedSize +{s5[2] - b[1]:.0f}; direct +{s5[4] - b[3]:.0f}; max Size over the hold - baseline = {max(r[1] for r in hold) - b[0]:.0f}; '
         f'RssAnon +{(at5.get("rss") or 0) - (rss_idle or 0)}; RequestDiscarded +{rows[-1][6] - b[5]:.0f} by the end')
    for k in ('SEND', 'SENT', 'HELD', 'RESP', 'FOLLOW', 'CTL'):
        for _, l in ev.get(k, []):
            note(f'[{label}] client: {l[:400]}')
    # Byteman trace of this lifetime (after the start-up)
    tr = open(f'{D}/nms.trace').read().splitlines() if os.path.exists(f'{D}/nms.trace') else []
    kinds = {}
    for l in tr:
        kinds[l.split()[0]] = kinds.get(l.split()[0], 0) + 1
    note(f'[{label}] trace lines: {kinds} ({n_trace0} before the client)')
    held = {}
    for l in tr:
        if l.startswith('frm '):
            d = dict(re.findall(r'(\w+)=(\S+)', l))
            if int(d['ms']) <= t_held + 5000:
                held[d['h']] = d
    for h, d in held.items():
        note(f'[{label}] trace at 5 s of the hold, connection h={h}: last frame seen toobig={d["toobig"]} ovl={d["ovl"]} buffers kept n={d["n"]} '
             f'received before it {d["recv"]} of size {d["size"]}')
    for l in tr:
        if l.startswith(('lm ', 'toobig ', 'acq ', 'ffl ', 'done ')):
            note(f'[{label}] trace: {l}')
    stop_node()
    return dict(label=label, knob=knob, cfg=cfg, ret=ret, held=held, ev=ev, kinds=kinds)


def classify(ret):
    if 6 * MiB <= ret <= 10 * MiB:
        return 'about 8 MiB'
    if ret <= 1 * MiB:
        return 'about one frame'
    return 'neither'


def main():
    if java_daemons():
        fail('a CassandraDaemon is already running: ' + java_daemons()[0][:200])
    labels = sys.argv[2:] or ORDER
    _, desc = sh('git describe --tags && git rev-parse HEAD')
    md5 = sh(f'cd {HARNESS} && md5sum cluster-run.py hold-client.py drv.py nms.btm Jmx.java make-node-yaml.sh')[1]
    note(f'cluster-run {RUN} {time.strftime("%F %T %Z")} host {os.uname().nodename} clone {" ".join(desc.split())} labels {labels}')
    note('harness md5 ' + ' '.join(f'{p[1]}={p[0][:12]}' for p in (l.split() for l in md5.splitlines()) if len(p) == 2))
    sh(f'rm -rf {CLS} && mkdir -p {CLS} && javac -d {CLS} {HARNESS}/Jmx.java')
    res = {}
    for label in labels:
        res[label] = run_label(label)
        r = res[label]
        if r['knob']:
            expect(f'[{label}] config dump native_transport_max_message_size = {r["knob"]} B ({r["cfg"].get("native_transport_max_message_size")})',
                   r['cfg'].get('native_transport_max_message_size') in (f'{r["knob"] // MiB}MiB', f'{r["knob"] // KiB}KiB', f'{r["knob"]}B'))
    if java_daemons():
        note('WARNING: a CassandraDaemon is still running after the run')
    else:
        note('no CassandraDaemon left running')
    note('---- 9a readings (R2: about 8 MiB = 6-10 MiB over the idle baseline; about one frame <= 1 MiB)')
    for label in labels:
        r = res[label]
        note(f'SUMMARY {label}: retained {r["ret"] / MiB:.3f} MiB -> {classify(r["ret"])}; responses: ' +
             ' | '.join(l.split(' ', 2)[2][:160] for _, l in r['ev'].get('RESP', [])))
    if all(k in res for k in ('k16', 'k4', 'k1', 'ref', 'ctl')):
        c = {k: classify(res[k]['ret']) for k in ('k16', 'k4', 'k1')}
        lowers = res['ctl']['ret'] < res['ref']['ret'] - 4 * MiB and classify(res['ctl']['ret']) == 'about 8 MiB'
        note(f'control: ref {res["ref"]["ret"] / MiB:.3f} MiB, ctl {res["ctl"]["ret"] / MiB:.3f} MiB -> control lowers retention: {lowers}')
        if res['k16']['ret'] <= 1 * MiB:
            row = 'Invalid run (the pool does not rise for the held request at 16 MiB)'
        elif all(v == 'about 8 MiB' for v in c.values()):
            row = 'Confirmed' if lowers else 'Not confirmed (the control does not change retention)'
        elif c['k1'] == c['k4'] == 'about one frame' and c['k16'] == 'about 8 MiB':
            row = 'Refuted (retained memory follows the knob, per request)'
        elif all(v == 'about one frame' for v in c.values()):
            row = 'Not confirmed (about one frame at every value)'
        else:
            row = 'no 9a row fits: ' + str(c)
        note(f'ROW (computed by the run script; the AI judges it in the results file): {row}; per value {c}')


if __name__ == '__main__':
    try:
        main()
    except SystemExit:
        raise
    except BaseException as e:
        fail(f'{type(e).__name__}: {e}')
