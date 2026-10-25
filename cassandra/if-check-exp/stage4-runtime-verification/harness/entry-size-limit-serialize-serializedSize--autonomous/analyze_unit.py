#!/usr/bin/env python3
"""Unit tier: compare results.csv RESULT lines with the frozen predictions (case file B2f as made numeric in B2i.6).
Usage: analyze_unit.py <results.csv>   Prints one PASS/FAIL line per prediction. Independent of the probe's own judgement."""
import sys, re
rows = {}
for line in open(sys.argv[1]):
    if line.startswith('RESULT '):
        d = dict(t.split('=', 1) for t in line.split()[1:] if '=' in t)
        rows[d['arm']] = d
def f(a, k): return float(rows[a][k])
out = []
def chk(name, ok, detail): out.append(('PASS' if ok else 'FAIL', name, detail))
def has(a): return a in rows
for S, exp in (('2147483647', None), ('2147483648', 'x'), ('2147487744', 'x')):
    a = 'guard_' + S
    if not has(a): continue
    r = rows[a]
    if exp is None: chk(a + ' no exception', r['exception'] == 'none', r['exception'])
    else: chk(a + ' IllegalArgumentException "Unable to allocate 2.000GiB"', r['exception'] == 'java.lang.IllegalArgumentException' and r.get('message') == '"Unable_to_allocate_2.000GiB"', r.get('exception', '') + ' ' + r.get('message', ''))
    chk(a + ' weighted_B == 0', f(a, 'weighted_B') == 0, r['weighted_B'])
    chk(a + ' peak delta < 64 MiB', f(a, 'peak_delta_MiB') < 64, r['peak_delta_MiB'])
for a, C in (('agg64', 64), ('agg64_repeat', 64), ('agg128', 128), ('agg256', 256)):
    if not has(a): continue
    w = f(a, 'weighted_B') / 2**20; p = f(a, 'peak_delta_MiB'); n = f(a, 'size')
    chk(a + ' weighted in [0.95C, C]', 0.95 * C <= w <= C, '%.2f MiB' % w)
    chk(a + ' size within 2 of C', C - 2 <= n <= C, str(n))
    chk(a + ' peak in [0.95C, C+16]', 0.95 * C <= p <= C + 16, str(p))
    chk(a + ' end_clean <= 32', f(a, 'end_clean_delta_MiB') <= 32, rows[a]['end_clean_delta_MiB'])
if has('agg64') and has('agg256'):
    sl = (f('agg256', 'peak_delta_MiB') - f('agg64', 'peak_delta_MiB')) / 192
    chk('slope peak vs C (64->256) in [0.9,1.1]', 0.9 <= sl <= 1.1, '%.3f' % sl)
if has('agg64') and has('agg64_repeat'):
    r_ = f('agg64_repeat', 'peak_delta_MiB') / f('agg64', 'peak_delta_MiB')
    chk('repeat within 10 percent', 0.9 <= r_ <= 1.1, '%.3f' % r_)
if has('agg3072'):
    a = 'agg3072'; w = f(a, 'weighted_B') / 2**20; p = f(a, 'peak_delta_MiB')
    chk('agg3072 weighted in [0.95,1.0] x 3072', 0.95 * 3072 <= w <= 3072, '%.1f' % w)
    chk('agg3072 peak in [2918,3104] and > 2048', 2918 <= p <= 3104 and p > 2048, str(p))
if has('nocache'): chk('nocache peak < 32', f('nocache', 'peak_delta_MiB') < 32, rows['nocache']['peak_delta_MiB'])
if has('over1_512MiB'):
    a = 'over1_512MiB'
    chk(a + ' weighted 0, size 0', f(a, 'weighted_B') == 0 and f(a, 'size') == 0, rows[a]['weighted_B'] + '/' + rows[a]['size'])
    chk(a + ' peak >= 480', f(a, 'peak_delta_MiB') >= 480, rows[a]['peak_delta_MiB'])
    chk(a + ' end_fill <= 32', f(a, 'end_fill_delta_MiB') <= 32, rows[a]['end_fill_delta_MiB'])
for a, lo in (('over8x256MiB', 1946), ('over8x512MiB', 3891)):
    if has(a):
        chk(a + ' weighted 0', f(a, 'weighted_B') == 0, rows[a]['weighted_B'])
        chk(a + ' peak >= %d' % lo, f(a, 'peak_delta_MiB') >= lo, rows[a]['peak_delta_MiB'])
if has('shrink256to128'):
    a = 'shrink256to128'; w = f(a, 'after_weighted_B') / 2**20
    chk(a + ' weighted after in [0.9x128,128]', 0.9 * 128 <= w <= 128, '%.1f' % w)
    chk(a + ' RssAnon delta after <= 144', f(a, 'end_fill_delta_MiB') <= 144, rows[a]['end_fill_delta_MiB'])
if has('clear_probe64'):
    a = 'clear_probe64'; r = rows[a]; base = f(a, 'base_MiB')
    b4 = f(a, 'rss_before_clear_kB') / 1024 - base; af = f(a, 'rss_after_clear_kB') / 1024 - base
    chk(a + ' size 0 and weighted 0 after clear', f(a, 'after_size') == 0 and f(a, 'after_weighted_B') == 0, r['after_size'] + '/' + r['after_weighted_B'])
    chk(a + ' RssAnon delta after clear >= 0.9 x before (memory not freed)', af >= 0.9 * b4, 'before %.1f after %.1f MiB' % (b4, af))
for r in out: print(*r, sep=' | ')
print('TOTAL pass=%d fail=%d' % (sum(1 for r in out if r[0] == 'PASS'), sum(1 for r in out if r[0] == 'FAIL')))
