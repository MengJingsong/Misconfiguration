#!/usr/bin/env python3
"""Cluster-tier analyzer for B3f/B3g (frozen text, as amended 2026-10-27). Usage: analyze_cluster.py <arms-dir> [rows_per_pk]
Reads arms.txt (START/END/DISK events; START/END carry 'shape F L rchar'), markers.txt (one line per query), samples.csv (100 ms JMX samples).
Per arm: base = first sample at or after START (after jcmd GC.run); peak_used = max(heap_used) - base (young generation capped at about 20 MB, so the peak tracks the live set);
bytes_per_query = (rchar END - rchar START) / queries in the arm (rchar of the node, /proc/<pid>/io).
Rules fixed before run 1 (MB = 1e6 B), PARTS = 20, F = fetch size, L = PER PARTITION LIMIT:
  rows     : every query returns A: 20*min(L, rows_per_pk/100) groups, B: 20 groups (B3f 1)
  A_reads  : F=5000, forward: bytes_per_query(A, L=1) <= 0.10 * (A, L=abs) and bytes_per_query(A, L=100) <= 0.50 * (A, L=abs)
  B_reads  : F=5000, forward and reverse: max/min of bytes_per_query over B with L=1,100,abs <= 1.10
  B_heap   : F=5000, forward and reverse: max-min of peak_used over B with L=1,100,abs <= 30 MB
  disk     : |du(end) - du(start)| <= 1 %
  control  : peak_used(f_B_Labs_F100000) - peak_used(f_B_Labs_F5000) > 50 MB and > 3 x spread; spread = max(|forward - reverse| over the six F=5000 arms, peak_used of the noise arm)
  info     : F=100 and F=100000 arms are printed, not judged."""
import sys, os, statistics as st
d = sys.argv[1]; ROWS = int(sys.argv[2]) if len(sys.argv) > 2 else 200000
MB = 1e6; PARTS = 20
ev = [l.split() for l in open(os.path.join(d, 'arms.txt')) if l.strip()]
mk = [l.split() for l in open(os.path.join(d, 'markers.txt')) if l.strip()]
sm = []
for l in open(os.path.join(d, 'samples.csv')):
    p = l.strip().split(',')
    if p[0].isdigit() and len(p) == 4: sm.append(tuple(int(x) for x in p))
arms = {}; disk = {}
for e in ev:
    if e[1] == 'DISK': disk[e[2]] = int(e[3]); continue
    w = arms.setdefault(e[2], {}); w[e[1]] = int(e[0]); w[e[1] + '_r'] = int(e[6]) if len(e) > 6 else None
    if e[1] == 'START': w['shape'], w['F'], w['L'] = e[3], e[4], e[5]
res = {}
for a, w in arms.items():
    if 'END' not in w: continue
    S = [s for s in sm if w['START'] <= s[0] <= w['END']]
    if not S: print('no samples for', a); continue
    q = [m for m in mk if m[1] == a]
    sh, L = w['shape'], w['L']
    gpp = ROWS // 100
    want = None if sh == 'P' else (PARTS * (gpp if L == 'abs' else min(int(L), gpp)) if sh == 'A' else PARTS)
    res[a] = dict(shape=sh, F=w['F'], L=L, n=len(S), peak_used=max(s[1] for s in S) - S[0][1], alloc=S[-1][3] - S[0][3], q=len(q),
                  bpq=(w['END_r'] - w['START_r']) / max(len(q), 1), rows_ok=all(int(m[3]) == want for m in q) if want is not None and a != 'warmup' else None,
                  secs=(w['END'] - w['START']) / 1000, rows=sorted({int(m[3]) for m in q}))
print('%-20s %5s %7s %6s %4s %12s %14s %12s %8s  rows' % ('arm', 'shape', 'F', 'L', 'qry', 'peak_used_MB', 'bytes_per_qry', 'alloc_MB', 'secs'))
for a, r in res.items():
    print('%-20s %5s %7s %6s %4d %12.1f %14.0f %12.1f %8.1f  %s' % (a, r['shape'], r['F'], r['L'], r['q'], r['peak_used'] / MB, r['bpq'], r['alloc'] / MB, r['secs'], r['rows'][:3]))
ok = True
def exp(name, cond, detail):
    global ok; ok &= bool(cond); print('EXPECTED %-8s %s  %s' % (name, 'MATCH' if cond else 'MISMATCH', detail))
need = ['f_A_L1_F5000', 'f_A_L100_F5000', 'f_A_Labs_F5000', 'f_B_L1_F5000', 'f_B_L100_F5000', 'f_B_Labs_F5000', 'f_B_Labs_F100000', 'r_B_L1_F5000', 'r_B_Labs_F5000', 'noise']
if any(a not in res for a in need) or 'start' not in disk or 'end' not in disk:
    print('CLASS invalid: incomplete run (missing arm or disk reading)'); sys.exit(2)
exp('rows', all(r['rows_ok'] for r in res.values() if r['rows_ok'] is not None), {a: r['rows'][:2] for a, r in res.items() if r['rows_ok'] is not None})
bq = lambda a: res[a]['bpq']; pu = lambda a: res[a]['peak_used'] / MB
exp('A_reads', bq('f_A_L1_F5000') <= 0.10 * bq('f_A_Labs_F5000') and bq('f_A_L100_F5000') <= 0.50 * bq('f_A_Labs_F5000'),
    'bytes/query A F=5000 L=1,100,abs: %s' % [round(bq('f_A_L%s_F5000' % l)) for l in ('1', '100', 'abs')])
for pre, name in (('f', 'forward'), ('r', 'reverse')):
    v = [bq('%s_B_L%s_F5000' % (pre, l)) for l in ('1', '100', 'abs')]
    exp('B_reads', max(v) / min(v) <= 1.10, '%s bytes/query B F=5000 L=1,100,abs: %s ratio %.3f' % (name, [round(x) for x in v], max(v) / min(v)))
    h = [pu('%s_B_L%s_F5000' % (pre, l)) for l in ('1', '100', 'abs')]
    exp('B_heap', max(h) - min(h) <= 30, '%s peak_used MB B F=5000 L=1,100,abs: %s spread %.1f' % (name, [round(x, 1) for x in h], max(h) - min(h)))
exp('disk', abs(disk['end'] - disk['start']) <= 0.01 * disk['start'], 'du start %d end %d' % (disk['start'], disk['end']))
pairs = [abs(pu('f_%s_L%s_F5000' % (s, l)) - pu('r_%s_L%s_F5000' % (s, l))) for s in ('A', 'B') for l in ('1', '100', 'abs')]
spread = max(pairs + [pu('noise')])
ctl = pu('f_B_Labs_F100000') - pu('f_B_Labs_F5000')
exp('control', ctl > 50 and ctl > 3 * spread, 'peak_used(B, abs, F=100000) - peak_used(B, abs, F=5000) = %.1f MB; spread %.1f MB (forward-reverse pairs %s, noise %.1f)' % (ctl, spread, [round(x, 1) for x in pairs], pu('noise')))
print('INFO F=100 and F=100000 arms (peak_used MB, bytes/query):', {a: (round(pu(a), 1), round(bq(a))) for a in res if a.endswith('F100') or a.endswith('F100000')})
print('CLASS', 'B3g row 1: confirmed (counts exact, shape B reads and heap flat across L, control moves, disk flat)' if ok else
      'NOT row 1: see MISMATCH lines (rows/spread -> not confirmed; B_reads low at L=1 -> refuted; control -> not confirmed; A_reads only -> no matching row)')
sys.exit(0 if ok else 1)
