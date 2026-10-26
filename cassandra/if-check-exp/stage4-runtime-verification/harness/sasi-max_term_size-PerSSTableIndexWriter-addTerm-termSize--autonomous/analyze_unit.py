#!/usr/bin/env python3
"""Unit-tier PASS/FAIL per frozen prediction B2f(1)-(8) (as amended B5). Usage: analyze_unit.py <writer-results.csv> <writer-estimates.csv>. Exit 1 on any FAIL."""
import csv, sys, math
rows = list(csv.DictReader(open(sys.argv[1])))
est = list(csv.DictReader(open(sys.argv[2])))
def get(arm, size=None, n=None, src=None, opt=None):
    for r in rows:
        if r['arm'] != arm: continue
        if size is not None and int(r['size']) != size: continue
        if n is not None and int(r['n_adds']) != n: continue
        if src is not None and r['source'].upper() != src: continue
        if opt is not None and r['option_mb'] != opt: continue
        return r
    raise KeyError((arm, size, n, src, opt))
fails = 0
def check(tag, exp, got, ok):
    global fails
    print('%s EXPECTED: %s | GOT: %s | %s' % (tag, exp, got, 'PASS' if ok else 'FAIL'))
    if not ok: fails += 1
I = lambda r, k: int(r[k]) if r[k] != '' else None
C = 'COMPACTION'
# (1) boundary accepted
for s in (1022, 1023):
    r = get('boundary', s, 10000)
    check('B2f(1) S=%d' % s, 'reached=10000 info=0 est=%d' % (10000 * (s + 220)), 'reached=%s info=%s est=%s' % (r['reached_builder'], r['info_reject_lines'], r['est_final']),
          I(r, 'reached_builder') == 10000 and I(r, 'info_reject_lines') == 0 and I(r, 'est_final') == 10000 * (s + 220))
# (2) rejected
for s in (1024, 1025):
    r = get('boundary', s, 10000)
    check('B2f(2) S=%d' % s, 'reached=0 info=10000 err=0 est=0 file_len=0 cuts=0 seglines=0', 'reached=%s info=%s err=%s est=%s file=%s cuts=%s seg=%s' % tuple(r[k] for k in ('reached_builder', 'info_reject_lines', 'err_reject_lines', 'est_final', 'file_len', 'cuts_before_complete', 'segment_lines')),
          [I(r, k) for k in ('reached_builder', 'info_reject_lines', 'err_reject_lines', 'est_final', 'file_len', 'cuts_before_complete', 'segment_lines')] == [0, 10000, 0, 0, 0, 0, 0])
# (3) growth
fl = {}
for n in (1000, 10000, 100000):
    r = get('growth', 1023, n); fl[n] = I(r, 'file_len')
    check('B2f(3) N=%d' % n, 'est=%d file>=%d' % (n * 1243, n * 1023), 'est=%s file=%s' % (r['est_final'], r['file_len']), I(r, 'est_final') == n * 1243 and fl[n] >= n * 1023)
for a, b in ((1000, 10000), (10000, 100000)):
    ratio = fl[b] / fl[a]
    check('B2f(3) file ratio N=%d/%d' % (b, a), '8..12', '%.2f' % ratio, 8 <= ratio <= 12)
# estimate series: every 10k step in the 100k growth arm equals k*1243 (no plateau)
ser = [e for e in est if e['arm'] == 'growth' and e['size'] == '1023' and e['kind'] == 'estimate']
mono = sorted((int(e['at_add']), int(e['value'])) for e in ser if int(e['at_add']) % 10000 == 0)
check('B2f(3) series', 'value = at_add*1243 at every 10k step', 'steps=%d' % len(mono), len(mono) >= 10 and all(v == a * 1243 for a, v in mono))
# (4) cap control
caps = {'1': (1048576, 844), '8': (8388608, 6749), 'def': (161061273, 129575)}
flen = set()
for opt, (cap, cmin) in caps.items():
    r = get('cap', 1023, 100000, C, opt); cuts = 100000 // cmin; lines = cuts + (1 if cuts and 100000 % cmin else 0)
    flen.add(r['file_len'])
    ok = I(r, 'cuts_before_complete') == cuts and I(r, 'segment_lines') == lines
    if cuts: ok = ok and I(r, 'min_est_at_cut') >= cap and I(r, 'max_est_at_cut') < cap + 1243
    check('B2f(4) option=%s' % opt, 'cuts=%d lines=%d est_at_cut in [%d,%d)' % (cuts, lines, cap, cap + 1243), 'cuts=%s lines=%s est_at_cut=[%s,%s]' % (r['cuts_before_complete'], r['segment_lines'], r['min_est_at_cut'], r['max_est_at_cut']), ok)
check('B2f(4) final file equal across options', '1 distinct value', str(sorted(flen)), len(flen) == 1)
r = get('cap200k', 1023, 200000, C, 'def')
check('B2f(4) default, N=200k', 'cuts=1 lines=2', 'cuts=%s lines=%s' % (r['cuts_before_complete'], r['segment_lines']), I(r, 'cuts_before_complete') == 1 and I(r, 'segment_lines') == 2)
# (5) FLUSH
r = get('flush', 1023, 100000, 'FLUSH', '1')
check('B2f(5) FLUSH source, option 1', 'cuts=0 lines=0', 'cuts=%s lines=%s' % (r['cuts_before_complete'], r['segment_lines']), I(r, 'cuts_before_complete') == 0 and I(r, 'segment_lines') == 0)
# (6) tokenized
rd = get('token', None, 1, C, 'def'); r1 = get('token', None, 1, C, '1')
check('B2f(6) tokenized, default option', 'value=1048576 B, reached=131072 rejects=0 est=29753344 cuts=0', 'value=%s reached=%s info=%s est=%s cuts=%s' % (rd['size'], rd['reached_builder'], rd['info_reject_lines'], rd['est_final'], rd['cuts_before_complete']),
      I(rd, 'size') == 1048576 and I(rd, 'reached_builder') == 131072 and I(rd, 'info_reject_lines') == 0 and I(rd, 'err_reject_lines') == 0 and I(rd, 'est_final') == 29753344 and I(rd, 'cuts_before_complete') == 0)
check('B2f(6) tokenized, option 1', 'cuts=1 lines=1 rejects=0 (estimate at cut = 29753344 = %.1f x cap)' % (29753344 / 1048576), 'cuts=%s lines=%s info=%s' % (r1['cuts_before_complete'], r1['segment_lines'], r1['info_reject_lines']),
      I(r1, 'cuts_before_complete') == 1 and I(r1, 'segment_lines') == 1 and I(r1, 'info_reject_lines') == 0)
# (7) heap, indicative
r = get('growth', 1023, 100000)
hd = I(r, 'heap_delta_bytes')
check('B2f(7) heap delta (indicative)', '0.5x..2x of 124300000', str(hd), hd is not None and 0.5 * 124300000 <= hd <= 2 * 124300000)
print('SUMMARY', 'ALL PASS' if not fails else '%d FAIL' % fails)
sys.exit(1 if fails else 0)
