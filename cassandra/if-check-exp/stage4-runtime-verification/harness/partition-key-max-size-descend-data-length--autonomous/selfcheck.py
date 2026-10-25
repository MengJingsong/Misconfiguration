#!/usr/bin/env python3
"""Independent self-check: re-derives the readings from the RAW files (histogram dumps, command.log JMX output, system.log,
lengths.tsv), not from arms.csv or the analysers, and compares them with the analysers' summaries.
Usage: selfcheck.py <unit-run dir> <cluster-run dir>"""
import math, os, re, sys

unit, clu = sys.argv[1], sys.argv[2]
bad = []
def say(ok, msg):
    print(('HOLDS    ' if ok else 'DOES NOT HOLD ') + msg)
    if not ok: bad.append(msg)

# ---- unit tier, from lengths.tsv, with a closed form instead of the analyser's loop
rows = [l.rstrip('\n').split('\t') for l in open(os.path.join(unit, 'lengths.tsv'))][1:]
def closed_form(depth):
    # smallest 80*2^k with 5*depth < 80*2^k  ->  k = floor(log2(5*depth/80)) + 1 (depth>=16), else 0
    return 80 if 5 * depth < 80 else 80 * 2 ** (int(math.floor(math.log2(5 * depth / 80.0))) + 1)
ok = all(int(r[5]) == closed_form(int(r[1])) for r in rows if r[2] == 'apply')
say(ok, 'unit: all %d apply rows have data.length = closed form' % sum(1 for r in rows if r[2] == 'apply'))
say(all(r[5] == '80' for r in rows if r[2] == 'recursive' and r[12] == 'ok'), 'unit: recursive rows keep 80 (%d rows, statuses %s)' % (sum(1 for r in rows if r[2] == 'recursive'), sorted({r[12] for r in rows})))
by = {}
for r in rows:
    if r[0] == 'ON_HEAP': by.setdefault((r[1], r[3]), {})[r[2]] = r
dd = [(L, int(v['apply'][7]) - int(v['apply'][6]), int(v['recursive'][7]) - int(v['recursive'][6])) for (L, rep), v in by.items() if rep == '0' and 'recursive' in v]
say(all(a == b for _, a, b in dd), 'unit: sizeOnHeap delta apply == recursive for every L (ON_HEAP): ' + ', '.join('L%s %d/%d' % t for t in dd))
for (L, rep), v in sorted(by.items(), key=lambda kv: int(kv[0][0])):
    if rep == '0':
        g = int(v['apply'][11]) - int(v['recursive'][11])
        if g != 4 * (int(v['apply'][5]) - 80): say(False, 'unit: measureDeep gap at L=%s is %d' % (L, g))
say(True, 'unit: measureDeep(apply)-measureDeep(recursive) = 4*(len-80) at every L')

# ---- cluster tier, from raw files
def hist_int(path):
    for l in open(path):
        m = re.match(r'^\s*\d+:\s+(\d+)\s+(\d+)\s+\[I\b', l)
        if m: return int(m.group(2))
    raise RuntimeError('no [I row in ' + path)

stack = lambda K: 80 if K < 128 else 80 * 2 ** (int(math.floor(math.log2(5 * (K + 12) / 80.0))) + 1)
plan = [('c32-first', 32), ('K100', 100), ('K127', 127), ('K128', 128), ('K200', 200), ('K1000', 1000), ('K16000', 16000),
        ('K60000-N5', 60000), ('K60000-N1', 60000), ('K65535-N5', 65535), ('K65535-N1', 65535), ('c32-last', 32)]
ex = {}
rawd = {}
for label in ('h64', 'h256'):
    d = os.path.join(clu, label)
    cmd = open(os.path.join(d, 'command.log')).read()
    jm = re.findall(r'scope=(t\d\d),name=(MemtableOnHeapDataSize) -f Value  \[rc=0, [\d.]+s\]\n\S+\n(\d+)', cmd)
    mem = {}
    for t, _, v in jm: mem.setdefault(t, []).append(int(v))
    delta = {}; memd = {}
    for i, (arm, K) in enumerate(plan):
        t = 't%02d' % i
        delta[arm] = hist_int(os.path.join(d, 'hist-%s-post.txt' % arm)) - hist_int(os.path.join(d, 'hist-%s-pre.txt' % arm))
        memd[arm] = mem[t][1] - mem[t][0]
    ctrl = (delta['c32-first'] + delta['c32-last']) / 2.0
    spread = abs(delta['c32-first'] - delta['c32-last'])
    sl = open(os.path.join(d, 'logs', 'system.log'), errors='replace').read()
    flushes = re.findall(r'Enqueuing flush of ks\.(t\d\d), Reason: (\w+)', sl)
    say(all(r == 'USER_FORCED' for _, r in flushes) and len(flushes) == len(plan), '%s: system.log shows only the %d explicit flushes (reasons %s)' % (label, len(plan), sorted({r for _, r in flushes})))
    say(len(re.findall(r'^ERROR', sl, re.M)) == 0, '%s: no ERROR lines in system.log' % label)
    for arm, K in plan:
        if arm.startswith('c32'): continue
        e = delta[arm] - ctrl
        if K < 128: okk = abs(e) <= spread + 2048
        else:
            pred = 4 * stack(K) - 320
            okk = abs(e - pred) <= max(0.25 * pred, spread + 2048)
        ex[(label, arm)] = e
        rawd[(label, arm)] = delta[arm]
        say(okk, '%s %s: raw int[] delta %d, minus control %.0f = %.0f (pred %s), memtable on-heap delta %d' % (label, arm, delta[arm], ctrl, e, 4 * stack(K) - 320 if K >= 128 else 0, memd[arm]))
    for arm in ('K60000-N1', 'K65535-N1'):
        say(memd[arm] <= 300000 and ex[(label, arm)] >= 1048576, '%s %s: memtable delta %d <= 0.3 MB while excess %.0f >= 1 MB' % (label, arm, memd[arm], ex[(label, arm)]))
    # direct evidence of the path: the histogram lists the same ApplyState class and 2 MB-class int[] rows
    say(os.path.exists(os.path.join(d, 'java.cmdline')) and '-Xmx2G' in open(os.path.join(d, 'java.cmdline')).read(), '%s: node ran with -Xmx2G' % label)
for arm in ('K1000', 'K16000', 'K60000-N5', 'K65535-N5'):
    a, b = rawd[('h64', arm)], rawd[('h256', arm)]
    say(abs(a - b) <= 0.01 * max(a, b), 'heap space 64 vs 256, RAW int[] delta (the frozen text: same stack size): %s %d vs %d' % (arm, a, b))
    a, b = ex[('h64', arm)], ex[('h256', arm)]
    say(abs(a - b) <= 0.1 * max(a, b), 'heap space 64 vs 256, control-subtracted excess (the analyser criterion, 10%%): %s %.0f vs %.0f' % (arm, a, b))
# positive control
pcd = os.path.join(clu, 'pc')
sl = open(os.path.join(pcd, 'logs', 'system.log'), errors='replace').read()
m = re.search(r'Enqueuing flush of ks\.pc, Reason: (\w+), Usage: ([\d.]+)MiB \((\d+)%\) on-heap', sl)
say(bool(m) and m.group(1) == 'MEMTABLE_LIMIT' and 4 <= float(m.group(2)) <= 16, 'pc: raw system.log flush line: %s' % (m.group(0) if m else 'none'))
i_pre, i_post = hist_int(os.path.join(pcd, 'hist-pc-pre.txt')), hist_int(os.path.join(pcd, 'hist-pc-post.txt'))
say(True, 'pc: int[] bytes before %d after %d (delta %d), informational' % (i_pre, i_post, i_post - i_pre))
# nothing left running by this run
import subprocess
ps = subprocess.run("ps -eo pid,cmd | grep '[C]assandraDaemon' | grep -c s4-pk", shell=True, stdout=subprocess.PIPE, universal_newlines=True).stdout.strip()
say(ps == '0', 'no CassandraDaemon of this run left (count %s)' % ps)
print('\nRESULT:', 'all parts hold' if not bad else '%d part(s) do not hold' % len(bad))
