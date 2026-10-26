#!/usr/bin/env python3
"""PASS/FAIL per frozen unit prediction (B2f as amended B5.2, B5.6). Usage: analyze_unit.py <raw dir>  (reads unit-results.csv, unit-estimates.csv)"""
import csv, math, sys, collections
d = sys.argv[1]
N = 100000
rows = list(csv.reader(open(d + '/unit-results.csv')))[1:]
direct, fin, wcap, wbound = {}, {}, {}, {}
for r in rows:
    if r[0] == 'direct': direct[int(r[1])] = r
    elif r[0] == 'finish_returned': fin[int(r[2])] = (r[3] == 'true', r[5] == 'true')
    elif r[0] == 'writer-cap': wcap[int(r[3])] = r
    elif r[0] == 'writer-boundary': wbound[int(r[1])] = r
cuts = collections.defaultdict(list)
for r in list(csv.reader(open(d + '/unit-estimates.csv')))[1:]:
    if r[0].endswith('-segmentcut'): cuts[(r[0], r[4])].append(int(r[2]))
res = []
def chk(name, expected, got, ok):
    res.append(ok); print('%s  %s  EXPECTED: %s  GOT: %s' % ('PASS' if ok else 'FAIL', name, expected, got))
est = lambda s: int(direct[s][7]); acc = lambda s: int(direct[s][4]); errs = lambda s: int(direct[s][5]); flen = lambda s: int(direct[s][8])
chk('S=1023 accepted', N, acc(1023), acc(1023) == N)
chk('S=1023 estimate', N * 1243, est(1023), est(1023) == N * 1243)
chk('S=512 estimate', N * (220 + 512), est(512), est(512) == N * 732)
chk('S=1 estimate (62 distinct terms, B5.6)', 62 * 113 + N * 108, est(1), est(1) == 62 * 113 + N * 108)
chk('S=1023 file length > 0', '> 0', flen(1023), flen(1023) > 0)
for s in (1024, 1025, 4096):
    chk('S=%d accepted/rejection logs/estimate' % s, '0 / %d / 0' % N, '%d / %d / %d' % (acc(s), errs(s), est(s)), acc(s) == 0 and errs(s) == N and est(s) == 0)
    chk('S=%d finish returns false, file length 0 (B5.2)' % s, 'False, 0', '%s, %d' % (fin[s][0], flen(s)), fin[s][0] is False and flen(s) == 0)
for s in (1, 512, 1023):
    chk('S=%d finish returns true' % s, True, fin[s][0], fin[s][0])
for cap in (1, 4, 16):
    r = wcap[cap]; adds = int(r[2]); per = math.ceil(cap * 1048576 / 732); segs = int(r[9])
    cl = cuts[('writer-cap-segmentcut', 'cap_mb=%d' % cap)]
    diffs = set(cl[i] - (cl[i - 1] if i else 0) for i in range(len(cl)))
    chk('writer cap %d MB: segment cut every %d terms (estimate at flush %d in [C, C+732))' % (cap, per, per * 732), {per}, diffs, diffs == {per} and cap * 1048576 <= per * 732 < cap * 1048576 + 732)
    exp = adds // per
    chk('writer cap %d MB: segments before complete = floor(%d / %d)' % (cap, adds, per), exp, segs, segs == exp and adds == 229197)
    chk('writer cap %d MB: no rejection logs' % cap, 0, r[5] + '/' + r[6], r[5] == '0' and r[6] == '0')
sg = [int(wcap[c][9]) for c in (1, 4, 16)]
chk('control: segment count falls as C rises (same 229,197 adds)', '159 > 39 > 9', sg, sg[0] > sg[1] > sg[2])
b = wbound
chk('writer S=1023: 1 segment before complete (13,498 terms/segment at 16 MB, 20,000 adds), no rejection', '1, 0', '%s, %s' % (b[1023][9], b[1023][6]), b[1023][9] == '1' and b[1023][6] == '0')
chk('writer S=1024: 20,000 info rejection logs, 0 segments, file length 0', '20000, 0, 0', '%s, %s, %s' % (b[1024][6], b[1024][9], b[1024][8]), b[1024][6] == '20000' and b[1024][9] == '0' and b[1024][8] == '0')
print('SUMMARY unit predictions: %d/%d PASS' % (sum(res), len(res)))
print('HEAP (indicative): ' + ', '.join('S=%d delta=%s' % (s, direct[s][11]) for s in sorted(direct)))
print('FILE LENGTH direct: ' + ', '.join('S=%d len=%s' % (s, direct[s][8]) for s in sorted(direct)))
