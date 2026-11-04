#!/usr/bin/env python3
"""Cluster readings against B3f / B3g (as amended 2026-10-26, frozen text). Usage: analyze_cluster.py <outdir> [npk] [npk2]
Reads <outdir>/<arm>/ckpt.jsonl (checkpoints baseline, pass1, pass2). Prints 'EXPECTED ... | got ... | RESULT ok|MISMATCH PRIMARY|INFO' lines and a CLASS line.
r = 1.05 KiB = 1075.2 B. e(N) = Size/Entries after pass 1."""
import sys, os, json
out = sys.argv[1]; NPK = int(sys.argv[2]) if len(sys.argv) > 2 else 10000; NPK2 = int(sys.argv[3]) if len(sys.argv) > 3 else 2000
R = 1.05 * 1024; MIB = 1024 * 1024
def load(arm):
    p = os.path.join(out, arm, 'ckpt.jsonl')
    if not os.path.exists(p): return None
    return {j['name']: j for j in map(json.loads, open(p))}
A = {a: load(a) for a in ('n1', 'n10', 'n100', 'nall', 't10', 'none', 'c32')}
bad = 0; n = 0
def chk(what, got, ok, primary=True):
    global bad, n
    if primary:
        n += 1
        if not ok: bad += 1
    print('EXPECTED %s | got %s | RESULT %s %s' % (what, got, 'ok' if ok else 'MISMATCH', 'PRIMARY' if primary else 'INFO'))
def e(arm, ck='pass1'):
    d = A[arm]
    if not d or ck not in d or not d[ck].get('entries'): return None
    return d[ck]['size'] / d[ck]['entries']
chk('full-scale data (10,000 partitions in ks.t, 2,000 in ks.t2)', (NPK, NPK2), (NPK, NPK2) == (10000, 2000), False)
for arm, N in (('n1', 1), ('n10', 10), ('n100', 100)):
    v = e(arm)
    chk('%s: 0.75 <= e / (N x 1.05 KiB) <= 1.4' % arm, None if v is None else '%.2f (e = %.0f B)' % (v / (N * R), v), v is not None and 0.75 <= v / (N * R) <= 1.4)
v_all = e('nall')
chk('nall: 250 KiB <= e <= 400 KiB', None if v_all is None else '%.0f KiB' % (v_all / 1024), v_all is not None and 250 * 1024 <= v_all <= 400 * 1024)
if v_all and e('n100'): chk('nall: e(ALL)/e(100) in 2.4..3.8', '%.2f' % (v_all / e('n100')), 2.4 <= v_all / e('n100') <= 3.8)
else: chk('nall: e(ALL)/e(100) in 2.4..3.8', None, False)
for arm, lo_hi in (('n1', None), ('n10', None)):
    d = A[arm]
    if d and 'pass1' in d: chk('%s: Entries = %d after pass 1, Size about %d MB' % (arm, NPK, NPK * (1.2 if arm == 'n1' else 10.6) * 1024 / 1e6), (d['pass1']['entries'], round(d['pass1']['size'] / 1e6, 1)), d['pass1']['entries'] == NPK, False)
for arm, emax in (('n100', 2600), ('nall', 850)):
    d = A[arm]
    if d and 'pass1' in d:
        p = d['pass1']
        chk('%s: Size <= 256 MiB, Entries <= %d and < %d (cap binds)' % (arm, emax, NPK), (p['size'], p['entries']), p['size'] <= 256 * MIB and p['entries'] <= emax and p['entries'] < NPK)
    else: chk('%s present' % arm, None, False)
for arm in ('n1', 'n10', 'n100', 'nall'):
    d = A[arm]
    if d and 'pass1' in d and 'baseline' in d:
        delta = (d['pass1']['RssAnon_kb'] - d['baseline']['RssAnon_kb']) * 1024; s = d['pass1']['size']; tol = max(0.2 * s, 16 * MIB)
        chk('%s: RssAnon delta within max(20%% of Size, 16 MiB) of Size' % arm, 'delta %.1f MB, Size %.1f MB, tol %.1f MB' % (delta / 1e6, s / 1e6, tol / 1e6), abs(delta - s) <= tol)
    else: chk('%s RssAnon readings present' % arm, None, False)
d = A['n10']
if d and 'pass2' in d:
    h = d['pass2']['hit'] - d['pass1']['hit']
    chk('n10: pass-2 hits >= 95%% of %d and no HitOutOfRange' % NPK, (h, d['pass2']['outOfRange']), h >= 0.95 * NPK and d['pass2']['outOfRange'] == 0)
else: chk('n10 pass 2 present', None, False)
d = A['n1']
if d and 'pass2' in d:
    chk('n1: no hit in either pass; pass-2 HitOutOfRange >= 95%% of %d' % NPK, (d['pass2']['hit'], d['pass2']['outOfRange'] - d['pass1']['outOfRange']), d['pass2']['hit'] == 0 and d['pass2']['outOfRange'] - d['pass1']['outOfRange'] >= 0.95 * NPK)
else: chk('n1 pass 2 present', None, False)
t, b = e('t10'), e('n10')
chk('t10: e(t10) - e(n10) >= 2 KiB', None if (t is None or b is None) else '%.0f B (e(t10) = %.0f, e(n10) = %.0f)' % (t - b, t, b), t is not None and b is not None and t - b >= 2048)
d = A['none']
if d and 'pass2' in d:
    p = d['pass2']; chk('none: Entries = 0, Size = 0, Hit = Miss = 0 after both passes', (p['entries'], p['size'], p['hit'], p['miss']), (p['entries'], p['size'], p['hit'], p['miss']) == (0, 0, 0, 0))
else: chk('none present', None, False)
d = A['c32']
if d and 'pass1' in d:
    p = d['pass1']; chk('c32 (positive control): Size <= 32 MiB, Entries <= 330 and < %d' % NPK, (p['size'], p['entries']), p['size'] <= 32 * MIB and p['entries'] <= 330 and p['entries'] < NPK)
else: chk('c32 present', None, False)
for arm in ('n1', 'n10', 'n100', 'nall', 'none', 'c32', 't10'):
    d = A[arm]
    if d and 'pass1' in d:
        exp = 5 * (NPK2 if arm == 't10' else NPK); chk('%s: pass 1 returned %d rows (LIMIT 5)' % (arm, exp), d['pass1'].get('rows_returned'), d['pass1'].get('rows_returned') == exp, False)
# B3g row
v1, v10, v100 = e('n1'), e('n10'), e('n100')
if None in (v1, v10, v100, v_all): cls = 'no matching row (an arm is missing)'
elif bad == 0: cls = 'bytes/entry about proportional to N below the byte cap; Size <= 256 MiB: claim holds (ALL, tombstone and positive-control rows as predicted)'
elif v10 / v1 < 2: cls = 'bytes/entry independent of N: claim wrong'
else: cls = 'no matching row: %d of %d primary checks mismatch' % (bad, n)
print('CLASS %s | primary mismatches %d of %d' % (cls, bad, n))
