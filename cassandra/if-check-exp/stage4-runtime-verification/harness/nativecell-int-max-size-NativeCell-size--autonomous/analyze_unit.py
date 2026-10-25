#!/usr/bin/env python3
"""PASS/FAIL per frozen numeric prediction of B2i.5 from raw/results.csv. Usage: analyze_unit.py <results.csv>"""
import sys, csv, collections
D = collections.defaultdict(dict)
for r in csv.reader(open(sys.argv[1])):
    if len(r) >= 3: D[r[0]][r[1]] = ','.join(r[2:])
MiB = 1 << 20; out = []
def chk(name, ok, detail=''): out.append((name, 'PASS' if ok else 'FAIL', detail))
def g(a, k): return D[a][k]
def f(a, k): return float(D[a][k])
for arm in ('S_1KiB', 'S_200KiB', 'S_16MiB', 'S_255MiB', 'R_200KiB_a', 'R_200KiB_b'):
    if arm not in D: continue
    L = int(g(arm, 'L')); exp = 10 * (L + 21)
    chk('B2i.5a %s: 10 cells, offHeapSize==L+21, owns delta==L+21, no exception' % arm,
        f(arm, 'offHeapSize_mismatch') == 0 and f(arm, 'owns_delta_mismatch') == 0 and f(arm, 'exceptions') == 0 and f(arm, 'n_cells') == 10)
    chk('B2i.5a %s: sum(offHeapSize)==owns_total==10*(L+21)=%d' % (arm, exp), f(arm, 'sum_offHeapSize') == f(arm, 'owns_total') == exp, '%s %s' % (g(arm, 'sum_offHeapSize'), g(arm, 'owns_total')))
    if arm in ('S_16MiB', 'S_255MiB'):
        r = f(arm, 'rss_rise'); chk('B2i.5a %s: RssAnon rise in [0.90,1.15]x expected' % arm, 0.90 * exp <= r <= 1.15 * exp, 'rise/exp=%.4f' % (r / exp))
        a = f(arm, 'rss_rise_after_free'); chk('B2i.5a %s: after free <= 0.10*rise+64MiB' % arm, a <= 0.10 * r + 64 * MiB, 'after=%.1f MiB' % (a / MiB))
    chk('B2i.5a %s: owns==0 after discard' % arm, f(arm, 'owns_after_discard') == 0)
for arm in ('G1', 'G2'):
    if arm not in D: continue
    chk('B2i.5b %s throw: IllegalStateException' % arm, g(arm, 'throw_probe') == 'java.lang.IllegalStateException', g(arm, 'throw_probe'))
    chk('B2i.5b %s throw: message null' % arm, g(arm, 'throw_message') in ('null', ''))
    chk('B2i.5b %s throw: frame NativeCell.<init>:101' % arm, g(arm, 'throw_frame') == 'org.apache.cassandra.db.rows.NativeCell.<init>:101', g(arm, 'throw_frame'))
    chk('B2i.5b %s throw: owns unchanged, RssAnon rise < 64MiB' % arm, f(arm, 'throw_owns_delta') == 0 and f(arm, 'throw_rss_rise') < 64 * MiB, 'rss rise %.2f MiB' % (f(arm, 'throw_rss_rise') / MiB))
    chk('B2i.5b %s pass: no exception, offHeapSize==2147483647, owns delta==2147483647' % arm, g(arm, 'pass_probe') == 'OK' and f(arm, 'pass_offHeapSize') == 2147483647 and f(arm, 'pass_owns_delta') == 2147483647, g(arm, 'pass_probe'))
    if arm == 'G2': chk('B2i.5b G2 pass: owns delta > 255 x pool limit', f(arm, 'pass_owns_delta') > 255 * f(arm, 'pool_limit'), '%.0f x' % (f(arm, 'pass_owns_delta') / f(arm, 'pool_limit')))
for p in ('P8', 'P16', 'P32'):
    if p not in D: continue
    lim = f(p, 'limit'); unit = MiB + 21; k = int(lim // unit)
    chk('B2i.5c %s: admitted before block == floor(P/(1MiB+21)) == %d' % (p, k), f(p, 'admitted_before_block') == k and f(p, 'expected_admitted') == k, g(p, 'admitted_before_block'))
    chk('B2i.5c %s: owns at block == admitted x (1MiB+21); worker blocked' % p, f(p, 'owns_at_block') == k * unit and g(p, 'worker_alive_blocked') == 'true')
    chk('B2i.5c %s: blocked cell completes after release (<5 s)' % p, 0 <= f(p, 'completed_after_release_ms') < 5000, g(p, 'completed_after_release_ms') + ' ms')
    chk('B2i.5c %s: blocking group returns at once (<1 s per cell), owns > P' % p, f(p, 'blocking_max_ms') < 1000 and g(p, 'blocking_owns_over_limit') == 'true' and f(p, 'blocking_owns') == f(p, 'blocking_expected_owns'), 'max %s ms owns %s' % (g(p, 'blocking_max_ms'), g(p, 'blocking_owns')))
if 'O' in D:
    chk('B2i.5d O: 16MiB cell accepted, owns==16MiB+21 > 2x pool limit', f('O', 'owns') == 16 * MiB + 21 and f('O', 'owns') > 2 * f('O', 'pool_limit'), g('O', 'owns'))
if 'H' in D:
    chk('B2i.5e H: heap cell leaves owns unchanged', f('H', 'owns_before') == f('H', 'owns_after') == 0)
w = max(len(a) for a, _, _ in out)
for a, b, c in out: print('%s  %s  %s' % (b, a.ljust(w), c))
print('TOTAL pass=%d fail=%d' % (sum(1 for x in out if x[1] == 'PASS'), sum(1 for x in out if x[1] == 'FAIL')))
