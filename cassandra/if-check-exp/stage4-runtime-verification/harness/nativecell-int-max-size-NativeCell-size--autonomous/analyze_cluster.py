#!/usr/bin/env python3
"""PASS/FAIL per frozen numeric prediction of B3i.4 from the arm directories. Usage: analyze_cluster.py <outdir>"""
import sys, os, json, csv, statistics
OUT = sys.argv[1]; MiB = 1 << 20; res = []
def chk(n, ok, d=''): res.append((n, 'PASS' if ok else 'FAIL', d))
def load(lbl):
    d = os.path.join(OUT, lbl)
    if not os.path.exists(d + '/arm.json'): return None
    S = json.load(open(d + '/arm.json'))
    rows = [r for r in csv.DictReader(open(d + '/samples.csv'))]
    S['samples'] = [(int(r['epoch_ms']), int(r['rss_anon_kb']) * 1024, int(r['all_memtables_offheap']), int(r['memtable_offheap']), int(r['oversized_mutations'])) for r in rows]
    S['rows'] = [json.loads(l) for l in open(d + '/rows.jsonl')]
    return S
def blk(S, n): return next(b for b in S['blocks'] if b['name'] == n)
def win(S, a, b): return [x for x in S['samples'] if a <= x[0] <= b]
def work_window(S): return S['blocks'][0]['a'], S['blocks'][-1]['b'] + 5000
def baseline_rss(S):
    e = S['marks']['baseline_end']; w = [x[1] for x in S['samples'] if e - 8000 <= x[0] <= e]
    return statistics.median(w)
def peak_all(S):
    a, b = work_window(S); return max(x[2] for x in win(S, a, b))
def peak_rss_rise(S):
    a, b = work_window(S); return max(x[1] for x in win(S, a, b)) - baseline_rss(S)
def maxover(S): return max(max(0, x[4]) for x in S['samples'])
A = load('A')
if A:
    for n, rows in (('s1', 100), ('s8', 100), ('s15', 100)):
        b = blk(A, n); chk('B3i.4a A %s: all %d inserts ok, 0 errors' % (n, rows), b['ok'] == rows == b['rows'] and b['err'] == 0, 'ok=%d err=%d' % (b['ok'], b['err']))
    chk('B3i.4a A: system.log IllegalStateException==0, NativeCell==0', A['log']['ISE'] == 0 and A['log']['NativeCell'] == 0, str(A['log']['ISE']) + '/' + str(A['log']['NativeCell']))
    b = blk(A, 's17')
    chk('B3i.4a A s17: refused with "Request is too big"', b['err'] == 1 and 'Request is too big' in (b['first_err'] or ''), (b['first_err'] or '')[:160])
    chk('B3i.4a A: OverSizedMutations stays 0', maxover(A) == 0, str(maxover(A)))
    w = win(A, b['a'], b['b'] + 5000); v0 = [x for x in A['samples'] if x[0] <= b['a']][-1][2]
    chk('B3i.4a A s17: AllMemtablesOffHeapSize rise <= 1 MiB during/after refused row', max(x[2] for x in w) - v0 <= MiB, 'rise %.2f MiB' % ((max(x[2] for x in w) - v0) / MiB))
A2 = load('A2')
if A2:
    b = blk(A2, 's17'); e = (b['first_err'] or '')
    chk('B3i.4b A2 s17: refused, text mentions oversized mutation (client error or system.log)', b['err'] == 1 and ('oversized mutation' in e.lower() or A2['log']['oversized'] >= 1), e[:200] + ' | log oversized=%d' % A2['log']['oversized'])
    chk('B3i.4b A2: OverSizedMutations Count == 1', maxover(A2) == 1, str(maxover(A2)))
B = load('B')
if B:
    for n in ('s17', 's60'):
        b = blk(B, n); chk('B3i.4c B %s: 5 of 5 inserts ok' % n, b['ok'] == 5 and b['err'] == 0, 'ok=%d err=%d %s' % (b['ok'], b['err'], b['first_err'] or ''))
    chk('B3i.4c B: IllegalStateException==0, NativeCell==0', B['log']['ISE'] == 0 and B['log']['NativeCell'] == 0)
K = {}
for k in (64, 128, 256, 512):
    S = load('K%d' % k)
    if S:
        K[k] = S; b = blk(S, 's8'); chk('B3i.4d K%d: 100 inserts ok' % k, b['ok'] == 100 and b['err'] == 0, 'ok=%d err=%d' % (b['ok'], b['err']))
        chk('B3i.4d K%d: startup log shows off-heap threshold %d MiB' % (k, k), any(('%d.000MiB' % k in l or '%dMiB' % k in l) for l in S['log']['global_offheap']), str(S['log']['global_offheap']))
P = {k: peak_all(S) for k, S in K.items()}
for k, p in P.items():
    chk('B3i.4d K%d: peak %.1f MiB <= k + 16 MiB' % (k, p / MiB), p <= k * MiB + 16 * MiB)
    if k >= 128: chk('B3i.4d K%d: peak >= 0.30 x k' % k, p >= 0.30 * k * MiB, '%.2f x' % (p / (k * MiB)))
ks = sorted(P)
if len(ks) == 4: chk('B3i.4d peaks strictly increase 64<128<256<512', all(P[ks[i]] < P[ks[i + 1]] for i in range(3)), ' < '.join('%.1f' % (P[k] / MiB) for k in ks))
if 64 in P and 256 in P: chk('B3i.4d P(256)/P(64) >= 2.0', P[256] / P[64] >= 2.0, '%.2f' % (P[256] / P[64]))
if 256 in K:
    r = peak_rss_rise(K[256]); chk('B3i.4e K256: RssAnon rise >= 0.80 x P(256)', r >= 0.8 * P[256], 'rise %.1f MiB, P %.1f MiB, ratio %.2f' % (r / MiB, P[256] / MiB, r / P[256]))
H = load('hb')
if H:
    b = blk(H, 's8'); chk('B3i.4f hb: 100 inserts ok', b['ok'] == 100 and b['err'] == 0)
    a, bb = work_window(H); mx = max(x[2] for x in win(H, a, bb)); chk('B3i.4f hb: AllMemtablesOffHeapSize == 0 throughout', mx == 0, 'max %d' % mx)
    if 256 in K: chk('B3i.4f hb: RssAnon rise < half of K256 rise', peak_rss_rise(H) < 0.5 * peak_rss_rise(K[256]), 'hb %.1f MiB vs K256 %.1f MiB' % (peak_rss_rise(H) / MiB, peak_rss_rise(K[256]) / MiB))
w = max(len(a) for a, _, _ in res) if res else 0
for a, b, c in res: print('%s  %s  %s' % (b, a.ljust(w), c))
print('TOTAL pass=%d fail=%d' % (sum(1 for x in res if x[1] == 'PASS'), sum(1 for x in res if x[1] == 'FAIL')))
