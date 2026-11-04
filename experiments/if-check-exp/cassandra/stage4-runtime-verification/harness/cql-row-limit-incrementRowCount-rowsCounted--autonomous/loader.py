#!/usr/bin/env python3
"""Cluster-tier client of cql-row-limit-incrementRowCount-rowsCounted--autonomous (protocol 4, bundled driver). Not upstream code.
  loader.py <driver-dir> <addr> <port> load <table> <rows> <width>          write rows ck 0..rows-1 of pk 1, CL ONE
  loader.py <driver-dir> <addr> <port> q <table> <L|none> <fetch|none> <reps_label>   one query; prints one JSON line:
      {rows, bytes, pages, t0_ms, t1_ms, pages_ms:[[start,end],...], err}
      fetch 'none' = unpaged (fetch_size=None); LIMIT 'none' = no LIMIT clause."""
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
        table, rows, width = sys.argv[5], int(sys.argv[6]), int(sys.argv[7])
        ps = s.prepare("INSERT INTO ks.%s (pk, ck, v) VALUES (1, ?, ?)" % table)
        res = execute_concurrent_with_args(s, ps, [(i, bytes(width)) for i in range(rows)], concurrency=32, raise_on_first_error=True)
        print('loaded', len(res), 'rows of', width, 'B into', table)
    elif mode == 'q':
        table, L, fetch = sys.argv[5], sys.argv[6], sys.argv[7]
        q = "SELECT * FROM ks.%s WHERE pk = 1%s" % (table, '' if L == 'none' else ' LIMIT %s' % L)
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
