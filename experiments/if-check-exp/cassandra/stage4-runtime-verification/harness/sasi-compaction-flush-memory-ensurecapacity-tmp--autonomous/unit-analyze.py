#!/usr/bin/env python3
"""Unit-tier analysis. Usage: python3 -I unit-analyze.py <outdir with cells/>  -> prints tables (also written to <outdir>/unit-summary.txt).
Reads only the raw files: cells/*/p1.csv, cells/*/p2_*.csv and each cell's Byteman trace.txt. No verdict here."""
import sys, os, re, glob, collections
out = sys.argv[1]
lines = []
def say(s=''):
    print(s); lines.append(s)
def groups(trace):
    """list of dicts per sort call: alen, init, grows (list of tmplen), t0, t1, thr"""
    gs = {}; order = []
    cur = {}
    for l in open(trace):
        m = re.match(r'(\w+) ms=(\d+) thr=(\S+) alen=(\d+)(?: tmplen=(\d+))?', l)
        if not m: continue
        k, ms, thr, alen, tl = m.group(1), int(m.group(2)), m.group(3), int(m.group(4)), m.group(5)
        if k == 'SORT_BEGIN':
            g = dict(alen=alen, thr=thr, t0=ms, t1=None, init=None, grows=[]); cur[thr] = g; order.append(g)
        elif k == 'SORT_END':
            cur[thr]['t1'] = ms
        elif k == 'TMP_INIT':
            cur[thr]['init'] = int(tl)
        elif k == 'TMP_GROW':
            cur[thr]['grows'].append(int(tl))
    return order
def kv(line):
    d = {}
    for f in line.strip().split(',')[1:]:
        k, v = f.split('=', 1); d[k] = v
    return d

say('== Part 1: LongTimSort tmp (Byteman trace) against the array ==')
c = out + '/cells/p1'
if os.path.exists(c + '/p1.csv'):
    rows = [l.strip().split(',') for l in open(c + '/p1.csv') if l.startswith('P1,')]
    gs = groups(c + '/trace.txt')
    gs = gs[1:]          # sort number 0 is the warm-up
    say('rows in csv %d, sort groups after warm-up %d' % (len(rows), len(gs)))
    say('%-10s %-11s %3s %9s %12s %12s %12s %8s %s' % ('n', 'shape', 'rep', 'ms', 'init_longs', 'max_tmp_lg', 'cap_longs', 'tmp/cap', 'sorted_ok'))
    bad = 0
    for r, g in zip(rows, gs):
        _, seq, n, shape, rep, ms, alloc, ok = r
        n = int(n); assert g['alen'] == n, (g['alen'], n)
        mx = max([g['init']] + g['grows']); cap = n >> 1
        say('%-10d %-11s %3s %9s %12d %12d %12d %8.3f %s' % (n, shape, rep, ms, g['init'], mx, cap, mx / cap, ok))
        if mx > cap: bad += 1
    say('groups with max tmp > a.length>>>1: %d' % bad)
else:
    say('no p1 cell')

say(); say('== Part 2: SASI segment build ==')
say('%-9s %4s %5s %3s %8s %11s %10s %10s %10s %7s %9s %7s %12s %s' % ('mode', 'M', 'L', 'rep', 'N', 'chars', 'overshoot', 'sortAlen', 'maxTmpLg', 'incMiB', 'inc/M', 'B/char', 'alloc/char', 'file_len'))
for d in sorted(glob.glob(out + '/cells/p2_*')):
    csvs = glob.glob(d + '/p2_*.csv')
    if not csvs: say('%s: no csv (%s)' % (os.path.basename(d), open(d + '/jvm.log').read()[-200:].replace('\n', ' ') if os.path.exists(d + '/jvm.log') else '')); continue
    recs = [kv(l) for l in open(csvs[0]) if l.startswith('P2,')]
    gs = groups(d + '/trace.txt') if os.path.exists(d + '/trace.txt') else []
    if len(recs) > 1: gs = gs[1:]     # a warm-up build ran first
    for i, r in enumerate(recs):
        M = int(r['M_mib']); L = int(r['L']); chars = int(r['chars']); inc = int(r['increment'])
        g = gs[i] if i < len(gs) else None
        sal = g['alen'] if g else 0
        mt = max([g['init']] + g['grows']) if g else 0
        say('%-9s %4d %5d %3s %8s %11d %10s %10d %10d %7.1f %9.2f %7.2f %12.0f %s' % (r['mode'], M, L, r['rep'], r['N'], chars, r['overshoot'], sal, mt, inc / 1048576, inc / (M * 1048576), inc / chars, int(r['thread_alloc_bytes']) / chars, r['file_len']))
open(out + '/unit-summary.txt', 'w').write('\n'.join(lines) + '\n')
