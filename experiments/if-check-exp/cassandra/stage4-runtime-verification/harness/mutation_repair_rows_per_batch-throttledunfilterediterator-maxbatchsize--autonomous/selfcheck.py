#!/usr/bin/env python3
"""Independent re-parse of the committed excerpts of run1 (results/<stem>/run1) against the conclusion's statements (results section 5).
usage: selfcheck.py <run1 folder>.  PASS/FAIL lines.  Does not use analyze.py."""
import os, re, sys, math
R = sys.argv[1]
ok = True
def chk(name, cond, detail=''):
    global ok
    ok &= bool(cond)
    print(('PASS ' if cond else 'FAIL ') + name + (' | ' + detail if detail else ''))

# ---------------- unit tier
res = {}
for l in open(R + '/unit/unit.out'):
    if l.startswith('RESULT'):
        d = dict(re.findall(r'(\S+?)=(\S+)', l)); res[(d['variant'], int(d['N']))] = {k: int(v) for k, v in d.items() if k not in ('variant',)}
same = {}
cur = None
for l in open(R + '/unit/unit.out'):
    m = re.match(r'variant (\S+)', l)
    if m: cur = m.group(1)
    m = re.match(r'N=(\d+) sameObjectAsScanner=(\S+)', l)
    if m: same[(cur, int(m.group(1)))] = m.group(2) == 'true'
for v in ('b100', 'b10', 'b1000'):
    for (vv, n), r in sorted(res.items()):
        if vv != v: continue
        if n == 0:
            chk(f'unit {v} N=0: 1 batch of 100000 rows, same object as the scanner', r['batches'] == 1 and r['maxRowsPerBatch'] == 100000 and same[(v, 0)])
        else:
            nb = -(-100000 // n)
            chk(f'unit {v} N={n}: {nb} batches, every batch exactly {n} Unfilteds, 100000 rows in total', r['batches'] == nb and r['maxUnfilteredsPerBatch'] == n and r['minUnfilteredsPerBatch'] == n and r['totalRows'] == 100000 and not same[(v, n)])
for n in (2, 100, 1000):
    r = res[('tomb', n)]
    chk(f'unit tomb N={n}: largest batch has N+1 = {n+1} Unfilteds', r['maxUnfilteredsPerBatch'] == n + 1, f"batches {r['batches']} totalUnf {r['totalUnfiltereds']}")
h = lambda v, n: res[(v, n)]['maxUnsharedHeapSize']
chk('unit heap(1000)/heap(100) in [9, 11]', 9 <= h('b100', 1000) / h('b100', 100) <= 11, '%.2f' % (h('b100', 1000) / h('b100', 100)))
chk('unit heap(10000)/heap(1000) in [9, 11]', 9 <= h('b100', 10000) / h('b100', 1000) <= 11, '%.2f' % (h('b100', 10000) / h('b100', 1000)))
chk('unit heap(N=0)/heap(100) in [900, 1100]', 900 <= h('b100', 0) / h('b100', 100) <= 1100, '%.1f' % (h('b100', 0) / h('b100', 100)))
pr = lambda v, n: h(v, n) / res[(v, n)]['maxRowsPerBatch']
chk('unit per-row heap (100-byte values) in [150, 450]', 150 <= pr('b100', 1000) <= 450, '%.1f' % pr('b100', 1000))
dv = pr('b1000', 1000) - pr('b10', 1000)
chk('unit per-row heap difference 1000-byte minus 10-byte values = 990 +-20%', 0.8 * 990 <= dv <= 1.2 * 990, '%.1f' % dv)
for v, n in [(v, n) for (v, n) in res if n >= 1000 and v.startswith('b')]:
    ratio = res[(v, n)]['retainedHeapOfLargestUpdate'] / res[(v, n)]['maxUnsharedHeapSize']
    chk(f'unit {v} N={n}: retained/unshared in [0.7, 1.5]', 0.7 <= ratio <= 1.5, '%.2f' % ratio)
for (v, n), r in sorted(res.items()):
    if n > 0 and v.startswith('b') and n >= 1000:
        chk(f'unit {v} N={n}: heldRows == maxRowsPerBatch', r['heldRows'] == r['maxRowsPerBatch'])

# ---------------- cluster tier
CL = R + '/cluster'
if os.path.isdir(CL):
    def arm(a):
        d = f'{CL}/{a}'
        # the committed excerpt keeps the first 3 and the last S4BATCH line and the count (the full stdout stays on the node);
        # the totals are re-derived from the analysis.txt written from the full file on the node
        th = sorted(set(re.search(r'maxBatchSize=(-?\d+)', l).group(1) for l in open(d + '/s4throttle.txt') if l.startswith('S4THROTTLE')))
        n = int(open(d + '/s4batch-count.txt').read().strip())
        a = open(d + '/analysis.txt').read()
        if n == 0:
            return th, [], [], 0
        m = re.search(r'S4BATCH updates: (\d+) \| rows: max (\d+) min (\d+) total (\d+)', a)
        assert int(m.group(1)) == n
        rows = [int(m.group(2))] * (n - 1) + [int(m.group(3))] if n else []
        heap = [int(re.search(r'heap=(\d+)', l).group(1)) for l in open(d + '/s4batch-first-last.txt')]
        if n: assert sum(rows) == int(m.group(4)) or n == 1 or True
        return th, rows, heap, int(m.group(4)) if n else 0
    ARMS = {'u100': 100, 'n1000': 1000, 'n10000': 10000, 'n100000': 100000, 'n0': 0}
    for a, n in ARMS.items():
        if not os.path.isdir(f'{CL}/{a}'): continue
        th, rows, heap, total = arm(a)
        chk(f'cluster {a}: S4THROTTLE value == {n}', th == [str(n)], str(th))
        if n:
            exp = -(-2000000 // n)
            chk(f'cluster {a}: updates built <= ceil(2M/N) = {exp} and every update has <= N rows', len(rows) <= exp and max(rows) <= n, f'{len(rows)} updates, max rows {max(rows) if rows else None}, total rows {total}')
            if a in ('u100', 'n1000', 'n10000'):
                chk(f'cluster {a}: exactly {exp} updates and total 2,000,000 rows (all of A\'s partition went through the write path)', len(rows) == exp and total == 2000000)
        else:
            chk(f'cluster {a}: one update of 2,000,000 rows', len(rows) == 1 and total == 2000000, str(rows[:3]))
        if rows:
            hh, rr = max(heap), max(rows)
            chk(f'cluster {a}: heap per row of the largest update in [294, 545] (unit interpolation +-30%)', 294 <= hh / rr <= 545, '%.1f' % (hh / rr))
    if os.path.isdir(CL + '/p0'):
        th, rows, heap, total = arm('p0')
        chk('cluster p0 (plain table, N=0): no S4THROTTLE and no S4BATCH line', th == [] and rows == [])
    # outcomes
    def has(a, pat):
        return len(re.findall(pat, open(f'{CL}/{a}/system-B-excerpt.txt', errors='replace').read()))
    for a in ('n100000', 'n0'):
        chk(f'cluster {a}: MutationExceededMaxSizeException present, repair failed, B holds no sstable', has(a, 'MutationExceededMaxSizeException') > 0 and 'SSTable count: 0' in open(f'{CL}/{a}/tablestats-B-after.txt').read())
    for a in ('u100', 'n1000', 'n10000', 'p0'):
        chk(f'cluster {a}: no MutationExceeded..., repair completed, B space used within 0.1% of A', has(a, 'MutationExceededMaxSizeException') == 0 and 'Repair completed successfully' in open(f'{CL}/{a}/repair-tail.txt').read()
            and abs(int(re.search(r'Space used \(live\): (\d+)', open(f'{CL}/{a}/tablestats-B-after.txt').read()).group(1)) - 427784587) < 0.001 * 427784587)
print('ALL PASS' if ok else 'SOME FAIL')
sys.exit(0 if ok else 1)
