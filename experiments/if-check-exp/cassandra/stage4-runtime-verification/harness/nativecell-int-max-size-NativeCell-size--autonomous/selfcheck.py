#!/usr/bin/env python3
"""Independent re-parse of the raw run-1 files (does not import the analysers). Usage: selfcheck.py <unit-out-dir> <cluster-out-dir>
Unit: re-reads the RESULT lines of ant.log (not results.csv). Cluster: re-reads samples.csv / rows.jsonl / system.log per arm with plain code."""
import sys, os, re, json
MiB = 1 << 20
unit, clu = sys.argv[1], sys.argv[2]
print('== UNIT (from ant.log RESULT lines)')
R = {}
for l in open(os.path.join(unit, 'ant.log'), errors='replace'):
    m = re.search(r'RESULT (\S+?),(\S+?),(.*)$', l)
    if m: R.setdefault(m.group(1), {})[m.group(2)] = m.group(3).strip()
junit = [l for l in open(os.path.join(unit, 'ant.log'), errors='replace') if 'Tests run:' in l]
print('junit:', junit[-1].strip()[-120:] if junit else 'no junit line')
for arm in ('S_1KiB', 'S_200KiB', 'S_16MiB', 'S_255MiB'):
    cells = [R[arm]['cell%d' % i] for i in range(10)]
    L = int(R[arm]['L']); ok = all(c == '%d;%d' % (L + 21, L + 21) for c in cells)
    print(arm, 'L=%d' % L, '10 cells each L+21 and delta L+21:', ok, '| rss_rise/expected = %.4f' % (int(R[arm]['rss_rise']) / (10 * (L + 21))), '| after free %.1f MiB' % (int(R[arm]['rss_rise_after_free']) / MiB))
for g in ('G1', 'G2'):
    d = R[g]; print(g, 'throw:', d['throw_probe'], d['throw_message'], d['throw_frame'], 'owns delta', d['throw_owns_delta'], '| pass:', d['pass_probe'], d['pass_offHeapSize'], d['pass_owns_delta'], 'rise %.0f MiB' % (int(d['pass_rss_rise']) / MiB))
for p in ('P8', 'P16', 'P32'):
    d = R[p]; lim = int(d['limit']); print(p, 'limit', lim, 'admitted', d['admitted_before_block'], 'floor(limit/(1MiB+21))=', lim // (MiB + 21), 'owns', d['owns_at_block'], '=', int(d['admitted_before_block']) * (MiB + 21), '| released->done ms', d['completed_after_release_ms'], '| blocking owns', d['blocking_owns'], '>', lim, int(d['blocking_owns']) > lim)
print('O owns', R['O']['owns'], '= 16MiB+21?', int(R['O']['owns']) == 16 * MiB + 21, 'ratio', R['O']['owns_over_limit_ratio'])
print('H owns before/after', R['H']['owns_before'], R['H']['owns_after'])
print('== CLUSTER (from samples.csv / rows.jsonl / system.log)')
def rd(arm):
    d = os.path.join(clu, arm); S = json.load(open(d + '/arm.json'))
    sm = []
    for ln in open(d + '/samples.csv').read().splitlines()[1:]:
        f = ln.split(',')
        if len(f) == 5: sm.append(tuple(int(x) for x in f))
    rows = [json.loads(x) for x in open(d + '/rows.jsonl')]
    return d, S, sm, rows
res = {}
for arm in ('A', 'A2', 'B', 'K64', 'K128', 'K256', 'K512', 'hb'):
    if not os.path.exists(os.path.join(clu, arm, 'arm.json')): print(arm, 'missing'); continue
    d, S, sm, rows = rd(arm)
    t0 = S['blocks'][0]['a']; t1 = S['blocks'][-1]['b'] + 5000
    be = S['marks']['baseline_end']
    base = sorted(x[1] for x in sm if be - 8000 <= x[0] <= be); base = base[len(base) // 2] * 1024
    inw = [x for x in sm if t0 <= x[0] <= t1]
    pk = max(x[2] for x in inw); rs = max(x[1] for x in inw) * 1024 - base
    ok = {}; er = {}
    for r in rows: (ok if r['status'] == 'ok' else er).setdefault(r['block'], []).append(r)
    lg = open(d + '/system.log').read() if os.path.exists(d + '/system.log') else ''
    print(arm, 'rows ok/err per block:', {b['name']: (len(ok.get(b['name'], [])), len(er.get(b['name'], []))) for b in S['blocks']},
          '| peak AllMem %.1f MiB | RssAnon rise %.1f MiB | max OverSized %d | log ISE %d NativeCell %d' % (pk / MiB, rs / MiB, max(x[4] for x in sm), lg.count('IllegalStateException'), lg.count('NativeCell')))
    for b, e in er.items(): print('   first error in', b, ':', e[0]['msg'][:170])
    res[arm] = (pk, rs, len(sm), min(x[2] for x in inw))
    print('   samples', len(sm), 'in-window', len(inw), '| off-heap min in window', min(x[2] for x in inw))
ks = [(k, res['K%d' % k][0] / MiB) for k in (64, 128, 256, 512) if 'K%d' % k in res]
print('K peaks (MiB):', ks)
if 'K256' in res: print('K256 RssAnon rise / peak = %.2f' % (res['K256'][1] / res['K256'][0]))
