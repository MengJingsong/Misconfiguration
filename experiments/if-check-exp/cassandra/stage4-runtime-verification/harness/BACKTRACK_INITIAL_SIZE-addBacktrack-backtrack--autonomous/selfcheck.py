#!/usr/bin/env python3
"""Independent re-parse of the raw files (results section 5). Does not import or reuse the analysers; uses a formula for the unit tier
(L from E by the doubling rule) and re-reads bt-stats.txt, system.log and session.log directly for the cluster tier. Usage: selfcheck.py <run1-dir>"""
import sys, os, re, glob, csv
run = sys.argv[1]
ok = bad = 0
def chk(c, m):
    global ok, bad
    if c: ok += 1
    else: bad += 1
    print(('OK  ' if c else 'BAD ') + m)
def Lof(E):   # smallest 48*2^k with E <= 16*2^k
    L = 48
    while E > L // 3: L *= 2
    return L
# ---- unit: ant.log RESULT lines must equal results.csv; recompute L from E and E from shape/D
for d in sorted(glob.glob(run + '/unit/T*')):
    T = int(os.path.basename(d)[1:])
    csvrows = [l.strip() for l in open(d + '/results.csv') if not l.startswith('arm,')]
    antrows = [re.sub(r'^.*?RESULT,', '', l).strip() for l in open(d + '/ant.log', errors='replace') if 'RESULT,' in l and 'RESULT,arm,' not in l]
    chk(csvrows == antrows, 'unit T%d: results.csv (%d rows) identical to the RESULT lines in ant.log (%d)' % (T, len(csvrows), len(antrows)))
    for l in csvrows:
        f = l.split(',')
        arm, buf, shape = f[0], f[1], f[2]
        if arm == 'reuse': chk(f[7] == '48' and f[9] == '192', 'T%d %s %s fresh=48 reused keeps 192' % (T, arm, buf)); continue
        if arm == 'thr':
            Tm, thr = [int(x) for x in f[11].split(';')]; flags = f[12].split(';'); p = [int(x) for x in f[13].split(';')]; o = [int(x) for x in f[14].split(';')]
            chk(thr == T * 1048576 and flags == ['false', 'false', 'true'] and o == p and p[0] >= (T - 1) * 1048576 and p[1] >= T * 1048576 and int(f[8]) == 1024 and int(f[9]) == Lof(1024),
                'T%d thr: threshold %d, flags %s, sizeOffHeap==pos %s, E=%s L=%s' % (T, thr, flags, o == p, f[8], f[9])); continue
        D = int(f[3]); Fn = int(f[4]); E = int(f[8]); L = int(f[9])
        expE = {'chain': 0, 'sparse': D, 'split': 3 * D, 'sparse+filler': 64, 'sparse(put)': D}[shape]
        chk(E == expE and L == Lof(E) and int(f[10]) == 16 + 4 * L and f[11] == f[12] and f[13] == f[14] and f[6] == f[5] and f[7] == '48',
            'T%d %s %s: E=%d (shape rule %d), L=%d (doubling rule %d), sizes unchanged, content nodes %s==%s' % (T, arm, buf, E, expE, L, Lof(E), f[6], f[5]))
    for arm in set(l.split(',')[0] for l in csvrows):
        v = set((l.split(',')[8], l.split(',')[9]) for l in csvrows if l.split(',')[0] == arm)
        chk(len(v) == 1, 'T%d arm %s (E,L) identical for ON_HEAP and OFF_HEAP: %s' % (T, arm, v))
a = {}
for d in sorted(glob.glob(run + '/unit/T*')):
    for l in open(d + '/results.csv'):
        f = l.strip().split(',')
        if f[0] in ('arm', 'thr', 'reuse'): continue
        a.setdefault((f[0], f[1]), set()).add((f[8], f[9]))
chk(all(len(v) == 1 for v in a.values()), 'unit: every arm gives one (E,L) across the three T JVMs (%d arm/buffer pairs)' % len(a))
tests = [open(f, errors='replace').read() for f in glob.glob(run + '/unit/T*/ant.log')]
chk(all('Tests run: 1, Failures: 0, Errors: 0' in t for t in tests) and len(tests) == 3, 'unit: all three ant runs report Tests run: 1, Failures: 0, Errors: 0')
# ---- cluster
def stats(path):
    s = open(path).read().strip(); d = dict(re.findall(r'(\w+)=(\d+)', s))
    return int(d['cursors']), {int(k[4:]): int(v) for k, v in d.items() if k.startswith('grow')}
U = {'B': 1, 'KiB': 1024, 'MiB': 1 << 20, 'GiB': 1 << 30}
mx = {}; S = {}
for lab in ('hb64', 'hb256', 'hb512', 'oo64', 'm3', 'sl'):
    d = run + '/cluster/' + lab
    if not os.path.isdir(d): print('no', lab); continue
    cur, grow = stats(d + '/bt-stats.txt')
    log = open(d + '/system.log', errors='replace').read()
    chk(len(re.findall(r'^ERROR', log, re.M)) == 0, '%s: no ERROR lines in system.log' % lab)
    cmd = open(d + '/evidence/cmdline.txt').read()
    chk('-Xms1G' in cmd and '-Xmx1G' in cmd and 'byteman' in cmd, '%s: live command line has -Xms1G -Xmx1G and the Byteman agent' % lab)
    y = open(d + '/evidence/yaml-keys.txt').read()
    want = {'hb64': ('ByteOrdered', 'heap_buffers', 'memtable_heap_space: 64MiB'), 'hb256': ('ByteOrdered', 'heap_buffers', 'memtable_heap_space: 256MiB'), 'hb512': ('ByteOrdered', 'heap_buffers', 'memtable_heap_space: 512MiB'),
            'oo64': ('ByteOrdered', 'offheap_objects', 'memtable_heap_space: 64MiB'), 'm3': ('Murmur3', 'heap_buffers', 'memtable_heap_space: 256MiB'), 'sl': ('ByteOrdered', 'heap_buffers', 'memtable_heap_space: 256MiB')}[lab]
    chk(all(w in y for w in want) and ('memtable_offheap_space: 64MiB' in y if lab == 'oo64' else True), '%s: yaml has %s' % (lab, want))
    sch = open(d + '/schema.txt').read(); chk(("memtable = 'trie'" in sch) == (lab != 'sl'), "%s: table memtable option as designed (trie=%s)" % (lab, lab != 'sl'))
    if lab in ('hb64', 'hb256', 'hb512', 'oo64'):
        chk(sorted(grow) == [48, 96, 192, 384, 768, 1536] and len(set(grow.values())) == 1 and grow[48] >= 16, '%s: grow histogram %s' % (lab, grow))
        mx[lab] = 2 * max(grow)
        sj = open(run + '/cluster/session.log').read()
        flushes = re.findall(r'Enqueuing flush of ks\.t, Reason: (\w+), Usage: ([\d.]+)(\w+) \((\d+)%\) on-heap, ([\d.]+)(\w+) \((\d+)%\) off-heap', log)
        lim = [f for f in flushes if f[0] == 'MEMTABLE_LIMIT']
        chk(len(lim) >= 1, '%s: %d MEMTABLE_LIMIT flushes of ks.t, %d total' % (lab, len(lim), len(flushes)))
        if lim: S[lab] = (float(lim[0][1]) * U[lim[0][2]] / 1048576, float(lim[0][4]) * U[lim[0][5]] / 1048576, [round(float(f[1]) * U[f[2]] / 1048576, 1) for f in lim])
    elif lab == 'm3': chk(cur >= 1000 and not grow, 'm3: cursors %d, grow %s' % (cur, grow))
    else: chk(cur == 0 and not grow, 'sl: cursors %d, grow %s' % (cur, grow))
chk(len(set(mx.values())) == 1 and set(mx.values()) == {3072} if len(mx) == 4 else False, 'largest array equal in the four BOP trie labels: %s' % mx)
# accounting straight from session.log lines
sj = open(run + '/cluster/session.log').read()
accs = re.findall(r'acct (\{.*\})', sj)
import json
accs = [json.loads(x) for x in accs]
labsorder = []
for line in sj.splitlines():
    m = re.search(r'start node label (\w+)', line)
    if m: labsorder.append(m.group(1))
chk(len(accs) >= 4 * len(labsorder), 'session.log has %d accounting records for %d labels' % (len(accs), len(labsorder)))
# before_scan / after_scan pairs
bs = [x for x in accs if x['tag'] == 'before_scan']; as_ = [x for x in accs if x['tag'] == 'after_scan']
chk(len(bs) == len(as_) == len(labsorder) and all(b['MemtableOnHeapDataSize'] == a['MemtableOnHeapDataSize'] and b['MemtableOffHeapDataSize'] == a['MemtableOffHeapDataSize'] for b, a in zip(bs, as_)),
    'accounting identical before/after the scan phase in %d labels; on-heap bytes per label: %s' % (len(bs), [b['MemtableOnHeapDataSize'] for b in bs]))
print('first MEMTABLE_LIMIT flush usage (on, off MiB, all on-heap MiB):', S)
if all(l in S for l in ('hb64', 'hb256', 'hb512')):
    chk(3 <= S['hb256'][0] / S['hb64'][0] <= 5 and 6 <= S['hb512'][0] / S['hb64'][0] <= 10, 'control ratios %.2f and %.2f' % (S['hb256'][0] / S['hb64'][0], S['hb512'][0] / S['hb64'][0]))
if 'oo64' in S: chk(10 <= S['oo64'][1] <= 40, 'oo64 off-heap usage at first limit flush %.1f MiB' % S['oo64'][1])
# nothing left running
import subprocess
ps = subprocess.run("ps -eo pid,cmd | grep '[s]4-bt'", shell=True, stdout=subprocess.PIPE, text=True).stdout
chk('CassandraDaemon' not in ps, 'no CassandraDaemon of this run left (ps filter s4-bt)')
print('SUMMARY ok=%d bad=%d' % (ok, bad))
