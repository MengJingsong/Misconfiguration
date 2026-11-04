#!/usr/bin/env python3
"""Stage-4 cluster tier, one arm per invocation:   SM_TREE=<built tree> SM_OUT=<outdir> cluster-run.py <arm>
Case: compaction-min-threshold-mostInterestingBucket-minThreshold--autonomous (amendments A1, C1-C5, 2026-10-26). Port slot 7.
Arms: m2 m4 m16 m32 (min_threshold M, max 32; m32 ends with the runtime flip to 4/32, C4a) and mm4 (min 4, max 4, B3e step 6).
One node on 127.0.7.1 (JMX 7170), data on a tmpfs directory (/dev/shm/s4b10sm).  20 chunks of `cassandra-stress write n=100000 -pop dist=UNIFORM(1..200000)`,
`nodetool flush` after each.  End-state record after an idle test + 120 s hold.  Lines starting EXPECTED: are instrument/workload checks;
a failed check stops the arm (exit 2) after the node is stopped.  The prediction is judged by cluster-analyze.py, not here."""
import os, sys, re, time, json, shutil, subprocess, threading, signal, glob

ARMS = {
  'm2':  {'min': 2,  'max': 32, 'flip': False},
  'm4':  {'min': 4,  'max': 32, 'flip': False},
  'm16': {'min': 16, 'max': 32, 'flip': False},
  'm32': {'min': 32, 'max': 32, 'flip': True},
  'mm4': {'min': 4,  'max': 4,  'flip': False},
}
CHUNKS = int(os.environ.get('SM_CHUNKS', 20))
CHUNK_N = int(os.environ.get('SM_CHUNK_N', 100000))
HOLD_S = int(os.environ.get('SM_HOLD', 120))
ADDR, JMX = '127.0.7.1', 7170
MNT = os.environ.get('SM_MNT', '/dev/shm/s4b10sm')
TREE = os.environ.get('SM_TREE') or sys.exit('set SM_TREE to the copy-source.sh tree (built with ant jar)')
OUT = os.environ.get('SM_OUT') or sys.exit('set SM_OUT to the output directory')
ARM = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in ARMS else sys.exit('usage: cluster-run.py <arm>  arms: ' + ' '.join(ARMS))
spec = ARMS[ARM]
RUN = os.path.join(OUT, ARM); os.makedirs(RUN, exist_ok=True)
CMDLOG = open(os.path.join(RUN, 'commands.log'), 'a')
NODETOOL = f'{TREE}/bin/nodetool -h 127.0.0.1 -p {JMX}'
PIDFILE = os.path.join(RUN, 'node.pid')
state = {'pid': None}

def log(msg):
    line = f'{time.strftime("%H:%M:%S")} {msg}'
    print(line, flush=True); CMDLOG.write(line + '\n'); CMDLOG.flush()

class Fail(Exception): pass

def expect(name, ok, detail=''):
    log(f'EXPECTED: {name}: {"PASS" if ok else "FAIL"} {detail}')
    if not ok: raise Fail(f'{name} {detail}')

def sh(cmd, timeout=600, env=None, check=True, quiet=False):
    if not quiet: log('$ ' + cmd)
    e = dict(os.environ); e.update(env or {})
    r = subprocess.run(['bash', '-c', 'ulimit -n 100000; ' + cmd], capture_output=True, text=True, timeout=timeout, env=e, stdin=subprocess.DEVNULL)
    if not quiet:
        CMDLOG.write((r.stdout or '')[-2500:] + (r.stderr or '')[-1000:] + '\n'); CMDLOG.flush()
    if check and r.returncode != 0:
        raise Fail(f'command failed ({r.returncode}): {cmd}\n{r.stderr[-600:]}')
    return r.stdout

def nodetool(c, timeout=180, check=False, quiet=False):
    return sh(f'{NODETOOL} {c}', timeout=timeout, check=check, quiet=quiet)

def my_pid():
    try:
        pid = int(open(PIDFILE).read().strip())
        cmd = open(f'/proc/{pid}/cmdline').read()
        return pid if ('CassandraDaemon' in cmd and RUN in cmd) else None
    except Exception:
        return None

def rss_anon(pid):
    try:
        for l in open(f'/proc/{pid}/status'):
            if l.startswith('RssAnon:'): return int(l.split()[1]) * 1024
    except Exception: pass
    return -1

def table_dirs():
    return sorted(glob.glob(f'{MNT}/data/ks/standard1-*'))

def dir_bytes(path):
    n = 0
    for root, _, files in os.walk(path):
        for f in files:
            try: n += os.path.getsize(os.path.join(root, f))
            except OSError: pass
    return n

def table_files():
    n, data = 0, 0
    for d in table_dirs():
        for f in os.listdir(d):
            p = os.path.join(d, f)
            if os.path.isfile(p):
                n += os.path.getsize(p)
                if f.endswith('-Data.db'): data += 1
    return n, data

def parse_tablestats(txt):
    out = {}
    m = re.search(r'SSTables in each level: \[(.*?)\]', txt)
    out['levels'] = [int(re.sub(r'[^0-9]', '', x.split('/')[0]) or 0) for x in m.group(1).split(',')] if m else None
    m = re.search(r'SSTable count: (\d+)', txt); out['sstables'] = int(m.group(1)) if m else None
    m = re.search(r'Space used \(live\): (\d+)', txt); out['live'] = int(m.group(1)) if m else None
    m = re.search(r'Space used \(total\): (\d+)', txt); out['total'] = int(m.group(1)) if m else None
    return out

def pending(txt):
    m = re.search(r'pending tasks:?\s+(\d+)', txt)
    return int(m.group(1)) if m else -1

def compaction_completed():
    for l in nodetool('tpstats', quiet=True).splitlines():
        if l.startswith('CompactionExecutor'):
            p = l.split(); return {'active': int(p[1]), 'pending': int(p[2]), 'completed': int(p[3])}
    return None

def histogram_total(pid):
    out = sh(f'jcmd {pid} GC.class_histogram', quiet=True, check=False, timeout=300)
    for l in reversed(out.strip().splitlines()):
        m = re.match(r'\s*Total\s+(\d+)\s+(\d+)', l)
        if m: return int(m.group(2))
    return -1


def table_dirs():
    return sorted(glob.glob(f'{MNT}/data/ks/standard1-*'))

def dir_bytes(path):
    n = 0
    for root, _, files in os.walk(path):
        for f in files:
            try: n += os.path.getsize(os.path.join(root, f))
            except OSError: pass
    return n

def table_files():
    n, data = 0, 0
    for d in table_dirs():
        for f in os.listdir(d):
            p = os.path.join(d, f)
            if os.path.isfile(p):
                n += os.path.getsize(p)
                if f.endswith('-Data.db'): data += 1
    return n, data

def parse_tablestats(txt):
    out = {}
    def num(pat):
        m = re.search(pat + r':\s*([0-9.]+)', txt)
        return float(m.group(1)) if m else None
    out['sstables'] = int(num(r'SSTable count') or -1)
    out['live'] = num(r'Space used \(live\)'); out['total'] = num(r'Space used \(total\)')
    out['bloomOffHeap'] = num(r'Bloom filter off heap memory used'); out['summaryOffHeap'] = num(r'Index summary off heap memory used')
    out['compressionOffHeap'] = num(r'Compression metadata off heap memory used'); out['keys'] = num(r'Number of partitions \(estimate\)')
    return out

def pending(txt):
    m = re.search(r'pending tasks:?\s+(\d+)', txt)
    return int(m.group(1)) if m else -1

def compaction_executor():
    for l in nodetool('tpstats', quiet=True).splitlines():
        if l.startswith('CompactionExecutor'):
            p = l.split(); return {'active': int(p[1]), 'pending': int(p[2]), 'completed': int(p[3])}
    return None

def history_rows():
    return sum(1 for l in nodetool('compactionhistory', quiet=True).splitlines() if 'standard1' in l)

def trace_lines():
    try: return int(sh(f"grep -c 'Compaction buckets are' {RUN}/logs/debug.log", quiet=True, check=False).strip() or 0)
    except Exception: return -1

def histogram_total(pid):
    out = sh(f'jcmd {pid} GC.class_histogram', quiet=True, check=False, timeout=300)
    for l in reversed(out.strip().splitlines()):
        m = re.match(r'\s*Total\s+(\d+)\s+(\d+)', l)
        if m: return int(m.group(2))
    return -1

def make_conf():
    W = RUN + '/conf'
    shutil.rmtree(W, ignore_errors=True)
    shutil.copytree(TREE + '/conf', W)
    env = open(W + '/cassandra-env.sh').read()
    env2 = env.replace('JMX_PORT="7199"', f'JMX_PORT="{JMX}"'); assert env2 != env
    open(W + '/cassandra-env.sh', 'w').write(env2)
    add = {'cluster_name': f"'sm-{ARM}'", 'num_tokens': '1', 'endpoint_snitch': 'SimpleSnitch', 'listen_address': ADDR, 'rpc_address': ADDR,
           'commitlog_directory': MNT + '/commitlog', 'hints_directory': MNT + '/hints', 'saved_caches_directory': MNT + '/saved_caches',
           'cdc_raw_directory': MNT + '/cdc_raw', 'auto_snapshot': 'false', 'concurrent_compactors': '1', 'compaction_throughput': '0MiB/s',
           'native_transport_timeout': '30s'}
    lines = open(TREE + '/conf/cassandra.yaml').read().splitlines()
    keys = set(add) | {'seed_provider', 'data_file_directories'}
    out, skip = [], False
    for l in lines:
        m = re.match(r'^([A-Za-z_]+):', l)
        if m:
            skip = m.group(1) in keys
            if skip: continue
        elif skip and (l.startswith((' ', '\t', '-')) or not l.strip() or l.lstrip().startswith('#')):
            continue
        else: skip = False
        out.append(l)
    tail = [f'{k}: {v}' for k, v in add.items()]
    tail += ['seed_provider:', '  - class_name: org.apache.cassandra.locator.SimpleSeedProvider', '    parameters:', f'      - seeds: "{ADDR}:7000"',
             'data_file_directories:', f'    - {MNT}/data']
    open(W + '/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 min-threshold lines ----\n' + '\n'.join(tail) + '\n')
    log('yaml tail: ' + '; '.join(t for t in tail if not t.startswith(('  ', 'seed', 'data_file'))))
    return W

def start_node():
    expect('no node of this arm running', my_pid() is None)
    sh(f'rm -rf {MNT} && mkdir -p {MNT}/data {MNT}/commitlog {MNT}/hints {MNT}/saved_caches {MNT}/cdc_raw')
    conf = make_conf()
    logs = RUN + '/logs'; os.makedirs(logs, exist_ok=True)
    sh(f"cd {TREE} && CASSANDRA_CONF={conf} CASSANDRA_LOG_DIR={logs} MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M bin/cassandra -p {PIDFILE} > {RUN}/stdout.txt 2>&1")
    for _ in range(40):
        time.sleep(1)
        if my_pid(): break
    else: raise Fail('node did not start; see ' + RUN + '/stdout.txt')
    t0 = time.time()
    while time.time() - t0 < 300:
        if not my_pid(): raise Fail('node died during start')
        st = nodetool('status', quiet=True); sb = nodetool('statusbinary', quiet=True)
        if re.search(r'^UN\s', st, re.M) and re.search(r'^running\s*$', sb, re.M): break
        time.sleep(3)
    else: raise Fail('not UN within 300 s')
    state['pid'] = my_pid()
    log(f'node up after {time.time()-t0:.0f} s, pid {state["pid"]}')

def stop_node():
    pid = my_pid() or state['pid']
    if pid:
        try: os.kill(pid, signal.SIGTERM)
        except ProcessLookupError: pass
        for _ in range(40):
            time.sleep(1.5)
            if not os.path.exists(f'/proc/{pid}'): break
        else:
            try: os.kill(pid, signal.SIGKILL)
            except ProcessLookupError: pass
            time.sleep(3)
    left = my_pid()
    log('this arm\'s node left after stop: ' + (str(left) if left else 'none'))
    sh(f'rm -rf {MNT}', check=False, quiet=True)
    return left is None

def cql(stmt, timeout=300):
    return sh(f'{TREE}/bin/cqlsh {ADDR} -e "{stmt}"', timeout=timeout)

class Sampler(threading.Thread):
    """every 2 s: table-dir file bytes + data files, RssAnon (the peak of bytes is read from this file)"""
    def __init__(self, path):
        super().__init__(daemon=True); self.path = path; self.ev = threading.Event(); self.phase = 'pre'
    def run(self):
        f = open(self.path, 'a')
        while not self.ev.is_set():
            ts = time.time()
            try:
                nb, nd = table_files()
                f.write(json.dumps({'t': ts, 'phase': self.phase, 'bytes': nb, 'datafiles': nd, 'rssAnon': rss_anon(state['pid'])}) + '\n'); f.flush()
            except Exception as e:
                f.write(json.dumps({'t': ts, 'error': repr(e)}) + '\n'); f.flush()
            self.ev.wait(2)
    def stop(self): self.ev.set()

def wait_idle(maxs=300):
    """three consecutive polls 10 s apart with pending 0 and no active CompactionExecutor task; returns (reached, seconds)"""
    t0 = time.time(); ok = 0
    while time.time() - t0 < maxs:
        cs = nodetool('compactionstats', quiet=True); ce = compaction_executor()
        if pending(cs) == 0 and ce and ce['active'] == 0 and ce['pending'] == 0: ok += 1
        else: ok = 0
        if ok >= 3: return True, round(time.time() - t0)
        time.sleep(10)
    return False, round(time.time() - t0)

def phase_end(tag):
    tx = nodetool('tablestats ks.standard1'); cs = nodetool('compactionstats'); ce = compaction_executor()
    hist = nodetool('compactionhistory')
    open(f'{RUN}/tablestats-{tag}.txt', 'w').write(tx); open(f'{RUN}/compactionstats-{tag}.txt', 'w').write(cs); open(f'{RUN}/compactionhistory-{tag}.txt', 'w').write(hist)
    nb, nd = table_files(); pid = state['pid']
    rec = {'tag': tag, 't': time.time(), 'tablestats': parse_tablestats(tx), 'pending': pending(cs), 'compactionExecutor': ce,
           'historyRows': sum(1 for l in hist.splitlines() if 'standard1' in l), 'traceBucketLines': trace_lines(),
           'tableBytes': nb, 'dataFiles': nd, 'dataDirBytes': dir_bytes(MNT + '/data'),
           'rssAnon': rss_anon(pid), 'liveHeapHistogram': histogram_total(pid), 'rssAnonAfterGC': rss_anon(pid),
           'thresholds': nodetool('getcompactionthreshold ks standard1').strip()}
    json.dump(rec, open(f'{RUN}/phase-{tag}.json', 'w'), indent=1)
    log(f'phase {tag}: sstables={rec["tablestats"]["sstables"]} files={nd} tableBytes={nb} total={rec["tablestats"]["total"]} bloom={rec["tablestats"]["bloomOffHeap"]} summary={rec["tablestats"]["summaryOffHeap"]} hist={rec["historyRows"]} trace={rec["traceBucketLines"]} rssAnon={rec["rssAnon"]} heap={rec["liveHeapHistogram"]}')
    return rec

def chunk(i):
    cmd = (f"{TREE}/tools/bin/cassandra-stress write n={CHUNK_N} -pop 'dist=UNIFORM(1..200000)' -rate threads=16 -schema keyspace=ks "
           f"-node {ADDR} -port jmx={JMX} > {RUN}/stress-{i:02d}.txt 2>&1")
    p = subprocess.run(['bash', '-c', 'ulimit -n 100000; ' + cmd], stdin=subprocess.DEVNULL, timeout=900)
    wr = open(f'{RUN}/stress-{i:02d}.txt').read()
    errs = re.search(r'Total errors\s*:\s*(\d+)', wr)
    open(f'{RUN}/stress-{i:02d}.tail.txt', 'w').write('\n'.join(wr.splitlines()[-30:]) + '\n')
    expect(f'chunk {i}: stress completed without errors', bool(errs) and errs.group(1) == '0' and p.returncode == 0, f'errors={errs.group(1) if errs else None} rc={p.returncode}')
    nodetool('flush ks standard1', check=True)

def main():
    rc = 1
    sam = None
    try:
        log(f'== {ARM} start; tree={TREE} chunks={CHUNKS}x{CHUNK_N} spec={json.dumps(spec)}')
        start_node()
        sam = Sampler(f'{RUN}/samples.jsonl'); sam.start()
        nodetool('setlogginglevel org.apache.cassandra.db.compaction TRACE', check=True)
        cql("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
        cols = ', '.join(f'\\"C{i}\\" blob' for i in range(5))
        cql(f"CREATE TABLE ks.standard1 (key blob PRIMARY KEY, {cols}) WITH compression = {{'enabled':'false'}} AND compaction = {{'class':'SizeTieredCompactionStrategy','min_threshold':'{spec['min']}','max_threshold':'{spec['max']}'}}")
        th = nodetool('getcompactionthreshold ks standard1')
        mn, mx = re.search(r'min\s*=\s*(\d+)', th), re.search(r'max\s*=\s*(\d+)', th)
        expect('table thresholds are the arm\'s', bool(mn and mx) and int(mn.group(1)) == spec['min'] and int(mx.group(1)) == spec['max'], th.strip().replace('\n', ' ')[:120])
        sac = nodetool('statusautocompaction ks standard1')
        expect('autocompaction running for ks.standard1', 'running' in sac.lower() and 'not running' not in sac.lower(), sac.strip().replace('\n', ' | ')[:160])
        sam.phase = 'write'
        traj = []
        for i in range(1, CHUNKS + 1):
            chunk(i)
            tx = nodetool('tablestats ks.standard1', quiet=True); p = parse_tablestats(tx); nb, nd = table_files()
            traj.append({'chunk': i, 't': time.time(), 'sstables': p['sstables'], 'files': nd, 'bytes': nb, 'total': p['total'], 'historyRows': history_rows()})
            log(f'chunk {i}: sstables={p["sstables"]} files={nd} bytes={nb} historyRows={traj[-1]["historyRows"]}')
            if i == 1:
                expect('first flush: one sstable between 1 MiB and 50 MiB (one STCS size bucket; the limit-side workload reaches the bucket)', p['sstables'] == 1 and 1048576 < nb < 50 * 1048576, f'sstables={p["sstables"]} bytes={nb}')
            if i == 3:
                tl = trace_lines()
                expect('instrument: TRACE "Compaction buckets are" lines reach debug.log', tl > 0, f'lines={tl}')
            json.dump(traj, open(f'{RUN}/trajectory.json', 'w'), indent=1)
        sam.phase = 'idle'
        reached, secs = wait_idle()
        log(f'idle reached={reached} after {secs} s')
        json.dump({'idleReached': reached, 'idleSeconds': secs}, open(f'{RUN}/idle-end.json', 'w'))
        sam.phase = 'hold'; time.sleep(HOLD_S)
        E = phase_end('end')
        expect('instrument: tablestats SSTable count equals Data.db files on disk', E['tablestats']['sstables'] == E['dataFiles'], f"tablestats={E['tablestats']['sstables']} files={E['dataFiles']}")
        if spec['flip']:
            sam.phase = 'flip'
            nodetool('setcompactionthreshold ks standard1 4 32', check=True)
            th = nodetool('getcompactionthreshold ks standard1')
            expect('runtime flip applied (min 4, max 32)', re.search(r'min\s*=\s*4', th) is not None and re.search(r'max\s*=\s*32', th) is not None, th.strip().replace('\n', ' ')[:120])
            reached, secs = wait_idle()
            log(f'flip idle reached={reached} after {secs} s')
            json.dump({'idleReached': reached, 'idleSeconds': secs}, open(f'{RUN}/idle-flip.json', 'w'))
            time.sleep(60)
            F = phase_end('flip')
        sam.stop()
        rc = 0
    except Exception as e:
        log(f'FAILED: {e!r}'); rc = 2
    finally:
        if sam: sam.stop()
        ok = stop_node()
        open(f'{RUN}/exit.txt', 'w').write(f'rc={rc} node_stopped={ok}\n')
        log(f'== {ARM} done rc={rc} node stopped={ok}')
    sys.exit(rc if ok else 3)

main()
