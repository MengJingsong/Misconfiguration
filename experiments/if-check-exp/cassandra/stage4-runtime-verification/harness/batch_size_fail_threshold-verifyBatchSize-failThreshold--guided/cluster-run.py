#!/usr/bin/env python3
"""Stage 4, cluster tier, batch_size_fail_threshold-verifyBatchSize-failThreshold--guided (case 9b-9e, amended R1-R8).
usage: cluster-run.py [run-name]        output: ~/stage4-logs/bsf/<run-name, default run1>/cluster/
One node on 127.0.0.1 (~/cassandra-run1, conf and data under ~/stage4-bsf), -Xms4G -Xmx4G, Byteman batch-alloc.btm,
two lifetimes:
  main  yaml: in-flight limits 256 MiB, native_transport_max_message_size 64 MiB (R1). Idle control (10 s, no trace line),
        ctl16k at 50 KiB, then thresholds 50 KiB, 500 KiB, 5 MiB set live over JMX (StorageService
        BatchSizeFailureThreshold, read back) x batches 1, 4, 16 MiB, 20 each (9e control, A, B).
  ctl   the same yaml with native_transport_max_message_size 512 KiB: 16 MiB batches at 50 KiB (9e C, the positive control).
Per arm: jcmd GC.run, a 100 ms JMX poll of heap used and the networking BufferPool (UsedSize, Size, OverflowSize) while
the client runs, GC.run and GC.heap_info after (R2). Every command is logged to session.log; the readings go to
requests.txt (SendBatches req lines), arms.csv and summary.txt (EXPECTED lines, then analyze.py). The node is stopped on
any exit. Exit 1: a set-up or instrument check failed."""
import csv, os, re, statistics, subprocess, sys, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-run1')
HARNESS = os.path.dirname(os.path.abspath(__file__))
BSF = HOME + '/stage4-bsf'
RUN = sys.argv[1] if len(sys.argv) > 1 else 'run1'
D = f'{HOME}/stage4-logs/bsf/{RUN}/cluster'
os.makedirs(D, exist_ok=True)
SESSION = open(D + '/session.log', 'a')
SUMMARY = open(D + '/summary.txt', 'w')
REQS = open(D + '/requests.txt', 'w')
ARMS = csv.writer(open(D + '/arms.csv', 'w'))
ARMS.writerow(['lifetime', 'arm', 'fail_kib', 'bytes', 'n', 'heap_before_gc', 'heap_max', 'heap_max_minus_before',
               'pool_used_before', 'pool_used_max', 'pool_size_before', 'pool_size_max', 'pool_overflow_max', 'heap_after_gc'])
TRACE = D + '/batch-alloc.trace'
BYTEMAN = C + '/build/lib/jars/byteman-4.0.20.jar'
BM_SUBMIT = C + '/build/lib/jars/byteman-submit-4.0.20.jar'
JMX = 7199
SS = 'org.apache.cassandra.db:type=StorageService'
POOL = 'org.apache.cassandra.metrics:type=BufferPool,scope=networking,name='
KiB, MiB = 1024, 1 << 20
COUNT = int(os.environ.get('BSF_COUNT', '20'))
FIXED = ['native_transport_max_request_data_in_flight=256MiB', 'native_transport_max_request_data_in_flight_per_ip=256MiB']
CLS = D + '/classes'


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


def pid_of():
    lines = [l for l in java_daemons() if BSF in l]
    return int(lines[0].split()[0]) if lines else None


def java_daemons():
    """java processes running CassandraDaemon only: a plain grep of ps also matched a shell whose command line held the
    word (run 1, attempt 1, 2026-10-20: the operator's wait loop; results file §3)"""
    r = subprocess.run(['ps', '-eo', 'pid,comm,args'], capture_output=True, text=True)
    out = []
    for l in r.stdout.splitlines()[1:]:
        p = l.split(None, 2)
        if len(p) == 3 and p[1] == 'java' and 'org.apache.cassandra.service.CassandraDaemon' in p[2]:
            out.append(p[0] + ' ' + p[2])
    return out


def any_daemon():
    return '\n'.join(java_daemons())


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
    if any_daemon():
        log('WARNING: a CassandraDaemon is still running: ' + any_daemon()[:200])


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
    SESSION.write('jmx ' + ' '.join(args) + ' -> ' + out[-600:] + '\n')
    return out


def jmx_value(bean, attr):
    for l in jmx('get', bean, attr).splitlines():
        p = l.split('|')
        if len(p) == 3 and p[0] == bean:
            try:
                return int(float(p[2]))
            except ValueError:
                return None
    return None


def trace_lines():
    return open(TRACE).read().splitlines() if os.path.exists(TRACE) else []


def start_node(lifetime, keys):
    stop_node()
    if any_daemon():
        fail('another CassandraDaemon runs on this host: ' + any_daemon()[:200])
    sh(f'rm -rf {BSF}/data {BSF}/logs', check=False)
    _, y = sh(f'{HARNESS}/make-node-yaml.sh ' + ' '.join(f"'{a}'" for a in keys))
    note(f'[{lifetime}] yaml: ' + y.strip().splitlines()[-1][:1500])
    if os.path.exists(TRACE):
        os.rename(TRACE, f'{TRACE}.{int(time.time())}')
    env = dict(os.environ, CASSANDRA_CONF=BSF + '/conf', CASSANDRA_LOG_DIR=BSF + '/logs', MAX_HEAP_SIZE='4G')
    env.pop('HEAP_NEWSIZE', None)
    env['JVM_EXTRA_OPTS'] = (f'-javaagent:{BYTEMAN}=script:{HARNESS}/batch-alloc.btm,listener:true '
                             f'-Xbootclasspath/a:{D}/stage4-alloc.jar -Dorg.jboss.byteman.verbose=false -Dstage4.byteman.out={TRACE}')
    sh(f'bin/cassandra -p {BSF}/cassandra.pid > {D}/stdout-{lifetime}.txt 2>&1', env=env)
    time.sleep(5)
    if pid_of() is None:
        fail(f'node did not start; see {D}/stdout-{lifetime}.txt')
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
    open(f'{D}/submit-l-{lifetime}.txt', 'w').write(lst)
    rules = sorted({m.strip() for m in re.findall(r'^RULE (.+)$', lst, re.M)})
    if not expect(f'[{lifetime}] Submit -l lists the 10 rules of batch-alloc.btm ({len(rules)})', len(rules) == 10):
        fail('Byteman rules not loaded')
    jvm = open(f'/proc/{pid_of()}/cmdline').read().replace('\0', ' ')
    flags = [t for t in jvm.split() if t.startswith(('-Xm', '-javaagent', '-Dstage4', '-Xbootclasspath', '-XX:+Use'))]
    note(f'[{lifetime}] jvm: ' + ' '.join(flags))
    if not expect(f'[{lifetime}] heap -Xms4G -Xmx4G (9b hold fixed)', '-Xms4G' in jvm.split() and '-Xmx4G' in jvm.split()):
        fail('heap is not 4G')
    rc, out = sh('bin/cqlsh 127.0.0.1 9042 -e "CREATE KEYSPACE ks WITH replication = '
                 "{'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE ks.t (pk int PRIMARY KEY, v blob);\"",
                 check=False, timeout=120)
    if rc != 0:
        fail('schema: ' + out[-400:])
    note(f'[{lifetime}] schema: ks (RF 1), ks.t (pk int PRIMARY KEY, v blob)')
    n0 = len(trace_lines())
    time.sleep(10)
    n1 = len(trace_lines())
    if not expect(f'[{lifetime}] idle control: no trace line in 10 s with no batch ({n1 - n0} new, {n1} in all)', n1 == n0):
        fail('trace lines appear with no batch')


def set_threshold(kib):
    out = jmx('setint', SS, 'BatchSizeFailureThreshold', str(kib))
    back = jmx_value(SS, 'BatchSizeFailureThreshold')
    if not expect(f'threshold set live to {kib} KiB, read back {back} KiB', back == kib):
        fail('threshold did not take: ' + out[-300:])


def heap_info():
    p = pid_of()
    sh(f'jcmd {p} GC.run', check=False, quiet=True)
    time.sleep(1)
    _, out = sh(f'jcmd {p} GC.heap_info', check=False, quiet=True)
    m = re.search(r'total (\d+)K, used (\d+)K', out)
    return int(m.group(2)) * 1024 if m else None, out


def arm(lifetime, name, fail_kib, nbytes):
    h0, hi0 = heap_info()
    stop = f'{D}/poll-{name}.stop'
    if os.path.exists(stop):
        os.remove(stop)
    pf = open(f'{D}/poll-{name}.csv', 'w')
    poll = subprocess.Popen(['java', '-cp', CLS, 'Jmx', str(JMX), 'poll', '100', '100000', stop,
                             'java.lang:type=Memory', 'HeapMemoryUsage', POOL + 'UsedSize', 'Value', POOL + 'Size', 'Value',
                             POOL + 'OverflowSize', 'Value'], stdout=pf, stderr=subprocess.STDOUT)
    time.sleep(1.5)
    cmd = (f'java {client_jvm_opts()} -Dlogback.configurationFile={HARNESS}/client-logback.xml -Xmx2g '
           f'-cp "{CLS}:{C}/build/classes/main:{C}/build/lib/jars/*:{C}/lib/*" org.apache.cassandra.transport.SendBatches '
           f'--host 127.0.0.1 --port 9042 --keyspace ks --table t --trace {TRACE} --arm {name} --bytes {nbytes} '
           f'--partitions 64 --count {COUNT} --pause-ms 300')
    rc, out = sh(cmd, timeout=900, check=False)
    time.sleep(1)
    open(stop, 'w').close()
    poll.wait(timeout=30)
    pf.close()
    h1, hi1 = heap_info()
    open(f'{D}/heap-{name}.txt', 'w').write(hi0 + '\n---- after\n' + hi1)
    reqs = [l for l in out.splitlines() if l.startswith('req ')]
    for l in reqs:
        REQS.write(l + '\n')
    REQS.flush()
    rows = []
    for l in open(f'{D}/poll-{name}.csv'):
        p = l.strip().split(',')
        if len(p) == 5 and 'ERR' not in p:
            try:
                rows.append([int(x) for x in p])
            except ValueError:
                pass
    if rc != 0 or len(reqs) != COUNT or len(rows) < 5:
        fail(f'arm {name}: client rc={rc}, {len(reqs)} req lines, {len(rows)} poll rows; client output: {out[-600:]}')
    hb, pu0, ps0 = rows[0][1], rows[0][2], rows[0][3]
    hmax = max(r[1] for r in rows); pumax = max(r[2] for r in rows); psmax = max(r[3] for r in rows); pomax = max(r[4] for r in rows)
    ARMS.writerow([lifetime, name, fail_kib, nbytes, len(reqs), h0, hmax, hmax - hb, pu0, pumax, ps0, psmax, pomax, h1])
    oc = {}
    for l in reqs:
        o = re.search(r'outcome=(\S+)', l).group(1)
        oc[o[:60]] = oc.get(o[:60], 0) + 1
    tot = [int(re.search(r' dec=(-?\d+)', l).group(1)) + int(re.search(r' exe=(-?\d+)', l).group(1)) for l in reqs]
    note(f'ARM [{lifetime}] {name}: threshold {fail_kib} KiB, batch {nbytes} B, outcomes {oc}; median dec+exe {statistics.median(tot):.0f}; '
         f'heap max-start {hmax - hb}; pool UsedSize {pu0}->{pumax} Size {ps0}->{psmax} Overflow max {pomax}; heap after GC {h0}->{h1}')


def main():
    if any_daemon():
        fail('a CassandraDaemon is already running: ' + any_daemon()[:200])
    _, desc = sh('git describe --tags && git rev-parse HEAD')
    md5 = sh(f'cd {HARNESS} && md5sum Alloc.java batch-alloc.btm SendBatches.java Jmx.java cluster-run.py make-node-yaml.sh analyze.py')[1]
    note(f'cluster-run {RUN} {time.strftime("%F %T %Z")} host {os.uname().nodename} clone {" ".join(desc.split())} count {COUNT}')
    note('harness md5 ' + ' '.join(f'{p[1]}={p[0][:12]}' for p in (l.split() for l in md5.splitlines()) if len(p) == 2))
    sh(f'rm -rf {CLS} {D}/alloc-classes && mkdir -p {CLS} {D}/alloc-classes')
    sh(f'javac -d {D}/alloc-classes {HARNESS}/Alloc.java && jar cf {D}/stage4-alloc.jar -C {D}/alloc-classes .')
    sh(f'javac -d {CLS} {HARNESS}/Jmx.java')
    sh(f'javac -nowarn -d {CLS} -cp "{C}/build/classes/main:{C}/build/lib/jars/*:{C}/lib/*" {HARNESS}/SendBatches.java')

    # ---- lifetime 1: main
    start_node('main', FIXED + ['native_transport_max_message_size=64MiB'])
    mm = jmx_value(SS, 'BatchSizeFailureThreshold')
    expect(f'[main] default threshold over JMX {mm} KiB (50 KiB, Config.java:332)', mm == 50)
    _, y = sh(f'grep -E "^(batch_size_warn_threshold|batch_size_fail_threshold|native_transport_max_message_size|native_transport_max_request_data_in_flight[a-z_]*|memtable_allocation_type):" {BSF}/conf/cassandra.yaml')
    note('[main] yaml keys: ' + '; '.join(y.split('\n')).strip('; '))
    arm('main', 'ctl16k', 50, 16 * KiB)
    for kib in (50, 500, 5120):
        set_threshold(kib)
        for b in (1, 4, 16):
            arm('main', f't{kib}k-b{b}m', kib, b * MiB)
    sh(f'cp {BSF}/logs/system.log {D}/system-main.log', check=False)
    stop_node()

    # ---- lifetime 2: the positive control
    start_node('ctl', FIXED + ['native_transport_max_message_size=512KiB'])
    arm('ctl', 'C-msg512k-b16m', 50, 16 * MiB)
    sh(f'cp {BSF}/logs/system.log {D}/system-ctl.log', check=False)
    stop_node()
    if any_daemon():
        note('WARNING: a CassandraDaemon is still running after the run')
    else:
        note('no CassandraDaemon left running')

    sh(f'cat {D}/system-main.log {D}/system-ctl.log > {D}/system-all.log')
    traces = sorted(f for f in os.listdir(D) if f.startswith('batch-alloc.trace'))
    sh(f'cat ' + ' '.join(f'{D}/{f}' for f in traces) + f' > {D}/trace-all.txt')
    _, an = sh(f'python3 {HARNESS}/analyze.py cluster {D}/requests.txt {D}/trace-all.txt {D}/system-all.log', check=False)
    note(an)
    for l in open(D + '/arms.csv'):
        note('arms.csv ' + l.strip())


if __name__ == '__main__':
    try:
        main()
    except SystemExit:
        raise
    except BaseException as e:
        fail(f'{type(e).__name__}: {e}')
