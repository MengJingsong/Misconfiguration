#!/usr/bin/env python3
"""Stage-4 cluster tier, one arm per invocation:   SB_TREE=<built tree> SB_OUT=<outdir> cluster-run.py <arm>
Case: bucket-low-bucket-high-getBuckets-oldAverageSize--autonomous (amendments C1-C4, 2026-10-26). Port slot 8.
Arms: n (0.9,1.1)  d (0.5,1.5)  w (0.01,100)  wc (0.01,100 with max_threshold 4).  min_threshold 4, min_sstable_size 0.
One node on 127.0.8.1 (JMX 7180), data on a tmpfs directory (/dev/shm/s4b10sb).  Autocompaction off during the load; 12 chunks of
`cassandra-stress write n=round(50000*1.15^i) -pop seq=a..b`, `nodetool flush` after each; then enableautocompaction and wait for idle (3 polls).
Lines starting EXPECTED: are instrument/workload checks; a failed check stops the arm (exit 2) after the node is stopped.
The prediction is judged by cluster-analyze.py, not here."""
import os, sys, re, time, json, shutil, subprocess, threading, signal, glob

ARMS = {
  'n':  {'low': 0.9,  'high': 1.1,   'max': 32},
  'd':  {'low': 0.5,  'high': 1.5,   'max': 32},
  'w':  {'low': 0.01, 'high': 100.0, 'max': 32},
  'wc': {'low': 0.01, 'high': 100.0, 'max': 4},
}
CHUNKS = int(os.environ.get('SB_CHUNKS', 12))
BASE_ROWS = int(os.environ.get('SB_BASE_ROWS', 50000))
GROWTH = 1.15
HOLD_S = int(os.environ.get('SB_HOLD', 60))
ADDR, JMX = '127.0.8.1', 7180
MNT = os.environ.get('SB_MNT', '/dev/shm/s4b10sb')
TREE = os.environ.get('SB_TREE') or sys.exit('set SB_TREE to the copy-source.sh tree (built with ant jar)')
OUT = os.environ.get('SB_OUT') or sys.exit('set SB_OUT to the output directory')
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


def pending(txt):
    m = re.search(r'pending tasks:?\s+(\d+)', txt)
    return int(m.group(1)) if m else -1


def compaction_executor():
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



def make_conf():
    W = RUN + '/conf'
    shutil.rmtree(W, ignore_errors=True)
    shutil.copytree(TREE + '/conf', W)
    env = open(W + '/cassandra-env.sh').read()
    env2 = env.replace('JMX_PORT="7199"', f'JMX_PORT="{JMX}"'); assert env2 != env
    open(W + '/cassandra-env.sh', 'w').write(env2)
    add = {'cluster_name': f"'sb-{ARM}'", 'num_tokens': '1', 'endpoint_snitch': 'SimpleSnitch', 'listen_address': ADDR, 'rpc_address': ADDR,
           'commitlog_directory': MNT + '/commitlog', 'hints_directory': MNT + '/hints', 'saved_caches_directory': MNT + '/saved_caches',
           'cdc_raw_directory': MNT + '/cdc_raw', 'auto_snapshot': 'false', 'concurrent_compactors': '1', 'compaction_throughput': '0MiB/s',
           'native_transport_timeout': '30s', 'memtable_cleanup_threshold': '0.99'}
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
    open(W + '/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 bucket lines ----\n' + '\n'.join(tail) + '\n')
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


def table_dirs():
    return sorted(glob.glob(f'{MNT}/data/ks/standard1-*'))

def table_bytes():
    """(all file bytes in the table dir, Data.db bytes, Data.db count)"""
    allb, datab, n = 0, 0, 0
    for d in table_dirs():
        try:
            for f in os.listdir(d):
                p = os.path.join(d, f)
                try: sz = os.path.getsize(p)
                except OSError: continue
                allb += sz
                if f.endswith('-Data.db'): datab += sz; n += 1
        except OSError: pass
    return allb, datab, n

def data_sizes():
    out = []
    for d in table_dirs():
        for f in os.listdir(d):
            if f.endswith('-Data.db'): out.append(os.path.getsize(os.path.join(d, f)))
    return sorted(out)

class Sampler(threading.Thread):
    """every 0.2 s: table-dir bytes (all files / Data.db), Data.db count, RssAnon, phase"""
    def __init__(self, path):
        super().__init__(daemon=True); self.path = path; self.ev = threading.Event(); self.phase = 'load'
    def run(self):
        f = open(self.path, 'a'); n = 0
        while not self.ev.is_set():
            ts = time.time()
            try:
                a, d, c = table_bytes()
                f.write(json.dumps({'t': ts, 'phase': self.phase, 'all': a, 'data': d, 'files': c, 'rssAnon': rss_anon(state['pid']) if n % 2 == 0 else None}) + '\n'); f.flush()
            except Exception as e:
                f.write(json.dumps({'t': ts, 'error': repr(e)}) + '\n'); f.flush()
            n += 1
            self.ev.wait(0.2)
    def stop(self): self.ev.set()

class JStat(threading.Thread):
    """extra (not the frozen criterion): jcmd GC.heap_info used heap (KB) about every second (jstat cannot attach: Cassandra runs with PerfDisableSharedMem)"""
    def __init__(self, path, sam):
        super().__init__(daemon=True); self.path = path; self.sam = sam; self.ev = threading.Event()
    def run(self):
        f = open(self.path, 'a')
        while not self.ev.is_set():
            try:
                r = subprocess.run(['jcmd', str(state['pid']), 'GC.heap_info'], capture_output=True, text=True, timeout=20)
                m = re.search(r'total (\d+)K, used (\d+)K', r.stdout)
                f.write(json.dumps({'t': time.time(), 'phase': self.sam.phase, 'usedKB': int(m.group(2)), 'totalKB': int(m.group(1))}) + '\n'); f.flush()
            except Exception as e:
                f.write(json.dumps({'t': time.time(), 'error': repr(e)}) + '\n'); f.flush()
            self.ev.wait(0.3)
    def stop(self): self.ev.set()

def wait_idle(maxs=600):
    """three consecutive polls 5 s apart with pending 0 and no active/pending CompactionExecutor task; returns (reached, seconds)"""
    t0 = time.time(); ok = 0
    while time.time() - t0 < maxs:
        cs = nodetool('compactionstats', quiet=True); ce = compaction_executor()
        if pending(cs) == 0 and ce and ce['active'] == 0 and ce['pending'] == 0: ok += 1
        else: ok = 0
        if ok >= 3: return True, round(time.time() - t0)
        time.sleep(5)
    return False, round(time.time() - t0)

def chunk(i, start, rows):
    cmd = (f"{TREE}/tools/bin/cassandra-stress write n={rows} -pop 'seq={start}..{start+rows-1}' -rate threads=16 -schema keyspace=ks "
           f"-node {ADDR} -port jmx={JMX} > {RUN}/stress-{i:02d}.txt 2>&1")
    p = subprocess.run(['bash', '-c', 'ulimit -n 100000; ' + cmd], stdin=subprocess.DEVNULL, timeout=1800)
    wr = open(f'{RUN}/stress-{i:02d}.txt').read()
    errs = re.search(r'Total errors\s*:\s*(\d+)', wr)
    open(f'{RUN}/stress-{i:02d}.tail.txt', 'w').write('\n'.join(wr.splitlines()[-30:]) + '\n')
    expect(f'chunk {i}: stress wrote {rows} rows without errors', bool(errs) and errs.group(1) == '0' and p.returncode == 0, f'errors={errs.group(1) if errs else None} rc={p.returncode}')
    nodetool('flush ks standard1', check=True)

def main():
    rc = 1
    sam = None
    try:
        rows = [round(BASE_ROWS * GROWTH ** i) for i in range(CHUNKS)]
        log(f'== {ARM} start; tree={TREE} chunks={CHUNKS} rows={rows} spec={json.dumps(spec)}')
        start_node()
        sam = Sampler(f'{RUN}/samples.jsonl'); sam.start()
        js = JStat(f'{RUN}/heapinfo.jsonl', sam); js.start(); state['js'] = js
        nodetool('setlogginglevel org.apache.cassandra.db.compaction TRACE', check=True)
        cql("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
        cols = ', '.join(f'\\"C{i}\\" blob' for i in range(5))
        cql(f"CREATE TABLE ks.standard1 (key blob PRIMARY KEY, {cols}) WITH compression = {{'enabled':'false'}} AND compaction = {{'class':'SizeTieredCompactionStrategy','min_threshold':'4','max_threshold':'32','min_sstable_size':'0'}}")
        cql(f"ALTER TABLE ks.standard1 WITH compaction = {{'class':'SizeTieredCompactionStrategy','min_threshold':'4','max_threshold':'{spec['max']}','min_sstable_size':'0','bucket_low':'{spec['low']}','bucket_high':'{spec['high']}'}}")
        sc = cql("SELECT compaction FROM system_schema.tables WHERE keyspace_name='ks' AND table_name='standard1'")
        open(f'{RUN}/schema-compaction.txt', 'w').write(sc)
        ok = (f"'bucket_low': '{spec['low']}'" in sc and f"'bucket_high': '{spec['high']}'" in sc and f"'max_threshold': '{spec['max']}'" in sc
              and "'min_threshold': '4'" in sc and "'min_sstable_size': '0'" in sc)
        expect('schema compaction map holds the arm\'s bucket_low/bucket_high/max_threshold (read back)', ok, ' '.join(sc.split())[:240])
        th = nodetool('getcompactionthreshold ks standard1')
        mn, mx = re.search(r'min\s*=\s*(\d+)', th), re.search(r'max\s*=\s*(\d+)', th)
        expect('node reports thresholds 4/<arm max>', bool(mn and mx) and int(mn.group(1)) == 4 and int(mx.group(1)) == spec['max'], th.strip().replace('\n', ' ')[:120])
        nodetool('disableautocompaction ks standard1', check=True)
        sac = nodetool('statusautocompaction ks standard1')
        expect('autocompaction is off for ks.standard1 during the load', 'not running' in sac.lower() or 'false' in sac.lower(), sac.strip().replace('\n', ' | ')[:200])
        sam.phase = 'load'
        start = 1; traj = []
        for i in range(CHUNKS):
            chunk(i + 1, start, rows[i]); start += rows[i]
            a, d, c = table_bytes()
            traj.append({'chunk': i + 1, 'rows': rows[i], 't': time.time(), 'files': c, 'dataBytes': d})
            log(f'chunk {i+1}: rows={rows[i]} Data.db files={c} dataBytes={d}')
            if i == 0:
                expect('first flush: exactly one sstable', c == 1, f'files={c}')
            json.dump(traj, open(f'{RUN}/trajectory.json', 'w'), indent=1)
        sizes = data_sizes()
        ratios = [round(b / a, 4) for a, b in zip(sizes, sizes[1:])]
        total = sum(sizes)
        json.dump({'sizes': sizes, 'ratios': ratios, 'total': total}, open(f'{RUN}/presizes.json', 'w'))
        expect('12 sstables after the last flush, none compacted during the load', len(sizes) == CHUNKS, f'n={len(sizes)}')
        expect('sstable sizes ascend with consecutive ratios in [1.10,1.20] (narrow cannot join neighbours, default can)', all(1.10 <= r <= 1.20 for r in ratios), f'ratios={ratios}')
        expect('total Data.db bytes between 100 MB and 800 MB', float(os.environ.get('SB_MIN_TOTAL', 100e6)) <= total <= 800e6, f'total={total}')
        hist0 = nodetool('compactionhistory', quiet=True)
        expect('no compaction ran during the load (history has no ks standard1 row)', 'standard1' not in hist0, '')
        tx0 = nodetool('tablestats ks.standard1'); open(f'{RUN}/tablestats-pre.txt', 'w').write(tx0)
        a0, d0, c0 = table_bytes()
        # compaction phase
        sam.phase = 'compact'
        t_enable = time.time()
        nodetool('enableautocompaction ks standard1', check=True)
        sac = nodetool('statusautocompaction ks standard1')
        expect('autocompaction on again', 'running' in sac.lower() and 'not running' not in sac.lower(), sac.strip().replace('\n', ' | ')[:200])
        reached, secs = wait_idle()
        t_idle = time.time()
        log(f'idle reached={reached} after {secs} s')
        sam.phase = 'hold'; time.sleep(HOLD_S)
        hist = nodetool('compactionhistory'); open(f'{RUN}/compactionhistory.txt', 'w').write(hist)
        tx = nodetool('tablestats ks.standard1'); open(f'{RUN}/tablestats-end.txt', 'w').write(tx)
        a1, d1, c1 = table_bytes()
        pid = state['pid']
        json.dump({'idleReached': reached, 'idleSeconds': secs, 't_enable': t_enable, 't_idle': t_idle, 'pre': {'all': a0, 'data': d0, 'files': c0}, 'end': {'all': a1, 'data': d1, 'files': c1},
                   'liveHeapHistogram': histogram_total(pid), 'rssAnonEnd': rss_anon(pid)}, open(f'{RUN}/phase-end.json', 'w'), indent=1)
        sh(f"grep -E 'Compacting \\(|Compacted \\(|Compaction buckets are' {RUN}/logs/system.log {RUN}/logs/debug.log > {RUN}/compaction-lines.txt || true", check=False, quiet=True)
        expect('instrument: TRACE "Compaction buckets are" lines reached the log', int(sh(f"grep -c 'Compaction buckets are' {RUN}/compaction-lines.txt || true", quiet=True, check=False).strip() or 0) > 0, '')
        expect('idle reached', reached, f'{secs} s')
        sam.stop(); state['js'].stop()
        rc = 0
    except Exception as e:
        log(f'FAILED: {e!r}'); rc = 2
    finally:
        if sam: sam.stop()
        if state.get('js'): state['js'].stop()
        ok = stop_node()
        open(f'{RUN}/exit.txt', 'w').write(f'rc={rc} node_stopped={ok}\n')
        log(f'== {ARM} done rc={rc} node stopped={ok}')
    sys.exit(rc if ok else 3)

main()
