#!/usr/bin/env python3
"""Independent re-parse of the raw run-1 files of max_recursive_key_length-addterm-term--autonomous against the FROZEN predictions (case file amendments U2-U4, C1-C3).
usage: selfcheck.py <run1 dir containing unit/unit.out and cluster/<label>/...>"""
import os, re, sys
R = sys.argv[1]; res = []
def chk(name, ok, detail=''):
    res.append(ok); print('%s %s %s' % ('PASS' if ok else 'FAIL', name, detail))
T = {}; G = {}; lab = None
for l in open(R + '/unit/unit.out'):
    m = re.match(r'== (\S+) ', l)
    if m: lab = m.group(1)
    if l.startswith('STAGE4 TERM'): T[lab] = dict(re.findall(r'(\w+)=(\S+)', l))
    if l.startswith('STAGE4 GUARDTERM'): G.setdefault(lab, []).append(dict(re.findall(r'(\w+)=(\S+)', l)))
Ls = (64, 128, 129, 256, 2048, 7000)
chk('unit: 180 TERM lines (6 L x 2 passes x 5 builds x 3 repetitions)', len(T) == 180, 'n=%d' % len(T))
def t(L, p, ov, r=1): return T['%s-L%d-ov%s-r%d' % (p, L, ov, r)]
# (e) repetitions identical (sumAdd, onHeap)
bad = [(L, p, ov, r) for L in Ls for p in ('N20000', 'EQ') for ov in ('-', 'z0', 'z1', 'instr', 'zi0') for r in (2, 3)
       if t(L, p, ov, 1)['result'] == 'OK' and (t(L, p, ov, 1)['sumAdd'] != t(L, p, ov, r)['sumAdd'] or t(L, p, ov, 1)['onHeap'] != t(L, p, ov, r)['onHeap'])]
chk('3 repetitions agree on sumAdd/onHeap for every completed (L, pass, build)', not bad, str(bad[:5]))
sbad = [(L, p, r, t(L, p, 'z1', r)['done']) for L in (2048, 7000) for p in ('N20000', 'EQ') for r in (1, 2, 3)]
print('NOTE z1 SOE depth (terms completed before the overflow) by repetition: %s' % sbad)
# (a) routes
for L in Ls:
    for p in ('N20000', 'EQ'):
        x = t(L, p, 'instr'); n = int(x['N'])
        want = (n, 0) if L <= 128 else (0, n)
        chk('(a) instr counters L=%d %s: recursive/apply = %s' % (L, p, want), (int(x['routeRec']), int(x['routeApply'])) == want, '%s/%s' % (x['routeRec'], x['routeApply']))
        z = t(L, p, 'zi0'); chk('(a) zi0 (constant 0) L=%d %s: all terms on the apply route' % (L, p), (int(z['routeRec']), int(z['routeApply'])) == (0, int(z['N'])))
# (b) 129/128
for p in ('N20000', 'EQ'):
    r = float(t(129, p, '-')['perTermAdd']) / float(t(128, p, '-')['perTermAdd'])
    chk('(b) per-term bytes ratio L=129 / L=128 in [0.95,1.05] (%s, stock)' % p, 0.95 <= r <= 1.05, 'measured %.4f' % r)
    r = float(t(129, p, '-')['perTermTrie']) / float(t(128, p, '-')['perTermTrie'])
    chk('(b) trie bytes per term (sizeOn+sizeOff) ratio 129/128 in [0.95,1.05] (%s)' % p, 0.95 <= r <= 1.05, 'measured %.4f' % r)
# (c) z0, z1
for ov in ('z0', 'z1'):
    for L in Ls:
        for p in ('N20000', 'EQ'):
            s, x = t(L, p, '-'), t(L, p, ov)
            if x['result'] == 'SOE':
                print('NOTE %s L=%d %s: StackOverflowError after %s terms (stack resource, excluded from the memory comparison)' % (ov, L, p, x['done'])); continue
            d = abs(float(x['perTermAdd']) - float(s['perTermAdd'])) / float(s['perTermAdd'])
            chk('(c) %s per-term bytes within 1%% of stock (L=%d %s)' % (ov, L, p), d <= 0.01, 'diff %.4f%%' % (100 * d))
soe = sorted({(L) for L in Ls for p in ('N20000', 'EQ') if t(L, p, 'z1')['result'] == 'SOE'})
print('NOTE z1 StackOverflowError at L = %s (U3 predicted it possible for L >= 2048)' % soe)
chk('U3: z1 StackOverflowError occurs only at L >= 2048', all(L >= 2048 for L in soe))
chk('U3: stock, z0, instr, zi0 never overflow', all(x['result'] == 'OK' for k, x in T.items() if '-ovz1-' not in k))
# (d) guardrail control
for k, rows in G.items():
    by = {r['L']: r for r in rows}
    chk('(d) %s: 900 B terms grow the trie, 1500 B and 7000 B terms return 0 and do not change sizes' % k, int(by['900']['addsWithGrowth']) == 2000 and all(int(by[x]['addsWithGrowth']) == 0 and int(by[x]['sumAdd']) == 0 and int(by[x]['dOnHeap']) == 0 and int(by[x]['dOffHeap']) == 0 for x in ('1500', '7000')))
chk('(d) guardrail control ran 3 times', len(G) == 3, str(sorted(G)))
# ---------------- cluster ----------------
def rd(label):
    d = R + '/cluster/' + label
    if not os.path.exists(d + '/readings.txt'): return None
    s = open(d + '/readings.txt').read()
    mi = re.search(r'MEMTABLE_INDEX_BYTES .*?Value\|(\d+)', s); 
    if not mi: return None
    return dict(mib=int(mi.group(1)), ds=int(re.search(r'Memtable data size: (\d+)', s).group(1)), cells=int(re.search(r'Memtable cell count: (\d+)', s).group(1)), flush=int(re.search(r'FLUSHES_DURING_RUN (\d+)', s).group(1)),
                over=int(re.search(r'OVERSIZE_WARNINGS (\d+)', s).group(1)), heap=int(re.findall(r'heapUsedAfterGC_kB=(\d+)', s)[-1]), rss=int(re.findall(r'RssAnon_kB=(\d+)', s)[-1]))
labels = ['SH100', 'SH128', 'SH129', 'SH400', 'SH129b', 'SH129c', 'ZH100', 'ZH128', 'ZH129', 'ZH400', 'SO128', 'ZO128', 'SO129', 'ZO129', 'CTL1500']
C = {k: rd(k) for k in labels}
for k, v in C.items():
    print('NOTE cluster %s: %s' % (k, v if v else 'missing'))
if all(C[k] for k in ('SH128', 'SH129', 'SH100', 'SH400')):
    chk('flush disabled by size: no flush during any run', all(v['flush'] == 0 for v in C.values() if v))
    r = C['SH129']['mib'] / C['SH128']['mib']
    chk('C3 MemtableIndexBytes(L=129)/(L=128) in [0.95,1.05] (equal payload, stock heap)', 0.95 <= r <= 1.05, 'measured %.4f' % r)
    for L in (100, 128, 129, 400):
        if C.get('ZH%d' % L):
            d = abs(C['ZH%d' % L]['mib'] - C['SH%d' % L]['mib']) / C['SH%d' % L]['mib']
            chk('C3 stock vs Z (constant 0) within 3%% at L=%d (heap)' % L, d <= 0.03, 'diff %.2f%%' % (100 * d))
    if C.get('SH129b') and C.get('SH129c'):
        v = [C[k]['mib'] for k in ('SH129', 'SH129b', 'SH129c')]
        chk('C3 the three S-H L=129 repeats within 3% of each other', (max(v) - min(v)) / min(v) <= 0.03, str(v))
    for L in (128, 129):
        for a, b in (('SO', 'SH'), ('ZO', 'ZH')):
            pass
    if C.get('CTL1500') and C.get('SH400'):
        chk('C3 control: MemtableIndexBytes after the 1500-byte-term run < 10% of the L=400 run', C['CTL1500']['mib'] < 0.1 * C['SH400']['mib'], '%d vs %d' % (C['CTL1500']['mib'], C['SH400']['mib']))
        chk('C3 control: Memtable data size above the L=400 run', C['CTL1500']['ds'] > C['SH400']['ds'], '%d vs %d' % (C['CTL1500']['ds'], C['SH400']['ds']))
        chk('C3 control: oversize-term warnings present in system.log', C['CTL1500']['over'] > 0, str(C['CTL1500']['over']))
print('SUMMARY pass=%d fail=%d' % (sum(res), len(res) - sum(res)))
