#!/usr/bin/env python3
"""Cluster tier (B3) of max_keys_sparse-addinternal-keys--autonomous (2026-10-28 amendments).
usage: cluster-run.py <label>     copy ~/s4-b34/src; node dir ~/stage4-tmp/b34/mks/node (local disk); out $OUT (default ~/s4-b34/logs/max_keys_sparse/run1/cluster/<label>)
One node start: sasi_indexes_enabled, heap 1G (G1), Byteman rule mks.btm, `bin/cassandra -f`. Phase 1: tables t_{sparse,prefix}_k{5,6,1000}, 60 000 rows each (v = id // K),
flush each; Phase 2 (control): t_ctl_mb{1,64} PREFIX K=6 with max_compaction_flush_memory_in_mb, two flushes then `nodetool compact`.
Writes readings.txt (EXPECTED/READING lines), cmdlog.txt, stdout.txt, system.log, heap.csv, and per-step excerpts. The node is stopped on any exit."""
import glob, json, os, re, subprocess, sys, time, atexit, threading
label = sys.argv[1]
H = os.path.dirname(os.path.abspath(__file__)); HOME = os.path.expanduser('~')
C = HOME + '/s4-b34/src'; N = HOME + '/stage4-tmp/b34/mks/node'
OUT = os.path.join(os.environ.get('OUT', HOME + '/s4-b34/logs/max_keys_sparse/run1/cluster'), label); os.makedirs(OUT, exist_ok=True)
log = open(OUT + '/cmdlog.txt', 'a'); rd = open(OUT + '/readings.txt', 'a')
def say(*a):
    m = ' '.join(str(x) for x in a); print(m, flush=True); log.write(m + '\n'); log.flush()
def reading(m):
    say(m); rd.write(m + '\n'); rd.flush()
def sh(cmd, tmo=1800):
    say('$', cmd)
    r = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=C, timeout=tmo)
    say(r.stdout.rstrip()[-1500:]); return r.stdout
def daemons():
    out = subprocess.run("ps -eo pid,comm,args | awk '$2==\"java\" && /CassandraDaemon/'", shell=True, capture_output=True, text=True).stdout
    return [l for l in out.splitlines() if l.strip()]
stopflag = threading.Event()
def stop():
    stopflag.set()
    if daemons():
        subprocess.run('bin/nodetool stopdaemon', shell=True, cwd=C, capture_output=True)
        for _ in range(40):
            if not daemons(): break
            time.sleep(2)
        for l in daemons(): os.kill(int(l.split()[0]), 9)
atexit.register(stop)
assert not daemons(), 'daemon already running'
say('== %s start %d' % (label, time.time() * 1000))
subprocess.run('rm -rf %s' % N, shell=True)
open(OUT + '/extra.yaml', 'w').write('sasi_indexes_enabled: true\n')
sh('T=%s %s/make-node.sh %s %s/extra.yaml' % (N, H, C, OUT))
byteman = C + '/build/lib/jars/byteman-4.0.20.jar'
extra = '-javaagent:%s=script:%s/mks.btm' % (byteman, H)
open(OUT + '/jvm-extra.txt', 'w').write(extra + '\n')
env = dict(os.environ, CASSANDRA_CONF=N + '/conf', CASSANDRA_LOG_DIR=N + '/logs', MAX_HEAP_SIZE='1G', HEAP_NEWSIZE='256M', JVM_EXTRA_OPTS=extra)
nodeproc = subprocess.Popen('ulimit -n 100000; exec bin/cassandra -f > %s/stdout.txt 2>&1' % N, shell=True, cwd=C, env=env, start_new_session=True)
heapf = open(OUT + '/heap.csv', 'w'); heapf.write('epoch_ms,heap_used_kB\n')
def sampler():
    while not stopflag.is_set():
        ds = daemons()
        if ds:
            pid = ds[0].split()[0]
            hi = subprocess.run('jcmd %s GC.heap_info 2>/dev/null' % pid, shell=True, capture_output=True, text=True).stdout
            m = re.search(r'used (\d+)K', hi)
            if m: heapf.write('%d,%s\n' % (time.time() * 1000, m.group(1))); heapf.flush()
        time.sleep(1)
threading.Thread(target=sampler, daemon=True).start()
for _ in range(200):
    r = subprocess.run('bin/nodetool statusbinary', shell=True, cwd=C, capture_output=True, text=True)
    if r.stdout.strip() == 'running': break
    if nodeproc.poll() is not None: say('daemon died at start'); say(open(N + '/stdout.txt').read()[-2000:]); sys.exit(1)
    time.sleep(3)
else:
    sys.exit('node did not come up')
reading('NODE_UP_MS %d' % (time.time() * 1000))
# python driver (bundled zip), as bin/cqlsh.py does
for z in glob.glob(C + '/lib/*.zip'):
    base = os.path.basename(z)[:-4]
    sys.path.insert(0, os.path.join(z, base.replace('-internal-only-', '-')) if base.startswith('cassandra-driver') else z)
from cassandra.cluster import Cluster
from cassandra.concurrent import execute_concurrent_with_args
cl = Cluster(['127.0.0.1'], protocol_version=4, connect_timeout=30); s = cl.connect(); s.default_timeout = 120
def so(): return open(N + '/stdout.txt', errors='replace').read()
def syslog(): return open(N + '/logs/system.log', errors='replace').read()
def mksb(off): return [l for l in so()[off:].splitlines() if l.startswith('MKS_BUILD')]
def table_dir(t):
    d = glob.glob('%s/data/ks/%s-*' % (N, t)); return d[0] if d else None
def index_files(t):
    d = table_dir(t); return sorted((os.path.basename(f), os.path.getsize(f)) for f in glob.glob(d + '/*SI_*')) if d else []
def data_bytes(t):
    d = table_dir(t); return sum(os.path.getsize(f) for f in glob.glob(d + '/*-Data.db')) if d else -1
def heap_between(t0, t1):
    mx = 0
    for l in open(OUT + '/heap.csv').read().splitlines()[1:]:
        e, h = l.split(','); 
        if t0 <= int(e) <= t1: mx = max(mx, int(h))
    return mx
def fill(t, n_from, n_to, K):
    ins = s.prepare('INSERT INTO ks.%s (id, v) VALUES (?, ?)' % t)
    args = [(i, i // K) for i in range(n_from, n_to)]
    errs = sum(1 for ok, r in execute_concurrent_with_args(s, ins, args, concurrency=64, raise_on_first_error=False) if not ok)
    return errs
try:
    s.execute("CREATE KEYSPACE ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    # ---- phase 1
    for K in (5, 6, 1000):
        for mode in ('sparse', 'prefix'):
            t = 't_%s_k%d' % (mode, K)
            s.execute('CREATE TABLE ks.%s (id int PRIMARY KEY, v int)' % t)
            s.execute("CREATE CUSTOM INDEX ON ks.%s (v) USING 'org.apache.cassandra.index.sasi.SASIIndex' WITH OPTIONS = {'mode':'%s'}" % (t, mode.upper()))
            t0 = int(time.time() * 1000); sl0 = len(syslog()); so0 = len(so())
            errs = fill(t, 0, 60000, K)
            reading('FILL %s rows=60000 errors=%d' % (t, errs))
            sh('bin/nodetool flush ks %s' % t)
            for _ in range(40):
                time.sleep(1)
                if 'Index flush to' in syslog()[sl0:] or 'Failed to build index segment' in syslog()[sl0:]: break
            time.sleep(5)
            t1 = int(time.time() * 1000)
            new = syslog()[sl0:]
            fails = [l for l in new.splitlines() if 'Failed to build index segment' in l or 'Failed to flush index' in l or 'belongs to more than' in l]
            open(OUT + '/syslog-%s.txt' % t, 'w').write('\n'.join(l for l in new.splitlines() if 'sasi' in l.lower() or 'index' in l.lower())[:20000])
            b = mksb(so0)
            reading('BUILD %s %s' % (t, ' | '.join(b)))
            if mode == 'prefix' and not b: raise SystemExit('instrument check failed: no MKS_BUILD line for %s (Byteman rule did not fire)' % t)
            reading('LOGFAIL %s count=%d causes_5keys=%d first=%s' % (t, len(fails), sum('belongs to more than 5 keys in SPARSE mode' in l for l in fails), (fails[0][:200] if fails else '-')))
            reading('INDEXFILES %s %s' % (t, index_files(t)))
            reading('DATABYTES %s %d' % (t, data_bytes(t)))
            reading('HEAPMAX_kB %s %d' % (t, heap_between(t0, t1)))
            cnt = s.execute('SELECT count(*) FROM ks.%s' % t).one()[0]
            try:
                rows = list(s.execute('SELECT id FROM ks.%s WHERE v = 3' % t)); q = 'rows=%d' % len(rows)
            except Exception as e:
                q = 'error=%s' % str(e).replace('\n', ' ')[:160]
            reading('QUERY %s count_all=%d v=3 %s' % (t, cnt, q))
    # ---- phase 2: positive control
    for mb in (1, 64):
        t = 't_ctl_mb%d' % mb
        s.execute('CREATE TABLE ks.%s (id int PRIMARY KEY, v int)' % t)
        s.execute("CREATE CUSTOM INDEX ON ks.%s (v) USING 'org.apache.cassandra.index.sasi.SASIIndex' WITH OPTIONS = {'mode':'PREFIX', 'max_compaction_flush_memory_in_mb':'%d'}" % (t, mb))
        e = fill(t, 0, 30000, 6); sh('bin/nodetool flush ks %s' % t); time.sleep(8)
        e += fill(t, 30000, 60000, 6); sh('bin/nodetool flush ks %s' % t); time.sleep(8)
        reading('FILL %s rows=60000 errors=%d sstables=%d' % (t, e, len(glob.glob(table_dir(t) + '/*-Data.db'))))
        sl0 = len(syslog()); so0 = len(so())
        sh('bin/nodetool compact ks %s' % t); time.sleep(15)
        new = syslog()[sl0:]
        seg = [l for l in new.splitlines() if 'Flushed index segment' in l]
        open(OUT + '/syslog-%s-compact.txt' % t, 'w').write('\n'.join(l for l in new.splitlines() if 'index' in l.lower())[:20000])
        reading('CONTROL %s flushed_index_segment_lines=%d index_flush_lines=%d' % (t, len(seg), new.count('Index flush to')))
        reading('CONTROL_BUILDS %s %s' % (t, ' | '.join(mksb(so0))))
        reading('INDEXFILES %s %s' % (t, index_files(t)))
finally:
    stopflag.set(); time.sleep(1)
    subprocess.run('cp %s/logs/system.log %s/system.log; cp %s/stdout.txt %s/stdout.txt; ls -lR %s/data/ks > %s/datalist.txt; df -h / | tail -n 1 >> %s/datalist.txt' % (N, OUT, N, OUT, N, OUT, OUT), shell=True)
    cl.shutdown(); stop(); time.sleep(2)
    say('daemons left: %d' % len(daemons()))
