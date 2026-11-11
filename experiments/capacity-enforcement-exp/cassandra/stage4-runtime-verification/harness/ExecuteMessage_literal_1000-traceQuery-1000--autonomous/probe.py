#!/usr/bin/env python3
"""Cluster tier client (B3c/B3d, amendments C1-C3 of 2026-10-27) of ExecuteMessage_literal_1000-traceQuery-1000--autonomous.
usage: probe.py <driver zip> schema
       probe.py <driver zip> cell <P|Q> <S> <N>     P = prepared EXECUTE (target), Q = unprepared QUERY with inline literal (control)
       probe.py <driver zip> scan
Lines: REQ path= S= i= key= len= suffix= match= | REQFAIL path= S= i= err= | CELL path= S= N= ok= fail= nmatch= maxlen= minlen= nsuffix= secs=
       ROW sid= bv= bvsuffix= q= sumv= | SCAN rows= nbv= maxbv= minbv= nbvsuffix= maxq= minq= sumv=
"""
import os, sys, time
zp = sys.argv[1]
ver = os.path.splitext(os.path.basename(zp))[0][len('cassandra-driver-internal-only-'):]
sys.path.insert(0, os.path.join(zp, 'cassandra-driver-' + ver))   # as bin/cqlsh.py does
from cassandra.cluster import Cluster
from cassandra.policies import DCAwareRoundRobinPolicy
from cassandra.query import SimpleStatement


def p(s):
    print(s, flush=True)


def connect():
    c = Cluster(['127.0.0.1'], port=9042, protocol_version=5, load_balancing_policy=DCAwareRoundRobinPolicy(),
                token_metadata_enabled=False, connect_timeout=30, idle_heartbeat_interval=0)
    s = c.connect()
    s.default_timeout = 300
    return c, s


def expected_stored(full):
    return full[:1000] + "...'" if len(full) > 1000 else full


mode = sys.argv[2]
c, s = connect()
if mode == 'schema':
    s.execute("CREATE KEYSPACE IF NOT EXISTS p WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    s.execute("CREATE TABLE IF NOT EXISTS p.t (k int PRIMARY KEY, v blob)")
    time.sleep(5)
    p('SCHEMA ok')
elif mode == 'cell':
    path, S, N = sys.argv[3], int(sys.argv[4]), int(sys.argv[5])
    for tb in ('system_traces.sessions', 'system_traces.events', 'p.t'):
        s.execute('TRUNCATE ' + tb, timeout=300)
    p('TRUNCATED system_traces.sessions system_traces.events p.t')
    ps = s.prepare("INSERT INTO p.t (k, v) VALUES (?, ?)") if path == 'P' else None
    ok = fail = nmatch = nsuf = 0
    lens = []
    t0 = time.time()
    for i in range(N):
        b = os.urandom(S)
        try:
            if path == 'P':
                rs = s.execute(ps, (i, b), trace=True, timeout=300)
                key = 'bound_var_1_v'
                exp = expected_stored('0x' + b.hex())
            else:
                q = "INSERT INTO p.t (k, v) VALUES (%d, 0x%s)" % (i, b.hex())
                rs = s.execute(SimpleStatement(q), trace=True, timeout=300)
                key = 'query'
                exp = q
            tr = rs.get_query_trace(max_wait_sec=10)
            v = (tr.parameters or {}).get(key)
            if v is None:
                fail += 1
                p('REQFAIL path=%s S=%d i=%d err=missing_key_%s' % (path, S, i, key))
                continue
            m = 1 if v == exp else 0
            sf = 1 if v.endswith("...'") else 0
            ok += 1; nmatch += m; nsuf += sf; lens.append(len(v))
            p('REQ path=%s S=%d i=%d key=%s len=%d suffix=%d match=%d' % (path, S, i, key, len(v), sf, m))
        except Exception as e:
            fail += 1
            p('REQFAIL path=%s S=%d i=%d err=%s:%s' % (path, S, i, type(e).__name__, str(e).replace('\n', ' ')[:200]))
    p('CELL path=%s S=%d N=%d ok=%d fail=%d nmatch=%d maxlen=%s minlen=%s nsuffix=%d secs=%.1f'
      % (path, S, N, ok, fail, nmatch, max(lens) if lens else -1, min(lens) if lens else -1, nsuf, time.time() - t0))
elif mode == 'scan':
    st = SimpleStatement("SELECT session_id, parameters FROM system_traces.sessions", fetch_size=5)
    rows = nbv = nbvs = 0
    bvs, qs = [], []
    sumv = 0
    for r in s.execute(st, timeout=300):
        prm = r.parameters or {}
        bv = prm.get('bound_var_1_v')
        q = prm.get('query')
        sv = sum(len(x) for x in prm.values())
        rows += 1; sumv += sv
        if bv is not None:
            nbv += 1; bvs.append(len(bv)); nbvs += 1 if bv.endswith("...'") else 0
        if q is not None:
            qs.append(len(q))
        p('ROW sid=%s bv=%d bvsuffix=%d q=%d sumv=%d' % (r.session_id, len(bv) if bv is not None else -1,
                                                          1 if (bv or '').endswith("...'") else 0, len(q) if q is not None else -1, sv))
    p('SCAN rows=%d nbv=%d maxbv=%d minbv=%d nbvsuffix=%d maxq=%d minq=%d sumv=%d'
      % (rows, nbv, max(bvs) if bvs else -1, min(bvs) if bvs else -1, nbvs, max(qs) if qs else -1, min(qs) if qs else -1, sumv))
c.shutdown()
