#!/usr/bin/env python3
"""Cluster tier (B3f / B3g with AM6) analyzer of file_cache_size-chunk_cache_eviction-weighted_size--autonomous.
usage: python3 -I cluster-analyze.py <run dir, e.g. /mydata/jingsong-cass-s4/o06/logs/run1/cluster>
Reads marks.txt, jmx-<F>.csv, cql-<F>.txt, nmt-<F>.csv; prints per-F readings and the B3f/B3g checks."""
import csv, re, statistics as st, sys, os
D = sys.argv[1]; MiB = 1 << 20; CH = 16384
marks = {}
for l in open(os.path.join(D, 'marks.txt')):
    t, rest = l.split(' ', 1); rest = rest.strip()
    m = re.match(r'F=(\d+) (\w+)', rest)
    if m: marks[(int(m.group(1)), m.group(2))] = int(t)
Fs = sorted({f for f, _ in marks})
def num(x): return int(float(x)) if x not in ('', None) else None
R = {}
for F in Fs:
    rows = list(csv.DictReader(open(os.path.join(D, 'jmx-%d.csv' % F))))
    rs, re_, tail = marks[(F, 'read_start')], marks[(F, 'read_end')], marks[(F, 'tail')]
    allr = [r for r in rows if rs - 10000 <= int(r['epoch_ms']) <= tail]
    # AM6 window: the last minute of the read run, clipped to the read run (runs last < 60 s; v1 of this script did not clip
    # and so averaged pre-read samples with an empty cache: kept as analysis-v1-unclipped.txt)
    last = [r for r in rows if max(rs, re_ - 60000) <= int(r['epoch_ms']) <= re_]
    unclipped = [r for r in rows if re_ - 60000 <= int(r['epoch_ms']) <= re_]
    tailr = [r for r in rows if re_ + 5000 <= int(r['epoch_ms']) <= tail]
    g = lambda rr, k: [num(r[k]) for r in rr if num(r[k]) is not None]
    cap = (g(allr, 'cc_capacity') or [None])[0]
    sz = g(allr, 'cc_size'); szl = g(last, 'cc_size')
    ent = g(allr, 'cc_entries'); mis = g(allr, 'cc_misses')
    x = dict(F=F, n=len(allr), nlast=len(last), cap=cap,
             size_max=max(sz) if sz else None, size_plateau=st.median(szl) if szl else None,
             entries_max=max(ent) if ent else None, entries_end=ent[-1] if ent else None,
             misses=(mis[-1] - mis[0]) if mis else None,
             pool_max=max(g(allr, 'ccpool_size')), pool_used_max=max(g(allr, 'ccpool_used')),
             overflow_max=max(g(allr, 'ccpool_overflow')), pool_cap=g(allr, 'ccpool_capacity')[0],
             net_max=max(g(allr, 'netpool_size')),
             direct_last=st.mean(g(last, 'direct_used')), direct_unclipped=st.mean(g(unclipped, 'direct_used')), direct_tail=st.mean(g(tailr, 'direct_used')), direct_max=max(g(allr, 'direct_used')),
             read_s=(re_ - rs) / 1000.0)
    x['over_cap_samples'] = sum(1 for v in sz if cap is not None and v > cap + 32 * CH)
    x['evictions'] = (x['misses'] - x['entries_end']) if x['misses'] is not None else None
    # cqlsh rows: size_bytes
    cs = []
    for l in open(os.path.join(D, 'cql-%d.txt' % F)):
        t = int(l.split(' ', 1)[0])
        if not (rs - 10000 <= t <= tail): continue
        m = re.search(r'chunks \|\s*(\d+) \|\s*(\d+) \|\s*(\d+)', l)
        if m: cs.append((int(m.group(1)), int(m.group(2)), int(m.group(3))))
    x['cql_rows'] = len(cs); x['cql_size_max'] = max(c[1] for c in cs) if cs else None
    x['cql_capacity'] = cs[0][0] if cs else None
    nm = []; rss = []
    for l in open(os.path.join(D, 'nmt-%d.csv' % F)):
        t = int(l.split(',', 1)[0])
        if not (max(rs, re_ - 60000) <= t <= re_): continue
        m = re.search(r'Other \(reserved=(\d+)KB, committed=(\d+)KB\)', l)
        if m: nm.append(int(m.group(2)) * 1024)
        m = re.search(r'rss_kb=(\d+)', l)
        if m: rss.append(int(m.group(1)) * 1024)
    x['nmt_other_last'] = st.mean(nm) if nm else None; x['rss_last'] = st.mean(rss) if rss else None
    R[F] = x
B = R.get(32)
def mib(v): return 'n/a' if v is None else '%.2f MiB' % (v / MiB)
for F in Fs:
    x = R[F]
    x['delta'] = x['direct_last'] - B['direct_last'] if B else None
    x['nmt_delta'] = (x['nmt_other_last'] - B['nmt_other_last']) if B and x['nmt_other_last'] and B['nmt_other_last'] else None
    x['rss_delta'] = (x['rss_last'] - B['rss_last']) if B and x['rss_last'] and B['rss_last'] else None
    print('F=%d read %.0f s, %d jmx samples (%d in last 60 s), %d cql rows' % (F, x['read_s'], x['n'], x['nlast'], x['cql_rows']))
    print('  capacity %s (cql %s); size max %s, plateau(last 60 s median) %s, cql size max %s; samples over cap+32 chunks: %d' % (
        x['cap'], x['cql_capacity'], x['size_max'], x['size_plateau'], x['cql_size_max'], x['over_cap_samples']))
    print('  entries max %s end %s; misses %s; evictions (misses - entries) %s' % (x['entries_max'], x['entries_end'], x['misses'], x['evictions']))
    print('  ccpool Size max %s (%s), Used max %s, Overflow max %s, Capacity %s; netpool Size max %s' % (
        x['pool_max'], mib(x['pool_max']), mib(x['pool_used_max']), x['overflow_max'], mib(x['pool_cap']), mib(x['net_max'])))
    print('  direct MemoryUsed read-run (last <= 60 s) mean %s (delta vs F=32 %s); max %s; NMT Other delta %s; RSS delta %s' % (
        mib(x['direct_last']), mib(x['delta']), mib(x['direct_max']), mib(x['nmt_delta']), mib(x['rss_delta'])))
    print('  info: unclipped-window delta %s; 60 s tail (steady) mean %s, tail delta %s' % (
        mib(x['direct_unclipped'] - B['direct_unclipped']), mib(x['direct_tail']), mib(x['direct_tail'] - B['direct_tail'])))
print()
def chk(name, ok): print('%s %s' % ('PASS' if ok else 'FAIL', name))
if 32 in R:
    x = R[32]; chk('B3f F=32: no chunks row (cache null)', x['cap'] is None and x['cql_rows'] == 0)
    chk('B3f F=32: chunk-cache pool Size <= 32 MiB', x['pool_max'] <= 32 * MiB)
for F, capb, exp in [(96, 67108864, 64), (288, 268435456, 256)]:
    if F not in R: continue
    x = R[F]
    chk('B3f F=%d: capacity_bytes = %d' % (F, capb), x['cap'] == capb and x['cql_capacity'] == capb)
    chk('B3f F=%d: size plateau = cap +- 1 chunk' % F, abs(x['size_plateau'] - capb) <= CH)
    chk('B3f F=%d: size never above cap + 32 x 16 KiB (jmx and cql)' % F, x['size_max'] <= capb + 32 * CH and (x['cql_size_max'] or 0) <= capb + 32 * CH)
    chk('B3f F=%d: ccpool Size <= F MiB' % F, x['pool_max'] <= F * MiB)
    chk('B3f F=%d: direct delta = (F-32) +- 32 MiB (%s)' % (F, mib(x['delta'])), abs(x['delta'] - exp * MiB) <= 32 * MiB)
    chk('B3f F=%d: OverflowSize ~0 (max %s)' % (F, x['overflow_max']), x['overflow_max'] <= 32 * CH)
    print('     AM6 refuted-on-resource test: delta > (F-32)+64 MiB ? %s' % (x['delta'] > (exp + 64) * MiB))
    print('     AM6 partial test: delta > F+32 MiB ? %s' % (x['delta'] > (F + 32) * MiB))
if 96 in R and 288 in R:
    d = R[288]['delta'] - R[96]['delta']
    print('     relation: delta(288) - delta(96) = %s (B3f: ~192 MiB); tail: %s' % (mib(d), mib(R[288]['direct_tail'] - R[96]['direct_tail'])))
if 2080 in R:
    x = R[2080]
    chk('B3f F=2080: capacity_bytes = 2147483648', x['cap'] == 2147483648)
    chk('B3f F=2080: size plateau below capacity', x['size_plateau'] < 2147483648)
    chk('B3g/AM6 positive control: F=2080 plateau >= 1 GiB', x['size_plateau'] >= 1024 * MiB)
    chk('B3f F=2080: ccpool Size <= 2080 MiB', x['pool_max'] <= 2080 * MiB)
    print('     F=2080 direct delta %s (B3f: ~ +1.5 GiB)' % mib(x['delta']))
    if 288 in R: chk('AM6: F=288 plateau <= 256 MiB + 32 chunks', R[288]['size_plateau'] <= 268435456 + 32 * CH)
