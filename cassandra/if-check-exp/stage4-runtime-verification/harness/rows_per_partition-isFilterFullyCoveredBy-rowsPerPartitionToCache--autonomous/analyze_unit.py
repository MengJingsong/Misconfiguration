#!/usr/bin/env python3
"""Unit tier readings against B2f / B2g (frozen text). Usage: analyze_unit.py unit.txt
Prints one line per check: 'EXPECTED <what> | got <value> | RESULT ok|MISMATCH [PRIMARY|INFO]' and a CLASS line.
PRIMARY checks are the B2f numbers; INFO checks (hit/miss counters, read row counts) come from B2d/B2e step 4 and the code, not B2f."""
import sys, re
kv = {}
for l in open(sys.argv[1]):
    l = l.strip()
    if '=' in l:
        k, v = l.split('=', 1); kv[k] = v
def g(k):
    return kv.get(k)
def gi(k):
    v = g(k); return int(v) if v is not None and re.fullmatch(r'-?\d+', v) else None
bad_primary = 0; n_primary = 0
def chk(what, got, ok, primary=True):
    global bad_primary, n_primary
    if primary: n_primary += 1
    if primary and not ok: bad_primary += 1
    print('EXPECTED %s | got %s | RESULT %s%s' % (what, got, 'ok' if ok else 'MISMATCH', ' PRIMARY' if primary else ' INFO'))
rows = gi('ROWS')
chk('ROWS = 1000 (full-scale run)', rows, rows == 1000, False)
chk('firsttrigger=OK', g('firsttrigger'), g('firsttrigger') == 'OK')
chk('done=1', g('done'), g('done') == '1')
exp_live = {'1': 1, '10': 10, '100': 100, 'ALL': 1000, '2000': 1000}
for n, e in exp_live.items():
    p = 'N' + n
    chk('%s entry present' % p, g(p + '.entry'), g(p + '.entry') == 'present')
    chk('%s cachedLiveRows = %d' % (p, e), gi(p + '.cachedLiveRows'), gi(p + '.cachedLiveRows') == e)
    chk('%s rowCount = cachedLiveRows (no dead rows)' % p, gi(p + '.rowCount'), gi(p + '.rowCount') == gi(p + '.cachedLiveRows'))
    chk('%s coveredFullSlice = %s' % (p, 'true' if n in ('ALL', '2000') else 'false'), g(p + '.coveredFullSlice'), g(p + '.coveredFullSlice') == ('true' if n in ('ALL', '2000') else 'false'))
    chk('%s coveredHead5 = %s' % (p, 'false' if n == '1' else 'true'), g(p + '.coveredHead5'), g(p + '.coveredHead5') == ('false' if n == '1' else 'true'))
    chk('%s LIMIT 5 returns 5 rows both reads' % p, (g(p + '.read1.rows'), g(p + '.read2.rows')), g(p + '.read1.rows') == '5' and g(p + '.read2.rows') == '5', False)
s10, s100, sALL, s1 = gi('N10.serializedSize'), gi('N100.serializedSize'), gi('NALL.serializedSize'), gi('N1.serializedSize')
if s10 and s100:
    r = s100 / s10
    chk('serializedSize N=100 / N=10 within 8..12 (about 10x within 20%)', '%.2f (%s / %s)' % (r, s100, s10), 8 <= r <= 12)
else:
    chk('serializedSize N=100 / N=10 within 8..12', None, False)
if s100 and sALL: chk('serializedSize ALL / N=100 within 8..12 (INFO, derived: 1000/100 rows)', '%.2f' % (sALL / s100), 8 <= sALL / s100 <= 12, False)
if s1 and s10: chk('serializedSize strictly increasing 1 < 10 < 100 < ALL', (s1, s10, s100, sALL), s1 < s10 < s100 < sALL)
chk('NNONE entry absent', g('NNONE.entry'), g('NNONE.entry') == 'absent')
chk('NNONE hit = miss = outOfRange = 0 after both reads', (g('NNONE.after2.hit'), g('NNONE.after2.miss'), g('NNONE.after2.outOfRange')), (g('NNONE.after2.hit'), g('NNONE.after2.miss'), g('NNONE.after2.outOfRange')) == ('0', '0', '0'))
chk('NNONE isRowCacheEnabled = false', g('NNONE.isRowCacheEnabled'), g('NNONE.isRowCacheEnabled') == 'false', False)
chk('N10 after read 1: miss=1 hit=0; after read 2: hit=1', (g('N10.after1.miss'), g('N10.after1.hit'), g('N10.after2.hit')), (g('N10.after1.miss'), g('N10.after1.hit'), g('N10.after2.hit')) == ('1', '0', '1'), False)
chk('N1 after read 2: hit=0 outOfRange=1', (g('N1.after2.hit'), g('N1.after2.outOfRange')), (g('N1.after2.hit'), g('N1.after2.outOfRange')) == ('0', '1'), False)
chk('TOMBROWS entry present', g('TOMBROWS.entry'), g('TOMBROWS.entry') == 'present')
chk('TOMBROWS cachedLiveRows = 10', gi('TOMBROWS.cachedLiveRows'), gi('TOMBROWS.cachedLiveRows') == 10)
chk('TOMBROWS rowCount = 60 (> N)', gi('TOMBROWS.rowCount'), gi('TOMBROWS.rowCount') == 60)
chk('TOMBRANGE cachedLiveRows = 10', gi('TOMBRANGE.cachedLiveRows'), gi('TOMBRANGE.cachedLiveRows') == 10)
chk('TOMBRANGE rowCount = 10 and rangeTombstones >= 1', (gi('TOMBRANGE.rowCount'), gi('TOMBRANGE.rangeTombstones')), gi('TOMBRANGE.rowCount') == 10 and (gi('TOMBRANGE.rangeTombstones') or 0) >= 1)
for k in ('NOCK_N1_v100', 'NOCK_N5_v100', 'NOCK_N1_v5000'):
    chk('%s cachedLiveRows = 1 and rowCount = 1' % k, (gi(k + '.cachedLiveRows'), gi(k + '.rowCount')), (gi(k + '.cachedLiveRows'), gi(k + '.rowCount')) == (1, 1))
a, b, c = gi('NOCK_N1_v100.serializedSize'), gi('NOCK_N5_v100.serializedSize'), gi('NOCK_N1_v5000.serializedSize')
if None not in (a, b, c):
    chk('no-clustering: size(N=1) == size(N=5) at v=100 B', (a, b), a == b)
    chk('no-clustering: size(v=5000) - size(v=100) within 4900 +- 300', c - a, 4600 <= c - a <= 5200)
else:
    chk('no-clustering sizes present', (a, b, c), False)
# B2g row
live_ok = all(gi('N%s.cachedLiveRows' % n) == e for n, e in exp_live.items())
over = any((gi('N%s.cachedLiveRows' % n) or 0) > e for n, e in exp_live.items() if n in ('1', '10', '100'))
if g('firsttrigger') != 'OK':
    cls = 'setup error (no entry after the first read): not a refutation'
elif over:
    cls = 'cachedLiveRows > N for some N below 1000: claim wrong (the cap does not bind)'
elif bad_primary == 0:
    cls = 'claim holds (population honours the cap; size follows N; tombstone/ALL/no-clustering overshoots as predicted)'
else:
    cls = 'cachedLiveRows follows N=%s but %d of %d primary checks mismatch: see MISMATCH lines (no row fits unless named in B2g)' % (live_ok, bad_primary, n_primary)
print('CLASS %s | primary mismatches %d of %d' % (cls, bad_primary, n_primary))
