#!/usr/bin/env python3
"""Independent re-parse of the raw run-1 logs (not the analyzers). Usage: selfcheck.py <logdir>
Unit: re-reads the "STAGE4 ..." lines echoed in ant.log (not unit.txt) and recomputes groups/pulled/retained/control with plain loops.
Cluster: re-reads markers.txt, arms.txt, samples.csv and the node's system.log segment with its own windowing."""
import sys, re, os, bisect, statistics
ld = sys.argv[1]; bad = []
def chk(name, cond, detail=''):
    print(('HOLDS    ' if cond else 'FAILS    ') + name, detail)
    if not cond: bad.append(name)
# ---- unit
rows = {'run': {}, 'ctl': {}}; R = None
for l in open(os.path.join(ld, 'unit', 'ant.log'), errors='replace'):
    m = re.search(r'STAGE4 R=(\d+)', l)
    if m: R = int(m.group(1))
    m = re.search(r'STAGE4 (run|ctl) N=(\S+) groups=(\d+) pulled=(\d+) counted=(\d+) countedInPartition=(\d+) rowsCounted=(\d+) alloc=(\d+) used_before=(\d+) used_after=(\d+)', l)
    if m:
        n = R if m.group(2) == 'NO_LIMIT' else int(m.group(2))
        rows[m.group(1)].setdefault(n, []).append([int(x) for x in m.group(3, 4, 5, 6, 7, 8, 9, 10)])
chk('unit: R parsed; 5 N values x 5 reps in both arms (+1 first-trigger rep at N=10 in the run arm)', R and all(len(rows[k]) == 5 for k in rows) and all(len(v) == (6 if (k == 'run' and n == 10) else 5) for k in rows for n, v in rows[k].items()), '%s' % {k: {n: len(v) for n, v in d.items()} for k, d in rows.items()})
chk('unit: groups == min(N,R) in all 50 reps', all(r[0] == min(n, R) for k in rows for n, v in rows[k].items() for r in v))
chk('unit: counter.counted() equals groups returned (one less at N=R: the last open group is closed after the read)', all(r[2] == (r[0] if n < R else r[0] - 1) for k in rows for n, v in rows[k].items() for r in v))
chk('unit: rows pulled = N+1 for N<R, R for N=R', all((r[1] == n + 1) if n < R else (r[1] == R) for n, v in rows['run'].items() for r in v), {n: sorted({r[1] for r in v}) for n, v in rows['run'].items()})
ret = {n: statistics.median(r[7] for r in v) for n, v in rows['run'].items()}
chk('unit: median retained heap after GC flat within 5%', (max(ret.values()) - min(ret.values())) / min(ret.values()) <= 0.05, {n: int(x) for n, x in ret.items()})
al = {n: statistics.median(r[5] for r in v) for n, v in rows['run'].items()}; ns = sorted(al)
chk('unit: median allocation rises with N', all(al[a] < al[b] for a, b in zip(ns, ns[1:])), {n: int(x) for n, x in al.items()})
cd = {n: statistics.median(r[7] - r[6] for r in v) for n, v in rows['ctl'].items()}
chk('unit: control retained delta rises with N and exceeds 1 MB at N=R', all(cd[a] < cd[b] for a, b in zip(ns[2:], ns[3:])) and cd[R] > 1e6, {n: int(x) for n, x in cd.items()})
noise = [abs(int(b) - int(a)) for a, b in re.findall(r'STAGE4 noise rep=\d+ used_before=(\d+) used_after=(\d+)', open(os.path.join(ld, 'unit', 'ant.log'), errors='replace').read())]
chk('unit: no-query noise swing far below the control delta at N=R', noise and max(noise) * 10 <= cd[R], 'noise max %s B' % (max(noise) if noise else None))
# ---- cluster
cd_ = os.path.join(ld, 'cluster', 'arms')
S = [tuple(int(x) for x in l.split(',')) for l in open(os.path.join(cd_, 'samples.csv')) if re.match(r'^\d+,\d+,\d+,\d+$', l.strip())]
T = [s[0] for s in S]
ev = {}
for l in open(os.path.join(cd_, 'arms.txt')):
    p = l.split()
    if p[1] in ('START', 'END'): ev.setdefault(p[2], {})[p[1]] = (int(p[0]), p[3:])
mk = [l.split() for l in open(os.path.join(cd_, 'markers.txt'))]
def arm_stats(a):
    s, e = ev[a]['START'][0], ev[a]['END'][0]
    i, j = bisect.bisect_left(T, s), bisect.bisect_right(T, e)
    w = S[i:j]; return (max(x[1] for x in w) - w[0][1]) / 1e6, w[-1][3] - w[0][3], len(w)
labels = [a for a in ev if a not in ('warmup', 'noise')]
chk('cluster: 12 measured arms completed', len(labels) == 12, sorted(labels))
chk('cluster: every query of every measured arm returned min(N,200000) rows', all(int(m[4]) == (200000 if ev[m[1]]['START'][1][1] == 'absent' else min(int(ev[m[1]]['START'][1][1]), 200000)) for m in mk if m[1] in labels), 'queries %d' % len([m for m in mk if m[1] in labels]))
chk('cluster: 100 queries in every measured arm', all(len([m for m in mk if m[1] == a]) == 100 for a in labels))
pk = {a: arm_stats(a)[0] for a in labels}
f = [pk['f_N%s_P1000' % n] for n in ('1', '100', '10000', 'abs')]; r = [pk['r_N%s_P1000' % n] for n in ('1', '100', '10000', 'abs')]
chk('cluster: N=absent minus N=1 peak heap within 30 MB (both sweeps)', abs(f[3] - f[0]) <= 30 and abs(r[3] - r[0]) <= 30, 'fwd %s rev %s' % ([round(x, 1) for x in f], [round(x, 1) for x in r]))
chk('cluster: control (P=300000) exceeds P=1000 by > 30 MB', pk['c_Nabs_P300000'] - pk['f_Nabs_P1000'] > 30, '%.1f vs %.1f' % (pk['c_Nabs_P300000'], pk['f_Nabs_P1000']))
fl = open(os.path.join(cd_, 'vmflags.txt')).read()
chk('cluster: JVM ran with the 1 GiB heap, G1, young generation caps', 'MaxHeapSize' in fl and re.search(r'MaxHeapSize\s*=\s*1073741824', fl) and 'UseG1GC' in fl and re.search(r'G1MaxNewSizePercent\s*=\s*2\b', fl))
seg = open(os.path.join(cd_, 'system.log.segment'), errors='replace').read()
chk('cluster: no ERROR lines in the node log segment', not [l for l in seg.splitlines() if l.startswith('ERROR')])
body = '\n'.join(l for l in seg.splitlines() if 'JVM Arguments' not in l)
chk('cluster: no OutOfMemoryError, no dropped-message report in the node log', 'OutOfMemoryError' not in body and not re.search(r'messages were dropped|DroppedMessages|MessagingService.*dropped', body))
d = {l.split()[2]: int(l.split()[3]) for l in open(os.path.join(cd_, 'arms.txt')) if l.split()[1] == 'DISK'}
chk('cluster: data size unchanged (reads only)', abs(d['end'] - d['start']) <= 0.01 * d['start'], d)
print('SELFCHECK', 'ALL HOLD' if not bad else 'FAILS: %s' % bad); sys.exit(1 if bad else 0)
