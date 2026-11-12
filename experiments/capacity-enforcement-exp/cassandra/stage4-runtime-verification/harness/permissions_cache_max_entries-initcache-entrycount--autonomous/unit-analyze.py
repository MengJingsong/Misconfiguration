#!/usr/bin/env python3
"""B2f/B2g of the case file as amended by AM3/AM4 (section D1). Input: probe-lines.txt (PROBE lines from the junit XML).
Prints one EXPECTED line per check (PASS/FAIL) and the matched B2g row."""
import re, sys
path = sys.argv[1]; shake = '--shakedown' in sys.argv
N = 300 if shake else 30000
arms, neg, shrink = {}, None, None
for line in open(path):
    m = re.search(r'PROBE max=(-?\d+) n=(\d+) estimatedSize=(\d+) asMap=(\d+) loads=(\d+) reloads100=(\d+) heapDeltaMB=(-?[\d.]+)', line)
    if m:
        k = int(m.group(1)); arms[k] = dict(n=int(m.group(2)), size=int(m.group(3)), asmap=int(m.group(4)), loads=int(m.group(5)),
                                           reloads=int(m.group(6)), mb=float(m.group(7))); continue
    m = re.search(r'PROBE max=-1 -> (.*?)(<|$)', line)
    if m: neg = m.group(1).strip(); continue
    m = re.search(r'PROBE shrink 10000->100 before=(\d+) after=(\d+)', line)
    if m: shrink = (int(m.group(1)), int(m.group(2)))
for k in sorted(arms):
    a = arms[k]; per = (a['mb'] * 1048576 / a['size'] / 1024) if a['size'] else float('nan')
    print(f"ARM M={k}: size={a['size']} asMap={a['asmap']} loads={a['loads']} reloads100={a['reloads']} heapDeltaMB={a['mb']:.1f} perEntryKB={per:.2f}")
print(f"ARM M=-1: {neg}"); print(f"ARM shrink: {shrink}")
res = {}
def ex(name, ok, detail):
    res[name] = ok; print(f"EXPECTED {'PASS' if ok else 'FAIL'}: {name}: {detail}")
if shake:
    for k in (100, 100000):
        a = arms.get(k); ex(f'shakedown M={k} line parsed, size=min(M,N)', a is not None and a['size'] == min(k, N), a)
    sys.exit(0)
binding = [0, 100, 1000, 10000]
have = all(k in arms for k in binding + [100000])
if not have:
    print("MATCHED: Not confirmed (arms missing)", sorted(arms)); sys.exit(0)
for k in binding:
    s = arms[k]['size']; ex(f'size M={k} in [0.95*min(M,N), M]', 0.95 * min(k, N) <= s <= k, s)
pc = arms[100000]['size']; ex('positive control M=100000 size >= 27000', pc >= 27000, pc)
for k in binding + [100000]:
    ex(f'loads M={k} == N', arms[k]['loads'] == N, arms[k]['loads'])
for k in (1000, 10000, 100000):
    a = arms[k]; per = a['mb'] * 1048576 / a['size'] / 1024 if a['size'] else 0
    ex(f'per-entry KB M={k} in [2.8, 6.3]', 2.8 <= per <= 6.3, round(per, 2))
for k in (0, 100):
    ex(f'heap delta M={k} < 2 MB', arms[k]['mb'] < 2.0, arms[k]['mb'])
ex('reloads100 M=0 == 100 (B2f)', arms[0]['reloads'] == 100, arms[0]['reloads'])
ex('reloads100 M=100000 == 0 (B2f)', arms[100000]['reloads'] == 0, arms[100000]['reloads'])
print(f"INFO reloads100 binding arms (AM3, informational): " + ", ".join(f"M={k}:{arms[k]['reloads']}" for k in (100, 1000, 10000)))
ex('M=-1 throws IllegalArgumentException (informational)', neg is not None and 'IllegalArgumentException' in neg, neg)
ex('shrink before 10000, after <= 100', shrink is not None and shrink[0] == 10000 and shrink[1] <= 100, shrink)
# rows
uncapped = arms[100000]['mb']
row2 = any(arms[k]['size'] > 1.1 * k for k in binding if k > 0) or arms[0]['size'] > 0
row3 = pc < 27000
row4 = any(arms[k]['loads'] < N for k in binding + [100000])
row5 = any(arms[k]['mb'] >= 0.5 * uncapped for k in binding)
row6 = shrink is None or shrink[1] > 100
between = any((k < arms[k]['size'] <= 1.1 * k) or arms[k]['size'] < 0.95 * min(k, N) for k in binding if k > 0)
print(f"ROWS row2={row2} row3={row3} row4={row4} row5={row5} row6={row6} between={between}")
core = [f'size M={k} in [0.95*min(M,N), M]' for k in binding] + ['positive control M=100000 size >= 27000'] + \
       [f'loads M={k} == N' for k in binding + [100000]] + [f'per-entry KB M={k} in [2.8, 6.3]' for k in (1000, 10000, 100000)] + \
       [f'heap delta M={k} < 2 MB' for k in (0, 100)]
if row3: print("MATCHED: B2g row 3 (positive control failed) -> no test of the claim")
elif row4: print("MATCHED: B2g row 4 (loads < N) -> fix workload")
elif row2: print("MATCHED: B2g row 2 (bound does not hold) -> Refuted")
elif row5: print("MATCHED: B2g row 5 (count capped, memory elsewhere) -> Refuted (memory part)")
elif row6: print("MATCHED: B2g row 6 (shrink not enforcing) -> partial refutation")
elif all(res[c] for c in core): print("MATCHED: B2g row 1 (size = min(M,N), heap scales, control holds 30000) -> Confirmed")
else: print("MATCHED: Not confirmed (no matching row); failing checks: " + ", ".join(c for c in core if not res[c]))
