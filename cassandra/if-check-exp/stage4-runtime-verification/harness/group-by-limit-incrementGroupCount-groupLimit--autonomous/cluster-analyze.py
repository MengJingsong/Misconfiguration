#!/usr/bin/env python3
"""Cluster tier (B3f/B3g) analysis of group-by-limit-incrementGroupCount-groupLimit--autonomous.
usage: cluster-analyze.py <cluster-log-dir> [--shakedown]      (dir holds cells.jsonl, l79.trace, heap.csv)
Prints each frozen prediction as an `EXPECTED:` line with PASS/FAIL, then the matched B3g row. Thresholds are the case file's B3f/B3g as amended
2026-10-27 (A9, A12, A13, A14); nothing here was tuned to a reading. --shakedown: scale 50 (N_S 20000, ks.g 600 x 30), instrument check only.
Byteman calibration: each local sub-page read closes K counters, so every sub-page appears K times in l79.trace; K is calibrated on the
first-trigger query (ds FT: one sub-page) and every other window must hold a multiple of K lines (else the instrument is not trusted)."""
import json, os, re, statistics as st, sys

D = sys.argv[1]
SHAKE = '--shakedown' in sys.argv
SC = 50 if SHAKE else 1
N_S = 1000000 // SC
N_G = 3000 // max(1, SC // 10)
R_G = 300 if SC == 1 else 30
G_BIG = str(100000 // SC)
cells = [json.loads(l) for l in open(os.path.join(D, 'cells.jsonl'))]
tr = []
for l in open(os.path.join(D, 'l79.trace'), errors='replace'):
    m = re.search(r'GB ms=(\d+) rows=(\d+) groups=(\d+) unfinished=(\w+) done=(\w+)', l)
    if m:
        tr.append((int(m[1]), int(m[2]), int(m[3]), m[4], m[5]))
heap = []
for l in open(os.path.join(D, 'heap.csv')):
    p = l.strip().split(',')
    if len(p) == 3 and p[0].isdigit():
        heap.append((int(p[0]), int(p[1])))
bad = []


def check(name, ok, detail):
    print(f'EXPECTED: {name}: {"PASS" if ok else "FAIL"} ({detail})')
    if not ok:
        bad.append(name)
    return ok


ft = next(c for c in cells if c['ds'] == 'FT')
w0 = [t for t in tr if ft['t0'] <= t[0] <= ft['t1'] + 100]
K = len(w0)
check(f'instrument: first-trigger query (ks.g GROUP BY pk LIMIT 1, P=10000) leaves K Byteman lines, all rows={R_G} groups=1 done=true', K >= 1 and all(t[1:3] == (R_G, 1) and t[4] == 'true' for t in w0), f'K={K} {w0}')
print(f'INFO: K = {K} counters closed per sub-page read')


def window(c):
    return [t for t in tr if c['t0'] <= t[0] <= c['t1'] + 100]


def peak(c):
    v = [u for ms, u in heap if c['t0'] - 100 <= ms <= c['t1'] + 100]
    return max(v) if v else None


def info(c):
    w = window(c)
    return dict(mult=len(w) % K == 0, rows=sum(t[1] for t in w) / K, groups=sum(t[2] for t in w) / K, sub=len(w) // K,
                maxrows=max([t[1] for t in w] or [0]), lastdone=(all(t[4] == 'true' for t in w[-K:]) if w else None),
                earlydone=any(t[4] == 'true' for t in w[:-K]) if w else None)


timed = [c for c in cells if c['ds'] in ('T', 'G', 'C') and not c['warm']]
idle = [abs(c['alloc_bytes']) / c['wall_ms'] for c in cells if c['ds'] == 'idle']
print(f'INFO: idle allocation noise median {st.median(idle) * 1000:.0f} bytes/s over {len(idle)} windows (max {max(idle) * 1000:.0f})')
check('no client errors in timed queries', all(c['error'] is None for c in timed), [c['error'] for c in timed if c['error']][:2])


def group(ds, p, l):
    return [c for c in timed if c['ds'] == ds and c['P'] == p and str(c['L']) == str(l)]


def spread(vals):
    return max(vals) / min(vals)


def rising(vals):          # vals ordered by g
    return vals[-1] > 1.10 * vals[0] and all(vals[i] < vals[i + 1] for i in range(len(vals) - 1))


Ls = ['1', '100', G_BIG]
res = {}
for p in (10000, 100):
    for l in Ls:
        g = group('T', p, l)
        if not g:
            continue
        infos = [info(c) for c in g]
        res[(p, l)] = dict(alloc=st.mean(c['alloc_bytes'] for c in g), peak=st.mean(peak(c) for c in g), rchar=st.mean(c['rchar_delta'] for c in g),
                           wall=st.mean(c['wall_ms'] for c in g), rows=[i['rows'] for i in infos], sub=[i['sub'] for i in infos],
                           maxrows=max(i['maxrows'] for i in infos), earlydone=[i['earlydone'] for i in infos], mult=[i['mult'] for i in infos])
        r = res[(p, l)]
        check(f'T P={p} g={l}: trace line count is a multiple of K', all(r['mult']), r['mult'])
        check(f'T P={p} g={l}: rows read = {N_S} in every query', all(x == N_S for x in r['rows']), r['rows'])
        check(f'T P={p} g={l}: sub-pages = floor({N_S}/P)+1 = {N_S // p + 1} (A13)', all(x == N_S // p + 1 for x in r['sub']), r['sub'])
        check(f'T P={p} g={l}: rows per sub-page <= P', r['maxrows'] <= p, r['maxrows'])
        check(f'T P={p} g={l}: isDone false in every sub-page but the last', not any(r['earlydone']), r['earlydone'])
        print(f'INFO: T P={p} g={l}: wall ms mean {int(r["wall"])} alloc {int(r["alloc"])} rchar {int(r["rchar"])} peak-used {int(r["peak"])}')
    rr = [res[(p, l)] for l in Ls if (p, l) in res]
    if len(rr) == 3:
        for key, band in (('alloc', 1.15), ('rchar', 1.15), ('peak', 1.25)):
            v = [r[key] for r in rr]
            ok = spread(v) <= band and (not rising(v) if key == 'peak' else True)
            check(f'T P={p}: {key} within {int((band - 1) * 100)} percent across g = {", ".join(Ls)}' + (' and no monotone rise > 10 percent' if key == 'peak' else ''), ok, [int(x) for x in v] + [round(spread(v), 3)])
        check(f'T P={p}: wall time of g=1 at least 80 percent of g={G_BIG}', rr[0]['wall'] >= 0.8 * rr[2]['wall'], [int(rr[0]['wall']), int(rr[2]['wall'])])
dr = [c for c in timed if c['ds'] == 'T' and c['P'] == 10000 and str(c['L']) == 'none']
if dr:
    early, late = [c['alloc_bytes'] for c in dr[:3]], [c['alloc_bytes'] for c in dr[-3:]]
    check('drift: g=none P=10000 allocation at start and end within 15 percent', spread([st.mean(early), st.mean(late)]) <= 1.15, [int(st.mean(early)), int(st.mean(late))])
# small-group table ks.g
gres = {}
for p in (10000, 100):
    for l in Ls:
        g = group('G', p, l)
        if not g:
            continue
        infos = [info(c) for c in g]
        li = min(int(l), N_G)
        exp = (R_G * li, R_G * li + 1)
        rows = [i['rows'] for i in infos]
        check(f'G P={p} g={l}: trace line count multiple of K', all(i['mult'] for i in infos), [i['mult'] for i in infos])
        check(f'G P={p} g={l}: rows read in [{exp[0]}, {exp[1]}] = {R_G}*min(g, {N_G}) (A13)', all(exp[0] <= x <= exp[1] for x in rows), rows)
        check(f'G P={p} g={l}: client rows returned = {li}', all(c['rows_returned'] == li for c in g), [c['rows_returned'] for c in g])
        if int(l) < N_G:
            check(f'G P={p} g={l}: groups = g and isDone true in the last sub-page (disallow branch fired)', all(i['lastdone'] for i in infos) and all(i['groups'] == li for i in infos), [(i['groups'], i['lastdone']) for i in infos])
        gres[(p, l)] = dict(rchar=st.mean(c['rchar_delta'] for c in g), peak=st.mean(peak(c) for c in g), wall=st.mean(c['wall_ms'] for c in g), alloc=st.mean(c['alloc_bytes'] for c in g))
        print(f'INFO: G P={p} g={l}: wall ms {int(gres[(p, l)]["wall"])} alloc {int(gres[(p, l)]["alloc"])} rchar {int(gres[(p, l)]["rchar"])} peak-used {int(gres[(p, l)]["peak"])}')
    if all((p, l) in gres for l in Ls):
        a, b, c3 = (gres[(p, l)]['rchar'] for l in Ls)
        check(f'G P={p}: rchar at g=100 >= 20 x g=1 and g={G_BIG} >= 10 x g=100 (A13)', b >= 20 * a and c3 >= 10 * b, [int(a), int(b), int(c3)])
        long_ = [gres[(p, l)]['peak'] for l in Ls if gres[(p, l)]['wall'] >= 2000]
        if len(long_) >= 2:
            check(f'G P={p}: peak used within 25 percent across the g whose queries last >= 2 s (A13)', spread(long_) <= 1.25, [int(x) for x in long_] + [round(spread(long_), 3)])
        else:
            print(f'INFO: G P={p}: fewer than two cells last >= 2 s; peak not compared')
# control
cres = {}
for l in (1000 // SC, 10000 // SC, 100000 // SC):
    g = [c for c in timed if c['ds'] == 'C' and str(c['L']) == str(l)]
    if g:
        cres[l] = (st.mean(c['alloc_bytes'] for c in g), st.mean(peak(c) for c in g), [c['rows_returned'] for c in g], st.mean(c['rchar_delta'] for c in g))
        check(f'control n={l}: rows returned = n', all(x == l for x in cres[l][2]), cres[l][2])
        print(f'INFO: control n={l}: alloc {int(cres[l][0])} peak-used {int(cres[l][1])} rchar {int(cres[l][3])}')
ks = sorted(cres)
ctrl_moved = len(ks) == 3 and all(all(x == k for x in cres[k][2]) for k in ks) and cres[ks[2]][0] >= 10 * cres[ks[0]][0]
check(f'control moved (A13): rows == n and allocation at n={ks[-1] if ks else "?"} >= 10 x allocation at n={ks[0] if ks else "?"}', ctrl_moved, {k: int(v[0]) for k, v in cres.items()})

# B3g facts
def flat(key, band):
    return all(spread([res[(p, l)][key] for l in Ls]) <= band for p in (10000, 100))
rows_all = all(all(x == N_S for x in res[(p, l)]['rows']) for p in (10000, 100) for l in Ls)
conf_flat = flat('alloc', 1.15) and flat('rchar', 1.15) and flat('peak', 1.25) and rows_all and \
    not any(rising([res[(p, l)]['peak'] for l in Ls]) for p in (10000, 100))
early_stop = any(st.mean(res[(p, '1')]['rows']) < 0.9 * N_S or res[(p, '1')]['rchar'] < 0.85 * res[(p, G_BIG)]['rchar'] for p in (10000, 100))
follows = any(rising([res[(p, l)][k] for l in Ls]) for p in (10000, 100) for k in ('alloc', 'peak', 'rchar'))
gtrack = all((p, l) in gres for p in (10000, 100) for l in Ls) and all(gres[(p, Ls[1])]['rchar'] >= 20 * gres[(p, Ls[0])]['rchar'] for p in (10000, 100))
fired = all(info(c)['lastdone'] for c in timed if c['ds'] == 'G' and int(str(c['L'])) < N_G)
print()
print(f'B3g facts: flat_rows_alloc_rchar_peak={conf_flat} early_stop={early_stop} rises_with_g={follows} small_group_reads_track_g={gtrack} limit_fired_in_small_groups={fired} control_moved={ctrl_moved}')
if SHAKE:
    print('SHAKEDOWN: instrument check only, not a reading.')
if not ctrl_moved:
    row = 'Positive control did not move -> Not confirmed (B3g last row)'
elif early_stop:
    row = 'g=1 on the huge table reads far less -> claim wrong (B3g row 3)'
elif follows:
    row = 'Max heap / bytes read rise with g -> claim refuted (B3g row 4)'
elif conf_flat and gtrack and fired:
    row = 'Huge table: bytes read, allocation and heap flat across g; small-group table: bytes read grow with g, heap flat -> claim confirmed (B3g rows 1 and 2)'
else:
    row = 'No B3g row matches -> Not confirmed (no matching row)'
print('MATCHED ROW:', row)
print('FAILED EXPECTATIONS:', bad if bad else 'none')
