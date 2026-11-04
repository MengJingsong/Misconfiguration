#!/usr/bin/env python3
"""EXPECTED lines for the unit tier (instrument checks I1-I3, predictions P1-P4, controls C1-C2). usage: analyze-unit.py test.out"""
import re, sys
cells, other = [], []
for l in open(sys.argv[1]):
    if not l.startswith('STAGE4 '):
        continue
    l = l[7:].strip()
    kv = dict(re.findall(r'(\w[\w-]*)=([^\s]+)', l))
    if l.startswith('cell '):
        cells.append({k: (int(v) if re.fullmatch(r'-?\d+', v) else v) for k, v in kv.items()})
    else:
        other.append((l.split()[0], l, kv))
def ex(desc, ok):
    print(f'EXPECTED: {desc} — {"yes" if ok else "NO"}')
    return ok
bk = [o for o in other if o[0] == 'buckets']
ex('I1 one bucket holding all sstables for n=8 and n=40', [o[1] for o in bk and bk] and all(re.search(r'count=1 sizes=\[(8|40)\]', o[1]) for o in bk) and len(bk) == 2)
va = [o for o in other if o[0] == 'validate']
ex('I2 min 33 with max 32 is rejected and min is unchanged (amendment reason)', len(va) == 2 and all('-> RuntimeException' in o[1] for o in va) and all(o[2]['min-now'] == '4' for o in va))
exp = {(8, 2): 1, (8, 4): 1, (8, 8): 1, (8, 9): 0, (40, 2): 2, (40, 4): 2, (40, 9): 2}
ok = True
for c in cells:
    ok &= (c['est'] == exp[(c['n'], c['min'])])
ex(f'P1 estimate per (n,min) = ceil(n/32) if n>=min else 0, all {len(cells)} cells (forward and reverse sweeps)', ok and len(cells) == 7 + 7)
ex('I3 estimate varies with min (not all equal) at n=8', len({c['est'] for c in cells if c['n'] == 8}) > 1)
ex('P1b manager-level sum and PendingCompactions gauge equal the strategy estimate in every cell', all(c['csm'] == c['est'] and str(c['gauge']) == str(c['est']) for c in cells))
ex('P1c a task is returned exactly when the estimate > 0 or n>=min', all((c['task'] == 'true') == (c['n'] >= c['min']) for c in cells))
for n in (8, 40):
    cs = [c for c in cells if c['n'] == n]
    ex(f'P2 n={n}: disk bytes, live and total identical for every min', len({c['bytes'] for c in cs}) == 1 and len({c['live'] for c in cs}) == 1 and len({c['total'] for c in cs}) == 1)
    hs = [c['heap'] for c in cs]
    ex(f'P3 n={n}: heap max-min < 1 MiB over min values ({(max(hs) - min(hs)) / 1048576:.2f} MiB; sstables constant {len({c["sstables"] for c in cs}) == 1})', max(hs) - min(hs) < 1048576)
bs = {n: next(c['bytes'] for c in cells if c['n'] == n) for n in (8, 40)}
ex(f'P4 flushed data ~ 1 MiB per sstable (n=8: {bs[8]/1048576:.1f} MiB, n=40: {bs[40]/1048576:.1f} MiB)', 7.0e6 < bs[8] < 10e6 and 35e6 < bs[40] < 50e6)
ce = [o for o in other if o[0] == 'control-exec']
ex('C1 positive control: executing the (4,8) compaction takes 8 inputs to 1 sstable and changes the bytes', len(ce) == 1 and ce[0][2]['sstables-before'] == '8' and ce[0][2]['sstables-after'] == '1' and ce[0][2]['bytes-before'] != ce[0][2]['bytes-after'])
cm = [o for o in other if o[0] == 'control-max']
ex('C2 positive control: max_threshold 4 -> 4 inputs, 32 -> 32 inputs (4 again), input bytes follow max', len(cm) == 3 and [o[2]['inputs'] for o in cm] == ['4', '32', '4'] and int(cm[1][2]['input-bytes']) > 7 * int(cm[0][2]['input-bytes']) and cm[0][2]['input-bytes'] == cm[2][2]['input-bytes'])
for o in other:
    if o[0] in ('control-exec', 'control-max'): print('  ' + o[1])
for c in cells: print('  cell', {k: c[k] for k in ('n', 'min', 'est', 'bytes', 'total', 'heap', 'sstables')})
