#!/usr/bin/env python3
"""Cluster tier (B3) of native_protocol_v1_v2_collection_size_limit-writesize-size--autonomous (2026-10-28 amendment).
usage: cluster-run.py <label> <default|control>
default: user_defined_functions_enabled; V2 probe; workload W (plain set<int> writes N = 1000/65536/500000, v4, one table per N, flush) with Byteman pack counts;
         workload U (Java UDF returning list<int> of N, client v4 then v3) with Byteman CS_PACK / CS_WRITESIZE / CS_PACK_RET lines.
control: same node with collection_size_fail_threshold: 200KiB; the W inserts only (N=1000 accepted, 65536 and 500000 rejected by the guardrail).
Copy ~/s4-b34/src; node dir ~/stage4-tmp/b34/cs/node (local); out $OUT (default ~/s4-b34/logs/collection_size_limit/run1/cluster/<label>). Node stopped on any exit."""
import glob, os, re, subprocess, sys, time, atexit, threading
label, mode = sys.argv[1:3]
H = os.path.dirname(os.path.abspath(__file__)); HOME = os.path.expanduser('~')
C = HOME + '/s4-b34/src'; N = HOME + '/stage4-tmp/b34/cs/node'
OUT = os.path.join(os.environ.get('OUT', HOME + '/s4-b34/logs/collection_size_limit/run1/cluster'), label); os.makedirs(OUT, exist_ok=True)
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
say('== %s %s start %d' % (label, mode, time.time() * 1000))
subprocess.run('rm -rf %s' % N, shell=True)
open(OUT + '/extra.yaml', 'w').write('user_defined_functions_enabled: true\n' + ('authenticator: PasswordAuthenticator\n' if mode == 'control' else '') + ('collection_size_fail_threshold: 200KiB\n' if mode == 'control' else ''))
sh('T=%s %s/make-node.sh %s %s/extra.yaml' % (N, H, C, OUT))
byteman = C + '/build/lib/jars/byteman-4.0.20.jar'
extra = '-javaagent:%s=script:%s/cs.btm' % (byteman, H)
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
        time.sleep(0.5)
threading.Thread(target=sampler, daemon=True).start()
for _ in range(200):
    r = subprocess.run('bin/nodetool statusbinary', shell=True, cwd=C, capture_output=True, text=True)
    if r.stdout.strip() == 'running': break
    if nodeproc.poll() is not None: say('daemon died at start'); say(open(N + '/stdout.txt').read()[-2000:]); sys.exit(1)
    time.sleep(3)
else:
    sys.exit('node did not come up')
reading('NODE_UP_MS %d' % (time.time() * 1000))
for z in glob.glob(C + '/lib/*.zip'):
    base = os.path.basename(z)[:-4]
    sys.path.insert(0, os.path.join(z, base.replace('-internal-only-', '-')) if base.startswith('cassandra-driver') else z)
from cassandra.cluster import Cluster
from cassandra.concurrent import execute_concurrent_with_args
def so(): return open(N + '/stdout.txt', errors='replace').read()
def lines(tag, off): return [l for l in so()[off:].splitlines() if l.startswith(tag)]
def table_dir(t):
    d = glob.glob('%s/data/ks/%s-*' % (N, t)); return d[0] if d else None
def data_bytes(t):
    d = table_dir(t); return sum(os.path.getsize(f) for f in glob.glob(d + '/*-Data.db')) if d else -1
def heap_between(t0, t1):
    mx = 0
    for l in open(OUT + '/heap.csv').read().splitlines()[1:]:
        e, h = l.split(',')
        if t0 <= int(e) <= t1: mx = max(mx, int(h))
    return mx
def memtable_bytes(t):
    o = subprocess.run('bin/nodetool tablestats ks.%s' % t, shell=True, cwd=C, capture_output=True, text=True).stdout
    m = re.search(r'Memtable data size: (\d+)', o); return int(m.group(1)) if m else -1
NS = (1000, 65536, 500000)
try:
    if mode == 'default':
        try:
            c2 = Cluster(['127.0.0.1'], protocol_version=2, connect_timeout=15); c2.connect()
            reading('V2PROBE connected=yes'); c2.shutdown()
        except Exception as e:
            reading('V2PROBE connected=no error=%s' % str(e).replace('\n', ' ')[:300])
    if mode == 'control':
        # B3 control amendment (runbook defect 2): guardrails do not apply to superusers, and with AllowAllAuthenticator every client is one
        # (ClientState.isSuper -> !authenticator.requireAuthentication()); the control node therefore runs PasswordAuthenticator and the writer is an ordinary role.
        from cassandra.auth import PlainTextAuthProvider
        for _ in range(40):
            try:
                cl = Cluster(['127.0.0.1'], protocol_version=4, connect_timeout=30, auth_provider=PlainTextAuthProvider('cassandra', 'cassandra')); s = cl.connect(); break
            except Exception as e:
                say('waiting for the default superuser:', str(e)[:100]); time.sleep(5)
        s.default_timeout = 300
        s.execute("CREATE ROLE ord WITH PASSWORD = 'ord' AND LOGIN = true AND SUPERUSER = false")
        clw = Cluster(['127.0.0.1'], protocol_version=4, connect_timeout=30, auth_provider=PlainTextAuthProvider('ord', 'ord')); sw = clw.connect(); sw.default_timeout = 300
        reading('CONTROL_WRITER role=ord superuser=false')
    else:
        cl = Cluster(['127.0.0.1'], protocol_version=4, connect_timeout=30); s = cl.connect(); s.default_timeout = 300; sw = s
    reading('CLIENT_PROTOCOL_V4 negotiated=%s' % cl.protocol_version)
    s.execute("CREATE KEYSPACE ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    s.execute('CREATE TABLE ks.t1 (k int PRIMARY KEY, x int)'); s.execute('INSERT INTO ks.t1 (k, x) VALUES (1, 1)')
    # ---- workload W: plain set<int> writes
    for n in NS:
        t = 'tw_%d' % n
        s.execute('CREATE TABLE ks.%s (k int PRIMARY KEY, s set<int>)' % t)
        off = len(so()); t0 = int(time.time() * 1000)
        ins = sw.prepare('INSERT INTO ks.%s (k, s) VALUES (?, ?)' % t)
        try:
            sw.execute(ins, (1, set(range(n)))); res = 'accepted'
        except Exception as e:
            res = 'rejected %s: %s' % (type(e).__name__, str(e).replace('\n', ' ')[:300])
        t1 = int(time.time() * 1000)
        reading('W_INSERT N=%d %s' % (n, res))
        mt = memtable_bytes(t)
        if res == 'accepted':
            sh('bin/nodetool flush ks %s' % t); time.sleep(3)
            back = len(s.execute('SELECT s FROM ks.%s WHERE k = 1' % t).one()[0])
        else:
            back = -1
        reading('W_USAGE N=%d memtable_data_bytes=%d sstable_data_bytes=%d heapmax_kB=%d readback_elements=%d pack_calls=%d' % (n, mt, data_bytes(t), heap_between(t0, int(time.time() * 1000)), back, len(lines('CS_PACK ', off))))
    if mode == 'default':
        # ---- workload U: Java UDF returning list<int>
        s.execute("CREATE FUNCTION ks.mk(n int) CALLED ON NULL INPUT RETURNS list<int> LANGUAGE java AS 'java.util.ArrayList<Integer> l = new java.util.ArrayList<Integer>(); for (int i = 0; i < n; i++) l.add(i); return l;'")
        cl.shutdown()
        for pv in (4, 3):
            cu = Cluster(['127.0.0.1'], protocol_version=pv, connect_timeout=30); su = cu.connect(); su.default_timeout = 300
            for n in NS:
                off = len(so()); t0 = int(time.time() * 1000)
                try:
                    r = su.execute('SELECT ks.mk(%d) AS x FROM ks.t1 WHERE k = 1' % n).one()
                    res = 'ok elements=%d' % len(r.x)
                except Exception as e:
                    res = 'error %s: %s' % (type(e).__name__, str(e).replace('\n', ' ')[:300])
                t1 = int(time.time() * 1000)
                time.sleep(1)
                reading('U_QUERY proto=v%d N=%d %s heapmax_kB=%d' % (pv, n, res, heap_between(t0, t1)))
                reading('U_BYTEMAN proto=v%d N=%d %s' % (pv, n, ' | '.join(l[:120] for l in lines('CS_', off))))
            cu.shutdown()
finally:
    stopflag.set(); time.sleep(1)
    subprocess.run('cp %s/logs/system.log %s/system.log; cp %s/logs/system.log.*.zip %s/ 2>/dev/null; cp %s/stdout.txt %s/stdout.txt; ls -lR %s/data/ks > %s/datalist.txt' % (N, OUT, N, OUT, N, OUT, N, OUT), shell=True)
    stop(); time.sleep(2)
    say('daemons left: %d' % len(daemons()))
