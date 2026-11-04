#!/usr/bin/env python3
"""Cluster-tier client. Usage:
  loader.py schema <tree> <host> <port> <mode|NONE>        create ks.t (and a SASI index unless NONE; mode CONTAINS or PREFIX, analyzed=false)
  loader.py load   <tree> <host> <port> <size> <rowcap> <inflight> <stopfile> <rowslog> <pausefile>
        insert rows of exactly <size> random ASCII chars (seed = size), until <rowcap> rows or <stopfile> exists;
        appends 'epoch_ms,rows' to <rowslog> after every row (inflight 1) or every 1000 rows
  loader.py verify <tree> <host> <port> <size> <mode>      one read by key (row 0) and one LIKE query on 20 characters of row 0's value"""
import sys, glob, random, time, os, uuid
cmd, tree, host, port = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
sys.path.insert(0, glob.glob(tree + '/lib/cassandra-driver-internal-only-*.zip')[0] + '/cassandra-driver-3.29.0')
from cassandra.cluster import Cluster
from cassandra.policies import DCAwareRoundRobinPolicy
cl = Cluster([host], port=port, protocol_version=4, load_balancing_policy=DCAwareRoundRobinPolicy(), token_metadata_enabled=False, connect_timeout=30)
s = cl.connect()
s.default_timeout = 300
ALNUM = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
def value(size, i):
    return ''.join(random.Random(size * 1000003 + i).choices(ALNUM, k=size))
if cmd == 'schema':
    mode = sys.argv[5]
    s.execute("CREATE KEYSPACE ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    s.execute("CREATE TABLE ks.t (id uuid PRIMARY KEY, v text)")
    if mode != 'NONE':
        opts = "'mode':'%s','analyzed':'false'" % mode
        s.execute("CREATE CUSTOM INDEX t_v_idx ON ks.t (v) USING 'org.apache.cassandra.index.sasi.SASIIndex' WITH OPTIONS = {%s}" % opts)
        print('index created with options', opts, flush=True)
    else:
        print('no index', flush=True)
elif cmd == 'load':
    size, rowcap, inflight, stopfile, rowslog, pausefile = int(sys.argv[5]), int(sys.argv[6]), int(sys.argv[7]), sys.argv[8], sys.argv[9], sys.argv[10]
    ps = s.prepare("INSERT INTO ks.t (id, v) VALUES (?, ?)")
    f = open(rowslog, 'a')
    t0 = time.time(); pend = []; n = 0
    while n < rowcap and not os.path.exists(stopfile):
        while os.path.exists(pausefile) and not os.path.exists(stopfile):
            time.sleep(0.05)
        v = value(size, n)
        assert len(v) == size
        pend.append(s.execute_async(ps, (uuid.UUID(int=n + 1), v)))
        if len(pend) >= inflight:
            pend.pop(0).result()
        n += 1
        if inflight == 1 or n % 1000 == 0:
            f.write('%d,%d\n' % (int(time.time() * 1000), n)); f.flush()
    for p in pend: p.result()
    f.write('%d,%d\n' % (int(time.time() * 1000), n)); f.flush()
    print('loaded %d rows of %d chars in %.1f s (stopped by %s)' % (n, size, time.time() - t0, 'stopfile' if os.path.exists(stopfile) else 'rowcap'), flush=True)
elif cmd == 'verify':
    size, mode = int(sys.argv[5]), sys.argv[6]
    v = value(size, 0)
    r = s.execute("SELECT id FROM ks.t WHERE id = " + str(uuid.UUID(int=1)))
    print('read_by_key rows=%d' % len(list(r)), flush=True)
    if mode != 'NONE':
        pat = v[100:120] if mode == 'CONTAINS' else v[:20]
        q = "SELECT id FROM ks.t WHERE v LIKE '%%%s%%'" % pat if mode == 'CONTAINS' else "SELECT id FROM ks.t WHERE v LIKE '%s%%'" % pat
        try:
            r = list(s.execute(q))
            print('like_hits=%d' % len(r), flush=True)
        except Exception as e:
            print('like_error=%r' % (e,), flush=True)
cl.shutdown()
