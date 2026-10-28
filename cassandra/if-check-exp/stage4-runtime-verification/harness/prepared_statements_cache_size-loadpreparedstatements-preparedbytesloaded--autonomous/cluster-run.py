#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of prepared_statements_cache_size-loadpreparedstatements-preparedbytesloaded--autonomous.
usage: cluster-run.py seed [M]                   start arm A at 64 MiB, PREPARE M distinct statements (nothing evicted), drain, stop, keep a data copy
       cluster-run.py run <A|B> <MiB> <tag>      restore a fresh copy of the seeded data, start <arm> at <MiB>, read the preload line, wait, GC + readings, stop
       cluster-run.py down                       stop any node this script started
Arm A = ~/s4-base, arm B = ~/s4-psc-b (1.1 -> 1000.0). Node dir ~/s4-pthr/node, seeded copy ~/s4-pthr/seed-data. Logs ~/stage4-logs/pthr/cluster/<tag>/.
Exit 1: a set-up or instrument check failed; the node is stopped."""
import os, re, subprocess, sys, time, shutil

HOME = os.path.expanduser('~'); HARNESS = os.path.dirname(os.path.abspath(__file__))
TREE = {'A': HOME + '/s4-base', 'B': HOME + '/s4-psc-b'}
N = HOME + '/s4-pthr/node'; SEED = HOME + '/s4-pthr/seed-data'; JMXC = HOME + '/s4-pthr/jmx'
MIB = 1 << 20; SETTLE = int(os.environ.get('PTHR_SETTLE', 60))
cmd = sys.argv[1]
tag = sys.argv[4] if cmd == 'run' else cmd
LOGS = HOME + '/stage4-logs/pthr/cluster/' + tag; os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a'); SUMMARY = open(LOGS + '/summary.txt', 'a')
BEAN_CNT = 'org.apache.cassandra.metrics:type=CQL,name=PreparedStatementsCount'
BEAN_EV = 'org.apache.cassandra.metrics:type=CQL,name=PreparedStatementsEvicted'
BEAN_MT = 'org.apache.cassandra.metrics:type=Table,keyspace=system,scope=prepared_statements,name=AllMemtablesHeapSize'
tree = None


def log(s):
    l = f'[{time.strftime("%F %T")}] {s}'; print(l, file=sys.stderr); SESSION.write(l + '\n'); SESSION.flush()


def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush(); log(s)


def sh(c, timeout=900, check=True, env=None, cwd=None, quiet=False):
    log('+ ' + c)
    r = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd or tree or HOME)
    out = (r.stdout or '') + (r.stderr or '')
    if not quiet:
        SESSION.write(out[-3000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'rc={r.returncode}: {c}\n{out[-800:]}')
    return r.returncode, out


def pid():
    try:
        return int(open(N + '/cassandra.pid').read().strip())
    except Exception:
        return None


def alive():
    p = pid()
    return p is not None and os.path.exists(f'/proc/{p}')


def stop_node():
    if alive():
        sh('bin/nodetool stopdaemon', check=False, timeout=180)
        for _ in range(120):
            if not alive():
                break
            time.sleep(1)
        if alive():
            subprocess.run(['kill', '-9', str(pid())]); time.sleep(2)
    _, o = sh("ps -eo cmd | grep '[C]assandraDaemon' || true", check=False, quiet=True)
    return o.strip()


def fail(m):
    note('FAIL: ' + m); stop_node(); sys.exit(1)


def jmx(*pairs):
    _, o = sh(f'java -cp {JMXC} Jmx 7199 get ' + ' '.join(pairs), check=False, quiet=True)
    res = {}
    for l in o.strip().splitlines():
        b, a, v = l.split('|', 2); res[b.split('name=')[-1] if 'name=' in b else b] = v
    return res


def counters():
    r = jmx(BEAN_CNT, 'Value', BEAN_EV, 'Count', BEAN_MT, 'Value')
    g = lambda k: int(float(r.get(k, 'nan'))) if re.match(r'^[0-9.eE+]+$', r.get(k, '')) else -1
    return g('PreparedStatementsCount'), g('PreparedStatementsEvicted'), g('AllMemtablesHeapSize')


def histo(t):
    p = pid(); f = f'{LOGS}/histo-{t}.txt'
    sh(f'jmap -histo:live {p} > {f}', timeout=300)
    txt = open(f).read()
    tot = re.search(r'^Total\s+(\d+)\s+(\d+)', txt, re.M)
    prep = re.search(r'^\s*\d+:\s+(\d+)\s+(\d+)\s+org\.apache\.cassandra\.cql3\.QueryHandler\$Prepared\s*$', txt, re.M)
    sh(f'jcmd {p} GC.heap_info > {LOGS}/heapinfo-{t}.txt', check=False)
    r = dict(live_bytes=int(tot.group(2)), live_objects=int(tot.group(1)),
             prepared_instances=int(prep.group(1)) if prep else 0, prepared_shallow=int(prep.group(2)) if prep else 0)
    note(f'HISTO {t} ' + ' '.join(f'{k}={v}' for k, v in r.items()))
    return r


def rows():
    _, o = sh(f"bin/cqlsh --request-timeout=300 127.0.0.1 -e \"SELECT count(*) FROM system.prepared_statements\" 2>&1 | grep -E '^ +[0-9]+ *$'", check=False, timeout=400, quiet=True)
    return ' '.join(o.split())


def client(*a, timeout=3600):
    _, o = sh(f'python3 {HARNESS}/prep-load.py ' + ' '.join(map(str, a)), timeout=timeout, env=dict(os.environ, CASSANDRA_HOME=tree), check=False)
    res = [l for l in o.splitlines() if l.startswith('RESULT')]
    note(res[-1] if res else 'RESULT missing: ' + o[-400:])
    return res[-1] if res else ''


def start_node():
    env = dict(os.environ, CASSANDRA_CONF=N + '/conf', CASSANDRA_LOG_DIR=N + '/logs', MAX_HEAP_SIZE='1G')
    env.pop('HEAP_NEWSIZE', None); env.pop('JVM_EXTRA_OPTS', None)
    lp = N + '/logs/system.log'
    off = os.path.getsize(lp) if os.path.exists(lp) else 0
    sh(f'bin/cassandra -p {N}/cassandra.pid > {N}/stdout.txt 2>&1', env=env)
    for _ in range(300):
        time.sleep(2)
        if not alive():
            fail('daemon died during start; see ' + N + '/stdout.txt')
        if os.path.exists(lp):
            with open(lp, errors='replace') as f:
                f.seek(off); txt = f.read()
            if 'Starting listening for CQL clients' in txt:
                break
    else:
        fail('node did not start listening for CQL')
    time.sleep(5)
    open(LOGS + '/system-log-this-start.txt', 'w').write(txt)
    return txt


def fresh(mib):
    left = stop_node()
    if left:
        fail('a CassandraDaemon is already running: ' + left[:200])
    sh(f'rm -rf {N}')
    os.makedirs(N)
    sh(f'mkdir -p {JMXC} && javac -d {JMXC} {HARNESS}/Jmx.java', cwd=HOME)
    y = sh(f'{HARNESS}/make-node-yaml.sh {tree} {mib} {N}')[1]; note(y.strip().splitlines()[-1][:500])


if cmd == 'down':
    tree = TREE['A']; note('down: ' + (stop_node() or 'no CassandraDaemon left')); sys.exit(0)
if cmd == 'seed':
    tree = TREE['A']; M = int(sys.argv[2]) if len(sys.argv) > 2 else 20000
    note(f'=== seed: arm A tree {tree} at 64 MiB, M={M}')
    fresh(64)
    syslog = start_node()
    m = re.search(r'Initialized prepared statement caches with (\d+) MiB', syslog)
    note(f'READBACK log: "Initialized prepared statement caches with {m.group(1) if m else "?"} MiB"')
    if not m or int(m.group(1)) != 64:
        fail('knob read-back did not match')
    client('setup')
    client('load', M, 2000, N + '/no-stop-file')
    time.sleep(10)
    c = counters(); note(f'COUNTERS count={c[0]} evicted={c[1]} memtable_heap={c[2]}')
    r = rows(); note(f'ROWS system.prepared_statements: {r}')
    if c[0] < M or c[1] != 0:
        fail(f'seed incomplete: count={c[0]} evicted={c[1]} M={M}')
    sh('bin/nodetool drain', timeout=300, check=False); left = stop_node(); note('STOPPED: ' + (left or 'no CassandraDaemon left'))
    sh(f'rm -rf {SEED} && mkdir -p {SEED} && cp -a {N}/data {N}/commitlog {SEED}/ && du -sb {SEED} | tee -a {LOGS}/summary.txt', cwd=HOME)
    sys.exit(0)
if cmd == 'run':
    arm, mib = sys.argv[2], int(sys.argv[3]); tree = TREE[arm]; cap = mib * MIB
    note(f'=== run {tag}: arm {arm} ({tree}) cap {mib} MiB ({cap} B), settle {SETTLE}s')
    fresh(mib)
    sh(f'rm -rf {N}/data {N}/commitlog && cp -a {SEED}/data {SEED}/commitlog {N}/', cwd=HOME)
    t_start = time.time()
    syslog = start_node()
    m = re.search(r'Initialized prepared statement caches with (\d+) MiB', syslog)
    note(f'READBACK log: "Initialized prepared statement caches with {m.group(1) if m else "?"} MiB"')
    if not m or int(m.group(1)) != mib:
        fail('knob read-back did not match')
    pre = re.findall(r'Preloaded (\d+) prepared statements in (\d+) ms', syslog)
    wn = [l for l in syslog.splitlines() if 'Detected prepared statement cache filling up' in l]
    note(f'PRELOAD lines={pre}; filling-up warnings={len(wn)}')
    for w in wn:
        note('WARN-LINE ' + w[:400])
    time.sleep(SETTLE)
    c = counters(); note(f'COUNTERS count={c[0]} evicted={c[1]} memtable_heap={c[2]}')
    H = histo('after-preload')
    note(f'ROWS system.prepared_statements: {rows()}')
    left = stop_node(); note('STOPPED: ' + (left or 'no CassandraDaemon left'))
