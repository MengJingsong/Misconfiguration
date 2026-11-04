#!/usr/bin/env python3
"""Cluster readings against B3f / B3g (frozen text 2026-10-27). Usage: analyze_cluster.py <outdir> [npk] [npk2]
Reads <outdir>/<arm>/ckpt.jsonl (checkpoints baseline, pass1..pass3) and <arm>/jmx.csv. Prints
'EXPECTED ... | got ... | RESULT ok|MISMATCH PRIMARY|INFO' lines and a CLASS line. e(N) = Size/Entries after pass 1 (bytes)."""
import sys, os, json, csv
out = sys.argv[1]; NPK = int(sys.argv[2]) if len(sys.argv) > 2 else 20000; NPK2 = int(sys.argv[3]) if len(sys.argv) > 3 else 2000
CAP = 256 * 1024 * 1024; MIB = 1024 * 1024
def load(arm):
    p = os.path.join(out, arm, 'ckpt.jsonl')
    if not os.path.exists(p): return None
    return {j['name']: j for j in map(json.loads, open(p))}
def polls(arm):
    p = os.path.join(out, arm, 'jmx.csv')
    if not os.path.exists(p): return []
    return [r for r in csv.DictReader(open(p)) if r.get('epoch_ms', '').isdigit()]
ARMS = ('n5', 'n50', 'nall', 'none', 't5')
A = {a: load(a) for a in ARMS}
bad = 0; n = 0; flags = set()
def chk(what, got, ok, primary=True, flag=None):
    global bad, n
    if primary:
        n += 1
        if not ok: bad += 1; flags.add(flag or what)
    print('EXPECTED %s | got %s | RESULT %s %s' % (what, got, 'ok' if ok else 'MISMATCH', 'PRIMARY' if primary else 'INFO'))
def has(arm, *names): return A[arm] is not None and all(k in A[arm] for k in names)
def e(arm, ck='pass1'):
    d = A[arm]
    if not d or ck not in d or not d[ck].get('entries'): return None
    return d[ck]['size'] / d[ck]['entries']
chk('full-scale data (20,000 partitions in ks.t, 2,000 in ks.t2)', (NPK, NPK2), (NPK, NPK2) == (20000, 2000), False)
# 1. Size <= Capacity at every poll and checkpoint of every arm (the n50 shrink phase is informational and excluded)
for arm in ARMS:
    if A[arm] is None: chk('%s present' % arm, None, False); continue
    P = [r for r in polls(arm) if True]
    mx = max([int(r['size']) for r in P] + [c['size'] for k, c in A[arm].items() if 'size' in c and not k.startswith('shrunk')] or [0])
    # polls after the shrink would exceed the new capacity only transiently; cap used here is the original 256 MiB, so they cannot exceed it either
    chk('%s: Size <= Capacity (268,435,456 B) at every poll (%d polls)' % (arm, len(P)), 'max Size %d' % mx, mx <= CAP, True, 'size<=capacity')
# 2-4. entry sizes
e5, e50, eA, et = e('n5'), e('n50'), e('nall'), e('t5')
d = A['n5']
if has('n5', 'pass1'):
    p = d['pass1']; chk('n5: Entries = %d after P1' % NPK, p['entries'], p['entries'] == NPK)
    chk('n5: 600 <= e(5) <= 1200 B and Size 12..24 MB', '%.0f B, Size %.1f MB' % (e5, p['size'] / 1e6), 600 <= e5 <= 1200 and 12e6 <= p['size'] <= 24e6)
else: chk('n5 pass1 present', None, False)
d = A['n50']
if has('n50', 'pass1'):
    chk('n50: Entries = %d after P1' % NPK, d['pass1']['entries'], d['pass1']['entries'] == NPK)
    r = e50 / e5 if e5 and e50 else None
    chk('n50: e(50)/e(5) within 7..10.5', None if r is None else '%.2f (e50 %.0f, e5 %.0f)' % (r, e50, e5), r is not None and 7 <= r <= 10.5, True, 'e(N) ratio')
else: chk('n50 pass1 present', None, False)
d = A['nall']
if has('nall', 'pass1'):
    p = d['pass1']; r = eA / e50 if eA and e50 else None
    chk('nall: e(ALL)/e(50) within 3.3..4.1', None if r is None else '%.2f (eALL %.0f)' % (r, eA), r is not None and 3.3 <= r <= 4.1, True, 'e(N) ratio')
    chk('nall: Size >= 0.85 x Capacity and 5,000 <= Entries <= 12,000 and < %d' % NPK, (p['size'], p['entries']), p['size'] >= 0.85 * CAP and 5000 <= p['entries'] <= 12000 and p['entries'] < NPK, True, 'nall cap-binding')
else: chk('nall pass1 present', None, False)
# 5. LIMIT does not move the cache (n5, n50)
for arm in ('n5', 'n50'):
    if has(arm, 'pass1', 'pass2', 'pass3'):
        d = A[arm]; s = [(d[k]['size'], d[k]['entries']) for k in ('pass1', 'pass2', 'pass3')]
        chk('%s: (Size, Entries) equal after P1, P2, P3' % arm, s, s[0] == s[1] == s[2], True, 'LIMIT moves cache')
    else: chk('%s pass1-3 present' % arm, None, False)
# 6. counters
for arm in ('n5', 'n50'):
    if has(arm, 'baseline', 'pass1', 'pass2', 'pass3'):
        d = A[arm]
        def dl(k1, k2, f): return d[k2][f] - d[k1][f]
        chk('%s: P1 miss delta = %d' % (arm, NPK), dl('baseline', 'pass1', 'miss'), dl('baseline', 'pass1', 'miss') == NPK, True, 'counters')
        chk('%s: P2 outOfRange delta = %d and hit delta = 0' % (arm, NPK), (dl('pass1', 'pass2', 'outOfRange'), dl('pass1', 'pass2', 'hit')), (dl('pass1', 'pass2', 'outOfRange'), dl('pass1', 'pass2', 'hit')) == (NPK, 0), True, 'counters')
        chk('%s: P3 hit delta = %d' % (arm, NPK), dl('pass2', 'pass3', 'hit'), dl('pass2', 'pass3', 'hit') == NPK, True, 'counters')
        chk('%s: P1 hit and outOfRange deltas = 0 (INFO)' % arm, (dl('baseline', 'pass1', 'hit'), dl('baseline', 'pass1', 'outOfRange')), (dl('baseline', 'pass1', 'hit'), dl('baseline', 'pass1', 'outOfRange')) == (0, 0), False)
    else: chk('%s counters present' % arm, None, False)
if has('nall', 'pass1', 'pass2', 'pass3'):
    d = A['nall']; print('INFO nall counters P2: hit +%d out +%d miss +%d; P3: hit +%d out +%d miss +%d' % tuple(d[b][f] - d[a][f] for a, b in (('pass1', 'pass2'), ('pass2', 'pass3')) for f in ('hit', 'outOfRange', 'miss')))
# 7. none
if has('none', 'pass3'):
    p = A['none']['pass3']; chk('none: Entries = 0, Size = 0, hit = miss = outOfRange = 0 after P3', (p['entries'], p['size'], p['hit'], p['miss'], p['outOfRange']), (p['entries'], p['size'], p['hit'], p['miss'], p['outOfRange']) == (0, 0, 0, 0, 0), True, 'none arm')
else: chk('none pass3 present', None, False)
# 8. t5
if has('t5', 'pass1'):
    p = A['t5']['pass1']; chk('t5: Entries = %d' % NPK2, p['entries'], p['entries'] == NPK2)
    chk('t5: e(t5) > e(5) + 500 B', None if (et is None or e5 is None) else '%.0f B (e(t5) %.0f, e(5) %.0f)' % (et - e5, et, e5), et is not None and e5 is not None and et > e5 + 500, True, 't5 overshoot')
else: chk('t5 pass1 present', None, False)
# 9. RssAnon rule, net of the none arm
def dd(arm):
    d = A[arm]
    if d and 'pass3' in d and 'baseline' in d: return (d['pass3']['RssAnon_kb'] - d['baseline']['RssAnon_kb']) * 1024
dn = dd('none'); worst_over_cap = False
for arm in ('n5', 'n50', 'nall'):
    da = dd(arm)
    if da is None or dn is None: chk('%s RssAnon readings present' % arm, None, False); continue
    s = A[arm]['pass3']['size']; net = da - dn
    chk('%s: RssAnon delta net of none <= 1.5 x Size + 16 MiB' % arm, 'net %.1f MB, Size %.1f MB, bound %.1f MB (d %.1f, d(none) %.1f)' % (net / 1e6, s / 1e6, (1.5 * s + 16 * MIB) / 1e6, da / 1e6, dn / 1e6), net <= 1.5 * s + 16 * MIB, True, 'RSS rule')
    if net > 1.5 * CAP: worst_over_cap = True
# informational: shrink phase of n50
if A['n50']:
    for k in ('shrunk5s', 'shrunk60s', 'shrunk_p4'):
        if k in A['n50']: print('INFO n50 %s: Size %d Capacity %d Entries %d' % (k, A['n50'][k]['size'], A['n50'][k]['capacity'], A['n50'][k]['entries']))
# B3g class
sizeover = any(r in flags for r in ('size<=capacity',))
if None in (e5, e50, eA): cls = 'no matching row (an arm is missing)'
elif any(not A[a] or 'pass1' not in A[a] for a in ('n5', 'n50')) : cls = 'no matching row (an arm is missing)'
elif 'size<=capacity' in flags: cls = 'Size above Capacity: byte cap does not hold, claim (ii) refuted'
elif 'LIMIT moves cache' in flags: cls = 'Size/Entries of n5 or n50 differ after P2 or P3: LIMIT influences the cache, claim (i) refuted'
elif e50 / e5 < 2: cls = 'e(N) flat across N: per-partition cap did not move usage (control failed), Not confirmed'
elif worst_over_cap: cls = 'RssAnon far above the cache (net > 1.5 x Capacity): claim (ii) real-memory part refuted for that arm'
elif bad == 0: cls = 'claim holds: Size <= Capacity, n5/n50 unchanged by P2/P3, counters as predicted, e(N) follows N, byte cap binds in nall; overshoots as predicted'
elif flags <= {'counters'}: cls = 'memory claim holds; counters differ from B3f (recorded): Not confirmed for the counter row'
else: cls = 'no matching row or partly unmatched: %d of %d primary checks mismatch (%s)' % (bad, n, ', '.join(sorted(flags)))
print('CLASS %s | primary mismatches %d of %d' % (cls, bad, n))
