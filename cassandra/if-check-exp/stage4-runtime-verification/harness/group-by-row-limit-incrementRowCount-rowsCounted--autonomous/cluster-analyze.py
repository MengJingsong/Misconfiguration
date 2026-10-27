#!/usr/bin/env python3
"""Cluster tier (B3f/B3g) analysis of group-by-row-limit-incrementRowCount-rowsCounted--autonomous.
usage: cluster-analyze.py <cluster-log-dir> [--shakedown]
The dir holds cells.jsonl, gcrun.jsonl, b78-n{1,2}.trace, gc-n{1,2}.log, heap-n{1,2}.csv, system-n{1,2}.log (the run script copies them there).
Prints each frozen prediction (B3f as amended 2026-10-27, A7 and A9) as an `EXPECTED:` line with PASS/FAIL, then the facts that select a B3g row.
Definitions fixed before any reading (case-file amendments A7, A9; the node-death rule was added after the scale-5 shakedown, an instrument check):
  OOM evidence = a node found dead right after the query (cassandra-env.sh runs the JVM with -XX:OnOutOfMemoryError="kill -9 %p", so an OutOfMemoryError
                 ends the JVM without a log line in system.log; start.out holds the JVM's own message), or an OutOfMemoryError line in system.log in the window;
  peak heap above baseline = max over the query window of the occupancy after a GC pause (gc.log `Pause ... X->Y`) minus the occupancy after the
                             forced full GC (jcmd GC.run) just before the cell, per node; a cell's value is the mean over its repetitions;
  severe GC                = sum of pause durations inside the query window > 50 percent of its wall time; OOM = `OutOfMemoryError` in the client error or
                             in system.log inside the window;
  'near baseline' (fetch 100, guardrail run) = at most 10 MB above baseline (below the low end of the fetch-1000 prediction);
  'within 20 percent' compares the cell means of the post-GC peak occupancy.
Byteman calibration: each sub-read closes K counters; K = number of trace lines of the calibration query (one small sub-read, both nodes)."""
import datetime as dt, json, os, re, statistics as st, sys

D = sys.argv[1]
SHAKE = '--shakedown' in sys.argv
SC = int(os.environ.get('B78_SCALE', 50 if SHAKE else 1))
N_T = 200000 // SC
MB = 1024 * 1024
bad = []


def check(name, ok, detail):
    print(f'EXPECTED: {name}: {"PASS" if ok else "FAIL"} ({detail})')
    if not ok:
        bad.append(name)
    return ok


def rd(name):
    p = os.path.join(D, name)
    return open(p, errors='replace').read().splitlines() if os.path.exists(p) else []


cells = [json.loads(l) for l in rd('cells.jsonl')]
gcruns = [json.loads(l) for l in rd('gcrun.jsonl')]
tr = {n: [] for n in (1, 2)}
for n in (1, 2):
    for l in rd(f'b78-n{n}.trace'):
        m = re.search(r'GB ms=(\d+) rows=(\d+) groups=(\d+) unfinished=(\w+) done=(\w+)', l)
        if m:
            tr[n].append((int(m[1]), int(m[2]), int(m[3]), m[4], m[5]))
heap = {n: [] for n in (1, 2)}
for n in (1, 2):
    for l in rd(f'heap-n{n}.csv'):
        p = l.split(',')
        if len(p) == 3 and p[0].isdigit():
            heap[n].append((int(p[0]), int(p[1])))
GCPAT = re.compile(r'^\[([^\]]+)\]\[[^\]]*\] GC\(\d+\) Pause (\w+).*? (\d+)([MGK])->(\d+)([MGK])\((\d+)([MGK])\) ([\d.]+)ms')
UNIT = {'K': 1 / 1024, 'M': 1, 'G': 1024}
gc = {n: [] for n in (1, 2)}      # (epoch ms, kind, before MB, after MB, pause ms, line)
for n in (1, 2):
    for fn in sorted(x for x in os.listdir(D) if x.startswith(f'gc-n{n}.log')):
      for l in rd(fn):
        m = GCPAT.match(l)
        if m:
            ts = re.sub(r'([+-]\d\d)(\d\d)$', r'\1:\2', m[1])
            t = int(dt.datetime.fromisoformat(ts).timestamp() * 1000)
            gc[n].append((t, m[2], int(m[3]) * UNIT[m[4]], int(m[5]) * UNIT[m[6]], float(m[9]), l))
    gc[n].sort()
oom = {n: [] for n in (1, 2)}     # epoch ms of OutOfMemoryError lines
for n in (1, 2):
    tz = None
    for l in rd(f'gc-n{n}.log')[:3] or rd(f'gc-n{n}.log.00')[:3]:
        mm = re.match(r'^\[[^\]]*([+-]\d\d)(\d\d)\]', l)
        if mm:
            tz = dt.timezone(dt.timedelta(hours=int(mm[1]), minutes=int(mm[2]) * (1 if mm[1][0] == '+' else -1)))
            break
    for l in rd(f'system-n{n}.log'):
        if re.search(r'java\.lang\.OutOfMemoryError|OutOfMemoryError:', l) and '-XX' not in l:
            mm = re.search(r'(\d{4}-\d\d-\d\d)[ T](\d\d:\d\d:\d\d),(\d+)', l)
            if mm:      # system.log timestamps are UTC (observed: 07:33 UTC while the shell is 03:33 EDT)
                oom[n].append(int(dt.datetime.strptime(mm[1] + ' ' + mm[2], '%Y-%m-%d %H:%M:%S').replace(tzinfo=dt.timezone.utc).timestamp() * 1000) + int(mm[3]))
            else:
                oom[n].append(None)


def window(lst, t0, t1, pad=100):
    return [x for x in lst if t0 - pad <= x[0] <= t1 + pad]


cal = [c for c in cells if c.get('label') == 'calibration']
K = sum(len(window(tr[n], cal[0]['t0'], cal[0]['t1'], 500)) for n in (1, 2)) if cal else 0
print(f'INFO: K = {K} trace lines per sub-read (calibration query, both nodes)')
ft = [c for c in cells if c.get('label') == 'first-trigger']
flines = [t for n in (1, 2) for t in window(tr[n], ft[0]['t0'], ft[0]['t1'], 500)] if ft else []
check('instrument: first-trigger query (fetch 1000) leaves trace lines with rows=1000 groups=0 unfinished=true, none above 1000, and the calibration gave K >= 1',
      K >= 1 and any(t[1] == 1000 and t[2] == 0 and t[3] == 'true' for t in flines) and max([t[1] for t in flines] or [0]) <= 1000,
      f'K={K}, {len(flines)} lines, max rows {max([t[1] for t in flines] or [0])}')


def gcrun_for(label, node, before):
    g = [x for x in gcruns if x['label'] == label and x['node'] == node and x['t1'] <= before]
    if not g:
        return None
    g = g[-1]
    f = [x for x in gc[node] if g['t0'] - 1000 <= x[0] <= g['t1'] + 3000 and x[1] == 'Full']
    return f[-1][3] if f else None


def info(c, label):
    t0, t1 = c['t0'], c['t1']
    out = dict(c=c)
    nodes = {}
    for n in (1, 2):
        base = gcrun_for(label, n, t0)
        pw = [x for x in gc[n] if t0 <= x[0] <= t1]
        after = max([x[3] for x in pw] or [None]) if pw else None
        pause = sum(x[4] for x in pw)
        used = [u for ms, u in heap[n] if t0 <= ms <= t1]
        pre = [u for ms, u in heap[n] if t0 - 1000 <= ms <= t0]
        nodes[n] = dict(dused=((max(u for ms, u in heap[n] if t0 - 100 <= ms <= t1 + 100) - min(pre)) / MB if (pre and any(t0 - 100 <= ms <= t1 + 100 for ms, u in heap[n])) else None), base=base, peak_after=after, delta=(after - base) if (after is not None and base is not None) else None,
                        pause_frac=pause / max(1, c['wall_ms']), npauses=len(pw), used_max=(max(used) / MB if used else None),
                        oom=any((o is None) or (t0 <= o <= t1 + 5000) for o in oom[n]))
    out['nodes'] = nodes
    w = [t for n in (1, 2) for t in window(tr[n], t0, t1, 300)]
    out['lines'] = len(w)
    out['sub'] = len(w) / K if K else None
    out['rows'] = sum(t[1] for t in w) / K if K else None
    out['maxrows'] = max([t[1] for t in w] or [0])
    out['mult'] = (len(w) % K == 0) if K else None
    out['served_by'] = {n: len(window(tr[n], t0, t1, 300)) for n in (1, 2)}
    out['severe'] = any(nodes[n]['pause_frac'] > 0.5 for n in (1, 2))
    out['dead'] = c.get('dead_nodes') or []
    out['oom'] = any(nodes[n]['oom'] for n in (1, 2)) or bool(out['dead']) or (c['error'] is not None and 'OutOfMemory' in c['error'])
    return out


def cell(label, fetch, kind):
    cs = [c for c in cells if c.get('label') == kind and c['fetch'] == fetch]
    return [info(c, {'groupby': 'gb', 'control-select': 'ctl', 'small-rows': 'small'}[kind] + f'-{fetch}') for c in cs]


def mean(xs):
    xs = [x for x in xs if x is not None]
    return st.mean(xs) if xs else None


def eff(f):
    return 10000 if f is None else f


def fmt(x):
    return 'NA' if x is None else f'{x:.1f}'


summary = {}
print('\nINFO per cell (mean over repetitions): kind fetch | errors | rows read | sub-reads | max rows/line | node1 delta MB | node1 peak-after MB | node1 base MB | node2 delta MB | pause frac n1 | sampled used max n1 MB | OOM')
for kind in ('groupby', 'control-select', 'small-rows'):
    for f in ([100, 1000, 10000, 100000, 1000000, None] if kind != 'small-rows' else [10000, 100000]):
        r = cell(None, f, kind)
        if not r:
            continue
        s = dict(n=len(r), errs=[x['c']['error'] or '' for x in r], errors=[x['c']['error'] for x in r if x['c']['error']], rows=[x['rows'] for x in r], sub=[x['sub'] for x in r],
                 maxrows=max(x['maxrows'] for x in r), d1=mean([x['nodes'][1]['delta'] for x in r]), p1=mean([x['nodes'][1]['peak_after'] for x in r]),
                 b1=mean([x['nodes'][1]['base'] for x in r]), d2=mean([x['nodes'][2]['delta'] for x in r]), pf1=mean([x['nodes'][1]['pause_frac'] for x in r]),
                 u1=mean([x['nodes'][1]['used_max'] for x in r]), oom=[x['oom'] for x in r], severe=[x['severe'] for x in r], mult=[x['mult'] for x in r],
                 served=[x['served_by'] for x in r], wall=[x['c']['wall_ms'] for x in r], returned=[x['c']['rows_returned'] for x in r])
        summary[(kind, f)] = s
        print(f'INFO {kind} {f} | dead {[x["dead"] for x in r]} | err {len(s["errors"])}/{s["n"]} | rows {[None if x is None else int(x) for x in s["rows"]]} | sub {[None if x is None else int(x) for x in s["sub"]]} | maxrows {s["maxrows"]} | d1 {fmt(s["d1"])} | p1 {fmt(s["p1"])} | b1 {fmt(s["b1"])} | d2 {fmt(s["d2"])} | pf1 {fmt(s["pf1"])} | used1 {fmt(s["u1"])} | oom {s["oom"]} | served {s["served"][0]} | wall {s["wall"]}')
        if s['errors']:
            print('     errors:', [e[:160] for e in s['errors'][:2]])

G = lambda f: summary.get(('groupby', f))
print()
# mechanism (B1 trace; same as the unit tier)
for f in (100, 1000, 10000, None):
    s = G(f)
    if not s:
        continue
    e = eff(f)
    ok = not s['errors'] and all(x == N_T for x in s['rows']) and s['maxrows'] <= e and all(s['mult'])
    exp_sub = N_T // e + 1
    check(f'[B1] fetch {f}: all {N_T} rows read, max rows per sub-read <= {e}, trace lines a multiple of K', ok, f'rows {s["rows"]}, maxrows {s["maxrows"]}, errors {len(s["errors"])}')
    check(f'[B1] fetch {f}: sub-reads == floor({N_T}/{e})+1 = {exp_sub}', all(x == exp_sub for x in s['sub']), s['sub'])
# B3f
for f, lo, hi in ((1000, 10, 30), (10000, 100, 300)):
    s = G(f)
    if s:
        check(f'B3f: fetch {f}: peak heap above baseline in [{lo}, {hi}] MB (node 1)', s['d1'] is not None and lo <= s['d1'] <= hi, f'{fmt(s["d1"])} MB (node 2: {fmt(s["d2"])})')
s = G(100)
if s:
    check('B3f: fetch 100 stays near baseline (<= 10 MB above)', s['d1'] is not None and s['d1'] <= 10, f'{fmt(s["d1"])} MB')
for f in (100000, 1000000):
    s = G(f)
    if s:
        check(f'B3f: fetch {f}: OOM or severe GC in every repetition', all(o or sv or 'OutOfMemory' in e for o, sv, e in zip(s['oom'], s['severe'], s['errs'])),
              f'oom {s["oom"]}, severe {s["severe"]}, errors {[e[:80] for e in s["errors"]]}')
s10, su = G(10000), G(None)
if s10 and su:
    check('B3f: PAGING OFF within 20 percent of fetch 10000 (post-GC peak), no OOM', s10['p1'] and su['p1'] and abs(su['p1'] - s10['p1']) / s10['p1'] <= 0.2 and not any(su['oom']), f'{fmt(su["p1"])} vs {fmt(s10["p1"])} MB; oom {su["oom"]}')
# guardrail
gr = [c for c in cells if c.get('label') == 'guardrail']
if gr:
    ok_pass = gr[0]['fetch'] == 10000 and gr[0]['error'] is None
    fails = [c for c in gr if c['fetch'] == 100000]
    check('B3f: guardrail run: fetch 10000 passes', ok_pass, gr[0]['error'])
    check('B3f: guardrail run: fetch 100000 fails fast with the page-size error', fails and all(c['error'] and 'exceeds fail threshold' in c['error'] for c in fails), [(c['wall_ms'], (c['error'] or '')[:120]) for c in fails])
    gi = [info(c, 'guardrail') for c in fails]
    fl = lambda x: x['nodes'][1]['delta'] if x['nodes'][1]['delta'] is not None else x['nodes'][1]['dused']      # a rejected query is too short for a GC pause: fall back to the growth of sampled used
    check('B3f: guardrail run: heap flat (<= 10 MB above baseline; sampled-used growth when no GC pause fell in the window)', all(fl(x) is not None and fl(x) <= 10 for x in gi) if gi else False, [fmt(fl(x)) for x in gi])
# controls (B3h)
sm = summary.get(('small-rows', 100000))
if sm:
    d_sm = sm['d1'] if sm['d1'] is not None else mean([x['nodes'][1]['dused'] for x in cell(None, 100000, 'small-rows')])
    check('B3h 2: 100-byte rows at fetch 100000: no OOM, no error, <= 100 MB above baseline (sampled-used growth when no GC pause fell in the window)', not sm['errors'] and not any(sm['oom']) and d_sm is not None and d_sm <= 100, f'{fmt(d_sm)} MB, errors {len(sm["errors"])}')
ctl = [summary.get(('control-select', f)) for f in (100, 1000, 10000)]
if all(ctl):
    check('B3h 1: plain SELECT * rises with the fetch size (delta at 100 < 1000 < 10000)', all(c['d1'] is not None for c in ctl) and ctl[0]['d1'] < ctl[1]['d1'] < ctl[2]['d1'], [fmt(c['d1']) for c in ctl])
    for f, c in zip((100, 1000, 10000), ctl):
        print(f'INFO control SELECT * fetch {f}: errors {len(c["errors"])}, rows returned {c["returned"]}')
idle = [c for c in cells if c.get('ds') == 'idle']
if idle:
    for n in (1, 2):
        u = [x for ms, x in heap[n] if idle[0]['t0'] <= ms <= idle[0]['t1']]
        print(f'INFO idle 30 s node {n}: used min/max {min(u) / MB:.0f}/{max(u) / MB:.0f} MB' if u else f'INFO idle node {n}: no samples')
print()
s1, s2, s3 = G(100), G(1000), G(10000)
rises = all(x and x['d1'] is not None for x in (s1, s2, s3)) and s1['d1'] < s2['d1'] < s3['d1']
big_fail = all(G(f) and (any(G(f)['oom']) or any(G(f)['severe'])) for f in (100000, 1000000))
small_ok = all(G(f) and not any(G(f)['oom']) and not G(f)['errors'] for f in (100, 1000, 10000))
um = bool(s10 and su and s10['p1'] and su['p1'] and abs(su['p1'] - s10['p1']) / s10['p1'] <= 0.2)
print(f'B3g facts: peak_rises_with_fetch={rises} large_sizes_oom_or_severe={big_fail} small_sizes_clean={small_ok} unset_matches_10000={um}')
if SHAKE:
    print('SHAKEDOWN: instrument check only, not a reading.')
print('FAILED EXPECTATIONS:', bad if bad else 'none')
