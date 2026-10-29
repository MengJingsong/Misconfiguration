#!/usr/bin/env python3
"""Independent re-parse of the raw run-1 files of max_array_length-checkmaxleafnodecount-numleaves--autonomous against the FROZEN predictions
(case file amendments U2-U4, C1-C2 and B2f/B3f). usage: selfcheck.py <run1 dir containing unit/unit.out and cluster/<label>/...>"""
import math, os, re, sys
R = sys.argv[1]; res = []
def chk(name, ok, detail=''):
    res.append(ok); print('%s %s %s' % ('PASS' if ok else 'FAIL', name, detail))
runs = {}
for l in open(R + '/unit/unit.out'):
    if l.startswith('STAGE4 RESULT'):
        kv = dict(re.findall(r'(\w+)=(\[[^\]]*\]|\S+)', l)); runs[kv['label']] = kv
LIMIT = int(next(iter(runs.values()))['LIMIT'])
def smp(r): return [tuple(map(int, x.split(':'))) for x in r['retainedSamples'].strip('[]').split() if x]
chk('unit: 15 runs, all printed RESULT', len(runs) == 15, 'n=%d' % len(runs))
chk('LIMIT = ArrayUtil.MAX_ARRAY_LENGTH read at run time = 2147483631 (A1 "value not verified" resolved)', LIMIT == 2147483631, str(LIMIT))
for lab in ('A-B24-M1024-N50e6', 'Ap-B16-M1024-N50e6'):
    r = runs[lab]; B = int(r['B'])
    chk('run A (%s): completes, leaves = ceil(50e6/1024) = 48829' % lab, r['result'] == 'OK' and r['leavesAtEnd'] == '48829')
    chk('run A (%s): ratio B*leaves/LIMIT < 0.001' % lab, float(r['ratio']) < 0.001, 'ratio=%s (formula %.3e)' % (r['ratio'], B * 48829 / LIMIT))
    s = smp(r)
    chk('[pre-registered 3..5 MB] run A (%s): retained at the last sample' % lab, 3e6 <= s[-1][1] <= 5e6, 'measured %d B' % s[-1][1])
    g = (s[-1][1] - s[0][1]) / (s[-1][0] - s[0][0])
    chk('[pre-registered B+24..B+80 per leaf] run A (%s): retained growth per leaf' % lab, B + 24 <= g <= B + 80, 'measured %.1f per leaf' % g)
for B in (1048576, 262144, 4096):
    L = LIMIT // B + 1
    pre = {1048576: 'B-B1MiB-L-r1', 262144: 'B-B262144-L', 4096: 'B-B4096-L'}[B]; ok_ = {1048576: 'C-B1MiB-L-1-r1', 262144: 'C-B262144-L-1', 4096: 'C-B4096-L-1'}[B]
    t, o = runs[pre], runs[ok_]
    chk('U2 B=%d: throw at exactly leaf L = floor(LIMIT/B)+1 = %d, "too many nodes", consumed = L' % (B, L), t['result'] == 'THROW' and int(t['leavesAtEnd']) == L and int(t['consumed']) == L and 'too many nodes' in t['msg'], 'leavesAtEnd=%s' % t['leavesAtEnd'])
    chk('U2 B=%d: N = L-1 completes with product <= LIMIT' % B, o['result'] == 'OK' and int(o['product']) <= LIMIT and int(o['leavesAtEnd']) == L - 1, 'product=%s' % o['product'])
    chk('U2 B=%d: product at the throw is the first count above LIMIT: B*L > LIMIT >= B*(L-1)' % B, B * L > LIMIT >= B * (L - 1))
    g = (smp(t)[-1][1] - smp(t)[0][1]) / (smp(t)[-1][0] - smp(t)[0][0])
    chk('[pre-registered B+24..B+80 per leaf] B=%d throw run: retained growth per leaf' % B, B + 24 <= g <= B + 80, 'measured %.1f (B+24 = %d)' % (g, B + 24))
    chk('B2g row: heap just before the throw is LIMIT-scale (>= 0.99 LIMIT)', smp(t)[-1][1] >= 0.99 * LIMIT, 'retained %d = %.4f LIMIT' % (smp(t)[-1][1], smp(t)[-1][1] / LIMIT))
chk('3 repetitions of the 1 MiB pair agree (throw leaf, consumed)', all(runs['B-B1MiB-L-r%d' % i]['leavesAtEnd'] == '2048' and runs['C-B1MiB-L-1-r%d' % i]['leavesAtEnd'] == '2047' for i in (1, 2, 3)))
chk('C5 (L-5) completes', runs['C5-B1MiB-L-5']['result'] == 'OK')
a, b = runs['CTL-B24-M1024-N1e6'], runs['CTL-B24-M1-N1e6']
chk('control: leaf count M=1 vs M=1024 scales by about 1024 (1,000,000 / 977)', 1000 <= int(b['leavesAtEnd']) / int(a['leavesAtEnd']) <= 1050, '%s / %s' % (b['leavesAtEnd'], a['leavesAtEnd']))
for r in (a, b):
    s = smp(r); g = (s[-1][1] - s[0][1]) / (s[-1][0] - s[0][0])
    chk('[pre-registered B+24..B+80 per leaf] control %s: retained growth per leaf' % r['label'], 24 + 24 <= g <= 24 + 80, 'measured %.1f' % g)
# ---------------- cluster ----------------
def an(label):
    d = R + '/cluster/' + label
    if not os.path.exists(d + '/wcs.txt'): return None
    o = os.popen('python3 %s/analyze_cluster.py %s' % (os.path.dirname(os.path.abspath(__file__)), d)).read()
    r = {}
    for l in o.splitlines():
        m = re.match(r'ANALYSIS (flush|rebuild) bpv=(\S+) .*', l)
        if m: r[(m.group(1), m.group(2))] = dict(re.findall(r'(\w+)=(\S+)', l))
    rd = open(d + '/readings.txt').read()
    r['tmn'] = re.search(r'TOO_MANY_NODES_LINES (\d+)', rd).group(1); r['rd'] = rd; r['dir'] = d
    sb = [int(l.split(',')[1]) for l in open(d + '/segbuf.csv') if re.match(r'^\d+,\d+', l)] if os.path.exists(d + '/segbuf.csv') else []
    r['segbuf'] = max(sb or [0])
    return r
CL = {k: an(k) for k in ('R5', 'R20a', 'R20b', 'R40', 'C32')}
for k, v in CL.items():
    if v is None: print('NOTE cluster run %s missing' % k); continue
    f, rb = v[('flush', 'None')], v[('rebuild', 'None')]
    print('NOTE cluster %s: flush segs=%s maxLeavesOneSeg=%s leavesSum=%s treeLen=%s | rebuild segs=%s maxLeaves=%s | tooMany=%s | segbufPeak=%.1f MiB | %s' % (k, f['segments'], f['maxLeavesOneSegment'], f['leavesSum'], f['treeLenSum'], rb['segments'], rb['maxLeavesOneSegment'], v['tmn'], v['segbuf'] / 1048576.0, re.sub(r'\s+', ' ', ' '.join(l for l in v['rd'].splitlines() if l.startswith(('LOAD', 'AUTO', 'SEGMENTS'))))))
if all(CL.get(k) for k in ('R5', 'R20a', 'R40')):
    chk('C2 no "too many nodes" in any arm', all(v['tmn'] == '0' for v in CL.values() if v))
    chk('C2 largest num_leaves per segment below 1e5 in every arm (ratio below 1e-3)', all(int(v[(p, 'None')]['maxLeavesOneSegment']) < 100000 for v in CL.values() if v for p in ('flush', 'rebuild')), str({k: (v[('flush', 'None')]['maxLeavesOneSegment'], v[('rebuild', 'None')]['maxLeavesOneSegment']) for k, v in CL.items() if v}))
    t = {k: sum(int(CL[k][(p, '8')]['treeLenSum']) + int(CL[k][(p, '24')]['treeLenSum']) for p in ('flush', 'rebuild')) for k in ('R5', 'R20a', 'R40')}
    r1, r2 = t['R20a'] / t['R5'], t['R40'] / t['R20a']
    chk('C2 BALANCED_TREE length ratio N=20M/N=5M in [3.0,4.4] (flush + rebuild, both indexes)', 3.0 <= r1 <= 4.4, 'measured %.2f' % r1)
    chk('C2 BALANCED_TREE length ratio N=40M/N=20M in [1.6,2.2]', 1.6 <= r2 <= 2.2, 'measured %.2f' % r2)
    al = {k: int(CL[k][('flush', 'None')]['allocSum']) + int(CL[k][('rebuild', 'None')]['allocSum']) for k in ('R5', 'R20a', 'R40')}
    chk('C2 ALLOC sums grow with N (R5 < R20a < R40)', al['R5'] < al['R20a'] < al['R40'], str(al))
    hp = {k: float(CL[k][('flush', 'None')]['heapUsedPeak_kB']) for k in ('R5', 'R20a', 'R40')}
    print('NOTE heap used sampled peak during flush (kB): %s' % hp)
if CL.get('R20a') and CL.get('C32'):
    a, c = CL['R20a'][('rebuild', 'None')], CL['C32'][('rebuild', 'None')]
    chk('C2 control: segments(32MiB) >= 10 x segments(1024MiB) on the rebuild path (N=20M)', int(c['segments']) >= 10 * int(a['segments']), '%s vs %s' % (c['segments'], a['segments']))
    chk('C2 control: peak SegmentBufferSpaceUsedBytes at 32MiB < 80 MiB and at 1024MiB > 200 MiB', CL['C32']['segbuf'] < 80 * 1048576 and CL['R20a']['segbuf'] > 200 * 1048576, '%.1f MiB / %.1f MiB' % (CL['C32']['segbuf'] / 1048576.0, CL['R20a']['segbuf'] / 1048576.0))
print('SUMMARY pass=%d fail=%d' % (sum(res), len(res) - sum(res)))
