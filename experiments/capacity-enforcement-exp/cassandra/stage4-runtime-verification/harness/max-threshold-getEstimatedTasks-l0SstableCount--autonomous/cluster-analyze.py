#!/usr/bin/env python3
"""Judge B3f/B3g with amendments C5-C7 from <outdir>/<arm>/phase-{A,B}.json, write.json.   usage: cluster-analyze.py <outdir>"""
import sys, json, os, math
def byte_term(b, size=160 * 1048576):
    return int(math.ceil(max(0, b - int(4 * size * 1.001)) / float(size)))
O = sys.argv[1]
ARMS = {'mt4': 4, 'mt32': 32, 'mt128': 128, 'mt32b': 32, 'c64': 32, 'd32': 32}
D = {}
for a in ARMS:
    p = f'{O}/{a}/phase-A.json'
    if os.path.exists(p):
        D[a] = {'A': json.load(open(p)), 'B': json.load(open(f'{O}/{a}/phase-B.json')), 'w': json.load(open(f'{O}/{a}/write.json'))}
res = []
def chk(name, ok, detail): res.append((name, ok)); print(('PASS ' if ok else 'FAIL ') + name + ' :: ' + detail)
print('arm   mt  | L0  pend base | tableBytes  dataDirBytes  rssAnon     liveHeap  | B: L0 pend tableBytes rssAnon liveHeap')
for a, d in D.items():
    A, B = d['A'], d['B']
    print(f"{a:6}{ARMS[a]:4} | {A['tablestats']['levels'][0]:4} {A['pending']:4} {d['w']['baselinePending']:3} | {A['tableBytes']:11} {A['dataDirBytes']:12} {A['rssAnon']:11} {A['liveHeapHistogram']:9} | {B['tablestats']['levels'][0]:4} {B['pending']:4} {B['tableBytes']:11} {B['rssAnon']:11} {B['liveHeapHistogram']:9}")
need = ['mt4', 'mt32', 'mt128', 'mt32b', 'c64', 'd32']
chk('all six arms present', all(a in D for a in need), str([a for a in need if a not in D]))
if not all(a in D for a in need): print('SUMMARY INCOMPLETE'); sys.exit(1)
# the estimate follows L0/max_threshold (phase A)
for a in need:
    A = D[a]['A']; l0 = A['tablestats']['levels'][0]; mt = ARMS[a]
    bt = byte_term(A['tablestats']['levelBytes'][0]); lt = 0 if a == 'd32' else l0 // mt; want = lt + bt
    chk(f'{a}: pending - baseline = {"byte term only (STCS-in-L0 off)" if a == "d32" else "floor(L0/max_threshold) + byte term"}', A['pending'] - D[a]['w']['baselinePending'] == want, f"pending={A['pending']} L0={l0} mt={mt} stcsTerm={lt} byteTerm={bt} want={want}")
    chk(f'{a}: no merging before phase A end (sstables == L0)', A['tablestats']['sstables'] == l0, f"sstables={A['tablestats']['sstables']} L0={l0}")
# flatness (C6): spread across mt4, mt32, mt128 within 10% and within 2 x |mt32 - mt32b| + 2% of the mean
for key, label in (('tableBytes', 'table file bytes'), ('dataDirBytes', 'data dir bytes'), ('rssAnon', 'RssAnon'), ('liveHeapHistogram', 'live heap (histogram)')):
    v = {a: D[a]['A'][key] for a in ('mt4', 'mt32', 'mt128')}
    mean = sum(v.values()) / 3; sp = max(v.values()) - min(v.values()); noise = abs(D['mt32']['A'][key] - D['mt32b']['A'][key])
    ok = sp <= 0.10 * mean and sp <= 2 * noise + 0.02 * mean
    chk(f'phase A flat: {label}', ok, f'{v} spread={sp} ({100*sp/mean:.2f}% of mean) noise(mt32 vs mt32b)={noise} limit10%={0.1*mean:.0f} limitNoise={2*noise+0.02*mean:.0f}')
# positive control (C7)
l0b = {a: D[a]['B']['tablestats']['levels'][0] for a in need}
chk('positive control moves: phase B L0 of c64 < half of mt32 and mt32b', l0b['c64'] < 0.5 * min(l0b['mt32'], l0b['mt32b']), str(l0b))
# phase B differences, reported (not part of the line-655 verdict, C6)
for key, label in (('tableBytes', 'table file bytes'), ('rssAnon', 'RssAnon'), ('liveHeapHistogram', 'live heap'), ):
    v = {a: D[a]['B'][key] for a in ('mt4', 'mt32', 'mt128')}
    mean = sum(v.values()) / 3; sp = max(v.values()) - min(v.values())
    print(f'INFO phase B {label}: {v} spread={100*sp/mean:.2f}% of mean')
print('INFO phase B L0 count by arm:', l0b)
print('SUMMARY', 'ALL PASS' if all(r[1] for r in res) else 'FAILURES: ' + '; '.join(r[0] for r in res if not r[1]))
