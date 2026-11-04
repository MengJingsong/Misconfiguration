#!/usr/bin/env python3
"""Cluster-tier analyzer for the three range_tombstone_list_growth_factor autonomous cases (CASE from cells.jsonl).
usage: cluster-analyze.py <cluster-log-dir>
Reads cells.jsonl, series.csv, heap.txt, growth-trace.txt of every cell; prints EXPECTED: lines (the B3f predictions of that file with
the audit's R3 and R8 definitions), OBSERVED: lines, and a MATCHED ROW line (B3g); writes readings.csv next to cells.jsonl."""
import csv, json, math, os, re, sys, collections

D = sys.argv[1]
recs = [json.loads(l) for l in open(D + '/cells.jsonl')]
CASE = recs[0]['case']
cells = collections.OrderedDict()
lifes = {}
sysl = {}
for r in recs:
    if r['kind'] == 'life': lifes[r['life']] = r
    elif r['kind'] == 'syslog': sysl[r['life']] = r
    else:
        c = cells.setdefault(r['cell'], dict(cps=[], base=None, end=None, life=r['life']))
        if r['kind'] == 'base': c['base'] = r
        elif r['kind'] == 'cp': c['cps'].append(r)
        elif r['kind'] == 'end': c['end'] = r
res, failed = [], []
MiB = 1 << 20


def check(name, ok, detail=''):
    res.append(ok)
    if not ok: failed.append(name)
    print(f'EXPECTED: {name}: {"PASS" if ok else "FAIL"}' + (f' ({detail})' if detail else ''))


def obs(m): print('OBSERVED: ' + m)
def I(x): return int(float(x))
def nextcap(c, f):
    n = math.ceil(c * f)
    return n if n > c else (c * 3) // 2 + 1


def cell_factor(c):
    return float(c['base']['factor_read'])      # run_cell reads it back after the runtime change of cell J


def hv(h, k, i): return h.get(k, [0, 0])[i]


def series(label):
    out = []
    for l in open(f'{D}/{label}/series.csv'):
        t = l.strip().split(',')
        if len(t) == 3 and t[1].lstrip('-').isdigit():
            out.append((int(t[0]), int(t[1]), int(t[2])))
    return out


def peak_heap(label):
    best = 0
    for l in open(f'{D}/{label}/heap.txt'):
        t = l.split()
        if len(t) == 4 and t[0].isdigit(): best = max(best, int(t[1]) + int(t[2]) + int(t[3]))
    return best


rows = []
for lab, c in cells.items():
    for cp in c['cps']:
        h = cp['histo']
        rows.append(dict(cell=lab, life=c['life'], k=cp['k'], tombstones=cp['tombstones'], counter=I(cp['metrics']['counter']), columns=I(cp['metrics']['columns']),
                         switch=I(cp['metrics']['switch']), CB_count=hv(h, 'ClusteringBound[]', 0), CB_bytes=hv(h, 'ClusteringBound[]', 1),
                         BCB_count=hv(h, 'BufferClusteringBound', 0), BCB_bytes=hv(h, 'BufferClusteringBound', 1), long_bytes=hv(h, 'long[]', 1),
                         int_bytes=hv(h, 'int[]', 1), total_bytes=hv(h, 'total', 1), rss_anon=cp['rss_anon'], factor=cp['factor_read']))
with open(D + '/readings.csv', 'w') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)


def last(lab): return [r for r in rows if r['cell'] == lab][-1]
def basehist(lab, k, i): return hv(cells[lab]['base']['histo'], k, i)


main = [l for l, c in cells.items() if not c['base']['control'] and not c['base'].get('control_table') and c['base']['load'] != 'ins']
ctrl = [l for l, c in cells.items() if c['base']['control']]
print(f'cells: main {main}; controls {ctrl}')

bad = [(l, c['base']['factor_set'], c['base']['factor_read']) for l, c in cells.items()
       if abs(float(c['base']['factor_read']) - (c['base']['factor_set'])) > 1e-9 and not l.startswith('J')]
jb = [(l, c['base']['factor_read']) for l, c in cells.items() if l.startswith('J') and abs(float(c['base']['factor_read']) - 5.0) > 1e-9]
check('factor read back over JMX equals the factor set (yaml or JMX; cell J: 5.0 after the runtime change) before every cell', not bad and not jb, f'{len(cells)} cells; mismatches {bad + jb}')
badw = [(l, c['cps'][-1]['writes_ok_total'], c['cps'][-1]['write_errors_total']) for l, c in cells.items()
        if c['cps'][-1]['write_errors_total'] != 0 or c['cps'][-1]['writes_ok_total'] != c['cps'][-1]['tombstones']]
check('every write was acknowledged: ok == tombstones (or rows) written, errors == 0, in every cell (no rejection at any f)', not badw, f'{sum(c["cps"][-1]["writes_ok_total"] for c in cells.values())} acknowledged; bad {badw}')
badf = [(l, [cp['metrics']['switch'] for cp in c['cps']], c['base']['metrics']['switch']) for l, c in cells.items()
        if l in main and any(cp['metrics']['switch'] != c['base']['metrics']['switch'] for cp in c['cps'])]
check('main cells are flush-free: MemtableSwitchCount unchanged from the start of the cell to its last checkpoint (R3)', not badf, f'bad {badf}')
errs = {k: v['error_lines'] for k, v in sysl.items()}
check('no ERROR or OutOfMemoryError line in system.log of any lifetime', all(v['error_lines'] == 0 and not v['oom'] for v in sysl.values()), str(errs))
bt = []
for l in main:
    c = cells[l]
    for cp in c['cps']:
        bcb = hv(cp['histo'], 'BufferClusteringBound', 0) - basehist(l, 'BufferClusteringBound', 0)
        if abs(bcb - 2 * cp['tombstones']) > 0.01 * 2 * cp['tombstones'] + 10 or abs(I(cp['metrics']['columns']) - cp['tombstones']) > 0.005 * cp['tombstones'] + 10:
            bt.append((l, cp['k'], bcb, 2 * cp['tombstones'], cp['metrics']['columns']))
check('the tombstones are live in the memtable: BufferClusteringBound count delta == 2 x tombstones (1 %) and MemtableColumnsCount == tombstones, at every checkpoint of every main cell', not bt, f'bad {bt[:4]}')
tbad, tcount, tlines = [], 0, 0
for l, c in cells.items():
    if c['base']['load'] == 'ins': continue
    f = cell_factor(c)
    for ln in open(f'{D}/{l}/growth-trace.txt'):
        m = re.match(r'grow n=(\d+) index=(\d+) cap=(\d+) newLength=(\d+)', ln)
        g = re.match(r'growToFree n=(\d+) cap=(\d+) size=(\d+) factor=([0-9.]+)', ln)
        if m:
            cap, nl = int(m.group(3)), int(m.group(4)); tlines += 1
            if cap >= 20:
                tcount += 1
                if nl != nextcap(cap, f): tbad.append((l, cap, nl, nextcap(cap, f)))
        elif g:
            if abs(float(g.group(4)) - f) > 1e-9: tbad.append((l, 'factor', g.group(4), f))
check('Byteman trace on the live node: every sampled grow(i, newLength) (cap >= 20) has newLength == iterated expression at the cell factor, and every sampled growToFree line reads the cell factor', not tbad and tcount > 0, f'{tcount} grow lines checked ({tlines} sampled); bad {tbad[:3]}')


def grows(l):
    rs = [r for r in rows if r['cell'] == l]
    inc = all(rs[i + 1]['counter'] > rs[i]['counter'] for i in range(len(rs) - 1))
    ratio = rs[-1]['counter'] / rs[0]['counter']; tr = rs[-1]['tombstones'] / rs[0]['tombstones']
    return inc, ratio, tr, 0.6 * tr <= ratio <= 1.4 * tr
bg = []
for l in main:
    inc, ratio, tr, ok = grows(l)
    if not (inc and ok): bg.append((l, round(ratio, 2), tr))
check('counter grows with N at every main cell: rises at every checkpoint and last/first within [0.6, 1.4] x (tombstones last/first) (R3)', not bg, f'{len(main)} cells; bad {bg}')
bp = []
for l in main:
    rs = [r for r in rows if r['cell'] == l]
    a, b = rs[-2], rs[-1]
    if b['tombstones'] >= 1.5 * a['tombstones'] and abs(b['counter'] / a['counter'] - 1) < 0.05: bp.append((l, a['counter'], b['counter']))
check('no plateau at any factor: NOT (last two checkpoints differ by less than 5 % while the tombstone counts differ by at least 1.5x) (R3)', not bp, f'bad {bp}')

shapes = collections.defaultdict(list)
for l in main:
    c = cells[l]
    shapes[(c['base']['P'], c['cps'][-1]['tombstones'])].append(l)
badpair, npairs = [], 0
for sh, labs in shapes.items():
    for i in range(len(labs)):
        for j in range(i + 1, len(labs)):
            a, b = labs[i], labs[j]
            fa, fb = cell_factor(cells[a]), cell_factor(cells[b])
            ra, rb = last(a), last(b)
            npairs += 1
            d = abs(ra['counter'] - rb['counter']); bound = 28 * abs(fa - fb) * ra['tombstones'] + MiB
            if d > bound: badpair.append((a, b, d, round(bound)))
check('|counter(f_a) - counter(f_b)| <= 28 B x |f_a - f_b| x T + 1 MiB for every pair of main cells of the same shape at the last checkpoint (R3)', not badpair, f'{npairs} pairs; bad {badpair[:4]}')
badord = []
for sh, labs in shapes.items():
    byf = collections.defaultdict(list)
    for l in labs: byf[cell_factor(cells[l])].append(last(l)['CB_bytes'])
    fs = sorted(byf); mean_ = [sum(byf[f]) / len(byf[f]) for f in fs]
    if any(mean_[i + 1] < mean_[i] for i in range(len(mean_) - 1)): badord.append((sh, fs, mean_))
check('live ClusteringBound[] bytes after the last checkpoint are ordered like the factor (non-decreasing in f) for every shape (R3)', not badord, f'bad {badord}')

for l in main:
    r = last(l)
    slots = (r['CB_bytes'] - basehist(l, 'ClusteringBound[]', 1) - 16 * (r['CB_count'] - basehist(l, 'ClusteringBound[]', 0))) / 8
    live = (r['BCB_count'] - basehist(l, 'BufferClusteringBound', 0)) / 2
    obs(f'{l} f={cell_factor(cells[l])}: T={r["tombstones"]} counter {r["counter"]} ({r["counter"] / r["tombstones"]:.0f} B/tombstone); live tombstones {live:.0f}, allocated slots {slots:.0f} (slots/live {slots / max(live, 1):.3f}); CB[] bytes {r["CB_bytes"]}, BCB bytes {r["BCB_bytes"]}, long[] {r["long_bytes"]}, int[] {r["int_bytes"]}, histogram total {r["total_bytes"]}; peak EU+OU+SU in the run {peak_heap(l) // MiB} MiB')


def cell_counter_series_max(l): return max(v for _, v, _ in series(l))
def mean(xs): return sum(xs) / len(xs)

if CASE == 'A':
    out = {}
    for sh in ('M', 'S1', 'S100'):
        a = [last(l)['counter'] for l in main if l.startswith(sh + '-5.0')]; b = [last(l)['counter'] for l in main if l.startswith(sh + '-1.2')]
        T = last([l for l in main if l.startswith(sh + '-5.0')][0])['tombstones']
        out[sh] = (mean(a) - mean(b), T, mean(b))
        obs(f'shape {sh}: counter(5.0) - counter(1.2) = {out[sh][0]:.0f} B for T={T} ({out[sh][0] / T:.1f} B/tombstone), {100 * out[sh][0] / out[sh][2]:.1f} % of counter(1.2)')
    d1, T1, c1 = out['S1']
    check('S1 (1 x 50,000): 0 < counter(5.0) - counter(1.2) <= (5.0 - 1.2) x 50,000 x 28 B = 5.32 MB (about 4 MB, B3f)', 0 < d1 <= 3.8 * 50000 * 28, f'{d1:.0f} B')
    per = [out[s][0] / out[s][1] for s in out]
    check('per-tombstone difference of M, S1 and S100 is equal within [0.5, 2]x (R8: replaces "smaller per tombstone")', min(per) > 0 and max(per) / min(per) <= 2, str([round(p, 1) for p in per]))
    check('the difference is small compared with the bound objects: |counter(5.0) - counter(1.2)| < 25 % of counter(1.2) in every shape (R8)', all(abs(out[s][0]) / out[s][2] < 0.25 for s in out), str({s: round(100 * out[s][0] / out[s][2], 1) for s in out}))
    for cl in ctrl:
        sw = [cp['metrics']['switch'] for cp in cells[cl]['cps']]; st = cells[cl]['base']['metrics']['switch']; mx = cell_counter_series_max(cl)
        check(f'positive control {cl}: the memtable flushes (switch count above its start) and the counter series stays <= 1.5 x 128 MiB (R8)', int(sw[-1]) > int(st) and mx <= 1.5 * 128 * MiB, f'switch {st}->{sw}; series max {mx / MiB:.1f} MiB')
        obs(f'control {cl}: counter at the last checkpoint {last(cl)["counter"] / MiB:.1f} MiB, series peak {mx / MiB:.1f} MiB; main M-1.2 last counter {last([l for l in main if l.startswith("M-1.2")][0])["counter"] / MiB:.1f} MiB')
    reps = collections.defaultdict(list)
    for l in main:
        if l.startswith('M-'): reps[cell_factor(cells[l])].append(last(l)['counter'])
    obs('repeat stability (B3h), final counters per factor: ' + str(dict(reps)))
    for l in [x for x in cells if x.startswith('J')]:
        mm = [last(x)['counter'] for x in main if x.startswith('M-5.0')]
        obs(f'cell J (yaml 1.2, runtime change to 5.0): final counter {last(l)["counter"]} vs M-5.0 {mm}; factor read back {cells[l]["base"]["factor_read"]}')

if CASE == 'G':
    m = {cell_factor(cells[l]): l for l in main}
    r12, r15, r50 = last(m[1.2]), last(m[1.5]), last(m[5.0])
    ratio = r50['CB_bytes'] / r12['CB_bytes']
    check('ClusteringBound[] bytes: f=5.0 / f=1.2 in [2.5, 4.5] and ordered like f (R8: "up to 3 to 4 times")', 2.5 <= ratio <= 4.5 and r12['CB_bytes'] <= r15['CB_bytes'] <= r50['CB_bytes'], f'ratio {ratio:.2f}; {r12["CB_bytes"]} <= {r15["CB_bytes"]} <= {r50["CB_bytes"]}')
    bc = [last(m[f])['BCB_count'] - basehist(m[f], 'BufferClusteringBound', 0) for f in (1.2, 1.5, 5.0)]
    check('bound objects roughly equal across cells: live BufferClusteringBound counts differ by <= 2 % (R8)', (max(bc) - min(bc)) / max(bc) <= 0.02, str(bc))
    dd = (r50['counter'] - r12['counter']) / r12['counter']
    check('total memtable counter difference is a modest percentage: |counter(5.0) - counter(1.2)| < 50 % of counter(1.2) (R8)', abs(dd) < 0.5, f'{100 * dd:.1f} %; {r50["counter"] - r12["counter"]} B')
    obs(f'histogram total heap f=5.0 minus f=1.2: {r50["total_bytes"] - r12["total_bytes"]} B; CB[]+long[]+int[] difference {sum(r50[k] - r12[k] for k in ("CB_bytes", "long_bytes", "int_bytes"))} B')
    for cl in ctrl:
        sw = [cp['metrics']['switch'] for cp in cells[cl]['cps']]; mx = cell_counter_series_max(cl)
        check(f'positive control {cl}: all rows acknowledged, MemtableSwitchCount ends >= 3 and the counter series max is within [0.25, 1.0] x 64 MiB (R8)', int(sw[-1]) >= 3 and 0.25 * 64 * MiB <= mx <= 64 * MiB, f'switch {sw}; series max {mx / MiB:.1f} MiB')

if CASE == 'N':
    byf = collections.defaultdict(list)
    for l in main: byf[cell_factor(cells[l])].append(last(l))
    diff = mean([r['counter'] for r in byf[5.0]]) - mean([r['counter'] for r in byf[1.2]])
    check('counter(5.0) - counter(1.2) (means of the repeats) is on the order of 76 MB: within [38, 152] MB (R8)', 38e6 <= diff <= 152e6, f'{diff / 1e6:.1f} MB')
    lg = {f: mean([r['long_bytes'] for r in v]) for f, v in byf.items()}; cb = {f: mean([r['CB_bytes'] for r in v]) for f, v in byf.items()}
    fs = sorted(lg)
    extra = (cb[5.0] - cb[1.2]) / 8
    check('long[] bytes are ordered like f, and long[](5.0) - long[](1.2) in [0.5, 2] x 8 B x extra slots (R8)', all(lg[fs[i]] <= lg[fs[i + 1]] for i in range(len(fs) - 1)) and 0.5 * 8 * extra <= lg[5.0] - lg[1.2] <= 2 * 8 * extra, f'long[] {lg}; extra slots {extra:.0f}; diff {lg[5.0] - lg[1.2]:.0f}')
    for l in [x for x, c in cells.items() if c['base']['load'] == 'ins']:
        d = last(l)['CB_bytes'] - basehist(l, 'ClusteringBound[]', 1)
        check(f'plain-insert table {l}: live ClusteringBound[] bytes exceed the cell baseline by < 64 KiB (R8)', d < 64 * 1024, f'{d} B')
    for cl in ctrl:
        sw = [cp['metrics']['switch'] for cp in cells[cl]['cps']]; st = cells[cl]['base']['metrics']['switch']; mx = cell_counter_series_max(cl)
        check(f'positive control {cl}: MemtableSwitchCount rises above its start (main cells: no flush) and the counter series max <= 256 MiB (R8)', int(sw[-1]) > int(st) and mx <= 256 * MiB and not badf, f'switch {st}->{sw}; series max {mx / MiB:.1f} MiB; main cells flush-free: {not badf}')

ok = all(res)
print(f'SUMMARY: {sum(res)}/{len(res)} expectations hold')
if ok:
    print('MATCHED ROW: B3g row 1 (usage rises with N at all factors; the factor changes it only within the slack bound; no cap tied to f) with the positive control moving (flush-bound memtable) while the factor stays flat -- Confirmed, does not cap')
else:
    print('MATCHED ROW: none yet -- failed: ' + ' | '.join(failed)[:900])
