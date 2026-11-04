#!/usr/bin/env python3
"""Independent re-parse of raw-all.csv; expectations re-derived from the pool rules, not from analyze.py. Usage: selfcheck.py <raw-all.csv>"""
import csv, sys
hdr = 'mode c arm rep cap0 target usedAlloc ovfAlloc poolAlloc u0 o0 d0 sc u128 o128 capNew u1 o1 d1 p1 d2 u2 o2 heap exc'.split()
R = []
cache = None
for l in csv.reader(open(sys.argv[1])):
    if not l: continue
    if l[0].startswith('#'):
        cache = l[-1].split('cache=')[-1].split()[0] if 'cache=' in ','.join(l) else cache; continue
    r = dict(zip(hdr, l))
    for k in hdr:
        if k not in ('mode', 'arm', 'exc'): r[k] = int(r[k])
    r['cache'] = cache; R.append(r)
ok = bad = 0
def hold(name, c):
    global ok, bad
    if c: ok += 1
    else: bad += 1; print('FAIL', name)
for r in R:
    if r['mode'] != 'sweep' or r['rep'] == 0: continue
    t = f"C={r['c']} {r['arm']} rep{r['rep']}"
    overflow = r['c'] > 128 * 1024              # pool serves only up to NORMAL_CHUNK_SIZE
    hold(t + ' alloc state', r['usedAlloc'] == r['cap0'] and r['ovfAlloc'] == (r['cap0'] if overflow else 0))
    hold(t + ' released to 0', r['u2'] == 0 and r['o2'] == 0)
    if r['arm'] == 'E':
        hold(t + ' E no-op', r['sc'] == 0 and r['capNew'] == r['cap0'] and r['u1'] == r['u0'] and r['o1'] == r['o0'])
    elif r['arm'] in ('G', 'S'):
        hold(t + ' one buffer in steady state', r['sc'] == 1 and r['u1'] == r['capNew'])
        hold(t + ' two buffers at the put', r['u128'] == r['cap0'] + r['capNew'])
        hold(t + ' overflow gauge equals used when overflow', (r['o1'] == r['u1']) if overflow else (r['o1'] == 0))
    else:
        hold(t + ' M rejected, state unchanged', r['exc'] == 'IllegalArgumentException' and r['u1'] == r['u0'] and r['capNew'] == r['cap0'])
for c, want_pool, want_ovf in (('128', 8388608, 0), ('0', 0, 4096)):
    rs = [r for r in R if r['mode'] == 'control' and r['c'] == 4096 and r['cache'] == c and r['rep'] >= 1]
    hold(f'control cache={c}', len(rs) == 5 and all(r['poolAlloc'] == want_pool and r['ovfAlloc'] == want_ovf for r in rs))
print('SELFCHECK %d hold, %d fail' % (ok, bad))
sys.exit(1 if bad else 0)
