#!/usr/bin/env python3
"""Client of the recheck harness (protocol 4, bundled driver 3.29.0). Not upstream code.
  client.py <driver-dir> load <table> <rows> <width> <concurrency>   write ck 0..rows-1 of pk 1 (value = width zero bytes), CL ONE
  client.py <driver-dir> q <table> <L|none> <fetch|none>             one query; prints one JSON line
      fetch 'none' = unpaged (fetch_size=None); otherwise only the FIRST page is read (no page 2 is fetched).
      LIMIT 'none' = no LIMIT clause (the shipped default NO_LIMIT)."""
import sys, json, time
drv, mode = sys.argv[1], sys.argv[2]
sys.path.insert(0, drv)
from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
from cassandra.policies import DCAwareRoundRobinPolicy
from cassandra.query import SimpleStatement
from cassandra import ConsistencyLevel
from cassandra.concurrent import execute_concurrent_with_args
prof = ExecutionProfile(request_timeout=300, consistency_level=ConsistencyLevel.ONE, load_balancing_policy=DCAwareRoundRobinPolicy(local_dc='datacenter1'))
c = Cluster(['127.0.0.1'], port=9042, protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof},
            schema_metadata_enabled=False, token_metadata_enabled=False)
s = c.connect()
try:
    if mode == 'load':
        table, rows, width, conc = sys.argv[3], int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6])
        ps = s.prepare("INSERT INTO ks.%s (pk, ck, v) VALUES (1, ?, ?)" % table)
        res = execute_concurrent_with_args(s, ps, ((i, bytes(width)) for i in range(rows)), concurrency=conc, raise_on_first_error=True)
        print('loaded', len(res), 'rows of', width, 'B into', table)
    elif mode == 'q':
        table, L, fetch = sys.argv[3], sys.argv[4], sys.argv[5]
        q = "SELECT * FROM ks.%s WHERE pk = 1%s" % (table, '' if L == 'none' else ' LIMIT %s' % L)
        st = SimpleStatement(q, fetch_size=None if fetch == 'none' else int(fetch))
        out = {'q': q, 'fetch': fetch, 'rows': 0, 'bytes': 0, 'has_more_pages': None, 'err': None}
        time.sleep(1.0)
        out['t0_ms'] = int(time.time() * 1000)
        try:
            rs = s.execute(st)
            for r in rs.current_rows:
                out['rows'] += 1; out['bytes'] += len(r.v)
            out['has_more_pages'] = rs.has_more_pages
        except Exception as e:
            out['err'] = '%s: %s' % (type(e).__name__, str(e)[:400])
            out['err_codes'] = {str(k): v for k, v in (getattr(e, 'error_code_map', None) or {}).items()}
        out['t1_ms'] = int(time.time() * 1000)
        rs = None
        print(json.dumps(out))
finally:
    c.shutdown()
