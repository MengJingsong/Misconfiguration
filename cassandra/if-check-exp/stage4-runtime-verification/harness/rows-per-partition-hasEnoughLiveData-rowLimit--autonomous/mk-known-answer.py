#!/usr/bin/env python3
"""Writes a synthetic unit.txt for the instrument check of analyze_unit.py. Usage: mk-known-answer.py good|bad > file
'bad' lets N=5 cache 8 live rows and makes the 5-arm entry change after the L reads (cap broken, LIMIT moves memory)."""
import sys
mode = sys.argv[1]
def out(k, v): print('%s=%s' % (k, v))
out('ROWS', 200); out('firsttrigger', 'OK')
LIM = [1, 4, 5, 6, 49, 50, 51, 1000]
def mk(p, n, rows, size, he_thr, cov_thr, nonexp=None, live=None, rowcount=None):
    out(p + '.populate.entry', 'present'); out(p + '.populate.rowCount', rowcount if rowcount is not None else rows)
    out(p + '.populate.cachedLiveRows', live if live is not None else rows); out(p + '.populate.rowsWithNonExpiringCells', nonexp if nonexp is not None else rows)
    out(p + '.pre.rcWeightedSize', 0); out(p + '.populate.serializedSize', size); out(p + '.populate.rcSize', 1); out(p + '.populate.rcWeightedSize', size + 100)
    for L in LIM:
        k = '%s.L%d' % (p, L)
        out(k + '.hasEnough', 'true' if L <= he_thr else 'false'); cov = cov_thr is None or L <= cov_thr
        out(k + '.covered', 'true' if cov else 'false'); out(k + '.dHit', 1 if cov else 0); out(k + '.dOut', 0 if cov else 1); out(k + '.dMiss', 0)
    bad = mode == 'bad' and p == '5'
    out(p + '.after.rowCount', rows + (3 if bad else 0)); out(p + '.after.cachedLiveRows', rows); out(p + '.after.serializedSize', size + (400 if bad else 0))
    out(p + '.after.rcSize', 1); out(p + '.after.rcWeightedSize', size + 100 + (400 if bad else 0))
mk('5', 5, 8 if mode == 'bad' else 5, 60 + 150 * 5, 5, 5)
mk('50', 50, 50, 60 + 150 * 50, 50, 50)
mk('ALL', 0, 200, 60 + 150 * 200, 200, None)
out('NONE.populate.entry', 'absent'); out('NONE.populate.hit', 0); out('NONE.populate.miss', 0); out('NONE.populate.outOfRange', 0); out('NONE.isRowCacheEnabled', 'false')
for p, rc, nonexp in (('TTL', 5, 0), ('TOMB', 55, 5)):
    out(p + '.populate.entry', 'present'); out(p + '.populate.rowCount', rc); out(p + '.populate.cachedLiveRows', 5); out(p + '.populate.rowsWithNonExpiringCells', nonexp)
    for L in (1, 5, 6): out('%s.L%d.hasEnough' % (p, L), 'true' if L <= 5 else 'false')
out('NOCK.cachedLiveRows', 1); out('NOCK.rowCount', 1)
out('done', 1)
