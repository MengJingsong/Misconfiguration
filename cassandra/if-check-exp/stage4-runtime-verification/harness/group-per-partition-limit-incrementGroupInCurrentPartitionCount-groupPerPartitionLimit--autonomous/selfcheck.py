#!/usr/bin/env python3
"""Independent re-parse of the raw run-1 logs (not the analyzers). Usage: selfcheck.py <logdir>
Unit: re-reads the "STAGE4 ..." lines echoed in unit/ant.log (not unit.txt) and recomputes the B2f relations with plain loops.
Cluster: re-reads markers.txt, arms.txt, samples.csv and the node's system.log segment with its own windowing and its own per-query arithmetic."""
import sys, re, os, bisect, statistics
ld = sys.argv[1]; bad = []
def chk(name, cond, detail=''):
    print(('HOLDS    ' if cond else 'FAILS    ') + name, detail)
    if not cond: bad.append(name)
NO = 2**31 - 1
# ---- unit
txt = open(os.path.join(ld, 'unit', 'ant.log'), errors='replace').read()
B = int(re.search(r'STAGE4 B_ROWS=(\d+)', txt).group(1)); reps = int(re.search(r'STAGE4 reps=(\d+)', txt).group(1))
rows = {}
for m in re.finditer(r'STAGE4 run shape=(\w) gppl=(\S+) rowLimit=(\S+) returned=(\d+) pulled=(\d+) parts=(\d+) counted=(\d+) cip_before_close=(\d+) cip=(\d+) rowsCounted=(\d+) alloc=(\d+)', txt):
    g = NO if m.group(2) == 'NO_LIMIT' else int(m.group(2)); r = NO if m.group(3) == 'NO_LIMIT' else int(m.group(3))
    rows.setdefault((m.group(1), g, r), []).append([int(x) for x in m.group(4, 5, 6, 7, 8, 9, 10, 11)])  # ret, pulled, parts, counted, cipb, cip, rowsC, alloc
# the first-trigger rep (A, gppl=10, NO_LIMIT) and two warm-ups are extra lines of the A/NO_LIMIT/NO_LIMIT and B cells
cells = {k: v for k, v in rows.items()}
chk('unit: 18 cells (2 shapes x 3 gppl x 3 rowLimit) each with at least %d reps' % reps, len(cells) == 18 and all(len(v) >= reps for v in cells.values()), {k: len(v) for k, v in cells.items()})
chk('unit: shape A rows returned = min(20*min(gppl,1000), rowLimit) in every rep', all(x[0] == min(20 * min(g, 1000), r) for (s, g, r), v in cells.items() if s == 'A' for x in v))
ok = True
for (s, g, r), v in cells.items():
    if s != 'A': continue
    G = 20 * min(g, 1000)
    for x in v:
        want = (r <= x[1] <= r + 21) if G > r else (x[1] == (20 * (g + 1) if g < NO else 20000))
        ok &= want
chk('unit: shape A rows pulled = 20*(gppl+1) / 20000 / within [rowLimit, rowLimit+21] as stated', ok)
chk('unit: shape B rowLimit=NO_LIMIT: returned = pulled = 4*B_ROWS for all gppl, counted 4, cip 1 after close, 0 before', all(x[0] == 4 * B and x[1] == 4 * B and x[3] == 4 and x[5] == 1 and x[4] == 0 for g in (1, 10, NO) for x in cells[('B', g, NO)]), 'B_ROWS=%d' % B)
chk('unit: shape B rowLimit 100/10000: pulled in [rowLimit, rowLimit+1] for all gppl', all(r <= x[1] <= r + 1 for g in (1, 10, NO) for r in (100, 10000) for x in cells[('B', g, r)]))
al = {g: statistics.median(x[7] for x in cells[('B', g, NO)]) for g in (1, 10, NO)}
chk('unit: shape B median allocation within 10 % across gppl', max(al.values()) / min(al.values()) <= 1.10, {('NO' if g == NO else g): int(v) for g, v in al.items()})
mp = {r: statistics.median(x[1] for g in (1, 10, NO) for x in cells[('B', g, r)]) for r in (100, 10000, NO)}
chk('unit: control: shape B rows pulled follow rowLimit (100 < 10000 < 4*B_ROWS)', mp[100] < mp[10000] < mp[NO] == 4 * B, mp)
# ---- cluster
cd_ = os.path.join(ld, 'cluster', 'arms')
S = [tuple(int(x) for x in l.split(',')) for l in open(os.path.join(cd_, 'samples.csv')) if re.match(r'^\d+,\d+,\d+,\d+$', l.strip())]
T = [s[0] for s in S]
ev = {}
for l in open(os.path.join(cd_, 'arms.txt')):
    p = l.split()
    if p[1] in ('START', 'END'): ev.setdefault(p[2], {})[p[1]] = (int(p[0]), p[3:])
mk = [l.split() for l in open(os.path.join(cd_, 'markers.txt'))]
def peak(a):
    s, e = ev[a]['START'][0], ev[a]['END'][0]
    i, j = bisect.bisect_left(T, s), bisect.bisect_right(T, e)
    w = S[i:j]; return (max(x[1] for x in w) - w[0][1]) / 1e6
def bpq(a):
    n = len([m for m in mk if m[1] == a]); return (int(ev[a]['END'][1][3]) - int(ev[a]['START'][1][3])) / n
labels = [a for a in ev if a not in ('warmup', 'noise')]
chk('cluster: 16 forward + 6 reverse arms completed', len([a for a in labels if a.startswith('f_')]) == 16 and len([a for a in labels if a.startswith('r_')]) == 6, sorted(labels))
def want(a):
    sh, L = ev[a]['START'][1][0], ev[a]['START'][1][2]
    return 20 * (2000 if L == 'abs' else min(int(L), 2000)) if sh == 'A' else 20
chk('cluster: every query of every measured arm returned the stated number of groups', all(int(m[3]) == want(m[1]) for m in mk if m[1] in labels), 'queries %d' % len([m for m in mk if m[1] in labels]))
chk('cluster: 3 queries in every measured arm', all(len([m for m in mk if m[1] == a]) == 3 for a in labels))
for pre in ('f', 'r'):
    v = [bpq('%s_B_L%s_F5000' % (pre, l)) for l in ('1', '100', 'abs')]
    chk('cluster: %s shape B bytes read per query within 10 %% across L' % pre, max(v) / min(v) <= 1.10, [round(x) for x in v])
    h = [peak('%s_B_L%s_F5000' % (pre, l)) for l in ('1', '100', 'abs')]
    chk('cluster: %s shape B peak heap spread <= 30 MB across L' % pre, max(h) - min(h) <= 30, [round(x, 1) for x in h])
a = [bpq('f_A_L%s_F5000' % l) for l in ('1', '100', 'abs')]
chk('cluster: shape A bytes read: L=1 <= 10 %, L=100 <= 50 % of unset', a[0] <= 0.1 * a[2] and a[1] <= 0.5 * a[2], [round(x) for x in a])
ctl = peak('f_B_Labs_F100000') - peak('f_B_Labs_F5000')
chk('cluster: page-size control moves the shape B peak by > 50 MB', ctl > 50, '%.1f MB' % ctl)
fl = open(os.path.join(cd_, 'vmflags.txt')).read()
chk('cluster: JVM ran with the 1 GiB heap, G1, young generation caps', re.search(r'MaxHeapSize\s*=\s*1073741824', fl) and 'UseG1GC' in fl and re.search(r'G1MaxNewSizePercent\s*=\s*2\b', fl))
seg = open(os.path.join(cd_, 'system.log.segment'), errors='replace').read()
chk('cluster: no ERROR lines in the node log segment', not [l for l in seg.splitlines() if l.startswith('ERROR')])
body = '\n'.join(l for l in seg.splitlines() if 'JVM Arguments' not in l)
chk('cluster: no OutOfMemoryError, no dropped-message report in the node log', 'OutOfMemoryError' not in body and not re.search(r'messages were dropped|DroppedMessages|MessagingService.*dropped', body))
d = {l.split()[2]: int(l.split()[3]) for l in open(os.path.join(cd_, 'arms.txt')) if l.split()[1] == 'DISK'}
chk('cluster: data size unchanged (reads only)', abs(d['end'] - d['start']) <= 0.01 * d['start'], d)
print('SELFCHECK', 'ALL HOLD' if not bad else 'FAILS: %s' % bad); sys.exit(1 if bad else 0)
