#!/usr/bin/env python3
"""Readings table and EXPECTED lines for B2f (amended 2026-10-28) from ~/s4-b34/logs/tpb/unit/<label>/*.out.   usage: analyze_unit.py <unit-dir> [out-file]"""
import glob, math, os, re, statistics, sys

d = sys.argv[1]
out = open(sys.argv[2], 'w') if len(sys.argv) > 2 else sys.stdout
fails = 0


def kv(line):
    return dict(re.findall(r'(\w+)=("[^"]*"|\S+)', line))


rows = {}
for f in sorted(glob.glob(d + '/*.out')):
    tag = os.path.basename(f)[:-4]
    r = {}
    for l in open(f, errors='replace'):
        if l.startswith('STAGE4 '):
            r[l.split()[1]] = kv(l)
    rows[tag] = r


def P(s):
    print(s, file=out)


def expect(name, cond, detail=''):
    global fails
    P(f'EXPECTED {name}: {"OK" if cond else "MISMATCH"} {detail}')
    if not cond:
        fails += 1


P('== arm N | TOKENS_PER_BLOCK tokenCount numBlocks serializedSize maxInterior maxLeaf interiorNodes leaves levels retainedHeap (rep 1)')
for tag, r in rows.items():
    if 'tree' in r and tag.endswith('r1'):
        t = r['tree']
        P(f"{tag.split('-')[0]:5} N={t['n']:>7} | {t['TOKENS_PER_BLOCK']} {t['tokenCount']} {t['numBlocks']} {t['serializedSize']} {t['maxInteriorTokens']} {t['maxLeafTokens']} {t['interiorNodes']} {t['leaves']} {t['levels']} {t['retainedHeap']}")
for tag, r in rows.items():
    if 'tree' in r:
        t = r['tree']; n = int(t['n']); tpb = int(t['TOKENS_PER_BLOCK']); arm = tag.split('-')[0]
        expect(f'{tag} constant in the loaded interface is {248 if arm == "stock" else 124}', tpb == (248 if arm == 'stock' else 124), f'TOKENS_PER_BLOCK={tpb}')
        expect(f'{tag} no token dropped or rejected (tokenCount == N)', int(t['tokenCount']) == n)
        expect(f'{tag} interior and leaf nodes never exceed the constant', int(t['maxInteriorTokens']) <= tpb and int(t['maxLeafTokens']) <= tpb, f"{t['maxInteriorTokens']} / {t['maxLeafTokens']} <= {tpb}")
        expect(f'{tag} serializedSize == bytes written', t['serializedSize'] == t['writtenBytes'])
        nb = int(t['numBlocks'])
        if n <= tpb:
            expect(f'{tag} one block when N <= constant', nb == 1)
        else:
            lv = math.ceil(n / tpb)
            expect(f'{tag} blocks ~ N/constant plus interior levels (ceil(N/c) <= blocks <= 1.1 x ceil(N/c) + 3)', lv <= nb <= 1.1 * lv + 3, f'blocks={nb} leaves-needed={lv}')
            expect(f'{tag} serializedSize == numBlocks x 4096', int(t['serializedSize']) == nb * 4096)
for rep in ('1', '2', '3'):
    for n in (61504, 246016):
        s, v = rows[f'stock-tree-{n}-r{rep}']['tree'], rows[f'v124-tree-{n}-r{rep}']['tree']
        expect(f'N={n} r{rep}: the 124 build roughly doubles the block count (1.9 .. 2.1)', 1.9 <= int(v['numBlocks']) / int(s['numBlocks']) <= 2.1, f"{s['numBlocks']} -> {v['numBlocks']}")
    s, v = int(rows[f'stock-tree-246016-r{rep}']['tree']['retainedHeap']), int(rows[f'v124-tree-246016-r{rep}']['tree']['retainedHeap'])
    expect(f'N=246016 r{rep}: retained heap equal across the two builds within 5 % (the TreeMap dominates)', abs(s - v) <= 0.05 * s, f'stock {s} v124 {v} diff {abs(s - v) / s:.3%}')
    a, b = int(rows[f'stock-tree-61504-r{rep}']['tree']['retainedHeap']), int(rows[f'stock-tree-246016-r{rep}']['tree']['retainedHeap'])
    expect(f'r{rep}: retained heap tracks N (246016 / 61504 within 3.4 .. 4.6)', 3.4 <= b / a <= 4.6, f'{b / a:.2f}')
for rep in ('1', '2', '3'):
    for m in (1000, 100000, 1000000):
        s, v = rows[f'stock-ctl-{m}-r{rep}']['control'], rows[f'v124-ctl-{m}-r{rep}']['control']
        expect(f'control M={m} r{rep}: estimatedMemoryUse == M x 236 in both builds (independent of the constant)', int(s['estimatedMemoryUse']) == m * 236 == int(v['estimatedMemoryUse']), f"{s['estimatedMemoryUse']} / {v['estimatedMemoryUse']}")
    s, v = int(rows[f'stock-ctl-1000000-r{rep}']['control']['retainedHeap']), int(rows[f'v124-ctl-1000000-r{rep}']['control']['retainedHeap'])
    expect(f'control M=1e6 r{rep}: retained heap equal across builds within 5 %', abs(s - v) <= 0.05 * s, f'{s} / {v}')
    a, b = int(rows[f'stock-ctl-100000-r{rep}']['control']['retainedHeap']), s
    expect(f'control r{rep}: retained heap grows with M (1e6 / 1e5 within 8 .. 12)', 8 <= b / a <= 12, f'{b / a:.2f}')
up = [l for l in open(os.path.join(d, 'summary.txt')) if 'upstream' in l]
expect('upstream TokenTreeTest passed (stock build)', bool(up) and 'exit=0' in up[0] and 'Failures: 0, Errors: 0' in up[0], up[0].strip() if up else '')
P(f'SUMMARY mismatches={fails} runs={len(rows)}')
