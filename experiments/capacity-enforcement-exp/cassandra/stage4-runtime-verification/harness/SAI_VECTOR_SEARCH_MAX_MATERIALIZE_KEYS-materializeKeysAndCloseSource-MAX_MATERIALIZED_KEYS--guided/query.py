#!/usr/bin/env python3
"""Cluster-tier client, SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS-materializeKeysAndCloseSource-MAX_MATERIALIZED_KEYS (case 9c "query.py").
usage: query.py --table t|far --m <M> [--q <Q>] [--trace] [--ann-only] [--k 10]
Runs the hybrid query  SELECT pk, i FROM ks.<table> WHERE i <= <M> ORDER BY val ANN OF <q> LIMIT <k>  (or, with --ann-only,
SELECT pk, i FROM ks.<table> ORDER BY val ANN OF <q> LIMIT <k>) at ONE, timeout 200 s; with --q, Q copies at once on one session.
Checks every returned row has i <= M. With --trace (one query) prints the trace events' activity texts.
Prints one line: OK <json> if every query returned k rows with i <= M, else ERR <json>."""
import argparse, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mmkdata as d  # noqa: E402
from driver import session  # noqa: E402


def main():
    a = argparse.ArgumentParser()
    a.add_argument('--table', required=True, choices=['t', 'far'])
    a.add_argument('--m', type=int, default=0)
    a.add_argument('--q', type=int, default=1)
    a.add_argument('--k', type=int, default=10)
    a.add_argument('--trace', action='store_true')
    a.add_argument('--ann-only', action='store_true')
    o = a.parse_args()
    q = d.vec_literal(d.query_vector())
    if o.ann_only:
        cql = f'SELECT pk, i FROM ks.{o.table} ORDER BY val ANN OF {q} LIMIT {o.k}'
    else:
        cql = f'SELECT pk, i FROM ks.{o.table} WHERE i <= {o.m} ORDER BY val ANN OF {q} LIMIT {o.k}'
    c, s = session()
    out = {'cql': cql, 'protocol': c.protocol_version, 'queries': []}
    t0 = time.time()
    futs = [(time.time(), s.execute_async(cql, trace=o.trace)) for _ in range(o.q)]
    ok = True
    for ts, f in futs:
        r = {'start_ms': int(ts * 1000)}
        try:
            rows = list(f.result())
            r['rows'] = len(rows)
            r['bad'] = 0 if o.ann_only else sum(1 for x in rows if x.i > o.m)
            r['max_i'] = max((x.i for x in rows), default=None)
            if o.trace:
                tr = f.get_query_trace(max_wait=30)
                out['trace_events'] = [e.description for e in tr.events]
        except Exception as e:  # noqa: BLE001
            r['err'] = f'{type(e).__name__}: {str(e)[:300]}'
        r['end_ms'] = int(time.time() * 1000)
        ok &= r.get('rows') == o.k and r.get('bad') == 0
        out['queries'].append(r)
    out['secs'] = round(time.time() - t0, 2)
    c.shutdown()
    print(('OK ' if ok else 'ERR ') + json.dumps(out))
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
