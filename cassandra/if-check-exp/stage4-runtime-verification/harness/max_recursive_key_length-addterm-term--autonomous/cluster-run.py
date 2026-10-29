#!/usr/bin/env python3
"""One cluster-tier run of max_recursive_key_length-addterm-term--autonomous (B3e + amendment C2/C3, 2026-10-28).
usage: cluster-run.py <label> <build S|Z> <alloc heap|off> <L> <rows> <slot> [guard]
S = ~/s4-b34 (stock, constant 128), Z = ~/s4-b34-vZ (constant 0). Node: 2G heap (G1), memtable_heap_space 1024MiB, memtable_offheap_space 1024MiB, memtable_allocation_type heap_buffers|offheap_objects;
'guard' adds sai_string_term_size_{warn,fail}_threshold 1KiB. Table ks.t (id bigint pk, v text) with a SAI index; cassandra-stress user, v size fixed(L), 16 threads, n=<rows>, no flush;
after 60 s idle: tablestats, MemtableIndexBytes (JMX), jcmd GC.run + GC.heap_info, VmRSS/RssAnon, oversize-term warnings."""
import os, re, subprocess, sys, time
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
from nodelib import Node, HOME
label, build, alloc, L, rows, slot = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6])
guard = len(sys.argv) > 7 and sys.argv[7] == 'guard'
C = HOME + ('/s4-b34' if build == 'S' else '/s4-b34-vZ')
OUT = os.path.join(os.environ.get('OUT', HOME + '/s4-b34-logs/b4/run1/cluster'), label)
yaml = 'memtable_heap_space: 1024MiB\nmemtable_offheap_space: 1024MiB\nmemtable_allocation_type: %s\n' % ('heap_buffers' if alloc == 'heap' else 'offheap_objects')
if guard: yaml += 'sai_string_term_size_warn_threshold: 1KiB\nsai_string_term_size_fail_threshold: 1KiB\n'
n = Node(C, HOME + '/stage4-tmp/b34/c4/' + label, OUT, label, heap='2G', yaml_lines=yaml, jmx_port=7199 + 100 * slot, ip='127.0.0.%d' % (slot + 1))
rd = open(OUT + '/readings.txt', 'a')
def reading(m): n.say(m); rd.write(m + '\n'); rd.flush()
prof = OUT + '/profile.yaml'
open(prof, 'w').write("""keyspace: ks
keyspace_definition: |
  CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};
table: t
table_definition: |
  CREATE TABLE IF NOT EXISTS ks.t (id bigint PRIMARY KEY, v text);
columnspec:
  - name: id
    population: seq(1..%d)
  - name: v
    size: fixed(%d)
    population: uniform(1..1000000000)
insert:
  partitions: fixed(1)
  batchtype: UNLOGGED
queries: {}
""" % (rows, L))
n.say('== %s build=%s alloc=%s L=%d rows=%d slot=%d guard=%s start %d' % (label, build, alloc, L, rows, slot, guard, time.time() * 1000))
n.say(n.sh("javap -p -c -cp %s/build/apache-cassandra-5.0.9-SNAPSHOT.jar org.apache.cassandra.index.sai.memory.TrieMemoryIndex | grep -A30 'void addTerm' | grep -E 'sipush|bipush|ifgt|if_icmpgt|iconst_0' | head -3" % C, show=300))
n.make_conf(); n.start()
os.makedirs(H + '/cls', exist_ok=True); subprocess.run('javac -d %s/cls %s/Jmx.java' % (H, H), shell=True, check=True)
JM = 'java -cp %s/cls Jmx %d query "org.apache.cassandra.metrics:type=StorageAttachedIndex,*,name=MemtableIndexBytes" Value' % (H, n.jmx)
def heapinfo():
    subprocess.run('jcmd %d GC.run' % n.pid, shell=True, capture_output=True)
    time.sleep(2)
    hi = subprocess.run('jcmd %d GC.heap_info' % n.pid, shell=True, capture_output=True, text=True).stdout
    m = re.search(r'used (\d+)K', hi)
    st = dict(l.split(':', 1) for l in open('/proc/%d/status' % n.pid).read().splitlines() if ':' in l)
    return 'heapUsedAfterGC_kB=%s VmRSS_kB=%s RssAnon_kB=%s' % (m.group(1) if m else -1, st['VmRSS'].split()[0], st['RssAnon'].split()[0])
n.cql("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
n.cql('CREATE TABLE IF NOT EXISTS ks.t (id bigint PRIMARY KEY, v text)')
n.cql("CREATE CUSTOM INDEX t_v_idx ON ks.t(v) USING 'StorageAttachedIndex'")
reading('BASELINE ' + heapinfo() + ' MemtableIndexBytes=' + re.sub(r'\s+', ' ', n.sh(JM, show=300)).strip())
sm0 = os.path.getsize(n.T + '/logs/system.log')
t0 = time.time()
so = n.stress('user profile=%s "ops(insert=1)" n=%d no-warmup -rate threads=16' % (prof, rows))
open(OUT + '/stress.txt', 'w').write(so)
reading('LOAD_SECONDS %.1f rows=%d L=%d' % (time.time() - t0, rows, L))
time.sleep(60)
sysl = open(n.T + '/logs/system.log', errors='replace').read()[sm0:]
reading('FLUSHES_DURING_RUN %d' % len(re.findall(r'Enqueuing flush of ks\.t', sysl)))
reading('OVERSIZE_WARNINGS %d' % sysl.count('is too large and cannot be indexed'))
reading('MEMTABLE_INDEX_BYTES ' + re.sub(r'\s+', ' ', n.sh(JM, show=300)).strip())
ts = n.nt('tablestats ks.t', show=0)
open(OUT + '/tablestats.txt', 'w').write(ts)
reading('TABLESTATS ' + ' | '.join(l.strip() for l in ts.splitlines() if 'Memtable' in l))
reading('AFTER_RUN ' + heapinfo())
subprocess.run('cp %s/logs/system.log %s/system.log' % (n.T, OUT), shell=True)
n.stop()
reading('RUN_DONE %s' % label)
