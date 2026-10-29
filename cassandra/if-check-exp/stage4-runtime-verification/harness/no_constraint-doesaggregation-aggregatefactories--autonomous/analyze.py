#!/usr/bin/env python3
"""Judge raw.csv / proof.txt / trace.txt of a run against the frozen prediction V1-V5 of
no_constraint-doesaggregation-aggregatefactories--autonomous (B2f) and the conclusions table (B2g).
Usage: analyze.py <raw-dir-plain> [<raw-dir-byteman>]"""
import csv, sys, collections, statistics as st
plain = sys.argv[1]; bm = sys.argv[2] if len(sys.argv) > 2 else None
res = []
def check(name, ok, detail=''):
    res.append(ok); print(('PASS ' if ok else 'FAIL ') + name + ((' :: ' + detail) if detail else ''))
rows = list(csv.DictReader(open(plain + '/raw.csv')))
al = collections.defaultdict(list); rt = collections.defaultdict(list); nr = collections.defaultdict(set)
for r in rows:
    k = (r['pass'], int(r['N']), r['arm']); al[k].append(int(r['alloc'])); rt[k].append(int(r['retained'])); nr[k].add(int(r['rows']))
Ns = sorted({k[1] for k in al}); arms = ['P', 'P2', 'A1', 'A2', 'C']
def amed(p, n, a): return st.median(al[('A', n, a)] + al[('B', n, a)]) if p == 'AB' else st.median(al[(p, n, a)])
def rmed(p, n, a): return st.median(rt[('A', n, a)] + rt[('B', n, a)]) if p == 'AB' else st.median(rt[(p, n, a)])

proof = open(plain + '/proof.txt').read().splitlines()
check('instrument known-answers (alloc, measureDeep)', sum(1 for l in proof if l.startswith('CHECK') and l.endswith(' ok')) == 2)
pl = [l for l in proof if l.startswith('PROOF')]; bad = []
for l in pl:
    d = dict(x.split('=', 1) for x in l.split()[1:]); n = int(d['n'])
    fr = d['firstRow'].strip('/').split('/')
    exp_rows = {'P': n, 'P2': n, 'A1': 1, 'A2': 1, 'C': min(100, n)}[d['arm']]
    ok = d['isAggregate'] == d['expect'] and int(d['rows']) == exp_rows
    if d['arm'] == 'A1': ok &= fr == [str(n - 1)]
    if d['arm'] == 'A2': ok &= fr == [str(n - 1), '0']
    if not ok: bad.append(l)
check('V1 branch proof: isAggregate side, row counts, values on every cell', not bad and len(pl) == len(Ns) * 2 * len(arms), f'{len(pl)} lines, {len(bad)} bad' + (' e.g. ' + bad[0] if bad else ''))
if bm:
    cur = None; cnt = collections.defaultdict(collections.Counter)
    for l in open(bm + '/trace.txt'):
        l = l.strip()
        if l.startswith('MARK'):
            f = l.split(); kind = f[1]; d = dict(x.split('=') for x in f[2:]); cur = (kind, int(d['n'].replace('n=', '')) if 'n' in d else 0, d['arm']); continue
        if cur and (l.startswith('DA') or l.startswith('AQP')): cnt[cur][l.replace(' ', '_')] += 1
    badc = []
    for (kind, n, arm), c in cnt.items(): pass
    for kind in ('prep', 'cell'):
        for n in Ns:
            for arm in arms:
                c = cnt.get((kind, n, arm), collections.Counter())
                if arm == 'P' and (c['DA_true'] or c['DA_false'] or c['AQP']): badc.append((kind, n, arm, dict(c)))
                if arm in ('P2', 'C') and (c['DA_true'] or c['AQP'] or (arm == 'P2' and not c['DA_false'] and kind == 'prep')): badc.append((kind, n, arm, dict(c)))
                if arm in ('A1', 'A2') and (not c['DA_true'] or (kind == 'cell' and c['AQP'] < 10)): badc.append((kind, n, arm, dict(c)))
    check('V1 byteman: doesAggregation true only for A1/A2 (prepare and run), false for P2, not evaluated for P; aggregate pager only for A1/A2', not badc, f'bad={badc[:3]}')
for p in ('A', 'B', 'AB'):
    big, small = Ns[-1], Ns[0]
    ok = True; det = []
    for a in ('P', 'P2'):
        r1, r0 = rmed(p, big, a), rmed(p, small, a); ok &= r1 >= 4_000_000 and r1 >= 50 * r0; det.append(f'{a} {r0}->{r1} ({r1/r0:.0f}x, {r1/big:.0f} B/row)')
    for a in ('A1', 'A2'):
        vals = [rmed(p, n, a) for n in Ns]; ok &= max(vals) <= 2048 and max(vals) <= 1.5 * min(vals); det.append(f'{a} {vals}')
    check(f'V2 retained result (pass {p})', ok, '; '.join(det))
for p in ('A', 'B', 'AB'):
    ok = True; det = []
    for a in ('P', 'P2', 'A1', 'A2'):
        ratio = amed(p, Ns[-1], a) / amed(p, Ns[0], a); ok &= ratio >= 10; det.append(f'{a} x{ratio:.1f}')
    for n in [x for x in Ns if x >= 10000]:
        for a in ('A1', 'A2'):
            rr = amed(p, n, a) / amed(p, n, 'P2'); ok &= rr >= 0.3; det.append(f'{a}/P2@{n}={rr:.2f}')
    check(f'V3 allocation follows N in every arm; aggregate arms >= 0.3 x P2 (pass {p})', ok, '; '.join(det))
for p in ('A', 'B', 'AB'):
    big, small = Ns[-1], Ns[0]
    ok = (nr[('A', big, 'C')] == {100}) and rmed(p, big, 'C') <= 0.01 * rmed(p, big, 'P') and amed(p, big, 'C') <= 0.1 * amed(p, big, 'P') and 0.5 <= amed(p, big, 'C') / amed(p, small, 'C') <= 2
    check(f'V4 control C moved (pass {p})', ok, f'C rows {sorted(nr[("A", big, "C")])} retained {rmed(p, big, "C")} vs P {rmed(p, big, "P")}; alloc {amed(p, big, "C")} vs P {amed(p, big, "P")} vs own@small {amed(p, small, "C")}')
mx = 0; rg = 0; rd = 0; wc = None
for n in Ns:
    for a in arms:
        d = abs(amed('A', n, a) - amed('B', n, a)) / amed('AB', n, a)
        if d > mx: mx, wc = d, (n, a, amed('A', n, a), amed('B', n, a))
        for p in 'AB':
            v = al[(p, n, a)]; rg = max(rg, (max(v) - min(v)) / st.median(v))
        rd = max(rd, abs(rmed('A', n, a) - rmed('B', n, a)) / max(1, rmed('AB', n, a)))
check('V5 noise: allocation passes within 5%', mx <= 0.05, f'largest {mx:.5f} at {wc}')
check('V5 repeats (max-min)/median <= 10%', rg <= 0.10, f'largest {rg:.5f}')
check('V5 retained sizes of the two passes within 1%', rd <= 0.01, f'largest {rd:.6f}')
print('--- allocation medians (pooled) and retained medians per N', Ns)
for a in arms: print(a, 'alloc', [int(amed('AB', n, a)) for n in Ns], 'retained', [int(rmed('AB', n, a)) for n in Ns], 'rows', [sorted(nr[('A', n, a)]) for n in Ns])
print('SUMMARY all_pass=%s' % all(res))
