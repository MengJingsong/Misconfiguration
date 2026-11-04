#!/usr/bin/env python3
"""Cluster tier client. usage:
  query.py hybrid --table t|mt --grp G [--n 200] [--limit 10] [--trace]
  query.py range  --n <rows in range> [--n 200] [--limit 100] [--start-idx I] [--trace]   (token(pk) > lo AND token(pk) <= hi, ORDER BY ANN)
Prints "OK <json>" (json has start_ms/end_ms, rows returned, bad rows for hybrid, and for --trace the trace event descriptions)."""
import argparse, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import srdata as d  # noqa: E402
from driver import session  # noqa: E402
def main():
    a = argparse.ArgumentParser()
    a.add_argument('mode', choices=['hybrid', 'range'])
    a.add_argument('--table', default='t'); a.add_argument('--grp', type=int, default=1)
    a.add_argument('--n', type=int, default=200); a.add_argument('--rows', type=int, default=1000)
    a.add_argument('--limit', type=int, default=10); a.add_argument('--start-idx', type=int, default=10000)
    a.add_argument('--trace', action='store_true')
    o = a.parse_args()
    c, s = session()
    out = {'mode': o.mode}
    q = d.lit(d.query_vec())
    if o.mode == 'hybrid':
        cql = f'SELECT pk, grp FROM ks.{o.table} WHERE grp = {o.grp} ORDER BY v ANN OF {q} LIMIT {o.limit}'
    else:
        toks = sorted(r[0] for r in s.execute('SELECT token(pk) FROM ks.t'))
        lo, hi = toks[o.start_idx - 1], toks[o.start_idx - 1 + o.rows]   # (lo, hi] holds exactly o.rows tokens
        out.update(range_rows=o.rows, lo=lo, hi=hi, tokens=len(toks))
        cql = f'SELECT pk FROM ks.t WHERE token(pk) > {lo} AND token(pk) <= {hi} ORDER BY v ANN OF {q} LIMIT {o.limit}'
    out['cql'] = cql
    ok = True; res = []
    for i in range(1 if o.trace else o.n):
        t0 = int(time.time() * 1000)
        try:
            f = s.execute_async(cql, trace=o.trace); rows = list(f.result())
            r = {'start_ms': t0, 'rows': len(rows)}
            if o.mode == 'hybrid': r['bad'] = sum(1 for x in rows if x.grp != o.grp)
            if o.trace:
                tr = f.get_query_trace(max_wait=30); out['trace_events'] = [e.description for e in tr.events]
        except Exception as e:  # noqa: BLE001
            r = {'start_ms': t0, 'err': f'{type(e).__name__}: {str(e)[:300]}'}; ok = False
        r['end_ms'] = int(time.time() * 1000); res.append(r)
    out['first'] = res[0]; out['last'] = res[-1]; out['n'] = len(res)
    out['errors'] = sum(1 for r in res if 'err' in r); out['short'] = sum(1 for r in res if r.get('rows', 0) < o.limit)
    out['start_ms'] = res[0]['start_ms']; out['end_ms'] = res[-1]['end_ms']
    c.shutdown()
    print(('OK ' if ok else 'ERR ') + json.dumps(out)); sys.exit(0 if ok else 1)
if __name__ == '__main__':
    main()
