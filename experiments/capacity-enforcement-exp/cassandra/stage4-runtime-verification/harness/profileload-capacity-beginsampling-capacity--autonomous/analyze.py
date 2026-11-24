#!/usr/bin/env python3
"""Apply the frozen B2f/B2g (S4-A2) and B3f/B3g (S4-A4) rules to the raw files.
usage: analyze.py <unit-test-log> <cluster-dir>"""
import re, sys, os
res = []
def chk(name, ok, detail=''):
    res.append(ok); print(('PASS ' if ok else 'FAIL ') + name + (' | ' + detail if detail else ''))
# ---------- unit ----------
log = open(sys.argv[1]).read()
arms = {}
for m in re.finditer(r'RESULT order=(ASC|RND) cap=(-?\d+) N=(\d+) size=(\d+) expected=(\d+) bytes=(\d+) bytesPerEntry=([\d.]+)', log):
    o, cap, n, size, exp, b, bpe = m.groups(); arms[(o, int(cap))] = (int(size), int(b), float(bpe))
fh = re.findall(r'RESULT control=fieldHuge cap=10 size=(\d+)', log)
inact = re.findall(r'RESULT control=inactive queue=(\S+)', log)
print('UNIT arms parsed:', len(arms))
chk('U: 16 arms present', len(arms) == 16)
for (o, cap), (size, b, bpe) in sorted(arms.items()):
    exp = min(max(1, cap), 50000)
    chk(f'U: {o} cap={cap} size={size} == min(max(1,cap),N)={exp}', size == exp, f'bytes={b} bpe={bpe}')
big = [bpe for (o, cap), (size, b, bpe) in arms.items() if size >= 256 and cap != 100000]
mean = sum(big) / len(big)
chk('U: bytesPerEntry of binding arms with size>=256 within +-20% of mean', all(abs(x - mean) <= 0.2 * mean for x in big), f'mean={mean:.1f} range={min(big)}..{max(big)}')
for o in ('ASC', 'RND'):
    b1024 = arms[(o, 1024)][1]; b100k = arms[(o, 100000)][1]
    chk(f'U: {o} bytes(1024) < 0.1*bytes(100000)', b1024 < 0.1 * b100k, f'{b1024} vs {b100k}')
    chk(f'U: {o} control size=50000 and bytes>=1MB', arms[(o, 100000)][0] == 50000 and b100k >= 1_000_000)
chk('U: fieldHuge size 10', fh[-1:] == ['10'], str(fh[-1:]))
chk('U: inactive baseline null', inact[-1:] == ['null'], str(inact[-1:]))
# ---------- cluster ----------
d = sys.argv[2]
def histo(f):
    c = b = 0; tot = None
    for line in open(f):
        p = line.split()
        if len(p) >= 4 and p[3] == 'org.apache.cassandra.metrics.Sampler$Sample': c, b = int(p[1]), int(p[2])
        if p and p[0] == 'Total': tot = int(p[2])
    return c, b, tot
def used(f):
    m = re.search(r'garbage-first heap\s+total \d+K, used (\d+)K', open(f).read()); return int(m.group(1))
rl = open(os.path.join(d, 'run-cluster.log')).read()
bc, _, btot = histo(os.path.join(d, 'histo-baseline.txt'))
chk('C: baseline no Sample instances', bc == 0, f'live={btot}')
pl = open(os.path.join(d, 'profileload-s2000.txt')).read()
chk('C: nodetool -s 2000 rejected', 'Capacity (-s) cannot exceed 1024.' in pl)
blocks = rl.split('================ ARM C=')[1:]
rows = {}
for blk in blocks:
    C = int(blk.split()[0])
    D0, W0 = map(int, re.search(r'D0=(\d+) W0=(\d+)', blk).groups())
    D1, W1 = map(int, re.search(r'D1=(\d+) W1=(\d+)', blk).groups())
    S = (W1 - W0) - (D1 - D0)
    c1, b1, l1 = histo(os.path.join(d, f'histo-M1-{C}.txt')); c2, b2, l2 = histo(os.path.join(d, f'histo-M2-{C}.txt'))
    u1, u2 = used(os.path.join(d, f'heapinfo-M1-{C}.txt')), used(os.path.join(d, f'heapinfo-M2-{C}.txt'))
    so = open(os.path.join(d, f'stress-{C}.out')).read()
    err = re.search(r'Total errors\s*:\s*([\d,]+)', so).group(1)
    rows[C] = dict(S=S, D=D1 - D0, W=W1 - W0, c1=c1, b1=b1, c2=c2, dK=u1 - u2, u1=u1, u2=u2, l1=l1, l2=l2, dl=l1 - l2, err=err)
    print(f'C={C}: W={W1-W0} drops={D1-D0} S={S} count1={c1} bytes1={b1} count2={c2} usedK {u1}->{u2} delta={u1-u2}K live {l1}->{l2} liveDelta={l1-l2} stressErrors={err}')
ctl = rows[2000000]
chk('C: control count1 ~ S (|c1-S| <= 0.001 S) and S >= 900000', abs(ctl['c1'] - ctl['S']) <= 0.001 * ctl['S'] and ctl['S'] >= 900000, f"{ctl['c1']} vs {ctl['S']}")
for C in (256, 1024, 100000):
    chk(f'C: count1 == C for C={C}', rows[C]['c1'] == C, str(rows[C]['c1']))
    chk(f'C: S >= 900000 for C={C}', rows[C]['S'] >= 900000, str(rows[C]['S']))
for C in rows:
    chk(f'C: count2 <= 1 for C={C}', rows[C]['c2'] <= 1, str(rows[C]['c2']))
cd = ctl['dK'] * 1024
chk('C: control G1-used delta >= 20 MB', cd >= 20e6, f'{cd/1e6:.1f} MB')
chk('C: delta(100000) <= 0.3 * control delta', rows[100000]['dK'] * 1024 <= 0.3 * cd, f"{rows[100000]['dK']*1024/1e6:.1f} MB vs {0.3*cd/1e6:.1f} MB")
for C in (256, 1024):
    chk(f'C: delta({C}) <= 5 MB', rows[C]['dK'] * 1024 <= 5e6, f"{rows[C]['dK']*1024/1e6:.1f} MB")
print('SECONDARY (S4-A6) live-bytes deltas: ' + ', '.join(f"C={C}: {rows[C]['dl']/1e6:.2f} MB" for C in rows))
print('SECONDARY per-entry live bytes: ' + ', '.join(f"C={C}: {rows[C]['dl']/max(1,rows[C]['c1']):.1f} B" for C in rows))
print(f'TOTAL: {sum(res)} PASS, {len(res)-sum(res)} FAIL')
