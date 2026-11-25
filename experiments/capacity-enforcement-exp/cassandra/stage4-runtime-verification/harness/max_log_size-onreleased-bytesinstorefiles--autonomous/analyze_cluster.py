#!/usr/bin/env python3
"""o72 cluster-tier analysis: B3f predictions read with the M8 rules.
Usage: analyze_cluster.py <results-dir>
Needs sample-<tag>.txt (epoch n rolled total alloc), archiver-<tag>.txt (debug.log lines of DeletingArchiver for
that run's path), cluster-driver.log (stress start/end epochs), conf-<tag>.txt, scale.txt."""
import re, sys, os, statistics, datetime
R = sys.argv[1]
MiB = 1 << 20
out = []
def p(s=''):
    out.append(s); print(s)
drv = open(os.path.join(R, 'cluster-driver.log'), errors='replace').read()
scale = open(os.path.join(R, 'scale.txt')).read()
p('scale.txt: ' + scale.replace('\n', '; '))
def ts(line):
    m = re.search(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d),(\d{3})', line)
    d = datetime.datetime.strptime(m.group(1), '%Y-%m-%dT%H:%M:%S').replace(tzinfo=datetime.timezone.utc)
    return d.timestamp() + int(m.group(2)) / 1000
res = {}
for tag in ('C1', 'K1', 'K2', 'C2'):
    sp = os.path.join(R, f'sample-{tag}.txt')
    if not os.path.exists(sp) or not os.path.exists(os.path.join(R, f'archiver-{tag}.txt')):
        p(f'-- {tag}: not run'); continue
    S = [list(map(int, l.split())) for l in open(sp) if len(l.split()) == 5]
    A = open(os.path.join(R, f'archiver-{tag}.txt'), errors='replace').read().splitlines()
    rel = [(ts(l), int(re.search(r'rolled file size (\d+)', l).group(1))) for l in A if 'rolled file size' in l]
    dele = [(ts(l), int(re.search(r'store file size: (\d+)', l).group(1)), int(re.search(r'bytes in store files: (\d+)', l).group(1)),
             int(re.search(r'max log size: (\d+)', l).group(1))) for l in A if 'Deleted chronicle store file' in l]
    fails = [l for l in A if 'Failed to delete' in l]
    conf = open(os.path.join(R, f'conf-{tag}.txt')).read()
    M = int(re.search(r'max_log_size\s+(\d+)', conf).group(1))
    arch = re.search(r'^archive_command[ \t]*(.*)$', conf, re.M).group(1).strip()
    st = int(re.search(rf'stress start {tag} (\d+)', drv).group(1)) / 1000
    en = int(re.search(rf'stress rc=\d+ end {tag} (\d+)', drv).group(1)) / 1000
    fp = statistics.median([x for _, x in rel]) if rel else None
    if fp is None and 'C1' in res:  # C2 uses ExternalArchiver: no DeletingArchiver DEBUG lines; use C1's F'
        fp = res['C1']['fp']; p(f'   ({tag}: no release lines; F\' taken from C1)')
    r_ = [s[2] for s in S]
    nseg = S[-1][1] if S else 0
    p(f'-- {tag}: M={M} archive_command="{arch}" stress {en - st:.0f} s; samples={len(S)}; releases={len(rel)} F\'(median rolled file size)={fp} ({(fp or 0) / MiB:.1f} MiB); '
      f'release sizes min/max={min(x for _, x in rel) if rel else None}/{max(x for _, x in rel) if rel else None}; deletions={len(dele)}; failed deletes={len(fails)}')
    p(f'   final sample: n={S[-1][1]} rolled={S[-1][2]} ({S[-1][2] / MiB:.1f} MiB) total={S[-1][3]} alloc={S[-1][4]}; max rolled={max(r_)} ({max(r_) / MiB:.1f} MiB); max total={max(s[3] for s in S)}; alloc>apparent samples={sum(1 for s in S if s[4] > s[3])}')
    d = dict(M=M, fp=fp, ndel=len(dele), finalr=S[-1][2], maxr=max(r_), nseg=nseg)
    if dele:
        maxlogged = max(x[2] for x in dele)
        p(f'   logged bytes-in-store: min={min(x[2] for x in dele)} max={maxlogged} (<= M: {maxlogged <= M}); first deletion {dele[0][0] - st:.0f} s after stress start; deleted sizes min/max={min(x[1] for x in dele)}/{max(x[1] for x in dele)}')
        p(f'   logged bytes-in-store sequence: {[x[2] for x in dele]}')
    if tag in ('K1', 'K2'):
        k = int(M // fp)
        run = best = 0
        for x in r_:
            run = run + 1 if x > M + fp else 0
            best = max(best, run)
        bounded = (not dele or max(x[2] for x in dele) <= M) and best < 36
        w0 = dele[0][0] + 60 if dele else None
        win = [s[2] for s in S if w0 is not None and w0 <= s[0] <= en]
        win_n = [s[1] - 1 for s in S if w0 is not None and w0 <= s[0] <= en]
        plat = statistics.median(win) if win else None
        lo, hi = k * fp * 0.95, (k + 1) * fp * 1.05
        plateau = plat is not None and lo <= plat <= hi
        # drift indicator: logged operand vs on-disk rolled at the nearest sample after each deletion
        drift = []
        for t_, sz, op, _ in dele:
            nxt = next((s for s in S if s[0] >= t_), None)
            if nxt: drift.append(op - nxt[2])
        d.update(k=k, bounded=bounded, plateau=plateau, plat=plat, longest_over=best, win=len(win))
        p(f'   k=floor(M/F\')={k}; longest run rolled>M+F\' = {best} samples; bounded={bounded}')
        p(f'   steady window {len(win)} samples: plateau (median rolled)={plat} ({(plat or 0) / MiB:.1f} MiB, {(plat or 0) / fp:.2f} F\'), window [{lo:.0f},{hi:.0f}] -> plateau={plateau}; median rolled segment count={statistics.median(win_n) if win_n else None}')
        if drift: p(f'   logged operand minus on-disk rolled (next sample) per deletion: first={drift[0]} last={drift[-1]} max={max(drift)}')
    else:
        grows = len(dele) == 0 and S[-1][2] >= 0.8 * max(nseg - 1, 0) * fp
        d['grows'] = grows
        p(f'   rolled segments at end={nseg - 1}; final rolled >= 0.8 x n x F\' ({0.8 * max(nseg - 1, 0) * fp:.0f}): {S[-1][2] >= 0.8 * max(nseg - 1, 0) * fp}; zero deletions: {len(dele) == 0}; grows={grows}')
    res[tag] = d
if 'K1' in res and 'K2' in res and res['K1'].get('plat') and res['K2'].get('plat'):
    ratio = res['K2']['plat'] / res['K1']['plat']
    follows = 2.0 <= ratio <= 3.0
    p(f'== K2/K1 plateau ratio = {ratio:.3f}; follows [2.0,3.0]={follows}; row3 (<=1.25)={ratio <= 1.25}')
else:
    ratio, follows = None, False
    p('== K2/K1 ratio not computable')
if all(t in res for t in ('C1', 'K1', 'K2', 'C2')):
    row1 = all(res[t]['bounded'] and res[t]['plateau'] for t in ('K1', 'K2')) and follows and res['C1']['grows'] and res['C2']['grows']
    row2 = any(not res[t]['bounded'] for t in ('K1', 'K2')) or any(res[t]['finalr'] >= 0.5 * res['C1']['finalr'] for t in ('K1', 'K2'))
    row4 = res['C1']['nseg'] - 1 < 5
    row5 = res['C2']['ndel'] > 0 or not res['C2']['grows']
    p(f'ROW1 (confirmed)={row1} ROW2 (claim wrong)={row2} ROW3 (plateau ~)={ratio is not None and ratio <= 1.25} ROW4 (C1 invalid)={row4} ROW5 (C2 bounded)={row5}')
open(os.path.join(R, 'cluster-analysis.txt'), 'w').write('\n'.join(out) + '\n')
