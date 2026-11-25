#!/usr/bin/env python3
"""o116 analysis: evaluates the S4-A2 (unit) and S4-A3 (client-process) criteria from the raw files.
usage: analyze.py <dir with U*.probe.txt / S*.probe.txt> <dir with data-*.txt peak-*.txt *.out>"""
import sys, re, os, glob
MIB = 1 << 20
U, P = sys.argv[1], sys.argv[2]
res = []
def chk(name, ok, note=''):
    res.append((name, ok)); print(('PASS ' if ok else 'FAIL ') + name + ('  [' + note + ']' if note else ''))
def gen(n):
    g = n.split('-')[1]
    return (0, int(g), '') if g.isdigit() else (1, 0, g)
def probe(name):
    f = os.path.join(U, name + '.probe.txt')
    if not os.path.exists(f): return None
    d = {'sync': [], 'heap': [], 'quarter': [], 'sorted': [], 'data': []}
    for l in open(f):
        l = l.strip()
        m = re.match(r'PROBE writer=(\S+) limitBytes=(-?\d+)', l)
        if m: d['writer'] = m.group(1); d['limit'] = int(m.group(2))
        m = re.match(r'PROBE sync=(\d+) preSyncSample=(\d+) limit=(-?\d+) row=(\d+)', l)
        if m: d['sync'].append((int(m.group(1)), int(m.group(2)), int(m.group(4))))
        m = re.match(r'PROBE heapSample=(\d+) currentSize=(\d+) retained=(-?\d+)', l)
        if m: d['heap'].append((int(m.group(1)), int(m.group(2)), int(m.group(3))))
        m = re.match(r'PROBE (quarterHeap|sortedHeap) row=(\d+) currentSize=(-?\d+) retained=(-?\d+)', l)
        if m: d['quarter' if m.group(1) == 'quarterHeap' else 'sorted'].append((int(m.group(2)), int(m.group(4))))
        m = re.match(r'PROBE syncs=(\d+) maxCurrentSize=(\d+) maxIncrement=(\d+) endCurrentSize=(\d+)', l)
        if m: d['syncs'], d['maxcs'], d['maxinc'], d['endcs'] = map(int, m.groups())
        m = re.match(r'PROBE data (\S+) (\d+)', l)
        if m: d['data'].append((m.group(1), int(m.group(2))))
        m = re.match(r'PROBE dataFiles=(\d+) totalDataBytes=(\d+)', l)
        if m: d['files'], d['total'] = int(m.group(1)), int(m.group(2))
    d['data'].sort(key=lambda x: gen(x[0]))
    d['heap'].sort(); d['quarter'].sort(); d['sorted'].sort()
    return d

print('== unit tier ==')
ranges = {'U1': (1, 140, 150), 'U4': (4, 34, 38), 'U16': (16, 8, 10), 'U64': (64, 2, 2)}
r = {}
for n, (k, lo, hi) in ranges.items():
    d = probe(n); L = k * MIB
    if d is None or 'syncs' not in d: chk(n + ' present', False); continue
    ns = len(d['sync'])
    print(f"{n}: limit={d.get('limit')} syncLines={ns} syncs={d['syncs']} files={d.get('files')} maxCS={d['maxcs']} maxInc={d['maxinc']} total={d.get('total')} "
          f"preSync[min,max]=[{min(s[1] for s in d['sync']) if ns else None},{max(s[1] for s in d['sync']) if ns else None}] heap={d['heap']} quarter={d['quarter']}")
    sizes = [s for _, s in d['data']]
    nonlast = sizes[:-1]
    print(f"   non-last Data.db min/max = {min(nonlast) if nonlast else None}/{max(nonlast) if nonlast else None} ({(min(nonlast)/L if nonlast else 0):.4f}L-{(max(nonlast)/L if nonlast else 0):.4f}L); last={sizes[-1] if sizes else None}")
    chk(n + ' limitBytes = L', d.get('limit') == L, str(d.get('limit')))
    chk(n + f' syncs in [{lo},{hi}]', lo <= ns <= hi and ns == d['syncs'], str(ns))
    chk(n + ' files = syncs+1', d.get('files') == ns + 1, f"{d.get('files')}")
    chk(n + ' every preSyncSample <= L < preSyncSample+maxInc', ns > 0 and all(p <= L < p + d['maxinc'] for _, p, _ in d['sync']))
    chk(n + ' maxCurrentSize <= L', d['maxcs'] <= L, str(d['maxcs']))
    chk(n + ' non-last Data.db in [0.90L,1.05L]', bool(nonlast) and all(0.90 * L <= s <= 1.05 * L for s in nonlast))
    if n != 'U1':
        if d['heap']:
            r[n] = d['heap'][0][2] / L
            for (i, cs, ret) in d['heap'][1:]:
                chk(f'{n} heap sample {i} <= 2rL+8MiB', ret <= 2 * r[n] * L + 8 * MIB, f'{ret/MIB:.1f} MiB vs {(2*r[n]*L+8*MIB)/MIB:.1f}')
            print(f"   r({n}) = {r[n]:.3f}  retained1 = {d['heap'][0][2]/MIB:.1f} MiB")
        else: chk(n + ' heap sample present', False)
if 'U4' in r:
    chk('r(U4) in [1.1,2.0]', 1.1 <= r['U4'] <= 2.0, f"{r['U4']:.3f}")
    for n in ('U16', 'U64'):
        if n in r: chk(f'r({n}) within +-20% of r(U4)', abs(r[n] / r['U4'] - 1) <= 0.20, f"{r[n]:.3f}/{r['U4']:.3f}={r[n]/r['U4']:.3f}")
    u4, u64 = probe('U4'), probe('U64')
    if u4 and u64 and u4['heap'] and u64['heap']:
        dlt = u64['heap'][0][2] - u4['heap'][0][2]
        chk('retained(U64)-retained(U4) >= 8 MiB', dlt >= 8 * MIB, f'{dlt/MIB:.1f} MiB')
# controls
ss = {}
for n in ('S16', 'S64'):
    d = probe(n)
    if d is None: chk(n + ' present', False); continue
    vals = [x[1] for x in d['sorted']]; ss[n] = sum(vals) / len(vals) if vals else None
    sizes = [s for _, s in d['data']]
    print(f"{n}: writer={d.get('writer')} files={d.get('files')} sortedHeap={[round(v/MIB,1) for v in vals]} MiB non-last sizes={sorted(set(sizes[:-1]))[:3]}..{sorted(set(sizes[:-1]))[-3:] if sizes[:-1] else ''} total={d.get('total')}")
    chk(n + ' every sortedHeap < 16 MiB', bool(vals) and all(v < 16 * MIB for v in vals))
if len([v for v in ss.values() if v is not None]) == 2: chk('S16/S64 mean sortedHeap within 8 MiB', abs(ss['S16'] - ss['S64']) <= 8 * MIB, f"{ss['S16']/MIB:.1f} vs {ss['S64']/MIB:.1f}")
d = probe('Uinf'); u64 = probe('U64')
if d:
    q = [x[1] for x in d['quarter']]
    print(f"Uinf: limit={d.get('limit')} syncs={len(d['sync'])} files={d.get('files')} total={d.get('total')} quarter={[round(v/MIB,1) for v in q]} MiB heap={d['heap']}")
    chk('Uinf quarter samples strictly increase', len(q) == 3 and q[0] < q[1] < q[2])
    if u64 and u64['heap']: chk("Uinf 3N/4 sample > U64 sample-1 retained", len(q) == 3 and q[2] > u64['heap'][0][2], f"{q[2]/MIB if q else 0:.1f} vs {u64['heap'][0][2]/MIB:.1f} MiB")
    chk('Uinf limit 1 GiB, 0 syncs, 1 file', d.get('limit') == 1024 * MIB and len(d['sync']) == 0 and d.get('files') == 1)
print('-- sub-findings --')
for n in ('Udef', 'U0'):
    d = probe(n)
    if d: 
        print(f"{n}: limit={d.get('limit')} syncs={len(d['sync'])} files={d.get('files')} maxCS={d.get('maxcs')} sizes={[s for _, s in d['data']]} heap={[(i, round(x/MIB,1)) for i,_,x in d['heap']]}")
        chk(n + ' limitBytes = 134217728, 1 sync, 2 files', d.get('limit') == 134217728 and len(d['sync']) == 1 and d.get('files') == 2)
d = probe('Ubig')
if d:
    sz = [s for _, s in d['data']]
    print(f"Ubig: syncs={len(d['sync'])} files={d.get('files')} sizes={sz}")
    chk('Ubig 5 syncs, 5 files each > L', len(d['sync']) == 5 and d.get('files') == 5 and all(s > MIB for s in sz))
d = probe('Udel')
if d:
    print(f"Udel: syncs={len(d['sync'])} files={d.get('files')} maxCS={d.get('maxcs')} ({d.get('maxcs',0)/MIB:.2f} L) sizes={[s for _, s in d['data']]}")
    chk('Udel bypass: 0 syncs, 1 file, maxCurrentSize >= 12 L', len(d['sync']) == 0 and d.get('files') == 1 and d.get('maxcs', 0) >= 12 * MIB)

print('== client-process tier ==')
def cl(name):
    o = os.path.join(P, name + '.out')
    if not os.path.exists(o): return None
    txt = open(o, errors='replace').read()
    ex = re.findall(r'^exit=(\d+)', txt, re.M)
    dd = {'exit': int(ex[-1]) if ex else None, 'done': 'BULK done' in txt, 'oom': 'OutOfMemoryError' in txt, 'files': [], 'du': None, 'peak': None}
    m = re.search(r'BULK done rows=\d+ secs=([\d.]+)', txt); dd['secs'] = float(m.group(1)) if m else None
    df = os.path.join(P, 'data-' + name + '.txt')
    if os.path.exists(df):
        for l in open(df):
            p = l.split()
            if l.endswith('-Data.db\n') and len(p) >= 9: dd['files'].append((os.path.basename(p[-1]), int(p[4])))
            elif len(p) == 2 and p[0].isdigit(): dd['du'] = int(p[0])
    dd['files'].sort(key=lambda x: gen(x[0]))
    pf = os.path.join(P, 'peak-' + name + '.txt')
    if os.path.exists(pf) and open(pf).read().strip(): dd['peak'] = int(open(pf).read().strip())
    return dd
spec = {'m16': (16, 31, 35, 15, 17), 'm64': (64, 8, 10, 58, 67), 'mdef': (128, 5, 5, 115, 135), 'm256': (256, 3, 3, 230, 270)}
pk = {}; dus = {}
for n, (k, flo, fhi, slo, shi) in spec.items():
    d = cl('m16-first') if n == 'm16' and cl('m16-first') else cl(n)   # measurement = first m16 run; the rerun only feeds the load step
    if d is None: chk(n + ' present', False); continue
    L = k * MIB; sz = [s for _, s in d['files']]; nl = sz[:-1]
    print(f"{n}: exit={d['exit']} done={d['done']} secs={d['secs']} files={len(sz)} non-last MiB [{min(nl)/MIB if nl else 0:.2f},{max(nl)/MIB if nl else 0:.2f}] last={sz[-1]/MIB if sz else 0:.2f} max={max(sz) if sz else 0} du={d['du']} peak={d['peak']} MiB")
    chk(n + ' exit 0 + BULK done', d['exit'] == 0 and d['done'])
    chk(n + f' files in [{flo},{fhi}]', flo <= len(sz) <= fhi, str(len(sz)))
    chk(n + f' non-last Data.db in [{slo},{shi}] MiB', bool(nl) and all(slo * MIB <= s <= shi * MIB for s in nl))
    chk(n + ' no Data.db > L + 1152 B', bool(sz) and max(sz) <= L + 1152, f'max {max(sz) if sz else 0} vs {L+1152}')
    pk[n] = d['peak']; dus[n] = d['du']
if len(pk) == 4 and None not in pk.values():
    chk('peak strictly increasing m16<m64<mdef<m256', pk['m16'] < pk['m64'] < pk['mdef'] < pk['m256'], str(pk))
    chk('peak(m16) < 150 MiB', pk['m16'] < 150, str(pk['m16']))
    chk('peak(m256) >= 256 MiB', pk['m256'] >= 256, str(pk['m256']))
    print(f"peak(m256)-peak(m16) = {pk['m256']-pk['m16']} MiB")
if len(dus) == 4 and None not in dus.values():
    mean = sum(dus.values()) / 4
    chk('du within +-2% of mean', all(abs(v / mean - 1) <= 0.02 for v in dus.values()), f'{min(dus.values())}..{max(dus.values())} spread {(max(dus.values())-min(dus.values()))/mean*100:.3f}%')
for n in ('x16', 'x256', 'm16-first'):
    d = cl(n)
    if d: print(f"{n}: exit={d['exit']} done={d['done']} oom={d['oom']} files={len(d['files'])} peak={d['peak']} du={d['du']}")
d = cl('x16'); chk('x16 exit 0 + BULK done', bool(d) and d['exit'] == 0 and d['done'])
d = cl('x256'); chk('x256 non-zero exit + OutOfMemoryError', bool(d) and d['exit'] not in (0, None) and d['oom'])
print(f"TOTAL PASS={sum(1 for _, o in res if o)} FAIL={sum(1 for _, o in res if not o)}")
