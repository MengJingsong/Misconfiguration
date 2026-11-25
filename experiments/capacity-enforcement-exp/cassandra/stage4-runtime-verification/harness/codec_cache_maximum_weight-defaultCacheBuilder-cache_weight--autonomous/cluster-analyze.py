#!/usr/bin/env python3
# Cluster-tier analysis for order 96 (B3f/B3g with S4-A8, S4-A10). Usage: cluster-analyze.py <readings.txt>
import re, statistics, sys
R = {}; F = {}; T = {}
for line in open(sys.argv[1]):
    m = re.match(r'READING tag=(\S+) n=(\d) (.*?)\s*\|', line)
    if m:
        kv = dict(x.split('=') for x in m.group(3).split() if '=' in x)
        R.setdefault(m.group(1), []).append({k: (int(v) if v.isdigit() else v) for k, v in kv.items()})
        continue
    m = re.match(r'READING tag=(\S+) functions=(\S*)', line)
    if m: F[m.group(1)] = m.group(2)
    m = re.match(r'TIMING tag=(\S+) file=(\S+) seconds=(\d+) cqlsh_rc=(\d+) error_lines=(\d+)', line)
    if m: T[m.group(1)] = (m.group(2), int(m.group(3)), int(m.group(4)), int(m.group(5)))

keys = ['CacheKey', 'SVR', 'WSVR', 'VectorCodecFixed', 'TupleCodec', 'TupleType', 'ObjArrBytes', 'HistTotalBytes', 'HeapUsedAfterGC_K']
order = [t for t in ['base', 'n500', 'n2000', 'n4000', 'ndrop', 'w1', 'w1drop', 'w2000', 'w2000drop'] if t in R]
med = {t: {k: statistics.median(r[k] for r in R[t] if isinstance(r.get(k), int)) for k in keys} for t in order}
spread = {t: (max(r['HeapUsedAfterGC_K'] for r in R[t]) - min(r['HeapUsedAfterGC_K'] for r in R[t])) / 1024 for t in order}
b = med['base']
print('| tag | functions | ΔCacheKey | ΔSVR | ΔWSVR | ΔVectorCodec$FixedLength | ΔTupleCodec | ΔTupleType | Δ[Object; MB | Δlive (hist Total) MB | Δheap after GC MB | heap spread MB | cqlsh s / errors |')
print('|---|---|---|---|---|---|---|---|---|---|---|---|---|')
for t in order:
    m = med[t]
    tm = T.get(t, ('', '', '', ''))
    print(f"| {t} | {F.get(t,'')} | {m['CacheKey']-b['CacheKey']:.0f} | {m['SVR']-b['SVR']:.0f} | {m['WSVR']-b['WSVR']:.0f} | "
          f"{m['VectorCodecFixed']-b['VectorCodecFixed']:.0f} | {m['TupleCodec']-b['TupleCodec']:.0f} | {m['TupleType']-b['TupleType']:.0f} | "
          f"{(m['ObjArrBytes']-b['ObjArrBytes'])/2**20:.2f} | {(m['HistTotalBytes']-b['HistTotalBytes'])/2**20:.2f} | "
          f"{(m['HeapUsedAfterGC_K']-b['HeapUsedAfterGC_K'])/1024:.2f} | {spread[t]:.2f} | {tm[1]} / {tm[3]} |")
print()

def H(t, k='HeapUsedAfterGC_K'): return med[t][k] / 1024.0   # MB
def within(x, n, tol=0.1): return abs(x - n) <= tol * n
out = []
if all(t in med for t in ('base', 'n500', 'n2000', 'n4000')):
    for key, name in (('HeapUsedAfterGC_K', 'heap after GC'), ('HistTotalBytes', 'live bytes (histogram Total)')):
        conv = (lambda t: H(t)) if key == 'HeapUsedAfterGC_K' else (lambda t: med[t][key] / 2**20)
        d0 = conv('n500') - conv('base'); d1 = conv('n2000') - conv('n500'); d2 = conv('n4000') - conv('n2000')
        s0, s1, s2 = d0 / 500, d1 / 1500, d2 / 2000
        noise = max(2.0, *(spread[t] for t in ('base', 'n500', 'n2000', 'n4000')))
        nok = s1 >= 0.5 * s0 and s2 >= 0.5 * s0 and d1 > noise and d2 > noise
        flat = (s1 < 0.25 * s0 and s2 < 0.25 * s0) or (abs(d1) <= noise and abs(d2) <= noise)
        out.append(f"{name}: rises base->n500 {d0:.1f} MB, n500->n2000 {d1:.1f} MB, n2000->n4000 {d2:.1f} MB; "
                   f"slopes s0={s0*1024:.1f} KB/fn s1={s1*1024:.1f} s2={s2*1024:.1f}; noise ±{noise:.1f} MB; "
                   f"no-knee rule: {nok}; flat/knee (refuting) rule: {flat}")
    dc = {t: med[t]['CacheKey'] - b['CacheKey'] for t in order}
    dv = {t: med[t]['VectorCodecFixed'] - b['VectorCodecFixed'] for t in order}
    out.append(f"cache entries ΔCacheKey: n500 {dc['n500']:.0f} (≈500: {within(dc['n500'],500)}), n2000 {dc['n2000']:.0f}, n4000 {dc['n4000']:.0f}; "
               f"plateau 900-1100 at n2000 and n4000: {900 <= dc['n2000'] <= 1100 and 900 <= dc['n4000'] <= 1100}; never plateaus (≈N): {dc['n4000'] >= 3600}")
    out.append(f"ΔVectorCodec$FixedLength: n500 {dv['n500']:.0f}, n2000 {dv['n2000']:.0f} (≈2000: {within(dv['n2000'],2000)}), n4000 {dv['n4000']:.0f} (≈4000: {within(dv['n4000'],4000)})")
if 'ndrop' in med:
    out.append(f"ndrop: ΔVectorCodec {med['ndrop']['VectorCodecFixed']-b['VectorCodecFixed']:.0f} (950-1000 predicted), ΔCacheKey {med['ndrop']['CacheKey']-b['CacheKey']:.0f}, "
               f"Δheap {H('ndrop')-H('base'):.1f} MB (within a few MB of base predicted)")
if 'w1drop' in med and 'w2000drop' in med:
    t1 = med['w1drop']['TupleCodec'] - b['TupleCodec']; t2 = med['w2000drop']['TupleCodec'] - b['TupleCodec']
    dh = H('w2000drop') - H('w1drop'); do = (med['w2000drop']['ObjArrBytes'] - med['w1drop']['ObjArrBytes']) / 2**20
    dl = (med['w2000drop']['HistTotalBytes'] - med['w1drop']['HistTotalBytes']) / 2**20
    out.append(f"wide: post-drop ΔTupleCodec M=1 {t1:.0f}, M=2000 {t2:.0f} (same ±10 %: {within(t2, t1) if t1 else 'n/a'}); "
               f"heap(w2000drop)-heap(w1drop) {dh:.1f} MB (≥ +4 MB: {dh >= 4}; within ±2 MB: {abs(dh) <= 2}); "
               f"Δ[Object; bytes {do:.1f} MB; Δlive (hist Total) {dl:.1f} MB")
    out.append(f"wide: ΔCacheKey w1 {med['w1']['CacheKey']-b['CacheKey']:.0f}, w1drop {med['w1drop']['CacheKey']-b['CacheKey']:.0f}, "
               f"w2000 {med['w2000']['CacheKey']-b['CacheKey']:.0f}, w2000drop {med['w2000drop']['CacheKey']-b['CacheKey']:.0f}")
print('\n'.join('- ' + o for o in out))
