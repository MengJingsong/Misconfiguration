#!/usr/bin/env python3
"""Unit-tier analyzer for B2f/B2g (frozen text, as amended 2026-10-27). Usage: analyze_unit.py <unit.txt>. Prints EXPECTED lines and a B2g row class.
Rules fixed before run 1 (A = 20 partitions x 1000 one-row groups, B = 4 x 100000 rows one group each; G = 20*min(gppl,1000)):
 A_ret   : shape A rows returned = min(G, rowLimit) in every rep
 A_pull  : shape A rows pulled = 20*(gppl+1) for finite gppl and no binding rowLimit; 20000 for NO_LIMIT without a binding rowLimit; in [rowLimit, rowLimit+21] when G > rowLimit
 A_cnt   : shape A, no binding rowLimit: counted = G for finite gppl, 20000 for NO_LIMIT
 B_pull  : shape B rowLimit=NO_LIMIT: rows returned = pulled = 4*B_ROWS for every gppl; counted = 4, cip = 1 after close, cip_before_close = 0
 B_alloc : shape B rowLimit=NO_LIMIT: median alloc across gppl within 10 %
 B_rl    : shape B rowLimit 100 / 10000: pulled in [rowLimit, rowLimit+1] for every gppl
 control : shape B median pulled differs between rowLimit 100, 10000 and NO_LIMIT, rising (100 < 10000 < 4*B_ROWS)"""
import sys, re, statistics as st
L = open(sys.argv[1]).read().splitlines()
kv = dict(l.split('=', 1) for l in L if re.match(r'^[A-Za-z_]+=', l))
NO = 2**31 - 1
runs = {}
for l in L:
    m = re.match(r'^run shape=(\w) gppl=(\S+) rowLimit=(\S+) (.*)$', l)
    if m:
        g = NO if m.group(2) == 'NO_LIMIT' else int(m.group(2)); r = NO if m.group(3) == 'NO_LIMIT' else int(m.group(3))
        runs.setdefault((m.group(1), g, r), []).append({k: int(v) for k, v in (x.split('=') for x in m.group(4).split())})
ok = True
def exp(name, cond, detail):
    global ok; ok &= bool(cond); print('EXPECTED %-8s %s  %s' % (name, 'MATCH' if cond else 'MISMATCH', detail))
print('firsttrigger =', kv.get('firsttrigger'), ' B_ROWS =', kv.get('B_ROWS'), ' reps =', kv.get('reps'), ' maxMemory =', kv.get('maxMemory'))
if not kv.get('firsttrigger', '').startswith('OK') or kv.get('done') != '1':
    print('CLASS  invalid: first trigger failed or run incomplete'); sys.exit(2)
B = int(kv['B_ROWS']); BT = 4 * B; AT = 20 * 1000
gs, rls = [1, 10, NO], [100, 10000, NO]
nm = lambda x: 'NO' if x == NO else x
def G(g): return 20 * min(g, 1000)
fa, fp, fc = [], [], []
for g in gs:
    for r in rls:
        for x in runs[('A', g, r)]:
            if x['returned'] != min(G(g), r): fa.append((g, r, 'ret', x['returned']))
            if G(g) > r:
                if not (r <= x['pulled'] <= r + 21): fp.append((g, r, x['pulled']))
            else:
                want = 20 * (g + 1) if g < NO else AT
                if x['pulled'] != want: fp.append((g, r, x['pulled'], want))
                wc = G(g) if g < NO else AT
                if x['counted'] != wc: fc.append((g, r, x['counted'], wc))
exp('A_ret', not fa, 'mismatches %s' % fa[:4])
exp('A_pull', not fp, 'mismatches %s' % fp[:4] + '; sample gppl=1,10,NO at NO_LIMIT rowLimit: %s' % [sorted({x['pulled'] for x in runs[('A', g, NO)]}) for g in gs])
exp('A_cnt', not fc, 'mismatches %s' % fc[:4])
bp = [(g, x['returned'], x['pulled'], x['counted'], x['cip'], x['cip_before_close']) for g in gs for x in runs[('B', g, NO)]]
exp('B_pull', all(a[1] == BT and a[2] == BT and a[3] == 4 and a[4] == 1 and a[5] == 0 for a in bp), 'shape B rowLimit=NO_LIMIT (returned, pulled, counted, cip, cip_before): %s' % sorted(set(bp))[:5])
al = {g: st.median(x['alloc'] for x in runs[('B', g, NO)]) for g in gs}
exp('B_alloc', max(al.values()) / min(al.values()) <= 1.10, 'median alloc per gppl %s ratio %.3f' % ({nm(g): int(v) for g, v in al.items()}, max(al.values()) / min(al.values())))
brl = [(g, r, x['pulled']) for g in gs for r in (100, 10000) for x in runs[('B', g, r)] if not (r <= x['pulled'] <= r + 1)]
exp('B_rl', not brl, 'mismatches %s' % brl[:4])
med = {r: st.median(x['pulled'] for g in gs for x in runs[('B', g, r)]) for r in rls}
exp('control', med[100] < med[10000] < med[NO] and med[NO] == BT, 'shape B median rows pulled by rowLimit 100, 10000, NO_LIMIT: %s' % med)
print('INFO shape B allocated bytes median, by (gppl,rowLimit):', {(nm(g), nm(r)): int(st.median(x['alloc'] for x in runs[('B', g, r)])) for g in gs for r in rls})
print('CLASS', 'B2g row 1: confirmed (shape A follows gppl, shape B flat across gppl, control moves)' if ok else
      'NOT row 1: see MISMATCH lines (control -> not confirmed; B_pull/B_alloc low at gppl=1 -> refuted; A_* -> trace wrong / limit never reached; other -> no matching row)')
sys.exit(0 if ok else 1)
