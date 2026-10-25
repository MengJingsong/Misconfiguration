#!/usr/bin/env python3
"""Stage-4 cluster tier, one label per invocation:  LCS_TREE=<tree> LCS_OUT=<dir> cluster-run.py <label>
Case: sstable_size_in_mb-getnextlevel-candidate-total-bytes--autonomous
One node (127.0.0.1) with data on a dedicated tmpfs; stress write; lag-phase snapshot; drain; TRUNCATE control; node stopped.
Sampler: file bytes of the table directory every 5 s, tablestats + compactionstats every 20 s (raw text kept)."""

ROWS = 2000000
COLS = 'size=FIXED(256) n=FIXED(4)'
THREADS = 32
LABELS = {
  'N5':   {'compaction': "{'class':'LeveledCompactionStrategy','sstable_size_in_mb':'5'}", 'throughput': '0MiB/s', 'compactors': 1, 'drain_boost': False},
  'N20':  {'compaction': "{'class':'LeveledCompactionStrategy','sstable_size_in_mb':'20'}", 'throughput': '0MiB/s', 'compactors': 1, 'drain_boost': False},
  'N160': {'compaction': "{'class':'LeveledCompactionStrategy','sstable_size_in_mb':'160'}", 'throughput': '0MiB/s', 'compactors': 1, 'drain_boost': False},
  'T20':  {'compaction': "{'class':'LeveledCompactionStrategy','sstable_size_in_mb':'20'}", 'throughput': '16MiB/s', 'compactors': 1},
  'STCS': {'compaction': "{'class':'SizeTieredCompactionStrategy'}", 'throughput': '0MiB/s', 'compactors': 1, 'drain_boost': False},
}

# ---------------------------------------------------------------- core (same in all three LCS harnesses)
import os, sys, re, time, json, shutil, subprocess, threading, signal, glob

HOME = os.path.expanduser('~')
TREE = os.environ.get('LCS_TREE') or sys.exit('set LCS_TREE to the copy-source.sh tree the node runs from')
OUT = os.environ.get('LCS_OUT') or sys.exit('set LCS_OUT to the run output directory')
MNT = os.environ.get('LCS_MNT', '/mnt/lcsrun')          # dedicated tmpfs (amendment 5): data, commitlog, hints, saved caches
LABEL = sys.argv[1] if len(sys.argv) > 1 else sys.exit('usage: cluster-run.py <label>  labels: ' + ' '.join(LABELS))
N_ROWS = int(os.environ.get('LCS_ROWS', ROWS))           # overridden only by a shakedown
RUN = os.path.join(OUT, LABEL)
os.makedirs(RUN, exist_ok=True)
CMDLOG = open(os.path.join(RUN, 'commands.log'), 'a')
NODETOOL = f'{TREE}/bin/nodetool -h 127.0.0.1'
KS_TABLE = 'ks.standard1'
state = {'pid': None, 'stop': False}

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

def daemons():
    out = subprocess.run(['ps', '-eo', 'pid,args'], capture_output=True, text=True).stdout
    return [l for l in out.splitlines() if re.search(r'(^|/)java .*CassandraDaemon', l)]

def table_dir():
    c = glob.glob(f'{MNT}/data/ks/standard1-*') + glob.glob(f'{MNT}/data/ks/big-*')
    return sorted(c)

def files_bytes(dirs):
    n, data = 0, []
    for d in dirs:
        for f in os.listdir(d):
            p = os.path.join(d, f)
            if os.path.isfile(p):
                sz = os.path.getsize(p); n += sz
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
    setk('cluster_name', f"'lcs-{LABEL}'")
    setk('hints_directory', f'{MNT}/hints')
    setk('commitlog_directory', f'{MNT}/commitlog')
    setk('saved_caches_directory', f'{MNT}/saved_caches')
    y += f'\ndata_file_directories:\n    - {MNT}/data\n'
    setk('auto_snapshot', 'false')
    setk('compaction_throughput', spec['throughput'])
    setk('concurrent_compactors', spec['compactors'])
    open(f'{conf}/cassandra.yaml', 'w').write(y)
    return conf

def start_node(spec):
    assert not daemons(), 'a CassandraDaemon is already running: ' + str(daemons())
    sh(f'sudo mkdir -p {MNT} && (mountpoint -q {MNT} || sudo mount -t tmpfs -o size=24g tmpfs {MNT}) && sudo chown $(id -u):$(id -g) {MNT}')
    sh(f'rm -rf {MNT}/* && mkdir -p {MNT}/data {MNT}/commitlog {MNT}/hints {MNT}/saved_caches')
    conf = make_conf(spec)
    logs = os.path.join(RUN, 'logs'); os.makedirs(logs, exist_ok=True)
    env = f'CASSANDRA_CONF={conf} CASSANDRA_LOG_DIR={logs} MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M'
    sh(f'ulimit -n 100000; cd {TREE} && ( {env} setsid nohup bin/cassandra -f -p {RUN}/pid < /dev/null > {RUN}/node.out 2>&1 & )')
    t0 = time.time()
    while time.time() - t0 < 240:
        time.sleep(3)
        if not daemons(): raise RuntimeError('node died during start; see node.out')
        st = subprocess.run(f'{NODETOOL} status 2>/dev/null | grep -c "^UN"; {NODETOOL} statusbinary 2>/dev/null', shell=True, capture_output=True, text=True, stdin=subprocess.DEVNULL).stdout
        if st.split() and st.split()[0] == '1' and 'running' in st: break
    else: raise RuntimeError('node did not come up')
    state['pid'] = int(daemons()[0].split()[0])
    log(f'node up, pid {state["pid"]}')

def stop_node():
    pid = state['pid']
    if pid:
        try: os.kill(pid, signal.SIGTERM)
        except ProcessLookupError: pass
        for _ in range(40):
            time.sleep(1.5)
            if not daemons(): break
        else:
            try: os.kill(pid, signal.SIGKILL)
            except ProcessLookupError: pass
            time.sleep(3)
    left = daemons()
    log('daemons left after stop: ' + (str([l[:60] for l in left]) if left else 'none'))
    return not left

def cql(stmt, timeout=300):
    return sh(f'{TREE}/bin/cqlsh 127.0.0.1 -e "{stmt}"', timeout=timeout)

def tablestats(table=KS_TABLE):
    return sh(f'{NODETOOL} tablestats {table}', check=False, timeout=120)

def compactionstats():
    return sh(f'{NODETOOL} compactionstats', check=False, timeout=120)

def parse_levels(txt):
    out = {}
    for key, name in (('SSTables in each level', 'count'), ('SSTable bytes in each level', 'bytes')):
        m = re.search(rf'{key}: \[(.*?)\]', txt)
        out[name] = [int(re.sub(r'[^0-9]', '', x) or 0) for x in m.group(1).split(',')] if m else None
    m = re.search(r'Space used \(live\): (\d+)', txt); out['live'] = int(m.group(1)) if m else None
    m = re.search(r'SSTable count: (\d+)', txt); out['sstables'] = int(m.group(1)) if m else None
    return out

def pending(txt):
    m = re.search(r'pending tasks:?\s+(\d+)', txt)
    return int(m.group(1)) if m else -1

class Sampler(threading.Thread):
    """every 5 s the table directories' file bytes (the real resource); every 20 s tablestats + compactionstats raw"""
    def __init__(self, path, tablename):
        super().__init__(daemon=True); self.path = path; self.tn = tablename; self.ev = threading.Event()
    def run(self):
        f = open(self.path, 'a'); last = 0
        while not self.ev.is_set():
            ts = time.time()
            try:
                dirs = [d for d in table_dir() if os.path.basename(d).startswith(self.tn)]
                nb, data = files_bytes(dirs) if dirs else (0, [])
                rec = {'t': ts, 'bytes': nb, 'datafiles': len(data), 'maxdata': max(data) if data else 0}
                if ts - last >= 20:
                    last = ts
                    ts_txt = tablestats(f'ks.{self.tn}'); cs = compactionstats()
                    rec.update({'tablestats': ts_txt, 'compactionstats': cs}); rec['parsed'] = parse_levels(ts_txt); rec['pending'] = pending(cs)
                f.write(json.dumps(rec) + '\n'); f.flush()
            except Exception as e:
                f.write(json.dumps({'t': ts, 'error': repr(e)}) + '\n'); f.flush()
            self.ev.wait(5)
    def stop(self): self.ev.set()

def compaction_busy():
    """CompactionExecutor active+pending from tpstats (the estimate in compactionstats can stay > 0 when only one L0 sstable is left)"""
    t = sh(f'{NODETOOL} tpstats', check=False, timeout=120)
    for l in t.splitlines():
        if l.startswith('CompactionExecutor'):
            p = l.split(); return int(p[1]) + int(p[2])
    return -1

def drain(tn, spec, tag):
    """amendments F6/C5/N5: raise compaction throughput/compactors for the drain (unless the spec keeps them), then wait until
    3 reads 20 s apart show no active or queued compaction task and identical file bytes (cap 25 min)"""
    if spec.get('drain_boost', True):
        sh(f'{NODETOOL} setcompactionthroughput 0'); sh(f'{NODETOOL} setconcurrentcompactors 4')
    t0 = time.time(); hist = []
    while time.time() - t0 < 1500:
        time.sleep(20)
        dirs = [d for d in table_dir() if os.path.basename(d).startswith(tn)]
        nb, _ = files_bytes(dirs)
        busy = compaction_busy(); est = pending(compactionstats())
        hist.append((busy, nb, est))
        log(f'drain[{tag}] busy={busy} estimate={est} bytes={nb}')
        if len(hist) >= 3 and all(h[0] == 0 for h in hist[-3:]) and len({h[1] for h in hist[-3:]}) == 1:
            return {'settled': True, 'seconds': round(time.time() - t0), 'hist': hist[-3:]}
    return {'settled': False, 'seconds': round(time.time() - t0), 'hist': hist[-3:]}

def snapshot(tn, tag):
    """end-of-phase record: tablestats raw, file sizes, df"""
    dirs = [d for d in table_dir() if os.path.basename(d).startswith(tn)]
    nb, data = files_bytes(dirs)
    txt = tablestats(f'ks.{tn}')
    open(f'{RUN}/tablestats-{tag}.txt', 'w').write(txt)
    rec = {'tag': tag, 'bytes': nb, 'datafiles': sorted(data), 'parsed': parse_levels(txt), 't': time.time(),
           'df': sh(f'df -B1 {MNT} | tail -1', check=False).strip()}
    json.dump(rec, open(f'{RUN}/snapshot-{tag}.json', 'w'))
    log(f'snapshot {tag}: bytes={nb} files={len(data)} levels={rec["parsed"]["bytes"]}')
    return rec

def stress_write(n, cols, threads, tag, extra=''):
    import shlex
    qcols = ' '.join(shlex.quote(x) for x in cols.split())
    t0 = time.time()
    out = sh(f'{TREE}/tools/bin/cassandra-stress write n={n} -col {qcols} -pop seq=1..{n} -schema keyspace=ks -rate threads={threads} -node 127.0.0.1 {extra} > {RUN}/stress-{tag}.txt 2>&1; tail -n 45 {RUN}/stress-{tag}.txt | head -n 40', timeout=3600, check=False)
    log(f'stress {tag} finished in {time.time()-t0:.0f}s')
    if 'Total errors' not in open(f'{RUN}/stress-{tag}.txt').read(): raise RuntimeError('stress did not complete; see stress-%s.txt' % tag)
    return time.time() - t0

def create_table(tn, compaction):
    cql("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    cols = ', '.join(f'\\"C{i}\\" blob' for i in range(5))
    cql(f"CREATE TABLE IF NOT EXISTS ks.{tn} (key blob PRIMARY KEY, {cols}) WITH compression = {{'enabled':'false'}} AND compaction = {compaction}")

def extras(spec, smp):
    # N5: supplementary overwrite phase, same keys (seeded generator -> same values)
    stress_write(N_ROWS, COLS, THREADS, 'overwrite')
    snapshot('standard1', 'lag-end-overwrite')
    d = drain('standard1', spec, 'overwrite'); json.dump(d, open(f'{RUN}/drain-overwrite.json', 'w'))
    snapshot('standard1', 'settled-overwrite')
    # N6: large-partition table with the same compaction option
    if spec['compaction'].startswith("{'class':'LeveledCompactionStrategy'"):
        comp = spec['compaction']
        cql(f"CREATE TABLE IF NOT EXISTS ks.big (pk text, ck int, val blob, PRIMARY KEY (pk, ck)) WITH compression = {{'enabled':'false'}} AND compaction = {comp}")
        sm2 = Sampler(f'{RUN}/samples-big.jsonl', 'big'); sm2.start()
        zipf = glob.glob(f'{TREE}/lib/cassandra-driver-internal-only-*.zip')[0]
        sh(f'PYTHONPATH={zipf}/cassandra-driver-3.29.0 python3 {os.path.dirname(os.path.abspath(__file__))}/big-writer.py > {RUN}/big-writer.txt 2>&1', timeout=1800, check=False)
        if 'payload bytes' not in open(f'{RUN}/big-writer.txt').read(): raise RuntimeError('big-writer.py did not finish; see big-writer.txt')
        sh(f'{NODETOOL} flush ks big')
        d = drain('big', spec, 'big'); json.dump(d, open(f'{RUN}/drain-big.json', 'w'))
        snapshot('big', 'settled-big')
        sm2.stop(); time.sleep(6)
        cql('TRUNCATE ks.big', timeout=600)

# ---------------------------------------------------------------- run one label
def main():
    spec = LABELS[LABEL]
    rc = 1
    try:
        log(f'== {LABEL} start; tree={TREE} rows={N_ROWS} spec={json.dumps(spec)}')
        start_node(spec)
        create_table('standard1', spec['compaction'])
        smp = Sampler(f'{RUN}/samples-standard1.jsonl', 'standard1'); smp.start()
        for c in spec.get('post_start', []): sh(f'{NODETOOL} {c}')
        t_w = stress_write(N_ROWS, COLS, THREADS, 'write')
        snapshot('standard1', 'lag-end')
        d = drain('standard1', spec, 'write')
        snap = snapshot('standard1', 'settled-write'); snap['drain'] = d
        json.dump(d, open(f'{RUN}/drain-write.json', 'w'))
        extras(spec, smp)
        smp.stop(); time.sleep(6)
        # instrument control (amendments F7/C7/N7): TRUNCATE must bring the file bytes to ~0
        cql('TRUNCATE ks.standard1', timeout=600)
        time.sleep(10)
        snapshot('standard1', 'truncated')
        rc = 0
    except Exception as e:
        log(f'FAILED: {e!r}'); rc = 2
    finally:
        ok = stop_node()
        open(f'{RUN}/exit.txt', 'w').write(f'rc={rc} daemons_stopped={ok}\n')
        log(f'== {LABEL} done rc={rc} node stopped={ok}')
    sys.exit(rc if ok else 3)

main()
