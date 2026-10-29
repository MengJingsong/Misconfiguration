#!/usr/bin/env python3
"""Independent self-check of run 1 for one EXCESS_WASTE_* case: python3 selfcheck.py <case 1|2|3|4>
Re-parses the raw logs (it does not import analyze_unit.py / analyze_cluster.py and parses with plain string operations, not their regexes) and
evaluates the S5 rules of the case file's B0 text. Prints PASS/FAIL/NOTE lines and a final tally. Logs: ~/stage4-logs/ew/{unit-c<case>,cluster}/."""
import glob, os, statistics, sys

case = int(sys.argv[1]); L = os.path.expanduser('~/stage4-logs/ew'); out = []


def rep(kind, name, detail=''):
    out.append(kind); print('%-5s %s %s' % (kind, name, detail))


def kvs(line):
    d = {}
    for tok in line.split()[2:]:
        if '=' in tok:
            k, v = tok.split('=', 1); d[k] = v
    return d


def probe(path):
    return [(l.split()[1], kvs(l)) for l in open(path) if l.startswith('PROBE ') and len(l.split()) > 1]


# ---------------- unit tier ----------------
for f in sorted(glob.glob('%s/unit-c%d/*-all.out' % (L, case))):
    name = os.path.basename(f); P = probe(f)
    cfg = [d for k, d in P if k == 'config'][0]; C = int(cfg['C']); OFF = int(cfg['OFFSET'])
    bad = [d for k, d in P if k == 'direct' and ((d['ret'] == 'true') != (int(d['w']) >= C - 1023 and int(d['w']) > 0 and int(d['units']) >= OFF or int(d['w']) >= C))]
    rep('PASS' if not bad else 'FAIL', '%s direct: ret true exactly when ceil(w/1024) >= OFFSET or w >= C (%d rows)' % (name, sum(1 for k, _ in P if k == 'direct')), str(bad[:2]))
    lat = [d for k, d in P if k == 'latch']
    rep('PASS' if lat and lat[0]['afterSentinelTenCallsOfOneByte'] == 'true' else 'FAIL', '%s latch' % name)
    for k, d in P:
        if k == 'burst' and d['gapMs'] == '0':
            u = int(d['units']); calls = int(d['calls']); credit = int(d['elapsedNs']) >> 17
            lo = (OFF + credit - 3 * u) // u; hi = (OFF + credit + 3 * u) // u + 2
            rep('PASS' if lo <= calls <= hi and d['locked'] == 'true' else 'FAIL', '%s burst w=%s calls=%d in [%d,%d]' % (name, d['w'], calls, lo, hi))
    for k, d in P:
        if k == 'control':
            lim = int(d['limit']); own = int(d['ownsOffAtFirstClean' if d['type'] == 'offheap_objects' else 'ownsOnAtFirstClean'])
            rep('PASS' if lim * 0.5 <= own <= lim * 0.55 else 'FAIL', '%s control %s %d MiB first clean at %.3f x limit' % (name, d['type'], lim >> 20, own / lim))
    for lab in sorted({d['label'] for k, d in P if k == 'cont'}):
        s = [d for k, d in P if k == 'cont' and d['label'] == lab and d['run'] == 'single'][0]
        key = 'ownsOff' if s['type'] == 'offheap_objects' else 'ownsOn'
        r = [int(d[key]) for k, d in P if k == 'cont' and d['label'] == lab and d['run'] != 'single']
        rep('PASS' if min(r) > int(s[key]) else 'FAIL', '%s cont %s: contended %s min %d > single %s (S2)' % (name, lab, key, min(r), s[key]), 'spread %d..%d' % (min(r), max(r)))
    for k, d in P:
        if k == 'sentinel':
            ok = d['sentinelOwnsOn'] == d['normalOwnsOn'] and d['sentinelOwnsOff'] == d['normalOwnsOff']
            rep('PASS' if ok else 'FAIL', '%s sentinel vs normal owns equal (%s)' % (name, d['type']))
        if k == 'memo':
            rep('PASS' if abs(int(d['deltaBytes'])) < 1_000_000 else 'FAIL', '%s memo delta %s B' % (name, d['deltaBytes']))
# the unit builds against each other (S5: same within the larger repeat spread)
bymap = {}
for f in glob.glob('%s/unit-c%d/*-all.out' % (L, case)):
    P = probe(f); b = os.path.basename(f).replace('-all.out', '')
    for lab in {d['label'] for k, d in P if k == 'cont'}:
        key = 'ownsOff' if [d for k, d in P if k == 'cont' and d['label'] == lab][0]['type'] == 'offheap_objects' else 'ownsOn'
        bymap[(lab, b)] = [int(d[key]) for k, d in P if k == 'cont' and d['label'] == lab and d['run'] != 'single']
for lab in sorted({l for l, _ in bymap}):
    bs = {b: v for (l, b), v in bymap.items() if l == lab}
    if len(bs) > 1:
        meds = {b: statistics.median(v) for b, v in bs.items()}; spread = max(max(v) - min(v) for v in bs.values())
        diff = max(meds.values()) - min(meds.values())
        rep('PASS' if diff <= spread else 'NOTE', 'unit builds %s: contended-owns medians %s differ by %d vs larger repeat spread %d' % (lab, {b: int(m) for b, m in meds.items()}, diff, spread))

# ---------------- cluster tier ----------------
UN = {'B': 1, 'KiB': 1024, 'MiB': 1048576, 'GiB': 1 << 30}


def tosz(x):
    for u in ('KiB', 'MiB', 'GiB', 'B'):
        if x.endswith(u): return float(x[:-len(u)]) * UN[u]
    raise ValueError(x)


def cellinfo(tag):
    d = '%s/cluster/%s' % (L, tag)
    if not os.path.exists(d + '/debug.log'): return None
    ops, enq = [], []
    for l in open(d + '/debug.log', errors='replace'):
        if 'Writing Memtable-t@' in l:
            seg = l.split('serialized bytes, ')[1]; ops.append((int(seg.split(' ops')[0]), tosz(seg.split(', ')[1].split(' ')[0])))
        elif 'Enqueuing flush of ks.t,' in l:
            enq.append(tosz(l.split('Usage: ')[1].split(' ')[0]))
    ops = ops[1:-1]; enq = enq[1:] if len(enq) > 1 else enq
    first = open(d + '/s4waste.csv').readline().strip()
    last = [x for x in open(d + '/s4waste.csv').read().split('\n') if x[:1].isdigit()][-1].split(',')
    ld = open(d + '/loadgen.out').read() if os.path.exists(d + '/loadgen.out') else ''
    errs = int(ld.split('errors=')[1].split()[0]) if 'errors=' in ld else -1; req = int(ld.split('requests=')[1].split()[0]) if 'requests=' in ld else 0
    return dict(C=int(first.split('C=')[1].split()[0]) if 'C=' in first else None, nops=len(ops), ops=statistics.median([o for o, _ in ops]) if ops else 0,
                onheap=statistics.median([s for _, s in ops]) if ops else 0, enq=statistics.median(enq) if enq else 0, attempts=int(last[1]), fails=int(last[2]),
                lfails=int(last[5]), flips=int(last[9]), errs=errs, req=req)


cells = {}
for p in glob.glob('%s/cluster/c%d-*' % (L, case)):
    t = os.path.basename(p); ci = cellinfo(t)
    if ci: cells[t] = ci
want = {1: 11, 2: 6, 3: 14, 4: 8}[case]
rep('PASS' if len(cells) == want else 'FAIL', 'cluster cells with logs: %d of %d' % (len(cells), want))
for t, c in sorted(cells.items()):
    ok = c['errs'] >= 0 and c['errs'] <= 0.01 * max(1, c['req']) and c['nops'] >= 4 and c['attempts'] > 0
    rep('PASS' if ok else 'FAIL', 'valid cell %s (S5)' % t, 'errors %d/%d, flushes used %d, attempts %d, C=%s, flips %d, fails %d' % (c['errs'], c['req'], c['nops'], c['attempts'], c['C'], c['flips'], c['fails']))


def med(tags, k):
    v = [cells[t][k] for t in tags if t in cells and cells[t]['nops'] >= 4]
    return statistics.median(v) if v else None


def ratio_rule(title, groups, keys=('ops', 'onheap', 'enq')):
    for k in keys:
        m = {g: med(ts, k) for g, ts in groups.items()}
        if None in m.values() or min(m.values()) <= 0:
            rep('NOTE', '%s %s: missing data %s' % (title, k, m)); continue
        r = max(m.values()) / min(m.values())
        order = sorted(m, key=lambda g: m[g])
        rep('NOTE', '%s %s medians %s ratio %.2f -> %s' % (title, k, {g: round(v, 1) for g, v in m.items()}, r, 'FLAT (<=1.3)' if r <= 1.3 else 'ratio >1.3, order ' + '<'.join(order)))


if case == 1:
    G = {v: ['c1-%s-r%d' % (v, k) for k in (1, 2, 3)] for v in ('v1', 'v10m', 'v2p40')}
    ratio_rule('case1 constants', G)
    for v, ts in G.items():
        rep('NOTE', 'regime %s: flips per cell %s ; locked-branch fails %s' % (v, [cells[t]['flips'] for t in ts if t in cells], [cells[t]['lfails'] for t in ts if t in cells]))
    ratio_rule('case1 pool control (128 / 512 / 1024)', {'128': ['c1-ctl128'], '512': ['c1-v10m-r1', 'c1-v10m-r2', 'c1-v10m-r3'], '1024': ['c1-ctl1024']}, ('enq', 'onheap'))
if case == 2:
    ratio_rule('case2 hot constants 1MiB/10MiB/100MiB', {'v1m': ['c2-hot-v1m'], 'v10m': ['c2-hot'], 'v100m': ['c2-hot-v100m']})
    ratio_rule('case2 hot pool', {'128': ['c2-hot128'], '512': ['c2-hot']}, ('enq', 'onheap'))
    ratio_rule('case2 cold pool', {'128': ['c2-cold128'], '512': ['c2-cold']}, ('enq', 'onheap'))
    for t in ('c2-hot', 'c2-cold', 'c2-hot128', 'c2-cold128', 'c2-hot-v1m', 'c2-hot-v100m'):
        if t in cells: rep('NOTE', 'regime %s: flips %d fails %d attempts %d' % (t, cells[t]['flips'], cells[t]['fails'], cells[t]['attempts']))
if case == 3:
    for w in ('WD', 'WE'):
        ratio_rule('case3 %s constants' % w, {v: ['c3-%s-%s-r%d' % (w, v, k) for k in (1, 2)] for v in ('v1m', 'v10m', 'v1g')})
        for v in ('v1m', 'v10m', 'v1g'):
            ts = ['c3-%s-%s-r%d' % (w, v, k) for k in (1, 2)]
            rep('NOTE', 'regime %s %s: flips %s fails %s' % (w, v, [cells[t]['flips'] for t in ts if t in cells], [cells[t]['fails'] for t in ts if t in cells]))
    ratio_rule('case3 pool 128 vs 512 (WD v10m)', {'128': ['c3-ctl128'], '512': ['c3-WD-v10m-r1', 'c3-WD-v10m-r2']}, ('enq', 'onheap'))
    if 'c3-single' in cells: rep('PASS' if cells['c3-single']['fails'] == 0 and cells['c3-single']['flips'] == 0 else 'FAIL', 'single-thread cell: fails %d flips %d' % (cells['c3-single']['fails'], cells['c3-single']['flips']))
if case == 4:
    for w in ('WF', 'WG'):
        ratio_rule('case4 %s constants' % w, {v: ['c4-%s-%s' % (w, v)] for v in ('v10m', 'v1g', 'v1024')})
        for v in ('v10m', 'v1g', 'v1024'):
            t = 'c4-%s-%s' % (w, v)
            if t in cells: rep('NOTE', 'regime %s: flips %d fails %d attempts %d' % (t, cells[t]['flips'], cells[t]['fails'], cells[t]['attempts']))
    ratio_rule('case4 pool 128/512/1024 (WF v10m)', {'128': ['c4-ctl128'], '512': ['c4-WF-v10m'], '1024': ['c4-ctl1024']}, ('enq', 'onheap'))
print('\nTALLY: %d PASS, %d FAIL, %d NOTE' % (out.count('PASS'), out.count('FAIL'), out.count('NOTE')))
