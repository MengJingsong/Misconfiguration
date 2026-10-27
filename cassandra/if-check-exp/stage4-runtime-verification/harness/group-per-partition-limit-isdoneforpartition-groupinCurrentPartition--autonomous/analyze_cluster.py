#!/usr/bin/env python3
"""Cluster-tier analyzer for B3f/B3g (frozen text, thresholds as amended 2026-10-27). Usage: analyze_cluster.py <arms-dir> [rows_per_pk]
Reads arms.txt (START/END/DISK events), markers.txt (one line per query), samples.csv (100 ms JMX samples).
Per arm: base = the first sample at or after START (after jcmd GC.run); peak_used = max(heap_used) - base (the JVM runs with a young generation capped at 2 % of the 1 GiB heap (G1MaxNewSizePercent=2, about 20 MB), so garbage adds at most ~20 MB and the peak tracks the live set); peak_live = max(pools_collection_used) - base is printed for reference only;
alloc = allocated bytes (all live threads) END - START.
Rules fixed before run 1 (MB = 1e6 B):
  rows    : every query returns exactly min(N, rows_per_pk) groups (B3f 1)
  flat    : at P=1000, |peak_used(N absent) - peak_used(N=1)| <= 30 MB in the forward and in the reverse sweep, and peak_used does not rise monotonically with N
            (1 < 100 < 10000 < absent) by more than 30 MB in total in both sweeps (B3f 2)
  disk    : |du(end) - du(start)| <= 1 % (B3f 3)
  spread  : run-to-run spread = max over N of |peak_used(f_N) - peak_used(r_N)|, and the largest peak_live of the noise arm
  control : peak_used(c_Nabs_P300000) - peak_used(f_Nabs_P1000) > 30 MB and > 3 x spread (B3f 4, amended)
  info    : exploratory arms x_* (P=300000 with finite N) are printed, not judged."""
import sys, os, re, statistics as st
d = sys.argv[1]; ROWS = int(sys.argv[2]) if len(sys.argv) > 2 else 200000
MB = 1e6
ev = [l.split() for l in open(os.path.join(d, 'arms.txt')) if l.strip()]
mk = [l.split() for l in open(os.path.join(d, 'markers.txt')) if l.strip()]
sm = []
for l in open(os.path.join(d, 'samples.csv')):
    p = l.strip().split(',')
    if p[0].isdigit() and len(p) == 4: sm.append(tuple(int(x) for x in p))
arms = {}; disk = {}
for e in ev:
    if e[1] == 'DISK': disk[e[2]] = int(e[3]); continue
    arms.setdefault(e[2], {})[e[1]] = int(e[0]); 
    if e[1] == 'START' and len(e) > 4: arms[e[2]]['P'], arms[e[2]]['N'] = e[3], e[4]
res = {}
for a, w in arms.items():
    if 'END' not in w: continue
    S = [s for s in sm if w['START'] <= s[0] <= w['END']]
    if not S: print('no samples for', a); continue
    base = S[0]
    q = [m for m in mk if m[1] == a]
    N = w.get('N'); want = (ROWS if N == 'absent' else min(int(N), ROWS)) if N else None
    res[a] = dict(P=w.get('P'), N=N, n=len(S), peak_live=max(s[2] for s in S) - base[2], peak_used=max(s[1] for s in S) - base[1],
                  alloc=S[-1][3] - base[3], q=len(q), rows_ok=all(int(m[4]) == want for m in q) if want is not None and a != 'noise' else None,
                  secs=w['END'] / 1000 - w['START'] / 1000, rows=sorted({int(m[4]) for m in q}))
print('%-18s %6s %7s %5s %4s %12s %12s %12s %8s  rows' % ('arm', 'P', 'N', 'samp', 'qry', 'peak_live_MB', 'peak_used_MB', 'alloc_MB', 'secs'))
for a, r in res.items():
    print('%-18s %6s %7s %5d %4d %12.1f %12.1f %12.1f %8.1f  %s' % (a, r['P'], r['N'], r['n'], r['q'], r['peak_live'] / MB, r['peak_used'] / MB, r['alloc'] / MB, r['secs'], r['rows'][:3]))
ok = True
def exp(name, cond, detail):
    global ok; ok &= bool(cond); print('EXPECTED %-8s %s  %s' % (name, 'MATCH' if cond else 'MISMATCH', detail))
need = ['f_N1_P1000', 'f_Nabs_P1000', 'r_N1_P1000', 'r_Nabs_P1000', 'c_Nabs_P300000', 'noise']
if any(a not in res for a in need) or 'start' not in disk or 'end' not in disk:
    print('CLASS invalid: incomplete run (missing arm or disk reading)'); sys.exit(2)
exp('rows', all(r['rows_ok'] for a, r in res.items() if r['rows_ok'] is not None), {a: r['rows'][:2] for a, r in res.items() if r['rows_ok'] is not None})
pl = lambda a: res[a]['peak_used'] / MB
seq = lambda pre: [pl('%s_N%s_P1000' % (pre, n)) for n in ('1', '100', '10000', 'abs')]
f, r = seq('f'), seq('r')
flat = abs(f[3] - f[0]) <= 30 and abs(r[3] - r[0]) <= 30
mono = lambda s: s[0] < s[1] < s[2] < s[3] and s[3] - s[0] > 30
exp('flat', flat and not (mono(f) and mono(r)), 'peak_used MB N=1,100,10000,absent: forward %s reverse(N=1..absent) %s' % ([round(x, 1) for x in f], [round(x, 1) for x in r]))
exp('disk', abs(disk['end'] - disk['start']) <= 0.01 * disk['start'], 'du start %d end %d' % (disk['start'], disk['end']))
spread = max([abs(a - b) for a, b in zip(f, r)] + [pl('noise')])
ctl = pl('c_Nabs_P300000') - pl('f_Nabs_P1000')
exp('control', ctl > 30 and ctl > 3 * spread, 'peak_used(P=300000,absent) - peak_used(P=1000,absent) = %.1f MB; spread %.1f MB' % (ctl, spread))
print('INFO exploratory (not judged): ' + ', '.join('%s peak_used %.1f MB alloc %.0f MB' % (a, pl(a), res[a]['alloc'] / MB) for a in res if a.startswith('x_')))
print('INFO alloc at P=1000 (N=1,100,10000,absent) forward MB:', [round(res['f_N%s_P1000' % n]['alloc'] / MB, 1) for n in ('1', '100', '10000', 'abs')])
print('CLASS', 'B3g row 1: confirmed (groups = N, peak heap flat, disk flat, control moves)' if ok else
      'NOT row 1: see MISMATCH lines (rows -> A3 trace wrong; flat -> refuted if monotone beyond spread; control -> not confirmed)')
sys.exit(0 if ok else 1)
