#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of the EXCESS_WASTE_* cases (written 2026-10-28; one script for the four case files).
usage: cluster-run.py run <tag> <variant> <workload> <memtable_heap_space_MiB> [alloc=heap_buffers] [seconds=120]
       cluster-run.py down
One node lifetime = one cell: fresh data, the variant's patched AtomicBTreePartition class directory (mkvariant.sh) first on the class path
through CASSANDRA_INCLUDE, MAX_HEAP_SIZE 8G, the workload (LoadGen) for <seconds>, samplers, thread dumps, flush, stop.
Run copy ~/s4-ew, node dir ~/s4-ew-node, logs ~/stage4-logs/ew/cluster/<tag>/. Exit 1 on a failed check; the node is stopped on every exit.
Variants: v10m stock literal (instrumented), v1 = 1L, v1024 = 1024L, v1m = 1 MiB, v100m = 100 MiB, v1g = 1 GiB, v2p40 = 1L << 40.
Workloads: WA hot random ck 256 threads 1 row 200 B | WB hot 64 thr batches 2000 x 100 B | WC cold (1M pks) same | WD hot 32 thr 64 x 1 KiB |
           WE hot 32 thr 1200 x 8 KiB | WF hot 64 thr 1 row 4 KiB | WG 64 partitions (one per thread) 1 row 4 KiB | W1 hot 1 thr 64 x 1 KiB"""
import os, re, shutil, subprocess, sys, time, glob

HOME = os.path.expanduser('~'); C = HOME + '/s4-ew'; N = HOME + '/s4-ew-node'; H = os.path.dirname(os.path.abspath(__file__))
WL = {'WA': (256, 'hotrand', 1, 200), 'WB': (64, 'hot', 2000, 100), 'WC': (64, 'cold', 2000, 100), 'WD': (32, 'hot', 64, 1024),
      'WE': (32, 'hot', 1200, 8192), 'WF': (64, 'hot', 1, 4096), 'WG': (64, 'perthread', 1, 4096), 'W1': (1, 'hot', 64, 1024)}
cmd = sys.argv[1]
tag = sys.argv[2] if cmd == 'run' else 'down'
LOGS = HOME + '/stage4-logs/ew/cluster/' + tag; os.makedirs(LOGS, exist_ok=True)
SUMMARY = open(LOGS + '/summary.txt', 'a')


def note(s):
    print(s, flush=True); SUMMARY.write(s + '\n'); SUMMARY.flush()


def sh(c, timeout=900, env=None, cwd=None):
    r = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd or C)
    return r.returncode, (r.stdout or '') + (r.stderr or '')


def pid():
    try: return int(open(N + '/cassandra.pid').read().strip())
    except Exception: return None


def alive():
    p = pid(); return p is not None and os.path.exists('/proc/%d' % p)


def daemons():
    return sh("ps -eo cmd | grep '[C]assandraDaemon' || true")[1].strip()


def stop():
    if alive():
        sh('bin/nodetool stopdaemon', timeout=180)
        for _ in range(120):
            if not alive(): break
            time.sleep(1)
        if alive(): subprocess.run(['kill', '-9', str(pid())]); time.sleep(2)
    return daemons()


def fail(m):
    note('FAIL: ' + m); stop(); sys.exit(1)


if cmd == 'down':
    note('down: ' + (stop() or 'no CassandraDaemon left')); sys.exit(0)
variant, wk, heap = sys.argv[3], sys.argv[4], int(sys.argv[5])
alloc = sys.argv[6] if len(sys.argv) > 6 else 'heap_buffers'
secs = int(sys.argv[7]) if len(sys.argv) > 7 else 120
threads, mode, rows, vb = WL[wk]
note('=== %s: variant %s workload %s (%d thr, %s, %d rows x %d B) memtable_heap_space %d MiB alloc %s %d s' % (tag, variant, wk, threads, mode, rows, vb, heap, alloc, secs))
if daemons(): fail('a CassandraDaemon is already running')
vdir = HOME + '/s4-ew-var/' + variant
if not os.path.isdir(vdir): fail('no variant dir ' + vdir)
if os.path.isdir(N): shutil.rmtree(N)
os.makedirs(N)
for d in ('logs', 'data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw'): os.makedirs('%s/%s' % (N, d))
shutil.copytree(C + '/conf', N + '/conf')
y = open(N + '/conf/cassandra.yaml').read()
add = {'cluster_name': 'stage4-ew', 'num_tokens': '1', 'listen_address': '127.0.0.1', 'rpc_address': '127.0.0.1',
       'commitlog_directory': N + '/commitlog', 'hints_directory': N + '/hints', 'saved_caches_directory': N + '/saved_caches', 'cdc_raw_directory': N + '/cdc_raw',
       'memtable_allocation_type': alloc, 'memtable_heap_space': '%dMiB' % heap, 'memtable_offheap_space': '%dMiB' % heap, 'memtable_flush_writers': '2',
       'concurrent_writes': '128', 'commitlog_sync': 'periodic', 'commitlog_segment_size': '32MiB', 'commitlog_total_space': '1024MiB',
       'hinted_handoff_enabled': 'false', 'write_request_timeout': '120000ms', 'native_transport_timeout': '300s',
       'native_transport_max_request_data_in_flight': '2048MiB', 'native_transport_max_request_data_in_flight_per_ip': '2048MiB',
       'endpoint_snitch': 'SimpleSnitch'}
for k in add:  # drop the shipped uncommented line of a key we set; commented ones are left (a later line wins nothing, so there must be exactly one live line)
    y = re.sub(r'^%s:.*\n' % k, '', y, flags=re.M)
y = re.sub(r'^data_file_directories:\n(\s+-.*\n)+', '', y, flags=re.M)
y = re.sub(r'(- seeds:\s*)"[^"]*"', r'\1"127.0.0.1:7000"', y, count=1)
y += '\n# ---- stage4 ew lines ----\n' + ''.join('%s: %s\n' % kv for kv in add.items()) + 'data_file_directories:\n    - %s/data\n' % N
open(N + '/conf/cassandra.yaml', 'w').write(y)
for k in list(add) + ['data_file_directories']:
    if len(re.findall(r'^%s:' % k, y, re.M)) != 1: fail('yaml key %s appears %d times' % (k, len(re.findall(r'^%s:' % k, y, re.M))))
# the include file: the original class path with the variant directory first
open(N + '/include.sh', 'w').write('. "%s/bin/cassandra.in.sh"\nCLASSPATH="%s:$CLASSPATH"\n' % (C, vdir))
env = dict(os.environ, CASSANDRA_HOME=C, CASSANDRA_CONF=N + '/conf', CASSANDRA_LOG_DIR=N + '/logs', CASSANDRA_INCLUDE=N + '/include.sh', MAX_HEAP_SIZE='8G')
env['JVM_EXTRA_OPTS'] = '-Xlog:gc*:file=%s/gc.log:time,uptime:filecount=0 -Dstage4.wastelog=%s/s4waste.csv' % (N, N)
env.pop('HEAP_NEWSIZE', None)
rc, o = sh('bin/cassandra -p %s/cassandra.pid > %s/stdout.txt 2>&1' % (N, N), env=env)
lp = N + '/logs/system.log'
for _ in range(300):
    time.sleep(2)
    if not alive(): fail('daemon died during start; see ' + N + '/stdout.txt')
    if os.path.exists(lp) and 'Starting listening for CQL clients' in open(lp, errors='replace').read(): break
else: fail('no CQL listener')
P = pid(); time.sleep(5)
cl = open('/proc/%d/cmdline' % P).read().replace('\0', ' ')
note('READBACK cmdline: ' + ' '.join(x for x in cl.split() if x.startswith(('-Xm', '-Xlog', '-Dstage4', '-XX:+UseG1'))))
cp = [x for x in open('/proc/%d/environ' % P, errors='replace').read().split('\0') if x.startswith('CASSANDRA_INCLUDE')]
note('READBACK include: %s; variant dir first: %s' % (cp, open(N + '/include.sh').read().splitlines()[-1][:80]))
nodedir_ok = (N + '/data') in open(N + '/conf/cassandra.yaml').read()
if not nodedir_ok: fail('data dir not in yaml')
m = None
for _ in range(20):
    time.sleep(1)
    try: m = re.search(r'# C=(\S+) OFFSET=(\S+)', open(N + '/s4waste.csv').read())
    except Exception: m = None
    if m: break
if not m: fail('the S4Waste counter file shows no constant: the variant class was not loaded (or not yet used)')
note('READBACK constant in the running node: EXCESS_WASTE_BYTES=%s EXCESS_WASTE_OFFSET=%s' % (m.group(1), m.group(2)))
rc, o = sh('bin/nodetool setlogginglevel org.apache.cassandra.db.memtable.SkipListMemtable TRACE'); note('setlogginglevel rc=%d' % rc)
rc, o = sh('bin/cqlsh 127.0.0.1 -e "CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {\'class\':\'SimpleStrategy\',\'replication_factor\':1}; CREATE TABLE IF NOT EXISTS ks.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck)); DESCRIBE TABLE ks.t"')
open(LOGS + '/schema.txt', 'w').write(o)
if 'CREATE TABLE ks.t' not in o: fail('schema not created: ' + o[:200])
# samplers
CLS = HOME + '/s4-ew-cls'; os.makedirs(CLS, exist_ok=True)
sh('javac -d %s %s/Jmx.java' % (CLS, H)); sh('javac -cp "%s/build/lib/jars/*" -d %s %s/LoadGen.java' % (C, CLS, H))
beans = ['org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=t,name=%s Value' % x for x in ('AllMemtablesHeapSize', 'MemtableOnHeapSize', 'MemtableOffHeapSize', 'MemtableLiveDataSize', 'MemtableColumnsCount')]
beans += ['org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=t,name=MemtableSwitchCount Count', 'java.lang:type=Memory HeapMemoryUsage',
          'org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=t,name=LiveDiskSpaceUsed Count']
stopf = LOGS + '/stop'
if os.path.exists(stopf): os.remove(stopf)
jm = subprocess.Popen('java -cp %s Jmx 7199 poll 1000 100000 %s %s > %s/samples.csv 2> %s/sampler.err' % (CLS, stopf, ' '.join(beans), LOGS, LOGS), shell=True)
open(LOGS + '/samples-header.txt', 'w').write('ts,' + ','.join(b.split('name=')[1].replace(' ', ':') if 'name=' in b else b.replace(' ', ':') for b in beans) + '\n')
t0 = time.time(); note('workload start %d' % (t0 * 1000))
ld = subprocess.Popen('java -Xmx2g -cp "%s:%s/build/lib/jars/*" LoadGen 127.0.0.1 %d %d %s %d %d %s %s/load.csv 6000 > %s/loadgen.out 2>&1' % (CLS, C, threads, secs, mode, rows, vb, stopf, LOGS, LOGS), shell=True)
dumps = 0; nxt_dump = t0 + 20; nxt_df = t0
with open(LOGS + '/du.csv', 'w') as du:
    while ld.poll() is None:
        now = time.time()
        if now >= nxt_df:
            free = int(sh("df --output=avail -B1G %s | tail -1" % N)[1].strip() or 0)
            sz = sh('du -sb %s/data %s/commitlog | cut -f1 | paste -sd,' % (N, N))[1].strip()
            du.write('%d,%d,%s\n' % (now * 1000, free, sz)); du.flush(); nxt_df = now + 5
            if free < 8:
                open(stopf, 'w').close(); note('STOP: free disk %d GB' % free)
        if now >= nxt_dump and dumps < 5:
            rc, o = sh('jcmd %d Thread.print' % P, timeout=120); open('%s/threads-%d.txt' % (LOGS, dumps), 'w').write(o)
            dumps += 1; nxt_dump = now + 20
        time.sleep(1)
note('workload end %d rc=%s: %s' % (time.time() * 1000, ld.returncode, open(LOGS + '/loadgen.out').read().strip()[-200:]))
time.sleep(5)
rc, o = sh('bin/nodetool tablestats ks.t'); open(LOGS + '/tablestats-before-flush.txt', 'w').write(o)
rc, o = sh('bin/nodetool flush'); note('flush rc=%d' % rc)
rc, o = sh('bin/nodetool tablestats ks.t'); open(LOGS + '/tablestats.txt', 'w').write(o)
open(stopf, 'w').close(); time.sleep(2)
try: jm.wait(timeout=20)
except Exception: jm.kill()
for f in ('system.log', 'debug.log', 'gc.log'):
    src = N + ('/' + f if f == 'gc.log' else '/logs/' + f)
    if os.path.exists(src): shutil.copy(src, LOGS + '/' + f)
shutil.copy(N + '/s4waste.csv', LOGS + '/s4waste.csv')
note('STOPPED: ' + (stop() or 'no CassandraDaemon left'))
sh('du -sb %s/data > %s/du-final.txt' % (N, LOGS))
shutil.rmtree(N)
note('=== %s end; node dir removed' % tag)
