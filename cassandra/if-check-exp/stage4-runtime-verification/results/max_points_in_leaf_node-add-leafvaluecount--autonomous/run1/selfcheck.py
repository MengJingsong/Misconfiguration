#!/usr/bin/env python3
"""Independent re-parse of the raw run-1 files of max_points_in_leaf_node-add-leafvaluecount--autonomous against the FROZEN predictions (case file amendments U4/U5/C5).
usage: selfcheck.py <run1 dir containing unit/unit.out and cluster/<label>/...>   Prints PASS/FAIL/NOTE; a FAIL is a sub-prediction that missed (reported, never edited)."""
import math, os, re, sys
R = sys.argv[1]; res = []
def chk(name, ok, detail=''):
    res.append(ok); print('%s %s %s' % ('PASS' if ok else 'FAIL', name, detail))
cells = {}; lab = None
for l in open(R + '/unit/unit.out'):
    m = re.match(r'== (\S+) ', l)
    if m: lab = m.group(1)
    if l.startswith('STAGE4 '):
        kind = l.split()[1]; kv = dict(re.findall(r'(\w+)=(\S+)', l)); cells.setdefault(lab, {})[kind] = (kv, l)
def C(M, N, B): return cells['G-M%d-N%d-B%d' % (M, N, B)]
Ms = (16, 128, 1024, 8192, 65536)
chk('unit: every grid label has CELL, LEAFPOST and SCRATCH lines (20 labels)', sum(1 for k, v in cells.items() if k.startswith('G-') and {'CELL', 'LEAFPOST', 'SCRATCH'} <= set(v)) == 20)
# (a) leaf counts
chk('(a) num_leaves == ceil(N/M) in every cell and max_points_in_leaf_node == M', all(int(c['CELL'][0]['num_leaves']) == int(c['CELL'][0]['expectLeaves']) and int(c['CELL'][0]['max_points_in_leaf_node']) == int(c['CELL'][0]['M']) for k, c in cells.items() if 'CELL' in c and 'num_leaves' in c['CELL'][0]))
chk('(a) bytes_per_value in the CELL lines equals B (4 or 16)', all(c['CELL'][0]['bytes_per_value'] == c['CELL'][0]['B'] for k, c in cells.items() if 'CELL' in c and 'bytes_per_value' in c['CELL'][0]))
# (b) scratch
for M in Ms:
    s = int(C(M, 1000000, 4)['SCRATCH'][0]['retainedBytes']); per = s / M
    if M >= 1024: chk('(b) SCRATCH/M in [35,60] (B=4, M=%d)' % M, 35 <= per <= 60, 'measured %.2f' % per)
    else: print('NOTE (b) SCRATCH/M at M=%d (B=4): %.2f (pre-registered range is for M >= 1024)' % (M, per))
    s16 = int(cells['G-M%d-N1000000-B16' % M]['SCRATCH'][0]['retainedBytes'])
    chk('(b) SCRATCH(B=16) - SCRATCH(B=4) within 20%% of 12 x M (M=%d)' % M, abs((s16 - s) - 12 * M) <= 0.2 * 12 * M, 'measured %d vs %d' % (s16 - s, 12 * M))
for M in (16, 1024, 65536):
    z = cells.get('Z-M%d-N0-B4' % M)
    if z and 'SCRATCH' in z:
        chk('(b) SCRATCH at N=0 equals SCRATCH at N=1e6 (M=%d), within 2%%' % M, abs(int(z['SCRATCH'][0]['retainedBytes']) - int(C(M, 1000000, 4)['SCRATCH'][0]['retainedBytes'])) <= 0.02 * int(C(M, 1000000, 4)['SCRATCH'][0]['retainedBytes']))
    else: chk('(b) N=0 cell present (M=%d)' % M, False)
# (c) allocation
A = lambda M, N, B=4: int(C(M, N, B)['CELL'][0]['alloc'])
for M in Ms:
    r = A(M, 4000000) / A(M, 100000)
    chk('(c) ALLOC(N=4e6)/ALLOC(N=1e5) in [20,60] (M=%d)' % M, 20 <= r <= 60, 'measured %.1f' % r)
slope = math.log(A(65536, 1000000) / A(16, 1000000)) / math.log(65536 / 16)
chk('(c) log-log slope of ALLOC vs M over 16..65536 at N=1e6 is below 0.5', slope < 0.5, 'measured %.3f' % slope)
chk('(c) ALLOC(M=16)/ALLOC(M=1024) >= 1.2 at N=1e6', A(16, 1000000) / A(1024, 1000000) >= 1.2, 'measured %.2f' % (A(16, 1000000) / A(1024, 1000000)))
chk('(c) ALLOC(M=65536)/ALLOC(M=1024) <= 1.5 at N=1e6', A(65536, 1000000) / A(1024, 1000000) <= 1.5, 'measured %.2f' % (A(65536, 1000000) / A(1024, 1000000)))
# (d) file lengths
for kind in ('treeLen', 'postLen'):
    for M in Ms:
        r = int(C(M, 4000000, 4)['CELL'][0][kind]) / int(C(M, 100000, 4)['CELL'][0][kind])
        chk('(d) %s(N=4e6)/%s(N=1e5) in [20,60] (M=%d)' % (kind, kind, M), 20 <= r <= 60, 'measured %.1f' % r)
    v = [int(C(M, 1000000, 4)['CELL'][0][kind]) for M in Ms]
    chk('(d) %s at N=1e6: largest/smallest across the five M below 3' % kind, max(v) / min(v) < 3, 'measured %.2f' % (max(v) / min(v)))
# (e) leaf postings
for M in Ms:
    p = float(C(M, 1000000, 4)['LEAFPOST'][0]['perLeaf'])
    chk('(e) LEAFPOST per leaf in [150,600] bytes (M=%d, N=1e6)' % M, 150 <= p <= 600, 'measured %.1f' % p)
bad = [(k, v['LEAFPOST'][0]['retainedBytes']) for k, v in cells.items() if k.startswith('G-') and int(v['LEAFPOST'][0]['retainedBytes']) < 0]
if bad: print('NOTE anomaly: negative retained heap in LEAFPOST (instrument limitation, GC baseline): %s' % bad)
# control / repeats
reps = [cells[k]['CELL'][0] for k in ('G-M1024-N1000000-B4', 'R2-M1024-N1000000-B4', 'R3-M1024-N1000000-B4')]
chk('repeats of (1024, 1e6, B=4): same num_leaves/treeLen/postLen, ALLOC within 1%', all(r['num_leaves'] == reps[0]['num_leaves'] and r['treeLen'] == reps[0]['treeLen'] and r['postLen'] == reps[0]['postLen'] and abs(int(r['alloc']) - int(reps[0]['alloc'])) <= 0.01 * int(reps[0]['alloc']) for r in reps), 'allocs %s' % [r['alloc'] for r in reps])
t = open(R + '/unit/unit.out').read()
chk('U5 control: new long[k] allocation differs by about 8 x (1e6 - 1e3)', abs((int(re.search(r'k=1000000 allocBytes=(\d+)', t).group(1)) - int(re.search(r'k=1000 allocBytes=(\d+)', t).group(1))) - 8 * (1000000 - 1000)) <= 0.01 * 8 * 999000)
chk('U5 control: constructor rejects M=0 and M=MAX_ARRAY_LENGTH+1', 'REJECT M=0 IllegalArgumentException' in t and 'REJECT M=2147483632 IllegalArgumentException' in t)
# ---------------- cluster ----------------
def an(label):
    d = R + '/cluster/' + label
    if not os.path.exists(d + '/wcs.txt'): return None
    o = os.popen('python3 %s/analyze_cluster.py %s' % (os.path.dirname(os.path.abspath(__file__)), d)).read()
    r = {}
    for l in o.splitlines():
        m = re.match(r'ANALYSIS (flush|rebuild) .*', l)
        if m: r[m.group(1)] = dict(re.findall(r'(\w+)=(\S+)', l))
    r['tmn'] = re.search(r'TOO_MANY_NODES_LINES (\d+)', open(d + '/readings.txt').read()).group(1)
    r['comps'] = o
    return r
CL = {k: an(k) for k in ('A2', 'A8', 'B2', 'B8a', 'B8b', 'B8c', 'C2', 'C8', 'B8ctl16')}
for k, v in CL.items():
    if v is None: print('NOTE cluster run %s missing' % k); continue
    print('NOTE cluster %s: flush %s | rebuild %s | tooManyNodes=%s | %s' % (k, {x: v['flush'][x] for x in ('segments', 'allocSum', 'leavesSum', 'valuesSum', 'treeLenSum', 'postLenSum')}, {x: v['rebuild'][x] for x in ('segments', 'allocSum', 'leavesSum')}, v['tmn'], ''))
if all(CL.get(k) for k in ('A2', 'A8', 'B2', 'B8a', 'C2', 'C8')):
    chk('C5 no "too many nodes" in any arm', all(v['tmn'] == '0' for v in CL.values() if v))
    for x in 'ABC':
        a2, a8 = CL[x + '2'], CL[x + '8' + ('a' if x == 'B' else '')]
        r = int(a8['flush']['treeLenSum']) / int(a2['flush']['treeLenSum'])
        chk('C5 BALANCED_TREE length N=8e6/N=2e6 in [3.5,4.2] (variant %s, flush)' % x, 3.5 <= r <= 4.2, 'measured %.2f' % r)
        r = int(a8['flush']['allocSum']) / int(a2['flush']['allocSum'])
        chk('C5 ALLOC N=8e6/N=2e6 in [3,5] (variant %s, flush)' % x, 3 <= r <= 5, 'measured %.2f' % r)
    t8 = [int(CL[k]['flush']['treeLenSum']) for k in ('A8', 'B8a', 'C8')]; p8 = [int(CL[k]['flush']['postLenSum']) for k in ('A8', 'B8a', 'C8')]
    chk('C5 BALANCED_TREE length across variants at N=8e6: largest/smallest below 1.3', max(t8) / min(t8) < 1.3, 'measured %.3f' % (max(t8) / min(t8)))
    chk('C5 POSTING_LISTS length across variants at N=8e6: largest/smallest below 2', max(p8) / min(p8) < 2, 'measured %.3f' % (max(p8) / min(p8)))
    al = {k: int(CL[k]['flush']['allocSum']) for k in ('A8', 'B8a', 'C8')}
    chk('C5 ALLOC(A)/ALLOC(B) and ALLOC(C)/ALLOC(B) each in [0.6,3.0] (N=8e6, flush)', 0.6 <= al['A8'] / al['B8a'] <= 3.0 and 0.6 <= al['C8'] / al['B8a'] <= 3.0, 'A/B %.2f C/B %.2f' % (al['A8'] / al['B8a'], al['C8'] / al['B8a']))
    chk('leaf counts: leavesSum(flush) per variant at N=8e6 follows ceil(values/M) (M = 128/1024/16384)', all(abs(int(CL[k]['flush']['leavesSum']) - math.ceil(int(CL[k]['flush']['valuesSum']) / M)) <= 1 for k, M in (('A8', 128), ('B8a', 1024), ('C8', 16384))), str({k: (CL[k]['flush']['leavesSum'], CL[k]['flush']['valuesSum']) for k in ('A8', 'B8a', 'C8')}))
    chk('variants ran the intended constant (M in the WCS lines)', all(CL[k]['flush']['M'] == "['%d']" % M or CL[k]['flush']['M'] == '[%d]' % M for k, M in (('A8', 128), ('B8a', 1024), ('C8', 16384))), str({k: CL[k]['flush']['M'] for k in ('A8', 'B8a', 'C8')}))
if CL.get('B8a') and CL.get('B8ctl16'):
    cb, cc = CL['B8a']['rebuild'], CL['B8ctl16']['rebuild']
    chk('C5 control: segments(16MiB) >= 10 x segments(1024MiB) on the rebuild path', int(cc['segments']) >= 10 * int(cb['segments']), '%s vs %s' % (cc['segments'], cb['segments']))
def segbuf(label):
    f = R + '/cluster/%s/segbuf.csv' % label
    return max([int(l.split(',')[1]) for l in open(f) if re.match(r'^\d+,\d+', l)] or [0]) if os.path.exists(f) else None
sb = {k: segbuf(k) for k in ('B8b', 'B8c', 'B8ctl16')}
print('NOTE peak SegmentBufferSpaceUsedBytes: %s (runs B2, B8a, A2 have no JMX poll, see README)' % sb)
if all(sb.values()):
    chk('C5 control: peak SegmentBufferSpaceUsedBytes at 16 MiB < 40 MiB and at 1024 MiB (B8b, B8c) > 100 MiB', sb['B8ctl16'] < 40 * 1048576 and min(sb['B8b'], sb['B8c']) > 100 * 1048576, '%.1f MiB vs %.1f / %.1f MiB' % (sb['B8ctl16'] / 1048576.0, sb['B8b'] / 1048576.0, sb['B8c'] / 1048576.0))
if CL.get('B8b') and CL.get('B8c'):
    ta = [int(CL[k]['flush']['treeLenSum']) for k in ('B8a', 'B8b', 'B8c')]
    chk('C5 noise: BALANCED_TREE length of the three B/8e6 flushes within 1%', (max(ta) - min(ta)) / min(ta) < 0.01, str(ta))
    al = [int(CL[k]['flush']['allocSum']) for k in ('B8a', 'B8b', 'B8c')]
    print('NOTE ALLOC (flush) of the three B/8e6 runs: %s (spread %.1f%%)' % (al, 100.0 * (max(al) - min(al)) / min(al)))
print('SUMMARY pass=%d fail=%d' % (sum(res), len(res) - sum(res)))
