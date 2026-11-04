#!/usr/bin/env python3
"""Cluster tier (B3f/B3g) analysis of default_page_size-cqlgroupbylimits_onclose-rowlimit--autonomous.
usage: cluster-analyze.py <cluster-log-dir> [--shakedown]
The dir holds cells.jsonl, gcrun.jsonl, sstables-*.txt and, per variant (stock, 500, 200000): heap.csv, dps.trace, gc.log*, system.log, start.out.
Prints each frozen prediction (B3f as amended 2026-10-27, C1-C4) as an `EXPECTED:` line with PASS/FAIL, then the facts that select a B3g row.
Definitions fixed in the case file (C2) before any reading:
  peak heap above baseline = max over the query window of the occupancy after a GC pause (gc.log `Pause ... X->Y`) minus the occupancy after the
      forced full GC (jcmd GC.run) just before the query; if no pause fell in the window (a short query), growth of the sampled MBean `used`;
      a cell's value is the mean over its repetitions; a node found dead right after a query (OnOutOfMemoryError kill -9) counts as 'above the heap';
  'several times' = >= 5x; 'well below the heap' = <= 256 MB above baseline; 'visibly more GC activity' = pause time > 20 percent of the wall time.
Choices made here and fixed before any reading: plain-count 'not affected by the constant' = the three variants' means within 50 MB of each other and no
  node death; the stock-build client-fetch arm 'matches' the variant of the same limit = same death outcome, or means within max(30 MB, 50 percent);
  disk 'unchanged' = size of the ks data directory changes by <= 1 MiB over every query.
K = number of trace lines of the calibration query (one small read)."""
import datetime as dt, glob, json, os, re, statistics as st, sys

D = sys.argv[1]
SHAKE = '--shakedown' in sys.argv
SC = int(os.environ.get('DPS_SCALE', 100 if SHAKE else 1))
N = 2000000 // SC
MB = 1024 * 1024
CONST = {'stock': 10000, '500': 500, '200000': 200000}
bad = []


def check(name, ok, detail):
    print(f'EXPECTED: {name}: {"PASS" if ok else "FAIL"} ({detail})')
    if not ok:
        bad.append(name)
    return ok


def rd(path):
    return open(path, errors='replace').read().splitlines() if os.path.exists(path) else []


cells = [json.loads(l) for l in rd(os.path.join(D, 'cells.jsonl'))]
gcruns = [json.loads(l) for l in rd(os.path.join(D, 'gcrun.jsonl'))]
GCPAT = re.compile(r'^\[([^\]]+)\]\[[^\]]*\] GC\(\d+\) Pause (\w+).*? (\d+)([MGK])->(\d+)([MGK])\((\d+)([MGK])\) ([\d.]+)ms')
UNIT = {'K': 1 / 1024, 'M': 1, 'G': 1024}
V = {}
for v in CONST:
    d = os.path.join(D, v)
    tr = []
    for l in rd(os.path.join(d, 'dps.trace')):
        m = re.search(r'GB ms=(\d+) rows=(\d+) groups=(\d+) unfinished=(\w+) done=(\w+)', l)
        if m:
            tr.append((int(m[1]), int(m[2]), int(m[3]), m[4], m[5]))
    heap = []
    for l in rd(os.path.join(d, 'heap.csv')):
        p = l.split(',')
        if len(p) == 3 and p[0].isdigit():
            heap.append((int(p[0]), int(p[1])))
    gc = []
    for fn in sorted(glob.glob(os.path.join(d, 'gc.log*'))):
        for l in rd(fn):
            m = GCPAT.match(l)
            if m:
                ts = re.sub(r'([+-]\d\d)(\d\d)$', r'\1:\2', m[1])
                t = int(dt.datetime.fromisoformat(ts).timestamp() * 1000)
                gc.append((t, m[2], int(m[3]) * UNIT[m[4]], int(m[5]) * UNIT[m[6]], float(m[9]), l))
    gc.sort()
    V[v] = dict(tr=tr, heap=heap, gc=gc)


def window(lst, t0, t1, pad=300):
    return [x for x in lst if t0 - pad <= x[0] <= t1 + pad]


def K_of(v):
    cal = [c for c in cells if c.get('variant') == v and c.get('label') == 'calibration']
    return len(window(V[v]['tr'], cal[0]['t0'], cal[0]['t1'], 500)) if cal else 0


def baseline(v, t0):
    g = [x for x in gcruns if x['variant'] == v and x['t1'] <= t0]
    if not g:
        return None
    g = g[-1]
    f = [x for x in V[v]['gc'] if g['t0'] - 1000 <= x[0] <= g['t1'] + 3000 and x[1] == 'Full']
    return f[-1][3] if f else None


def info(c):
    v, t0, t1 = c['variant'], c['t0'], c['t1']
    gc, heap, tr = V[v]['gc'], V[v]['heap'], V[v]['tr']
    K = K_of(v)
    base = baseline(v, t0)
    pw = [x for x in gc if t0 <= x[0] <= t1]
    after = max([x[3] for x in pw]) if pw else None
    pause = sum(x[4] for x in pw)
    pre = [u for ms, u in heap if t0 - 1000 <= ms <= t0]
    inw = [u for ms, u in heap if t0 - 100 <= ms <= t1 + 100]
    dused = (max(inw) - min(pre)) / MB if (pre and inw) else None
    w = window(tr, t0, t1)
    delta = (after - base) if (after is not None and base is not None) else dused
    return dict(c=c, base=base, peak_after=after, delta=delta, dused=dused, pause_frac=pause / max(1, c['wall_ms']), npauses=len(pw),
                lines=len(w), sub=(len(w) / K if K else None), rows=(sum(t[1] for t in w) / K if K else None), maxrows=max([t[1] for t in w] or [0]),
                mult=(len(w) % K == 0) if K else None, dead=c['dead'], diskdelta=c['data_bytes_after'] - c['data_bytes_before'])


def cellset(v, label, fetch='any'):
    return [info(c) for c in cells if c.get('variant') == v and c.get('label') == label and (fetch == 'any' or c['fetch'] == fetch)]


def mean(xs):
    xs = [x for x in xs if x is not None]
    return st.mean(xs) if xs else None


fmt = lambda x: 'NA' if x is None else f'{x:.1f}'
print('INFO per cell: variant | label fetch | n | dead | err | rows read | sub-reads | max rows/line | delta MB (per rep) | base MB | peak-after MB | pause frac | used growth | disk delta | wall ms')
S = {}
for v in CONST:
    print(f'INFO K[{v}] = {K_of(v)}')
    for label, fetch in (('groupby-unset', None), ('plain-count', None), ('groupby-fetch', 500), ('groupby-fetch', 200000)):
        r = cellset(v, label, fetch)
        if not r:
            continue
        S[(v, label, fetch)] = r
        print(f'INFO {v} | {label} {fetch} | {len(r)} | dead {[x["dead"] for x in r]} | err {[ (x["c"]["error"] or "")[:50] for x in r]} | rows {[None if x["rows"] is None else int(x["rows"]) for x in r]} | sub {[None if x["sub"] is None else int(x["sub"]) for x in r]} | maxrows {max(x["maxrows"] for x in r)} | delta {[fmt(x["delta"]) for x in r]} | base {fmt(mean([x["base"] for x in r]))} | peak {fmt(mean([x["peak_after"] for x in r]))} | pause {[round(x["pause_frac"], 2) for x in r]} | used {fmt(mean([x["dused"] for x in r]))} | disk {[x["diskdelta"] for x in r]} | wall {[x["c"]["wall_ms"] for x in r]}')
print()
# instrument
for v in CONST:
    ft = [c for c in cells if c.get('variant') == v and c.get('label') == 'first-trigger']
    fl = window(V[v]['tr'], ft[0]['t0'], ft[0]['t1'], 500) if ft else []
    check(f'instrument [{v}]: first-trigger fetch-1000 query leaves reads of rows=1000 groups=0 unfinished=true, none above 1000, K >= 1',
          K_of(v) >= 1 and any(t[1] == 1000 and t[2] == 0 and t[3] == 'true' for t in fl) and max([t[1] for t in fl] or [0]) <= 1000, f'K={K_of(v)}, {len(fl)} lines')
dmean = {}
for v in CONST:
    r = S.get((v, 'groupby-unset', None), [])
    if not r:
        continue
    c = CONST[v]
    dmean[v] = None if any(x['dead'] for x in r) else mean([x['delta'] for x in r])
    ok_all = [x for x in r if not x['dead'] and not x['c']['error']]
    if ok_all:
        check(f'[B1] [{v}] limit {c}: every completed query read all {N} rows, max rows per read <= {c}, trace lines a multiple of K',
              all(abs(x['rows'] - N) < 0.5 and x['maxrows'] <= c and x['mult'] for x in ok_all), [(x['rows'], x['maxrows']) for x in ok_all])
        check(f'[B1] [{v}] limit {c}: reads per query == floor({N}/{c})+1 = {N // c + 1} (C2)', all(x['sub'] == N // c + 1 for x in ok_all), [x['sub'] for x in ok_all])
    else:
        print(f'INFO [{v}]: no completed query (node dead in {[x["dead"] for x in r]}); trace lines per query {[x["lines"] for x in r]}, max rows {[x["maxrows"] for x in r]}')
s5, s0, s2 = (S.get((v, 'groupby-unset', None)) for v in ('500', 'stock', '200000'))
if s5 and s0:
    check('B3f: limits 500 and 10000 stay well below the heap (<= 256 MB above baseline, no death)', all(not x['dead'] and x['delta'] is not None and x['delta'] <= 256 for x in s5 + s0), [fmt(x['delta']) for x in s5 + s0])
if s2 and s5:
    d5 = mean([x['delta'] for x in s5])
    check('B3f: limit 200000: node death, or peak above baseline >= 5x the 500 value, or pause time > 20 percent, in every repetition',
          all(x['dead'] or (x['delta'] is not None and d5 and x['delta'] >= 5 * d5) or x['pause_frac'] > 0.2 for x in s2), [(x['dead'], fmt(x['delta']), round(x['pause_frac'], 2)) for x in s2])
    big = float('inf') if any(x['dead'] for x in s2) else mean([x['delta'] for x in s2])
    d0 = mean([x['delta'] for x in s0]) if s0 else None
    check('B3f: peak rises with the constant: 500 < 10000 < 200000 (death = above)', d0 is not None and d5 < d0 < big, f'{fmt(d5)} < {fmt(d0)} < {big}')
    print(f'INFO ratio: 10000/500 = {fmt(d0 / d5) if d0 and d5 else "NA"}; 200000/500 = {"inf (death)" if big == float("inf") else fmt(big / d5)}')
pl = {v: S.get((v, 'plain-count', None)) for v in CONST}
if all(pl.values()):
    ms = [mean([x['delta'] for x in pl[v]]) for v in CONST]
    check('B3f: plain count(payload) (no GROUP BY): no death, the three variants within 50 MB of each other', all(not x['dead'] for v in CONST for x in pl[v]) and None not in ms and max(ms) - min(ms) <= 50, [fmt(m) for m in ms])
    for v in CONST:
        print(f'INFO plain [{v}]: rows read by GroupBy counter lines {[x["lines"] for x in pl[v]]} (0 expected: no GROUP BY counter)')
alld = [x for r in S.values() for x in r]
check('B3f: disk: the ks data directory is unchanged by reads (<= 1 MiB) in every query', all(abs(x['diskdelta']) <= MB for x in alld), [x['diskdelta'] for x in alld if abs(x['diskdelta']) > MB])
# controls: client fetch arms on stock
f5 = S.get(('stock', 'groupby-fetch', 500)); f2 = S.get(('stock', 'groupby-fetch', 200000))
if f5 and s5:
    a, b = mean([x['delta'] for x in f5]), mean([x['delta'] for x in s5])
    check('B3h: client fetch 500 on the stock build reads 500-row reads (floor+1 = %d) and matches the 500 variant (within max(30 MB, 50 percent))' % (N // 500 + 1),
          all(x['sub'] == N // 500 + 1 and x['maxrows'] <= 500 for x in f5) and abs(a - b) <= max(30, 0.5 * b), f'{fmt(a)} vs {fmt(b)}; sub {[x["sub"] for x in f5]}')
if f2 and s2:
    da = any(x['dead'] for x in f2); db = any(x['dead'] for x in s2)
    ok = (da and db) or (not da and not db and abs(mean([x['delta'] for x in f2]) - mean([x['delta'] for x in s2])) <= max(30, 0.5 * mean([x['delta'] for x in s2])))
    check('B3h: client fetch 200000 on the stock build ends like the 200000 variant (same death outcome, or means within max(30 MB, 50 percent))', ok, f'dead {[x["dead"] for x in f2]} vs {[x["dead"] for x in s2]}')
gr = [c for c in cells if c.get('label') == 'guardrail']
if gr:
    check('B3f/B3g: guardrail arm: fetch 500 passes', gr[0]['fetch'] == 500 and gr[0]['error'] is None, gr[0]['error'])
    fails = [c for c in gr if c['fetch'] == 200000]
    check('B3f/B3g: guardrail arm: fetch 200000 rejected in under 5 s with the page-size error', len(fails) == 3 and all(c['error'] and 'exceeds fail threshold' in c['error'] and c['wall_ms'] < 5000 for c in fails), [(c['wall_ms'], (c['error'] or '')[:100]) for c in fails])
print()
rises = (dmean.get('500') is not None and dmean.get('stock') is not None and dmean['500'] < dmean['stock'] and (not s2 or any(x['dead'] for x in s2) or (mean([x['delta'] for x in s2]) > dmean['stock'])))
print(f'B3g facts: peak_rises_with_constant={rises} deaths_at_200000={[x["dead"] for x in s2] if s2 else None} plain_unaffected={all(pl.values()) and max(mean([x["delta"] for x in pl[v]]) for v in CONST) - min(mean([x["delta"] for x in pl[v]]) for v in CONST) <= 50 if all(pl.values()) else None}')
if SHAKE:
    print('SHAKEDOWN: instrument check only, not a reading.')
print('FAILED EXPECTATIONS:', bad if bad else 'none')
