#!/usr/bin/env python3
"""Judge B3f/B3g (amended 2026-10-26) from the per-arm directories.   usage: cluster-analyze.py <outdir>   (arms n d w wc under it)
Re-parses the raw files (samples.jsonl, compactionhistory.txt, compaction-lines.txt, presizes.json, phase-end.json). Exit 0 always."""
import sys, os, re, json
O = sys.argv[1]
res = []
def chk(name, ok, detail, kind='B3f'): res.append((kind, name, ok)); print(('PASS ' if ok else 'FAIL ') + f'[{kind}] ' + name + ' :: ' + detail)
A = {}
def arm(a):
    d = os.path.join(O, a)
    pre = json.load(open(d + '/presizes.json')); pe = json.load(open(d + '/phase-end.json'))
    S = [json.loads(l) for l in open(d + '/samples.jsonl') if l.strip()]
    S = [s for s in S if 'error' not in s]
    comp = [s for s in S if s['phase'] in ('compact', 'hold')]
    base_all, base_data = pe['pre']['all'], pe['pre']['data']
    pk_all = max(s['all'] for s in comp) - base_all; pk_data = max(s['data'] for s in comp) - base_data
    rss = [s['rssAnon'] for s in S if s['phase'] == 'compact' and s.get('rssAnon')]
    rss_base = [s['rssAnon'] for s in S if s['phase'] == 'load' and s.get('rssAnon')]
    hist = []
    for l in open(d + '/compactionhistory.txt'):
        p = l.split()
        if len(p) >= 7 and 'standard1' in p:
            i = p.index('standard1'); hist.append({'id': p[0], 'bytes_in': int(p[i + 2]), 'bytes_out': int(p[i + 3])})
    inputs = {}
    for l in open(d + '/compaction-lines.txt'):
        m = re.search(r'Compacting \(([0-9a-f-]{36})\) \[(.*)\]', l)
        if m: inputs[m.group(1)] = m.group(2).count(':level=')
    for h in hist: h['inputs'] = inputs.get(h['id'])
    buckets = [l for l in open(d + '/compaction-lines.txt') if 'Compaction buckets are' in l]
    A[a] = {'T': pre['total'], 'sizes': pre['sizes'], 'ratios': pre['ratios'], 'hist': hist, 'endFiles': pe['end']['files'], 'pkAll': pk_all, 'pkData': pk_data,
            'rssPeak': max(rss) if rss else None, 'rssBase': max(rss_base) if rss_base else None, 'idle': pe['idleReached'], 'nsamples': len(comp), 'buckets': buckets, 'liveHeap': pe['liveHeapHistogram']}
for a in ('n', 'd', 'w', 'wc'): arm(a)
for a, v in A.items():
    print(f"  arm {a}: T={v['T']} compactions={[(h['inputs'], h['bytes_in'], h['bytes_out']) for h in v['hist']]} endFiles={v['endFiles']} peakExtra(all)={v['pkAll']} peakExtra(data)={v['pkData']} ({v['pkData']/v['T']:.3f} T) rssPeak={v['rssPeak']} rssBase={v['rssBase']} sampling={v['nsamples']} samples")
    chk(f'{a}: workload instrument: 12 files, ratios 1.10-1.20, idle reached, >= 50 samples in the compaction window', len(v['sizes']) == 12 and all(1.10 <= r <= 1.20 for r in v['ratios']) and v['idle'] and v['nsamples'] >= 50, f"ratios {min(v['ratios'])}-{max(v['ratios'])} idle={v['idle']} samples={v['nsamples']}", 'instrument')
    chk(f'{a}: every compaction line has inputs and bytes (history joined to the Compacting lines)', all(h['inputs'] for h in v['hist']), str([h['inputs'] for h in v['hist']]), 'instrument')
n, d, w, wc = A['n'], A['d'], A['w'], A['wc']
chk('n: no compaction, 12 sstables at the end, peak extra 0 (<= 1% of T)', len(n['hist']) == 0 and n['endFiles'] == 12 and n['pkData'] <= 0.01 * n['T'], f"compactions={len(n['hist'])} endFiles={n['endFiles']} pk={n['pkData']}")
nb = [l for l in n['buckets'] if '/ks/standard1-' in l]
first = nb[0] if nb else ''
nbk = len(re.findall(r'\], \[', first)) + 1
chk('n: TRACE bucket listing for ks.standard1 shows 12 singleton buckets (nothing grouped)', nbk == 12 and first.count('BigTableReader') == 12, f"{len(nb)} listings; first: buckets={nbk} sstables={first.count('BigTableReader')}", 'instrument')
big = max((h['bytes_in'] for h in d['hist']), default=0)
chk('d: two compactions, each 4 to 8 inputs, 2 sstables at the end', len(d['hist']) == 2 and all(4 <= (h['inputs'] or 0) <= 8 for h in d['hist']) and d['endFiles'] == 2, f"{[(h['inputs'], h['bytes_in']) for h in d['hist']]} endFiles={d['endFiles']}")
chk('d: largest compaction reads 0.5 to 0.85 T; peak extra (Data.db) within 0.8-1.15 of it', 0.5 * d['T'] <= big <= 0.85 * d['T'] and big and 0.8 <= d['pkData'] / big <= 1.15, f"big/T={big/d['T']:.3f} pk/big={d['pkData']/big if big else None}")
chk('w: one compaction of 12 inputs, 1 sstable at the end, peak extra 0.85-1.15 T', len(w['hist']) == 1 and w['hist'][0]['inputs'] == 12 and w['endFiles'] == 1 and 0.85 <= w['pkData'] / w['T'] <= 1.15, f"{[(h['inputs'], h['bytes_in']) for h in w['hist']]} endFiles={w['endFiles']} pk/T={w['pkData']/w['T']:.3f}")
chk('wc: every compaction has <= 4 inputs; peak extra 0.4-0.7 T and below w', len(wc['hist']) >= 1 and all((h['inputs'] or 99) <= 4 for h in wc['hist']) and 0.4 <= wc['pkData'] / wc['T'] <= 0.7 and wc['pkData'] < w['pkData'], f"{[(h['inputs'], h['bytes_in']) for h in wc['hist']]} pk/T={wc['pkData']/wc['T']:.3f} (w {w['pkData']/w['T']:.3f})")
chk('peak extra disk ordered w > d > n (0)', w['pkData'] > d['pkData'] > n['pkData'], f"w={w['pkData']} d={d['pkData']} n={n['pkData']}")
# heap: B3g last row; "materially" = spread of peak RssAnon (n vs w) > 25% and monotone n < d < w
for a in ('n', 'd', 'w', 'wc'):
    J = [json.loads(l) for l in open(os.path.join(O, a, 'heapinfo.jsonl')) if l.strip()]
    J = [j['usedKB'] for j in J if 'error' not in j and j['phase'] == 'compact']
    print(f"  arm {a}: GC.heap_info used heap in the compaction window: n={len(J)} peak={max(J) if J else None} KB (information, not the frozen criterion)")
rp = [A[a]['rssPeak'] for a in ('n', 'd', 'w')]
spread = (max(rp) - min(rp)) / min(rp) if all(rp) else None
mono = all(rp[i] < rp[i + 1] for i in range(2)) if all(rp) else None
chk('heap (RssAnon peak) does not differ materially across the ratios (spread <= 25% or not monotone n<d<w)', spread is not None and (spread <= 0.25 or not mono), f"peaks n,d,w={rp} spread={spread:.3f} monotone={mono}")
bad = [x for k, x, ok in res if not ok]
print('SUMMARY', 'ALL PASS (B3f holds: B3g row 1 + row 3, control moved)' if not bad else 'FAILURES: ' + '; '.join(bad))
