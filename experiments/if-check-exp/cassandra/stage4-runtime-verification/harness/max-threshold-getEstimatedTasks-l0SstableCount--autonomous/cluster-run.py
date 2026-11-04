#!/usr/bin/env python3
"""Stage-4 cluster tier, one arm per invocation:   MT_TREE=<built tree> MT_OUT=<outdir> cluster-run.py <arm>
Case: max-threshold-getEstimatedTasks-l0SstableCount--autonomous (amendments C1-C7, 2026-10-26). Port slot 6.
Arms: mt4 mt32 mt128 mt32b c64 d32.  One node on 127.0.6.1 (JMX 7160), data on a tmpfs (/mnt/s4b10lm).
Per arm: start node; create ks.standard1 (LCS, max_threshold N); disableautocompaction; stress write n=ROWS (throttled) while a loop
runs `nodetool flush`; PHASE A (compaction held): 60 s sampling, then the end-of-phase record; PHASE B: enableautocompaction at the arm's
throughput, 180 s, end-of-phase record; TRUNCATE instrument control; node stopped on ANY exit.  Lines starting EXPECTED: are checks;
a failed check stops the arm (exit 2) after the node is stopped."""
import os, sys, re, time, json, shutil, subprocess, threading, signal, glob

ARMS = {
  'mt4':   {'mt': 4,   'stcs_off': False, 'tpB': '1'},
  'mt32':  {'mt': 32,  'stcs_off': False, 'tpB': '1'},
  'mt128': {'mt': 128, 'stcs_off': False, 'tpB': '1'},
  'mt32b': {'mt': 32,  'stcs_off': False, 'tpB': '1'},
  'c64':   {'mt': 32,  'stcs_off': False, 'tpB': '64'},
  'd32':   {'mt': 32,  'stcs_off': True,  'tpB': '1'},
}
ROWS = int(os.environ.get('MT_ROWS', 800000))
THROTTLE = os.environ.get('MT_THROTTLE', '1800/s')
PHASE_A_S, PHASE_B_S = int(os.environ.get('MT_A', 60)), int(os.environ.get('MT_B', 180))
MIN_L0 = int(os.environ.get('MT_MINL0', 128))   # lowered only by a shakedown
ADDR, JMX = '127.0.6.1', 7160
MNT = os.environ.get('MT_MNT', '/mnt/s4b10lm')
TREE = os.environ.get('MT_TREE') or sys.exit('set MT_TREE to the copy-source.sh tree (built with ant jar)')
OUT = os.environ.get('MT_OUT') or sys.exit('set MT_OUT to the output directory')
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
    m = re.search(r'SSTable bytes in each level: \[(.*?)\]', txt)
    out['levelBytes'] = [int(re.sub(r'[^0-9]', '', x.split('/')[0]) or 0) for x in m.group(1).split(',')] if m else None
    m = re.search(r'SSTable count: (\d+)', txt); out['sstables'] = int(m.group(1)) if m else None
    m = re.search(r'Space used \(live\): (\d+)', txt); out['live'] = int(m.group(1)) if m else None
    m = re.search(r'Space used \(total\): (\d+)', txt); out['total'] = int(m.group(1)) if m else None
    return out

def byte_term(l0bytes, size_mib=160):
    """LeveledManifest.getEstimatedTasks lines 648-653 for level 0 (amendment C5): ceil(max(0, bytes - (long)(4*size*1.001)) / size)"""
    import math
    size = size_mib * 1048576
    return int(math.ceil(max(0, l0bytes - int(4 * size * 1.001)) / float(size)))

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

def make_conf():
    W = RUN + '/conf'
    shutil.rmtree(W, ignore_errors=True)
    shutil.copytree(TREE + '/conf', W)
    env = open(W + '/cassandra-env.sh').read()
    env2 = env.replace('JMX_PORT="7199"', f'JMX_PORT="{JMX}"'); assert env2 != env
    open(W + '/cassandra-env.sh', 'w').write(env2)
    add = {'cluster_name': f"'mt-{ARM}'", 'num_tokens': '16', 'endpoint_snitch': 'SimpleSnitch', 'listen_address': ADDR, 'rpc_address': ADDR,
           'commitlog_directory': MNT + '/commitlog', 'hints_directory': MNT + '/hints', 'saved_caches_directory': MNT + '/saved_caches',
           'cdc_raw_directory': MNT + '/cdc_raw', 'auto_snapshot': 'false', 'concurrent_compactors': '1', 'compaction_throughput': '1MiB/s',
           'memtable_allocation_type': 'offheap_objects', 'native_transport_timeout': '30s'}
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
    open(W + '/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 max-threshold lines ----\n' + '\n'.join(tail) + '\n')
    log('yaml tail: ' + '; '.join(t for t in tail if not t.startswith(('  ', 'seed', 'data_file'))))
    return W

def start_node():
    expect('no node of this arm running', my_pid() is None)
    sh(f'sudo mkdir -p {MNT} && (mountpoint -q {MNT} || sudo mount -t tmpfs -o size=8g tmpfs {MNT}) && sudo chown $(id -u):$(id -g) {MNT}')
    sh(f'rm -rf {MNT}/* && mkdir -p {MNT}/data {MNT}/commitlog {MNT}/hints {MNT}/saved_caches {MNT}/cdc_raw')
    conf = make_conf()
    logs = RUN + '/logs'; os.makedirs(logs, exist_ok=True)
    opts = f"-Dcassandra.disable_stcs_in_l0={'true' if spec['stcs_off'] else 'false'}"
    sh(f"cd {TREE} && JVM_EXTRA_OPTS='{opts}' CASSANDRA_CONF={conf} CASSANDRA_LOG_DIR={logs} MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M bin/cassandra -p {PIDFILE} > {RUN}/stdout.txt 2>&1")
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
    log(f'node up after {time.time()-t0:.0f} s, pid {state["pid"]}, JVM_EXTRA_OPTS {opts}')

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
    return left is None

def cql(stmt, timeout=300):
    return sh(f'{TREE}/bin/cqlsh {ADDR} -e "{stmt}"', timeout=timeout)

class Sampler(threading.Thread):
    """every 5 s: table-dir file bytes, RssAnon; every 20 s: tablestats + compactionstats raw text"""
    def __init__(self, path):
        super().__init__(daemon=True); self.path = path; self.ev = threading.Event(); self.phase = 'pre'
    def run(self):
        f = open(self.path, 'a'); last = 0
        while not self.ev.is_set():
            ts = time.time()
            try:
                nb, nd = table_files()
                rec = {'t': ts, 'phase': self.phase, 'bytes': nb, 'datafiles': nd, 'rssAnon': rss_anon(state['pid'])}
                if ts - last >= 20:
                    last = ts
                    tx = nodetool('tablestats ks.standard1', quiet=True); cs = nodetool('compactionstats', quiet=True)
                    rec.update({'tablestats': tx, 'compactionstats': cs, 'parsed': parse_tablestats(tx), 'pending': pending(cs)})
                f.write(json.dumps(rec) + '\n'); f.flush()
            except Exception as e:
                f.write(json.dumps({'t': ts, 'error': repr(e)}) + '\n'); f.flush()
            self.ev.wait(5)
    def stop(self): self.ev.set()

def phase_end(tag):
    """end-of-phase record: raw tablestats + compactionstats + tpstats, file bytes (table dir, whole data dir), RssAnon, live heap (class histogram)"""
    tx = nodetool('tablestats ks.standard1'); cs = nodetool('compactionstats'); tp = compaction_completed()
    open(f'{RUN}/tablestats-{tag}.txt', 'w').write(tx); open(f'{RUN}/compactionstats-{tag}.txt', 'w').write(cs)
    nb, nd = table_files(); pid = state['pid']
    rec = {'tag': tag, 't': time.time(), 'tablestats': parse_tablestats(tx), 'pending': pending(cs), 'compactionExecutor': tp,
           'tableBytes': nb, 'dataFiles': nd, 'dataDirBytes': dir_bytes(MNT + '/data'), 'commitlogBytes': dir_bytes(MNT + '/commitlog'),
           'rssAnon': rss_anon(pid), 'liveHeapHistogram': histogram_total(pid), 'rssAnonAfterGC': rss_anon(pid),
           'thresholds': nodetool('getcompactionthreshold ks standard1').strip(), 'throughputCmd': nodetool('getcompactionthroughput').strip()}
    json.dump(rec, open(f'{RUN}/phase-{tag}.json', 'w'), indent=1)
    log(f'phase {tag}: L0..={rec["tablestats"]["levels"]} pending={rec["pending"]} tableBytes={nb} dataDir={rec["dataDirBytes"]} rssAnon={rec["rssAnon"]} heap={rec["liveHeapHistogram"]} compExec={tp}')
    return rec

def main():
    rc = 1
    sam = None
    try:
        log(f'== {ARM} start; tree={TREE} rows={ROWS} throttle={THROTTLE} spec={json.dumps(spec)}')
        start_node()
        sam = Sampler(f'{RUN}/samples.jsonl'); sam.start()
        cql("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
        cols = ', '.join(f'\\"C{i}\\" blob' for i in range(5))
        cql(f"CREATE TABLE ks.standard1 (key blob PRIMARY KEY, {cols}) WITH compression = {{'enabled':'false'}} AND compaction = {{'class':'LeveledCompactionStrategy','max_threshold':'{spec['mt']}'}}")
        th = nodetool('getcompactionthreshold ks standard1')
        mm = re.search(r'max\s*=\s*(\d+)', th)
        expect('table max_threshold', bool(mm) and int(mm.group(1)) == spec['mt'], th.strip().replace('\n', ' ')[:120])
        base = pending(nodetool('compactionstats'))
        expect('baseline pending tasks before the stress is 0', base == 0, f'baseline={base}')
        nodetool('disableautocompaction ks standard1', check=True)
        sac = nodetool('statusautocompaction ks standard1')
        expect('autocompaction disabled for ks.standard1', 'not running' in sac.lower(), sac.strip().replace('\n', ' | ')[:160])
        comp0 = compaction_completed()
        sam.phase = 'write'
        # ---- stress write with a flush loop
        t0 = time.time()
        cmd = (f"{TREE}/tools/bin/cassandra-stress write n={ROWS} -col 'size=FIXED(256)' 'n=FIXED(4)' -pop seq=1..{ROWS} -schema keyspace=ks "
               f"-rate threads=8 throttle={THROTTLE} -node {ADDR} -port jmx={JMX} > {RUN}/stress-write.txt 2>&1")
        log('$ ' + cmd)
        p = subprocess.Popen(['bash', '-c', 'ulimit -n 100000; ' + cmd], stdin=subprocess.DEVNULL)
        flushes = 0
        while p.poll() is None and time.time() - t0 < 1200:
            nodetool('flush ks standard1', quiet=True, timeout=120); flushes += 1
            time.sleep(0.3)
        if p.poll() is None:
            p.kill(); raise Fail('stress write did not finish in 1200 s')
        nodetool('flush ks standard1', quiet=True); flushes += 1
        wr = open(f'{RUN}/stress-write.txt').read()
        errs = re.search(r'Total errors\s*:\s*(\d+)', wr)
        open(f'{RUN}/stress-write.tail.txt', 'w').write('\n'.join(wr.splitlines()[-45:]) + '\n')
        expect('stress completed without errors', bool(errs) and errs.group(1) == '0' and p.returncode == 0, f'errors={errs.group(1) if errs else None} rc={p.returncode} flushes={flushes} secs={time.time()-t0:.0f}')
        json.dump({'flushCalls': flushes, 'writeSeconds': round(time.time() - t0), 'baselinePending': base, 'compactionExecutorBefore': comp0}, open(f'{RUN}/write.json', 'w'))
        # ---- PHASE A (hold)
        sam.phase = 'A'
        log(f'PHASE A: {PHASE_A_S} s of sampling with compaction held')
        time.sleep(PHASE_A_S)
        A = phase_end('A')
        l0 = A['tablestats']['levels'][0]
        expect('limit reached: L0 holds more than 128 sstables', l0 > MIN_L0, f'L0={l0}')
        hist = nodetool('compactionhistory')
        nhist = sum(1 for l in hist.splitlines() if 'standard1' in l)
        open(f'{RUN}/compactionhistory-A.txt', 'w').write(hist)
        expect('no compaction ran on ks.standard1 in the write and phase A', nhist == 0 and A['tablestats']['sstables'] == l0, f"compactionhistory rows for standard1={nhist} sstables={A['tablestats']['sstables']} L0={l0}")
        lb = A['tablestats']['levelBytes']
        expect('levels above 0 are empty (the byte term is L0 only)', all(x == 0 for x in lb[1:]) and all(x == 0 for x in A['tablestats']['levels'][1:]), f"levels={A['tablestats']['levels']} bytes={lb}")
        bt = byte_term(lb[0]); lterm = 0 if spec['stcs_off'] else l0 // spec['mt']; want = lterm + bt
        expect('first trigger: pending tasks = floor(L0/max_threshold) + byte term (STCS term 0 when STCS-in-L0 is off)', A['pending'] - base == want, f"pending={A['pending']} baseline={base} L0={l0} max_threshold={spec['mt']} stcsTerm={lterm} byteTerm={bt} (L0 bytes {lb[0]}) expected={want}")
        # ---- PHASE B (as filed)
        sam.phase = 'B'
        nodetool('enableautocompaction ks standard1', check=True)
        nodetool(f"setcompactionthroughput {spec['tpB']}", check=True)
        expect('throughput set', re.search(rf"\b{spec['tpB']}\b", nodetool('getcompactionthroughput')) is not None, nodetool('getcompactionthroughput').strip())
        log(f'PHASE B: {PHASE_B_S} s with autocompaction on at {spec["tpB"]} MiB/s')
        time.sleep(PHASE_B_S)
        B = phase_end('B')
        sam.phase = 'post'
        # ---- instrument control
        sam.stop(); time.sleep(6)
        cql('TRUNCATE ks.standard1', timeout=600); time.sleep(10)
        nb, nd = table_files()
        json.dump({'bytesAfterTruncate': nb, 'dataFilesAfterTruncate': nd}, open(f'{RUN}/truncate.json', 'w'))
        expect('truncate empties the table directory', nb < 1048576, f'bytes={nb}')
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
