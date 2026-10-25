#!/usr/bin/env python3 -I
"""PASS/FAIL of the frozen unit predictions (case file B2i.6, sha256 in results §1). Usage: analyze_unit.py <plain-raw-dir> [<byteman-raw-dir>]"""
import sys, os
def cap(n):
    if n == 0: return 0
    c = 5
    while c < n: c *= 2
    return c
plain = sys.argv[1]; bm = sys.argv[2] if len(sys.argv) > 2 else None
rows = [l.strip().split(',') for l in open(os.path.join(plain, 'raw.csv')) if l.strip() and not l.startswith('#')]
res = []
def chk(name, ok, detail=''):
    res.append((name, ok)); print(('PASS ' if ok else 'FAIL ') + name + ('  ' + detail if detail else ''))
byk = {}
for r in rows:
    if r[0] == 'buildup':
        k, sl, ln = int(r[1]), int(r[6]), int(r[7]); chk('U1 buildup K=%d' % k, sl == cap(k) and ln == k, 'stack.length=%d expected %d' % (sl, cap(k)))
refill_len = {}
for r in rows:
    if r[0] != 'refill': continue
    k, m, p, q, rr = map(int, r[1:6]); capb, lenb, mcb, sl, ln, mcl, refills, sch, mch = map(int, r[6:15]); fs = r[15] == 'true'
    grow = (p + m) > cap(k + m)
    exp_sl = p + m if grow else cap(k + m)
    ok = (sl == exp_sl and ln == p + m and refills == rr and sch == (1 if grow else 0) and mcl == 1 + q and mch == q and fs and capb == cap(k + m))
    chk('U2 refill K=%d M=%d P=%d Q=%d R=%d' % (k, m, p, q, rr), ok,
        'stack.length=%d (exp %d) changes=%d (exp %d) mc.length=%d (exp %d) mcChanges=%d (exp %d) refills=%d' % (sl, exp_sl, sch, 1 if grow else 0, mcl, 1 + q, mch, q, refills))
    refill_len.setdefault((k, m, p, q), {})[rr] = sl
for key, d in refill_len.items():
    chk('U3 R-independence K,M,P,Q=%s' % (key,), len(set(d.values())) == 1 and set(d) == {1, 10, 1000}, str(d))
hs = [r for r in rows if r[0] == 'heapstack']
for r in hs:
    sl, di, dr = int(r[3]), int(r[4]), int(r[5]); ratio = di / dr if dr else float('nan')
    chk('U4 heap K=1000000 rep=%s' % r[2], sl == cap(1000000) and 0.8 <= ratio <= 1.25, 'cap=%d iterator delta=%d Object[] delta=%d ratio=%.3f' % (sl, di, dr, ratio))
ctl = {r[1]: r for r in rows if r[0] == 'control'}
prev = 0
for n in (20000, 80000, 160000):
    r = ctl.get('ctl_%d' % n)
    if not r: chk('U5 ctl_%d present' % n, False); continue
    held, oom, d, sl = int(r[3]), r[4] == 'true', int(r[5]), int(r[6])
    chk('U5 control N=%d' % n, held == n and not oom and 0.9 * n * 1024 <= d <= 2.0 * n * 1024 and d > prev and sl == 6,
        'held=%d delta=%d (%.2f x N*1KiB) stack.length=%d' % (held, d, d / (n * 1024), sl)); prev = d
r = ctl.get('ctl_cap')
if r:
    held, oom, d, sl, mx = int(r[3]), r[4] == 'true', int(r[5]), int(r[6]), int(r[7])
    mib = held * 1024 / 2**20
    chk('U5 ctl_cap (OOM at Xmx=%d MiB)' % (mx // 2**20), oom and 200 <= mib <= 512 and sl == 5, 'rows held=%d (~%.0f MiB of 1 KiB values) oom=%s stack.length=%d' % (held, mib, oom, sl))
else: chk('U5 ctl_cap present', False)
if bm:
    tot = [l for l in open(os.path.join(bm, 'raw.csv')) if l.startswith('# TOTAL')][0]
    kv = dict(x.split('=') for x in tot.split()[2:])
    S = G = 0
    for l in open(os.path.join(bm, 'trace.txt')):
        if l.startswith('S '): S += 1
        elif l.startswith('G '): G += 1
    chk('B Byteman S count (line 94 entries) == 2 x refills', S == int(kv['splice_calls_expected']), 'S=%d expected %s' % (S, kv['splice_calls_expected']))
    chk('B Byteman G count (line 95 grows) == identity changes', G == int(kv['grow_expected']), 'G=%d expected %s' % (G, kv['grow_expected']))
print('SUMMARY %d PASS, %d FAIL' % (sum(1 for _, o in res if o), sum(1 for _, o in res if not o)))
