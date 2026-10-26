#!/usr/bin/env python3
"""usage: unit-analyze.py <summary.txt>. Re-parses the RESULT lines of unit-run.sh and prints one EXPECTED line per B2f prediction (frozen 2026-10-26):
yes / NO for each; it judges nothing else. The AI judges the outcome against B2g in the results file."""
import re, sys, math
rows = []
for l in open(sys.argv[1]):
    if l.startswith('RESULT'):
        rows.append(dict(kv.split('=', 1) for kv in l.split()[1:] if '=' in kv))
for r in rows:
    for k in list(r):
        if re.fullmatch(r'-?\d+', r[k]): r[k] = int(r[k])
def expect(desc, ok): print(f'EXPECTED: {desc} -- {"yes" if ok else "NO"}')
cap = lambda n: 10 * 2 ** max(0, math.ceil(math.log2(max(n, 1) / 10)))
direct = [r for r in rows if r['mode'] == 'direct']
tree = [r for r in rows if r['mode'] == 'tree']
for r in direct:
    n = r['n']; expect(f"direct n={n}: values.length {r['values_length']} = 10*2^ceil(log2(n/10)) = {cap(n)}", r['values_length'] == cap(n))
want = {10: 10, 11: 20, 8192: 10240, 131072: 163840, 1048576: 1310720, 1048577: 1310720}
for r in direct:
    if r['n'] in want: expect(f"direct n={r['n']} equals the listed B2f value {want[r['n']]}", r['values_length'] == want[r['n']])
def key(r): return (r['S'], r['RF'], r['D'])
for r in tree:
    n = r['leaves']
    expect(f"tree S={r['S']} RF={r['RF']} D={r['D']}: values.length {r['values_length']} follows the formula for n=leaves={n} ({cap(n)})", r['values_length'] == cap(n))
    if r['D'] == 10: expect(f"tree S={r['S']} D=10: leaves {n} <= 1024 and values.length {r['values_length']} <= 1280", n <= 1024 and r['values_length'] <= 1280)
    if r['D'] == 20 and r['RF'] == 3 and r['S'] in (512, 2047): expect(f"tree S={r['S']} (RF 3, D 20): depth 20, leaves 2^20, values.length 1310720", r['depth'] == 20 and n == 2**20 and r['values_length'] == 1310720)
    if r['RF'] == 1 and r['S'] == 2047 and r['D'] == 20: expect("tree S=2047 RF=1 D=20: depth 20, values.length 1310720", r['depth'] == 20 and r['values_length'] == 1310720)
    if r['S'] >= 2048 and r['S'] in (2048, 4096): expect(f"tree S={r['S']} RF={r['RF']} D={r['D']}: int budget wraps -> depth 1, leaves 2, values.length 10", r['depth'] == 1 and n == 2 and r['values_length'] == 10)
    if r['depth'] == 20 and r['D'] == 20:
        expect(f"tree S={r['S']} RF={r['RF']} (depth 20): array bytes/leaf {r['array_bytes']/n:.2f} within 8..16", 8 <= r['array_bytes'] / n <= 16)
        expect(f"tree S={r['S']} RF={r['RF']} (depth 20): hist thread-allocated {r['hist_alloc_median']} in (10.5 MB, ~120 MB)", 10_485_776 < r['hist_alloc_median'] < 120_000_000)
    expect(f"tree S={r['S']} RF={r['RF']} D={r['D']}: measureDeep(tree)/leaf = {r['tree_bytes_per_leaf']} B > array bytes/leaf {r['array_bytes']/n:.1f}", r['tree_bytes_per_leaf'] > r['array_bytes'] / n)
# independence of S at equal n, and monotone depth with S below the wrap
byn = {}
for r in tree + direct:
    n = r.get('leaves', r.get('n')); byn.setdefault(n, set()).add(r['values_length'])
expect('values.length is a function of n alone (one value per n across all rows)', all(len(v) == 1 for v in byn.values()))
t3 = sorted([r for r in tree if r['RF'] == 3 and r['D'] == 20 and r['S'] <= 2047], key=lambda r: r['S'])
expect('RF=3 D=20, S=1..2047: depth non-decreasing with S: ' + str([(r['S'], r['depth']) for r in t3]), all(a['depth'] <= b['depth'] for a, b in zip(t3, t3[1:])))
expect('positive control: measureDeep(tree) non-decreasing with S below the cap and 2^depth proportional: ' + str([(r['S'], r['tree_measureDeep']) for r in t3]),
       all(a['tree_measureDeep'] <= b['tree_measureDeep'] for a, b in zip(t3, t3[1:])))
if any(r['depth'] == 20 for r in t3):
    big = [r for r in t3 if r['depth'] == 20]; expect('flat above the cap: values.length identical for all S with depth 20: ' + str([(r['S'], r['values_length']) for r in big]), len({r['values_length'] for r in big}) == 1)
for r in tree:
    if r['D'] == 20 and r['RF'] == 3 and r['depth'] == 20:
        hashed = r['tree_bytes_per_leaf'] + 2 * r['hash_array_bytes']
        print(f"INFO: S={r['S']} array/tree ratio: unhashed {r['array_bytes']/r['tree_measureDeep']:.3f}, with leaf+inner hash arrays added {r['array_bytes']/(n*hashed):.3f}")
