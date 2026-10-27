#!/usr/bin/env python3
"""EXPECTED lines for B2f / B2g (frozen text, as amended 2026-10-27). Usage: analyze_unit.py unit.txt
Prints one line per check: EXPECTED <what> <expected> GOT <value> ok|MISMATCH, then a class line. Primary checks decide the class."""
import sys
d = {}
for l in open(sys.argv[1]):
    l = l.strip()
    if '=' in l:
        k, v = l.split('=', 1); d[k] = v
ROWS = int(d.get('ROWS', 1000))
LS = ['1', '50', '100', '101', '1000', '1000000', 'none']
bad = []; n = 0
def chk(what, exp, got, primary=True):
    global n
    n += 1; ok = (exp == got); print('EXPECTED %s %s GOT %s %s%s' % (what, exp, got, 'ok' if ok else 'MISMATCH', '' if primary else ' (secondary)'))
    if not ok and primary: bad.append(what)
def lv(l): return 10**9 if l == 'none' else int(l)
cached = {'100': 100, 'ALL': ROWS, '500': 500}
for r in ('100', 'ALL', '500'):
    p = 'R' + r; c = cached[r]
    chk(p + ' pre.size (cache empty before the arm)', '0', d.get(p + '.pre.size'))
    chk(p + ' entry.cachedLiveRows', str(c), d.get(p + '.entry.cachedLiveRows'))
    base_w = d.get(p + '.base.weighted'); base_s = d.get(p + '.base.size')
    heaps = [int(d[p + '.base.heap'])] if p + '.base.heap' in d else []
    for rd in (1, 2, 3):
        for l in LS:
            k = '%s.r%d.L%s' % (p, rd, l)
            # direct call: true iff rowsWithNonExpiringCells (= cached rows) >= L; NONE (no limit) is false always
            exp_direct = 'false' if l == 'none' else ('true' if c >= lv(l) else 'false')
            chk(k + '.direct', exp_direct, d.get(k + '.direct'))
            # through the read: R=ALL short-circuits at ColumnFamilyStore:1931 (hit); otherwise hit iff direct is true
            hit = 1 if (r == 'ALL' or exp_direct == 'true') else 0
            chk(k + '.hit', str(hit), d.get(k + '.hit')); chk(k + '.oor', str(1 - hit), d.get(k + '.oor')); chk(k + '.miss', '0', d.get(k + '.miss'))
            chk(k + '.weighted', base_w, d.get(k + '.weighted')); chk(k + '.size', base_s, d.get(k + '.size'))
            rows = min(ROWS, lv(l)); chk(k + '.rows', str(rows), d.get(k + '.rows'), False)
            if k + '.heap' in d: heaps.append(int(d[k + '.heap']))
    if heaps:
        spread = max(heaps) - min(heaps)
        chk(p + ' heap spread < 8 MiB', 'True', str(spread < 8 * 2**20), True); print('  heap spread %d B' % spread)
w100 = int(d['R100.base.weighted']); w500 = int(d['R500.base.weighted']); ratio = w500 / w100
chk('control R500/R100 weightedSize in [4.5, 5.5]', 'True', str(4.5 <= ratio <= 5.5)); print('  ratio %.3f (w100 %d, w500 %d, wALL %s)' % (ratio, w100, w500, d.get('RALL.base.weighted')))
chk('NEG cache disabled', 'false', d.get('NEG.isRowCacheEnabled'))
for c in ('hit', 'miss', 'oor'): chk('NEG.' + c, '0', d.get('NEG.' + c))
chk('NEG.entry', 'absent', d.get('NEG.entry'))
chk('done', '1', d.get('done'))
print('primary mismatches: %d of %d checks' % (len(bad), n))
print('CLASS: ' + ('claim holds (B2g row 1)' if not bad else 'see mismatches: ' + '; '.join(bad[:12])))
