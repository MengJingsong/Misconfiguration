#!/usr/bin/env python3
"""Stage-4 cluster tier, one label per invocation:  L0_TREE=<tree> L0_OUT=<dir> cluster-run.py <label>
Case: max-compacting-l0-getSTCSInL0CompactionCandidate-l0SstableCount--autonomous  (B3, amendments A3-A5 of 2026-10-26)
One node on 127.0.4.1 (port slot 4: JMX 7140, native 9042) with data on a dedicated tmpfs (/mnt/s4lz); cassandra-stress write
(throttled) while a loop runs `nodetool flush ks standard1`; samplers; lag-end snapshot; drain (A, C, D); TRUNCATE control; node stopped.
Stops at a failed first-trigger check (no sstable after the first 40 s of writing) and the node is stopped on any exit."""

ROWS = 1500000
COLS = 'size=FIXED(1000) n=FIXED(1)'
THREADS = 64
THROTTLE = '5000/s'
# label -> settings. flag = -Dcassandra.disable_stcs_in_l0 ; compaction_off = disableautocompaction before the write
LABELS = {
  'A': {'throughput': '1MiB/s', 'compactors': 1, 'flag': False, 'compaction_off': False, 'drain': True},
  'B': {'throughput': '1MiB/s', 'compactors': 1, 'flag': False, 'compaction_off': True,  'drain': False},
  'C': {'throughput': '1MiB/s', 'compactors': 1, 'flag': True,  'compaction_off': False, 'drain': True},
  'D': {'throughput': '0MiB/s', 'compactors': 4, 'flag': False, 'compaction_off': False, 'drain': True, 'drain_boost': False},
}
COMPACTION = "{'class':'LeveledCompactionStrategy','sstable_size_in_mb':'10','fanout_size':'10'}"

import os, sys, re, time, json, shutil, subprocess, threading, signal, glob

TREE = os.environ.get('L0_TREE') or sys.exit('set L0_TREE to the copy-source.sh tree the node runs from')
OUT = os.environ.get('L0_OUT') or sys.exit('set L0_OUT to the run output directory')
MNT = os.environ.get('L0_MNT', '/mnt/s4lz')
ADDR = '127.0.4.1'; JMX = 7140
LABEL = sys.argv[1] if len(sys.argv) > 1 else sys.exit('usage: cluster-run.py <label>  labels: ' + ' '.join(LABELS))
N_ROWS = int(os.environ.get('L0_ROWS', ROWS))           # overridden only by a shakedown
RUN = os.path.join(OUT, LABEL)
os.makedirs(RUN, exist_ok=True)
CMDLOG = open(os.path.join(RUN, 'commands.log'), 'a')
NODETOOL = f'{TREE}/bin/nodetool -h 127.0.0.1 -p {JMX}'
TN = 'standard1'
state = {'pid': None}

def log(msg):
    line = f'{time.strftime("%H:%M:%S")} {msg}'
    print(line, flush=True); CMDLOG.write(line + '\n'); CMDLOG.flush()

def sh(cmd, timeout=600, env=None, check=True):
    log('$ ' + cmd)
    e = dict(os.environ); e.update(env or {})
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=e, stdin=subprocess.DEVNULL)
    CMDLOG.write((r.stdout or '')[-3000:] + (r.stderr or '')[-1500:] + '\n'); CMDLOG.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed ({r.returncode}): {cmd}\n{r.stderr[-800:]}')
    return r.stdout

def my_daemons():
    """only the daemon of THIS run: java CassandraDaemon whose command line holds our conf dir (other cases run on this node)"""
    out = subprocess.run(['ps', '-eo', 'pid,args'], capture_output=True, text=True).stdout
    return [l for l in out.splitlines() if re.search(r'(^|/)java .*CassandraDaemon', l) and f'{RUN}/conf' in l]

def table_dirs():
    return sorted(glob.glob(f'{MNT}/data/ks/{TN}-*'))

def files_bytes(dirs):
    n, data = 0, []
    for d in dirs:
        for f in os.listdir(d):
            p = os.path.join(d, f)
            if os.path.isfile(p):
                try: sz = os.path.getsize(p)
                except FileNotFoundError: continue
                n += sz
                if f.endswith('-Data.db'): data.append(sz)
    return n, data

def make_conf(spec):
    conf = os.path.join(RUN, 'conf')
    shutil.rmtree(conf, ignore_errors=True)
    shutil.copytree(f'{TREE}/conf', conf)
    y = open(f'{conf}/cassandra.yaml').read()
    def setk(k, v):
        nonlocal y
        if re.search(rf'^{k}:', y, re.M): y = re.sub(rf'^{k}:.*$', f'{k}: {v}', y, flags=re.M)
        else: y += f'\n{k}: {v}\n'
    setk('cluster_name', f"'s4lz-{LABEL}'")
    setk('listen_address', ADDR); setk('rpc_address', ADDR)
    y = re.sub(r'(seeds:\s*)"[^"]*"', rf'\1"{ADDR}:7000"', y)
    setk('hints_directory', f'{MNT}/hints'); setk('commitlog_directory', f'{MNT}/commitlog'); setk('saved_caches_directory', f'{MNT}/saved_caches')
    y = re.sub(r'^data_file_directories:\n(\s+- .*\n)+', '', y, flags=re.M)
    y += f'\ndata_file_directories:\n    - {MNT}/data\n'
    setk('auto_snapshot', 'false'); setk('compaction_throughput', spec['throughput']); setk('concurrent_compactors', spec['compactors'])
    setk('memtable_flush_writers', 2)
    open(f'{conf}/cassandra.yaml', 'w').write(y)
    env = open(f'{conf}/cassandra-env.sh').read()
    env, k = re.subn(r'^JMX_PORT="7199"', f'JMX_PORT="{JMX}"', env, flags=re.M)
    assert k == 1, 'JMX_PORT line not found in cassandra-env.sh'
    open(f'{conf}/cassandra-env.sh', 'w').write(env)
    return conf

def start_node(spec):
    assert not my_daemons(), 'a CassandraDaemon of this run is already running'
    sh(f'sudo mkdir -p {MNT} && (mountpoint -q {MNT} || sudo mount -t tmpfs -o size=12g tmpfs {MNT}) && sudo chown $(id -u):$(id -g) {MNT}')
    sh(f'rm -rf {MNT}/* && mkdir -p {MNT}/data {MNT}/commitlog {MNT}/hints {MNT}/saved_caches')
    conf = make_conf(spec)
    logs = os.path.join(RUN, 'logs'); os.makedirs(logs, exist_ok=True)
    extra = '-Dcassandra.disable_stcs_in_l0=true' if spec['flag'] else ''
    env = f'CASSANDRA_CONF={conf} CASSANDRA_LOG_DIR={logs} MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M' + (f' JVM_EXTRA_OPTS="{extra}"' if extra else '')
    sh(f'ulimit -n 100000; cd {TREE} && ( {env} setsid nohup bin/cassandra -f -p {RUN}/pid < /dev/null > {RUN}/node.out 2>&1 & )')
    t0 = time.time()
    while time.time() - t0 < 240:
        time.sleep(3)
        if time.time() - t0 > 20 and not my_daemons(): raise RuntimeError('node died during start; see node.out')
        st = subprocess.run(f'{NODETOOL} status 2>/dev/null | grep -c "^UN"; {NODETOOL} statusbinary 2>/dev/null', shell=True, capture_output=True, text=True, stdin=subprocess.DEVNULL).stdout
        if st.split()[:2] == ['1', 'running']: break   # 'not running' contains 'running': compare the whole word
    else: raise RuntimeError('node did not come up')
    d = my_daemons()
    if not d: raise RuntimeError('node died during start; see node.out')
    state['pid'] = int(d[0].split()[0])
    open(f'{RUN}/jvm-args.txt', 'w').write(d[0] + '\n')
    log(f'node up, pid {state["pid"]}')

def stop_node():
    pid = state['pid']
    if pid:
        try: os.kill(pid, signal.SIGTERM)
        except ProcessLookupError: pass
        for _ in range(40):
            time.sleep(1.5)
            if not my_daemons(): break
        else:
            try: os.kill(pid, signal.SIGKILL)
            except ProcessLookupError: pass
            time.sleep(3)
    left = my_daemons()
    log('daemons of this run left after stop: ' + (str([l[:60] for l in left]) if left else 'none'))
    return not left

def cql(stmt, timeout=300):
    return sh(f'{TREE}/bin/cqlsh {ADDR} -e "{stmt}"', timeout=timeout)

def tablestats(table=f'ks.{TN}'):
    return sh(f'{NODETOOL} tablestats {table}', check=False, timeout=120)

def compactionstats():
    return sh(f'{NODETOOL} compactionstats', check=False, timeout=120)

def level_list(txt, key):
    """'SSTables in each level: [150/4, 10, 0, ...]' -> [150, 10, 0, ...]  (the '/limit' suffix is dropped)"""
    m = re.search(rf'{key}: \[(.*?)\]', txt)
    if not m: return None
    return [int(re.sub(r'[^0-9]', '', x.split('/')[0]) or 0) for x in m.group(1).split(',')]

def parse_levels(txt):
    out = {'count': level_list(txt, 'SSTables in each level'), 'bytes': level_list(txt, 'SSTable bytes in each level')}
    m = re.search(r'Space used \(live\): (\d+)', txt); out['live'] = int(m.group(1)) if m else None
    m = re.search(r'SSTable count: (\d+)', txt); out['sstables'] = int(m.group(1)) if m else None
    return out

def pending(txt):
    m = re.search(r'pending tasks:?\s+(\d+)', txt)
    return int(m.group(1)) if m else -1

def proc_info(pid):
    fds = len(os.listdir(f'/proc/{pid}/fd')) if os.path.isdir(f'/proc/{pid}/fd') else -1
    rss = -1
    try:
        for l in open(f'/proc/{pid}/status'):
            if l.startswith('RssAnon:'): rss = int(l.split()[1]) * 1024
    except Exception: pass
    return fds, rss

class Sampler(threading.Thread):
    """every 5 s: table-directory file bytes (the real resource), Data.db count, fds, RssAnon; every 20 s tablestats + compactionstats raw"""
    def __init__(self, path):
        super().__init__(daemon=True); self.path = path; self.ev = threading.Event()
    def run(self):
        f = open(self.path, 'a'); last = 0
        while not self.ev.is_set():
            ts = time.time()
            try:
                nb, data = files_bytes(table_dirs())
                fds, rss = proc_info(state['pid'])
                rec = {'t': ts, 'bytes': nb, 'datafiles': len(data), 'maxdata': max(data) if data else 0, 'fds': fds, 'rssanon': rss}
                if ts - last >= 20:
                    last = ts
                    t = tablestats(); cs = compactionstats()
                    rec.update({'tablestats': t, 'compactionstats': cs, 'parsed': parse_levels(t), 'pending': pending(cs)})
                f.write(json.dumps(rec) + '\n'); f.flush()
            except Exception as e:
                f.write(json.dumps({'t': ts, 'error': repr(e)}) + '\n'); f.flush()
            self.ev.wait(5)
    def stop(self): self.ev.set()

class Flusher(threading.Thread):
    """B3c: `nodetool flush ks standard1` back to back (each call is a JVM start, ~2 s), timestamps in flushes.log"""
    def __init__(self, path):
        super().__init__(daemon=True); self.path = path; self.ev = threading.Event(); self.count = 0
    def run(self):
        f = open(self.path, 'a')
        while not self.ev.is_set():
            t0 = time.time()
            r = subprocess.run(f'{NODETOOL} flush ks {TN}', shell=True, capture_output=True, text=True, stdin=subprocess.DEVNULL)
            self.count += 1
            f.write(json.dumps({'t0': t0, 't1': time.time(), 'rc': r.returncode, 'err': r.stderr[-200:]}) + '\n'); f.flush()
            self.ev.wait(0.3)
    def stop(self): self.ev.set()

def compaction_busy():
    t = sh(f'{NODETOOL} tpstats', check=False, timeout=120)
    for l in t.splitlines():
        if l.startswith('CompactionExecutor'):
            p = l.split(); return int(p[1]) + int(p[2])
    return -1

def drain(spec, tag):
    """wait until 3 reads 20 s apart show no active or queued compaction task and identical file bytes (cap 25 min)"""
    if spec.get('drain_boost', True):
        sh(f'{NODETOOL} setcompactionthroughput 0'); sh(f'{NODETOOL} setconcurrentcompactors 4')
    t0 = time.time(); hist = []
    while time.time() - t0 < 1500:
        time.sleep(20)
        nb, _ = files_bytes(table_dirs())
        busy = compaction_busy(); est = pending(compactionstats())
        hist.append((busy, nb, est))
        log(f'drain[{tag}] busy={busy} estimate={est} bytes={nb}')
        if len(hist) >= 3 and all(h[0] == 0 for h in hist[-3:]) and len({h[1] for h in hist[-3:]}) == 1:
            return {'settled': True, 'seconds': round(time.time() - t0), 'hist': hist[-3:]}
    return {'settled': False, 'seconds': round(time.time() - t0), 'hist': hist[-3:]}

def snapshot(tag):
    nb, data = files_bytes(table_dirs())
    txt = tablestats()
    open(f'{RUN}/tablestats-{tag}.txt', 'w').write(txt)
    rec = {'tag': tag, 'bytes': nb, 'datafiles': sorted(data), 'parsed': parse_levels(txt), 't': time.time(),
           'df': sh(f'df -B1 {MNT} | tail -1', check=False).strip()}
    json.dump(rec, open(f'{RUN}/snapshot-{tag}.json', 'w'))
    log(f'snapshot {tag}: bytes={nb} files={len(data)} L0..={rec["parsed"]["count"]} bytes/level={rec["parsed"]["bytes"]}')
    return rec

def stress_write(n, tag):
    import shlex
    qcols = ' '.join(shlex.quote(x) for x in COLS.split())
    t0 = time.time()
    sh(f'{TREE}/tools/bin/cassandra-stress write n={n} -col {qcols} -pop seq=1..{n} -schema keyspace=ks -rate threads={THREADS} throttle={THROTTLE} -node {ADDR} > {RUN}/stress-{tag}.txt 2>&1; tail -n 45 {RUN}/stress-{tag}.txt | head -n 40', timeout=3600, check=False)
    log(f'stress {tag} finished in {time.time()-t0:.0f}s')
    if 'Total errors' not in open(f'{RUN}/stress-{tag}.txt').read(): raise RuntimeError('stress did not complete; see stress-%s.txt' % tag)
    return time.time() - t0

def create_table():
    cql("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    cols = ', '.join(f'\\"C{i}\\" blob' for i in range(5))
    cql(f"CREATE TABLE IF NOT EXISTS ks.{TN} (key blob PRIMARY KEY, {cols}) WITH compression = {{'enabled':'false'}} AND compaction = {COMPACTION}")

def main():
    spec = LABELS[LABEL]
    rc = 1; smp = fl = None
    try:
        log(f'== {LABEL} start; tree={TREE} rows={N_ROWS} spec={json.dumps(spec)} addr={ADDR} jmx={JMX}')
        start_node(spec)
        create_table()
        t = tablestats()
        if 'SSTables in each level' not in t: raise RuntimeError('first-trigger check 1 failed: table is not under LCS (no per-level line)')
        sh(f'{NODETOOL} setlogginglevel org.apache.cassandra.db.compaction.LeveledManifest DEBUG')
        if spec['compaction_off']: sh(f'{NODETOOL} disableautocompaction ks {TN}')
        open(f'{RUN}/settings-live.txt', 'w').write(sh(f'{NODETOOL} getcompactionthroughput; {NODETOOL} getconcurrentcompactors; {NODETOOL} getlogginglevels | grep -i LeveledManifest', check=False))
        smp = Sampler(f'{RUN}/samples.jsonl'); smp.start()
        fl = Flusher(f'{RUN}/flushes.log'); fl.start()
        # first-trigger check 2: an sstable must exist 40 s after the write starts (run in a side thread; sets a flag)
        flag = {'bad': False}
        def watchdog():
            time.sleep(40)
            nb, data = files_bytes(table_dirs())
            if not data: flag['bad'] = True; log('first-trigger check 2 FAILED: no sstable 40 s after the write started'); subprocess.run('pkill -f "cassandra-stress write" -P %d' % os.getpid(), shell=True)
        threading.Thread(target=watchdog, daemon=True).start()
        t_w = stress_write(N_ROWS, 'write')
        if flag['bad']: raise RuntimeError('first-trigger check 2 failed (no sstable)')
        fl.stop(); time.sleep(4)
        json.dump({'flush_calls': fl.count}, open(f'{RUN}/flush-count.json', 'w'))
        # one last flush so the memtable tail is on disk, then the lag-end snapshot
        sh(f'{NODETOOL} flush ks {TN}', check=False)
        snapshot('lag-end')
        if spec['drain']:
            d = drain(spec, 'write'); json.dump(d, open(f'{RUN}/drain-write.json', 'w'))
            snap = snapshot('settled-write')
        smp.stop(); time.sleep(6)
        sh(f'grep -h "L0 is too far behind" {RUN}/logs/debug.log* > {RUN}/stcs-lines.txt; wc -l < {RUN}/stcs-lines.txt', check=False)
        cql(f'TRUNCATE ks.{TN}', timeout=600)
        time.sleep(10)
        snapshot('truncated')
        rc = 0
    except Exception as e:
        log(f'FAILED: {e!r}'); rc = 2
    finally:
        for th in (smp, fl):
            if th: th.stop()
        ok = stop_node()
        open(f'{RUN}/exit.txt', 'w').write(f'rc={rc} daemons_stopped={ok}\n')
        log(f'== {LABEL} done rc={rc} node stopped={ok}')
    sys.exit(rc if ok else 3)

main()
