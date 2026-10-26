#!/usr/bin/env python3
"""Unit tier: PASS/FAIL per frozen prediction (B2f) with EXPECTED/GOT lines. Usage: analyze_unit.py <unit-results.csv>"""
import csv, sys
R = {}
for r in csv.DictReader(open(sys.argv[1])):
    R[(r['mode'], int(r['L']), int(r['N']))] = r
def S(m, L, N): return int(R[(m, L, N)]['sum_estimate'])
out = []
def chk(name, ok, exp, got):
    out.append(ok)
    print('%s %s\n  EXPECTED: %s\n  GOT: %s' % ('PASS' if ok else 'FAIL', name, exp, got))
for m in ('PREFIX', 'CONTAINS'):
    for L in (100, 512, 1022, 1023, 1):
        for (mm, LL, N), r in R.items():
            if mm == m and LL == L:
                chk('%s L=%d N=%d accepted and found' % (m, L, N), int(r['accepted_adds']) == N and r['found_first'] == 'true' and r['found_last'] == 'true' and int(r['cant_add_logs']) == 0,
                    'accepted=N, found first and last, 0 logs', 'accepted=%s found=%s,%s logs=%s' % (r['accepted_adds'], r['found_first'], r['found_last'], r['cant_add_logs']))
    for L in (1024, 1025, 4096):
        r = R[(m, L, 10)]
        chk('%s L=%d rejected' % (m, L), int(r['accepted_adds']) == 0 and int(r['sum_estimate']) == 0 and r['found_first'] == 'false' and int(r['cant_add_logs']) == 10,
            '0 accepted, size 0, not found, 10 info logs', 'accepted=%s size=%s found=%s logs=%s' % (r['accepted_adds'], r['sum_estimate'], r['found_first'], r['cant_add_logs']))
p1 = S('PREFIX', 1023, 1); c1 = S('CONTAINS', 1023, 1)
chk('PREFIX L=1023 per term in [3300, 7500]', 3300 <= p1 <= 7500, '3300..7500', p1)
chk('PREFIX L=512 / L=1023 in [0.45, 0.65]', 0.45 <= S('PREFIX', 512, 1) / p1 <= 0.65, '0.45..0.65', round(S('PREFIX', 512, 1) / p1, 3))
chk('CONTAINS L=1023 per term in [1.0e6, 5e6]', 1.0e6 <= c1 <= 5e6, '1.0e6..5e6', c1)
chk('CONTAINS L=1023 >= 150 x PREFIX (and not < 10x)', c1 >= 150 * p1, '>=150', round(c1 / p1, 1))
chk('CONTAINS L=512 / L=1023 in [0.15, 0.40]', 0.15 <= S('CONTAINS', 512, 1) / c1 <= 0.40, '0.15..0.40', round(S('CONTAINS', 512, 1) / c1, 3))
for m, L, Ns in (('PREFIX', 100, (10, 100)), ('PREFIX', 512, (10, 100)), ('PREFIX', 1023, (10, 100)), ('CONTAINS', 100, (10, 100)), ('CONTAINS', 512, (10, 100)), ('CONTAINS', 1023, (10, 30))):
    for N in Ns:
        ratio = S(m, L, N) / S(m, L, 1)
        chk('%s L=%d total(N=%d)/total(1) in [0.7N, 2N]' % (m, L, N), 0.7 * N <= ratio <= 2 * N, '%.1f..%d' % (0.7 * N, 2 * N), round(ratio, 2))
for m in ('PREFIX', 'CONTAINS'):
    for L in (100, 512, 1023):
        n2 = 30 if (m == 'CONTAINS' and L == 1023) else 100
        chk('%s L=%d no plateau: total grows with N' % (m, L), S(m, L, 1) < S(m, L, 10) < S(m, L, n2), 'N=1 < N=10 < N=%d' % n2, (S(m, L, 1), S(m, L, 10), S(m, L, n2)))
for N in (10, 100):
    chk('SKIPLIST control moves with N', S('SKIPLIST', 4, 1) < S('SKIPLIST', 4, N), 'size(1) < size(%d)' % N, (S('SKIPLIST', 4, 1), S('SKIPLIST', 4, N)))
# heap (indicative)
for key in (('PREFIX', 1023, 100), ('CONTAINS', 512, 100), ('CONTAINS', 1023, 30)):
    r = R[key]; e = int(r['sum_estimate']); h = int(r['heap_delta_bytes'])
    print('INFO heap %s: estimate %d, heap delta %d, ratio estimate/heap %.2f (indicative, within about 2 predicted)' % (key, e, h, e / h))
print('RESULT', 'ALL PASS' if all(out) else 'SOME FAIL', sum(out), '/', len(out))
