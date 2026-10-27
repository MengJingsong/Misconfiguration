#!/usr/bin/env python3
"""Stage 4, cluster tier (B3 + B3i) of max-unsigned-short-prepare-boundTerms--autonomous.
usage: cluster-run.py <run-name> <cache-MiB> <M>      one node lifetime for one (cache size, marker count) pair: wipe, start, load, stop
       cluster-run.py <run-name> down                 stop the node of this slot (by recorded PID) and remove the tmpfs directory
Phases: start + knob read-back (log "Initialized prepared statement caches with N MiB"); schema; baseline histogram; 10-repeat control (adds <= 1 entry);
load of distinct M-marker PREPAREs with a sample every 5 s and the stop rule of B3i.2; 70 s settle (past one scheduled-warning period); final histogram;
[M = 65535 only: one 65536-marker PREPARE]; rows of system.prepared_statements; stop.
Port slot 3: 127.0.3.1, JMX 7130, native 9042 on that address. Node data on tmpfs /dev/shm/s4-b9-bt/node. Tree $CASSANDRA_HOME (default ~/s4-b9-bt/c).
Output: ~/s4-b9-bt-logs/<run>/cluster/c<MiB>-m<M>/ (summary.txt with EXPECTED lines, samples.csv, histo-*.txt, session.log, system.log copy).
Exit 1 if a set-up or first-trigger check fails; the node is stopped on any exit."""
import atexit, csv, os, re, shutil, subprocess, sys, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/s4-b9-bt/c')
HARNESS = os.path.dirname(os.path.abspath(__file__))
W = '/dev/shm/s4-b9-bt/node'
ADDR, JMX = '127.0.3.1', 7130
RUN = sys.argv[1]; ARG = sys.argv[2]
MIB = 1 << 20
RATE = {10: 800, 1000: 800, 65535: 100}
LIMIT = {10: 150000, 1000: 20000, 65535: 400}
SAMPLE_S = 5.0
BEAN_CNT = 'org.apache.cassandra.metrics:type=CQL,name=PreparedStatementsCount'
BEAN_EV = 'org.apache.cassandra.metrics:type=CQL,name=PreparedStatementsEvicted'
BEAN_MT = 'org.apache.cassandra.metrics:type=Table,keyspace=system,scope=prepared_statements,name=AllMemtablesHeapSize'
PID = [None]
if ARG == 'down':
    LOGS = f'{HOME}/s4-b9-bt-logs/{RUN}/cluster/down'
else:
    cap_mib, M = int(ARG), int(sys.argv[3]); LOGS = f'{HOME}/s4-b9-bt-logs/{RUN}/cluster/c{cap_mib}-m{M}'
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a'); SUMMARY = open(LOGS + '/summary.txt', 'a')
JMXC = f'{HOME}/s4-b9-bt-logs/jmxc'


def log(s):
    SESSION.write(f'[{time.strftime("%F %T")}] {s}\n'); SESSION.flush()


def note(s):
    print(s, flush=True); SUMMARY.write(s + '\n'); SUMMARY.flush(); log(s)


def sh(cmd, timeout=900, check=True, env=None, cwd=C, quiet=False):
    log('+ ' + cmd)
    try:
        r = subprocess.run(['bash', '-c', 'ulimit -n 100000; ' + cmd], capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        log('  TIMEOUT')
        if check:
            raise RuntimeError('timeout: ' + cmd)
        return 124, ''
    out = (r.stdout or '') + (r.stderr or '')
    if not quiet:
        SESSION.write(out[-3000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'rc={r.returncode}: {cmd}\n{out[-800:]}')
    return r.returncode, out


def expect(desc, cond, detail=''):
    note(f'EXPECTED: {desc} - {"yes" if cond else "NO (recorded; judged in the results file)"}' + (f' [{detail}]' if detail else ''))
    return cond


def my_pid():
    """PID of this slot's daemon: the recorded pid file, accepted only if that process is a CassandraDaemon started with our log dir"""
    try:
        p = int(open(W + '/cassandra.pid').read().strip())
        cmd = open(f'/proc/{p}/cmdline').read().replace('\0', ' ')
        return p if 'CassandraDaemon' in cmd and W in cmd else None
    except (OSError, ValueError):
        return None


def nodetool(cmd, timeout=180):
    return sh(f'bin/nodetool -h 127.0.0.1 -p {JMX} {cmd}', timeout=timeout, check=False, quiet=True)[1]


def stop_node():
    p = my_pid()
    if p is None:
        return
    PID[0] = p
    nodetool('stopdaemon')
    for _ in range(90):
        if not os.path.exists(f'/proc/{p}'):
            return
        time.sleep(1)
    note(f'kill -9 {p}')
    subprocess.run(['kill', '-9', str(p)]); time.sleep(3)


def fail(msg):
    note('FAIL: ' + msg)
    stop_node()
    sys.exit(1)


atexit.register(stop_node)


def make_conf(mib):
    shutil.rmtree(W, ignore_errors=True)
    for d in ('logs', 'data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw'):
        os.makedirs(f'{W}/{d}', exist_ok=True)
    shutil.copytree(C + '/conf', W + '/conf')
    env = open(W + '/conf/cassandra-env.sh').read()
    env2 = env.replace('JMX_PORT="7199"', f'JMX_PORT="{JMX}"')
    assert env2 != env
    open(W + '/conf/cassandra-env.sh', 'w').write(env2)
    add = {'cluster_name': 'bt', 'num_tokens': '16', 'endpoint_snitch': 'SimpleSnitch', 'listen_address': ADDR, 'rpc_address': ADDR,
           'commitlog_directory': W + '/commitlog', 'hints_directory': W + '/hints', 'saved_caches_directory': W + '/saved_caches',
           'cdc_raw_directory': W + '/cdc_raw', 'auto_snapshot': 'false', 'prepared_statements_cache_size': f'{mib}MiB'}
    lines = open(C + '/conf/cassandra.yaml').read().splitlines()
    keys = set(add) | {'seed_provider', 'data_file_directories'}
    out, skip = [], False
    for l in lines:
        m = re.match(r'^([A-Za-z_]+):', l)
        if m:
            skip = m.group(1) in keys
            if skip:
                continue
        elif skip and (l.startswith((' ', '\t', '-')) or not l.strip() or l.lstrip().startswith('#')):
            continue
        else:
            skip = False
        out.append(l)
    tail = [f'{k}: {v}' for k, v in add.items()]
    tail += ['seed_provider:', '  - class_name: org.apache.cassandra.locator.SimpleSeedProvider', '    parameters:',
             f'      - seeds: "{ADDR}:7000"', 'data_file_directories:', f'    - {W}/data']
    open(W + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 bt lines ----\n' + '\n'.join(tail) + '\n')
    note('yaml tail: ' + '; '.join(t for t in tail if not t.startswith(('  ', 'seed', 'data_file'))))


def start_node():
    if my_pid() is not None:
        fail('node already running')
    env = dict(os.environ, CASSANDRA_CONF=W + '/conf', CASSANDRA_LOG_DIR=W + '/logs', MAX_HEAP_SIZE='2G')
    env.pop('JVM_EXTRA_OPTS', None); env.pop('HEAP_NEWSIZE', None)
    sh(f'bin/cassandra -p {W}/cassandra.pid > {W}/stdout.txt 2>&1', env=env)
    for _ in range(30):
        time.sleep(1)
        if my_pid() is not None:
            break
    else:
        fail('node did not start; see ' + W + '/stdout.txt')
    t0 = time.time()
    while time.time() - t0 < 300:
        if my_pid() is None:
            fail('node died during start')
        st = nodetool('status'); sb = nodetool('statusbinary')
        if re.search(r'^UN\s', st, re.M) and re.search(r'^running\s*$', sb, re.M):
            log(f'UN and serving after {time.time() - t0:.0f} s')
            return
        time.sleep(3)
    fail('not UN within 300 s')


def jmx(*pairs):
    _, o = sh(f'java -cp {JMXC} Jmx {JMX} get ' + ' '.join(pairs), check=False, quiet=True)
    res = {}
    for l in o.strip().splitlines():
        if '|' in l:
            b, a, v = l.split('|', 2); res[b.split('name=')[-1]] = v
    return res


def counters():
    r = jmx(BEAN_CNT, 'Value', BEAN_EV, 'Count', BEAN_MT, 'Value')
    g = lambda k: int(float(r.get(k, 'nan'))) if re.match(r'^[0-9.eE+]+$', r.get(k, '')) else -1
    return g('PreparedStatementsCount'), g('PreparedStatementsEvicted'), g('AllMemtablesHeapSize')


def histo(tag):
    p = my_pid(); f = f'{LOGS}/histo-{tag}.txt'
    sh(f'jmap -histo:live {p} > {f}', timeout=600)
    txt = open(f).read()
    tot = re.search(r'^Total\s+(\d+)\s+(\d+)', txt, re.M)
    prep = re.search(r'^\s*\d+:\s+(\d+)\s+(\d+)\s+org\.apache\.cassandra\.cql3\.QueryHandler\$Prepared\s*$', txt, re.M)
    spec = re.search(r'^\s*\d+:\s+(\d+)\s+(\d+)\s+org\.apache\.cassandra\.cql3\.ColumnSpecification\s*$', txt, re.M)
    sh(f'jcmd {p} GC.heap_info > {LOGS}/heapinfo-{tag}.txt', check=False)
    hi = re.search(r'garbage-first heap\s+total (\d+)K, used (\d+)K', open(f'{LOGS}/heapinfo-{tag}.txt').read())
    r = dict(live_bytes=int(tot.group(2)), live_objects=int(tot.group(1)), prepared_instances=int(prep.group(1)) if prep else 0,
             columnspec_instances=int(spec.group(1)) if spec else 0, heap_used_kb=int(hi.group(2)) if hi else -1)
    note(f'HISTO {tag} ' + ' '.join(f'{k}={v}' for k, v in r.items()))
    return r


def client(*a, timeout=7200):
    _, o = sh(f'python3 {HARNESS}/prep-load.py ' + ' '.join(map(str, a)), timeout=timeout, env=dict(os.environ, CASSANDRA_HOME=C, PSC_ADDR=ADDR), check=False)
    res = [l for l in o.splitlines() if l.startswith('RESULT')]
    note(res[-1] if res else 'RESULT missing: ' + o[-400:])
    return res[-1] if res else ''


if ARG == 'down':
    stop_node(); left = sh("ps -eo pid,args | grep '[C]assandraDaemon' | grep -F '" + W + "' || true", check=False, quiet=True)[1].strip()
    note('down: ' + (left or 'no daemon of this slot left')); shutil.rmtree('/dev/shm/s4-b9-bt', ignore_errors=True); sys.exit(0)

cap = cap_mib * MIB
note(f'=== run {RUN}: prepared_statements_cache_size {cap_mib} MiB (cap {cap} B), M = {M}, rate {RATE[M]}/s, limit {LIMIT[M]} offered, sample {SAMPLE_S}s')
if my_pid() is not None:
    fail('a daemon of this slot is already running')
if not os.path.exists(JMXC + '/Jmx.class'):
    os.makedirs(JMXC, exist_ok=True); sh(f'javac -d {JMXC} {HARNESS}/Jmx.java')
make_conf(cap_mib)
start_node()
syslog = open(W + '/logs/system.log', errors='replace').read()
m = re.search(r'Initialized prepared statement caches with (\d+) MiB', syslog)
expect(f'knob read-back "Initialized prepared statement caches with {cap_mib} MiB"', bool(m) and int(m.group(1)) == cap_mib, f'log says {m.group(1) if m else "nothing"}')
if not m or int(m.group(1)) != cap_mib:
    fail('knob read-back did not match')
if not client('setup').startswith('RESULT setup ok'):
    fail('schema step failed')
H0 = histo('0-baseline')
c0 = counters(); note(f'COUNTERS baseline count={c0[0]} evicted={c0[1]} memtable_heap={c0[2]}')
before = counters()[0]; client('dup', 10, 10); after = counters()[0]
expect('10 repeats of one statement add at most one cache entry', after - before <= 1, f'count {before} -> {after}')
# the 65536 boundary is tried first in the M = 65535 arms (first-trigger check): it must be rejected with the exact text
if M == 65535:
    cb = counters()[0]; r = client('boundary', 65536); ca = counters()[0]
    ok = 'Too many markers(?). 65536 markers exceed the allowed maximum of 65535' in r and 'rejected' in r and ca == cb
    expect('65536-marker PREPARE rejected with "Too many markers(?). 65536 markers exceed the allowed maximum of 65535" and the count unchanged', ok, f'count {cb} -> {ca}')
    if not ok:
        fail('first-trigger check (65536 rejection) failed')
stopf = W + '/stop-load'
if os.path.exists(stopf):
    os.remove(stopf)
smp = csv.writer(open(LOGS + '/samples.csv', 'w', newline='')); smp.writerow(['t_s', 'count', 'evicted', 'memtable_heap_bytes'])
ev_base = counters()[1]
p = subprocess.Popen(f'python3 {HARNESS}/prep-load.py load {M} {LIMIT[M]} {RATE[M]} {stopf}', shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                     env=dict(os.environ, CASSANDRA_HOME=C, PSC_ADDR=ADDR))
t0 = time.time(); hist = []; stop_met = None
while p.poll() is None:
    time.sleep(SAMPLE_S)
    cnt, ev, mt = counters(); hist.append(cnt)
    smp.writerow([round(time.time() - t0, 1), cnt, ev - ev_base, mt]); log(f'sample count={cnt} evicted={ev - ev_base} memtable_heap={mt}')
    last = hist[-4:]
    if stop_met is None and len(last) == 4 and cnt > 0 and ev - ev_base >= 3 * cnt and (max(last) - min(last)) <= 0.01 * max(last):
        stop_met = time.time() - t0; open(stopf, 'w').close(); note(f'STOP RULE met at {stop_met:.0f}s: evicted={ev - ev_base} >= 3 x count={cnt}; last 4 counts {min(last)}..{max(last)}')
out = p.communicate()[0]
res = [l for l in out.splitlines() if l.startswith('RESULT')]
note(res[-1] if res else 'RESULT missing: ' + out[-400:])
note(f'LOAD END stop_rule_met={stop_met is not None}')
time.sleep(70)
cnt, ev, mt = counters(); ev -= ev_base
note(f'COUNTERS final count={cnt} evicted={ev} memtable_heap={mt}')
H1 = histo('2-after-load')
note(f'HEAP DELTA live_bytes={H1["live_bytes"] - H0["live_bytes"]} prepared_instances={H1["prepared_instances"]} (baseline {H0["prepared_instances"]}); memtable_heap={mt}; delta_minus_memtable={H1["live_bytes"] - H0["live_bytes"] - mt}')
client('rows')
logtxt = open(W + '/logs/system.log', errors='replace').read()
warn = [l for l in logtxt.splitlines() if 'prepared statements discarded in the last minute' in l]
note(f'LOG discard-warnings={len(warn)}' + (' first: ' + warn[0][-140:] if warn else ''))
errs = [l for l in logtxt.splitlines() if l.startswith(('ERROR', 'WARN')) and 'discarded' not in l]
note(f'LOG other ERROR/WARN lines={len(errs)}' + (' first: ' + errs[0][:200] if errs else ''))
shutil.copy(W + '/logs/system.log', LOGS + '/system.log')
stop_node()
left = sh("ps -eo pid,args | grep '[C]assandraDaemon' | grep -F '" + W + "' || true", check=False, quiet=True)[1].strip()
note('STOPPED: ' + (left or 'no daemon of this slot left'))
