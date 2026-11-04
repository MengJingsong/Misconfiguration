#!/usr/bin/env python3
"""Cluster tier (B3) of filename_length-validatesnapshotname-snapshotname--autonomous. Run on pc41: cluster-run.py [run-name]
One node (127.0.0.1) from the copy ~/s4-b2/base (copy-source.sh + ant build-test), data/commitlog/logs under ~/s4-b2/node/ on local disk.
Output: ~/s4-b2/logs/<stem>/<run>/cluster/{log.txt,summary.txt,rows.csv,*.out}. 'EXPECTED' lines in summary.txt are the B3f predictions."""
import csv, glob, os, re, subprocess, sys, time
STEM = 'filename_length-validatesnapshotname-snapshotname--autonomous'
RUN = sys.argv[1] if len(sys.argv) > 1 else 'run1'
HOME = os.path.expanduser('~'); BASE = f'{HOME}/s4-b2/base'; NODE = f'{HOME}/s4-b2/node'
LOG = f'{HOME}/s4-b2/logs/{STEM}/{RUN}/cluster'; os.makedirs(LOG, exist_ok=True)
SUM = open(f'{LOG}/summary.txt', 'a'); LF = open(f'{LOG}/log.txt', 'a')
ROWS = open(f'{LOG}/rows.csv', 'a'); W = csv.writer(ROWS)
bad = 0; nexp = 0

def log(s):
    t = time.strftime('%H:%M:%S'); LF.write(f'{t} {s}\n'); LF.flush(); print(f'{t} {s}', flush=True)
def note(s): SUM.write(s + '\n'); SUM.flush(); log(s)
def sh(cmd, timeout=900, check=False, env=None):
    log('$ ' + cmd)
    e = dict(os.environ); e.update(env or {})
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, cwd=BASE, env=e, stdin=subprocess.DEVNULL)
    LF.write(f'  rc={r.returncode}\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}\n'); LF.flush()
    if check and r.returncode: raise SystemExit(f'failed: {cmd}')
    return r
def expect(desc, ok):
    global bad, nexp
    nexp += 1; bad += (not ok); note(f'EXPECTED {desc}: {"yes" if ok else "NO"}')

def pid():
    r = subprocess.run("pgrep -f '[C]assandraDaemon' | head -1", shell=True, capture_output=True, text=True); return r.stdout.strip()
def nt(cmd, timeout=300): return sh(f'bin/nodetool {cmd}', timeout=timeout)
def make_conf(validation):
    shutil = __import__('shutil'); shutil.rmtree(f'{NODE}/conf', ignore_errors=True); os.makedirs(NODE, exist_ok=True)
    shutil.copytree(f'{BASE}/conf', f'{NODE}/conf')
    y = open(f'{NODE}/conf/cassandra.yaml').read()
    y += f'\n# stage4\ndata_file_directories:\n    - {NODE}/data\ncommitlog_directory: {NODE}/commitlog\nhints_directory: {NODE}/hints\nsaved_caches_directory: {NODE}/saved_caches\ncdc_raw_directory: {NODE}/cdc_raw\n'
    # remove shipped keys that would be duplicated
    out, skip = [], False
    for l in y.splitlines():
        m = re.match(r'^(data_file_directories|commitlog_directory|hints_directory|saved_caches_directory|cdc_raw_directory):', l)
        out.append(l)
    open(f'{NODE}/conf/cassandra.yaml', 'w').write(y)
def clean_yaml():
    # keep only the last occurrence of the keys we appended (shipped file has them commented out; check)
    y = open(f'{NODE}/conf/cassandra.yaml').read().splitlines()
    for k in ('data_file_directories', 'commitlog_directory', 'hints_directory', 'saved_caches_directory', 'cdc_raw_directory'):
        n = sum(1 for l in y if l.startswith(k + ':'))
        assert n == 1, f'{k} appears {n} times'
def start(validation):
    make_conf(validation); clean_yaml()
    opts = f'-Dcassandra.snapshot.validation={"true" if validation else "false"}'
    env = {'CASSANDRA_CONF': f'{NODE}/conf', 'CASSANDRA_LOG_DIR': f'{NODE}/logs', 'MAX_HEAP_SIZE': '2G', 'HEAP_NEWSIZE': '400M', 'JVM_EXTRA_OPTS': opts}
    os.makedirs(f'{NODE}/logs', exist_ok=True)
    sh(f'ulimit -n 100000; nohup bin/cassandra -p {NODE}/pid > {NODE}/logs/stdout.log 2>&1 < /dev/null &', env=env)
    t0 = time.time()
    while time.time() - t0 < 300:
        time.sleep(5)
        if not pid() and time.time() - t0 > 20: raise SystemExit('daemon died during start')
        r = nt('statusbinary', 60)
        if 'running' in r.stdout and 'not running' not in r.stdout:
            s = nt('status', 60).stdout
            if re.search(r'^UN ', s, re.M): break
    else: raise SystemExit('start timeout')
    note(f'node up validation={validation} pid={pid()} opts={opts}')
    j = open(f'/proc/{pid()}/cmdline').read().replace('\0', ' ')
    expect(f'JVM has {opts} and -Xmx2G', opts in j and '-Xmx2G' in j)
def stop():
    p = pid()
    if p:
        sh(f'kill {p}')
        for _ in range(60):
            time.sleep(2)
            if not pid(): break
        if pid(): sh(f'kill -9 {pid()}')
    note(f'node stopped; daemons left: {pid() or "none"}')
def heap_used():
    p = pid(); sh(f'jcmd {p} GC.run'); time.sleep(1)
    r = sh(f'jcmd {p} GC.heap_info'); m = re.search(r'used (\d+)K', r.stdout)
    return int(m.group(1)) * 1024
def rss(): 
    for l in open(f'/proc/{pid()}/status'):
        if l.startswith('VmRSS'): return int(l.split()[1]) * 1024
def physical(root):
    seen = set(); tot = 0
    for d, _, fs in os.walk(root):
        for f in fs:
            st = os.lstat(os.path.join(d, f))
            if (st.st_dev, st.st_ino) not in seen: seen.add((st.st_dev, st.st_ino)); tot += st.st_size
    return tot
def tabledir(): return (glob.glob(f'{NODE}/data/keyspace1/standard1-*') or [None])[0]
def snapdir(name):
    t = tabledir(); return os.path.join(t, 'snapshots', name) if t else None
def dirstats(d):
    if not d or not os.path.isdir(d): return (-1, -1, -1, -1)
    fs = [f for f in os.listdir(d) if os.path.isfile(os.path.join(d, f))]
    tot = sum(os.path.getsize(os.path.join(d, f)) for f in fs)
    m = os.path.getsize(os.path.join(d, 'manifest.json')) if 'manifest.json' in fs else -1
    s = os.path.getsize(os.path.join(d, 'schema.cql')) if 'schema.cql' in fs else -1
    return (tot, len(fs), m, s)
def load(n, lo=None):
    pop = f'-pop seq={lo}..{n}' if lo else ''
    r = sh(f'tools/bin/cassandra-stress write n={(n - lo + 1) if lo else n} no-warmup -col n=FIXED\\(1\\) size=FIXED\\(200\\) {pop} -rate threads=64 -node 127.0.0.1', timeout=1800)
    open(f'{LOG}/stress-{n}.out', 'w').write(r.stdout[-6000:])
    m = re.search(r'Total errors\s*:\s*(\d+)', r.stdout); expect(f'stress to {n}: errors 0', bool(m) and m.group(1) == '0')
def settle_state():
    p = tabledir() and tabledir()
    return dict(heap=heap_used(), rss=rss(), phys=physical(f'{NODE}/data'))
def snapshot(N, tag, L, expect_ok, validation):
    name = 'a' * L
    b = settle_state(); nt('flush') if False else None
    t0 = time.time(); r = nt(f'snapshot -t {name} keyspace1', 300); t1 = time.time()
    time.sleep(30)
    a = settle_state(); ds = dirstats(snapdir(name))
    ls = nt('listsnapshots', 120).stdout
    line = [l for l in ls.splitlines() if l.startswith(name[:20]) and name in l.split()[0:1]] if False else [l for l in ls.splitlines() if l.split() and l.split()[0] == name]
    ts = line[0].split() if line else []
    open(f'{LOG}/listsnapshots-{tag}-L{L}.out', 'w').write(re.sub(r'a{20,}', lambda m: f'a*{len(m.group(0))}', ls))
    err = re.sub(r'a{20,}', lambda m: f'a*{len(m.group(0))}', (r.stderr + r.stdout)).strip().replace('\n', ' | ')[:240]
    row = [tag, N, validation, L, r.returncode, ds[0], ds[1], ds[2], ds[3], a['phys'] - b['phys'], a['heap'] - b['heap'], a['rss'] - b['rss'], ' '.join(ts[-5:]) if ts else 'none', err]
    W.writerow(row); ROWS.flush()
    note(f'SNAP {tag} N={N} v={validation} L={L} rc={r.returncode} snapFileBytes={ds[0]} files={ds[1]} manifest={ds[2]} schema={ds[3]} physDelta={a["phys"]-b["phys"]} heapDelta={a["heap"]-b["heap"]} rssDelta={a["rss"]-b["rss"]} listsnap="{" ".join(ts[-5:]) if ts else "none"}" err="{err[:160]}"')
    ok = r.returncode == 0
    expect(f'{tag} N={N} L={L} v={validation} nodetool snapshot {"succeeds" if expect_ok else "fails"}', ok == expect_ok)
    if expect_ok: expect(f'{tag} L={L} snapshot dir exists with files', ds[1] > 0)
    else: expect(f'{tag} L={L} no snapshot dir created', ds[0] == -1)
    if not expect_ok and validation:
        expect(f'{tag} L={L} message is the line-2187 text', 'Snapshot name must not be more than 255 characters' in (r.stderr + r.stdout))
    if not expect_ok and not validation:
        expect(f'{tag} L={L} message is NOT the line-2187 text (OS rejection)', 'Snapshot name must not be more than 255 characters' not in (r.stderr + r.stdout))
    if expect_ok: nt(f'clearsnapshot -t {name} keyspace1', 300)
    return dict(snap=ds, phys=a['phys'] - b['phys'], heap=a['heap'] - b['heap'], rss=a['rss'] - b['rss'], true=ts[-5:] if ts else None)

def main():
    note(f'cluster-run {RUN} start {time.strftime("%Y-%m-%dT%H:%M:%S%z")} host {os.uname().nodename} copy {BASE} {sh("git describe --tags").stdout.strip()}')
    W.writerow('tag N validation L rc snapFileBytes files manifest schema physDelta heapDelta rssDelta listsnapshots_tail err'.split())
    sh(f'rm -rf {NODE}'); os.makedirs(NODE)
    free = int(sh(f'df --output=avail -B1G {HOME} | tail -1').stdout.strip()); expect(f'local disk free {free} GB >= 10', free >= 10)
    start(True)
    try:
        load(200000)
        nt('disableautocompaction keyspace1'); nt('flush keyspace1', 600); time.sleep(10)
        res = {}
        snapshot(200000, 'warmup', 100, True, True)
        for L in (1, 100, 255, 256):
            res[(200000, L)] = snapshot(200000, 'N200k', L, L <= 255, True)
        load(2000000, 200001)
        nt('flush keyspace1', 900); time.sleep(20)
        for L in (100, 255):
            res[(2000000, L)] = snapshot(2000000, 'N2M', L, True, True)
        # cross-L comparisons
        a, b = res[(200000, 1)], res[(200000, 255)]
        expect('N=200k snapFileBytes equal for L=1,100,255', res[(200000, 1)]['snap'][0] == res[(200000, 100)]['snap'][0] == b['snap'][0])
        expect('N=200k manifest/schema sizes equal for L=1,100,255', res[(200000, 1)]['snap'][2:] == res[(200000, 100)]['snap'][2:] == b['snap'][2:])
        expect(f'N=200k |physDelta(255)-physDelta(1)| <= 64 KiB ({b["phys"]} vs {a["phys"]})', abs(b['phys'] - a['phys']) <= 65536)
        expect(f'N=200k |heapDelta(255)-heapDelta(1)| < 1 MiB ({b["heap"]} vs {a["heap"]})', abs(b['heap'] - a['heap']) < 1 << 20)
        c, d = res[(2000000, 100)], res[(2000000, 255)]
        expect('N=2M snapFileBytes equal for L=100,255', c['snap'][0] == d['snap'][0])
        expect(f'N=2M |physDelta(255)-physDelta(100)| <= 64 KiB ({d["phys"]} vs {c["phys"]})', abs(d['phys'] - c['phys']) <= 65536)
        expect(f'N=2M |heapDelta(255)-heapDelta(100)| < 1 MiB ({d["heap"]} vs {c["heap"]})', abs(d['heap'] - c['heap']) < 1 << 20)
        expect(f'positive control: snapFileBytes N=2M >= 5x N=200k ({c["snap"][0]} vs {res[(200000,100)]["snap"][0]})', c['snap'][0] >= 5 * res[(200000, 100)]['snap'][0])
        stop()
        start(False)
        nt('disableautocompaction keyspace1')
        snapshot(2000000, 'valfalse', 256, False, False)
        snapshot(2000000, 'valfalse', 255, True, False)
    finally:
        stop()
    note(f'SUMMARY expected-lines={nexp} not-yes={bad}')
    note(f'done {time.strftime("%Y-%m-%dT%H:%M:%S%z")}')
main()
