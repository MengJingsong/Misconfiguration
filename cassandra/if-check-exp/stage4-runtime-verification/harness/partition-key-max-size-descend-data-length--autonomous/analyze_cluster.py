#!/usr/bin/env python3
"""Cluster-tier analyser: arms.csv (labels h64, h256) and poscontrol.csv against the frozen B3f / B3i.3-5 predictions.
Usage: analyze_cluster.py <clusterdir> [depth_extra]   (clusterdir holds h64/, h256/, pc/); writes <clusterdir>/summary.txt"""
import csv, os, sys

root = sys.argv[1]
EXTRA = int(sys.argv[2]) if len(sys.argv) > 2 else 12     # DecoratedKey depth = K + EXTRA (unit tier, B2i.3)
lines = []
def check(name, ok, detail):
    lines.append('CHECK %-44s %s  %s' % (name, 'PASS' if ok else 'FAIL', detail))

def stack_len(K):
    if K < 128: return 80
    n = 80; d = K + EXTRA
    while 5 * d >= n: n *= 2
    return n

def load(label):
    with open(os.path.join(root, label, 'arms.csv')) as f:
        return {r['arm']: {k: (int(v) if v.lstrip('-').isdigit() else v) for k, v in r.items()} for r in csv.DictReader(f)}

res = {}
for label in ('h64', 'h256'):
    A = load(label)
    c1 = A['c32-first']['int_post'] - A['c32-first']['int_pre']; c2 = A['c32-last']['int_post'] - A['c32-last']['int_pre']
    ctrl = (c1 + c2) / 2.0; spread = abs(c1 - c2)
    lines.append('[%s] control deltas: first=%d last=%d mean=%.0f spread=%d' % (label, c1, c2, ctrl, spread))
    ex = {}
    for arm, r in A.items():
        K, N = r['K'], r['N']
        d = r['int_post'] - r['int_pre']; excess = d - ctrl
        pred = 4 * stack_len(K) - 320 if K >= 128 else 0
        mem = r['onheap_post'] - r['onheap_pre']
        dropped = r['int_post'] - r['int_flush']
        ex[arm] = excess
        lines.append('  %-10s K=%-5d N=%d predicted stack %d B (len %d) | int[] delta %d, excess over control %.0f (pred %d) | memtable on-heap delta %d | flush drop %d | ApplyState %d->%d->%d | flush-before-explicit %d'
                     % (arm, K, N, 4 * stack_len(K), stack_len(K), d, excess, pred, mem, dropped, r['applystate_pre'], r['applystate_post'], r['applystate_flush'], r['flush_logged_before_explicit']))
        if arm.startswith('c32'): continue
        if K <= 127:
            check('[%s] %s excess within control spread+2KB' % (label, arm), abs(excess) <= spread + 2048, 'excess=%.0f spread=%d' % (excess, spread))
        else:
            tol = max(0.25 * pred, spread + 2048)
            check('[%s] %s excess within 25%% of 4*len-320' % (label, arm), abs(excess - pred) <= tol, 'excess=%.0f pred=%d tol=%.0f' % (excess, pred, tol))
            if K >= 1000:
                check('[%s] %s stack leaves with the memtable (flush drop)' % (label, arm), abs(dropped - pred) <= max(0.25 * pred, spread + 2048), 'drop=%d pred=%d' % (dropped, pred))
        check('[%s] %s no flush before explicit' % (label, arm), r['flush_logged_before_explicit'] == 0, str(r['flush_logged_before_explicit']))
    for arm in ('K60000-N1', 'K65535-N1'):
        r = A[arm]; mem = r['onheap_post'] - r['onheap_pre']
        check('[%s] %s excess >= 1.0 MB, memtable delta <= 0.3 MB' % (label, arm), ex[arm] >= 1048576 and mem <= 300000, 'excess=%.0f memtable=%d' % (ex[arm], mem))
        check('[%s] %s memtable NOT within 0.2 MB of excess (not-accounted)' % (label, arm), mem < ex[arm] - 200000, 'memtable=%d excess=%.0f' % (mem, ex[arm]))
    check('[%s] N=1 vs N=5 at K=60000 same stack within 10%%' % label, abs(ex['K60000-N1'] - ex['K60000-N5']) <= 0.10 * ex['K60000-N5'], 'N1=%.0f N5=%.0f' % (ex['K60000-N1'], ex['K60000-N5']))
    check('[%s] N=5 memtable delta scales with N (K=60000)' % label, A['K60000-N5']['onheap_post'] - A['K60000-N5']['onheap_pre'] > 2 * (A['K60000-N1']['onheap_post'] - A['K60000-N1']['onheap_pre']), 'N5=%d N1=%d' % (A['K60000-N5']['onheap_post'] - A['K60000-N5']['onheap_pre'], A['K60000-N1']['onheap_post'] - A['K60000-N1']['onheap_pre']))
    res[label] = ex
for arm in res['h64']:
    if arm.startswith('c32') or int(arm.replace('K', '').split('-')[0]) < 1000: continue
    a, b = res['h64'][arm], res['h256'][arm]
    check('heap space 64 vs 256 MiB, %s same stack (10%%)' % arm, abs(a - b) <= 0.10 * max(a, b), '64MiB=%.0f 256MiB=%.0f' % (a, b))
# positive control
pc = list(csv.DictReader(open(os.path.join(root, 'pc', 'poscontrol.csv'))))
last = pc[-1]
lines.append('[pc] last row: writes=%s onheap=%s flush lines=%s memtable_limit=%s' % (last['writes'], last['onheap'], last['enqueued_flush_lines'], last['reason_memtable_limit']))
check('[pc] flush by MEMTABLE_LIMIT logged', last['reason_memtable_limit'] == 'True', last['reason_memtable_limit'])
peak = max(int(r['onheap']) for r in pc)   # the row after the flush reads the new, empty memtable
fl = open(os.path.join(root, 'pc', 'poscontrol.flushlines')).read().strip().splitlines()
lines.append('[pc] flush log line: ' + (fl[0].split(' - ')[-1] if fl else 'none'))
check('[pc] peak on-heap charge before the flush in 4..16 MiB', 4 * 2**20 <= peak <= 16 * 2**20, 'peak=%d' % peak)
lines.append('[pc] ' + open(os.path.join(root, 'pc', 'poscontrol.summary')).read().strip())
open(os.path.join(root, 'summary.txt'), 'w').write('\n'.join(lines) + '\n')
print('\n'.join(lines))
