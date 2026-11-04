#!/usr/bin/env python3
"""Cluster tier analysis against B3f (as amended B3i). Usage: analyze_cluster.py <cluster-outdir> [arm ...]"""
import sys, os, json
MiB = 1024 * 1024; KiB = 1024
root = sys.argv[1]; arms = sys.argv[2:] or ['c0', 'c128', 'c512', 'c1024', 'n128', 'c128b']
def ck(arm):
    p = os.path.join(root, arm, 'ckpt.jsonl')
    return {r['name']: r for r in map(json.loads, open(p))} if os.path.exists(p) else {}
def jmx(arm):
    rows = []
    for l in open(os.path.join(root, arm, 'jmx.csv')).read().splitlines()[1:]:
        p = l.split(',')
        if p[0] != 'ERR' and len(p) == 4: rows.append(tuple(int(x) for x in p))
    return rows
fails = []
def chk(name, ok, detail):
    print('RESULT', 'PASS' if ok else 'FAIL', name, detail)
    if not ok: fails.append(name)
C = {a: ck(a) for a in arms}
c0 = C.get('c0', {})
print('arm checkpoint size_MiB capacity_MiB entries RssAnon_MiB est_vs_c0_MiB RssAnon-idle_MiB nmtTotal_MiB')
for a in arms:
    for n, r in C[a].items():
        est = (r['RssAnon_kb'] - c0[n]['RssAnon_kb']) / KiB if n in c0 and a != 'c0' else float('nan')
        print('%s %s %.2f %.0f %s %.1f %.1f %.1f %.1f' % (a, n, r.get('size', -1) / MiB, r.get('capacity', -1) / MiB, r.get('entries'), r['RssAnon_kb'] / KiB, est, (r['RssAnon_kb'] - C[a]['idle']['RssAnon_kb']) / KiB, (r.get('nmt_total_committed_kb') or 0) / KiB))
print()
cap = {'c128': 128, 'c512': 512, 'c1024': 1024, 'c128b': 128}
for a in arms:
    if not C[a]: print('no data for', a); continue
    rows = jmx(a)
    if a == 'c0':
        chk('c0 Size==Capacity==0, Entries==0 at every checkpoint', all(r.get('size') == 0 and r.get('capacity') == 0 and r.get('entries') == 0 for r in C[a].values()), '')
        g = (C[a]['rand']['RssAnon_kb'] - C[a]['idle']['RssAnon_kb']) / KiB
        chk('c0 RssAnon growth idle->rand < 100 MiB', g < 100, 'growth=%.1f MiB' % g)
    elif a == 'n128':
        chk('n128 (rows_per_partition NONE) Size==0, Entries==0', all(r.get('size') == 0 and r.get('entries') == 0 for r in C[a].values()), '')
    else:
        capb = cap[a] * MiB
        chk('%s every JMX sample has Size<=Capacity' % a, all(s <= c for _, s, c, _ in rows if c > 0), 'samples=%d maxSize/Capacity(initial)=%.4f' % (len(rows), max(s for _, s, _, _ in rows) / capb))
        for n in ('pass1', 'pass2', 'rand'):
            r = C[a][n]
            chk('%s %s Size<=Capacity=%dMiB' % (a, n, cap[a]), r['size'] <= r['capacity'] == capb, 'size=%d capacity=%d' % (r['size'], r['capacity']))
            chk('%s %s cache full (Size>=0.97 Capacity: limit reached)' % (a, n), r['size'] >= 0.97 * capb, 'size/cap=%.4f' % (r['size'] / capb))
            chk('%s %s Entries<=Capacity/64KiB' % (a, n), r['entries'] <= capb / (64 * KiB), 'entries=%d bound=%d' % (r['entries'], capb // (64 * KiB)))
        r = C[a]['rand']; est = (r['RssAnon_kb'] - c0['rand']['RssAnon_kb']) * KiB if 'rand' in c0 else None
        if est is not None:
            lo, hi = 0.9 * r['size'], 1.3 * r['size'] + 64 * MiB
            chk('%s est(RssAnon-c0) in [0.9 Size, 1.3 Size+64MiB] at rand' % a, lo <= est <= hi, 'est=%.1f MiB Size=%.1f MiB band=[%.1f,%.1f] MiB' % (est / MiB, r['size'] / MiB, lo / MiB, hi / MiB))
            if cap[a] == 128: chk('%s est < 230 MiB' % a, est < 230 * MiB, 'est=%.1f MiB' % (est / MiB))
        gr = C[a]['rand']['RssAnon_kb'] - C[a]['pass2']['RssAnon_kb']
        print('INFO %s RssAnon growth pass2->rand = %.1f MiB (Size flat: %d -> %d)' % (a, gr / KiB, C[a]['pass2']['size'], C[a]['rand']['size']))
if all(C.get(a) for a in ('c128', 'c512', 'c1024')) and c0:
    e = {a: C[a]['rand']['RssAnon_kb'] - c0['rand']['RssAnon_kb'] for a in ('c128', 'c512', 'c1024')}
    chk('est rises with capacity 128<512<1024', e['c128'] < e['c512'] < e['c1024'], str({k: round(v / KiB, 1) for k, v in e.items()}))
if C.get('c1024') and 'set256' in C['c1024']:
    for n, lim in (('set256', 256), ('set64', 64), ('set1024', 1024)):
        r = C['c1024'][n]; chk('c1024 %s Capacity==%dMiB and Size<=Capacity' % (n, lim), r['capacity'] == lim * MiB and r['size'] <= r['capacity'], 'size=%.2f MiB entries=%d' % (r['size'] / MiB, r['entries']))
    r = C['c1024']
    print('INFO c1024 RssAnon MiB: rand %.1f set256 %.1f set64 %.1f set1024 %.1f rand_after %.1f ; c0 rand %.1f' % tuple([r[n]['RssAnon_kb'] / KiB for n in ('rand', 'set256', 'set64', 'set1024', 'rand_after_set1024')] + [c0['rand']['RssAnon_kb'] / KiB]))
print('\nFAILED CHECKS (%d): %s' % (len(fails), fails))
