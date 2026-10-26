#!/usr/bin/env python3
"""usage: cluster-analyze.py <cluster-run-dir> <unit summary.txt>. Re-parses the raw per-run files (jfr-sizes-n*.txt, debuglog-n*.txt, repair-output.txt) and prints one
EXPECTED line per B3f prediction (frozen 2026-10-26) plus INFO lines. The unit summary supplies the RF=2 depth/array size for each S (unit tier runs first).
Judging is the AI's job (results file)."""
import os, re, sys
D, U = sys.argv[1], sys.argv[2]
unit = {}
for l in open(U):
    if l.startswith('RESULT') and 'mode=tree' in l:
        r = dict(kv.split('=', 1) for kv in l.split()[1:] if '=' in kv)
        unit[(int(r['S']), int(r['RF']), int(r['D']))] = {k: int(v) for k, v in r.items() if re.fullmatch(r'-?\d+', v)}
def expect(desc, ok): print(f'EXPECTED: {desc} -- {"yes" if ok else "NO"}')
def sizes(label, i):
    p = f'{D}/{label}/jfr-sizes-n{i}.txt'
    out = {}
    if os.path.exists(p):
        for l in open(p):
            if l.startswith('DISTINCT'): _, b, x = l.split(); out[int(b)] = int(x[1:])
    return out
def created(label, i):
    res = []
    for l in open(f'{D}/{label}/debuglog-n{i}.txt'):
        m = re.search(r'Created (\d+) merkle trees with merkle trees size (\d+), (\d+) partitions, (\d+) bytes', l)
        if m: res.append(tuple(int(x) for x in m.groups()))
    return res
def hist_leaves(label, i):
    # sum of the bucket counts printed after 'Partitions per leaf are:' (up to 'Partition sizes are:') = the number of values the first HistogramBuilder received
    tot, on = 0, False
    for l in open(f'{D}/{label}/debuglog-n{i}.txt'):
        if 'Partitions per leaf' in l: on = True; continue
        if 'Partition sizes are' in l: on = False
        m = re.search(r'EstimatedHistogram\.java:\d+ - +\[\d+\.\.\d+\]: (\d+)', l)
        if on and m: tot += int(m.group(1))
    return tot
def ppl(label, i): return sum('Partitions per leaf' in l for l in open(f'{D}/{label}/debuglog-n{i}.txt'))
PLAN = {'r1': (700, 20, 'DEBUG'), 'r2': (700, 20, 'INFO'), 'r3': (64, 20, 'DEBUG'), 'r4': (8, 20, 'DEBUG'), 'r5': (700, 12, 'DEBUG'), 'r1b': (700, 20, 'DEBUG')}
valid = lambda b: any(b == 16 + 80 * 2 ** k for k in range(0, 20))
largest = {}
for lab, (S, Dp, lvl) in PLAN.items():
    if not os.path.isdir(f'{D}/{lab}'): continue
    u = unit.get((S, 2, Dp))
    for i in (1, 2):
        s = sizes(lab, i); c = created(lab, i)
        mx = max(s) if s else 0; largest[(lab, i)] = mx
        print(f'INFO: {lab} node {i}: sizes {sorted(s.items())}; Created lines (trees, leaves, partitions, serialized bytes): {c}; "Partitions per leaf" lines {ppl(lab, i)}')
        if lvl == 'INFO':
            expect(f'{lab} node {i} (INFO): zero HistogramBuilder.add allocation events and zero "Partitions per leaf" lines', not s and ppl(lab, i) == 0)
            continue
        expect(f'{lab} node {i}: every HistogramBuilder.add array size is 16+8*10*2^k', bool(s) and all(valid(b) for b in s))
        if u:
            expect(f'{lab} node {i}: largest array {mx} = unit RF=2 prediction {u["array_bytes"]} (S={S}, D={Dp}, leaves {u["leaves"]})', mx == u['array_bytes'])
            expect(f'{lab} node {i}: Created line reports a tree of {u["leaves"]} leaves {c}', any(x[1] == u['leaves'] for x in c))
            hl = hist_leaves(lab, i)
            print(f'INFO: {lab} node {i}: leaves per the "Partitions per leaf" bucket sum = {hl} (unit tier tree.size() = {u["leaves"]})')
        if lab in ('r1', 'r1b'):
            expect(f'{lab} node {i}: largest array is 10,485,776 B (S=700, D=20)', mx == 10485776)
            expect(f'{lab} node {i}: the array before it, 5,242,896 B, is present and each size appears twice (count and size calls, one tree)', s.get(5242896, 0) >= 1 and s.get(10485776, 0) == 2)
        if lab == 'r5':
            expect(f'{lab} node {i}: D=12 -> largest array 40,976 B', mx == 40976)
            expect(f'{lab} node {i}: D=12 -> a 4096-leaf tree in the Created line (frozen wording; that line is logged before init(), see results) {c}', any(x[1] == 4096 for x in c))
            expect(f'{lab} node {i}: D=12 -> 4096 (+1) values in the "Partitions per leaf" bucket sum: {hist_leaves(lab, i)}', hist_leaves(lab, i) in (4096, 4097))
        if mx and c:
            leaves = hist_leaves(lab, i) or max(x[1] for x in c)
            print(f'INFO: {lab} node {i}: array bytes per leaf (n = {leaves} values from the bucket sum) {mx / leaves:.2f}; serialized bytes of the pre-init tree per leaf (proxy only, not heap) {max(x[3] for x in c) / leaves:.5f}')
            if u:
                heap_leaf = u['tree_bytes_per_leaf']; hashed = heap_leaf + 2 * u['hash_array_bytes']
                print(f'INFO: {lab} node {i}: array/(measureDeep per leaf, unhashed {heap_leaf} B) = {mx / leaves / heap_leaf:.3f}; with leaf+inner hash arrays added ({hashed} B) = {mx / leaves / hashed:.3f}')
                expect(f'{lab} node {i}: array bytes per leaf {mx / leaves:.2f} within 8..16 and below one fifth of heap bytes per leaf ({heap_leaf})', 8 <= mx / leaves <= 16 and mx / leaves < heap_leaf / 5)
for i in (1, 2):
    a = [largest.get((l, i), 0) for l in ('r4', 'r3', 'r1')]
    if all(a): expect(f'node {i}: largest array strictly rises with S: S=8 {a[0]} < S=64 {a[1]} < S=700 {a[2]}', a[0] < a[1] < a[2])
    if largest.get(('r1', i)) and largest.get(('r1b', i)): expect(f'node {i}: r1 and r1b agree {largest[("r1", i)]} {largest[("r1b", i)]}', largest[('r1', i)] == largest[('r1b', i)])
    if largest.get(('r5', i)) and largest.get(('r1', i)): expect(f'node {i}: D=12 largest array {largest[("r5", i)]} is below the D=20 one and independent of S', largest[('r5', i)] < largest[('r1', i)])
