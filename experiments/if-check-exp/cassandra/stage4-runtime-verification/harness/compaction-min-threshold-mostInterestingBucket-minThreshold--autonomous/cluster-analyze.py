#!/usr/bin/env python3
"""Judge B3f/B3g (with amendments C3-C5) from the arms' phase-*.json.   usage: cluster-analyze.py <outdir containing m2 m4 m16 m32 mm4>"""
import sys, json, os
O = sys.argv[1]
def ph(arm, tag):
    p = f'{O}/{arm}/phase-{tag}.json'
    return json.load(open(p)) if os.path.exists(p) else None
res = []
def chk(name, ok, detail): res.append((name, ok, detail)); print(('PASS ' if ok else 'FAIL ') + name + ' :: ' + detail)
E = {a: ph(a, 'end') for a in ('m2', 'm4', 'm16', 'm32', 'mm4')}
for a, e in E.items():
    if e is None: print('MISSING arm', a); continue
    print(f"{a}: sstables={e['tablestats']['sstables']} files={e['dataFiles']} tableBytes={e['tableBytes']} bloom={e['tablestats']['bloomOffHeap']} summary={e['tablestats']['summaryOffHeap']} history={e['historyRows']} trace={e['traceBucketLines']} rssAnon={e['rssAnon']} heap={e['liveHeapHistogram']}")
    idle = json.load(open(f'{O}/{a}/idle-end.json')); print(f"   idle reached={idle['idleReached']} after {idle['idleSeconds']} s")
if all(E[a] for a in ('m2', 'm4', 'm16', 'm32')):
    n = {a: E[a]['tablestats']['sstables'] for a in ('m2', 'm4', 'm16', 'm32')}
    b = {a: E[a]['tableBytes'] for a in ('m2', 'm4', 'm16', 'm32')}
    bl = {a: E[a]['tablestats']['bloomOffHeap'] for a in n}; sm = {a: E[a]['tablestats']['summaryOffHeap'] for a in n}
    chk('every arm idle at end-state', all(json.load(open(f'{O}/{a}/idle-end.json'))['idleReached'] for a in n), str({a: json.load(open(f'{O}/{a}/idle-end.json'))['idleReached'] for a in n}))
    chk('B3f M=2 and M=4: count <= 4 (filed: under 8)', n['m2'] <= 4 and n['m4'] <= 4, f"m2={n['m2']} m4={n['m4']}")
    chk('B3f/C5 M=16: count 5 (filed: <= ~15)', n['m16'] == 5, f"m16={n['m16']} (row governed by <= 15: {n['m16'] <= 15})")
    chk('B3f/C5 M=32: exactly 20 sstables, zero compaction history rows', n['m32'] == 20 and E['m32']['historyRows'] == 0, f"count={n['m32']} history={E['m32']['historyRows']}")
    ms = ('m2', 'm4', 'm16', 'm32')
    chk('B3f count non-decreasing in M', all(n[x] <= n[y] for x, y in zip(ms, ms[1:])), str(n))
    chk('B3f bloom filter and index summary memory non-decreasing in M', all(bl[x] <= bl[y] and sm[x] <= sm[y] for x, y in zip(ms, ms[1:])), f'bloom={bl} summary={sm}')
    chk('B3f/C5 bytes M=32 >= 3 x M=2 (expected 8-20)', b['m32'] >= 3 * b['m2'], f"m32={b['m32']} m2={b['m2']} ratio={b['m32']/max(b['m2'],1):.2f}")
    chk('B3f bytes non-decreasing in M', all(b[x] <= b[y] for x, y in zip(ms, ms[1:])), str(b))
    F = ph('m32', 'flip')
    if F:
        chk('C4a flip 32 -> 4/32: count falls to <= 5', F['tablestats']['sstables'] <= 5, f"count={F['tablestats']['sstables']} (from {n['m32']})")
        chk('C4a flip: bytes fall below the M=32 end-state by the duplicate fraction (>= 3x)', F['tableBytes'] * 3 <= b['m32'], f"before={b['m32']} after={F['tableBytes']}")
    else: print('MISSING flip')
    if E['mm4']: chk('B3e(6) min 4/max 4 arm: count < 20', E['mm4']['tablestats']['sstables'] < 20, f"count={E['mm4']['tablestats']['sstables']}")
ok = all(r[1] for r in res)
print('SUMMARY', 'ALL PASS' if ok else 'FAILURES: ' + ', '.join(r[0] for r in res if not r[1]))
