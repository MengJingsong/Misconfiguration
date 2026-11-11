#!/usr/bin/env python3
"""Stage-4 cluster tier of max-compaction-threshold-getCandidatesFor-candidatesSize--autonomous (B3, amendments C1-C5, 2026-10-26).

  LC_TREE=<copy-source.sh tree> LC_OUT=<outdir> lcmt_cluster.py build <role>      role = lcs | stcs
  LC_TREE=... LC_OUT=... lcmt_cluster.py run <role> <N>

Slot 5: role lcs = 127.0.5.1, JMX 7150; role stcs = 127.0.5.2, JMX 7151; native 9042 on that address only.
Data, commit log, hints and caches on the tmpfs $LC_MNT (default /mnt/s4lc, 40 GiB), under work-<role>/; the fixture is fx-<role>/.
build: creates ks.standard1 (compaction disabled in its schema), builds the fixture (lcs: 1.5 M rows compacted into L1, then 100 flushes of
65,536 rows; stcs: the 100 flushes only), drains, stops the node, moves the data directory to fx-<role>/.
run: restores a copy of fx-<role>, starts the node, sets max_threshold N (nodetool setcompactionthreshold ks standard1 2 N), samples, enables autocompaction,
stops at the first task (disable at its 'Compacting (' log line), waits for it to finish, records, stops the node.
Stops at the first failed check; the node is stopped on any exit."""
import os, sys, re, time, json, shutil, subprocess, threading, signal, glob, shlex

TREE = os.environ.get('LC_TREE') or sys.exit('set LC_TREE')
OUT = os.environ.get('LC_OUT') or sys.exit('set LC_OUT')
MNT = os.environ.get('LC_MNT', '/mnt/s4lc')
MODE = sys.argv[1] if len(sys.argv) > 1 else sys.exit(__doc__)
ROLE = sys.argv[2] if len(sys.argv) > 2 else sys.exit(__doc__)
NVAL = int(sys.argv[3]) if MODE == 'run' else None
ADDR, JMX = {'lcs': ('127.0.5.1', 7150), 'stcs': ('127.0.5.2', 7151)}[ROLE]
N_PHASE1 = int(os.environ.get('LC_PHASE1_ROWS', 1500000))
N_FLUSHES = int(os.environ.get('LC_FLUSHES', 100))
ROWS_PER_FLUSH = int(os.environ.get('LC_FLUSH_ROWS', 65536))
L1MIN = int(os.environ.get('LC_L1MIN', 9)); L1MAX = int(os.environ.get('LC_L1MAX', 11))   # shakedowns only override these
COLS = 'size=FIXED(256) n=FIXED(4)'
THREADS = 16
LABEL = f'{MODE}-{ROLE}' + (f'-N{NVAL}' if NVAL else '')
RUN = os.path.join(OUT, LABEL)
os.makedirs(RUN, exist_ok=True)
WORK = f'{MNT}/work-{ROLE}'
FX = f'{MNT}/fx-{ROLE}'
CMDLOG = open(os.path.join(RUN, 'commands.log'), 'a')
NT = f'{TREE}/bin/nodetool -h 127.0.0.1 -p {JMX}'
COMPACTION = {'lcs': "{'class':'LeveledCompactionStrategy','sstable_size_in_mb':'160','enabled':'false'}",
              'stcs': "{'class':'SizeTieredCompactionStrategy','enabled':'false'}"}[ROLE]
state = {'pid': None}

def log(msg):
    line = f'{time.strftime("%H:%M:%S")} {msg}'
    print(line, flush=True); CMDLOG.write(line + '\n'); CMDLOG.flush()

def sh(cmd, timeout=600, check=True, quiet=False):
    if not quiet: log('$ ' + cmd[:300])
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    if not quiet:
        CMDLOG.write((r.stdout or '')[-2000:] + (r.stderr or '')[-1000:] + '\n'); CMDLOG.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed ({r.returncode}): {cmd[:200]}\n{r.stderr[-600:]}')
    return r.stdout

def daemons():
    """only this run's daemon: the command line holds this run's log directory"""
    out = subprocess.run(['ps', '-eo', 'pid,args'], capture_output=True, text=True).stdout
    return [l for l in out.splitlines() if 'CassandraDaemon' in l and f'{RUN}/' in l and re.search(r'(^|/)java ', l)]

def table_dirs():
    return sorted(glob.glob(f'{WORK}/data/ks/standard1-*'))

def dir_bytes():
    n, files, data = 0, 0, []
    for d in table_dirs():
        for e in os.scandir(d):
            if e.is_file(follow_symlinks=False):
                try: sz = e.stat().st_size
                except FileNotFoundError: continue
                n += sz; files += 1
                if e.name.endswith('-Data.db'): data.append(sz)
    return n, files, data

def data_sizes():
    out = {}
    for d in table_dirs():
        for e in os.scandir(d):
            if e.is_file() and e.name.endswith('-Data.db'): out[e.name] = e.stat().st_size
    return out

def make_conf():
    conf = os.path.join(RUN, 'conf')
    shutil.rmtree(conf, ignore_errors=True)
    shutil.copytree(f'{TREE}/conf', conf)
    env = open(f'{conf}/cassandra-env.sh').read()
    assert 'JMX_PORT="7199"' in env
    open(f'{conf}/cassandra-env.sh', 'w').write(env.replace('JMX_PORT="7199"', f'JMX_PORT="{JMX}"'))
    add = {
        'cluster_name': f"'s4-b10-lc-{ROLE}'", 'num_tokens': '1', 'auto_bootstrap': 'false',
        'listen_address': ADDR, 'rpc_address': ADDR, 'native_transport_port': '9042',
        'commitlog_directory': f'{WORK}/commitlog', 'hints_directory': f'{WORK}/hints',
        'saved_caches_directory': f'{WORK}/saved_caches', 'cdc_raw_directory': f'{WORK}/cdc_raw',
        'auto_snapshot': 'false', 'concurrent_compactors': '1', 'compaction_throughput': '0MiB/s',
    }
    lines, skip = [], False
    for l in open(f'{conf}/cassandra.yaml').read().splitlines():
        m = re.match(r'^([A-Za-z_]+):', l)
        if m:
            skip = m.group(1) in add or m.group(1) in ('seed_provider', 'data_file_directories')
            if skip: continue
        elif skip and (l.startswith((' ', '\t', '-')) or l.strip() == '' or l.lstrip().startswith('#')):
            continue
        else: skip = False
        lines.append(l)
    tail = [f'{k}: {v}' for k, v in add.items()]
    tail += ['seed_provider:', '  - class_name: org.apache.cassandra.locator.SimpleSeedProvider', '    parameters:', f'      - seeds: "{ADDR}:7000"',
             'data_file_directories:', f'    - {WORK}/data']
    open(f'{conf}/cassandra.yaml', 'w').write('\n'.join(lines) + '\n# ---- stage4 b10-lc lines ----\n' + '\n'.join(tail) + '\n')
    shutil.copy(f'{conf}/cassandra.yaml', f'{RUN}/cassandra.yaml.used')
    return conf

def start_node():
    assert not daemons(), 'a daemon of this run already exists'
    conf = make_conf()
    logs = os.path.join(RUN, 'logs'); os.makedirs(logs, exist_ok=True)
    env = f'CASSANDRA_CONF={conf} CASSANDRA_LOG_DIR={logs} MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M'
    sh(f'ulimit -n 100000; cd {TREE} && ( {env} setsid nohup bin/cassandra -f -p {RUN}/pid < /dev/null > {RUN}/node.out 2>&1 & )')
    t0 = time.time()
    while time.time() - t0 < 300:
        time.sleep(3)
        if not daemons(): raise RuntimeError('node died during start; see node.out')
        st = subprocess.run(f'{NT} status 2>/dev/null | grep -c "^UN"; {NT} statusbinary 2>/dev/null', shell=True, capture_output=True, text=True, stdin=subprocess.DEVNULL).stdout
        if st.split() and st.split()[0] == '1' and any(x.strip() == 'running' for x in st.splitlines()): break
    else: raise RuntimeError('node did not come up')
    state['pid'] = int(daemons()[0].split()[0])
    log(f'node up, pid {state["pid"]}, address {ADDR}, jmx {JMX}')

def stop_node():
    pid = state['pid']
    if pid:
        try: os.kill(pid, signal.SIGTERM)
        except ProcessLookupError: pass
        for _ in range(60):
            time.sleep(1.5)
            if not daemons(): break
        else:
            try: os.kill(pid, signal.SIGKILL)
            except ProcessLookupError: pass
            time.sleep(3)
    left = daemons()
    log('daemons of this run left after stop: ' + (str([l[:80] for l in left]) if left else 'none'))
    return not left

def cql(stmt, timeout=300):
    return sh(f'{TREE}/bin/cqlsh {ADDR} -e "{stmt}"', timeout=timeout)

def tablestats():
    return sh(f'{NT} tablestats ks.standard1', check=False, timeout=120, quiet=True)

def parse_levels(txt):
    out = {}
    m = re.search(r'SSTables in each level: \[(.*?)\]', txt)
    out['count'] = [int(re.sub(r'[^0-9]', '', x.split('/')[0]) or 0) for x in m.group(1).split(',')] if m else None
    m = re.search(r'SSTable count: (\d+)', txt); out['sstables'] = int(m.group(1)) if m else None
    m = re.search(r'Space used \(live\): (\d+)', txt); out['live'] = int(m.group(1)) if m else None
    return out

def compaction_busy():
    t = sh(f'{NT} tpstats', check=False, timeout=120, quiet=True)
    for l in t.splitlines():
        if l.startswith('CompactionExecutor'):
            p = l.split(); return int(p[1]) + int(p[2])
    return -1

def settle(tag, cap=1500, gap=15):
    """3 reads gap s apart with no active or queued compaction task and identical file bytes"""
    t0 = time.time(); hist = []
    while time.time() - t0 < cap:
        time.sleep(gap)
        nb, nf, _ = dir_bytes(); busy = compaction_busy()
        hist.append((busy, nb)); log(f'settle[{tag}] busy={busy} bytes={nb} files={nf}')
        if len(hist) >= 3 and all(h[0] == 0 for h in hist[-3:]) and len({h[1] for h in hist[-3:]}) == 1:
            return True
    return False

def stress(n, a, b, tag):
    qcols = ' '.join(shlex.quote(x) for x in COLS.split())
    out = f'{RUN}/stress-{tag}.txt'
    sh(f'{TREE}/tools/bin/cassandra-stress write n={n} -col {qcols} -pop seq={a}..{b} -schema keyspace=ks -rate threads={THREADS} -node {ADDR} -port native=9042 jmx={JMX} > {out} 2>&1', timeout=3600, check=False, quiet=True)
    txt = open(out).read()
    if 'Total errors' not in txt or not re.search(r'Total errors\s*:\s*0 ', txt):
        raise RuntimeError(f'stress {tag} did not finish clean; see {out}')

def create_table():
    cql("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    cols = ', '.join(f'\\"C{i}\\" blob' for i in range(5))
    cql(f"CREATE TABLE IF NOT EXISTS ks.standard1 (key blob PRIMARY KEY, {cols}) WITH compression = {{'enabled':'false'}} AND compaction = {COMPACTION}")

def prep_mnt():
    sh(f'sudo mkdir -p {MNT} && (mountpoint -q {MNT} || sudo mount -t tmpfs -o size=40g tmpfs {MNT}) && sudo chown $(id -u):$(id -g) {MNT}')

def fresh_dirs():
    sh(f'rm -rf {WORK} && mkdir -p {WORK}/data {WORK}/commitlog {WORK}/hints {WORK}/saved_caches {WORK}/cdc_raw')

# ------------------------------------------------------------------------------------------------ build
def build():
    prep_mnt(); fresh_dirs(); sh(f'rm -rf {FX}')
    start_node(); create_table()
    if ROLE == 'lcs':
        sh(f'{NT} enableautocompaction ks standard1')
        stress(N_PHASE1, 1, N_PHASE1, 'phase1')
        if not settle('phase1'): raise RuntimeError('phase 1 did not settle')
        sh(f'{NT} disableautocompaction ks standard1')
        ts = tablestats(); open(f'{RUN}/tablestats-phase1.txt', 'w').write(ts)
        lv = parse_levels(ts); log(f'phase 1 levels {lv}')
        c = lv['count'] or []
        if not (len(c) > 1 and c[0] <= 2 and L1MIN <= c[1] <= L1MAX and sum(c[2:]) == 0):
            raise RuntimeError(f'fixture check failed after phase 1: L0 <= 2, L1 {L1MIN}..{L1MAX}, L2+=0 required, got {lv}')
        left0 = c[0]          # a lone L0 sstable cannot be compacted (LeveledManifest.java:569); it counts toward the 100 L0 sstables
        log(f'phase 1 leftover in L0: {left0}; phase 2 flushes: {N_FLUSHES - left0}')
    else:
        left0 = 0
    base = 2000000
    def n_now():
        lv_ = parse_levels(tablestats())
        return (lv_['count'][0] if (ROLE == 'lcs' and lv_['count']) else lv_['sstables']), lv_
    i = 0
    cur = left0 if ROLE == 'lcs' else 0
    while cur < N_FLUSHES:
        a = base + i * ROWS_PER_FLUSH + 1; b = a + ROWS_PER_FLUSH - 1
        stress(ROWS_PER_FLUSH, a, b, f'f{i:03d}')
        sh(f'{NT} flush ks standard1', quiet=True)
        i += 1
        prev = cur; cur, lv_ = n_now()          # an extra sstable from a spontaneous memtable flush is possible: flush until the count is exactly 100
        if cur != prev + 1: log(f'note: flush {i} changed the L0/sstable count {prev} -> {cur}')
        if i % 10 == 0: log(f'flush {i}: count {cur} {lv_}')
        if i > N_FLUSHES + 20: raise RuntimeError('too many flushes')
    log(f'{i} stress+flush rounds')
    ts = tablestats(); open(f'{RUN}/tablestats-fixture.txt', 'w').write(ts); lv = parse_levels(ts)
    sizes = data_sizes(); json.dump(sizes, open(f'{RUN}/fixture-datafiles.json', 'w'))
    log(f'fixture levels {lv}; data files {len(sizes)}; bytes {dir_bytes()[0]}')
    c = lv['count'] or []
    if ROLE == 'lcs' and not (c and c[0] == N_FLUSHES): raise RuntimeError(f'fixture check failed: L0 count {c[:1]} != {N_FLUSHES}')
    if ROLE == 'stcs' and lv['sstables'] != N_FLUSHES: raise RuntimeError(f'fixture check failed: {lv["sstables"]} sstables != {N_FLUSHES}')
    sh(f'{NT} drain', check=False, timeout=300)
    return lv

# ------------------------------------------------------------------------------------------------ run
class Sampler(threading.Thread):
    def __init__(self, path):
        super().__init__(daemon=True); self.path = path; self.ev = threading.Event()
    def run(self):
        f = open(self.path, 'a'); pid = state['pid']
        while not self.ev.is_set():
            t = time.time(); rec = {'t': t}
            try:
                nb, nf, data = dir_bytes(); rec.update({'bytes': nb, 'files': nf, 'datafiles': len(data)})
                for l in open(f'/proc/{pid}/status'):
                    if l.startswith('RssAnon:'): rec['rssAnonKB'] = int(l.split()[1])
                j = subprocess.run(['jcmd', str(pid), 'GC.heap_info'], capture_output=True, text=True, timeout=10).stdout   # jstat is unusable (-XX:+PerfDisableSharedMem)
                mh = re.search(r'garbage-first heap\s+total (\d+)K, used (\d+)K', j)
                if mh: rec['heapUsedKB'] = int(mh.group(2)); rec['heapTotalKB'] = int(mh.group(1))
            except Exception as e:
                rec['error'] = repr(e)
            f.write(json.dumps(rec) + '\n'); f.flush()
            self.ev.wait(1.0)
    def stop(self): self.ev.set()

class Sampler2(threading.Thread):
    """run 2 (LC_SAMPLER=v2): two threads. Fast: every 0.25 s table-directory bytes and RssAnon. Slow: every ~2 s the LIVE heap, as the total of
    `jcmd GC.class_histogram` (it runs a collection first, so garbage is excluded; environment lessons: 'live heap: the GC.class_histogram total')."""
    def __init__(self, path):
        super().__init__(daemon=True); self.path = path; self.ev = threading.Event(); self.lock = threading.Lock()
        self.slow = threading.Thread(target=self.run_slow, daemon=True)
    def write(self, rec):
        with self.lock:
            self.f.write(json.dumps(rec) + '\n'); self.f.flush()
    def start(self):
        self.f = open(self.path, 'a'); self.pid = state['pid']
        super().start(); self.slow.start()
    def run(self):
        while not self.ev.is_set():
            t = time.time(); rec = {'t': t}
            try:
                nb, nf, data = dir_bytes(); rec.update({'bytes': nb, 'files': nf, 'datafiles': len(data)})
                for l in open(f'/proc/{self.pid}/status'):
                    if l.startswith('RssAnon:'): rec['rssAnonKB'] = int(l.split()[1])
            except Exception as e:
                rec['error'] = repr(e)
            self.write(rec)
            self.ev.wait(0.25)
    def run_slow(self):
        while not self.ev.is_set():
            t = time.time(); rec = {'t': t, 'slow': True}
            try:
                h = subprocess.run(['jcmd', str(self.pid), 'GC.class_histogram'], capture_output=True, text=True, timeout=60).stdout
                mt = re.search(r'^Total\s+(\d+)\s+(\d+)', h, re.M)
                if mt: rec['liveHeapKB'] = int(mt.group(2)) / 1024.0
            except Exception as e:
                rec['error'] = repr(e)
            rec['t_end'] = time.time()
            self.write(rec)
            self.ev.wait(1.0)
    def stop(self): self.ev.set()

def syslog():
    return f'{RUN}/logs/system.log'

def run_one():
    prep_mnt()
    if not os.path.isdir(f'{FX}/data'): raise RuntimeError(f'no fixture {FX}/data (run build {ROLE} first)')
    fresh_dirs(); sh(f'rm -rf {WORK}/data && cp -a {FX}/data {WORK}/data')
    start_node()
    ts = tablestats(); open(f'{RUN}/tablestats-before.txt', 'w').write(ts); lv = parse_levels(ts); log(f'before: {lv}')
    c = lv['count'] or []
    if ROLE == 'lcs' and not (c and c[0] == N_FLUSHES and L1MIN <= c[1] <= L1MAX): raise RuntimeError(f'restored fixture is not as built: {lv}')
    if ROLE == 'stcs' and lv['sstables'] != N_FLUSHES: raise RuntimeError(f'restored fixture is not as built: {lv}')
    if compaction_busy() != 0: raise RuntimeError('a compaction is active before the enable')
    sizes = data_sizes(); json.dump(sizes, open(f'{RUN}/files-before.json', 'w'))
    sh(f'{NT} setcompactionthreshold ks standard1 2 {NVAL}')
    got = sh(f'{NT} getcompactionthreshold ks standard1', quiet=False)
    open(f'{RUN}/getcompactionthreshold.txt', 'w').write(got)
    if f'maximum compaction threshold: {NVAL}' not in got.lower() and f'{NVAL}' not in got: raise RuntimeError('threshold not set: ' + got)
    smp = (Sampler2 if os.environ.get('LC_SAMPLER') == 'v2' else Sampler)(f'{RUN}/samples.jsonl'); smp.start()
    time.sleep(10)                                   # idle baseline
    meta = {'N': NVAL, 'role': ROLE}
    # helper JVM with an open JMX connection: disables autocompaction within milliseconds of the first 'Compacting (' line
    hd = os.path.join(RUN, 'helper'); os.makedirs(hd, exist_ok=True)
    sh(f'javac -d {hd} {os.path.dirname(os.path.abspath(__file__))}/LcDisable.java', quiet=True)
    helper = subprocess.Popen(['java', '-cp', hd, 'LcDisable', str(JMX), 'ks', 'standard1'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    if helper.stdout.readline().strip() != 'ready': raise RuntimeError('JMX helper did not start')
    lg = syslog(); pos = os.path.getsize(lg) if os.path.exists(lg) else 0
    meta['t_enable'] = time.time()
    helper.stdin.write('enable\n'); helper.stdin.flush()
    meta['enable_reply'] = helper.stdout.readline().strip(); log('helper: ' + meta['enable_reply'])
    first = None; t0 = time.time(); buf = ''
    while time.time() - t0 < 900 and not first:
        time.sleep(0.05)
        with open(lg, errors='replace') as f:
            f.seek(pos); chunk = f.read(); pos += len(chunk.encode('utf-8', 'replace'))
        buf += chunk
        while '\n' in buf and not first:
            line, buf = buf.split('\n', 1)
            if 'Compacting (' in line and 'standard1' in line: first = line
        if first:
            helper.stdin.write('disable\n'); helper.stdin.flush()
            meta['disable_reply'] = helper.stdout.readline().strip()
            meta['t_disable_returned'] = time.time()
        elif not daemons(): raise RuntimeError('node died while waiting for the first task')
    meta['first_compacting_line'] = first
    try:
        helper.stdin.write('quit\n'); helper.stdin.flush()
    except Exception: pass
    if not first: raise RuntimeError('no compaction task started within 900 s')
    settled = settle('task', cap=1800, gap=10)
    meta['settled'] = settled; meta['t_settled'] = time.time()
    smp.stop(); time.sleep(2)
    ts = tablestats(); open(f'{RUN}/tablestats-after.txt', 'w').write(ts); log(f'after: {parse_levels(ts)}')
    json.dump(data_sizes(), open(f'{RUN}/files-after.json', 'w'))
    shutil.copy(syslog(), f'{RUN}/system.log.copy')
    json.dump(meta, open(f'{RUN}/meta.json', 'w'))
    if not settled: raise RuntimeError('task did not settle')

def main():
    rc = 1
    try:
        log(f'== {LABEL} start; tree={TREE} mnt={MNT}')
        if MODE == 'build': build()
        elif MODE == 'run': run_one()
        else: sys.exit(__doc__)
        rc = 0
    except Exception as e:
        log(f'FAILED: {e!r}'); rc = 2
    finally:
        ok = stop_node()
        if MODE == 'build' and rc == 0 and ok:
            sh(f'rm -rf {FX} && mkdir -p {FX} && mv {WORK}/data {FX}/data && rm -rf {WORK}')
            log(f'fixture moved to {FX}: {dir_bytes() and ""}' + sh(f'du -sb {FX} | cut -f1', quiet=True).strip())
        open(f'{RUN}/exit.txt', 'w').write(f'rc={rc} daemons_stopped={ok}\n')
        log(f'== {LABEL} done rc={rc} node stopped={ok}')
    sys.exit(rc if ok else 3)

main()
