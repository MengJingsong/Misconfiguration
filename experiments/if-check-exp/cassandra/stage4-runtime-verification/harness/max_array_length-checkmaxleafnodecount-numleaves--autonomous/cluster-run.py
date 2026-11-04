#!/usr/bin/env python3
"""One cluster-tier run of max_array_length-checkmaxleafnodecount-numleaves--autonomous (B3e + amendment C1/C2, 2026-10-28).
usage: cluster-run.py <label> <rows> <buffer_mib> <slot>
Run copy ~/s4-b34-vB (the unmodified tree plus the stage4.Alloc Byteman helper in its jar). Node: 4G heap (G1), segment_write_buffer_size <buffer_mib>MiB, shipped memtable settings,
autocompaction disabled on ks.t2 (so the flush path and the rebuild path stay separate). Table ks.t2 (id bigint pk, vb bigint, vd decimal), SAI indexes t2_vb_idx and t2_vd_idx created
before the load; cassandra-stress user n=<rows>; nodetool flush; rebuild_index of both indexes. Samplers: jcmd heap_info (2 s), JMX SegmentBufferSpaceUsedBytes (2 s)."""
import os, re, subprocess, sys, time
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
from nodelib import Node, HOME
label, rows, bufmib, slot = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
C = HOME + '/s4-b34-vB'
OUT = os.path.join(os.environ.get('OUT', HOME + '/s4-b34-logs/b2/run1/cluster'), label)
yaml = 'sai_options:\n    segment_write_buffer_size: %dMiB\n' % bufmib
n = Node(C, HOME + '/stage4-tmp/b34/c2/' + label, OUT, label, heap='4G', yaml_lines=yaml, byteman_script=H + '/alloc.btm', jmx_port=7199 + 100 * slot, ip='127.0.0.%d' % (slot + 1))
rd = open(OUT + '/readings.txt', 'a')
def reading(m): n.say(m); rd.write(m + '\n'); rd.flush()
n.say('== %s rows=%d buffer=%dMiB slot=%d start %d' % (label, rows, bufmib, slot, time.time() * 1000))
n.make_conf(); n.start(); n.sampler()
os.makedirs(H + '/cls', exist_ok=True); subprocess.run('javac -d %s/cls %s/Jmx.java' % (H, H), shell=True, check=True)
stopf = OUT + '/jmx.stop'
if os.path.exists(stopf): os.remove(stopf)
bean = 'org.apache.cassandra.metrics:type=StorageAttachedIndex,name=SegmentBufferSpaceUsedBytes'
jm = subprocess.Popen('java -cp %s/cls Jmx %d poll 2000 100000 %s %s Value > %s/segbuf.csv 2>&1' % (H, n.jmx, stopf, bean, OUT), shell=True)
n.cql("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
n.cql('CREATE TABLE IF NOT EXISTS ks.t2 (id bigint PRIMARY KEY, vb bigint, vd decimal)')
n.cql("CREATE CUSTOM INDEX t2_vb_idx ON ks.t2(vb) USING 'StorageAttachedIndex'")
n.cql("CREATE CUSTOM INDEX t2_vd_idx ON ks.t2(vd) USING 'StorageAttachedIndex'")
n.nt('disableautocompaction ks t2')
n.say(n.cql('SELECT index_name, is_queryable, is_building FROM system_views.sai_column_indexes'))
sm0 = os.path.getsize(n.T + '/logs/system.log')
t0 = time.time()
so = n.stress('user profile=%s/profile-t2.yaml "ops(insert=1)" n=%d no-warmup -rate threads=64' % (H, rows))
open(OUT + '/stress.txt', 'w').write(so)
reading('LOAD_SECONDS %.1f rows=%d' % (time.time() - t0, rows))
sysl = open(n.T + '/logs/system.log', errors='replace').read()[sm0:]
reading('AUTO_FLUSHES_DURING_LOAD %d' % len(re.findall(r'Enqueuing flush of ks\.t2', sysl)))
time.sleep(5)
fl0 = int(time.time() * 1000); reading('FLUSH_START_MS %d' % fl0)
n.nt('flush ks t2'); fl1 = int(time.time() * 1000); reading('FLUSH_END_MS %d' % fl1)
time.sleep(5)
comps = n.sh("find %s/data -name '*SAI*' -type f -printf '%%s %%p\\n'" % n.T, show=0)
open(OUT + '/components-after-flush.txt', 'w').write(comps)
def segments(tag):
    o = n.sh("bin/cqlsh %s -e 'PAGING OFF; SELECT index_name, sstable_name, cell_count FROM system_views.sai_sstable_index_segments'" % n.ip, show=0, tmo=900)
    open(OUT + '/segments-%s.txt' % tag, 'w').write(o)
    cnt = {}
    for l in o.splitlines():
        p = [x.strip() for x in l.split('|')]
        if len(p) == 3 and p[0].startswith('t2_'): cnt[p[0]] = cnt.get(p[0], 0) + 1
    reading('SEGMENTS_%s %s' % (tag, sorted(cnt.items())))
segments('AFTER_FLUSH')
rb0 = int(time.time() * 1000); reading('REBUILD_START_MS %d' % rb0)
n.nt('rebuild_index ks t2 t2_vb_idx', tmo=14400); n.nt('rebuild_index ks t2 t2_vd_idx', tmo=14400)
rb1 = int(time.time() * 1000); reading('REBUILD_END_MS %d' % rb1)
time.sleep(5)
comps = n.sh("find %s/data -name '*SAI*' -type f -printf '%%s %%p\\n'" % n.T, show=0)
open(OUT + '/components-after-rebuild.txt', 'w').write(comps)
segments('AFTER_REBUILD')
open(stopf, 'w').write('x'); n.sampler_stop()
try: jm.wait(timeout=30)
except Exception: jm.kill()
subprocess.run('cp %s/logs/system.log %s/system.log; cp %s/logs/debug.log %s/debug.log' % (n.T, OUT, n.T, OUT), shell=True)
subprocess.run("grep -c 'too many nodes' %s/logs/system.log > %s/too-many-nodes-count.txt; grep -E '^WCS_' %s/stdout.txt > %s/wcs.txt; wc -l %s/wcs.txt" % (n.T, OUT, n.T, OUT, OUT), shell=True)
reading('TOO_MANY_NODES_LINES %s' % open(OUT + '/too-many-nodes-count.txt').read().strip())
reading('GLOBAL_LIMIT_EXCEEDED_LINES %s' % subprocess.run("grep -c 'Global limit of' %s/logs/debug.log" % n.T, shell=True, capture_output=True, text=True).stdout.strip())
n.stop()
reading('RUN_DONE %s' % label)
