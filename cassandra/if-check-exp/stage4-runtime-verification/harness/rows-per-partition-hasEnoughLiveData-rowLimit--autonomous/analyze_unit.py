#!/usr/bin/env python3
"""Unit tier readings against B2f / B2g (frozen text 2026-10-27). Usage: analyze_unit.py unit.txt
Prints 'EXPECTED <what> | got <value> | RESULT ok|MISMATCH PRIMARY|INFO' per check and a CLASS line.
PRIMARY = a B2f prediction. INFO = row counts returned by the reads."""
import sys, re
kv = {}
for l in open(sys.argv[1]):
    l = l.strip()
    if '=' in l:
        k, v = l.split('=', 1); kv[k] = v
g = kv.get
def gi(k):
    v = g(k); return int(v) if v is not None and re.fullmatch(r'-?\d+', v) else None
bad = 0; npri = 0
def chk(what, got, ok, primary=True):
    global bad, npri
    if primary: npri += 1
    if primary and not ok: bad += 1
    print('EXPECTED %s | got %s | RESULT %s%s' % (what, got, 'ok' if ok else 'MISMATCH', ' PRIMARY' if primary else ' INFO'))
LIM = [1, 4, 5, 6, 49, 50, 51, 1000]
chk('ROWS = 200 (full-scale run)', g('ROWS'), g('ROWS') == '200', False)
chk('firsttrigger=OK', g('firsttrigger'), g('firsttrigger') == 'OK')
chk('done=1', g('done'), g('done') == '1')
changed = False   # did the entry / sizes change across the L reads, for any arm with an entry
def arm(p, N, rowcount, live, nonexp, cover_thr, hasenough_exp):
    """cover_thr: covered(L) is true iff L <= cover_thr (None = all L); hasenough_exp: function L -> bool"""
    global changed
    chk('%s populate entry present' % p, g(p + '.populate.entry'), g(p + '.populate.entry') == 'present')
    chk('%s rowCount = %d' % (p, rowcount), gi(p + '.populate.rowCount'), gi(p + '.populate.rowCount') == rowcount)
    chk('%s cachedLiveRows = %d' % (p, live), gi(p + '.populate.cachedLiveRows'), gi(p + '.populate.cachedLiveRows') == live)
    chk('%s rowsWithNonExpiringCells = %d' % (p, nonexp), gi(p + '.populate.rowsWithNonExpiringCells'), gi(p + '.populate.rowsWithNonExpiringCells') == nonexp)
    for L in LIM:
        k = '%s.L%d' % (p, L)
        he = 'true' if hasenough_exp(L) else 'false'
        chk('%s hasEnoughLiveData(L=%d) = %s' % (p, L, he), g(k + '.hasEnough'), g(k + '.hasEnough') == he)
        cov = 'true' if (cover_thr is None or L <= cover_thr) else 'false'
        chk('%s isFilterFullyCoveredBy(L=%d) = %s' % (p, L, cov), g(k + '.covered'), g(k + '.covered') == cov)
        dh, do, dm = gi(k + '.dHit'), gi(k + '.dOut'), gi(k + '.dMiss')
        exp = (1, 0, 0) if cov == 'true' else (0, 1, 0)
        chk('%s read L=%d: dHit,dOut,dMiss = %s' % (p, L, exp), (dh, do, dm), (dh, do, dm) == exp)
    same = all(g('%s.populate.%s' % (p, f)) == g('%s.after.%s' % (p, f)) for f in ('rowCount', 'cachedLiveRows', 'serializedSize', 'rcSize', 'rcWeightedSize'))
    if not same: changed = True
    chk('%s entry shape, size() and weightedSize() unchanged by the L reads' % p, [(f, g('%s.populate.%s' % (p, f)), g('%s.after.%s' % (p, f))) for f in ('rowCount', 'serializedSize', 'rcSize', 'rcWeightedSize')], same)
arm('5', 5, 5, 5, 5, 5, lambda L: L <= 5)
arm('50', 50, 50, 50, 50, 50, lambda L: L <= 50)
arm('ALL', None, 200, 200, 200, None, lambda L: L <= 200)
s5, s50, sA = gi('5.populate.serializedSize'), gi('50.populate.serializedSize'), gi('ALL.populate.serializedSize')
def wd(p):
    a, b = gi(p + '.populate.rcWeightedSize'), gi(p + '.pre.rcWeightedSize')
    return None if a is None or b is None else a - b
w5, w50, wA = wd('5'), wd('50'), wd('ALL')
chk('serializedSize 5 < 50 < ALL', (s5, s50, sA), None not in (s5, s50, sA) and s5 < s50 < sA)
r = (s50 / s5) if s5 and s50 else None
chk('serializedSize(50)/serializedSize(5) within 7..10.5', None if r is None else '%.2f' % r, r is not None and 7 <= r <= 10.5)
chk('weightedSize growth populate-minus-pre: 5 < 50 < ALL (B2f; pre = the cache just before the populate read)', (w5, w50, wA), None not in (w5, w50, wA) and w5 < w50 < wA, False)
chk('NONE entry absent', g('NONE.populate.entry'), g('NONE.populate.entry') == 'absent')
chk('NONE hit = miss = outOfRange = 0 after all reads', (g('NONE.populate.hit'), g('NONE.populate.miss'), g('NONE.populate.outOfRange')), (g('NONE.populate.hit'), g('NONE.populate.miss'), g('NONE.populate.outOfRange')) == ('0', '0', '0'))
chk('NONE isRowCacheEnabled = false', g('NONE.isRowCacheEnabled'), g('NONE.isRowCacheEnabled') == 'false')
# TTL variant
chk('TTL populate entry present', g('TTL.populate.entry'), g('TTL.populate.entry') == 'present')
chk('TTL rowCount 5, cachedLiveRows 5, rowsWithNonExpiringCells 0', (gi('TTL.populate.rowCount'), gi('TTL.populate.cachedLiveRows'), gi('TTL.populate.rowsWithNonExpiringCells')), (gi('TTL.populate.rowCount'), gi('TTL.populate.cachedLiveRows'), gi('TTL.populate.rowsWithNonExpiringCells')) == (5, 5, 0))
for L, e in ((1, 'true'), (5, 'true'), (6, 'false')):
    chk('TTL hasEnoughLiveData(L=%d) = %s' % (L, e), g('TTL.L%d.hasEnough' % L), g('TTL.L%d.hasEnough' % L) == e)
# TOMB variant
chk('TOMB populate entry present', g('TOMB.populate.entry'), g('TOMB.populate.entry') == 'present')
chk('TOMB cachedLiveRows 5, rowCount 55, rowsWithNonExpiringCells 5', (gi('TOMB.populate.cachedLiveRows'), gi('TOMB.populate.rowCount'), gi('TOMB.populate.rowsWithNonExpiringCells')), (gi('TOMB.populate.cachedLiveRows'), gi('TOMB.populate.rowCount'), gi('TOMB.populate.rowsWithNonExpiringCells')) == (5, 55, 5))
for L, e in ((1, 'true'), (5, 'true'), (6, 'false')):
    chk('TOMB hasEnoughLiveData(L=%d) = %s' % (L, e), g('TOMB.L%d.hasEnough' % L), g('TOMB.L%d.hasEnough' % L) == e)
chk('NOCK cachedLiveRows = rowCount = 1', (gi('NOCK.cachedLiveRows'), gi('NOCK.rowCount')), (gi('NOCK.cachedLiveRows'), gi('NOCK.rowCount')) == (1, 1))
# B2g class
over = any((gi(p + '.populate.cachedLiveRows') or 0) > e for p, e in (('5', 5), ('50', 50)))
pattern_bad = bad
if g('firsttrigger') != 'OK':
    cls = 'setup error (no entry after the populate read): not a refutation'
elif over:
    cls = 'cachedLiveRows > N: cap does not bind, claim (ii) refuted'
elif changed:
    cls = 'entry / size() / weightedSize() differ after the L reads: LIMIT influences memory, claim (i) refuted'
elif bad == 0:
    cls = 'claim holds (LIMIT changes only hit / out of range; rows per entry = N; TOMB overshoot 55; sizes follow N)'
else:
    cls = '%d of %d primary checks mismatch while the entry and sizes are unchanged by LIMIT: see MISMATCH lines (B2g: memory claim holds if only the pattern differs; otherwise no matching row)' % (bad, npri)
print('CLASS %s | primary mismatches %d of %d' % (cls, bad, npri))
