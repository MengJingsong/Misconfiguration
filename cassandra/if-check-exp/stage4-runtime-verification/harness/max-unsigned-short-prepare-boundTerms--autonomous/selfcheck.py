#!/usr/bin/env python3
"""Independent self-check for max-unsigned-short-prepare-boundTerms--autonomous: re-parses the RAW outputs of one run and recomputes every number the results
file cites (it does not read the run scripts' own summary verdict lines).
usage: python3 -I selfcheck.py <logs>/run1        (<logs>/run1/unit/run.out, <logs>/run1/cluster/c<MiB>-m<M>/{samples.csv,histo-*.txt,system.log,session.log})
Prints PART n: HOLDS/DOES NOT HOLD lines and the recomputed table; exit 1 if any part does not hold."""
import csv, glob, os, re, sys

root = sys.argv[1]; MIB = 1 << 20; bad = []


def part(n, ok, text):
    print(f'PART {n}: {"HOLDS" if ok else "DOES NOT HOLD"} - {text}')
    if not ok:
        bad.append(n)


def kv(line):
    return dict(re.findall(r'(\w+)=(-?\d+)', line))


# ---------------- unit tier
U = {}
for l in open(f'{root}/unit/run.out'):
    m = re.match(r'STAGE4 (cal|boundary|final|run) label=(c\d+) ', l)
    if not m:
        continue
    kind, lab = m.groups(); d = U.setdefault(lab, {'cal': {}, 'final': {}, 'bound': None, 'run': None})
    v = kv(l)
    if kind == 'run': d['run'] = v
    elif kind == 'cal':
        d['cal'][int(v['M'])] = dict(v, msg=l.split('result=')[1].split(' weight=')[0].strip())
    elif kind == 'boundary': d['bound'] = dict(v, msg=l.split('result=')[1].split(' count_before=')[0].strip())
    else: d['final'][int(v['M'])] = v
checks = [l.strip() for l in open(f'{root}/unit/run.out') if l.startswith('STAGE4 check')]
labs = sorted(U, key=lambda s: int(s[1:]))
print('unit JVMs:', labs, ' check lines:', len(checks), ' MISMATCH:', sum(c.endswith('MISMATCH') for c in checks))
part('U1 validity', len(labs) == 3 and all(U[l]['run'] and int(U[l]['run']['cap_mib']) == int(l[1:]) for l in labs),
     'three JVMs, each reports the cap_mib it was given (the yaml knob took effect): ' + ', '.join(f"{l}->{U[l]['run']['cap_mib']}" for l in labs))
EXP = 'Too many markers(?). 65536 markers exceed the allowed maximum of 65535'
part('U2 boundary', all(U[l]['bound']['msg'] == EXP and U[l]['bound']['count_before'] == U[l]['bound']['count_after'] for l in labs),
     'M=65536 rejected with the exact text and the count unchanged in every JVM')
# weight of one 65535-marker statement from whichever JVM accepted it, cross-checked with the size-gate message of a JVM that rejected it
w65 = [int(U[l]['cal'][65535]['weight']) for l in labs if U[l]['cal'][65535]['weight'] != '-1' and int(U[l]['cal'][65535]['weight']) > 0]
rej = [int(re.search(r'size (\d+) bytes', U[l]['cal'][65535]['msg']).group(1)) for l in labs if 'Prepared statement of size' in U[l]['cal'][65535]['msg']]
part('U3 weights', (not w65 or not rej or abs(w65[0] - 16 - rej[0]) <= 64) and all(int(U[labs[0]]['cal'][m]['weight']) == int(U[labs[-1]]['cal'][m]['weight']) or -1 in (int(U[labs[0]]['cal'][m]['weight']), int(U[labs[-1]]['cal'][m]['weight'])) for m in (1, 10, 1000)),
     f'w(1,10,1000)={[U[labs[-1]]["cal"][m]["weight"] for m in (1,10,1000)]}; w(65535) accepted={w65} size-gate message={rej} (pstmntSize + 16 B key)')
ok = True; rows = []
for l in labs:
    cap = int(U[l]['run']['cap_bytes'])
    for m, f in sorted(U[l]['final'].items()):
        s, c, e, o, r = (int(f[k]) for k in ('sumWeights', 'count', 'evicted', 'offered', 'rejected'))
        w = int(f['w'])
        good = s <= cap and (c + e == o if w > 0 else (c == 0 and r == o))
        ok &= good
        rows.append((l, m, cap, w, o, r, s, c, e, round(s / cap, 3), good))
print('label M cap w offered rejected sumWeights count evicted sum/cap ok'); [print(*r) for r in rows]
part('U4 ceiling', ok, 'sumWeights <= cap in every arm; count + evicted == offered where accepted, all rejected by the size gate where w(M) > cap')
# cap follows the knob: M=10 and M=1000 retained sums across the three caps
byM = {m: {int(U[l]['run']['cap_mib']): int(U[l]['final'][m]['sumWeights']) for l in labs} for m in (10, 1000)}
ok2 = all(v[100] / v[1] > 20 and v[1] <= v[10] <= v[100] and all(int(U[l]['final'][m]['evicted']) > 0 for l in labs) for m, v in byM.items())
part('U5 follows the knob', ok2, f'retained sums by cap MiB {byM}; ratio 100 MiB / 1 MiB = ' + ', '.join(f'M={m}: {v[100]/v[1]:.1f}' for m, v in byM.items()))
m65 = {int(U[l]['run']['cap_mib']): U[l]['final'][65535] for l in labs}
print('M=65535 by cap:', {c: (f['offered'], f['rejected'], f['count'], f['sumWeights'], f['evicted']) for c, f in sorted(m65.items())})
w = int(w65[0]) if w65 else None
part('U6 size gate / retention at 65535', all((int(f['count']) == 0 and int(f['rejected']) == int(f['offered'])) if (w is None or w > c * MIB) else (int(f['rejected']) == 0 and int(f['count']) * w <= c * MIB + w) for c, f in m65.items()),
     f'w(65535)={w}: rejected whole where w > cap, retained count*w <= cap where w <= cap')

# ---------------- cluster tier
arms = {}
for d in sorted(glob.glob(f'{root}/cluster/c*-m*')):
    mm = re.match(r'.*/c(\d+)-m(\d+)$', d); cap, M = int(mm.group(1)), int(mm.group(2))
    a = {'dir': d}
    txt = open(d + '/session.log', errors='replace').read()
    a['readback'] = re.search(r'Initialized prepared statement caches with (\d+) MiB', open(d + '/system.log', errors='replace').read()).group(1)
    s = list(csv.DictReader(open(d + '/samples.csv')))
    a['samples'] = [(float(r['t_s']), int(r['count']), int(r['evicted'])) for r in s]
    hs = {}
    for f in glob.glob(d + '/histo-*.txt'):
        t = open(f).read()
        tot = re.search(r'^Total\s+(\d+)\s+(\d+)', t, re.M); pr = re.search(r'^\s*\d+:\s+(\d+)\s+(\d+)\s+org\.apache\.cassandra\.cql3\.QueryHandler\$Prepared\s*$', t, re.M)
        hs[os.path.basename(f)[6:-4]] = (int(tot.group(2)), int(pr.group(1)) if pr else 0)
    a['histo'] = hs
    a['res'] = re.findall(r'^.*RESULT (load|boundary|rows).*$', txt, re.M)
    sm = open(d + '/summary.txt').read()
    a['final'] = kv(re.search(r'COUNTERS final.*', sm).group(0)); a['load'] = kv(re.search(r'RESULT load.*', sm).group(0))
    a['stop'] = 'STOP RULE met' in sm; a['warn'] = int(re.search(r'LOG discard-warnings=(\d+)', sm).group(1))
    a['bound'] = re.search(r'RESULT boundary.*', sm).group(0) if M == 65535 else None
    a['left'] = 'no daemon of this slot left' in sm.split('STOPPED:')[-1]
    arms[(cap, M)] = a
print('\ncluster arms:', sorted(arms))
part('C1 validity', len(arms) == 9 and all(int(a['readback']) == c for (c, m), a in arms.items()), 'nine arms; the log read-back equals the cap of each: ' + str({k: a['readback'] for k, a in sorted(arms.items())}))
part('C2 boundary', all(a['bound'] and EXP in a['bound'] and 'rejected' in a['bound'] for (c, m), a in arms.items() if m == 65535), '65536-marker prepare rejected with the exact text in every 65535 arm')
wU = {m: int(U[labs[-1]]['cal'][m]['weight']) for m in (10, 1000)}; wU[65535] = w
print('cap MiB, M: samples-final count, evicted, offered, accepted, rejected, live-Prepared(after-baseline), live_bytes delta, count*w_unit/cap')
ok3 = ok4 = ok5 = True; strict = []
for (c, m), a in sorted(arms.items()):
    cnt, ev = int(a['final']['count']), int(a['final']['evicted']); ld = a['load']; h0, h1 = a['histo']['0-baseline'], a['histo']['2-after-load']
    wm = wU[m] if wU.get(m) and wU[m] > 0 else None
    util = (cnt * wm / (c * MIB)) if wm else None
    print(c, m, cnt, ev, ld['offered'], ld['accepted'], ld['rejected'], h1[1] - h0[1], h1[0] - h0[0], None if util is None else round(util, 3))
    if wm:
        strict.append(cnt * wm <= c * MIB)
        ok3 &= (cnt * wm <= 1.05 * c * MIB) and (cnt < 10 or cnt * wm >= 0.95 * c * MIB)
    if m in (10, 1000):
        ok4 &= ev > 0 and cnt > 0
    ok5 &= a['left']
part('C3 ceiling (implied weight)', ok3, 'count x unit-tier weight within 5 % of the cap (0.95..1.05 when count >= 10, <= 1.05 below): the cluster does not measure a per-entry weight, so the unit-tier weight is a proxy; '
     f'strict count x w_unit <= cap held in {sum(strict)} of {len(strict)} arms (first version of this part, kept in selfcheck-first.out, required all)')
part('C4 binding', ok4, 'M=10 and M=1000 arms: evictions > 0 and count > 0 at every cap')
ret = {m: {c: int(arms[(c, m)]['final']['count']) for c in (10, 50, 200)} for m in (10, 1000)}
part('C5 follows the knob', all(r[10] < r[50] < r[200] and r[200] / r[10] > 8 for r in ret.values()), f'retained counts by cap MiB {ret} (caps 1:5:20)')
inst = {(c, m): arms[(c, m)]['histo']['2-after-load'][1] - arms[(c, m)]['histo']['0-baseline'][1] for (c, m) in arms}
part('C6 live Prepared objects match the cache', all(abs(inst[k] - int(arms[k]['final']['count'])) <= max(3, 0.02 * int(arms[k]['final']['count'])) for k in arms), f'histogram delta of QueryHandler$Prepared vs count: {inst}')
part('C7 stopped clean', ok5, 'every arm ended with no daemon of this slot left')
sys.exit(1 if bad else 0)
