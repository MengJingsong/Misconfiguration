#!/usr/bin/env python3
"""analyze-unit.py <logdir> names|rows : EXPECTED lines for B2i (frozen numbers) from the STAGE4 lines."""
import re, sys, statistics
L, what = sys.argv[1], sys.argv[2]
def rows_of(f):
    try:
        return [l[7:].strip() for l in open(f'{L}/{f}.out') if l.startswith('STAGE4 arm ')]
    except FileNotFoundError:
        return []
def kv(line):
    return dict(re.findall(r'(\w+)=(\S+)', line.split(' msg=')[0]))
def exp(desc, ok, detail=''):
    print(f'EXPECTED: {desc} - {"yes" if ok else "NO"}' + (f' [{detail}]' if detail else ''))
    return ok
def arms(f):
    d = {}
    for r in rows_of(f):
        x = kv(r)
        key = (x['kind'], int(x['L']), int(x['N']))
        msg = r.split('msg=', 1)[1] if 'msg=' in r else ''
        d.setdefault(key, []).append((x, msg, r))
    return d
def spread(vals): return (max(vals) - min(vals)) / (sum(vals) / len(vals))
if what == 'names':
    d = arms('names')
    for L_ in (1, 47, 48):
        v = d.get(('custom', L_, 10000), [])
        exp(f'boundary custom L={L_} accepted (3 of 3)', len(v) == 3 and all(x.get('result') == 'accepted' for x, _, _ in v), f'{len(v)} arms')
    for L_ in (49, 64, 200):
        v = d.get(('custom', L_, 10000), [])
        name = 'c' + 'x' * (L_ - 1)
        want = f"Column '{name}' is longer than the permissible name length of 48 characters"
        ok = len(v) == 3 and all(x.get('create_index') == 'rejected' and want in m for x, m, _ in v)
        exp(f'boundary custom L={L_} rejected with the exact text (3 of 3)', ok, (v[0][1][:200] if v else 'none'))
    for L_ in (1, 47, 48, 49, 64, 200):
        v = d.get(('plain', L_, 10000), [])
        exp(f'boundary plain L={L_} accepted (3 of 3)', len(v) == 3 and all(x.get('result') == 'accepted' for x, _, _ in v), (v[0][1][:200] if v and v[0][1] else f'{len(v)} arms'))
    def med_of(kind, L_, field):
        v = [int(x[field]) for x, _, _ in d.get((kind, L_, 10000), []) if x.get('result') == 'accepted']
        return statistics.median(v) if v else None
    for field, label in (('base_owns', 'memtable owns'), ('dir_bytes', 'flushed directory bytes')):
        pl = {L_: med_of('plain', L_, field) for L_ in (1, 47, 48, 49, 64, 200)}
        if all(pl.values()):
            sp = spread(list(pl.values()))
            exp(f'plain: {label} (max-min)/mean across the six L <= 1%', sp <= 0.01, f'{sp * 100:.3f}% values={pl}')
            exp(f'plain: {label} |L=49 - L=48| <= 1% of L=48 (no step at 48)', abs(pl[49] - pl[48]) <= 0.01 * pl[48], f'{pl[49]} vs {pl[48]}')
        else:
            exp(f'plain: {label} readings present for all six L', False, str(pl))
        cu = {L_: med_of('custom', L_, field) for L_ in (1, 47, 48)}
        if all(cu.values()):
            sp = spread(list(cu.values()))
            exp(f'custom: {label} (max-min)/mean across L=1,47,48 <= 1%', sp <= 0.01, f'{sp * 100:.3f}% values={cu}')
        else:
            exp(f'custom: {label} readings present for L=1,47,48', False, str(cu))
    for (k, L_, n), v in sorted(d.items()):
        ds = [int(x['dir_bytes']) for x, _, _ in v if 'dir_bytes' in x]
        if ds:
            print(f'INFO: {k} dir_bytes reps={ds} heap_delta={[int(x["heap_after_load"]) - int(x["heap_before"]) for x, _, _ in v if "heap_before" in x]}')
else:
    d = arms('rows')
    def g(n, f):
        v = d.get(('plain', 10, n))
        return int(v[0][0][f]) if v and 'result' in v[0][0] else None
    for f, lo, hi, label in (('base_owns', 7, 13, 'memtable owns'), ('dir_bytes', 5, 13, 'flushed directory bytes')):
        a, b, c = g(1000, f), g(10000, f), g(100000, f)
        if a and b and c:
            exp(f'row-count control: {label} ratio 10,000/1,000 in [{lo}, {hi}]', lo <= b / a <= hi, f'{b / a:.2f}')
            exp(f'row-count control: {label} ratio 100,000/10,000 in [{lo}, {hi}]', lo <= c / b <= hi, f'{c / b:.2f}')
        else:
            exp(f'row-count control: {label} readings present', False, f'{a} {b} {c}')
    nn = d.get(('none', 10, 10000))
    if nn and g(10000, 'dir_bytes'):
        u = int(nn[0][0]['dir_bytes'])
        exp('unindexed baseline directory bytes < indexed table directory bytes (N=10,000)', u < g(10000, 'dir_bytes'), f'{u} vs {g(10000, "dir_bytes")}')
    else:
        exp('unindexed baseline reading present', False)
