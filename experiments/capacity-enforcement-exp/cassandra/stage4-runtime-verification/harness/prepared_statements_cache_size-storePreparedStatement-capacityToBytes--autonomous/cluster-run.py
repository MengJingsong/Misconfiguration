#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of prepared_statements_cache_size-storePreparedStatement-capacityToBytes--autonomous.
usage: cluster-run.py <MiB> [restart]     one node lifetime for one knob value (wipe, start, work, stop)   |   cluster-run.py down
Phases: start + knob read-back; schema; baseline heap; plain-query control (B3h d); duplicate control (B3h a); PREPARE load (B3c)
with a sample every 30 s and the stop rule of B3c; settle; final heap; oversize PREPARE; [restart check, B3e 7]; stop.
Heap reading (B3d amendment): `jmap -histo:live` total bytes (forces a full GC) at the baseline, after the plain control and after
the load; instance count of QueryHandler$Prepared; GC.heap_info; and the memtable heap of system.prepared_statements (JMX), the
n-dependent consumer the cache does not hold.  Output: ~/stage4-logs/psc/cluster/k<MiB>/  (session.log, summary.txt, samples.csv, histo-*.txt)
Exit 1: an instrument or set-up check failed; the node is stopped."""
import csv, os, re, subprocess, sys, time

HOME = os.path.expanduser('~'); C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-run1')
HARNESS = os.path.dirname(os.path.abspath(__file__)); PSC = os.environ.get('PSC', HOME + '/stage4-psc')
JMXC = PSC + '/jmx'; MIB = 1 << 20
RATE = float(os.environ.get('PSC_RATE', 500)); MAXN = int(os.environ.get('PSC_MAXN', 200000)); PLAIN_N = int(os.environ.get('PSC_PLAIN', 20000))
SAMPLE_S = float(os.environ.get('PSC_SAMPLE', 30))
arg = sys.argv[1] if len(sys.argv) > 1 else ''
LOGS = os.environ.get('PSC_LOGS', HOME + '/stage4-logs/psc/cluster') + '/k' + (arg if arg != 'down' else 'down')
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a'); SUMMARY = open(LOGS + '/summary.txt', 'a')
BEAN_CNT = 'org.apache.cassandra.metrics:type=CQL,name=PreparedStatementsCount'
BEAN_EV = 'org.apache.cassandra.metrics:type=CQL,name=PreparedStatementsEvicted'
BEAN_MT = 'org.apache.cassandra.metrics:type=Table,keyspace=system,scope=prepared_statements,name=AllMemtablesHeapSize'


def log(s):
    l = f'[{time.strftime("%F %T")}] {s}'; print(l, file=sys.stderr); SESSION.write(l + '\n'); SESSION.flush()


def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush(); log(s)


def sh(cmd, timeout=900, check=True, env=None, cwd=C, quiet=False):
    log('+ ' + cmd)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
    out = (r.stdout or '') + (r.stderr or '')
    if not quiet:
        SESSION.write(out[-3000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'rc={r.returncode}: {cmd}\n{out[-800:]}')
    return r.returncode, out


def pid():
    try:
        return int(open(PSC + '/cassandra.pid').read().strip())
    except Exception:
        return None


def alive():
    p = pid()
    return p is not None and os.path.exists(f'/proc/{p}')


def stop_node():
    if alive():
        sh(f'bin/nodetool stopdaemon', check=False, timeout=180)
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


def histo(tag):
    p = pid(); f = f'{LOGS}/histo-{tag}.txt'
    sh(f'jmap -histo:live {p} > {f}', timeout=300)
    txt = open(f).read()
    tot = re.search(r'^Total\s+(\d+)\s+(\d+)', txt, re.M)
    prep = re.search(r'^\s*\d+:\s+(\d+)\s+(\d+)\s+org\.apache\.cassandra\.cql3\.QueryHandler\$Prepared\s*$', txt, re.M)
    sh(f'jcmd {p} GC.heap_info > {LOGS}/heapinfo-{tag}.txt', check=False)
    hi = re.search(r'garbage-first heap\s+total (\d+)K, used (\d+)K', open(f'{LOGS}/heapinfo-{tag}.txt').read())
    r = dict(live_bytes=int(tot.group(2)), live_objects=int(tot.group(1)),
             prepared_instances=int(prep.group(1)) if prep else 0, prepared_shallow=int(prep.group(2)) if prep else 0,
             heap_used_kb=int(hi.group(2)) if hi else -1)
    note(f'HISTO {tag} ' + ' '.join(f'{k}={v}' for k, v in r.items()))
    return r


def client(*a, timeout=3600):
    _, o = sh(f'python3 {HARNESS}/prep-load.py ' + ' '.join(map(str, a)), timeout=timeout, env=dict(os.environ, CASSANDRA_HOME=C), check=False)
    res = [l for l in o.splitlines() if l.startswith('RESULT')]
    note((res[-1] if res else 'RESULT missing: ' + o[-400:]))
    return res[-1] if res else ''


def start_node():
    sh(f'{HARNESS}/make-node-yaml.sh {mib}') if first_start else None
    env = dict(os.environ, CASSANDRA_CONF=PSC + '/conf', CASSANDRA_LOG_DIR=PSC + '/logs', MAX_HEAP_SIZE='2G')
    env.pop('HEAP_NEWSIZE', None); env.pop('JVM_EXTRA_OPTS', None)
    lp = PSC + '/logs/system.log'
    off = os.path.getsize(lp) if os.path.exists(lp) else 0     # only text written by THIS start counts
    sh(f'bin/cassandra -p {PSC}/cassandra.pid > {PSC}/stdout.txt 2>&1', env=env)
    for _ in range(240):
        time.sleep(2)
        if os.path.exists(lp):
            with open(lp, errors='replace') as f:
                f.seek(off); txt = f.read()
            if 'Starting listening for CQL clients' in txt:
                break
    else:
        fail('node did not start listening for CQL; see ' + PSC + '/stdout.txt')
    time.sleep(5)
    return txt


if arg == 'down':
    note('down: ' + (stop_node() or 'no CassandraDaemon left')); sys.exit(0)
mib = int(arg); first_start = True
restart = len(sys.argv) > 2 and sys.argv[2] == 'restart'
cap = mib * MIB
note(f'=== prepared_statements_cache_size {mib} MiB (cap {cap} B), rate {RATE}/s, max {MAXN} statements, sample {SAMPLE_S}s, restart check {restart}')
left = stop_node()
if left:
    fail('a CassandraDaemon is already running: ' + left[:200])
sh(f'rm -rf {PSC}/data {PSC}/commitlog {PSC}/saved_caches {PSC}/hints {PSC}/cdc_raw {PSC}/logs {PSC}/cassandra.pid')
os.makedirs(JMXC, exist_ok=True)
sh(f'javac -d {JMXC} {HARNESS}/Jmx.java')
y = sh(f'{HARNESS}/make-node-yaml.sh {mib}')[1]; note(y.strip().splitlines()[-1][:600]); first_start = False
syslog = start_node()
m = re.search(r'Initialized prepared statement caches with (\d+) MiB', syslog)
note(f'READBACK log: "Initialized prepared statement caches with {m.group(1) if m else "?"} MiB"')
if not m or int(m.group(1)) != mib:
    fail('knob read-back from the log did not match')
client('setup')
H0 = histo('0-baseline')
client('plain', PLAIN_N, RATE)
H0b = histo('1-after-plain')
c0 = counters(); note(f'COUNTERS after-plain count={c0[0]} evicted={c0[1]} memtable_heap={c0[2]}')
before = counters()[0]; client('dup', 100); after = counters()[0]
note(f'DUP count_before={before} count_after={after} (adds at most one: {after - before <= 1})')
# ---- load with samples and the stop rule
stopf = PSC + '/stop-load'
if os.path.exists(stopf):
    os.remove(stopf)
smp = csv.writer(open(LOGS + '/samples.csv', 'w', newline=''))
smp.writerow(['t_s', 'count', 'evicted', 'memtable_heap_bytes'])
ev_base = counters()[1]
p = subprocess.Popen(f'python3 {HARNESS}/prep-load.py load {MAXN} {RATE} {stopf}', shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                     env=dict(os.environ, CASSANDRA_HOME=C))
t0 = time.time(); hist = []; stop_met = False
while p.poll() is None:
    time.sleep(SAMPLE_S)
    cnt, ev, mt = counters(); hist.append(cnt)
    smp.writerow([round(time.time() - t0, 1), cnt, ev - ev_base, mt]); log(f'sample count={cnt} evicted={ev - ev_base} memtable_heap={mt}')
    last = hist[-10:]
    if len(last) == 10 and ev - ev_base >= 5 * cnt and cnt > 0 and (max(last) - min(last)) <= 0.01 * max(last):
        stop_met = True; open(stopf, 'w').close(); note(f'STOP RULE met at {time.time() - t0:.0f}s: evicted={ev - ev_base} >= 5 x count={cnt}; last 10 counts {min(last)}..{max(last)}')
out = p.communicate()[0]
res = [l for l in out.splitlines() if l.startswith('RESULT')]
note(res[-1] if res else 'RESULT missing: ' + out[-400:])
time.sleep(30)
cnt, ev, mt = counters(); ev -= ev_base
note(f'COUNTERS final count={cnt} evicted={ev} memtable_heap={mt} stop_rule_met={stop_met}')
H1 = histo('2-after-load')
note(f'HEAP DELTA vs baseline-after-plain: {H1["live_bytes"] - H0b["live_bytes"]} B (vs first baseline {H1["live_bytes"] - H0["live_bytes"]}); '
     f'memtable heap of system.prepared_statements {mt} B; delta minus memtable {H1["live_bytes"] - H0b["live_bytes"] - mt}')
_, o = sh(f"du -sb {PSC}/data/system/prepared_statements-* 2>/dev/null | cut -f1", check=False, quiet=True); note(f'DISK system.prepared_statements bytes={o.strip()}')
_, o = sh(f"bin/cqlsh --request-timeout=300 127.0.0.1 -e \"SELECT count(*) FROM system.prepared_statements\" 2>&1 | grep -E '^ +[0-9]+ *$' ", check=False, timeout=300, quiet=True)
note('ROWS system.prepared_statements: ' + ' '.join(o.split())[:200])
client('oversize', cap + MIB)
cnt2 = counters()[0]; note(f'OVERSIZE count_before={cnt} count_after={cnt2}')
if restart:
    stop_node(); note('RESTART: node stopped; starting without wiping')
    sl = start_node()
    pre = re.findall(r'Preloaded (\d+) prepared statements in (\d+) ms', sl)
    wn = [l for l in sl.splitlines() if 'Detected prepared statement cache filling up' in l]
    note(f'RESTART preload lines={pre}; filling-up warnings={len(wn)}; count after restart={counters()[0]}')
left = stop_node()
note('STOPPED: ' + (left or 'no CassandraDaemon left'))
