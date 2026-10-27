#!/usr/bin/env python3
"""Cluster-tier client of per-partition-limit-incrementRowCount-rowsincurrentpartition--autonomous (protocol 4, bundled driver). Not upstream code.
  loader.py <driver-dir> <addr> <port> load <table> <partitions> <rows-per-partition> <width>   write pk 1..P, ck 0..rows-1, CL ONE
  loader.py <driver-dir> <addr> <port> q <table> <n|none> <fetch|none>   one query `SELECT * FROM ks.<table> [PER PARTITION LIMIT n]`; prints one JSON line:
      {rows, bytes, pages, t0_ms, t1_ms, pages_ms:[[start,end],...], err}
      fetch 'none' = unpaged (fetch_size=None); n 'none' = no PER PARTITION LIMIT clause."""
import sys, json, time
drv, addr, port, mode = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
sys.path.insert(0, drv)
from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
from cassandra.policies import DCAwareRoundRobinPolicy
from cassandra.query import SimpleStatement
from cassandra import ConsistencyLevel
from cassandra.concurrent import execute_concurrent_with_args
prof = ExecutionProfile(request_timeout=300, consistency_level=ConsistencyLevel.ONE, load_balancing_policy=DCAwareRoundRobinPolicy(local_dc='datacenter1'))
c = Cluster([addr], port=port, protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof}, token_metadata_enabled=False)
s = c.connect()
try:
    if mode == 'load':
        table, parts, rows, width = sys.argv[5], int(sys.argv[6]), int(sys.argv[7]), int(sys.argv[8])
        ps = s.prepare("INSERT INTO ks.%s (pk, ck, v) VALUES (?, ?, ?)" % table)
        res = execute_concurrent_with_args(s, ps, [(p, i, bytes(width)) for p in range(1, parts + 1) for i in range(rows)], concurrency=32, raise_on_first_error=True)
        print('loaded', len(res), 'rows of', width, 'B into', table)
    elif mode == 'q':
        table, L, fetch = sys.argv[5], sys.argv[6], sys.argv[7]
        q = "SELECT * FROM ks.%s%s" % (table, '' if L == 'none' else ' PER PARTITION LIMIT %s' % L)
        st = SimpleStatement(q, fetch_size=None if fetch == 'none' else int(fetch))
        out = {'q': q, 'fetch': fetch, 'rows': 0, 'bytes': 0, 'pages': 0, 'pages_ms': [], 'err': None}
        time.sleep(1.5)   # let the server finish the connection's own start-up work before the window opens
        out['t0_ms'] = int(time.time() * 1000)
        try:
            ps0 = int(time.time() * 1000)
            rs = s.execute(st); pe = int(time.time() * 1000)
            while True:
                for r in rs.current_rows: out['rows'] += 1; out['bytes'] += len(r.v)
                out['pages'] += 1; out['pages_ms'].append([ps0, pe])
                if not rs.has_more_pages: break
                ps0 = int(time.time() * 1000); rs.fetch_next_page(); pe = int(time.time() * 1000)
        except Exception as e:
            out['err'] = '%s: %s' % (type(e).__name__, str(e)[:300]); out['err_codes'] = {str(k): v for k, v in (getattr(e, 'error_code_map', None) or {}).items()}
        out['t1_ms'] = int(time.time() * 1000)
        print(json.dumps(out))
finally:
    c.shutdown()
