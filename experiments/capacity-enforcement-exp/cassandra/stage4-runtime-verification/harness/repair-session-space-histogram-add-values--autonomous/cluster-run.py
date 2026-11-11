#!/usr/bin/env python3
"""Cluster tier driver for repair-session-space-histogram-add-values--autonomous (B3e as amended 2026-10-26).
Two nodes on ONE host (pc12, environment deviation): node 1 127.0.2.1 (JMX 7120, native 9042), node 2 127.0.2.2 (JMX 7121, native off), storage port 7000,
tree ~/s4-b7-hv/c509 (copy-source.sh + ant build-test; ant is never run here), node data on tmpfs /dev/shm/s4-b7-hv, logs in ~/s4-b7-hv-logs/cluster/<RUN>/.
usage: cluster-run.py all                  setup + the five runs + the repeat of run 1, nodes stopped at the end and on any exit
       cluster-run.py resume                 (start existing data dirs, then the same runs as `all`, then stop)
       cluster-run.py setup | start | stop  (setup wipes and loads, leaves the nodes up; start restarts the existing data dirs; stop kills only the recorded PIDs)
       cluster-run.py run <label> <S> <D> <DEBUG|INFO>      one repair on the running nodes
Run list of `all` (B3e step 2-6): r1 (S=700 D=20 DEBUG), r2 (INFO), r3 (S=64), r4 (S=8), r5 (S=700 D=12), r1b (repeat of r1).
Per run: log level, S and D set on both nodes (JMX) and read back, JFR recording on both nodes around `repair -full -pr keyspace1 standard1` on node 1,
jstat -gc samples, debug.log lines of the window. Output per run: <LOGS>/<RUN>/<label>/ (summary.txt = EXPECTED lines and readings).
First-trigger check: r1 must show HistogramBuilder.add allocations in the JFR of at least one node and a 'Created ... merkle trees' line; otherwise the driver stops.
Nothing here judges a result beyond the EXPECTED lines; cluster-analyze.py re-parses the raw files and the AI judges."""
import json, os, re, resource, subprocess, sys, time, glob

HARNESS = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser('~')
C = HOME + '/s4-b7-hv/c509'
ROOT = '/dev/shm/s4-b7-hv'
RUN = os.environ.get('HV_RUN', 'run1')
LOGS = f'{HOME}/s4-b7-hv-logs/cluster/{RUN}'
os.makedirs(LOGS, exist_ok=True)
NODES = {1: dict(ip='127.0.2.1', jmx=7120), 2: dict(ip='127.0.2.2', jmx=7121)}
PORTS = [(n['ip'], 7000) for n in NODES.values()] + [('127.0.2.1', 9042)] + [('127.0.0.1', n['jmx']) for n in NODES.values()]
resource.setrlimit(resource.RLIMIT_NOFILE, (100000, 100000))
JVM_EXTRA = '-XX:-ResizeTLAB -XX:TLABSize=16k -XX:FlightRecorderOptions=stackdepth=16,threadbuffersize=1M,globalbuffersize=64M,numglobalbuffers=8,memorysize=512M -Xlog:gc*:file={root}/n{i}/gc.log:time,uptime'
SESSION = open(LOGS + '/session.log', 'a')
SUMMARY = None
PIDS = {}

def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'; print(line, file=sys.stderr, flush=True); SESSION.write(line + '\n'); SESSION.flush()
def note(s):
    print(s, flush=True); (SUMMARY or SESSION).write(s + '\n'); (SUMMARY or SESSION).flush(); log(s)
def sh(cmd, timeout=600, check=True, env=None, cwd=None):
    log('+ ' + cmd)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env or os.environ, cwd=cwd or C)
    out = (r.stdout or '') + (r.stderr or '')
    SESSION.write(out[-3000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed rc={r.returncode}: {cmd}\n{out[-600:]}')
    return r.returncode, out
def nt(i, args, **kw):
    return sh(f'bin/nodetool -h 127.0.0.1 -p {NODES[i]["jmx"]} {args}', **kw)
def node_dir(i): return f'{ROOT}/n{i}'
def ports_busy():
    _, o = sh("ss -ltn | awk '{print $4}'", check=False)
    return [f'{a}:{p}' for a, p in PORTS if re.search(r'%s:%d$' % (re.escape(a), p), o, re.M)]
def alive(pid): return bool(pid) and os.path.exists(f'/proc/{pid}')
def read_pid(i):
    try: return int(open(node_dir(i) + '/pid').read().strip())
    except Exception: return None
def own(pid, i):
    try: return node_dir(i) + '/conf' in open(f'/proc/{pid}/cmdline').read()
    except OSError: return False
def stop_nodes():
    for i in (2, 1):
        pid = PIDS.get(i) or read_pid(i)
        if pid and alive(pid) and own(pid, i):
            log(f'stopping node {i} pid {pid}')
            subprocess.run(['kill', str(pid)])
            for _ in range(120):
                if not alive(pid): break
                time.sleep(1)
            if alive(pid):
                log(f'kill -9 {pid}'); subprocess.run(['kill', '-9', str(pid)]); time.sleep(3)
def finish(rc):
    stop_nodes()
    left = [i for i in (1, 2) if alive(PIDS.get(i) or read_pid(i)) and own(PIDS.get(i) or read_pid(i), i)]
    note(f'nodes stopped; our nodes still alive: {left}; ports still busy: {ports_busy()}')
    sys.exit(rc)
def fail(msg):
    note('FAIL: ' + msg); finish(1)

def start_node(i):
    env = dict(os.environ, CASSANDRA_CONF=f'{node_dir(i)}/conf', CASSANDRA_LOG_DIR=f'{node_dir(i)}/logs', CASSANDRA_HOME=C,
               MAX_HEAP_SIZE='3G', JVM_EXTRA_OPTS=JVM_EXTRA.format(root=ROOT, i=i))
    os.makedirs(node_dir(i) + '/logs', exist_ok=True)
    cmd = f'( setsid nohup bin/cassandra -p {node_dir(i)}/pid > {node_dir(i)}/stdout.log 2>&1 < /dev/null & )'
    sh(cmd, env=env)
    for _ in range(60):
        time.sleep(1)
        pid = read_pid(i)
        if pid and alive(pid): PIDS[i] = pid; break
    log(f'node {i} pid {PIDS.get(i)}')
def wait_up(timeout=420):
    t0 = time.time()
    while time.time() - t0 < timeout:
        for i in (1, 2):
            if not alive(PIDS.get(i)): fail(f'node {i} died during start (see {node_dir(i)}/logs/system.log)')
        rc, st = nt(1, 'status', check=False, timeout=60)
        rc2, sb = nt(1, 'statusbinary', check=False, timeout=60)
        if len(re.findall(r'^UN ', st, re.M)) == 2 and re.search(r'^running', sb.strip(), re.M): return True
        time.sleep(5)
    return False
def jmx_get(i, bean, attr):
    _, o = nt(i, f'sjk mx -mg -b {bean} -f {attr}', check=False, timeout=120)
    m = re.findall(r'-?\d+', o.strip().splitlines()[-1] if o.strip() else '')
    return int(m[-1]) if m else None
def jmx_set(i, bean, attr, v):
    nt(i, f'sjk mx -ms -b {bean} -f {attr} -v {v}', timeout=120)
AR = 'org.apache.cassandra.db:type=RepairService'
SS = 'org.apache.cassandra.db:type=StorageService'

def setup():
    busy = ports_busy()
    if busy: fail(f'ports busy before start: {busy}')
    sh(f'rm -rf {ROOT}', check=False)
    for i in (1, 2):
        sh(f'bash {HARNESS}/make-node-yaml.sh {C} {node_dir(i)} {i}')
    start_node(1); time.sleep(20); start_node(2)
    if not wait_up(): fail('nodes did not reach UN UN + native running')
    note('setup: both nodes UN, native running on 127.0.2.1')
    _, o = sh('tools/bin/cassandra-stress write n=2000000 cl=ONE -schema "replication(factor=2)" -rate threads=32 -node 127.0.2.1 -mode native cql3 protocolVersion=4', timeout=3000)
    open(LOGS + '/stress-load.txt', 'w').write(o[-3000:])
    note('stress: ' + '; '.join(l.strip() for l in o.splitlines() if re.search(r'Total errors|Total partitions|Op rate', l)))
    for i in (1, 2):
        nt(i, 'flush'); nt(i, 'compact keyspace1 standard1', timeout=1800)
        _, ts = nt(i, 'tablestats keyspace1.standard1', check=False)
        open(f'{LOGS}/tablestats-n{i}.txt', 'w').write(ts)
        note(f'node {i}: ' + '; '.join(l.strip() for l in ts.splitlines() if re.search(r'SSTable count|Number of partitions|Space used \(live\)', l)))
    sh(f'df -h /dev/shm | tail -1', check=False)

def jfr_sizes(path):
    rc, o = sh(f'python3 {HARNESS}/jfr-sizes.py {path}', check=False, timeout=900)
    return o

def run(label, S, D, level, first=False):
    global SUMMARY
    d = f'{LOGS}/{label}'; os.makedirs(d, exist_ok=True); SUMMARY = open(d + '/summary.txt', 'a')
    note(f'== run {label}: S={S} MiB, D={D}, level={level}, {time.strftime("%FT%TZ", time.gmtime())}')
    for i in (1, 2):
        nt(i, f'setlogginglevel org.apache.cassandra {level}')
        jmx_set(i, AR, 'RepairSessionSpaceInMiB', S)
        jmx_set(i, SS, 'RepairSessionMaxTreeDepth', D)
        gs, gd = jmx_get(i, AR, 'RepairSessionSpaceInMiB'), jmx_get(i, SS, 'RepairSessionMaxTreeDepth')
        note(f'EXPECTED: node {i} RepairSessionSpaceInMiB={S} and RepairSessionMaxTreeDepth={D} read back -- {"yes" if (gs, gd) == (S, D) else "NO read " + str((gs, gd))}')
        if (gs, gd) != (S, D): fail('could not set the knobs by JMX')
    _, lv = nt(1, 'getlogginglevels', check=False)
    note('log level org.apache.cassandra: ' + ' '.join(l.split() [-1] for l in lv.splitlines() if re.match(r'\s*org.apache.cassandra\s', l)))
    offs = {i: os.path.getsize(f'{node_dir(i)}/logs/debug.log') for i in (1, 2)}
    time.sleep(5)
    samplers = []
    for i in (1, 2):
        sh(f'jcmd {PIDS[i]} JFR.start name={label} settings=profile', check=True)
        samplers.append(subprocess.Popen(f'exec jstat -gc {PIDS[i]} 500 > {d}/jstat-n{i}.txt', shell=True))
    t0 = int(time.time() * 1000)
    rc, out = nt(1, 'repair -full -pr keyspace1 standard1', check=False, timeout=3000)
    t1 = int(time.time() * 1000)
    time.sleep(3)
    for p in samplers: p.terminate()
    for i in (1, 2):
        sh(f'jcmd {PIDS[i]} JFR.stop name={label} filename={d}/n{i}.jfr', check=True)
    open(d + '/repair-output.txt', 'w').write(out[-4000:])
    note(f'repair rc={rc} wall_ms={t1 - t0} t0_ms={t0}; completed: {"yes" if "Repair completed successfully" in out or "finished" in out.lower() else "NOT SEEN"}; ' + out.strip().splitlines()[-1][:160])
    if rc != 0: fail(f'repair failed in {label}')
    created = {}
    for i in (1, 2):
        data = open(f'{node_dir(i)}/logs/debug.log', 'rb').read()[offs[i]:].decode(errors='replace')
        keep = [l for l in data.splitlines() if re.search(r'merkle trees|Partitions per leaf|Partition sizes are|Validated \d+ partitions|EstimatedHistogram\.java', l)]
        open(f'{d}/debuglog-n{i}.txt', 'w').write('\n'.join(keep) + '\n')
        created[i] = [l for l in keep if 'Created' in l and 'merkle trees' in l]
        note(f'node {i} debug.log window: {len(keep)} relevant lines; Created-lines: {[re.sub(r"^.*Created", "Created", l) for l in created[i]]}; "Partitions per leaf" lines: {sum("Partitions per leaf" in l for l in keep)}')
        o = jfr_sizes(f'{d}/n{i}.jfr'); open(f'{d}/jfr-sizes-n{i}.txt', 'w').write(o)
        dist = [l.split()[1] for l in o.splitlines() if l.startswith('DISTINCT')]
        note(f'node {i} JFR: HistogramBuilder.add outside-TLAB sizes (distinct): {dist}; total outside-TLAB events {[l.split()[1] for l in o.splitlines() if l.startswith("TOTAL")]}')
    sh(f'cp {node_dir(1)}/logs/system.log {d}/system-n1.log; cp {node_dir(2)}/logs/system.log {d}/system-n2.log', check=False)
    SUMMARY.close(); SUMMARY = None
    return d

def first_trigger_check(d):
    hit = any(re.search(r'^DISTINCT', l) for i in (1, 2) for l in open(f'{d}/jfr-sizes-n{i}.txt'))
    made = any('Created' in l for i in (1, 2) for l in open(f'{d}/debuglog-n{i}.txt'))
    msg = f'EXPECTED: first trigger (r1, DEBUG): JFR shows HistogramBuilder.add arrays -- {"yes" if hit else "NO"}; debug.log has a Created-merkle-trees line -- {"yes" if made else "NO"}'
    note(msg); open(d + '/summary.txt', 'a').write(msg + '\n')
    if not (hit and made): fail('first-trigger check failed in r1 (instrument or path); stopping, no further runs')

PLAN = [('r1', 700, 20, 'DEBUG'), ('r2', 700, 20, 'INFO'), ('r3', 64, 20, 'DEBUG'), ('r4', 8, 20, 'DEBUG'), ('r5', 700, 12, 'DEBUG'), ('r1b', 700, 20, 'DEBUG')]

def main():
    cmd = sys.argv[1]
    try:
        if cmd == 'all':
            setup()
            for lab, S, D, lvl in PLAN:
                d = run(lab, S, D, lvl)
                if lab == 'r1': first_trigger_check(d)
            finish(0)
        elif cmd == 'resume':
            start_node(1); time.sleep(20); start_node(2)
            if not wait_up(): fail('nodes did not come back')
            note('resume: both nodes UN, native running')
            for lab, S, D, lvl in PLAN:
                d = run(lab, S, D, lvl)
                if lab == 'r1': first_trigger_check(d)
            finish(0)
        elif cmd == 'setup': setup()
        elif cmd == 'start':
            start_node(1); time.sleep(20); start_node(2)
            if not wait_up(): fail('nodes did not come back')
            note('start: both nodes UN, native running')
        elif cmd == 'run':
            for i in (1, 2): PIDS[i] = read_pid(i)
            run(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5])
        elif cmd == 'stop': finish(0)
    except SystemExit: raise
    except BaseException as e:
        note(f'ABORT: {type(e).__name__}: {e}'); finish(2)

if __name__ == '__main__':
    main()
