#!/usr/bin/env python3
"""B3f/B3g check for the cluster tier (tolerances: case file section D, AM4; heap from the histogram Total, AM3).
Usage: cluster-analyze.py <run-dir containing cluster-K<K>/>"""
import glob, os, re, sys
MB = 1024 * 1024
ROWS = ['java.net.Inet4Address', 'java.net.InetAddress$InetAddressHolder', 'java.util.concurrent.ConcurrentHashMap$Node']
def hist(path):
    d = {}; total = None
    for l in open(path):
        m = re.match(r'\s*\d+:\s+(\d+)\s+(\d+)\s+(\S+)', l)
        if m: d[m.group(3)] = (int(m.group(1)), int(m.group(2)))
        m = re.match(r'Total\s+(\d+)\s+(\d+)', l)
        if m: total = (int(m.group(1)), int(m.group(2)))
    return d, total
def heapinfo(path):
    m = re.search(r'used (\d+)K', open(path).read())
    return int(m.group(1)) * 1024 if m else None
ok = True
def exp(cond, text):
    global ok; ok &= bool(cond); print(("PASS " if cond else "FAIL ") + "EXPECTED: " + text)
def approx(x, X): return abs(x - X) <= 0.05 * abs(X) + 500
run = sys.argv[1]
res = {}
for kd in sorted(glob.glob(os.path.join(run, 'cluster-K*'))):
    K = int(re.search(r'K(\d+)$', kd).group(1))
    H = {}
    for ph in ['base1', 'base2', 'w1', 'w1b', 'flushed', 'w2']:
        p = f'{kd}/h-{K}-{ph}.txt'
        if os.path.exists(p): H[ph] = hist(p)
    if 'base2' not in H or 'w1' not in H: print(f'K={K}: incomplete'); continue
    b = H['base2'][0]
    caf = [c for c in set(H['w1'][0]) | set(b) if c.startswith('com.github.benmanes.caffeine.cache.P')]
    cafc = max(caf, key=lambda c: H['w1'][0].get(c, (0, 0))[0] - b.get(c, (0, 0))[0]) if caf else None
    rows = ROWS + ([cafc] if cafc else [])
    print(f'== K={K} (Caffeine node class: {cafc})')
    D = {}
    for ph in H:
        D[ph] = {r: (H[ph][0].get(r, (0, 0))[0] - b.get(r, (0, 0))[0], H[ph][0].get(r, (0, 0))[1] - b.get(r, (0, 0))[1]) for r in rows}
        D[ph]['Total'] = (H[ph][1][0] - H['base2'][1][0], H[ph][1][1] - H['base2'][1][1])
        print(f'  {ph:8s} ' + '  '.join(f'{r.split(".")[-1]}: {D[ph][r][0]:+d} inst {D[ph][r][1]:+d} B' for r in rows) + f'  Total: {D[ph]["Total"][1]:+d} B ({D[ph]["Total"][1]/MB:+.2f} MB)')
    hb, hw = heapinfo(f'{kd}/heap-{K}-base.txt'), heapinfo(f'{kd}/heap-{K}-w1.txt')
    hi = (hw - hb) if hb is not None and hw is not None else None
    print(f'  heap_info used base={hb} w1={hw} delta={hi} ({(hi or 0)/MB:+.2f} MB)  [secondary, AM3]')
    noise = H['base2'][0].get(ROWS[0], (0, 0))[0] - H['base1'][0].get(ROWS[0], (0, 0))[0] if 'base1' in H else None
    print(f'  baseline noise (Inet4Address base2-base1): {noise}; total bytes base2-base1: {H["base2"][1][1]-H["base1"][1][1] if "base1" in H else None}')
    res[K] = dict(D=D, caf=cafc, hi=hi)
    for l in open(f'{kd}/w1.txt'): print('  W1:', l.strip())
    if os.path.exists(f'{kd}/w2.txt'):
        for l in open(f'{kd}/w2.txt'): print('  W2:', l.strip())
print()
heapband = {100: (None, 5 * MB), 100000: (8 * MB, 20 * MB), 1000000: (50 * MB, 110 * MB)}
w2pred = {100: 100, 100000: 2000, 1000000: 2000}
match = {}
for K, r in sorted(res.items()):
    D = r['D']; I = ROWS[0]
    exp_w1 = min(600000, K)
    dW1 = D['w1'][I][0]; hW1 = D['w1']['Total'][1]
    c1 = approx(dW1, exp_w1); exp(c1, f'K={K}: dInet4Address after W1 ~ {exp_w1} (got {dW1})')
    if K not in heapband: print(f"K={K}: not a B3b value (shakedown), skipped"); continue
    lo, hi = heapband[K]
    c2 = (lo is None or hW1 >= lo) and hW1 <= hi
    exp(c2, f'K={K}: heap delta after W1 (histogram Total) in [{(lo or 0)/MB:.0f}, {hi/MB:.0f}] MB (got {hW1/MB:.2f} MB; heap_info {(r["hi"] or 0)/MB:.2f} MB)')
    for row in ROWS[1:] + ([r['caf']] if r['caf'] else []):
        exp(abs(D['w1'][row][0] - dW1) <= 0.05 * abs(dW1) + 500, f'K={K}: d{row.split(".")[-1]} ~ dInet4Address after W1 ({D["w1"][row][0]} vs {dW1})')
    if 'w1b' in D: exp(abs(D['w1b'][I][0] - dW1) <= 500, f'K={K}: w1b ~ w1 ({D["w1b"][I][0]} vs {dW1})')
    c3 = 'flushed' in D and abs(D['flushed'][I][0]) <= 500
    exp(c3, f'K={K}: dInet4Address after flush ~ 0 (got {D["flushed"][I][0] if "flushed" in D else None})')
    c4 = None
    if 'w2' in D:
        c4 = approx(D['w2'][I][0], w2pred[K]); exp(c4, f'K={K}: dInet4Address after W2 ~ {w2pred[K]} (got {D["w2"][I][0]})')
        for row in ROWS[1:] + ([r['caf']] if r['caf'] else []):
            exp(abs(D['w2'][row][0] - D['w2'][I][0]) <= 0.05 * abs(D['w2'][I][0]) + 500, f'K={K}: d{row.split(".")[-1]} ~ dInet4Address after W2 ({D["w2"][row][0]} vs {D["w2"][I][0]})')
    per = hW1 / dW1 if dW1 > 1000 else None
    if per: print(f'INFO K={K}: bytes per retained entry (histogram Total delta / dInet4Address) = {per:.1f}')
    much = dW1 > 2 * K + 500
    match[K] = dict(row1=c1 and c2 and c3, refuted=much and c3, elsewhere=much and not c3,
                    perentry=(per is not None and per > 500 and not much), pcfail=(K == 1000000 and dW1 < 0.5 * 600000),
                    w2pop=c4, w2zero=('w2' in D and abs(D['w2'][I][0]) <= 500 and K == 1000000))
print()
for K, m in sorted(match.items()):
    rows = [n for n, v in [('B3g row 1 (confirmed)', m['row1']), ('B3g row 2 (cap exceeded: refuted)', m['refuted']),
                           ('B3g row 3 (retention elsewhere)', m['elsewhere']), ('B3g row 4 (per-entry cost off)', m['perentry']),
                           ('B3g row 5 (positive control failed)', m['pcfail']), ('B3g row 6 (W2 populates same cache)', m['w2pop']),
                           ('B3g row 7 (W2 did not reach lookup)', m['w2zero'])] if v]
    print(f'MATCH K={K}: {rows if rows else "no row"}')
allrow1 = all(m['row1'] for m in match.values()) and set(match) == {100, 100000, 1000000}
print('CLUSTER: B3g row 1 holds for every K' if allrow1 else 'CLUSTER: B3g row 1 does NOT hold for every K')
print("ALL EXPECTED HOLD" if ok else "SOME EXPECTED FAIL")
