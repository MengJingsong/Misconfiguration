#!/usr/bin/env python3
"""Analyze $STAGE4_OUT/unit.txt of KeysToSaveWriterTest against B2f/B2g (as amended 2026-10-26).
usage: analyze_unit.py unit.txt   Prints readings, EXPECTED lines (ok / MISMATCH) and a row classification.
Rules fixed before run 1: n_K == min(K, N) (K=0 and MAX mean N); file_len affine in n (fit through K=1 and K=N points, residual <= 8 bytes
at the other points); L_N == L_0 == L_MAX == L_2000 within 8 bytes; L_100/L_N in [0.1, 0.1 + 2*hdr/L_N]; size/weighted unchanged by the save;
reload_count == n_logged; start_size == N; counter cache n == min(K, N)."""
import re, sys
rows = {}
N = None
for line in open(sys.argv[1]):
    line = line.strip()
    if line.startswith('N='):
        N = int(line[2:]); continue
    m = re.match(r'(key|ctr) K=(\d+) (.*)', line)
    if m:
        d = rows.setdefault((m.group(1), int(m.group(2))), {})
        for kv in m.group(3).split():
            k, v = kv.split('=', 1); d[k] = int(v)
done = any(l.strip() == 'done=1' for l in open(sys.argv[1]))
bad = 0
def exp(name, ok, detail=''):
    global bad
    print('EXPECTED %s: %s %s' % (name, 'ok' if ok else 'MISMATCH', detail)); bad += 0 if ok else 1
exp('run finished (done=1)', done)
if N is None or not done:
    print('no result'); sys.exit(1)
MAX = 2**31 - 1
for kind in ('key', 'ctr'):
    for (kk, k), d in sorted(rows.items()):
        if kk != kind: continue
        print(kind, 'K=%d' % k, d)
for kind in ('key', 'ctr'):
    for (kk, k), d in sorted(rows.items()):
        if kk != kind: continue
        want = N if (k == 0 or k >= N) else k
        exp('%s K=%d start_size == N' % (kind, k), d.get('start_size') == N, 'start_size=%s' % d.get('start_size'))
        exp('%s K=%d n_logged == min(K,N)=%d' % (kind, k, want), d.get('n_logged') == want, 'n_logged=%s' % d.get('n_logged'))
        exp('%s K=%d reload_count == n_logged' % (kind, k), d.get('reload_count') == d.get('n_logged'), 'reload=%s' % d.get('reload_count'))
key = {k: d for (kk, k), d in rows.items() if kk == 'key'}
if key:
    L = {k: d['file_len'] for k, d in key.items()}
    nn = {k: d['n_logged'] for k, d in key.items()}
    kmin = min(nn, key=lambda k: nn[k]); kmax = max(nn, key=lambda k: nn[k])
    e = (L[kmax] - L[kmin]) / float(nn[kmax] - nn[kmin])
    hdr = L[kmin] - e * nn[kmin]
    print('derived: e=%.2f bytes/entry hdr=%.1f bytes' % (e, hdr))
    for k in sorted(L):
        pred = hdr + e * nn[k]
        exp('key K=%d file_len affine in n (|resid| <= 8 B)' % k, abs(L[k] - pred) <= 8, 'len=%d pred=%.1f' % (L[k], pred))
    exp('key L(K=N,0,MAX,2000) equal within 8 B', max(L[k] for k in (N, 0, MAX, 2000) if k in L) - min(L[k] for k in (N, 0, MAX, 2000) if k in L) <= 8, str({k: L[k] for k in (N, 0, MAX, 2000) if k in L}))
    if 100 in L and N in L:
        r = L[100] / float(L[N]); hi = 0.1 + 2 * hdr / L[N]
        exp('key L(100)/L(N) in [0.1, 0.1 + 2 hdr/L(N)]', 0.1 <= r <= hi, 'ratio=%.4f hi=%.4f' % (r, hi))
    for k, d in sorted(key.items()):
        exp('key K=%d size and weighted unchanged by save' % k, d['size_after'] == d['start_size'] and d['weighted_after'] == d['start_weighted'], 'size %s->%s weighted %s->%s' % (d['start_size'], d['size_after'], d['start_weighted'], d['weighted_after']))
    print('INFO hot_in_saved (informational, no row): ' + str({k: d['hot_in_saved'] for k, d in sorted(key.items())}))
    # B2g classification
    cls = []
    if any(0 < k < N and d['n_logged'] > k for k, d in key.items()): cls.append('n_K > K for some 0<K<N: claim wrong (no cap)')
    if key.get(0, {}).get('n_logged') == 0: cls.append('K=0 writes 0 entries: mechanism differs')
    if len({d['weighted_after'] for d in key.values()}) > 1: cls.append('weightedSize changed: knob affects live memory')
    print('B2g classification:', '; '.join(cls) if cls else ('claim holds (disk)' if bad == 0 else 'see MISMATCH lines'))
print('MISMATCH total', bad)
sys.exit(1 if bad else 0)
