#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of monitoring_max_operations-operationsqueue_offer-maxoperations--autonomous.
usage: cluster-run.py seed                 shipped timeouts; cassandra-stress write n=200000; drain; stop; keep a data copy
       cluster-run.py run <N> <tag>        restore the copy, start with read_request_timeout 1ms + slow_query_log_timeout 1ms and
                                           -Dcassandra.monitoring_max_operations=<N> -Dcassandra.monitoring_report_interval_ms=600000,
                                           stress read for MON_DURATION s (default 240) at 1024 threads, histogram at baseline / 1/3 / 2/3 / end
       cluster-run.py down
Tree ~/s4-base. Node dir ~/s4-mon/node, seed copy ~/s4-mon/seed-data. Logs ~/stage4-logs/mon/cluster/<tag>/."""
import os, re, subprocess, sys, time

HOME = os.path.expanduser('~'); HARNESS = os.path.dirname(os.path.abspath(__file__)); tree = HOME + '/s4-base'
N = HOME + '/s4-mon/node'; SEED = HOME + '/s4-mon/seed-data'; JMXC = HOME + '/s4-mon/jmx'
DUR = int(os.environ.get('MON_DURATION', 240)); THREADS = int(os.environ.get('MON_THREADS', 1024))
cmd = sys.argv[1]; tag = sys.argv[3] if cmd == 'run' else cmd
LOGS = HOME + '/stage4-logs/mon/cluster/' + tag; os.makedirs(LOGS, exist_ok=True)
SUMMARY = open(LOGS + '/summary.txt', 'a')
CLS = {'FailedOperation': 'org.apache.cassandra.db.monitoring.MonitoringTask$FailedOperation',
       'SlowOperation': 'org.apache.cassandra.db.monitoring.MonitoringTask$SlowOperation',
       'SinglePartitionReadCommand': 'org.apache.cassandra.db.SinglePartitionReadCommand'}


def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush()


def sh(c, timeout=900, env=None, cwd=None):
    r = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd or tree)
    return r.returncode, (r.stdout or '') + (r.stderr or '')


def pid():
    try: return int(open(N + '/cassandra.pid').read().strip())
    except Exception: return None


def alive():
    p = pid(); return p is not None and os.path.exists(f'/proc/{p}')


def stop():
    if alive():
        sh('bin/nodetool stopdaemon', timeout=180)
        for _ in range(120):
            if not alive(): break
            time.sleep(1)
        if alive(): subprocess.run(['kill', '-9', str(pid())]); time.sleep(2)
    return sh("ps -eo cmd | grep '[C]assandraDaemon' || true")[1].strip()


def fail(m):
    note('FAIL: ' + m); stop(); sys.exit(1)


def start(mode, opts):
    sh(f'rm -rf {N}', cwd=HOME); os.makedirs(N)
    sh(f'mkdir -p {JMXC} && javac -d {JMXC} {HARNESS}/Jmx.java', cwd=HOME)
    note(sh(f'{HARNESS}/make-node-yaml.sh {tree} {N} {mode}')[1].strip().splitlines()[-1][:400])
    return opts


def boot(opts):
    env = dict(os.environ, CASSANDRA_CONF=N + '/conf', CASSANDRA_LOG_DIR=N + '/logs', MAX_HEAP_SIZE='1G')
    env.pop('HEAP_NEWSIZE', None); env.pop('JVM_EXTRA_OPTS', None)
    if opts: env['JVM_EXTRA_OPTS'] = opts
    sh(f'bin/cassandra -p {N}/cassandra.pid > {N}/stdout.txt 2>&1', env=env)
    lp = N + '/logs/system.log'
    for _ in range(300):
        time.sleep(2)
        if not alive(): fail('daemon died during start; see ' + N + '/stdout.txt')
        if os.path.exists(lp) and 'Starting listening for CQL clients' in open(lp, errors='replace').read(): break
    else: fail('no CQL listener')
    time.sleep(5)


def jmx(bean, attr):
    o = sh(f'java -cp {JMXC} Jmx 7199 get {bean} {attr}')[1].strip()
    return o.split('|')[-1]


def histo(t):
    p = pid(); f = f'{LOGS}/histo-{t}.txt'; sh(f'jmap -histo:live {p} > {f}', timeout=300)
    h = open(f).read(); tot = re.search(r'^Total\s+(\d+)\s+(\d+)', h, re.M); r = {'live_bytes': int(tot.group(2))}
    for k, c in CLS.items():
        m = re.search(r'^\s*\d+:\s+(\d+)\s+(\d+)\s+' + re.escape(c) + r'\s*$', h, re.M)
        r[k] = int(m.group(1)) if m else 0; r[k + '_bytes'] = int(m.group(2)) if m else 0
    to = jmx('org.apache.cassandra.metrics:type=ClientRequest,scope=Read,name=Timeouts', 'Count')
    note(f'HISTO {t} ' + ' '.join(f'{k}={v}' for k, v in r.items()) + f' coordinator_read_timeouts={to}')
    return r


if cmd == 'down':
    note('down: ' + (stop() or 'no CassandraDaemon left')); sys.exit(0)
if stop(): fail('a CassandraDaemon is already running')
if cmd == 'seed':
    start('slow', ''); boot('')
    rc, o = sh('tools/bin/cassandra-stress write n=200000 -rate threads=64 -node 127.0.0.1', timeout=1800)
    open(LOGS + '/stress-write.txt', 'w').write(o); note('STRESS write rc=%d %s' % (rc, ' | '.join(l for l in o.splitlines() if 'Total errors' in l or 'Total partitions' in l)))
    sh('bin/nodetool flush; bin/nodetool drain', timeout=600); note('STOPPED: ' + (stop() or 'no CassandraDaemon left'))
    note(sh(f'rm -rf {SEED} && mkdir -p {SEED} && cp -a {N}/data {N}/commitlog {SEED}/ && du -sb {SEED}', cwd=HOME)[1].strip()); sys.exit(0)
Nv = sys.argv[2]; note(f'=== {tag}: monitoring_max_operations={Nv}, duration {DUR}s, threads {THREADS}')
opts = f'-Dcassandra.monitoring_max_operations={Nv} -Dcassandra.monitoring_report_interval_ms=600000'
start('fast', opts); sh(f'rm -rf {N}/data {N}/commitlog && cp -a {SEED}/data {SEED}/commitlog {N}/', cwd=HOME)
boot(opts)
cl = open(f'/proc/{pid()}/cmdline').read().replace('\0', ' ')
m = re.search(r'-Dcassandra.monitoring_max_operations=(\S+)', cl); note(f'READBACK jvm property: {m.group(1) if m else None}')
if not m or m.group(1) != Nv: fail('read-back mismatch')
y = open(N + '/conf/cassandra.yaml').read(); note('READBACK yaml: ' + ' '.join(re.findall(r'^(read_request_timeout: \S+|slow_query_log_timeout: \S+)', y, re.M)))
H = [histo('0-baseline')]
sp = subprocess.Popen(f'tools/bin/cassandra-stress read duration={DUR}s cl=ONE no-warmup -pop "dist=UNIFORM(1..200000)" -rate threads={THREADS} -errors ignore -node 127.0.0.1 > {LOGS}/stress-read.txt 2>&1', shell=True, cwd=tree)
t0 = time.time()
for i, frac in enumerate((1 / 3, 2 / 3), 1):
    time.sleep(max(0, t0 + frac * DUR - time.time())); H.append(histo(f'{i}-t{int(frac * DUR)}s'))
sp.wait(); time.sleep(3); H.append(histo('3-after-stress'))
syslog = open(N + '/logs/system.log', errors='replace').read()
note('DRAIN-WARN lines (Some operations timed out / were slow)=%d' % len(re.findall(r'Some operations (timed out|were slow)', syslog)))
mm = re.search(r'Scheduling monitoring task with report interval of (\d+) ms, max operations (-?\d+)', syslog); note('LOG ' + (mm.group(0) if mm else 'no scheduling line'))
st = open(LOGS + '/stress-read.txt', errors='replace').read(); note('STRESS read: ' + ' | '.join(l.strip() for l in st.splitlines() if re.match(r'\s*(Op rate|Total errors|Total partitions|Running time)', l)))
note('STOPPED: ' + (stop() or 'no CassandraDaemon left'))
