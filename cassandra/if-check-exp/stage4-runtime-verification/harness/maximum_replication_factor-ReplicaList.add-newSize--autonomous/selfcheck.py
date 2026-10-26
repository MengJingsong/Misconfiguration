#!/usr/bin/env python3
"""Independent re-parse of the raw logs of maximum_replication_factor-ReplicaList.add-newSize--autonomous (run <dir>/unit/out.txt and
<dir>/cluster/{hist.csv,ddl.csv,stress-*.txt,summary.txt}). usage: python3 -I selfcheck.py <logdir e.g. ~/s4-b7-rl-logs/run1>
Recomputes every number the conclusion uses from the raw lines, not from the harness's own check lines."""
import csv, glob, os, re, sys
d = os.path.expanduser(sys.argv[1])
ok = True
def rep(name, good, detail):
    global ok
    ok &= bool(good)
    print(('HOLDS    ' if good else 'DOES NOT HOLD ') + name + ': ' + detail)

# ---- unit
rows = [dict(re.findall(r'(\w+)=(\S+)', l)) for l in open(d + '/unit/out.txt') if l.startswith('STAGE4 reading')]
def cap(n):
    c = 0 if n == 0 else 3 if n <= 3 else 9 if n <= 9 else None
    if c is None:
        c = 9
        while c < n: c *= 2
    return c
growth = [r for r in rows if r['phase'] == 'growth']
rep('unit growth rows', len(growth) == 9, f'{len(growth)} rows')
rep('unit capacity = 3/9/9*2^k', all(int(r['cap']) == cap(int(r['N'])) for r in growth), ', '.join(f"N={r['N']}:{r['cap']}" for r in growth))
rep('unit bytes = 16 + 4*cap (compressed oops, 8-aligned)', all(int(r['bytes']) == (16 + 4 * int(r['cap']) + 7) // 8 * 8 for r in growth), 'N=10: ' + [r for r in growth if r['N'] == '10'][0]['bytes'])
r10k = [r for r in growth if r['N'] == '10000'][0]
rep('N=10000 reallocs 13, cap 18432', r10k['reallocs'] == '13' and r10k['cap'] == '18432', str(r10k))
exact = [r for r in rows if r['phase'] == 'exact']
rep('exact capacity: no reallocation, cap = N', all(r['reallocs'] == '0' and r['cap'] == r['N'] for r in exact), f'{len(exact)} rows')
sweep = [r for r in rows if r['phase'] == 'sweep']
by = {}
for r in sweep: by.setdefault(r['N'], set()).add((r['cap'], r['reallocs'], r['bytes']))
rep('threshold sweep: one (cap, reallocs, bytes) triple per N across thr -1,1,3', len(sweep) == 9 and all(len(v) == 1 for v in by.values()), str(by))
chk = [l for l in open(d + '/unit/out.txt') if l.startswith('STAGE4 check')]
ctl = [l.strip() for l in chk if ' control-' in l]
rep('unit controls all ok', ctl and all(' ok ' in l for l in ctl), f'{len(ctl)} control checks')
heap = [l for l in open(d + '/unit/out.txt') if 'phase=heap' in l][0]
m = dict(re.findall(r'(\w+)=(\S+)', heap)); ratio = int(m['heapDelta']) / int(m['instrument'])
rep('heap of 10 retained 1M lists within 5 percent of instrument', 0.95 < ratio < 1.05, f'ratio {ratio:.3f}')

# ---- cluster
c = d + '/cluster'
if os.path.isdir(c):
    h = list(csv.DictReader(open(c + '/hist.csv')))
    after = {}
    for r in h:
        if r['label'] == 'after-stress': after[r['phase']] = (int(r['thr']), int(r['rep_bytes']), int(r['rep_instances']), int(r['total_bytes']))
    print('after-stress Replica[] by phase:', after)
    rep('six stress phases sampled', len(after) == 6, str(sorted(after)))
    allrep = [int(r['rep_bytes']) for r in h]
    rep('Replica[] bytes < 1 MB at every sample', max(allrep) < 1_000_000, f'max {max(allrep)}')
    byt = {}
    for ph, (t, b, i, tot) in after.items(): byt.setdefault(t, []).append(b)
    means = {t: sum(v) / len(v) for t, v in byt.items()}
    mx, mn = max(means.values()), min(means.values())
    rep('threshold means within 10 percent (or 50 KB)', (mx - mn) <= max(0.10 * (sum(means.values()) / len(means)), 50_000), f'{means}')
    noise = {t: max(v) - min(v) for t, v in byt.items()}
    print('noise (two phases per threshold):', noise)
    dd = list(csv.DictReader(open(c + '/ddl.csv')))
    def acc(ph, role, rf): return [r for r in dd if r['phase'] == ph and r['role'] == role and r['rf'] == str(rf)][0]['accepted'] == 'True'
    p0 = [r for r in dd if r['phase'] == 'P0'][0]
    rep('P0 ordinary role RF3 rejected at thr 1', p0['accepted'] == 'False' and 'above the failure threshold of 1' in p0['detail'], p0['detail'])
    good = True; det = []
    for i, t in enumerate([-1, 1, 3, -1, 1, 3]):
        ph = f'p{i+1}'
        e = {('ord', 3): t in (-1, 3), ('ord', 4): t == -1, ('ord', 1): True, ('su', 3): True}
        for (role, rf), want in e.items():
            got = acc(ph, role, rf)
            if got != want: good = False; det.append(f'{ph} thr={t} {role} RF{rf} got {got} want {want}')
    rep('DDL control matrix per threshold', good, '; '.join(det) or '24 rows as expected')
    for f in sorted(glob.glob(c + '/stress-*.txt')):
        t = open(f).read()
        err = re.search(r'Total errors\s*:\s*(\d+)', t); part = re.search(r'Total partitions\s*:\s*([\d,]+)', t)
        rep('stress ' + os.path.basename(f), err and int(err.group(1)) == 0 and part and int(part.group(1).replace(',', '')) >= 1_000_000, f'errors {err and err.group(1)} partitions {part and part.group(1)}')
    k = [r for r in h if r['phase'] == 'K200']
    if k:
        print('K200:', [(r['label'], r['rep_instances'], r['rep_bytes']) for r in k])
print('ALL HOLD' if ok else 'SOME PART DOES NOT HOLD')
