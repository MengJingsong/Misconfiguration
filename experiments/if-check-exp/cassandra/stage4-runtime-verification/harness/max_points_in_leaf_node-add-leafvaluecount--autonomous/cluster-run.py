#!/usr/bin/env python3
"""One cluster-tier run of max_points_in_leaf_node-add-leafvaluecount--autonomous (B3e + amendments C1-C5, 2026-10-28).
usage: cluster-run.py <label> <variant A|B|C> <rows> <buffer_mib> <slot>
Run copy ~/s4-b34-v<variant> (constant 128 / 1024 / 16384, see make-variants.sh); node root ~/stage4-tmp/b34/c1/<label>; slot k -> 127.0.0.<k+1>, JMX 7199+100k.
Steps: node (8G heap, 5GiB memtable) with Byteman alloc rule -> CREATE ks.t + SAI index -> cassandra-stress user n=<rows> -> nodetool flush -> nodetool rebuild_index -> readings.
Output $OUT/<label>/: cmdlog.txt readings.txt heap.csv gc-*.log stdout.txt system-log-excerpt.txt components.txt stress.txt. The node is stopped on any exit."""
import os, re, subprocess, sys, time
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
from nodelib import Node, HOME
label, variant, rows, bufmib, slot = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
C = HOME + '/s4-b34-v' + variant
OUT = os.path.join(os.environ.get('OUT', HOME + '/s4-b34-logs/b1/run1/cluster'), label)
yaml = ('memtable_heap_space: 5GiB\nmemtable_allocation_type: heap_buffers\ncommitlog_total_space: 8GiB\nmemtable_flush_writers: 1\n'
        'sai_options:\n    segment_write_buffer_size: %dMiB\n' % bufmib)
n = Node(C, HOME + '/stage4-tmp/b34/c1/' + label, OUT, label, heap='8G', yaml_lines=yaml, byteman_script=H + '/alloc.btm', jmx_port=7199 + 100 * slot, ip='127.0.0.%d' % (slot + 1))
rd = open(OUT + '/readings.txt', 'a')
def reading(m): n.say(m); rd.write(m + '\n'); rd.flush()
n.say('== %s variant=%s rows=%d buffer=%dMiB slot=%d start %d' % (label, variant, rows, bufmib, slot, time.time() * 1000))
n.say(n.sh('javap -constants -p -cp %s/build/apache-cassandra-5.0.9-SNAPSHOT.jar org.apache.cassandra.index.sai.disk.v1.bbtree.NumericIndexWriter | grep MAX_POINTS; df -h %s | tail -1' % (C, HOME), show=400))
n.make_conf(); n.start(); n.sampler()
# JMX poll of SegmentBufferSpaceUsedBytes (added 2026-10-28 while the chain was running: runs B2 and B8a, started before this block existed, have no segbuf.csv)
os.makedirs(H + '/cls', exist_ok=True); subprocess.run('javac -d %s/cls %s/Jmx.java' % (H, H), shell=True, check=True)
stopf = OUT + '/jmx.stop'
if os.path.exists(stopf): os.remove(stopf)
jm = subprocess.Popen('java -cp %s/cls Jmx %d poll 2000 100000 %s org.apache.cassandra.metrics:type=StorageAttachedIndex,name=SegmentBufferSpaceUsedBytes Value > %s/segbuf.csv 2>&1' % (H, n.jmx, stopf, OUT), shell=True)
def sysmark(): return os.path.getsize(n.T + '/logs/system.log')
n.cql("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
n.cql('CREATE TABLE IF NOT EXISTS ks.t (id bigint PRIMARY KEY, v int)')
n.cql("CREATE CUSTOM INDEX t_v_idx ON ks.t(v) USING 'StorageAttachedIndex'")
n.say(n.cql('SELECT index_name, is_queryable, is_building FROM system_views.sai_column_indexes'))
sm0 = sysmark()
t0 = time.time()
so = n.stress('user profile=%s/profile-t.yaml "ops(insert=1)" n=%d no-warmup -rate threads=64' % (H, rows))
open(OUT + '/stress.txt', 'w').write(so)
reading('LOAD_SECONDS %.1f rows=%d' % (time.time() - t0, rows))
sysl = open(n.T + '/logs/system.log', errors='replace').read()[sm0:]
reading('AUTO_FLUSHES_DURING_LOAD %d' % len(re.findall(r'Enqueuing flush of ks\.t', sysl)))
time.sleep(5)
fl0 = int(time.time() * 1000); reading('FLUSH_START_MS %d' % fl0)
n.nt('flush ks t'); fl1 = int(time.time() * 1000); reading('FLUSH_END_MS %d' % fl1)
time.sleep(5)
n.say(n.sh("find %s/data -name '*SAI*' -type f -printf '%%s %%p\\n' | sort -k2" % n.T, show=3000))
comps = n.sh("find %s/data -name '*SAI*' -type f -printf '%%s %%p\\n'" % n.T, show=0)
open(OUT + '/components-after-flush.txt', 'w').write(comps)
n.say(n.cql('SELECT count(*) FROM system_views.sai_sstable_index_segments'))
rb0 = int(time.time() * 1000); reading('REBUILD_START_MS %d' % rb0)
n.nt('rebuild_index ks t t_v_idx', tmo=7200); rb1 = int(time.time() * 1000); reading('REBUILD_END_MS %d' % rb1)
time.sleep(5)
comps = n.sh("find %s/data -name '*SAI*' -type f -printf '%%s %%p\\n'" % n.T, show=0)
open(OUT + '/components-after-rebuild.txt', 'w').write(comps)
n.say(n.cql('SELECT count(*) FROM system_views.sai_sstable_index_segments'))
n.say(n.cql('SELECT index_name, is_queryable, is_building FROM system_views.sai_column_indexes'))
open(stopf, 'w').write('x'); n.sampler_stop()
try: jm.wait(timeout=30)
except Exception: jm.kill()
subprocess.run('cp %s/logs/system.log %s/system.log' % (n.T, OUT), shell=True)
subprocess.run("grep -c 'too many nodes' %s/logs/system.log > %s/too-many-nodes-count.txt; grep -E '^WCS_' %s/stdout.txt > %s/wcs.txt; wc -l %s/wcs.txt" % (n.T, OUT, n.T, OUT, OUT), shell=True)
reading('TOO_MANY_NODES_LINES %s' % open(OUT + '/too-many-nodes-count.txt').read().strip())
reading('GLOBAL_LIMIT_EXCEEDED_LINES %s' % subprocess.run("grep -c 'Global limit of' %s/logs/debug.log" % n.T, shell=True, capture_output=True, text=True).stdout.strip())
subprocess.run('cp %s/logs/debug.log %s/debug.log' % (n.T, OUT), shell=True)
n.stop()
reading('RUN_DONE %s' % label)
