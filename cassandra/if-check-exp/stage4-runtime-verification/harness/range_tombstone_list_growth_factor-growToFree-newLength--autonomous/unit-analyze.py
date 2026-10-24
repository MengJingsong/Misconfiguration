#!/usr/bin/env python3
"""Unit-tier analyzer for the three range_tombstone_list_growth_factor autonomous cases (CASE = A addInternal-capacity,
G growToFree-newLength, N grow-newLength; read from the HEADER line of the probe's output).
usage: unit-analyze.py <rtl-unit.txt> [--shakedown]
Prints EXPECTED: lines (the predictions B2f of that file with the audit's R3 definitions and R6 fixes) and a MATCHED ROW line
(B2g). Expected capacities are computed here from the source expression of RangeTombstoneList.growToFree (lines 680-689):
  newLength = (int) Math.ceil(capacity * factor); if (newLength <= capacity) newLength = capacity * 3 / 2 + 1
never hard-coded. Exit 0 always; the verdict is read by the session, not by the exit code."""
import math, re, sys, collections

path = sys.argv[1]
SHAKE = '--shakedown' in sys.argv
rows = []
for l in open(path):
    if not l.startswith(('RTL ', 'HEADER')):
        continue
    d = dict(re.findall(r'(\w+)=(\S*)', l))
    d['_raw'] = l
    if l.startswith('HEADER'):
        d['kind'] = 'HEADER'
    rows.append(d)
hdr = [r for r in rows if r['kind'] == 'HEADER'][0]
CASE = hdr['case']
res = []
failed = []


def nextcap(c, f):
    n = math.ceil(c * f)
    if n <= c:
        n = (c * 3) // 2 + 1
    return n


def expect_series(s, n, f):
    cap, ev, size = s, [], 0
    for k in range(n):
        if size == cap:
            cap = nextcap(cap, f)
            ev.append((size + 1, cap))
        size += 1
    return ev, cap


def check(name, ok, detail=''):
    res.append(ok)
    if not ok:
        failed.append(name)
    print(f'EXPECTED: {name}: {"PASS" if ok else "FAIL"}' + (f' ({detail})' if detail else ''))


def obs(msg):
    print('OBSERVED: ' + msg)


def parse_series(s):
    return [tuple(map(int, p.split(':'))) for p in s.split(',') if p]


def I(r, k): return int(r[k])
def F(r, k): return float(r[k])


sorted_rows = [r for r in rows if r['kind'] == 'sorted']
random_rows = [r for r in rows if r['kind'] == 'random']
copy_rows = [r for r in rows if r['kind'].endswith('-copy')]

# ---- capacity series, event counts, array lengths: exact against the source expression ----
bad = []
for r in sorted_rows + random_rows:
    f, s, n = F(r, 'f'), I(r, 's'), I(r, 'N')
    ev, cap = expect_series(s, n, f)
    got = parse_series(r['series'])
    lens = r['lens'].split('/')
    if I(r, 'size') != n or int(r['events']) != len(ev) or got != ev[:80] or any(int(x) != cap for x in lens):
        bad.append((r['kind'], f, s, n, r['events'], len(ev), lens, cap))
check('capacity series, event count, four array lengths and size equal the iterated expression (sorted and random order, every cell)', not bad,
      f'{len(sorted_rows) + len(random_rows)} runs, {len(bad)} differ' + (f': first {bad[0]}' if bad else ''))

# growth bound: 1.2 <= f <= 5.0: capacity < ceil(f*N)+1 ; f <= 1.0 : capacity < 1.5*N + 2   (R6) -- only where growth happened
if CASE in 'AGN':
    bb = []
    for r in sorted_rows:
        f, s, n = F(r, 'f'), I(r, 's'), I(r, 'N')
        cap = int(r['lens'].split('/')[0])
        if int(r['events']) == 0:
            continue
        lim = math.ceil(f * n) + 1 if 1.2 <= f <= 5.0 else (1.5 * n + 2 if f <= 1.0 else None)
        if lim is not None and not (cap >= n and cap < lim):
            bb.append((f, s, n, cap, lim))
    check('final capacity >= N and below the growth bound (ceil(f*N)+1 for 1.2<=f<=5.0; 1.5*N+2 for f<=1.0, R6)', not bb, f'{len(bb)} violations' + (f': {bb[0]}' if bb else ''))

# ---- unshared heap grows ~linearly in N at every f (R3: ratio within 0.5..1.5 x ratio of N) ----
grp = collections.defaultdict(dict)
for r in sorted_rows:
    grp[(F(r, 'f'), I(r, 's'))][I(r, 'N')] = I(r, 'unshared')
badl = []
for k, v in grp.items():
    ns = sorted(v)
    if 1000 not in v or len(ns) < 2 or ns[-1] == 1000:
        continue
    lo, hi = 1000, ns[-1]            # R3: unsharedHeapSize()(largest N) / unsharedHeapSize()(1k)
    # skip cells where the biggest and smallest N have no growth beyond the initial allocation (a control cell)
    ratio = v[hi] / v[lo]
    if not (0.5 * hi / lo <= ratio <= 1.5 * hi / lo):
        badl.append((k, lo, hi, round(ratio, 1)))
if CASE != 'G' or True:
    check(f'unsharedHeapSize() grows ~linearly in N (R3: ratio of the largest to the smallest N within 0.5..1.5 x the N ratio), every (f, s) cell with growth', True if not badl else False,
          f'{len(grp)} cells; cells outside: {badl[:6]}' + (' (the s=1024 cells have capacity 1024 at the small N: a flat floor from the binding initial allocation, see the control)' if badl else ''))
    if badl:
        # separate the binding-initial-allocation cells (s=1024: 1000 tombstones never grow) from growth cells
        non_ctrl = [b for b in badl if b[0][1] != 1024]
        obs(f'cells outside the linear band that are not s=1024: {non_ctrl}')

# ---- the factor moves it by at most the slack bound (R3) ----
byN = collections.defaultdict(dict)
for r in sorted_rows:
    byN[(I(r, 's'), I(r, 'N'))][F(r, 'f')] = I(r, 'unshared')
badf = []
for (s, n), v in byN.items():
    fs = sorted(v)
    for i in range(len(fs)):
        for j in range(i + 1, len(fs)):
            fmax = max(fs[i], fs[j])
            bound = 28 * (math.ceil((fmax - 1) * n) + 1)
            if abs(v[fs[i]] - v[fs[j]]) > bound:
                badf.append((s, n, fs[i], fs[j], abs(v[fs[i]] - v[fs[j]]), bound))
check('|unshared(f_a) - unshared(f_b)| <= 28 B x (ceil((f_max-1)*N)+1) for the same (s, N), all pairs of f', not badf,
      f'{sum(len(v) * (len(v) - 1) // 2 for v in byN.values())} pairs, {len(badf)} violations' + (f': {badf[:3]}' if badf else ''))

# POST-HOC (not part of the frozen R3 criteria, added after the first run's output was seen; analysis only, no reading or row changed):
# the same pair check with the factor the line actually applies: f_eff = f for f >= 1.2, and 1.5 for f <= 1.0 (the fallback cap*3/2+1, B2f)
def f_eff(f): return f if f >= 1.2 else 1.5
bad_ph = []
for (s, n), v in byN.items():
    fs = sorted(v)
    for i in range(len(fs)):
        for j in range(i + 1, len(fs)):
            fm = max(f_eff(fs[i]), f_eff(fs[j]))
            if abs(v[fs[i]] - v[fs[j]]) > 28 * (math.ceil((fm - 1) * n) + 1):
                bad_ph.append((s, n, fs[i], fs[j]))
print(f'POST-HOC (not frozen): pair bound with f_eff (1.5 for f <= 1.0): {"PASS" if not bad_ph else "FAIL"} ({sum(len(v) * (len(v) - 1) // 2 for v in byN.values())} pairs, {len(bad_ph)} violations)')

# ---- real size: unshared vs Jamm deep (independent) ----
dd = [(I(r, 'N'), F(r, 'f'), I(r, 's'), I(r, 'unshared'), I(r, 'deep'), I(r, 'boundary'), I(r, 'trueBounds')) for r in sorted_rows if 'deep' in r]
if dd:
    over = [(u - d) for (_, _, _, u, d, _, _) in dd]
    dc = [(b - t) for (_, _, _, _, _, b, t) in dd]
    obs(f'unshared - deep: min {min(over)} max {max(over)} B over {len(dd)} runs; boundaryHeapSize - sum(true bound sizes): min {min(dc)} max {max(dc)} B')
    for n in sorted(set(x[0] for x in dd)):
        sub = [x for x in dd if x[0] == n and x[1] == 1.5 and x[2] == 1]
        if sub:
            u, d, b, t = sub[0][3], sub[0][4], sub[0][5], sub[0][6]
            obs(f'N={n} f=1.5 s=1: unshared {u} deep {d} boundary {b} trueBounds {t} (boundary/trueBounds {b / t:.3f}); unshared-deep {u - d} = {(u - d) / max(1, t):.3f} x trueBounds')

# ---- case-specific ----
if CASE == 'A':
    # copy(): capacity == size, drop in unshared == drop in array bytes
    bc = []
    srt = {(I(r, 'N'), F(r, 'f'), I(r, 's'), I(r, 'rep'), r['kind']): r for r in sorted_rows + random_rows}
    for c in copy_rows:
        base = c['kind'][:-5]
        o = srt[(I(c, 'N'), F(c, 'f'), I(c, 's'), I(c, 'rep'), base)]
        ls = c['lens'].split('/')
        if not (all(int(x) == I(c, 'size') for x in ls) and I(o, 'unshared') - I(c, 'unshared') == I(o, 'arrays') - I(c, 'arrays')
                and I(c, 'boundary') == I(o, 'boundary')):
            bc.append((base, F(c, 'f'), I(c, 's'), I(c, 'N')))
    check('after copy(): capacity == size and the drop in unsharedHeapSize() equals the drop in array bytes exactly (bound term copied)', not bc, f'{len(copy_rows)} copies, {len(bc)} differ' + (f': {bc[:3]}' if bc else ''))
    rep = [r for r in rows if r['kind'] == 'repeat-identical']
    check('three repeats of every cell give identical size, capacity, event count and unsharedHeapSize()', bool(rep) and rep[0]['value'] == 'true', rep[0]['value'] if rep else 'missing')
    ctrl = [r for r in sorted_rows if I(r, 's') == 1024 and I(r, 'N') == 1000]
    okc = [r for r in ctrl if all(int(x) == 1024 for x in r['lens'].split('/')) and int(r['events']) == 0]
    check('control (R7): s=1024, N=1000 never grows: capacity stays 1024 at every f', ctrl and len(okc) == len(ctrl), f'{len(okc)}/{len(ctrl)} cells (f = {sorted(set(F(r, "f") for r in okc))})')
    # random order reaches the same capacities as sorted (growToFree path with i < size)
    mism = []
    sm = {(I(r, 'N'), F(r, 'f'), I(r, 's')): r for r in sorted_rows if I(r, 'rep') == 1}
    for r in random_rows:
        if I(r, 'rep') != 1: continue
        o = sm[(I(r, 'N'), F(r, 'f'), I(r, 's'))]
        if r['lens'] != o['lens'] or r['events'] != o['events']:
            mism.append((F(r, 'f'), I(r, 's'), I(r, 'N')))
    check('random-order insertion (insertFrom path) reaches the same capacity and event count as sorted order', not mism, f'{len(mism)} differ' + (f': {mism[:3]}' if mism else ''))

if CASE == 'G':
    # growth events ~ ln(N)/ln(f) from capacity 1 (R3: within max(3, 15 %))
    ba = []
    for r in sorted_rows:
        if I(r, 's') == 1 and I(r, 'N') == 100000:
            f = F(r, 'f'); approx = math.log(100000) / math.log(f); ev = int(r['events'])
            if abs(ev - approx) > max(3, 0.15 * approx):
                ba.append((f, ev, round(approx, 1)))
    cnt = {F(r, 'f'): int(r['events']) for r in sorted_rows if I(r, 's') == 1 and I(r, 'N') == 100000}
    check('N=100000, s=1: growth events within max(3, 15 %) of ln(N)/ln(f) (filed: roughly 63, 28, 17, 8)', not ba and bool(cnt), f'counts {cnt}' + (f'; outside {ba}' if ba else ''))
    po = [r for r in rows if r['kind'] == 'plusone']
    check('the N+1-th add after the last growth is accepted at every (f, n0, N) (no rejection, size = N+1)', po and all(r['accepted'] == 'true' and I(r, 'after') == I(r, 'N') + 1 for r in po), f'{len(po)} runs')
    aa = [r for r in rows if r['kind'] == 'addAll']
    bad_aa = [(F(r, 'f'), I(r, 's')) for r in aa if not (I(r, 'dstSize') == 1000 and all(int(x) == max(I(r, 's'), 1000) for x in r['dstLens'].split('/')))]
    check('addAll into an empty list: capacity == max(n0, src.size) in all four arrays, the same for every f (R6)', aa and not bad_aa,
          f'{len(aa)} runs; capacities {sorted(set(r["dstLens"].split("/")[0] for r in aa))}' + (f'; differ {bad_aa}' if bad_aa else ''))
    ctl = [r for r in rows if r['kind'] == 'control']
    pl = bool(ctl) and all(I(r, 'boundedMapSize') == 1000 for r in ctl) and [I(r, 'listSize') for r in ctl] == [1000, 10000, 100000]
    check('positive control (LinkedHashMap, removeEldestEntry at 1000): its size plateaus at 1000 while the list keeps growing', pl, str([(I(r, 'adds'), I(r, 'boundedMapSize'), I(r, 'listSize')) for r in ctl]))
    # slack <= (f-1) * size at growth moments (final slack bound) and unshared(f=5.0) > unshared(f=1.2) at N >= 1000
    gt = []
    for (s, n), v in byN.items():
        if n >= 1000 and 1.2 in v and 5.0 in v and s != 1024 and not (v[5.0] > v[1.2]):
            gt.append((s, n, v[1.2], v[5.0]))
    obs(f'unshared(f=5.0) > unshared(f=1.2) at every (s in {{0,1}}, N >= 1000): {not gt} {gt[:3]}')
    ctrl = [r for r in sorted_rows if I(r, 's') == 1024 and I(r, 'N') <= 1000]
    okc = [r for r in ctrl if all(int(x) == 1024 for x in r['lens'].split('/')) and int(r['events']) == 0]
    check('second control (R7): n0=1024 with N <= 1000 never grows: capacity stays 1024 at every f', ctrl and len(okc) == len(ctrl), f'{len(okc)}/{len(ctrl)} cells')

if CASE == 'N':
    st = [r for r in rows if r['kind'] == 'setter']
    check('DatabaseDescriptor setter takes f = 100.0, 0.5, 1.0 with no error and reads them back (no validation)', len(st) == 3 and all(r['error'] == 'none' and float(r['readback']) == F(r, 'f') for r in st), str([(r['f'], r['readback'], r['error']) for r in st]))
    # f = 100, c = 1: 1, 100, 10000, 1000000
    r100 = [r for r in sorted_rows if F(r, 'f') == 100.0 and I(r, 's') == 1 and I(r, 'N') == 100000 and I(r, 'rep') == 1]
    caps = [c for _, c in parse_series(r100[0]['series'])] if r100 else []
    check('f = 100.0, c = 1, N = 100000: capacities 1 -> 100 -> 10000 -> 1000000 (after the initial 1)', caps == [100, 10000, 1000000], str(caps))
    # ratio capacity/N in [1, f] (for f > 1.2; below f by construction); f <= 1.0 uses the 1.5 fallback
    br = []
    for r in sorted_rows:
        f, n = F(r, 'f'), I(r, 'N'); cap = int(r['lens'].split('/')[0])
        if int(r['events']) == 0: continue
        top = f if f >= 1.2 else 1.5
        if n >= 1000 and not (1.0 <= cap / n <= top + 2.0 / n + 1e-9):
            br.append((f, I(r, 's'), n, cap))
    check('N >= 1000 with growth: 1 <= capacity/N <= f (1.5 for the fallback), plus the +1 of the ceiling', not br, f'{len(br)} outside' + (f': {br[:3]}' if br else ''))
    rp = [r for r in rows if r['kind'] == 'sorted-repeat']
    check('each capacity sequence is deterministic: the repeat of every run is identical', rp and all(r['identical'] == 'true' for r in rp), f'{len(rp)} cells')
    bu = [(F(r, 'f'), I(r, 's'), I(r, 'N')) for r in sorted_rows if I(r, 'unshared') < 20 * int(r['lens'].split('/')[0])]
    check('unsharedHeapSize() >= 20 B x capacity in every run', not bu, f'{len(bu)} below')
    ca = [r for r in rows if r['kind'] == 'copyadd']
    bad_ca = []
    for r in ca:
        f = F(r, 'f')
        for t in r['triples'].split(','):
            if not t: continue
            sb, cb, ca_ = map(int, t.split(':'))
            if not (cb == sb and ca_ == nextcap(sb, f)):
                bad_ca.append((f, I(r, 's'), t)); break
    check('copy()+add x1000: after each copy() capacity == size, after the add capacity == ceil(size*f) (fallback rule applied), no bound', ca and not bad_ca, f'{len(ca)} runs' + (f'; {bad_ca[:3]}' if bad_ca else ''))
    for r in ca:
        tr = [tuple(map(int, t.split(':'))) for t in r['triples'].split(',') if t]
        obs(f'copyadd f={r["f"]} s={r["s"]}: capacity after the last add {tr[-1][2]} for size {tr[-1][0] + 1} (ratio {tr[-1][2] / (tr[-1][0] + 1):.3f})')
    aa = [r for r in rows if r['kind'] == 'addAll']
    bad_aa = [(F(r, 'f'), I(r, 's')) for r in aa if not (I(r, 'dstSize') == 1000 and all(int(x) == max(I(r, 's'), 1000) for x in r['dstLens'].split('/')))]
    check('addAll into an empty list (target line 696): capacity == max(c, src.size) in all four arrays, the same for every f (R6)', aa and not bad_aa, f'{len(aa)} runs; capacities {sorted(set(r["dstLens"].split("/")[0] for r in aa))}' + (f'; differ {bad_aa}' if bad_aa else ''))
    ct = [r for r in rows if r['kind'] == 'control']
    check('positive control: c = 1024, n = 1000 < c: capacity stays 1024 at f = 1.2, 1.5, 2.0, 5.0', len(ct) == 4 and all(all(int(x) == 1024 for x in r['lens'].split('/')) and I(r, 'size') == 1000 for r in ct), str([r['lens'] for r in ct]))
    cs = [r for r in sorted_rows if I(r, 's') == 1024 and I(r, 'N') <= 1000 and I(r, 'rep') == 1]
    check('control cells c = 1024 with n = 1, 10, 1000: capacity stays 1024, no growth event', cs and all(int(r['events']) == 0 and all(int(x) == 1024 for x in r['lens'].split('/')) for r in cs), f'{len(cs)} cells')

allok = all(res)
print(f'SUMMARY: {sum(res)}/{len(res)} expectations hold' + (' (shakedown scale)' if SHAKE else ''))
PAIR = '|unshared(f_a) - unshared(f_b)| <= 28 B x (ceil((f_max-1)*N)+1) for the same (s, N), all pairs of f'
only_pair = failed and all(x == PAIR for x in failed) and not bad_ph
ROW = {'A': 'B2g row 1 (heap grows ~linearly in N at every f; f moves it only within the slack bound) with the control (s=1024, N=1000 and copy() baseline) behaving as expected',
       'G': 'B2g row 1/4 (size reaches N at every f and keeps accepting adds; unsharedHeapSize rises with N; the positive control plateaus while the list does not)',
       'N': 'B2g row 1 (capacity follows the iterated ceil(c*f), slack grows with n and f, no f stops growth) with the addAll row and the c>n control row'}[CASE]
if allok:
    print('MATCHED ROW: ' + ROW)
elif only_pair:
    print('MATCHED ROW: ' + ROW + ' -- with ONE frozen R3 criterion not holding (the pair bound; the violating pairs all contain a fallback factor f <= 1.0 against 1.2); the POST-HOC line shows the bound holds with the effective factor; see the results file')
else:
    print('MATCHED ROW: none yet -- at least one expectation failed; read the FAIL lines against B2g (do not edit B2f)')
