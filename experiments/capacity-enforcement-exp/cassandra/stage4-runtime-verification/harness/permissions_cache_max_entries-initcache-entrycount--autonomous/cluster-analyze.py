#!/usr/bin/env python3
"""B3f/B3g as amended by AM5 (case file D1). usage: cluster-analyze.py <run>/cluster [--shakedown]
Reads session.txt (EstimatedSize, vtable counts) and <arm>/{base,after,shrink}.hist (live objects after the histogram's full GC)."""
import re, sys, os
R = sys.argv[1]; shake = '--shakedown' in sys.argv; N = 50 if shake else 20000
sess = open(os.path.join(R, 'session.txt')).read().splitlines()
def hist(path):
    d = {'rr': 0, 'B': 0, 'total': None}
    if not os.path.exists(path): return None
    for l in open(path):
        m = re.match(r'\s*\d+:\s+(\d+)\s+(\d+)\s+(\S+)', l)
        if m:
            n, b, c = int(m.group(1)), int(m.group(2)), m.group(3)
            if c == 'org.apache.cassandra.auth.RoleResource': d['rr'] = n
            elif c == '[B': d['B'] = b
        m = re.match(r'Total\s+(\d+)\s+(\d+)', l)
        if m: d['total'] = int(m.group(2))
    return d
arm = None; es = {}; vt = {}
for l in sess:
    m = re.search(r'=== arm (\S+)', l)
    if m: arm = m.group(1); es[arm] = {}; vt[arm] = {}; continue
    m = re.search(r'\] (base|after|shrink) EstimatedSize=.*?(-?\d+)\s*$', l)
    if m and arm: es[arm][m.group(1)] = int(m.group(2))
    m = re.search(r'\] (after|shrink) vtable: (\d+)', l)
    if m and arm: vt[arm][m.group(1)] = int(m.group(2))
arms = [a for a in ('M1000', 'M5000', 'M100000', 'off') if a in es]
H = {a: {p: hist(os.path.join(R, a, p + '.hist')) for p in ('base', 'after', 'shrink')} for a in arms}
D = {}
for a in arms:
    b, af = H[a]['base'], H[a]['after']
    D[a] = dict(drr=af['rr'] - b['rr'], dB=af['B'] - b['B'], dT=af['total'] - b['total'])
    print(f"ARM {a}: ES base={es[a].get('base')} after={es[a].get('after')} vtable={vt[a].get('after')} | RoleResource base={b['rr']} after={af['rr']} d={D[a]['drr']} | "
          f"[B d={D[a]['dB']/1048576:.2f} MB | histTotal d={D[a]['dT']/1048576:.2f} MB | [B/dRR={(D[a]['dB']/D[a]['drr']/1024) if D[a]['drr'] else float('nan'):.2f} KB")
if 'M100000' in arms and H['M100000']['shrink']:
    s, b = H['M100000']['shrink'], H['M100000']['base']
    D['shrink'] = dict(drr=s['rr'] - b['rr'], dB=s['B'] - b['B'], dT=s['total'] - b['total'])
    print(f"SHRINK 100000->1000: ES={es['M100000'].get('shrink')} vtable={vt['M100000'].get('shrink')} RoleResource={s['rr']} d={D['shrink']['drr']} "
          f"[B d={D['shrink']['dB']/1048576:.2f} MB histTotal d={D['shrink']['dT']/1048576:.2f} MB")
res = {}
def ex(name, ok, detail):
    res[name] = ok; print(f"EXPECTED {'PASS' if ok else 'FAIL'}: {name}: {detail}")
if shake:
    ex('shakedown ES after - base == N', es['M100000'].get('after', 0) - es['M100000'].get('base', 0) == N, es['M100000'])
    ex('shakedown dRoleResource ~ N', abs(D['M100000']['drr'] - N) <= 5, D['M100000']['drr'])
    ex('shakedown shrink ES <= 1000', es['M100000'].get('shrink', 10**9) <= 1000, es['M100000'].get('shrink'))
    sys.exit(0)
need = ['M1000', 'M5000', 'M100000', 'off']
if not all(a in arms for a in need): print("MATCHED: Not confirmed (arms missing)", arms); sys.exit(0)
M = {'M1000': 1000, 'M5000': 5000, 'M100000': 100000}
for a in ('M1000', 'M5000'):
    ex(f'ES {a} <= M+10', es[a]['after'] <= M[a] + 10, es[a]['after'])
for a in ('M1000', 'M5000', 'M100000'):
    t = min(M[a], N)
    ex(f'ES {a} within 10% of {t}', abs(es[a]['after'] - t) <= 0.1 * t, es[a]['after'])
    ex(f'dRoleResource {a} within 10% of {t}', abs(D[a]['drr'] - t) <= 0.1 * t, D[a]['drr'])
r1 = D['M5000']['drr'] / D['M1000']['drr'] if D['M1000']['drr'] else float('inf')
r2 = D['M100000']['drr'] / D['M1000']['drr'] if D['M1000']['drr'] else float('inf')
ex('ratio dRR 5000/1000 in [3.5, 6.5]', 3.5 <= r1 <= 6.5, round(r1, 2))
ex('ratio dRR 100000/1000 in [14, 26]', 14 <= r2 <= 26, round(r2, 2))
for a in ('M5000', 'M100000'):
    per = D[a]['dB'] / D[a]['drr'] / 1024 if D[a]['drr'] else 0
    ex(f'd[B/dRR {a} in [2.8, 6.3] KB', 2.8 <= per <= 6.3, round(per, 2))
ex('d[B M1000 <= 8 MB', D['M1000']['dB'] <= 8 * 1048576, round(D['M1000']['dB'] / 1048576, 2))
sh = es['M100000'].get('shrink')
ex('shrink ES <= 1000 (B3f)', sh is not None and sh <= 1000, sh)
ex('shrink dRoleResource back to ~1000 (within 10%)', 'shrink' in D and abs(D['shrink']['drr'] - 1000) <= 100, D.get('shrink', {}).get('drr'))
ex('cache-off ES == 0', es['off']['after'] == 0, es['off']['after'])
ex('cache-off dRoleResource ~0 (<= 500)', D['off']['drr'] <= 500, D['off']['drr'])
ex('cache-off d[B ~0 (<= 8 MB)', D['off']['dB'] <= 8 * 1048576, round(D['off']['dB'] / 1048576, 2))
row2 = D['M1000']['drr'] >= 10000
row3 = any(es[a]['after'] <= M[a] + 10 and (D[a]['drr'] >= 0.5 * D['M100000']['drr'] or D[a]['dB'] >= 0.5 * D['M100000']['dB']) for a in ('M1000', 'M5000'))
row4 = D['M100000']['drr'] < 2000
row5 = sh is None or sh > 1100
row6 = D['off']['drr'] > 500 or D['off']['dB'] > 8 * 1048576
print(f"ROWS row2={row2} row3={row3} row4={row4} row5={row5} row6={row6}")
core = [k for k in res if not k.startswith('cache-off') and not k.startswith('shrink')]
if row4: print("MATCHED: B3g row 4 (positive control failed) -> no conclusion")
elif row6: print("MATCHED: B3g row 6 (cache-off arm grows) -> workload confounded")
elif row2: print("MATCHED: B3g row 2 (cap does not govern retained heap) -> Refuted")
elif row3: print("MATCHED: B3g row 3 (count capped, memory elsewhere) -> Refuted (memory part)")
elif row5: print("MATCHED: B3g row 5 (shrink not enforcing) -> partial")
elif all(res[c] for c in core): print("MATCHED: B3g row 1 (EstimatedSize and dRoleResource ~ min(M,20000), bytes scale) -> Confirmed")
else: print("MATCHED: Not confirmed (no matching row); failing checks: " + ", ".join(c for c in core if not res[c]))
