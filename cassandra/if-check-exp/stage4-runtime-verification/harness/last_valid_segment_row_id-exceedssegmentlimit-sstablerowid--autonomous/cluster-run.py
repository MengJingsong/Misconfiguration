#!/usr/bin/env python3
"""Cluster tier of last_valid_segment_row_id-exceedssegmentlimit-sstablerowid--autonomous (B3, amendments C1-C3, 2026-10-28).
usage: cluster-run.py seed <slot>                          load 5,000,000 rows of 1000 random bytes (ks.t3, column c0 text; defect D1 2026-10-28: the first attempt used cassandra-stress native mode, whose columns are blobs, and SAI rejects blob: "Unsupported type: blob"), flush, compact to one sstable, drain, copy the data dir to the seed
       cluster-run.py <label> <build std|small> <buffer_mib> <slot>    restore the seed, start the node (std = ~/s4-b34, small = ~/s4-b34-vS with LAST_VALID_SEGMENT_ROW_ID = 10000),
                                                              CREATE CUSTOM INDEX c0_idx on "C0", wait until built, record heap / segments / log lines
Node: 4G heap (G1), DEBUG logging as shipped, local disk. Output $OUT/<label>/."""
import os, re, subprocess, sys, time
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
from nodelib import Node, HOME
SEED = HOME + '/stage4-tmp/b34/c3/seed'
mode = sys.argv[1]
OUTB = os.environ.get('OUT', HOME + '/s4-b34-logs/b3/run1/cluster')
if mode == 'seed':
    slot = int(sys.argv[2]); label = 'seed'; C = HOME + '/s4-b34'
    n = Node(C, HOME + '/stage4-tmp/b34/c3/seednode', OUTB + '/seed', label, heap='4G', yaml_lines='', jmx_port=7199 + 100 * slot, ip='127.0.0.%d' % (slot + 1))
    n.make_conf(); n.start()
    so = n.stress('user profile=%s/profile-seed.yaml "ops(insert=1)" n=5000000 no-warmup -rate threads=64' % H)
    open(OUTB + '/seed/stress.txt', 'w').write(so)
    n.nt('flush'); n.nt('compact ks t3', tmo=14400)
    n.nt('tablestats ks.t3', show=3000)
    n.nt('drain'); n.stop()
    subprocess.run('rm -rf %s; mkdir -p %s; cp -a %s/data %s/data; du -sb %s/data' % (SEED, SEED, n.T, SEED, SEED), shell=True)
    subprocess.run('rm -rf %s' % n.T, shell=True)
    sys.exit(0)
label, build, bufmib, slot = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
C = HOME + ('/s4-b34' if build == 'std' else '/s4-b34-vS')
OUT = os.path.join(OUTB, label)
yaml = 'sai_options:\n    segment_write_buffer_size: %dMiB\n' % bufmib
n = Node(C, HOME + '/stage4-tmp/b34/c3/' + label, OUT, label, heap='4G', yaml_lines=yaml, jmx_port=7199 + 100 * slot, ip='127.0.0.%d' % (slot + 1))
rd = open(OUT + '/readings.txt', 'a')
def reading(m): n.say(m); rd.write(m + '\n'); rd.flush()
n.say('== %s build=%s buffer=%dMiB slot=%d start %d' % (label, build, bufmib, slot, time.time() * 1000))
n.say(n.sh('javap -constants -p -cp %s/build/apache-cassandra-5.0.9-SNAPSHOT.jar org.apache.cassandra.index.sai.disk.v1.segment.SegmentBuilder | grep LAST_VALID; df -h %s | tail -1' % (C, HOME), show=400))
n.make_conf()
n.sh('cp -a %s/data/. %s/data/' % (SEED, n.T), show=200)
n.start()
os.makedirs(H + '/cls', exist_ok=True); subprocess.run('javac -d %s/cls %s/Jmx.java' % (H, H), shell=True, check=True)
stopf = OUT + '/jmx.stop'
if os.path.exists(stopf): os.remove(stopf)
bean = 'org.apache.cassandra.metrics:type=StorageAttachedIndex,name=SegmentBufferSpaceUsedBytes'
jm = subprocess.Popen('java -cp %s/cls Jmx %d poll 2000 100000 %s %s Value > %s/segbuf.csv 2>&1' % (H, n.jmx, stopf, bean, OUT), shell=True)
n.sampler()
n.nt('disableautocompaction ks t3')
n.say(n.sh("grep -E 'Global limit|Flushed segment' %s/logs/debug.log | wc -l" % n.T, show=100))
dl0 = os.path.getsize(n.T + '/logs/debug.log')
b0 = int(time.time() * 1000); reading('INDEX_CREATE_MS %d' % b0)
n.say(n.cql("CREATE CUSTOM INDEX c0_idx ON ks.t3(c0) USING 'StorageAttachedIndex'"))
for _ in range(1800):
    r = n.sh("bin/cqlsh %s -e 'SELECT is_queryable, is_building FROM system_views.sai_column_indexes'" % n.ip, show=0)
    if re.search(r'True\s*\|\s*False', r): break
    time.sleep(10)
b1 = int(time.time() * 1000); reading('INDEX_QUERYABLE_MS %d' % b1)
time.sleep(5)
open(OUT + '/segments.txt', 'w').write(n.sh("bin/cqlsh %s -e 'PAGING OFF; SELECT sstable_name, segment_row_id_offset, cell_count, min_sstable_row_id, max_sstable_row_id FROM system_views.sai_sstable_index_segments'" % n.ip, show=0, tmo=600))
dl = open(n.T + '/logs/debug.log', errors='replace').read()
open(OUT + '/debug-sai-lines.txt', 'w').write('\n'.join(l for l in dl.splitlines() if 'Global limit' in l or 'Flushed segment' in l or 'released' in l))
reading('GLOBAL_LIMIT_LINES %d FLUSHED_SEGMENT_LINES %d' % (dl.count('Global limit of'), dl.count('Flushed segment with')))
comps = n.sh("find %s/data -name '*SAI*' -type f -printf '%%s %%p\\n'" % n.T, show=0)
open(OUT + '/components.txt', 'w').write(comps)
open(stopf, 'w').write('x'); n.sampler_stop()
try: jm.wait(timeout=30)
except Exception: jm.kill()
subprocess.run('cp %s/logs/system.log %s/system.log' % (n.T, OUT), shell=True)
n.stop()
reading('RUN_DONE %s' % label)
