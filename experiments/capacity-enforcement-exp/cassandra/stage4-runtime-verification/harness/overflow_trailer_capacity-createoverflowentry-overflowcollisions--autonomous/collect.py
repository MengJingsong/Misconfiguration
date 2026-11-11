#!/usr/bin/env python3
"""Copies the small excerpts of a run into the repository's results/<stem>/run1/ (full logs stay on the node).
usage: collect.py <node run1 dir> <repo run1 dir>
 - unit/*.out, unit-summary / analysis / selfcheck outputs if present (top level *.txt)
 - per cluster arm: the small text files; system.log -> system-log-excerpt.txt (ERROR/AssertionError/Flushed index segment (first 3 + count)/
   Scheduling index flush/flush lines of ks.t/Can't open); disk.csv and heap.csv decimated to one line in 15; gc.log -> gc-pauses-summary.txt
   (count, max post-collection occupancy); cmdlog.txt -> cmdlog-head.txt (first 60 lines)."""
import os, re, shutil, sys
src, dst = sys.argv[1], sys.argv[2]
SMALL = ['schema.txt', 'proc-args.txt', 'yaml-lines.txt', 'jvm-extra.txt', 'windows.txt', 'sizes.txt', 'ls-sstable-dir.txt', 'ls-before-compact.txt',
         'tablestats.txt', 'tablestats-before-compact.txt', 'byteman.txt', 'log-errors.txt', 'token-groups.txt', 'index-query.txt', 'collkeys.txt',
         'classload-ondiskindex.txt', 'compact.txt', 'stress-summary.txt', 'inserts.out']
os.makedirs(dst, exist_ok=True)
def cp(a, b):
    if os.path.exists(a):
        os.makedirs(os.path.dirname(b), exist_ok=True)
        if os.path.getsize(a) > 150000:
            lines = open(a, errors='replace').read().splitlines()
            open(b, 'w').write('\n'.join(lines[:60]) + '\n... (%d lines in all; head only)\n' % len(lines))
        else: shutil.copyfile(a, b)
for f in os.listdir(src):
    p = os.path.join(src, f)
    if os.path.isfile(p) and f.endswith(('.txt', '.out')) and os.path.getsize(p) < 200000: cp(p, os.path.join(dst, f))
u = os.path.join(src, 'unit')
if os.path.isdir(u):
    for f in sorted(os.listdir(u)):
        if f.endswith('.out'): cp(os.path.join(u, f), os.path.join(dst, 'unit', f))
        if f.endswith('.log') and os.path.getsize(os.path.join(u, f)) < 20000: cp(os.path.join(u, f), os.path.join(dst, 'unit', f))
c = os.path.join(src, 'cluster')
if os.path.isdir(c):
    for arm in sorted(os.listdir(c)):
        a = os.path.join(c, arm)
        if not os.path.isdir(a): continue
        o = os.path.join(dst, 'cluster', arm)
        for f in SMALL: cp(os.path.join(a, f), os.path.join(o, f))
        if os.path.exists(a + '/cmdlog.txt'):
            open(o + '/cmdlog-head.txt', 'w').write(''.join(open(a + '/cmdlog.txt', errors='replace').readlines()[:60]))
        for f in ('disk.csv', 'heap.csv'):
            if os.path.exists(os.path.join(a, f)):
                L = open(os.path.join(a, f)).read().splitlines()
                open(os.path.join(o, f.replace('.csv', '-decimated.csv')), 'w').write('\n'.join([L[0]] + L[1::15]) + '\n')
        sl = os.path.join(a, 'system.log')
        if os.path.exists(sl):
            keep, seg = [], 0
            for l in open(sl, errors='replace'):
                if 'Flushed index segment' in l:
                    seg += 1
                    if seg <= 3: keep.append(l)
                elif re.search(r"^ERROR|AssertionError|Scheduling index flush|Index flush to|Can't open index|Enqueuing flush of ks\.t|Failed to", l): keep.append(l[:300])
            keep.append('... "Flushed index segment" lines in the whole log: %d\n' % seg)
            open(o + '/system-log-excerpt.txt', 'w').write(''.join(keep[:80]))
        gl = os.path.join(a, 'gc.log')
        if os.path.exists(gl):
            n = 0; best = 0
            for l in open(gl, errors='replace'):
                m = re.search(r'Pause.*?(\d+)M->(\d+)M\(', l)
                if m: n += 1; best = max(best, int(m.group(2)))
            open(o + '/gc-pauses-summary.txt', 'w').write('pause lines %d, max post-collection occupancy %d MiB (whole run)\n' % (n, best))
print('collected', src, '->', dst)
