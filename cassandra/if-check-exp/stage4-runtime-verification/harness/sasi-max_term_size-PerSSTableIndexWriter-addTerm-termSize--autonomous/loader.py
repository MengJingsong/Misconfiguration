#!/usr/bin/env python3
"""Cluster-tier loader (stage 4, own harness). One invocation = one action on a running node.
  loader.py <tree> <host> <port> schema <kind> <cap_mb|->     kind: m | a | tc ; creates ks and the table(s) + SASI index(es)
  loader.py <tree> <host> <port> load <kind> <first> <last>   inserts ids [first, last)
  loader.py <tree> <host> <port> query <kind> <id>            prefix queries for the given id (m: a and b; tc: c)
Values: m/a  a = '%08d' + fill to 1023 bytes, b = 'b%07d' + fill to 1024 bytes (distinct by prefix)
        tc   c = 640 distinct 7-byte words ('w%06d', vocabulary 20,000, seeded per id) joined by spaces: 5,120 bytes."""
import sys, glob, random, time
tree, host, port, action, kind = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4], sys.argv[5]
sys.path.insert(0, glob.glob(tree + '/lib/cassandra-driver-internal-only-*.zip')[0] + '/cassandra-driver-3.29.0')
from cassandra.cluster import Cluster
from cassandra.policies import DCAwareRoundRobinPolicy
cl = Cluster([host], port=port, protocol_version=4, load_balancing_policy=DCAwareRoundRobinPolicy(), token_metadata_enabled=False, connect_timeout=30)
s = cl.connect(); s.default_timeout = 180
ALNUM = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
PAD = ''.join(random.Random(7).choice(ALNUM) for _ in range(16384))

def va(i): off = (i * 131) % 8192; return ('%08d' % i + PAD[off:off + 1100])[:1023]
def vb(i): off = (i * 197) % 8192; return ('b%07d' % i + PAD[off:off + 1100])[:1024]
def vc(i):
    r = random.Random(i); return ' '.join('w%06d' % w for w in r.sample(range(20000), 640))

if action == 'schema':
    cap = sys.argv[6]
    opt = "'mode':'PREFIX'" + ('' if cap == '-' else ",'max_compaction_flush_memory_in_mb':'%s'" % cap)
    s.execute("CREATE KEYSPACE ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    if kind == 'm':
        s.execute("CREATE TABLE ks.t (id bigint PRIMARY KEY, a text, b text)")
        for col in 'ab':
            s.execute("CREATE CUSTOM INDEX t_%s_idx ON ks.t (%s) USING 'org.apache.cassandra.index.sasi.SASIIndex' WITH OPTIONS = {%s}" % (col, col, opt))
    elif kind == 'a':
        s.execute("CREATE TABLE ks.t (id bigint PRIMARY KEY, a text)")
        s.execute("CREATE CUSTOM INDEX t_a_idx ON ks.t (a) USING 'org.apache.cassandra.index.sasi.SASIIndex' WITH OPTIONS = {%s}" % opt)
    elif kind == 'tc':
        s.execute("CREATE TABLE ks.tc (id bigint PRIMARY KEY, c text)")
        s.execute("CREATE CUSTOM INDEX tc_c_idx ON ks.tc (c) USING 'org.apache.cassandra.index.sasi.SASIIndex' WITH OPTIONS = {'mode':'PREFIX','analyzed':'true','analyzer_class':'org.apache.cassandra.index.sasi.analyzer.StandardAnalyzer'}")
    print('schema', kind, 'options', opt, flush=True)
elif action == 'load':
    first, last = int(sys.argv[6]), int(sys.argv[7])
    ps = {'m': "INSERT INTO ks.t (id, a, b) VALUES (?, ?, ?)", 'a': "INSERT INTO ks.t (id, a) VALUES (?, ?)", 'tc': "INSERT INTO ks.tc (id, c) VALUES (?, ?)"}[kind]
    ps = s.prepare(ps)
    t0 = time.time(); inflight = []
    for i in range(first, last):
        if kind == 'm': args = (i, va(i), vb(i))
        elif kind == 'a': args = (i, va(i))
        else: args = (i, vc(i))
        if kind != 'tc': assert len(args[1]) == 1023 and args[1].isascii()
        inflight.append(s.execute_async(ps, args))
        if len(inflight) >= 64: inflight.pop(0).result()
    for f in inflight: f.result()
    print('loaded ids [%d,%d) kind %s in %.1f s' % (first, last, kind, time.time() - t0), flush=True)
elif action == 'query':
    i = int(sys.argv[6])
    if kind in ('m', 'a'):
        for col, val in (('a', va(i)), ('b', vb(i))) if kind == 'm' else (('a', va(i)),):
            rows = list(s.execute("SELECT id FROM ks.t WHERE %s LIKE '%s%%' LIMIT 5" % (col, val[:64])))
            print('query %s prefix64 of id %d -> %d rows %s' % (col, i, len(rows), [r.id for r in rows]), flush=True)
    else:
        rows = list(s.execute("SELECT id FROM ks.tc WHERE c LIKE '%s%%' LIMIT 5" % vc(i).split(' ')[0]))
        print('query c first word of id %d -> %d rows (limit 5)' % (i, len(rows)), flush=True)
cl.shutdown()
