#!/usr/bin/env python3
"""Stage 4, cluster tier, batch_size_warn_threshold-verifyBatchSize-size--autonomous (B3 as amended A6-A8, 2026-10-26).
usage: cluster-run.py [run-name]        output: ~/s4-b9-bs-logs/<run-name, default run1>/cluster/
One node on 127.0.1.1 (port slot 1: JMX 7110, Byteman agent 19110, native 9042), tree ~/s4-b9-bs-n (ant jar), conf under
~/s4-b9-bs-node, data on tmpfs /dev/shm/s4-b9-bs, -Xms2G -Xmx2G, G1 with -Xlog:gc, Byteman warn-size.btm. Three lifetimes
(data wiped between):
  L1  yaml warn 5KiB, fail 100000KiB. Phases W1a, W1b (2000 LOGGED batches of 50 partitions x 1 KiB), W2a, W2b (20 UNLOGGED
      batches of 20480 partitions x 1 KiB = 20 MiB); then warn set live to 90000KiB over JMX (read back) and phases
      L1live-W1, L1live-W2.
  L2  yaml warn 90000KiB, fail 100000KiB: W1a, W1b, W2a, W2b.
  L3  yaml warn 5KiB, fail 20KiB: L3-ctl (W1, 2000 batches, all to be rejected), then warn set live to 200KiB: L3-inv (200 batches).
Per phase: a 100 ms JMX poll of heap used, nodetool flush, data-directory bytes (du -sb), WriteLatency Count of ks.t before/after.
Every command is logged to session.log; readings go to requests.txt (client lines), phases.csv, summary.txt (EXPECTED lines, then
analyze.py). The node is stopped on any exit. Exit 1: a set-up or instrument check failed."""
import csv, os, re, subprocess, sys, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/s4-b9-bs-n')
HARNESS = os.path.dirname(os.path.abspath(__file__))
BSN = HOME + '/s4-b9-bs-node'
DD = '/dev/shm/s4-b9-bs'
RUN = sys.argv[1] if len(sys.argv) > 1 else 'run1'
D = f'{HOME}/s4-b9-bs-logs/{RUN}/cluster'
os.makedirs(D, exist_ok=True)
SESSION = open(D + '/session.log', 'a')
SUMMARY = open(D + '/summary.txt', 'w')
REQS = open(D + '/requests.txt', 'w')
PHF = open(D + '/phases.csv', 'w')
PHASES = csv.writer(PHF)
PHASES.writerow(['phase', 'lifetime', 'disk_bytes', 'writes_before', 'writes_after', 'heap_poll_max'])
PHF.flush()
TRACE = D + '/warn-size.trace'
BYTEMAN = C + '/build/lib/jars/byteman-4.0.20.jar'
BM_SUBMIT = C + '/build/lib/jars/byteman-submit-4.0.20.jar'
ADDR, JMX, BMPORT = '127.0.1.1', 7110, 19110
SS = 'org.apache.cassandra.db:type=StorageService'
WL = 'org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=t,name=WriteLatency'
COUNT1 = int(os.environ.get('B9BS_COUNT1', '2000'))
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


def java_daemons():
    """java processes running CassandraDaemon only (not a shell whose command line holds the word)"""
    r = subprocess.run(['ps', '-eo', 'pid,comm,args'], capture_output=True, text=True)
    out = []
    for l in r.stdout.splitlines()[1:]:
        p = l.split(None, 2)
        if len(p) == 3 and p[1] == 'java' and 'org.apache.cassandra.service.CassandraDaemon' in p[2]:
            out.append(p[0] + ' ' + p[2])
    return out


def pid_of():
    """my node: the daemon whose command line names my conf directory"""
    for l in java_daemons():
        if BSN in l:
            return int(l.split()[0])
    return None


def stop_node():
    p = pid_of()
    if p:
        sh(f'bin/nodetool -h 127.0.0.1 -p {JMX} stopdaemon', check=False, timeout=120)
        for _ in range(60):
            if pid_of() is None:
                break
            time.sleep(1)
        if pid_of():
            sh(f'kill -9 {pid_of()}', check=False)
            time.sleep(2)
    if pid_of():
        log('WARNING: my CassandraDaemon is still running')


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


def start_node(life, keys):
    stop_node()
    if pid_of():
        fail('my CassandraDaemon is still running')
    sh(f'rm -rf {DD} {BSN}/logs', check=False)
    _, y = sh(f'{HARNESS}/make-node-yaml.sh ' + ' '.join(f"'{a}'" for a in keys))
    note(f'[{life}] yaml: ' + y.strip().splitlines()[-1][:1800])
    env = dict(os.environ, CASSANDRA_CONF=BSN + '/conf', CASSANDRA_LOG_DIR=BSN + '/logs', MAX_HEAP_SIZE='2G')
    env.pop('HEAP_NEWSIZE', None)
    env['JVM_EXTRA_OPTS'] = (f'-javaagent:{BYTEMAN}=script:{HARNESS}/warn-size.btm,listener:true,port:{BMPORT} '
                             f'-Xbootclasspath/a:{D}/stage4-alloc.jar -Dorg.jboss.byteman.verbose=false -Dstage4.byteman.out={TRACE} '
                             f'-Xlog:gc:file={D}/gc-{life}.log:utc')
    sh(f'ulimit -n 100000 && bin/cassandra -p {BSN}/cassandra.pid > {D}/stdout-{life}.txt 2>&1', env=env)
    time.sleep(5)
    if pid_of() is None:
        fail(f'node did not start; see {D}/stdout-{life}.txt')
    t0 = time.time()
    while time.time() - t0 < 300:
        if pid_of() is None:
            fail('node died during start-up')
        _, st = sh(f'bin/nodetool -h 127.0.0.1 -p {JMX} status', check=False, quiet=True)
        _, sb = sh(f'bin/nodetool -h 127.0.0.1 -p {JMX} statusbinary', check=False, quiet=True)
        if re.search(rf'^UN\s+{re.escape(ADDR)}\s', st, re.M) and re.search(r'^running\s*$', sb, re.M):
            log(f'node UN and native transport running after {time.time() - t0:.0f} s')
            break
        time.sleep(2)
    else:
        fail('node not UN / native transport not running in 300 s')
    _, lst = sh(f'java -cp {BM_SUBMIT} org.jboss.byteman.agent.submit.Submit -p {BMPORT} -l', check=False)
    open(f'{D}/submit-l-{life}.txt', 'w').write(lst)
    rules = sorted({m.strip() for m in re.findall(r'^RULE (.+)$', lst, re.M)})
    if not expect(f'[{life}] Submit -l (agent port {BMPORT}) lists the 10 rules of warn-size.btm ({len(rules)})', len(rules) == 10):
        fail('Byteman rules not loaded')
    jvm = open(f'/proc/{pid_of()}/cmdline').read().replace('\0', ' ')
    flags = [t for t in jvm.split() if t.startswith(('-Xm', '-javaagent', '-Dstage4', '-Xbootclasspath', '-XX:+Use', '-Xlog', '-Dcassandra.jmx'))]
    note(f'[{life}] jvm: ' + ' '.join(flags))
    if not expect(f'[{life}] heap -Xms2G -Xmx2G (B3a)', '-Xms2G' in jvm.split() and '-Xmx2G' in jvm.split()):
        fail('heap is not 2G')
    rc, out = sh(f'bin/cqlsh {ADDR} 9042 -e "CREATE KEYSPACE ks WITH replication = '
                 "{'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE ks.t (k int, c int, v blob, PRIMARY KEY (k, c)) "
                 "WITH compaction = {'class':'SizeTieredCompactionStrategy','enabled':'false'};\"", check=False, timeout=120)
    if rc != 0:
        fail('schema: ' + out[-400:])
    sh(f'bin/nodetool -h 127.0.0.1 -p {JMX} disableautocompaction ks t', check=False)
    note(f'[{life}] schema: ks (RF 1), ks.t (k int, c int, v blob, PRIMARY KEY (k, c)), autocompaction off')
    n0 = len(trace_lines())
    time.sleep(10)
    n1 = len(trace_lines())
    if not expect(f'[{life}] idle control: no trace line in 10 s with no batch ({n1 - n0} new, {n1} in all)', n1 == n0):
        fail('trace lines appear with no batch')
    kib = jmx_value(SS, 'BatchSizeWarnThresholdInKiB')
    fk = jmx_value(SS, 'BatchSizeFailureThreshold')
    note(f'[{life}] thresholds over JMX: warn {kib} KiB, fail {fk} KiB')
    return kib, fk


def set_warn(kib):
    out = jmx('setint', SS, 'BatchSizeWarnThresholdInKiB', str(kib))
    back = jmx_value(SS, 'BatchSizeWarnThresholdInKiB')
    if not expect(f'warn threshold set live to {kib} KiB, read back {back} KiB', back == kib):
        fail('threshold did not take: ' + out[-300:])


def phase(life, name, typ, parts, count, key_base=0):
    w0 = jmx_value(WL, 'Count')
    stop = f'{D}/poll-{name}.stop'
    if os.path.exists(stop):
        os.remove(stop)
    pf = open(f'{D}/poll-{name}.csv', 'w')
    poll = subprocess.Popen(['java', '-cp', CLS, 'Jmx', str(JMX), 'poll', '100', '1000000', stop, 'java.lang:type=Memory', 'HeapMemoryUsage'],
                            stdout=pf, stderr=subprocess.STDOUT)
    time.sleep(1.5)
    cmd = (f'java {client_jvm_opts()} -Dlogback.configurationFile={HARNESS}/client-logback.xml -Xmx2g '
           f'-cp "{CLS}:{C}/build/classes/main:{C}/build/lib/jars/*:{C}/lib/*" org.apache.cassandra.transport.WarnBatches '
           f'--host {ADDR} --port 9042 --keyspace ks --table t --arm {name} --type {typ} --partitions {parts} --rows 1 '
           f'--value-bytes 1024 --count {count} --key-base {key_base} --random true')
    rc, out = sh(cmd, timeout=1800, check=False)
    open(stop, 'w').close()
    poll.wait(timeout=30)
    pf.close()
    lines = [l for l in out.splitlines() if l.startswith(('req ', 'arm '))]
    for l in lines:
        REQS.write(l + '\n')
    REQS.flush()
    nreq = sum(1 for l in lines if l.startswith('req '))
    if rc != 0 or nreq != count:
        fail(f'phase {name}: client rc={rc}, {nreq}/{count} req lines; client output: {out[-600:]}')
    sh(f'bin/nodetool -h 127.0.0.1 -p {JMX} flush ks t', check=False, timeout=300)
    time.sleep(2)
    _, du = sh(f'du -sb {DD}/data/data/ks', check=False, quiet=True)
    disk = int(du.split()[0]) if du.strip() else -1
    w1 = jmx_value(WL, 'Count')
    hp = [int(l.split(',')[1]) for l in open(f'{D}/poll-{name}.csv') if re.match(r'^\d+,\d+$', l.strip())]
    PHASES.writerow([name, life, disk, w0, w1, max(hp) if hp else -1])
    PHF.flush()
    oc = {}
    for l in lines:
        if l.startswith('req '):
            o = re.search(r'outcome=(\S+)', l).group(1)[:50]
            oc[o] = oc.get(o, 0) + 1
    note(f'PHASE [{life}] {name}: {count} x {typ} {parts} partitions; outcomes {oc}; writes {w0}->{w1}; data dir {disk} B; heap poll max {max(hp) if hp else -1}')


def main():
    if pid_of():
        fail('my CassandraDaemon is already running')
    _, desc = sh('git describe --tags && git rev-parse HEAD')
    md5 = sh(f'cd {HARNESS} && md5sum Alloc.java warn-size.btm WarnBatches.java Jmx.java cluster-run.py make-node-yaml.sh analyze.py')[1]
    note(f'cluster-run {RUN} {time.strftime("%F %T %Z")} host {os.uname().nodename} tree {" ".join(desc.split())} count1 {COUNT1}')
    note('harness md5 ' + ' '.join(f'{p[1]}={p[0][:12]}' for p in (l.split() for l in md5.splitlines()) if len(p) == 2))
    sh(f'rm -rf {CLS} {D}/alloc-classes && mkdir -p {CLS} {D}/alloc-classes')
    sh(f'javac -d {D}/alloc-classes {HARNESS}/Alloc.java && jar cf {D}/stage4-alloc.jar -C {D}/alloc-classes .')
    sh(f'javac -d {CLS} {HARNESS}/Jmx.java')
    sh(f'javac -nowarn -d {CLS} -cp "{C}/build/classes/main:{C}/build/lib/jars/*:{C}/lib/*" {HARNESS}/WarnBatches.java')
    if os.path.exists(TRACE):
        os.rename(TRACE, f'{TRACE}.{int(time.time())}')

    def twice(life):
        phase(life, f'{life}-W1a', 'LOGGED', 50, COUNT1)
        phase(life, f'{life}-W1b', 'LOGGED', 50, COUNT1, key_base=10_000_000)
        phase(life, f'{life}-W2a', 'UNLOGGED', 20480, 20, key_base=20_000_000)
        phase(life, f'{life}-W2b', 'UNLOGGED', 20480, 20, key_base=30_000_000)

    # ---- L1: warn 5KiB by yaml, then live to 90000KiB
    w, f = start_node('L1', ['batch_size_warn_threshold=5KiB', 'batch_size_fail_threshold=100000KiB'])
    expect(f'[L1] warn {w} KiB / fail {f} KiB as in the yaml (5 / 100000)', (w, f) == (5, 100000))
    twice('L1')
    set_warn(90000)
    phase('L1live', 'L1live-W1', 'LOGGED', 50, COUNT1, key_base=40_000_000)
    phase('L1live', 'L1live-W2', 'UNLOGGED', 20480, 20, key_base=50_000_000)
    sh(f'cp {BSN}/logs/system.log {D}/system-L1.log', check=False)
    stop_node()

    # ---- L2: warn 90000KiB by yaml
    w, f = start_node('L2', ['batch_size_warn_threshold=90000KiB', 'batch_size_fail_threshold=100000KiB'])
    expect(f'[L2] warn {w} KiB / fail {f} KiB as in the yaml (90000 / 100000)', (w, f) == (90000, 100000))
    twice('L2')
    sh(f'cp {BSN}/logs/system.log {D}/system-L2.log', check=False)
    stop_node()

    # ---- L3: the fail control and the inversion arm
    w, f = start_node('L3', ['batch_size_warn_threshold=5KiB', 'batch_size_fail_threshold=20KiB'])
    expect(f'[L3] warn {w} KiB / fail {f} KiB as in the yaml (5 / 20)', (w, f) == (5, 20))
    phase('L3', 'L3-ctl', 'LOGGED', 50, COUNT1)
    set_warn(200)
    phase('L3', 'L3-inv', 'LOGGED', 50, 200, key_base=60_000_000)
    sh(f'cp {BSN}/logs/system.log {D}/system-L3.log', check=False)
    stop_node()
    if pid_of():
        note('WARNING: my CassandraDaemon is still running after the run')
    else:
        note('no CassandraDaemon of mine left running')
    sh(f'rm -rf {DD}', check=False)
    traces = sorted(f for f in os.listdir(D) if f.startswith('warn-size.trace'))
    sh('cat ' + ' '.join(f'{D}/{f}' for f in traces) + f' > {D}/trace-all.txt')
    _, an = sh(f'python3 {HARNESS}/analyze.py cluster {D}', check=False)
    note(an)


if __name__ == '__main__':
    try:
        main()
    except SystemExit:
        raise
    except BaseException as e:
        fail(f'{type(e).__name__}: {e}')
