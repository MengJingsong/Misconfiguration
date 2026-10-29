#!/usr/bin/env python3
"""analyze-unit.py <logdir> bounds|scale : EXPECTED lines for B2i (frozen numbers) from the STAGE4 lines."""
import re, sys
L, what = sys.argv[1], sys.argv[2]
def parse(f):
    rows = []
    try:
        for l in open(f'{L}/{f}.out'):
            if l.startswith('STAGE4 '):
                rows.append(l[7:].strip())
    except FileNotFoundError:
        pass
    return rows
def kv(line):
    return dict(re.findall(r'(\w+)=(\S+)', line))
def exp(desc, ok, detail=''):
    print(f'EXPECTED: {desc} - {"yes" if ok else "NO"}' + (f' [{detail}]' if detail else ''))
    return ok
MSG = re.compile(r'^rejected InvalidRequestException: Cannot index value of size (\d+) for index \S+ on \S+\(\S+\) \(maximum allowed size=65535\)$')
if what == 'bounds':
    rows = [r for r in parse('bounds') if r.startswith('bound ')]
    res = {}
    for r in rows:
        m = re.match(r'bound path=(\S+) indexed=(\S+) S=(\d+) result=(.*)$', r)
        if m: res[(m.group(1), m.group(2), int(m.group(3)))] = m.group(4)
    ok = True
    for s in (1000, 65533, 65534):
        ok &= exp(f'boundary regular indexed S={s} accepted', res.get(('regular', 'yes', s)) == 'accepted', str(res.get(('regular', 'yes', s))))
    for s in (65535, 65536):
        v = res.get(('regular', 'yes', s), '')
        m = MSG.match(v)
        ok &= exp(f'boundary regular indexed S={s} rejected with "Cannot index value of size {s} ... (maximum allowed size=65535)"', bool(m) and int(m.group(1)) == s, v[:160])
    for s in (65534, 65535, 65536):
        ok &= exp(f'boundary regular NOT indexed S={s} accepted (control)', res.get(('regular', 'no', s)) == 'accepted', str(res.get(('regular', 'no', s))))
    v = res.get(('clustering', 'yes', 65535), ''); m = MSG.match(v)
    ok &= exp('boundary clustering indexed S=65535 rejected with the index message', bool(m) and int(m.group(1)) == 65535, v[:160])
    ok &= exp('boundary clustering indexed S=65534 accepted', res.get(('clustering', 'yes', 65534)) == 'accepted', str(res.get(('clustering', 'yes', 65534))))
    ok &= exp('boundary clustering NOT indexed S=65535 accepted (control)', res.get(('clustering', 'no', 65535)) == 'accepted', str(res.get(('clustering', 'no', 65535))))
    for k, v in sorted(res.items()):
        if k[0] in ('partitionkey-composite',) or (k[0] == 'clustering' and k[2] == 65536):
            print(f'INFO: {k} -> {v[:200]}')
    if not ok: print('EXPECTED: boundary checks - NO')
else:
    d = {}
    for f in ('scale_default', 'scale_pool64'):
        for r in parse(f):
            if r.startswith('scale '):
                x = kv(r); d[(f, x['indexed'], int(x['N']))] = {k: (int(v) if re.fullmatch(r'-?\d+', v) else v) for k, v in x.items()}
    g = lambda f, i, n: d.get((f, i, n))
    MiB = 1 << 20
    for n in (100, 1000, 4000):
        a = g('scale_default', 'yes', n)
        if not a: continue
        NS = a['NxS']
        exp(f'N={n}: no insert rejected (default pool)', a['rejected'] == 0, str(a['rejected']))
        exp(f'N={n}: index disk bytes in [0.9, 2.2] x NxS', 0.9 * NS <= a['idx_disk'] <= 2.2 * NS, f"idx_disk={a['idx_disk']} ratio={a['idx_disk'] / NS:.2f}")
    a1, a2, a3 = g('scale_default', 'yes', 100), g('scale_default', 'yes', 1000), g('scale_default', 'yes', 4000)
    if a1 and a2 and a3:
        r1, r2 = a3['idx_disk'] / a2['idx_disk'], a2['idx_disk'] / a1['idx_disk']
        exp('index disk ratio N=4000/N=1000 in [3.5, 4.5]', 3.5 <= r1 <= 4.5, f'{r1:.2f}')
        exp('index disk ratio N=1000/N=100 in [8, 12]', 8 <= r2 <= 12, f'{r2:.2f}')
        exp('peak index memtable owns at N=4000 (default pool) >= 0.9 x NxS', a3['peak_idx_owns'] >= 0.9 * a3['NxS'], f"{a3['peak_idx_owns']} vs {0.9 * a3['NxS']:.0f}")
        b3 = g('scale_default', 'no', 4000)
        if b3:
            exp('base disk of indexed table within 5% of unindexed table (N=4000)', abs(a3['base_disk'] - b3['base_disk']) <= 0.05 * b3['base_disk'], f"{a3['base_disk']} vs {b3['base_disk']}")
            exp('index adds >= 0.9 x NxS on top of the base (N=4000)', a3['idx_disk'] >= 0.9 * a3['NxS'], f"idx_disk={a3['idx_disk']}")
    c = g('scale_pool64', 'yes', 4000)
    if c and a3:
        exp('control (64 MiB pool): at least one index memtable flush before the explicit flush', c['idx_sstables_before_flush'] >= 1, f"idx sstables before flush={c['idx_sstables_before_flush']}")
        exp('control: peak pool on-heap usage <= 160 MiB', c['peak_pool_onheap'] <= 160 * MiB, f"{c['peak_pool_onheap'] / MiB:.1f} MiB")
        exp('default arm peak pool usage > 2 x control peak', a3['peak_pool_onheap'] > 2 * c['peak_pool_onheap'], f"{a3['peak_pool_onheap'] / MiB:.1f} vs {c['peak_pool_onheap'] / MiB:.1f} MiB")
        exp('control: no insert rejected, index disk bytes in [0.9, 2.2] x NxS', c['rejected'] == 0 and 0.9 * c['NxS'] <= c['idx_disk'] <= 2.2 * c['NxS'], f"rejected={c['rejected']} idx_disk={c['idx_disk']}")
