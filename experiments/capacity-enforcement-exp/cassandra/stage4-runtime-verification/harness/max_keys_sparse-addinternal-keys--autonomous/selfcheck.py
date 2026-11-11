#!/usr/bin/env python3
"""Independent re-parse of the raw logs of max_keys_sparse-addinternal-keys--autonomous run 1 (unit test.out; cluster stdout.txt, system.log, datalist.txt).
usage: selfcheck.py <logs dir, e.g. ~/s4-b34/logs/max_keys_sparse/run1>. Prints PASS/FAIL lines and a final count; does not read readings.txt for the checks."""
import re, sys, os, glob, collections
D = sys.argv[1]; res = []
def chk(name, ok, detail=''):
    res.append(ok); print(('PASS ' if ok else 'FAIL ') + name + ((' :: ' + detail) if detail else ''))
def kv(line): return dict(re.findall(r'([\w/]+)=(\S+)', line))
# ---------------- unit
cells = [kv(l) for l in open(D + '/unit/test.out') if l.startswith('STAGE4 cell')]
ctl = [kv(l) for l in open(D + '/unit/test.out') if l.startswith('STAGE4 control')]
chk('unit: 54 cells (2 modes x 9 plan cells x 3 reps)', len(cells) == 54, str(len(cells)))
bad = [c for c in cells if int(c['est']) != int(c['T']) * 116 + int(c['T']) * int(c['K']) * 108]
chk('unit: estimatedMemoryUse == T*116 + T*K*108 in every cell, recomputed here', not bad, str(bad[:1]))
sp = [c for c in cells if c['mode'] == 'SPARSE']; pf = [c for c in cells if c['mode'] == 'PREFIX']
chk('unit: SPARSE K<=5 finish ok; K>=6 FSWriteError with the "belongs to more than 5 keys in SPARSE mode" cause (all reps)',
    all((c['outcome'].startswith('ok') if int(c['K']) <= 5 else (c['outcome'] == 'FSWriteError' and 'belongs_to_more_than_5_keys_in_SPARSE_mode' in c['cause'])) for c in sp))
chk('unit: PREFIX finish ok for every K', all(c['outcome'].startswith('ok') for c in pf))
byk = collections.defaultdict(set)
for c in pf: byk[(int(c['K']), int(c['T']))].add(int(c['filelen']))
chk('unit: PREFIX file length deterministic across the 3 reps', all(len(v) == 1 for v in byk.values()))
l = {k: list(v)[0] for k, v in byk.items()}
chk('unit: PREFIX file length grows with K at T=10000 (K=1,4,5,6,7,50) incl. 5 -> 6', all(l[(a, 10000)] < l[(b, 10000)] for a, b in [(1, 4), (4, 5), (5, 6), (6, 7), (7, 50)]), str({k: v for k, v in l.items() if k[1] == 10000}))
e = {(int(c['K']), int(c['T'])): int(c['est']) for c in cells if c['mode'] == 'PREFIX'}
chk('unit: doubling T doubles the estimate (K=4, K=6)', e[(4, 20000)] == 2 * e[(4, 10000)] and e[(6, 20000)] == 2 * e[(6, 10000)])
d6 = e[(6, 10000)] - e[(5, 10000)]; chk('unit: no break at 5 -> 6: est(6) - est(5) == T*(108*1)=1,080,000 and est(5)-est(4) the same', d6 == 1080000 and e[(5, 10000)] - e[(4, 10000)] == 1080000, str(d6))
a = collections.defaultdict(list)
for c in cells: a[(c['mode'], int(c['K']), int(c['T']))].append(int(c['allocAdds']))
chk('unit: allocated bytes of the add loop per add are the same SPARSE vs PREFIX (+-2%) at K=5 and K=6 (the mode does not change building cost)',
    all(abs(sum(a[('SPARSE', k, 10000)]) / sum(a[('PREFIX', k, 10000)]) - 1) < 0.02 for k in (5, 6)))
per = {k: sum(a[('PREFIX', k, 10000)]) / 3 / 10000 for k in (4, 5, 6, 7)}   # allocated bytes per term (K adds): linear in K means no break at 5 -> 6
dd = [per[5] - per[4], per[6] - per[5], per[7] - per[6]]
chk('unit: allocated bytes per term (PREFIX) linear in K over 4..7: successive differences within 2% of each other', max(dd) / min(dd) < 1.02, str(dd))
chk('unit: control T=20000/40000/80000: closed segments within 1 of floor(E/8MiB); no estimate above 8MiB+223',
    all(abs(int(c['closedSegments']) - int(c['floorE/max'])) <= 1 and int(c['maxAnyEst']) <= 8388608 + 223 for c in ctl) and len(ctl) == 3, str([(c['T'], c['closedSegments']) for c in ctl]))
chk('unit: control segments grow with volume (1 < 3 < 7)', [int(c['closedSegments']) for c in ctl] == sorted(int(c['closedSegments']) for c in ctl) and int(ctl[0]['closedSegments']) < int(ctl[2]['closedSegments']))
# ---------------- cluster
C = D + '/cluster/main'
import zipfile
so = open(C + '/stdout.txt', errors='replace').read(); sl = open(C + '/system.log', errors='replace').read()
for z in glob.glob(C + '/system.log.*.zip'):   # the node's log rolled at UTC midnight during the run: the archive holds the K=6 lines
    sl += zipfile.ZipFile(z).read(zipfile.ZipFile(z).namelist()[0]).decode(errors='replace')
builds = [kv(l) for l in so.splitlines() if l.startswith('MKS_BUILD')]
def tname(b): return re.search(r'/ks/([a-z0-9_]+)-', b['file']).group(1)
bt = collections.defaultdict(list)
for b in builds:
    m = re.search(r'/ks/([a-z0-9_]+)-', b['file'])
    if m: bt[m.group(1)].append(b)
exp = {'k5': (12000, 7872000), 'k6': (10000, 7640000), 'k1000': (60, 6486960)}
for K in ('k5', 'k6', 'k1000'):
    for m in ('sparse', 'prefix'):
        t = 't_%s_%s' % (m, K); bs = bt.get(t, [])
        chk('cluster: %s one build, terms and estimate exact' % t, len(bs) == 1 and int(bs[0]['terms']) == exp[K][0] and int(bs[0]['est']) == exp[K][0] * 116 + 60000 * 108 and int(bs[0]['est']) == exp[K][1], str(bs[:1]))
        chk('cluster: %s build mode matches' % t, len(bs) == 1 and bs[0]['mode'] == m.upper())
for K in ('k5', 'k6', 'k1000'):
    chk('cluster: sparse and prefix estimates equal at %s' % K, bt['t_sparse_' + K][0]['est'] == bt['t_prefix_' + K][0]['est'])
def fails(t): return [l for l in sl.splitlines() if 'Failed to build index segment' in l and '/ks/%s-' % t in l]
for t, want in [('t_sparse_k5', 0), ('t_sparse_k6', 1), ('t_sparse_k1000', 1), ('t_prefix_k5', 0), ('t_prefix_k6', 0), ('t_prefix_k1000', 0)]:
    chk('cluster: "Failed to build index segment" count for %s == %d' % (t, want), len(fails(t)) == want, str(len(fails(t))))
blk = re.findall(r"IOException: Term - '(\d+)' belongs to more than 5 keys in SPARSE mode", sl)
chk('cluster: system.log carries the line-599 message (SPARSE mode) for the two failing tables', len(blk) >= 2, str(blk))
chk('cluster: no "Failed to flush index" (merge path) in the flush phase', 'Failed to flush index' not in sl)
dl = open(C + '/datalist.txt').read()
def files(t):
    m = re.search(r'(/[^\n]*/ks/%s-[0-9a-f]+):\n(.*?)(?:\n\n|\Z)' % t, dl, re.S); return m.group(2) if m else ''
for t in ('t_sparse_k6', 't_sparse_k1000'):
    f = files(t); si = re.findall(r'\s(\d+) [A-Z][a-z]{2}\s+\d+\s+[\d:]+ (\S*SI_\S+)', f); dd = re.findall(r'\s(\d+) [A-Z][a-z]{2}\s+\d+\s+[\d:]+ (\S*-Data\.db)', f)
    chk('cluster: %s: index file is a stub (<100 B) while the base Data.db exists with data' % t, si and int(si[0][0]) < 100 and dd and int(dd[0][0]) > 100000, str((si, dd)))
for t in ('t_sparse_k5', 't_prefix_k5', 't_prefix_k6', 't_prefix_k1000'):
    f = files(t); si = re.findall(r'\s(\d+) [A-Z][a-z]{2}\s+\d+\s+[\d:]+ (\S*SI_\S+)', f)
    chk('cluster: %s: index file has real size (> 100 kB)' % t, si and int(si[0][0]) > 100000, str(si))
# positive control
def seg(t): return [l for l in sl.splitlines() if 'Flushed index segment' in l and '/ks/%s-' % t in l]
s1, s64 = len(seg('t_ctl_mb1')), len(seg('t_ctl_mb64'))
chk('cluster control (qualitative): 1 MiB option logs many "Flushed index segment" lines (>= 5), 64 MiB logs 0', s1 >= 5 and s64 == 0, 'mb1=%d mb64=%d' % (s1, s64))
print('NUMERIC-PREDICTION (frozen B3f c: 8 +-1 lines for 1 MiB) %s: observed %d' % ('MET' if 7 <= s1 <= 9 else 'MISSED', s1))
cb1 = bt.get('t_ctl_mb1', []); cb64 = bt.get('t_ctl_mb64', [])
print('INFO control builds (all stages incl. the two flushes): mb1 %d builds, mb64 %d builds; ests %s / %s' % (len(cb1), len(cb64), [b['est'] for b in cb1], [b['est'] for b in cb64]))
cmp1 = cb1[2:]; mx1 = max(int(b['est']) for b in cmp1)  # builds 1-2 are the two memtable flushes (1 GiB threshold); the rest are the compaction's segments

print('NUMERIC-PREDICTION (frozen: 7..9 compaction builds for 1 MiB) %s: observed %d' % ('MET' if 7 <= len(cmp1) <= 9 else 'MISSED', len(cmp1)))
chk('cluster control: compaction builds of mb1 outnumber mb64 compaction builds (1) by >= 5', len(cmp1) - len(cb64[2:]) >= 5 and len(cb64[2:]) == 1, '%d vs %d' % (len(cmp1), len(cb64[2:])))
chk('cluster control: no mb1 compaction build above 1 MiB + 223 (the cap binds on builder memory)', mx1 <= 1048576 + 223, str(mx1))
print('RESULT %d PASS %d FAIL' % (sum(res), len(res) - sum(res)))
