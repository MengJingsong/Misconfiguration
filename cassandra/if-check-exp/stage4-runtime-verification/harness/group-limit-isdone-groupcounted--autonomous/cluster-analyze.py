#!/usr/bin/env python3
"""Cluster tier (B3f/B3g) analysis of group-limit-isdone-groupcounted--autonomous.
usage: cluster-analyze.py <cluster-log-dir> [--shakedown]      (dir holds cells.jsonl, g72.trace, heap.csv)
Prints each frozen prediction as an `EXPECTED:` line with PASS/FAIL against the reading, then the matched B3g row. Thresholds are the case file's
B3f as amended 2026-10-27 (A6, A7, A9): 15 percent for 'the same', factor 2 across P for total allocation, sub-pages floor(N/P)+1, control values
1000/10000/50000. Nothing here was tuned to a reading. --shakedown: scale 50 (N_S 10000, N_G 400), instrument check, not a reading.

Byteman calibration: each local sub-page read closes K counters (the replica read and the coordinator-side merge/short-read counters),
so every sub-page appears K times in g72.trace. K is calibrated on the first-trigger query (many-groups, L=1, P=100: one sub-page), and
every other window must hold a multiple of K lines (else the instrument is not trusted)."""
import json, os, re, statistics as st, sys, collections

D = sys.argv[1]
SHAKE = '--shakedown' in sys.argv
SC = 50 if SHAKE else 1
N_S, N_G = 500000 // SC, 20000 // SC
cells = [json.loads(l) for l in open(os.path.join(D, 'cells.jsonl'))]
tr = []
for l in open(os.path.join(D, 'g72.trace'), errors='replace'):
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


first = next(c for c in cells if c['ds'] == 'G' and c['L'] == 1 and c['P'] == 100)
w0 = [t for t in tr if first['t0'] <= t[0] <= first['t1'] + 100]
K = len(w0)
check('instrument: first-trigger query (many-groups L=1 P=100) leaves K Byteman lines, all rows=1 groups=1 done=true', K >= 1 and all(t[1:3] == (1, 1) and t[4] == 'true' for t in w0), f'K={K} {w0}')
print(f'INFO: K = {K} counters closed per sub-page read')


def window(c):
    return [t for t in tr if c['t0'] <= t[0] <= c['t1'] + 100]


def peak(c):
    v = [u for ms, u in heap if c['t0'] - 100 <= ms <= c['t1'] + 100]      # samples every 100 ms; a window shorter than that takes its neighbours
    return max(v) if v else None


def info(c):
    w = window(c)
    mult = len(w) % K == 0
    rows = sum(t[1] for t in w) / K
    groups = sum(t[2] for t in w) / K
    sub = len(w) // K
    mx = max([t[1] for t in w] or [0])
    last = w[-K:] if w else []
    return dict(mult=mult, rows=rows, groups=groups, sub=sub, maxrows=mx, lastdone=(all(t[4] == 'true' for t in last) if last else None),
                earlydone=any(t[4] == 'true' for t in w[:-K]) if w else None)


timed = [c for c in cells if c['ds'] in ('S', 'G', 'C') and not c['warm']]
idle = [abs(c['alloc_bytes']) / c['wall_ms'] for c in cells if c['ds'] == 'idle']
print(f'INFO: idle allocation noise (absolute change of the thread-allocated sum): median {st.median(idle) * 1000:.0f} bytes/s over {len(idle)} windows (max {max(idle) * 1000:.0f})')
check('no client errors in timed queries', all(c['error'] is None for c in timed), [c['error'] for c in timed if c['error']][:2])


def group(ds, p, l):
    return [c for c in timed if c['ds'] == ds and c['P'] == p and str(c['L']) == str(l)]


Ls = ['1', str(100000 // SC), 'none']
res = {}
for p in (10000, 100):
    for l in Ls:
        g = group('S', p, l)
        if not g:
            continue
        infos = [info(c) for c in g]
        res[(p, l)] = dict(alloc=st.mean(c['alloc_bytes'] for c in g), peak=st.mean(peak(c) for c in g), rows=[i['rows'] for i in infos],
                           sub=[i['sub'] for i in infos], maxrows=max(i['maxrows'] for i in infos), alloc_all=[c['alloc_bytes'] for c in g],
                           walls=[c['wall_ms'] for c in g], earlydone=[i['earlydone'] for i in infos], lastdone=[i['lastdone'] for i in infos],
                           mult=[i['mult'] for i in infos], returned=[c['rows_returned'] for c in g])
        r = res[(p, l)]
        check(f'S P={p} L={l}: trace line count is a multiple of K', all(r['mult']), r['mult'])
        check(f'S P={p} L={l}: rows read = {N_S} in every query', all(x == N_S for x in r['rows']), r['rows'])
        check(f'S P={p} L={l}: sub-pages = floor({N_S}/P)+1 = {N_S // p + 1} (A9)', all(x == N_S // p + 1 for x in r['sub']), r['sub'])
        check(f'S P={p} L={l}: rows per sub-page <= P', r['maxrows'] <= p, r['maxrows'])
        check(f'S P={p} L={l}: isDone false in every sub-page but the last', not any(r['earlydone']), r['earlydone'])
        print(f'INFO: S P={p} L={l}: wall ms {r["walls"]} alloc mean {int(r["alloc"])} peak-used mean {int(r["peak"])}')
for p in (10000, 100):
    rr = [res[(p, l)] for l in Ls if (p, l) in res]
    if len(rr) == 3:
        for key in ('alloc', 'peak'):
            vals = [r[key] for r in rr]
            check(f'S P={p}: {key} within 15 percent across L=1 / {Ls[1]} / none', max(vals) <= 1.15 * min(vals), [int(v) for v in vals] + [round(max(vals) / min(vals), 3)])
if (10000, 'none') in res and (100, 'none') in res:
    a10, a100 = res[(10000, 'none')]['alloc'], res[(100, 'none')]['alloc']
    check('S L=none: total allocation across P=100 and P=10000 within a factor of 2 (A9)', max(a10, a100) <= 2 * min(a10, a100), [int(a10), int(a100), round(max(a10, a100) / min(a10, a100), 2)])
    per10 = a10 / (N_S // 10000 + 1); per100 = a100 / (N_S // 100 + 1)
    check('S L=none: allocation per sub-page at P=10000 at least 10 x that at P=100 (per-sub-page batch follows P)', per10 >= 10 * per100, [int(per10), int(per100), round(per10 / per100, 1)])
# drift
dr = [c for c in timed if c['ds'] == 'S' and c['P'] == 10000 and str(c['L']) == 'none']
if dr:
    early = [c['alloc_bytes'] for c in dr[:3]]
    late = [c['alloc_bytes'] for c in dr[-3:]]
    check('drift: L=none P=10000 allocation at start and end within 15 percent', max(st.mean(early), st.mean(late)) <= 1.15 * min(st.mean(early), st.mean(late)), [int(st.mean(early)), int(st.mean(late))])
# many-groups
mech = []
for p in (100, 10000):
    for l in ('1', '100', str(5000 // SC), 'none'):
        g = group('G', p, l)
        if not g:
            continue
        infos = [info(c) for c in g]
        rows = [i['rows'] for i in infos]
        li = N_G if l == 'none' else int(l)
        exp = (li, li + 1) if li < N_G else (N_G,)
        ok = all(x in exp for x in rows) and all(i['mult'] for i in infos)
        check(f'G P={p} L={l}: rows read = {"L or L+1" if li < N_G else N_G}', ok, rows)
        check(f'G P={p} L={l}: client rows returned = {li}', all(c['rows_returned'] == li for c in g), [c['rows_returned'] for c in g])
        if li < N_G:
            okd = all(i['lastdone'] for i in infos) and all(i['groups'] == li for i in infos)
            check(f'G P={p} L={l}: groups = L and isDone true in the last sub-page (disallow branch fired)', okd, [(i['groups'], i['lastdone']) for i in infos])
            mech.append(ok and okd)
        else:
            mech.append(ok)
# control
cres = {}
for l in (1000 // SC, 10000 // SC, 50000 // SC):
    g = [c for c in timed if c['ds'] == 'C' and str(c['L']) == str(l)]
    if g:
        cres[l] = (st.mean(c['alloc_bytes'] for c in g), st.mean(peak(c) for c in g), [c['rows_returned'] for c in g])
        check(f'control L={l}: rows returned = L', all(x == l for x in cres[l][2]), cres[l][2])
        print(f'INFO: control L={l}: alloc mean {int(cres[l][0])} peak-used mean {int(cres[l][1])}')
ks = sorted(cres)
ctrl_moved = len(ks) == 3 and cres[ks[2]][0] >= 10 * cres[ks[0]][0] and cres[ks[1]][0] > cres[ks[0]][0]
check('control moved: allocation at L=50000 >= 10 x allocation at L=1000, and L=10000 above L=1000', ctrl_moved, {k: int(v[0]) for k, v in cres.items()})

# B3g
def flat(key):
    return all(max(res[(p, l)][key] for l in Ls) <= 1.15 * min(res[(p, l)][key] for l in Ls) for p in (10000, 100))
rows_all = all(all(x == N_S for x in res[(p, l)]['rows']) for p in (10000, 100) for l in Ls)
conf_flat = flat('alloc') and flat('peak') and rows_all
early_stop = any(st.mean(res[(p, '1')]['rows']) < 0.9 * N_S or res[(p, '1')]['alloc'] < 0.85 * res[(p, 'none')]['alloc'] for p in (10000, 100))
follows = any(max(res[(p, l)]['alloc'] for l in Ls) > 1.15 * min(res[(p, l)]['alloc'] for l in Ls) or max(res[(p, l)]['peak'] for l in Ls) > 1.15 * min(res[(p, l)]['peak'] for l in Ls) for p in (10000, 100))
pmoves = (10000, 'none') in res and (100, 'none') in res and (res[(10000, 'none')]['alloc'] / (N_S // 10000 + 1)) >= 10 * (res[(100, 'none')]['alloc'] / (N_S // 100 + 1))
print()
print(f'B3g facts: flat_rows_alloc_peak={conf_flat} early_stop={early_stop} follows_L={follows} P_moves_batch={pmoves} many_groups_mechanism={all(mech) and bool(mech)} control_moved={ctrl_moved}')
if SHAKE:
    print('SHAKEDOWN: instrument check only, not a reading.')
if not ctrl_moved:
    row = 'Positive control flat -> control did not move; result not confirmed (B3g row 4)'
elif early_stop:
    row = 'L=1 reads far fewer rows or allocates far less than L=none -> Claim refuted (B3g row 2)'
elif follows and not conf_flat:
    row = 'Peak heap / allocation follows L -> Claim refuted (B3g row 3)'
elif conf_flat and pmoves and mech and all(mech):
    row = 'Heap peak, allocation and rows read flat across L at fixed P while P moves the per-sub-page batch; many-groups limit fires -> Claim confirmed (B3g row 1)'
elif not (mech and all(mech)):
    row = 'Many-groups variant did not reach the limit as predicted -> Not confirmed for that cell (B3g row 5)'
else:
    row = 'No B3g row matches -> Not confirmed (no matching row)'
print('MATCHED ROW:', row)
print('FAILED EXPECTATIONS:', bad if bad else 'none')
